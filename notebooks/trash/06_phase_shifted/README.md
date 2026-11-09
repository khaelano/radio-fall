# Phase-change CNN with explicit random windows

This experiment retrains the four-receiver CNN using only temporal calibrated
phase change, with no fitted normalization. It preserves the original
206-attempt cohort and frozen scenario split from `05_four_rx_cnn`.
Read the [measured report](results/phase_random20_v1/REPORT.md) or open the
executed [notebook](06_phase_shifted_training.ipynb) for the completed run.

Each training attempt contributes 20 distinct seeded random window offsets
within ±0.5 seconds, plus its central window. Random draws are stratified over
that interval. All 21 windows are materialized and included in every training
epoch. Low-coverage candidates are replaced with new seeded draws; preparation
fails rather than silently reducing the quota. Validation and test windows
remain central, and no scenario crosses splits. Closely overlapping windows
remain correlated observations from the same recording.

The Rust preprocessor used live also builds the training inputs: 100 ms wrapped
calibrated phase differences, inclusive maximum lag 150 ms, sine/cosine means
in 25 Hz bins, four receivers and 242 physical tones. Eight feature planes and
eight masks form a `[16, 100, 242]` input. Finite features remain unchanged in
[−1, 1]; missing features become zero with explicit masks. There are no amplitude
features, fitted scaler, smoothing or normalization layers. Amplitude still
controls the existing phase validity floor in the decoder.

Integer capture timestamps govern lag selection and bin assignment. An
independent NumPy calculation checks every generated candidate window against
Rust, reusing decoded packet phases. This exact timing contract avoids the
older Python analysis's floating-point ambiguity at the 150 ms cutoff. The
old artifacts and raw recordings remain unchanged.

Run from the repository root with the compiled native extension:

```sh
uv sync --extra radio --extra detection --extra analysis
uv pip install --python .venv/bin/python -r notebooks/trash/06_phase_shifted/requirements.txt
.venv/bin/python notebooks/trash/06_phase_shifted/run.py prepare
.venv/bin/python notebooks/trash/06_phase_shifted/run.py train
.venv/bin/python notebooks/trash/06_phase_shifted/run.py evaluate
.venv/bin/python notebooks/trash/06_phase_shifted/run.py verify_live
.venv/bin/python notebooks/trash/06_phase_shifted/run.py report
```

Preparation and training refuse to overwrite an existing run. The configuration
and current implementation hashes, source hashes, materialized offsets, trained
checkpoint hashes and library versions are saved in the run's provenance.
Arrays and checkpoints stay ignored under `artifacts/phase_random20_v1/`.
Small tables, plots and measured results are copied to `results/phase_random20_v1/`.

Evaluation exports `data/models/phase_random20_v1/`, which the live program can
load directly. The bundle has no normalization file:

```sh
.venv/bin/fall-detect --model data/models/phase_random20_v1
```

The ensemble retains the previous SmallCNN architecture and three training seeds,
with its first convolution expanded to 16 inputs. Every checkpoint minimizes
central validation weighted BCE; the threshold stays 0.5. The test scenarios
have already been inspected in the previous experiment, so these results remain
exploratory. Shift augmentation does not establish generalization to another
session or that the observed live failure is fixed.
