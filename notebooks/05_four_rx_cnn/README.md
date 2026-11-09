# Four-receiver CSI experiment

This experiment uses the completed 4 November 2026 session
`20261104T081805521126Z`: one transmitter, four real receiver views, nine
activities, and 232 accepted attempts from one participant. It runs EDA,
preprocessing, three-seed CNN training, validation selection, and held-out
scenario evaluation. Raw recordings remain read-only.

Open [05_four_rx_experiment.ipynb](05_four_rx_experiment.ipynb) for the executed
walkthrough and [the report](results/four_rx_v1/REPORT.md) for measured results.

Five four-second windows start at offsets −0.50, −0.25, 0, +0.25 and +0.50
seconds relative to the operator action cue. The fixed scheme trains on offset
zero. Shift augmentation draws one configured offset per training attempt per
epoch, preserving the same maximum optimizer-update budget. All repetitions,
retakes, receiver views and offsets from a scenario stay in one frozen split.
Validation uses central windows; test offsets are sensitivity measurements on
the same attempts, never independent extra test examples.

Run from the repository root using the existing isolated CPU environment and
its lockfile:

```bash
uv run --project notebooks/shared_cnn --frozen python notebooks/05_four_rx_cnn/run.py
uv run --project notebooks/shared_cnn --frozen python -m pytest -q notebooks/05_four_rx_cnn/tests
```

The repository package is loaded directly from `src/` for canonical gateway
capture alignment, HE-LTF decoding and circular phase changes. The shared experiment module supplies binning, the small CNN and metrics,
alongside the pinned NumPy/pandas/matplotlib/scikit-learn/PyTorch CPU environment. Current source files and their hashes are recorded in each
experiment manifest; the old pilot's recordings and outputs are unchanged.

Use `--stage prepare`, `eda`, `train`, `evaluate`, or `report` to run one stage.
Use `--output notebooks/05_four_rx_cnn/artifacts/<new-name>` for a new run;
preparation and training overwrite files inside the selected output directory.
All stages reject output paths overlapping the raw session. Evaluation rejects
changed arrays, splits, configuration, modeling code and checkpoints.

The default large arrays/checkpoints remain ignored under
`artifacts/four_rx_v1/`. Small reports, CSVs, metrics, source hashes and figures
are exported under `results/four_rx_v1/`. The notebook reads saved results by
default; its explicit rerun flag targets a separate artifact folder.

Execute the notebook from this folder with the same environment:

```bash
../shared_cnn/.venv/bin/python -m jupyter nbconvert --to notebook --execute --inplace 05_four_rx_experiment.ipynb
```

Only training CSI values enter signal EDA. Metadata audits cover all partitions.
Five predefined representations compare amplitude, raw/calibrated phase and
circular phase change with a smoothing ablation. Majority, signal-summary,
quality-only and collection-order logistic controls accompany the CNN.

This is an exploratory within-session classification experiment. Scenario
separation does not establish generalization to unseen participants, sessions,
rooms or continuous detection, and activity/equipment/time confounding remains
possible. Further tuning must not treat this now-inspected test set as untouched.

The shared helpers were extracted from the archived two-receiver pilot. Existing
selection manifests fingerprint the original paths and code; rerun preparation
and training before evaluating with the new implementation paths.
