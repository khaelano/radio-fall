# Self-contained CSI CNN pilot

This folder runs its own EDA, preprocessing, small CNN training, and held-out
binary evaluation on the same session used by `02_simple_eda.ipynb`. It does not
change that notebook or raw recordings. All experiment code, pinned decoder
snapshots, dependency lock, configuration, results, and local model artifacts
live here. Raw recordings remain an external, read-only input selected in
`config.json`; change that path when moving this folder.

Open [03_cnn_experiment.ipynb](03_cnn_experiment.ipynb) for the executed notebook
walkthrough. Run All reads saved results by default. Its explicit rerun switch
executes all stages into `artifacts/notebook_rerun/`, leaving `pilot_v1` intact.
The operator's manual action timestamp anchors the current fixed window; shifted
windows have not yet been evaluated.

From this folder:

```bash
uv sync --frozen
uv run --frozen python run.py
uv run --frozen pytest -q
```

For notebook execution, install the optional kernel/tools with
`uv sync --frozen --extra notebook`. Then run
`uv run --frozen --extra notebook jupyter nbconvert --to notebook --execute --inplace 03_cnn_experiment.ipynb`.

Run individual stages with `python run.py --stage prepare`, `eda`, `train`,
`evaluate`, or `report`. `--output` selects a separate artifact directory;
`--config` selects a configuration file. Session paths are relative to this
folder. Re-running preparation/training overwrites that output directory's
files. Use a different output directory for a new experiment. Stages reject
changed prepared arrays, split membership, config, or checkpoints rather than
silently evaluating a different experiment.

Read [the executed report](results/pilot_v1/REPORT.md) for measured results and
limitations. Small CSVs, plots, hashes, and metrics are exported to `results/`;
large arrays and CPU model checkpoints remain in ignored `artifacts/`.
`test_predictions.csv` contains one prediction per complete attempt, with both
receivers together. The report describes the exact split, preprocessing,
architecture, baseline comparisons, and validation selection rule.

The default experiment keeps all 242 valid HE20 tones, uses four-second
cue-aligned windows at 25 bins/second, and evaluates five predefined signal
representations. A three-seed CNN ensemble is selected on validation scenarios.
The test set holds out entire activity/direction scenarios including repetitions.
It shares the same session and participant, so this is an exploratory
within-session classification result. It is not a continuous fall detector or
an evaluation on unseen sessions or participants. Further tuning must not reuse
its reported test scores for selection.

`vendor/` pins the existing canonical HE-LTF decoder, phase loader, affine clock
synchronization, and signed circular-change function. Its provenance JSON records
original and snapshot SHA-256 hashes; only imports were localized, and only the
change-matrix function was retained from the motion module. There is no runtime
dependency on the repository's Python package. The independent CPU-only PyTorch
environment avoids modifying the repository environment.
