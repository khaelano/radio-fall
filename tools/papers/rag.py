#!/usr/bin/env python3
"""
RAG CLI -- Semantic search across the radio-fall-detection paper library.

Zero dependencies beyond numpy + Python stdlib. TF-IDF vector space model
with cosine similarity. Supports bilingual queries (EN + ID).

Usage:
    python3 tools/papers/rag.py index              # Build / rebuild index
    python3 tools/papers/rag.py query "your question"  # Search
    python3 tools/papers/rag.py list               # Indexed documents
    python3 tools/papers/rag.py status             # Index stats
    python3 tools/papers/rag.py check              # md files missing from tools/papers/index.json
    python3 tools/papers/rag.py query "..." --top 10  # More results
    python3 tools/papers/rag.py query "..." --no-snippet  # Titles only
"""

import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_DIR = Path(__file__).resolve().parent / ".rag-index"
INDEX_FILE = INDEX_DIR / "index.npz"
META_FILE = INDEX_DIR / "meta.json"
CATALOG_FILE = Path(__file__).resolve().with_name("index.json")

# Directories to index (relative to project root). Order by priority.
SOURCE_DIRS = [
    "resources/Papers/md",
]

# Chunking
MAX_CHUNK_LINES = 150  # Split long docs by this many lines
MIN_CHUNK_LINES = 20   # Below this, keep as whole doc
TOP_K = 5              # Default results
SNIPPET_LINES = 8      # Lines of context per result

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    """Simple language-agnostic tokenizer: lowercase, split on non-alphanum."""
    text = text.lower()
    # Keep alphanumeric and underscore, split everything else
    tokens = re.findall(r"[a-z0-9_]+", text)
    # Filter very short tokens (noise) and very long ones
    return [t for t in tokens if 2 <= len(t) <= 40]


def tokenize_with_ngrams(text: str, n: int = 3) -> list[str]:
    """Tokens plus character n-grams for fuzzy/partial matching across languages."""
    tokens = tokenize(text)
    grams = set()
    for t in tokens:
        if len(t) >= n:
            for i in range(len(t) - n + 1):
                grams.add(f"__gram_{t[i:i+n]}")
    return tokens + list(grams)


# ---------------------------------------------------------------------------
# Document source
# ---------------------------------------------------------------------------
def find_markdown_files() -> list[dict]:
    """Scan SOURCE_DIRS for .md files, return list of {path, rel, label, size}."""
    docs = []
    for rel_dir in SOURCE_DIRS:
        full_path = PROJECT_ROOT / rel_dir
        if not full_path.exists():
            continue
        for fpath in sorted(full_path.rglob("*.md")):
            rel = fpath.relative_to(PROJECT_ROOT)
            label = str(rel)
            size = fpath.stat().st_size
            if size == 0:
                continue
            docs.append({
                "path": str(fpath),
                "rel": str(rel),
                "label": label,
                "size": size,
            })
    return docs


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def chunk_document(text: str, source: dict) -> list[dict]:
    """Split a markdown file into searchable chunks."""
    lines = text.split("\n")
    total_lines = len(lines)

    # Small doc: keep as one chunk
    if total_lines <= MAX_CHUNK_LINES:
        return [{
            "text": text,
            "source": source["rel"],
            # For display, use first meaningful line
            "heading": extract_heading(lines) or source["rel"],
            "line_start": 0,
            "line_end": total_lines,
        }]

    # Large doc: split by sections (## headings) or line blocks
    chunks = []
    section_starts = []
    for i, line in enumerate(lines):
        if line.startswith("## ") or line.startswith("### "):
            section_starts.append(i)

    if section_starts and section_starts[0] > MIN_CHUNK_LINES:
        section_starts.insert(0, 0)

    if not section_starts:
        section_starts = [0]

    # Build chunks from section boundaries, subdivide if too long
    for idx in range(len(section_starts)):
        start = section_starts[idx]
        end = section_starts[idx + 1] if idx + 1 < len(section_starts) else total_lines

        if end - start <= MAX_CHUNK_LINES:
            chunk_text = "\n".join(lines[start:end])
            chunks.append({
                "text": chunk_text,
                "source": source["rel"],
                "heading": extract_heading(lines[start:start+3]) or source["rel"],
                "line_start": start,
                "line_end": end,
            })
        else:
            # Subdivide long section
            for sub_start in range(start, end, MAX_CHUNK_LINES):
                sub_end = min(sub_start + MAX_CHUNK_LINES, end)
                chunk_text = "\n".join(lines[sub_start:sub_end])
                chunks.append({
                    "text": chunk_text,
                    "source": source["rel"],
                    "heading": extract_heading(lines[sub_start:sub_start+3]) or source["rel"],
                    "line_start": sub_start,
                    "line_end": sub_end,
                })

    return chunks


def extract_heading(lines: list[str]) -> str | None:
    """Return first # or ## heading found in lines."""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
    return None


