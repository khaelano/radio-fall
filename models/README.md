# Model bundles

Sequence-training checkpoints, configuration, fitted normalizers, and ONNX
exports live in `sequence/<run-id>/`. `sequence.dvc` versions these bundles;
Git stores the DVC metadata rather than model binaries.

Restore a recorded snapshot with `uv run dvc pull models/sequence.dvc`.
After training or exporting another model, record the new snapshot with
`uv run dvc add models/sequence` and commit the updated DVC metadata with the
corresponding code. The configured DVC remote remains unchanged.

Notebook run metrics, splits, coverage tables, and figures live under the ignored
`artifacts/notebooks/` directory. Training checkpoints include a JSON sidecar;
normalizers are shared by duration within a run. ONNX exports include their own
normalizer copies and an input/output manifest. Interrupted historical runs can
have incomplete metadata, explicitly marked in their sidecars.
