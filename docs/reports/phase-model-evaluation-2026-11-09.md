# Exploratory collection-phase model comparison

On 9 November 2026, the training workflow in
`notebooks/latest/03_training.ipynb` was run on the
`amplitude_windows_v1/20261104T081805521126Z` dataset. All 12 models completed.
Their targets are the center-window collection cues preparation, action, and
resting. These are not verified fall-event labels.

The fixed seed-42 split contains 138 training, 47 validation, and 47 test
attempts from one session and one participant. All windows and receivers from
an attempt share a split. Overlapping windows and multiple receivers remain
correlated observations within the held-out attempts, and this single split
does not measure performance on new participants or sessions. The upstream
recording-wide min–max scaling and centered Hampel filtering use future samples
within each recording.

Each model receives 32 temporal bins containing per-subcarrier means and
coverage fractions. CNN, LSTM and GRU use Adam, up to 12 epochs, and checkpoint
selection by validation macro-F1 with patience 3. The forest has 150 trees.
Training ran on an AMD Ryzen 7 PRO 4750U CPU, with two PyTorch threads, seed 42,
PyTorch 2.14.1+cpu, NumPy 2.5.2, Polars 2.1.0 and scikit-learn 1.9.1.
The complete run took 414.5 seconds including indexing and artifact writing.

## Held-out window metrics

Macro-F1 uses the fixed three-phase label set, including any phase absent from
the test set. Majority baselines predict the most frequent training phase.

| Window | Model | Validation macro-F1 | Test macro-F1 | Test accuracy |
| --- | --- | ---: | ---: | ---: |
| 2 s | CNN | 0.560 | 0.565 | 0.584 |
| 2 s | LSTM | 0.536 | 0.561 | 0.570 |
| 2 s | GRU | 0.561 | 0.564 | 0.575 |
| 2 s | Random forest | 0.458 | 0.475 | 0.489 |
| 2 s | Majority baseline | — | 0.175 | 0.357 |
| 4 s | CNN | 0.303 | 0.287 | 0.522 |
| 4 s | LSTM | 0.503 | 0.531 | 0.590 |
| 4 s | GRU | 0.572 | 0.604 | 0.647 |
| 4 s | Random forest | 0.351 | 0.392 | 0.579 |
| 4 s | Majority baseline | — | 0.225 | 0.510 |
| 6 s | CNN | 0.285 | 0.282 | 0.733 |
| 6 s | LSTM | 0.285 | 0.282 | 0.733 |
| 6 s | GRU | 0.285 | 0.282 | 0.733 |
| 6 s | Random forest | 0.292 | 0.282 | 0.733 |
| 6 s | Majority baseline | — | 0.282 | 0.733 |

The 4-second GRU had the highest validation and test macro-F1 in this run.
On its 737 test windows, the confusion matrix below uses actual phases as rows
and predicted phases as columns. It still confuses preparation and resting.

| Actual / predicted | Preparation | Action | Resting |
| --- | ---: | ---: | ---: |
| Preparation | 62 | 27 | 58 |
| Action | 51 | 255 | 70 |
| Resting | 30 | 24 | 160 |

The 6-second data has no preparation-labeled windows in any split. Its 374
test windows contain 274 action and 100 resting windows. All four models
predicted action for every test window, matching the majority baseline; their
73.3% accuracy does not imply useful three-phase classification. Because the
class sets differ, the fixed-label 6-second macro-F1 is not directly comparable
to the 2- and 4-second results.

Each duration also covers a different number of windows and phase boundaries.
One random split and a single seed do not establish robust model ranking. The
results do not measure fall detection, real-time performance, or accuracy on an
independent participant or session. The mask-aware temporal pooling and
interpolation have not been compared against other signal representations or
preprocessing ablations.

## Artifacts

The derived directory
`data/experiments/phase_models_v1/20261104T081805521126Z/` contains
`comparison.csv`, `majority_baselines.json`, the window-level split in
`window_split.parquet`, source file metadata fingerprints in `manifest.json`,
and each model's checkpoint and `metrics.json` under its duration/model
directory. The fingerprints summarize file paths, sizes and modification times;
they are not content hashes. Metrics include fixed-order confusion matrices,
per-class reports, validation scores and neural training histories.

To reproduce, use the same dataset and configuration in the notebook. Launch
the kernel with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2` and set PyTorch to
two threads. Re-running the notebook writes to the same experiment directory.
