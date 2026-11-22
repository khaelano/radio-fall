# FallDeFi adapted to the ESP32-C5 receivers

`src/fall_detection/analysis/baselines/falldefi/` is a time-frequency fall detector
built on FallDeFi ([paper](../../resources/Papers/md/falldefi-2017.md),
[DOI](https://doi.org/10.1145/3161183)): spectrograms of CSI amplitude,
power-burst event detection, and an RBF support vector machine (SVM) on event
features. It keeps FallDeFi's structure but adapts each step to our radios
instead of reproducing the paper. Where the paper is silent, the authors'
released MATLAB code ([github.com/dmsp123/FallDeFi](https://github.com/dmsp123/FallDeFi),
MIT licence) was read for reference and not copied. It reads the preserved
recordings through the same session adapter as the [WiFall baseline](wifall.md)
and never modifies raw recordings. Tests check the processing and training
boundaries; they do not establish detection performance.

## Hardware constraints

- **Rate.** The receivers sample at 120 Hz, so the spectrum ends at 60 Hz.
  FallDeFi sampled at 1000 Hz and lost accuracy below 400 Hz (§8.1.4). Its
  event band (5–25 Hz) and selected features (1–30 Hz) still fit below 60 Hz,
  but fall components above 60 Hz alias into the band.
- **Separate radios.** Four single-antenna C5 receivers stand in for the
  paper's antenna pairs on one card. Each has its own gain, noise and
  multipath, so their spectrograms are not on one scale.
- **Scheduled gaps.** In the 9 November 13:15 session each receiver lost a
  0.1 s burst every 0.567 s (median), about 18 % of its samples; 95 % of gaps
  lasted at most 0.10–0.24 s depending on the receiver. The receivers lose
  their bursts at different times: at least three were complete 89 % of the
  time, all four only 26 %. No 0.53 s STFT window is free of a gap.
- **Many tones.** The C5 reports 245 HE20 tones, against the Intel 5300's 30.

## Pipeline

1. **Traces.** Each accepted attempt with a mapped label yields its action cue
   widened by 1 s on both sides. A non-fall cue longer than 10 s, such as a
   continuous segment, is split into 10 s traces; a longer fall cue is
   excluded, since the fall cannot be localized.
2. **Gaps and receivers.** Gaps up to 0.25 s are linearly interpolated and
   each receiver needs 0.7 coverage. A receiver failing either rule is
   dropped from that trace only; a trace needs two usable receivers.
3. **Per receiver.** 120 evenly spaced interior tones are divided by their
   trace means (relative amplitude), denoised with one sym3 wavelet level
   (which only affects 30–60 Hz), and projected on three principal components.
   Each component gets a Hamming STFT (64 samples = 0.53 s, hop 32, 1.875 Hz
   bins); the receiver's spectrogram is their average.
4. **Whitening and fusion.** Each receiver's spectrogram is divided bin by bin
   by its median resting spectrum from training countdowns, then the usable
   receivers are averaged. The result is in multiples of the resting floor.
5. **Threshold.** A log-normal fit to the fused resting spectrograms in
   5–25 Hz gives `10 ** (mean + k * std)`, the median over training resting
   segments. `k` is the largest of 0, 0.1, …, 4.3 at which 95 % of training
   traces contain an event; every trace is a cued activity, so this uses
   neither fall labels nor test data. `--threshold-k` fixes it instead.
6. **Region and events.** Bins above the threshold form 8-connected regions;
   the region with the most magnitude in 5–25 Hz is kept. Frames where its
   5–25 Hz sum exceeds the threshold times the band's bin count are events,
   merging runs less than 0.5 s apart.
7. **Features and labels.** Each event yields duration, spectral entropy in
   1–10 Hz and 10–30 Hz, and the box-counting dimension of its region. In a
   fall trace only the main event (longest duration × highest frequency) is a
   fall; other events and all events of non-fall traces are non-falls.
8. **Classifier.** Min–max scaling and an RBF SVM with balanced class
   weights, `C` and `γ` from `2⁻⁵…2¹⁵` by five-fold balanced accuracy, all
   fitted on training events. A trace is a fall if any event is.

## Relation to FallDeFi

| Step | FallDeFi (paper or released code) | Here | Reason |
| --- | --- | --- | --- |
| Gaps | Interpolate all losses | Interpolate up to 0.25 s; drop failing receivers per trace | Scheduled, staggered 0.1 s gaps; requiring all four receivers kept 12 of 231 traces |
| Scale | Raw amplitude | Relative amplitude per tone | Separate radios with their own gain |
| Tones | 30 (Intel 5300) | 120 interior tones | More averaging in each component |
| Denoising | sym3; 10 levels (text), 4 levels (code) | sym3, 1 level | Keeps < 30 Hz untouched, as 4 levels do at 1000 Hz |
| PCA | Fewest components for 95 % variance (text); 3 (code) | 3 | The 95 % rule keeps 28 of 30 components of a quiet segment, so resting and activity spectrograms differ in averaging |
| STFT | 512 samples, overlap 256 at 1000 Hz | 64 samples, hop 32 at 120 Hz | Same duration and about the same bin width |
| Fusion | Plain average over antenna pairs | Average of per-receiver whitened spectrograms | Different noise per radio; resting floor at 24 Hz is 0.33–0.47 of its 6 Hz value |
| Noise threshold | Fit above 200–250 Hz; `k` tuned per link (text), 4.3 (code) | Fit to resting countdowns in 5–25 Hz; `k` calibrated to a detection target | No motion-free band at 120 Hz; in the first single-receiver run, `k = 4.3` found one event in 88 training traces |
| Region | Largest region (code), with dilation (text) | Region with most event-band magnitude | Large regions outside the band hid events |
| Features | Duration, two entropies, fractal dimension | Same; entropy by the paper's equation, dimension of the region mask as in the code | Kept for comparison |
| Imbalance | SMOTE (text), none (code) | Balanced class weights, balanced-accuracy selection | Accuracy selection collapsed to the majority class |

## Run on existing recordings

```bash
uv sync --extra analysis --extra radio
```

On the data laptop, check new settings on one session and leave
multi-session runs to the training device. This is the subset run of the
[22 November smoke report](../reports/falldefi-smoke-2026-11-22.md):

```bash
uv run python -m fall_detection.analysis.baselines.falldefi \
  --session data/raw/sessions/20261109T131546367822Z.zip \
  --fall-label walk_to_fall --fall-label sit_to_fall --fall-label stand_to_fall \
  --non-fall-label sit_to_stand --non-fall-label sit_to_walk \
  --non-fall-label stand_to_sit --non-fall-label stand_to_walk \
  --non-fall-label walk_to_sit --non-fall-label walk_to_stand \
  --output artifacts/baselines/falldefi/<new-run>
```

Repeat `--session` to combine sessions and add `--non-fall-label non_fall` for
the continuous non-fall session. `--split-by session` trains on one day and
tests on another. `--receivers` restricts the receivers considered; `--help`
lists every setting. Use a new output directory for every run.

Outputs are `model.joblib` (fitted detector, coordinates and parameters; load
only from trusted sources), `predictions.json` (each held-out trace with its
provenance, receivers used, target, prediction and events), and `report.json`
(source fingerprints, settings, exclusion counts, split, threshold
calibration, training events, SVM selection, held-out metrics, event
detection, false alarms, versions and code hashes), written last. Git does not
ignore `artifacts/baselines/falldefi/`; keep a run with
`uv run dvc add artifacts/baselines/falldefi/<run>` and commit only the `.dvc` file.

## Evaluation

The holdout groups by attempt by default; `--split-by session` and
`--split-by participant` give stronger separation. Up to 100 seeded
assignments are examined only to find both classes on each side. The unit of
evaluation is the trace, so a fall without a detected event is a missed fall.
The released `svm_example.m` instead drops such falls and fits scaling on
training and test data together, which makes its results more optimistic.

The report includes balanced accuracy, event detection per class, and false
alarms: fall-classified events in held-out non-fall traces per hour of those
traces. Protocol traces are dense with transitions, so this rate does not
describe continuous monitoring.

## Limitations

- The 9 November 13:15 session informed the hardware choices above; treat it
  as development data and evaluate on other sessions.
- Aliasing above 60 Hz and interpolation of the scheduled gaps alter the
  analysed band; neither is corrected.
- Resting floors and the threshold assume still countdowns, which have not
  been inspected; the detection target is a chosen setting.
- Action cues are collection instructions, not measured movement or impact
  times.
- An attempt holdout within one session does not establish generalization to
  new sessions, rooms or participants.

## Code and checks

`signal.py` holds relative amplitude, denoising, PCA and the STFT; `events.py`
holds region selection, events and features; `model.py` owns whitening,
fusion, threshold calibration and the classifier; `dataset.py` adapts
preserved sessions; `experiment.py` owns grouped evaluation and output;
`__main__.py` supplies the command. Session reading and gap filling are shared
with WiFall in `analysis/baselines/_recorded_attempts.py`, and the grouped holdout and
metrics in `analysis/baselines/_grouped_holdout.py`.

```bash
uv run ruff format src/fall_detection/analysis/baselines/falldefi tests/analysis/baselines/falldefi
uv run ruff check src/fall_detection/analysis/baselines/falldefi tests/analysis/baselines/falldefi
uv run pytest
```
