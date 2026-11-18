# WiFall implementation with ESP32-C5 adaptations

`src/fall_detection/analysis/wifall/` implements amplitude smoothing, a resting
profile with Local Outlier Factor (LOF), and fall classification with random
forest or one-class SVM. It reads the preserved recordings through the existing
session loader. It does not use the neural models' `log1p(squared_difference)`
exports or modify raw recordings.

The source is [WiFall, §§4–6](../resources/Papers/md/wifall-2017.md)
([DOI](https://doi.org/10.1109/TMC.2016.2557792)). The paper does not specify
enough feature formulas and hyperparameters to claim an exact reproduction.
This implementation makes those choices explicit. Tests check equations,
training boundaries, and software behavior; they do not establish detection
performance on our recordings.

## Run on existing recordings

Install the analysis and radio dependencies from the repository root:

```bash
uv sync --extra analysis --extra radio
```

The following example uses activity labels present in the 4 November recording.
Repeat `--session` to include other closed session archives. Sources must share
the recorded 120 Hz, 5 GHz, 20 MHz sensing configuration and channel.

```bash
uv run python -m fall_detection.analysis.wifall \
  --session data/raw/sessions/20261104T081805521126Z.zip \
  --fall-label walk_to_fall \
  --fall-label sit_to_fall \
  --fall-label stand_to_fall \
  --non-fall-label sit_to_stand \
  --non-fall-label sit_to_walk \
  --non-fall-label stand_to_sit \
  --non-fall-label stand_to_walk \
  --non-fall-label walk_to_sit \
  --non-fall-label walk_to_stand \
  --classifier random_forest \
  --representation statistics \
  --minimum-coverage 0.7 \
  --max-gap-seconds 0.15 \
  --output artifacts/wifall/rf-statistics-seed42
```

The explicit coverage and gap settings accommodate the scheduled acquisition
gaps in these recordings. A smoke check of three `stand_to_fall` attempts in
this session found recurring 13-round finite-bracket separations (about
108 ms). With the stricter defaults, no windows survived the two-activity
adapter check. Interpolation across these gaps can remove motion detail; its
effect on detection remains unverified. The relaxed example is a runnable
adaptation, not a claim that the missing CSI is recovered.

Use a new output directory for every run. Change `--classifier` to
`one_class_svm` for the paper's fall-inlier classifier. Change
`--representation` to `singular_values` for the separate SVD interpretation.
`--help` lists window, gap, model, and split settings.

Outputs are:

- `model.joblib`: a dictionary with `schema`, `version`, fitted `detector`,
  receiver/tone `coordinates`, and model `parameters`.
- `predictions.json`: held-out targets, classifier predictions, gated
  predictions, activity flags, timestamps, coverage, and attempt identities.
- `report.json`: source/review fingerprints, dataset settings, code hashes,
  library versions, seed, full split assignments, resting-profile membership,
  model checksum, exclusion counts, and held-out window metrics. This file is
  published last to mark a completed run.

Model files use joblib serialization and should only be loaded from trusted
sources. A saved detector consumes raw amplitude windows with the saved receiver
and tone order:

```python
import joblib

bundle = joblib.load("artifacts/wifall/rf-statistics-seed42/model.joblib")
detector = bundle["detector"]
# windows: finite nonnegative [window, time, receiver, selected_subcarrier]
predictions = detector.predict(windows)
```

The run directory is Git-ignored. To retain a research run, version it with
`uv run dvc add artifacts/wifall/rf-statistics-seed42` and retain the resulting
DVC metadata alongside the existing raw-data metadata. No remote changes are
needed. Frame tables under `data/interim/frames/` are shared derived caches.

## Data handling and evaluation

The adapter reuses native magnitude decoding and the existing epoch/alignment
helpers. It retains the 120 Hz sequence grid and treats `rx-1` through `rx-4`
as four streams. The default selects 30 evenly spaced interior HE20 physical
tones, excluding indices outside −120…120 and the null tones −1, 0, 1.
Inspected C5 captures contain zeros at the positive edge tone; the fixed
interior selection avoids that edge without fitting to held-out labels or
accuracy. The selected indices are recorded. These
separate receivers differ from the paper's nine antenna-pair streams on
Intel 5300 hardware, sampled at 100 Hz. The paper's original input and
two-second matrix construction are described in
[§§4.2–4.3](../resources/Papers/md/wifall-2017.md).

Only accepted attempts without an exclusion review are eligible. Exact activity
labels must be mapped explicitly; unmapped attempts are counted and skipped.
Both fall and non-fall windows require their center inside the action cue.
This differs from the current neural experiment's non-fall window policy.
Collection cues remain approximate labels, not measured movement or impact
boundaries.

Windows never cross attempts, transmitter runs/boots, receiver reboots, or
all-receiver gaps of at least one second. Default windows are two seconds with
a one-second hop. Observed coverage must reach 90% per receiver across selected
tones. Only internal missing values whose finite bracketing samples are at
most 25 ms apart are linearly interpolated, independently inside each window.
Edges are never extrapolated; windows with remaining missing values are
excluded and counted. These policies are adaptations, not WiFall procedures.
Missing amplitudes never become zeros.

Resting chunks must fit wholly inside countdown cues. Countdown stillness is an
assumption that requires inspection; recovery after a fall is not automatically
treated as resting. LOF sees only chunks from training attempts, capped at 128
chunks by seeded selection. Each chunk is smoothed independently.

The default holdout groups by attempt, so overlapping windows cannot cross the
split. `--split-by session` and `--split-by participant` enforce stronger group
separation when enough data exist. Up to 100 seeded assignments are examined
only to find both classes on each side, never to select model performance.
The selected assignments are recorded. There is no hyperparameter search;
changing settings after inspecting this holdout makes it validation data and
requires an untouched test partition for final claims.

The report includes classifier-only and LOF-gated window metrics. These do not
measure event latency or false alarms per hour. An attempt holdout does not
establish generalization to new sessions or participants.

## Paper equations and explicit interpretations

Amplitude smoothing follows WiFall equation 9: the newest sample has weight
`m`, the oldest weight 1, divided by the sum of weights. The selected default
is `m=5`; the paper leaves `m` unspecified. Smoothing restarts at each window
and resting chunk, using an expanding weighted prefix at startup. This reset
policy is an adaptation to independent offline windows.

LOF uses the equation 8 stream aggregate:
`mean((subcarrier_frequency / center_frequency) * amplitude)`.
The denominator is the number of selected tones, not the sum of frequency
weights. Frequency ratios come from the recorded channel and HE20's 78.125 kHz
tone spacing. The defaults are 20 neighbors and anomaly-score threshold 1.5;
these are selected implementation settings. LOF scores are not probabilities.
The gate requires a simultaneous strict majority of streams at any sample in
the window: three of four streams. The paper describes majority voting but
does not establish its temporal voting rule precisely. See
[§4.3.1](../resources/Papers/md/wifall-2017.md).

The paper separately describes three leading SVD values and seven statistical
features per stream without explaining how to combine them. The implementation
therefore exposes two alternatives rather than inventing a combined pipeline:

| Representation | Defined input features |
| --- | --- |
| `statistics` | Seven features per stream, concatenated in receiver order: 28 features for four streams |
| `singular_values` | Leading three singular values of the uncentered, smoothed `[time, stream × tone]` matrix |

For `statistics`, temporal features are computed per tone and averaged within
each stream, except motion duration, which uses the stream's LOF flags:

| Feature | Implementation definition |
| --- | --- |
| Normalized standard deviation | Population standard deviation divided by mean; zero for zero-mean amplitude |
| Signal-strength offset | Maximum minus minimum amplitude |
| Motion period | Number of LOF-active samples divided by sample rate |
| Median absolute deviation | Median absolute deviation from the temporal median |
| Interquartile range | Temporal 75th minus 25th percentile |
| Signal entropy | Shannon entropy in bits using 16 bins over that tone's window-local amplitude range |
| Signal-change velocity | Mean absolute consecutive amplitude difference multiplied by sample rate |

These formulas resolve omissions in [§4.4](../resources/Papers/md/wifall-2017.md);
they are not verified author implementation details. In particular, the selected
max-minus-min offset is one interpretation of the paper's signal-strength
description. Histogram ranges are local descriptors, with no fitting on other
windows. There is no Hampel filter, log transform, or squared-difference stage
in this implementation.

Random forest uses 200 trees, seed 42, and one worker by default. Its scaler
fits all training windows. The one-class SVM uses an RBF kernel, `nu=0.1`, and
`gamma=scale`; its scaler and classifier fit only fall training windows.
**SVM inliers mean falls**, following the paper's objective-class definition.
These model hyperparameters are configurable choices because the paper does
not provide them. Neither classifier nor normalizer fits on held-out windows.

## Code and checks

`signal.py` contains smoothing and frequency aggregation; `features.py` defines
the two representations; `model.py` owns LOF and classifiers; `dataset.py`
adapts preserved sessions; `experiment.py` owns grouped evaluation and output;
`__main__.py` supplies the command above. Existing preprocessing, training, and
live detection remain separate consumers of their current representations.

```bash
uv run ruff format src/fall_detection/analysis/wifall tests/analysis/wifall
uv run ruff check src/fall_detection/analysis/wifall tests/analysis/wifall
uv run pytest
```
