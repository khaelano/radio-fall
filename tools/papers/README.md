# Local paper library

`resources/Papers/` is a local, ignored literature library. Create it when
setting up the paper tools; keep its files out of Git.

- `*.pdf` — raw papers
- `md/` — converted Markdown, one file per paper
- `tools/papers/index.json` — metadata catalog

## Workflow

1. Create the library and add a PDF: `mkdir -p resources/Papers`.
2. Convert it: `python3 tools/papers/pdf2md.py <paper.pdf>` (docling default; use `--fast` for clean-text PDFs, `--force-ocr` for scanned/garbled ones).
3. Add a metadata entry to `tools/papers/index.json` (schema below).
4. Rebuild the search index: `python3 tools/papers/rag.py index`
5. Verify the catalog is complete: `python3 tools/papers/rag.py check`
6. Search: `python3 tools/papers/rag.py query "fall detection using WiFi CSI"`

## Catalog Schema (`tools/papers/index.json`)

Each entry in `papers` uses:

- `id` — short slug, e.g. `wifi-csi-fall-detection-2020`
- `title` — paper title
- `file` — `Papers/md/<name>.md`, relative to `resources/`
- `year` — publication year or `null`
- `methods` — list of methods, e.g. `["CNN", "WiFi CSI"]`
- `keywords` — list of search keywords
- `language` — `en` or `id`
- `lines` — line count of the markdown file
- `summary` — one-line summary
- `status` — `converted` or `pdf`
