---
name: pdf-to-markdown
description: Convert research papers in the radio-fall-detection project from PDF to Markdown using Docling or the fast pdftotext path. Use when adding papers to Resources/Papers/ or converting PDFs for the thesis literature review.
---

# PDF to Markdown — radio-fall-detection

Convert PDF papers to clean Markdown for the thesis literature library. Docling handles layout (two-column academic PDFs, tables) and OCR; the `--fast` path is a quick fallback for clean text PDFs.

## Prerequisites

Docling must be installed:

```bash
uv tool install docling
docling --version
```

## Conversion

Run from the project root (`/home/khaelano/Projects/radio-fall-detection`).

### Default: docling (recommended)

```bash
python3 tools/papers/pdf2md.py Resources/Papers/<paper>.pdf
```

Output is written to `Resources/Papers/md/<paper>.md`.

### Fast path (clean text PDFs)

```bash
python3 tools/papers/pdf2md.py --fast Resources/Papers/<paper>.pdf
```

Tries `pdftotext -layout` first (~0.1s per paper) and promotes section headings to `##` for RAG chunking; falls back to docling if the text layer is garbled.

### Check text-layer quality first

```bash
python3 tools/papers/pdf2md.py --check Resources/Papers/*.pdf
```

Prints `CLEAN` or `GARBLED` per PDF.

### Scanned or garbled PDFs

```bash
python3 tools/papers/pdf2md.py --force-ocr Resources/Papers/<scanned>.pdf
```

## Options Reference

| Option | Effect |
|--------|--------|
| `--fast` | Use `pdftotext` first, docling fallback |
| `--force-ocr` | Force OCR in docling |
| `--check` | Only report text-layer quality |
| `--out <dir>` | Override output directory |

## Post-Conversion

1. Add a metadata entry to `tools/papers/index.json` (see `Resources/Papers/README.md`).
2. Rebuild the search index:

```bash
python3 tools/papers/rag.py index
```

3. Verify the catalog:

```bash
python3 tools/papers/rag.py check
```

## Common Issues

- **Docling fails or times out on a large PDF**: re-run with `--fast`; if the text layer is clean this still produces a usable file.
- **Garbled text in output**: re-run with `--force-ocr`.
- **Huge markdown files**: docling embeds images by default; `pdf2md.py` always uses `--image-export-mode placeholder` to keep files small.
