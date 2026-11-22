# WiFall adapted to the ESP32-C5 receivers

`src/fall_detection/analysis/wifall/` is a window-level fall detector built on
WiFall ([paper](../../resources/Papers/md/wifall-2017.md),
[DOI](https://doi.org/10.1109/TMC.2016.2557792)): smoothed CSI amplitude, a
Local Outlier Factor (LOF) activity detector trained on resting data, window
statistics and singular values, and a random forest or a fall-inlier
one-class SVM. It keeps WiFall's structure but adapts each step to our radios
instead of reproducing the paper, in the same way as the
[FallDeFi adaptation](falldefi.md). It reads the preserved recordings through
the shared session adapter and never modifies raw recordings. Tests check the
processing and training boundaries; they do not establish detection
performance.

## Hardware constraints

The constraints are those listed for [FallDeFi](falldefi.md#hardware-constraints):
120 Hz sampling, four single-antenna receivers that are separate radios,
245 reported tones, and a scheduled 0.1 s gap about every 0.57 s on each
receiver, staggered so that all four are complete only about a quarter of the
time. The first WiFall implementation required all four receivers in every
window. On the 9 November 13:15 session, with 0.7 coverage and gaps up to
0.15 s, that kept 134 of 1,005 action windows and 99 of 768 countdown windows.
Its default 0.9 coverage was above the about 0.82 that the schedule alone
leaves each receiver.

## Pipeline

1. **Windows.** Two-second windows slide by one second inside each recording
   epoch (§4.3.2). A window whose center lies in an action cue is classified
   for both classes; a window wholly inside a countdown cue is a resting
   chunk.
2. **Gaps and receivers.** Gaps up to 0.25 s are linearly interpolated and
   each receiver needs 0.7 coverage. A receiver failing either rule is dropped
   from that window only; a window needs two usable receivers.
3. **Representation per receiver.** 120 evenly spaced interior tones are
   divided by their window means (relative amplitude) and smoothed by
   equation 9 (`m = 5`, newest weight m, restarting in each window). From the
   smoothed tones come six statistics, averaged over tones; three singular
   values of the centered window divided by √(samples); and the activity
   stream, the window's first principal component with a fixed sign. This is computed once at load time; it uses no labels and no other
   window.
4. **Activity profile.** Each receiver gets a LOF profile (20 neighbors) of its
   resting stream values from at most 128 training countdown chunks (§4.3.1).
   A sample is active on a receiver when its LOF score exceeds 1.5.
5. **Activity gate.** A window passes when, at some sample, a strict majority
   of its profiled, present receivers is active: two of two, two of three,
   three of four. The motion period of a receiver is its active time.
6. **Features.** The seven statistics and three singular values of each
   receiver are pooled over present receivers by mean and maximum: 20
   features (`--features statistics` keeps 14, `singular_values` 6).
7. **Classifier.** Standard scaling, then a random forest (200 trees, balanced
   class weights) or a one-class SVM (RBF, `ν = 0.1`) fitted on fall windows
   only, falls being its inliers as in the paper (§4.4). Both are fitted on
   training windows only. A window is a fall when the classifier says so and
   it passes the gate.

| Feature | Definition per tone, on smoothed relative amplitude |
| --- | --- |
| Normalized standard deviation | Population standard deviation divided by mean |
| Signal offset | Maximum minus minimum |
| Motion period | LOF-active samples of the receiver divided by the sample rate |
| Median absolute deviation | Median absolute deviation from the median |
| Interquartile range | 75th minus 25th percentile |
| Signal entropy | Base-two entropy of a 16-bin histogram on the tone's own range |
| Signal-change velocity | Mean absolute first difference times the sample rate |

## Relation to WiFall

| Step | WiFall | Here | Reason |
| --- | --- | --- | --- |
| Streams | Nine antenna pairs on one Intel 5300, 30 subcarriers, 100 Hz | Four C5 receivers, 120 interior tones, 120 Hz | Hardware |
| Missing data | Not discussed | Interpolate up to 0.25 s; drop failing receivers per window | Scheduled, staggered gaps |
| Scale | Raw amplitude | Relative amplitude per tone and window | Separate radios with their own gain; profiles must transfer across sessions |
| Activity stream | Mean of `(f_j / f_0)` × amplitude over subcarriers (equation 8) | First principal component of the receiver's relative tones | Motion raises some tones and lowers others, so the mean cancels it: during falls its 2 s standard deviation was 1.14 times the resting value, against 1.54 times for the first component |
| Activity gate | LOF per stream, majority vote of nine streams | LOF per receiver, strict majority of present receivers | Receivers may be missing |
| Features | Seven statistics, or three SVD values; how they combine is not stated | Both, per receiver, pooled by mean and maximum | A fixed vector whatever receiver is dropped |
| SVD | Of the window matrix | Of the centered window per receiver, scaled by √(samples) | After relative scaling the first uncentered value is constant |
| Classifier | One-class SVM (falls as target class) or random forest | Same; random forest with balanced class weights | Non-falls outnumber falls |

The feature formulas, LOF settings, smoothing startup and classifier
hyperparameters are not given in the paper; the values above are adaptation
choices, not author details.

## Run on existing recordings

```bash
uv sync --extra analysis --extra radio
```

On the data laptop, check new settings on one session and leave
multi-session runs to the training device. These are the runs in the
[22 November smoke report](../reports/wifall-smoke-2026-11-22.md):

```bash
uv run python -m fall_detection.analysis.baselines.wifall \
  --session data/raw/sessions/20261109T131546367822Z.zip \
  --fall-label walk_to_fall --fall-label sit_to_fall --fall-label stand_to_fall \
  --non-fall-label sit_to_stand --non-fall-label sit_to_walk \
  --non-fall-label stand_to_sit --non-fall-label stand_to_walk \
  --non-fall-label walk_to_sit --non-fall-label walk_to_stand \
  --classifier random_forest \
  --output artifacts/baselines/wifall/<new-run>
```

Use `--classifier one_class_svm` for the fall-inlier SVM. Repeat `--session`
to combine sessions and add `--non-fall-label non_fall` for the continuous
non-fall session; `--split-by session` trains on one day and tests on another.
`--help` lists every setting. Use a new output directory for every run.

Outputs are `model.joblib` (fitted detector, coordinates, parameters and the
representation settings; load only from trusted sources), `predictions.json`
(each held-out window with its provenance, receivers used, gated and
classifier-only predictions, and activity flag), and `report.json` (sources,
settings, exclusion counts, split, profiled receivers, held-out window and
attempt metrics, activity fractions, versions and code hashes), written last.
A saved detector takes representations, not raw amplitude:

```python
import joblib
from fall_detection.analysis.baselines.wifall.representation import represent_windows

bundle = joblib.load("artifacts/baselines/wifall/<run>/model.joblib")
# windows: [window, time, receiver, tone] in the saved coordinates, NaN for
# a dropped receiver.
batch = represent_windows(windows, **bundle["representation"])
predictions = bundle["detector"].predict(batch)
```

Git does not ignore `artifacts/baselines/wifall/`; keep a run with
`uv run dvc add artifacts/baselines/wifall/<run>` and commit only the `.dvc` file.

## Evaluation

The holdout groups by attempt by default, so overlapping windows never cross
the split; `--split-by session` and `--split-by participant` give stronger
separation. Up to 100 seeded assignments are examined only to find both
classes on each side. The report gives gated and classifier-only window
metrics, balanced accuracy, the activity fraction per class, and attempt
metrics, where an attempt is a fall when any of its windows is. Attempt
metrics are the closest to FallDeFi's trace metrics, though FallDeFi traces
add 1 s margins. Neither measures event latency or false alarms per hour.

## Limitations

- On the 9 November 13:15 session the gate passed no held-out window and the
  classifiers alone reached balanced accuracy 0.52–0.56; the window features
  did not separate falls from other transitions there
  ([smoke report](../reports/wifall-smoke-2026-11-22.md)).
- The 9 November 13:15 session informed the hardware choices; treat it as
  development data and evaluate on other sessions.
- Interpolation of the scheduled gaps alters every window.
- Resting profiles assume still countdowns, which have not been inspected;
  the LOF threshold and neighbors are untuned.
- Action cues are collection instructions, not measured movement or impact
  times; windows overlap and are correlated within an attempt.
- An attempt holdout within one session does not establish generalization to
  new sessions, rooms or participants.

## Code and checks

`representation.py` holds smoothing, relative amplitude and the per-receiver
statistics; `model.py` owns the profiles, gate, pooling and classifiers;
`dataset.py` adapts preserved sessions; `experiment.py` owns grouped
evaluation and output; `__main__.py` supplies the command. Session reading,
gap filling and per-receiver checks are shared with FallDeFi in
`analysis/_recorded_attempts.py`, and the grouped holdout and metrics in
`analysis/_grouped_holdout.py`. Existing preprocessing, training, and live
detection do not use this package.

```bash
uv run ruff format src/fall_detection/analysis/wifall tests/analysis/wifall
uv run ruff check src/fall_detection/analysis/wifall tests/analysis/wifall
uv run pytest
```
