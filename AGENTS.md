# Repository Guidelines

## Project Overview

This repository supports a bachelor's thesis on fall detection for persons using radio waves (e.g., WiFi channel state information, radar, or ultra-wideband sensing). The project is in its early stages: the repository is currently empty and not yet initialized as a Git repository. These guidelines define how contributions should be organized once development begins.

## Project Structure & Module Organization

Planned layout:

- `src/` — Python package containing signal preprocessing, feature extraction, and machine learning models
- `notebooks/` — exploratory analysis and experiment notebooks, numbered sequentially (e.g., `01_data_exploration.ipynb`)
- `tests/` — unit tests mirroring the `src/` package structure
- `data/` — raw and processed datasets; never commit large data files (add to `.gitignore`)
- `docs/` — thesis notes, literature, and figures
- `Resources/Papers/` — literature library: raw PDFs plus converted Markdown in `Resources/Papers/md/`
- `tools/` — paper processing and retrieval scripts (`pdf2md.py`, `rag.py`) and the catalog `index.json`
- `skills/` — paper-related agent skills (`pdf-to-markdown`, `paper-rag`)

## Paper Processing & Retrieval

The literature library lives in `Resources/Papers/` with a metadata catalog at `tools/index.json`. Before working with papers, read the skills in `skills/pdf-to-markdown/` and `skills/paper-rag/`.

- Convert a PDF: `python3 tools/pdf2md.py <paper.pdf>` (docling default; `--fast` for clean text, `--force-ocr` for scanned)
- Rebuild the search index: `python3 tools/rag.py index`
- Search papers: `python3 tools/rag.py query "<question>"`
- List/status/verify: `python3 tools/rag.py list`, `status`, `check`
- Zotero: read `docs/zotero.md` before reading from or writing to the Zotero library (collections, items, PDF attachments).

## Build, Test, and Development Commands

No build system exists yet. When code lands, prefer:

- `python -m venv .venv` — create a virtual environment
- `uv pip install -e ".[dev]"` — install the package with development dependencies
- `pytest` — run all tests from the repository root
- `uv run jupyter nbconvert --to notebook --execute --inplace notebooks/<name>.ipynb` — verify a notebook executes end-to-end

## Coding Style & Naming Conventions

- Python 3 with PEP 8: `snake_case` for functions and variables, `PascalCase` for classes, `SCREAMING_SNAKE_CASE` for constants.
- Add type hints to public functions and use Google-style docstrings.
- Keep experiments reproducible: fix random seeds and record dataset versions.

## Testing Guidelines

- Use pytest. Name test files `test_<module>.py` and test cases `test_<function>_<scenario>`.
- Ensure tests are deterministic (fixed seeds, no network access).
- Run the full suite with `pytest` before submitting changes.

## Commit & Pull Request Guidelines

- No Git history exists yet; initialize the repository with `git init` and keep commits small and focused.
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
- Pull requests must describe the approach and results, link any related issue, and include relevant plots or metrics for model changes.

## Agent-Specific Instructions

- Do not invent experiment results; clearly mark uncertainty and unfinished work.
- Preserve raw data; only create derived, processed artifacts.
- Keep thesis-related writing in `docs/` and code in `src/` and `notebooks/`.
- Before writing any draft (thesis text, documentation, summaries, or other written deliverables), read `WRITING.md` at the repository root and follow its style guide.
