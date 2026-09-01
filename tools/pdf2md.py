#!/usr/bin/env python3
"""
pdf2md.py -- PDF -> Markdown converter for the paper library.

Strategy:
  - Default: `docling convert` (layout-aware; handles two-column academic
    PDFs, tables, and OCR). Slower but accurate.
  - `--fast`: `pdftotext -layout` (poppler) -- ~0.1s/paper, works for clean
    text PDFs. Heading-like lines are promoted to markdown '##' so the RAG
    index (rag.py chunks on ## headings) keeps section-level search. Falls
    back to docling when the text layer is garbled (custom font encoding,
    control chars, or too little printable text).
  - If docling fails, a clean pdftotext extraction is written as a degraded
    fallback with a warning instead of aborting.

Usage:
    python3 tools/pdf2md.py <file.pdf> [more.pdf ...]    # docling conversion
    python3 tools/pdf2md.py --fast <file.pdf>            # pdftotext first, docling fallback
    python3 tools/pdf2md.py --out <dir> <file.pdf> ...
    python3 tools/pdf2md.py --force-ocr <file.pdf>       # force OCR in docling
    python3 tools/pdf2md.py --check <file.pdf>           # print text-layer verdict only
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "Resources" / "Papers" / "md"

# ---------------------------------------------------------------------------
# Text-layer quality check
# ---------------------------------------------------------------------------
# Garbage control chars: exclude \n \t \r \x0c (form feed = page separator in
# pdftotext) and \x08 (backspace overstrike used for bold). Everything else in
# the C0 range indicates custom font encoding (garbled text).
GARBAGE_CHARS = re.compile(r"[\x00-\x07\x0b\x0e-\x1f\x7f]")
BACKSPACE_PAIR = re.compile(r".\x08")


def extract_text_fast(pdf_path: str) -> str:
    """pdftotext -layout; returns '' on failure."""
    r = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, timeout=120,
    )
    return r.stdout if r.returncode == 0 else ""


def clean_overstrike(text: str) -> str:
    """Resolve backspace overstrike ('b\\x08bold' -> 'bold') common in pdftotext."""
    prev = None
    while prev != text:
        prev = text
        text = BACKSPACE_PAIR.sub("", text)
    return text


def is_clean_text(text: str) -> bool:
    """
    Heuristic: is the text layer usable without OCR?
    Reject if high-density garbage control chars (custom font encoding),
    or too little printable text (e.g. < 20% alphanumeric).
    """
    if not text.strip():
        return False
    n_garbage = len(GARBAGE_CHARS.findall(text))
    if n_garbage > max(50, 0.01 * len(text)):
        return False
    letters = sum(1 for c in text if c.isalnum())
    return letters / max(1, len(text)) > 0.20


# ---------------------------------------------------------------------------
# Heading promotion (pdftotext -> markdown)
# ---------------------------------------------------------------------------
KNOWN_HEADINGS = {
    "abstract", "introduction", "conclusion", "conclusions", "references",
    "acknowledgment", "acknowledgments", "appendix", "results", "discussion",
    "experiments", "experimental setup", "methodology", "related work",
    "background", "summary", "future work",
}

# Section numbering: "3", "3.1", "4.2.3", "A", "A.1", "I", "II".
# Word after the number must be a real word (>=3 chars) to avoid matching
# equation fragments like "1 XX" or "N Tn".
SECTION_NUM = re.compile(
    r"^(?:\d+(?:\.\d+){0,3}|[A-Z](?:\.\d+)*|(?:[IVXL]+)(?:\.\d+)*)\s+"
    r"[A-Z][a-z]{2,}"
)

# Title-case heading words: each >= 2 chars, at least 2 words, at least one
# word >= 5 chars (avoids equation/abbreviation fragments like "N Tn").
TITLE_CASE_HEADING = re.compile(r"^[A-Z][a-z]*(?:\s+[A-Z][a-z]*){1,5}$")


def _looks_like_heading(stripped: str) -> bool:
    if SECTION_NUM.match(stripped):
        return True
    if stripped.lower() in KNOWN_HEADINGS and len(stripped) <= 40:
        return True
    if TITLE_CASE_HEADING.match(stripped) and 5 <= len(stripped) <= 60:
        words = stripped.split()
        if len(words) >= 2 and all(len(w) >= 2 for w in words) \
                and any(len(w) >= 5 for w in words):
            return True
    return False


def promote_headings(lines: list[str]) -> list[str]:
    """Promote heading-like lines to markdown '## ' headings."""
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        # Skip blank / code-like / table lines
        if not stripped:
            out.append(line)
            continue

        is_heading = False
        if SECTION_NUM.match(stripped):
            is_heading = True
        elif stripped.lower() in KNOWN_HEADINGS and len(stripped) <= 40:
            is_heading = True
        elif _looks_like_heading(stripped):
            is_heading = True

        if is_heading:
            # Guard: never promote lines ending with sentence punctuation
            if stripped.endswith((".", "?", ":", ",", ";")):
                is_heading = False

        if is_heading:
            out.append(f"## {stripped}")
        else:
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# OCR fallback (docling)
# ---------------------------------------------------------------------------
def convert_with_docling(pdf_path: str, out_dir: Path, force_ocr: bool = False) -> bool:
    """Convert with docling. Returns True on success (output written by docling)."""
    if not shutil.which("docling"):
        print("[error] docling not found. Install: uv tool install docling", file=sys.stderr)
        return False
    cmd = [
        "docling", "convert", pdf_path,
        "--to", "md",
        "--output", str(out_dir),
        "--image-export-mode", "placeholder",
    ]
    if force_ocr:
        cmd.append("--force-ocr")
    print(f"[docling] converting {Path(pdf_path).name} (OCR={'on' if force_ocr else 'off'})...",
          file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        print(f"[docling] failed: {r.stderr[-500:]}", file=sys.stderr)
        return False
    return True


def find_docling_output(out_dir: Path, pdf_stem: str) -> Path | None:
    """Locate docling's output .md for a given source pdf stem."""
    for f in out_dir.rglob("*.md"):
        if pdf_stem[:30].lower() in f.stem.lower():
            return f
    return None


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------
def convert_one(pdf_path: Path, out_dir: Path, force_ocr: bool = False,
                fast: bool = False) -> bool:
    """Convert one PDF. Defaults to docling; `fast` tries pdftotext first."""
    pdf_stem = pdf_path.stem
    out_file = out_dir / f"{pdf_stem}.md"

    # 1. Fast path (only when explicitly requested)
    fast_text = ""
    if fast and not force_ocr:
        fast_text = extract_text_fast(str(pdf_path))
        if is_clean_text(fast_text):
            text = clean_overstrike(fast_text)
            lines = text.split("\n")
            md = promote_headings(lines)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file.write_text("\n".join(md) + "\n", encoding="utf-8")
            n = len(md)
            print(f"[ok] {pdf_stem} -> {out_file.name} ({n} lines, pdftotext)")
            return True
        print(f"[garbled] {pdf_stem}: text layer unusable, falling back to docling", file=sys.stderr)
    elif force_ocr:
        print(f"[force-ocr] {pdf_stem}")

    # 2. Docling (default)
    if convert_with_docling(str(pdf_path), out_dir, force_ocr=force_ocr):
        found = find_docling_output(out_dir, pdf_stem)
        if found and found != out_file:
            # docling writes its own filename; rename to match vault convention
            found.rename(out_file)
        print(f"[ok] {pdf_stem} -> {out_file.name} (docling)")
        return True

    # 3. Degraded fallback: clean pdftotext text with a warning
    if not fast_text:
        fast_text = extract_text_fast(str(pdf_path))
    if is_clean_text(fast_text):
        text = clean_overstrike(fast_text)
        lines = text.split("\n")
        md = promote_headings(lines)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text("\n".join(md) + "\n", encoding="utf-8")
        print(f"[warn] {pdf_stem}: docling failed; wrote pdftotext fallback "
              f"({len(md)} lines)", file=sys.stderr)
        return True

    print(f"[error] {pdf_stem}: docling failed and no usable text layer exists", file=sys.stderr)
    return False


def cmd_check(pdf_path: Path) -> int:
    text = extract_text_fast(str(pdf_path))
    if is_clean_text(text):
        print(f"CLEAN  {pdf_path.name}  ({len(text)} chars, pdftotext works)")
        return 0
    print(f"GARBLED {pdf_path.name}  (needs OCR: docling --force-ocr)")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid PDF -> Markdown converter")
    ap.add_argument("pdfs", nargs="+", help="PDF file(s) to convert")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    ap.add_argument("--fast", action="store_true",
                    help="try pdftotext first, fall back to docling")
    ap.add_argument("--force-ocr", action="store_true", help="skip pdftotext, force OCR")
    ap.add_argument("--check", action="store_true", help="only report text-layer quality")
    args = ap.parse_args()

    out_dir = Path(args.out)
    ok = True
    for pdf in args.pdfs:
        p = Path(pdf)
        if not p.exists():
            print(f"[skip] not found: {pdf}", file=sys.stderr)
            ok = False
            continue
        if args.check:
            rc = cmd_check(p)
            ok = ok and rc == 0
        else:
            done = convert_one(p, out_dir, force_ocr=args.force_ocr, fast=args.fast)
            ok = ok and done
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
