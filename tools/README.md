# Project tools

Run tools from the repository root. Generated indexes, profiles, plots, and
experiment outputs belong in ignored local data directories.

```text
tools/
├── papers/       literature conversion, catalog, and retrieval
├── processing/  dataset processing, migration, benchmarks, and inspection
├── thesis/       local DOCX and ODT draft exporters
└── radio/        host access point setup and diagnostics
```

## Papers and retrieval

- See the [local library setup and catalog schema](papers/README.md).
- `tools/papers/pdf2md.py` converts PDFs into `resources/Papers/md/`.
- `tools/papers/rag.py` indexes and searches those Markdown files using
  `tools/papers/index.json`. Rebuild its ignored `.rag-index/` with
  `python3 tools/papers/rag.py index`.

## Processing and inspection

- `tools/processing/prune_data.py` previews local cleanup candidates;
  `--apply` removes only the paths it reports.
- `tools/processing/upgrade_session_archive.py` copies version-1 session
  archives into verified version-2 derived archives without changing sources.
- `tools/processing/pilot_session_archive.py` creates or verifies archives;
  `migrate_session_archives.py` validates and migrates session directories.
- `benchmark_*.py` and `check_*.py` measure or inspect processing and model paths.
  Sequence model training is defined in `notebooks/latest/03_training.ipynb`.
  `benchmark_live_detector.py` requires an experiment directory via
  `--experiment`.

## Other utilities

- `tools/thesis/build_draft_docx.py` and `build_draft_odt.py` create local
  exports from the ignored `draft/` directory.
- `tools/radio/csi_ap.sh` and `test-hostapd-coexist.conf` support local radio
  diagnostics.

Read each tool's help and the matching guide in `docs/` before migrating or
pruning local data.
