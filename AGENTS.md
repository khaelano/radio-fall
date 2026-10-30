# Repository Guidelines

## Project Overview

This repository supports a bachelor's thesis on fall detection using WiFi channel state information recorded with ESP32-C5 radios.

## Project Structure & Module Organization

Current layout:

- `src/fall_detection/` — Python package for shared contracts, radio processing, synchronized collection, and evaluation
- `src/firmware/radio/` — ESP-IDF transmitter and receiver projects
- `configs/` — versioned collection, radio, and experiment settings
- `notebooks/` — exploratory analysis and experiment notebooks, numbered sequentially (e.g., `01_data_exploration.ipynb`)
- `tests/` — unit tests mirroring the research modules under `src/fall_detection/`
- `data/` — raw recordings, derived datasets, annotations, and dataset splits; session bundles are documented in `docs/dataset-format.md`; never commit large data files
- `draft/` — thesis chapter drafts and other text intended to become part of the final thesis
- `docs/` — supporting notes, literature documentation, procedures, and figures
- `docs/project-knowledge.md` — compact record of current implementation facts, decisions, limitations, and open questions
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

## Citation Guidelines

- Use Pandoc citations that reference Zotero/Better BibTeX citation keys in
  every thesis-related Markdown draft: `[@citationKey]` for one source and
  `[@keyOne; @keyTwo]` for multiple sources.
- For a narrative citation, write the author in the sentence and place the
  citation immediately after the supported claim, for example:
  `Susilowati dkk. melaporkan ... [@susilowatiPrevalenceRiskFactors2020].`
- Copy each citation key exactly from the Zotero item's `citationKey` field.
  Never invent a key, use a Zotero item key as a citation key, or replace a
  citation with a manually typed number such as `[1]`.
- Verify that every cited item exists in Zotero and that the paper supports
  the claim. Cite numerical literature claims, quoted definitions, and
  comparisons at the sentence where they appear.
- Prefer primary or authoritative sources. If a review is used for a broad
  synthesis, do not present a study quoted inside the review as though the
  original study was read directly.
- Generate the reference list from Zotero/Better BibTeX through
  Pandoc/Citeproc. Do not maintain a hand-written reference list in a thesis
  draft.

## Build, Test, and Development Commands

No build system exists yet. When code lands, prefer:

- `uv sync --extra radio` — create or update the environment with radio and development dependencies
- `uv run pytest` — run all tests from the repository root
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

- Keep commits small and focused.
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
- Pull requests must describe the approach and results, link any related issue, and include relevant plots or metrics for model changes.

## Agent-Specific Instructions

- Do not invent experiment results; clearly mark uncertainty and unfinished work.
- Read `docs/project-knowledge.md` before making architectural, preprocessing,
  data-handling, or experimental-design decisions. When a change makes an
  entry inaccurate or resolves an open question, update the knowledge base in
  the same change. Keep it compact, link to canonical code or documentation,
  and distinguish implemented facts from proposals and unverified findings.
- Preserve raw data; only create derived, processed artifacts.
- Write all thesis drafts in `draft/`, including chapter text, section drafts,
  literature syntheses, and revisions intended for the final thesis. Use
  descriptive Markdown filenames such as `pendahuluan.md` or
  `landasan-kepustakaan.md`.
- Keep supporting notes, literature documentation, procedures, and figures in
  `docs/`. Keep code in `src/` and experiments in `notebooks/`.
- Before writing any draft (thesis text, documentation, summaries, or other written deliverables), read `WRITING.md` at the repository root and follow its style guide.
- Before finalizing a cited draft, extract its citation keys and compare them
  with Zotero. The draft must not contain unresolved or fabricated citation
  keys.
