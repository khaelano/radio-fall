# Project tools

Run tools from the repository root. Generated indexes, profiles, plots, and
experiment outputs belong in ignored local data directories.

```text
tools/
├── papers/       literature conversion, catalog, and retrieval
├── processing/  dataset processing, migration, benchmarks, and inspection
├── thesis/       local ODT draft exporter
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
- Session archives are written, migrated, verified and extracted by the Rust
  `radio_storage` library (`radio_storage` CLI: `convert`, `verify`, `migrate`,
  `verify-archive`; Python: `fall_detection._radio_native.storage_*`).
- `benchmark_*.py` measure offline amplitude preprocessing. Sequence model
  training is defined in `notebooks/latest/03_training.ipynb`. Live radio and
  detector runtime checks are Rust binaries in `radio_detection`; the earlier
  Python live-detector and radio-pipeline tools were removed with the Python
  acquisition path.

## Other utilities

- `tools/thesis/build_draft_odt.py` creates a local ODT export from Pandoc
  Markdown in the ignored `draft/` directory.
- `tools/radio/csi_ap.sh` and `test-hostapd-coexist.conf` support local radio
  diagnostics.

Read each tool's help and the matching guide in `docs/` before migrating or
pruning local data.