# ---------------------------------------------------------------------------
# TF-IDF Vectorizer (pure Python + numpy)
# ---------------------------------------------------------------------------
class TfidfVectorizer:
    def __init__(self):
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self.doc_norms: np.ndarray | None = None

    def fit(self, texts: list[str]):
        """Build vocabulary and compute IDF from a list of documents."""
        n_docs = len(texts)
        df = Counter()  # document frequency per term

        all_tokens = []
        for text in texts:
            tokens = tokenize_with_ngrams(text)
            all_tokens.append(tokens)
            df.update(set(tokens))

        # With a tiny corpus (1-2 docs), terms appear once per doc; keep them
        # so queries work before the library grows. Raise the floor once
        # enough documents exist to make single-occurrence terms noise.
        min_df = 1 if n_docs < 3 else 2

        # Build vocabulary (exclude terms that appear in every doc or only one)
        self.vocab = {}
        for term, freq in df.items():
            # Remove too-rare or too-common terms
            if freq < min_df or (n_docs >= 2 and freq > n_docs * 0.95):
                continue
            if len(term) > 40 or term.startswith("__gram_") and freq < 3:
                continue
            self.vocab[term] = len(self.vocab)

        # Compute IDF
        self.idf = np.zeros(len(self.vocab), dtype=np.float64)
        for term, idx in self.vocab.items():
            self.idf[idx] = math.log((n_docs + 1) / (df[term] + 1)) + 1.0

        print(f"[index] Vocabulary: {len(self.vocab)} terms", file=sys.stderr)

    def transform(self, texts: list[str]) -> np.ndarray:
        """Convert texts to TF-IDF matrix (n_docs x n_vocab)."""
        n_docs = len(texts)
        matrix = np.zeros((n_docs, len(self.vocab)), dtype=np.float32)

        for i, text in enumerate(texts):
            tokens = tokenize_with_ngrams(text)
            tf = Counter(tokens)
            # Log-normalized TF
            for term, count in tf.items():
                if term in self.vocab:
                    idx = self.vocab[term]
                    matrix[i, idx] = (1 + math.log(count)) * self.idf[idx]

        # L2 normalize rows
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms

        return matrix

    def transform_query(self, text: str) -> np.ndarray:
        """Convert query to TF-IDF vector (same weighting as documents)."""
        tokens = tokenize_with_ngrams(text)
        tf = Counter(tokens)
        vec = np.zeros((1, len(self.vocab)), dtype=np.float32)
        for term, count in tf.items():
            if term in self.vocab:
                idx = self.vocab[term]
                vec[0, idx] = (1 + math.log(count)) * self.idf[idx]
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------
def build_index():
    """Scan vault, chunk documents, compute TF-IDF, save to disk."""
    print("Scanning markdown files...", file=sys.stderr)
    sources = find_markdown_files()

    if not sources:
        print("No markdown files found.", file=sys.stderr)
        for f in (INDEX_FILE, META_FILE):
            if f.exists():
                f.unlink()
        return

    print(f"Found {len(sources)} files", file=sys.stderr)

    # Chunk all documents
    chunks = []
    for src in sources:
        try:
            with open(src["path"], "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            print(f"  [skip] {src['rel']}: {e}", file=sys.stderr)
            continue
        doc_chunks = chunk_document(text, src)
        chunks.extend(doc_chunks)

    if not chunks:
        print("No chunks produced.", file=sys.stderr)
        return

    print(f"Indexing {len(chunks)} chunks...", file=sys.stderr)

    # Build TF-IDF
    vec = TfidfVectorizer()
    texts = [c["text"] for c in chunks]
    vec.fit(texts)
    matrix = vec.transform(texts)

    # Save
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(INDEX_FILE), matrix=matrix, vocab_ids=np.array(list(vec.vocab.values())), idf=vec.idf)

    meta = {
        "vocab": list(vec.vocab.keys()),
        "chunks": [
            {"source": c["source"], "heading": c["heading"], "line_start": c["line_start"], "line_end": c["line_end"]}
            for c in chunks
        ],
        "build_time": time.time(),
        "n_docs": len(sources),
        "n_chunks": len(chunks),
        "n_vocab": len(vec.vocab),
    }
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Index saved: {len(chunks)} chunks, {len(vec.vocab)} terms, {len(sources)} files.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Query engine
# ---------------------------------------------------------------------------
def load_index():
    """Load saved index, return (vectorizer, chunks, matrix)."""
    if not INDEX_FILE.exists() or not META_FILE.exists():
        print("No index found. Run 'python3 tools/papers/rag.py index' first.", file=sys.stderr)
        sys.exit(1)

    data = np.load(str(INDEX_FILE))
    matrix = data["matrix"]

    with open(META_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Reconstruct vectorizer
    vec = TfidfVectorizer()
    vec.vocab = dict(zip(meta["vocab"], data["vocab_ids"]))
    vec.idf = data["idf"]

    chunks = meta["chunks"]

    return vec, chunks, matrix, meta


def query(search_text: str, top_k: int = TOP_K, show_snippet: bool = True):
    """Search indexed documents, print results."""
    vec, chunks, matrix, meta = load_index()

    query_vec = vec.transform_query(search_text)
    if query_vec.sum() == 0:
        print("No matching terms found. Try different keywords.", file=sys.stderr)
        return

    # Cosine similarity (dot product since vectors are L2-normalized)
    scores = matrix @ query_vec.T
    scores = scores.flatten()

    # Get top-k indices
    if len(scores) < top_k:
        top_k = len(scores)
    top_indices = np.argsort(scores)[::-1][:top_k]

    # Filter zero-score results
    top_indices = [i for i in top_indices if scores[i] > 0]
    if not top_indices:
        print("No relevant results found. Try different keywords or run 'python3 tools/papers/rag.py index'.", file=sys.stderr)
        return

    print(f"Query: {search_text}")
    print(f"Results: {len(top_indices)} matches\n")

    for rank, idx in enumerate(top_indices[:top_k], 1):
        chunk = chunks[idx]
        score = scores[idx]
        source_file = chunk["source"]
        heading = chunk["heading"] or "(no heading)"

        print(f"{rank}. [{score:.3f}] {source_file}")
        print(f"   Section: {heading}")

        if show_snippet and idx < len(chunks):
            # Load the source file and extract snippet
            full_path = PROJECT_ROOT / source_file
            if full_path.exists():
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                    start = chunk["line_start"]
                    end = min(chunk["line_end"], len(all_lines))
                    snippet_lines = all_lines[start:end]

                    # Trim to snippet length, centered on most relevant part
                    snippet = "".join(snippet_lines[:SNIPPET_LINES]).strip()
                    if snippet:
                        # Truncate long lines
                        formatted = []
                        for line in snippet.split("\n"):
                            if len(line) > 120:
                                line = line[:117] + "..."
                            formatted.append(line)
                        print(f"   Context:")
                        for line in formatted[:SNIPPET_LINES]:
                            print(f"     {line}")
                except Exception:
                    pass

        print()

    # Also show which source directories contributed
    sources_used = set()
    for idx in top_indices[:top_k]:
        sources_used.add(chunks[idx]["source"].split("/")[0])
    print(f"Sources: {', '.join(sorted(sources_used))}")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
def cmd_list():
    """List all indexed documents."""
    sources = find_markdown_files()
    if not sources:
        print("No markdown files found.")
        return

    print(f"Markdown resources ({len(sources)} files):\n")
    by_dir = defaultdict(list)
    for s in sources:
        parts = s["rel"].split("/")
        top = parts[0] if len(parts) > 1 else "root"
        by_dir[top].append(s)

    for dirname, files in sorted(by_dir.items()):
        print(f"  {dirname}/ ({len(files)} files)")
        for f in files:
            size_kb = f["size"] / 1024
            print(f"    {f['rel']:70s} {size_kb:7.1f} KB")
        print()


def cmd_status():
    """Show index statistics."""
    sources = find_markdown_files()
    total_size = sum(s["size"] for s in sources)

    print(f"resources: {len(sources)} markdown files, {total_size / 1024:.0f} KB total")

    by_dir = Counter(s["rel"].split("/")[0] for s in sources)
    for dirname, count in sorted(by_dir.items()):
        print(f"  {dirname}: {count} files")

    if INDEX_FILE.exists() and META_FILE.exists():
        with open(META_FILE) as f:
            meta = json.load(f)
        data = np.load(str(INDEX_FILE))
        matrix = data["matrix"]
        print(f"\nIndex: {meta['n_chunks']} chunks, {meta['n_vocab']} terms")
        print(f"  Matrix shape: {matrix.shape[0]} x {matrix.shape[1]}")
        print(f"  Built: {time.ctime(meta['build_time'])}")
    else:
        print("\nIndex: not built yet. Run 'python3 tools/papers/rag.py index'.")


def cmd_check():
    """Report markdown files missing from the tools/papers/index.json catalog."""
    sources = find_markdown_files()
    if not sources:
        print("No markdown files found.")
        return 0

    cataloged = set()
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        for paper in catalog.get("papers", []):
            file_field = paper.get("file") or ""
            if file_field.startswith("Papers/"):
                cataloged.add(f"resources/{file_field}")
            elif file_field:
                cataloged.add(file_field)

    missing = [s["rel"] for s in sources if s["rel"] not in cataloged]
    if missing:
        print(f"{len(missing)} markdown file(s) not cataloged in tools/papers/index.json:")
        for rel in missing:
            print(f"  {rel}")
        return 1
    print(f"All {len(sources)} markdown file(s) cataloged in tools/papers/index.json.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "index":
        build_index()

    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: python3 tools/papers/rag.py query \"your question\"")
            return
        query_text = sys.argv[2]

        # Parse optional args
        top_k = TOP_K
        show_snippet = True
        for i, arg in enumerate(sys.argv[3:], 3):
            if arg == "--top" and i + 1 < len(sys.argv):
                top_k = int(sys.argv[i + 1])
            elif arg == "--no-snippet":
                show_snippet = False

        query(query_text, top_k=top_k, show_snippet=show_snippet)

    elif cmd == "list":
        cmd_list()

    elif cmd == "status":
        cmd_status()

    elif cmd == "check":
        sys.exit(cmd_check())

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
