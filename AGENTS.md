# Repository Guidelines

Bachelor’s thesis on fall detection using WiFi CSI recorded with ESP32-C5 radios.

## Layout

- `src/fall_detection/`: Python contracts, processing, collection, and evaluation; `src/firmware/radio/`: ESP-IDF radio projects.
- `configs/`: collection, radio, and experiment settings; `notebooks/latest/`: current experiments; `tests/`: mirrors Python modules.
- `data/`: recordings, derived datasets, annotations, and splits; see `docs/dataset-format.md`.
- `draft/`: all thesis drafts and exports (Git-ignored); `docs/`: supporting notes, procedures, literature documentation, and figures.
- `resources/Papers/`: ignored PDFs and converted `md/`; `tools/papers/index.json`: literature catalog.
- `tools/{papers,processing,thesis,radio}/`: utilities; see `tools/README.md`. `skills/`: paper workflows.

## Working Rules

- Read `WRITING.md` before writing any draft, documentation, summary, or other written deliverable.
- Read `docs/project-knowledge.md` before architectural, preprocessing, data-handling, or experimental-design decisions. Update inaccurate entries and resolved questions in the same change; keep it compact, link canonical sources, and distinguish implementation from proposals and unverified findings.
- Preserve raw data; create derived artifacts only. Never commit large data files to Git. DVC is installed: use `uv run dvc` for data versioning, inspect existing tracking/configuration first, and commit relevant DVC metadata with code. Do not overwrite raw data or change remotes casually.
- Keep thesis text and literature syntheses in descriptive `draft/*.md` files, supporting material in `docs/`, code in `src/`, and experiments in `notebooks/`.
- Never invent results; state uncertainty and unfinished work. Fix random seeds and record dataset versions.
- Prefer jupyter-agent-bridge MCP tools for notebooks before reading or editing raw `.ipynb` files.

## Development and Validation

Ruff and DVC are installed in the `dev` dependency group. Use uv from the repository root:

- `uv sync --extra radio`: update the environment with radio and development dependencies.
- After every write/change, run `uv run ruff format <changed Python/notebook files>` and `uv run ruff check <changed Python/notebook files>`; resolve findings before finalizing. These are the formatting and check commands, not `uv format` or `uv check`. For Markdown-only changes, Ruff does not apply; review the diff and whitespace with `git diff --check`.
- `uv run pytest`: run the full suite before submitting code changes. Tests must be deterministic and offline; add only necessary tests whose coverage cannot be inferred from existing tests.
- `uv run jupyter nbconvert --to notebook --execute --inplace notebooks/<name>.ipynb`: verify notebook execution when applicable; rerun Ruff after notebook writes.
- Python: PEP 8, `snake_case` functions/variables, `PascalCase` classes, `SCREAMING_SNAKE_CASE` constants; public functions need type hints and Google-style docstrings. Tests: `test_<module>.py`, `test_<function>_<scenario>`.
- Keep commits focused and use Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`). PRs explain approach and results, link related issues, and include plots/metrics for model changes.

## Literature and Citations

- Before paper work, read `skills/pdf-to-markdown/SKILL.md` and `skills/paper-rag/SKILL.md`; before Zotero access, read `docs/zotero.md`.
- Convert: `python3 tools/papers/pdf2md.py <paper.pdf>` (Docling default; `--fast` for clean text, `--force-ocr` for scans).
- Retrieve: `python3 tools/papers/rag.py index`, `query "<question>"`, `list`, `status`, or `check`.
- Thesis Markdown uses Pandoc citations with exact Zotero `citationKey` values: `[@key]` or `[@keyOne; @keyTwo]`. Never invent keys, substitute Zotero item IDs, or type numeric citations.
- Place citations immediately after supported claims, including narrative citations, numerical claims, definitions, and comparisons. Verify each paper supports the claim; prefer primary/authoritative sources and distinguish review synthesis from originals actually read.
- Before finalizing cited drafts, extract all citation keys and compare them with Zotero; resolve every missing key. Generate references through Zotero/Better BibTeX and Pandoc/Citeproc, never a handwritten bibliography.
