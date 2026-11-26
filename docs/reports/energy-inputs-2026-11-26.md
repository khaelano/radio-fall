# Spectrograms, quiet baseline and motion-energy models, 26 November 2026

This report follows the [tone-pooling report](tone-pooling-2026-11-23.md), whose
most consistent model is `tonepool_tcn` at 4 s with burst-centred labels. It asks
what the model's input contains and whether a simpler input does as well. The
amplitude's fast fluctuations carry most of the difference between falls and
posture transitions, and squaring the difference removes their frequency
structure. Keeping that structure (the signed difference) did not help the model.
A causal quiet baseline removed level drift within a session but did not make
thresholds portable between participants. A model with 5,345 parameters that sees
only the mean motion energy over tones and receivers matched `tonepool_tcn`
(69,649 parameters): mean attempt AUC 0.846 against 0.836 over four holdouts,
better when tested on `akmal` and slightly worse on `khaelano`.

## Conditions

- Sessions `khaelano` (`20261104T081805521126Z`), `akmal`
  (`20261109T131546367822Z`) and `continuous_non_fall`
  (`20261109T161519702956Z`), read from the arrays staged by `02_preprocess`
  (120 Hz, Hampel-filtered amplitude and squared difference).
- Code: the working tree on top of `06500be`. No source file changed.
- Trained models use the burst-label `tonepool_tcn` configuration: 4 s windows,
  seeds 42–45, the four session holdouts, checkpoint by validation balanced log
  loss. A repeat of one earlier run (seed 42, test `akmal`) reproduced its 1,352
  test probabilities exactly, so earlier runs serve as the baseline. Calibrated
  rates use ten random non-fall attempts and a 0.2 target, with the same draws for
  every model (they differ by about 0.01 from the earlier reports' draws).
- Untrained screens score falls against posture transitions on attempts or on
  windows centred in the action cue. Every number here comes from the two
  participant sessions in one room, with every fall recorded after every
  non-fall, mattress in place.

## Noise and smoothing

`20261125-noise-and-smoothing/`: `noise.py`, `lag_auc.py`.

- **Hampel leaves small fluctuations alone.** It replaced 0.83 % (`akmal`) and
  0.95 % (`khaelano`) of valid samples.
- **Per tone, the 1-sample change is mostly noise.** While still, a tone's
  relative amplitude changes almost as much over 1 sample as over 24 (white noise,
  roughly 5 % of the amplitude). Within ±1 s of a fall's main burst, the 1-sample
  change energy is 1.26 (`akmal`) and 1.35 (`khaelano`) times the still level.
  About 5 % of a receiver's still change is common to all its tones.
- **Smoothing loses fall information.** A moving average of width *w* followed by
  the 1-sample difference equals the *w*-sample difference divided by *w*. Scoring
  each attempt by its peak tone- and receiver-averaged change energy (untrained):

  | Width (samples) | 1 | 2 | 4 | 8 | 16 |
  | --- | --- | --- | --- | --- | --- |
  | Falls against transitions, `akmal` | 0.64 | 0.61 | 0.53 | 0.51 | 0.49 |
  | Same, `khaelano` | 0.77 | 0.79 | 0.75 | 0.76 | 0.74 |

  This score averages power over tones, which hides activity (see the next
  section), so its absolute values are low; the direction agrees with the band
  results below.

## Spectrograms

`notebooks/latest/01_03_amplitude_spectral.ipynb` applies one STFT (Hann,
64 samples = 0.53 s, hop 8, FFT 128) to the squared difference, the signed
difference and the filtered amplitude, per tone, averaged in dB over each
receiver's tones and shown as the change over the median of the frames before the
action cue.

- **Gaps.** Every receiver loses 12 consecutive samples of every 68, so no frame
  is complete. Frames are masked rather than interpolated: each frame's weighted
  linear trend is removed, missing samples get weight zero, and power is divided
  by the summed squared weights. On white noise with a real gap pattern, masking
  stayed within 0.4 dB of the gap-free spectrum from about 4 Hz, while linear
  interpolation added 2.4 dB near 4 Hz and removed about 1 dB above 20 Hz. A
  strong component leaks into neighbouring bins with masking.
- **Averaging.** Averaging power over tones let a few noisy tones dominate and hid
  falls in the squared difference (a preliminary check, not kept); averaging dB
  showed them and makes each tone's gain a constant that the quiet reference
  removes.
- **The amplitude's band widens with the movement.** Sitting down and standing up
  stay mostly below 20 Hz and walking transitions below about 40 Hz, while falls
  reach 60 Hz around the main burst, often as a rising track. Power at 60 Hz, half
  the sampling rate, means faster fluctuations fold back.
- **The squared difference is flat over frequency.** Its change at the burst
  (±0.25 s, all falls) varies by 0.33 (`khaelano`) and 0.23 (`akmal`) of its
  mean over frequency, against 1.32 and 0.80 for the amplitude. Shuffling its
  samples within 0.13 s blocks keeps the mean change (4.67 against 4.82 dB and
  5.71 against 5.84 dB) and flattens it further (0.08 and 0.05): the bar reports
  how large the values are, not when they occur. Squaring mixes every pair of
  frequencies present and turns noise-like changes into nearly uncorrelated
  spikes.
- **The signed difference keeps the structure.** Its change over quiet follows
  the amplitude's at every frequency (range over frequency 1.21 and 0.83 of its
  mean, against 1.32 and 0.80), because the power factor of differencing,
  4 sin²(πf/120), is the same in quiet and motion.

Falls against transitions, attempt AUC of each band's 90th-percentile change from
0.5 s before to 1 s after the action cue (untrained; bands examined after the
spectrograms were seen; 95 % intervals about ±0.06):

| Band | Squared difference, `khaelano` / `akmal` | Signed difference | Filtered amplitude |
| --- | --- | --- | --- |
| 2–10 Hz | 0.76 / 0.75 | 0.61 / 0.47 | 0.58 / 0.41 |
| 10–20 Hz | 0.77 / 0.76 | 0.62 / 0.60 | 0.62 / 0.59 |
| 20–30 Hz | 0.76 / 0.76 | 0.73 / 0.71 | 0.73 / 0.71 |
| 30–45 Hz | 0.75 / 0.74 | 0.83 / 0.80 | 0.82 / 0.79 |
| 45–60 Hz | 0.74 / 0.72 | 0.78 / 0.80 | 0.80 / 0.78 |

## Signed difference as model input

`20261125-signed-difference/`: `export_signed.py` writes
`amplitude_sequence/120hz-signed_difference/` (4.6 GB, reproducible in about
30 s; equal to the default export up to square and `log1p`, with identical
validity and presence); `signed_seed_holdouts.py`, `compare_signed.py`.

- **Why it was tried.** Unlike the filtered amplitude, it has no static level:
  each tone's mean shifted between the participant sessions by a median of 1.07–1.34
  training standard deviations in the amplitude and 0.06 in the squared difference
  (`20261125-noise-and-smoothing/shift.py`).

| Test | Attempt AUC, squared → signed | Calibrated recall | Seeds higher |
| --- | --- | --- | --- |
| `akmal` | 0.85 → 0.79 | 0.73 → 0.60 | 1 of 4 |
| `akmal` + continuous | 0.81 → 0.80 | 0.62 → 0.59 | 1 of 4 |
| `khaelano` | 0.84 → 0.84 | 0.68 → 0.68 | 2 of 4 |
| `khaelano`, all continuous in training | 0.84 → 0.88 | 0.69 → 0.76 | 3 of 4 |

Calibrated false-positive rates were 0.21–0.25 for both. The signed input varied
more between seeds (attempt AUC SD 0.04–0.06 in three tests against 0.01–0.05).
Like `tonepool_tcn_lags`, it gained when trained on `akmal` and lost when trained
on `khaelano`, by less. The squared difference stays the input.

## Causal quiet baseline

`20261126-quiet-baseline/`: `quiet_baseline.py`, `checks.py`.

- **Rule.** Energy is the mean squared change per receiver and tone over 0.5 s
  (hop 0.1 s). The baseline is the mean energy over the past blocks whose pooled
  energy (dB over tones, centred per receiver, averaged over receivers) ranks in
  the lowest *keep* share of a window of recorded history ending 4 s before the
  block. Output: dB over baseline, averaged over tones and then present receivers.
  This is an order-statistic rule, related to OS-CFAR and trimmed-mean CFAR in
  radar (not yet cited from a source).
- **Score.** The 90th percentile of that output from 0.5 s before to 1 s after the
  action cue. Attempts every method scores: 231 (`khaelano`) and 228 (`akmal`).

| Baseline | AUC `khaelano` | AUC `akmal` |
| --- | --- | --- |
| None | 0.70 | 0.75 |
| Other session's fixed quiet floor | 0.70 | 0.75 |
| Own session's quiet phases (offline) | 0.70 | 0.75 |
| Own attempt's preparation phase (offline, cue needed) | 0.78 | 0.76 |
| Keep 100 % (plain mean), 60 s | 0.75 | 0.76 |
| Keep 75 %, 60 s | 0.78 | 0.76 |
| Keep 50 %, 60 s | 0.78 | 0.75 |
| Keep 20 %, 60 s | 0.78 | 0.75 |

- **Keep share and window barely matter.** Over 15, 60 and 120 s and keeps of 20,
  50 and 75 %, AUC stayed within 0.77–0.79 (`khaelano`) and 0.75–0.77 (`akmal`).
  Keep 75 % against 50 % or 20 % differed by at most 0.006. Keep 75 % gave the
  steadiest baseline (SD over time 0.39, 0.29 and 0.19 dB on `khaelano`, `akmal`
  and the continuous hour at 60 s) and a quiet level 0.16–0.19 dB below zero;
  keep 50 % was unbiased (−0.05 to 0.00 dB).
- **Trimming helped in one session.** Keep 75 % against the plain mean: +0.033
  [0.018, 0.049] on `khaelano`, −0.007 [−0.022, 0.007] on `akmal` (paired
  bootstrap over attempts).
- **The gain on `khaelano` is drift correction.** Its quiet level fell over the
  session (Spearman −0.53 with attempt order; −0.55 dB in the first third,
  −0.87 dB in the last), and every fall came last, so a fixed floor understated
  falls. Keep 75 % against no baseline: +0.082 [0.064, 0.104] on `khaelano` and
  +0.006 [−0.001, 0.014] on `akmal`, which had no drift (Spearman −0.02). Part of
  the gain is specific to this recording order.
- **Idle.** On the continuous hour, 0.52 %, 0.28 % and 0.08 % of 0.5 s blocks
  exceeded 1, 2 and 3 dB.
- **Long movement lifts it little.** With the last 30 s of a 60 s history replaced
  by walking-transition blocks, the keep-75 % baseline was 0.15 (`khaelano`) and
  0.05 dB (`akmal`) above the mean of quiet blocks, against −0.11 and −0.18 dB
  with 15 s of 120 s. Transitions raise the tone-averaged energy little (median
  attempt score 0.9–1.2 dB over quiet), so they barely move a trimmed mean.
- **It does not make thresholds portable.** With a threshold giving 20 % false
  alarms on one session's attempts: trained on `khaelano`, `akmal` had 31 %
  false alarms and 66 % recall; trained on `akmal`, `khaelano` had 4 % and 15 %.
  The baseline aligns quiet levels; `akmal` moves more strongly (median fall
  score 2.4 against 1.9 dB, transitions 1.2 against 0.9 dB).

## Combining receivers and tones

`20261126-receiver-collapse/`: `collapse_screen.py`, `fair_compare.py`.

Each input gives per 4 s window, per channel, the median, 90th percentile and
standard deviation over time; a logistic probe (C = 0.05, class-balanced) reads
them, as in the tone-pooling level screen. Session: balanced accuracy of telling
the sessions apart on still windows (preparation or resting of non-falls; 0.5 = no
signature), 5-fold by attempt. Falls: trained on one session's action-cue windows,
tested on the other's; an attempt's score is its highest window. Windows with a
baseline: 1,055 of 1,061 (`khaelano`), 1,049 of 1,055 (`akmal`).

| Input | Channels | Session, still windows | Attempt AUC → `akmal` / → `khaelano` |
| --- | --- | --- | --- |
| Receiver × tone, dB, no baseline (like the current input) | 980 | 1.00 | 0.70 / 0.30 |
| Receiver × tone, dB over quiet | 980 | 0.66 | 0.77 / 0.48 |
| Receivers averaged per tone, dB over quiet | 245 | 0.55 | 0.54 / 0.62 |
| Same, generalized mean (p = 3) over receivers | 245 | 0.53 | 0.50 / 0.56 |
| Receivers averaged per tone, no baseline | 245 | 1.00 | 0.58 / 0.49 |
| Amplitude averaged over receivers, then squared difference | 245 | 0.99 | 0.47 / 0.74 |
| Same on relative amplitude (offline median) | 245 | 1.00 | 0.36 / 0.31 |
| Tones averaged, four receivers, dB over quiet | 4 | 0.62 | 0.77 / 0.81 |
| Tones averaged, four receivers, no baseline | 4 | 0.77 | 0.75 / 0.86 |
| Tones and receivers averaged, dB over quiet | 1 | 0.59 | 0.80 / 0.81 |
| Tones and receivers averaged, no baseline | 1 | 0.60 | 0.83 / 0.84 |

- **The quiet baseline removes the session signature**; averaging receivers per
  tone removes most of what remains. Without the baseline, averaging leaves it.
- **Per-tone inputs do not transfer.** Receivers averaged per tone reached window
  AUC 0.90 within each session but 0.54–0.62 across. A linear probe treats each
  tone separately, so this does not rule out the input in a model that pools tones.
- **Averaging raw amplitude keeps the signature.** The set of present receivers
  changes at 12.4–12.8 % of samples; there, still-phase squared change was 1.6
  (`khaelano`) and 1.4 (`akmal`) times larger than elsewhere, 1.1 times on
  relative amplitude.
- **A single energy channel came close to `tonepool_tcn`.** On identical windows,
  the one-channel probe (no baseline) against the mean of `tonepool_tcn`'s four
  seeds: attempt AUC over action-cue windows 0.83 against 0.85 (`akmal`; −0.03
  [−0.07, 0.01]) and 0.84 against 0.85 (`khaelano`; −0.005 [−0.05, 0.03]); over
  all windows of an attempt 0.79 against 0.85 (−0.06 [−0.11, −0.02]) and 0.81
  against 0.84 (−0.04 [−0.08, 0.00]). The probe was trained on action-cue windows
  only, which favours `tonepool_tcn` on all windows.

## Tiny energy models

`20261126-tiny-tcn/`: `tiny_holdouts.py` (in-memory copies of `03_training`
with three added model classes), `compare_tiny.py`.

The default normalized input is collapsed inside the model: valid
tone-receiver values are averaged per sample, with the tone-pool models' tone and
receiver dropout in training. No preprocessing or export changes, so the Rust
detector could run them after registering the family.

- `tiny_tcn1`: one signal (mean), two strided convolutions (480 → 120 steps,
  16 channels), five residual dilated convolutions (1–16, about 2.2 s), max and
  mean over time, linear head. 5,345 parameters.
- `tiny_tcn3`: the same on mean, spread and coverage. 5,505 parameters.
- `tiny_cnn3`: the same three signals, six strided convolutions (about 2.1 s,
  14 channels) instead of dilation. 5,223 parameters.

Widths were fixed before training and training settings are `tonepool_tcn`'s, not
tuned.

| Test | Attempt AUC: `tonepool_tcn` / `tiny_tcn1` / `tiny_tcn3` / `tiny_cnn3` | Calibrated recall, same order |
| --- | --- | --- |
| `akmal` | 0.85 / 0.86 / 0.88 / 0.85 | 0.73 / 0.76 / 0.79 / 0.71 |
| `akmal` + continuous | 0.81 / 0.87 / 0.84 / 0.82 | 0.62 / 0.76 / 0.68 / 0.67 |
| `khaelano` | 0.84 / 0.82 / 0.82 / 0.80 | 0.68 / 0.67 / 0.66 / 0.64 |
| `khaelano`, all continuous in training | 0.84 / 0.83 / 0.83 / 0.80 | 0.69 / 0.69 / 0.68 / 0.64 |
| Mean | 0.836 / 0.846 / 0.843 / 0.819 | |

Calibrated false-positive rates were 0.22–0.25 for every model, and at most 0.7 %
of the unseen continuous windows were flagged at 0.5.

Paired bootstrap over attempts, difference of mean attempt AUC over seeds (seeds
in which the first model was higher):

| Test | `tiny_tcn1` − `tonepool_tcn` | `tiny_tcn3` − `tiny_cnn3` | `tiny_tcn3` − `tiny_tcn1` |
| --- | --- | --- | --- |
| `akmal` | +0.01 [−0.01, 0.04] (3) | +0.03 [0.01, 0.05] (1) | +0.02 [0.00, 0.03] (1) |
| `akmal` + continuous | +0.06 [0.02, 0.09] (3) | +0.02 [−0.01, 0.05] (3) | −0.03 [−0.06, 0.00] (2) |
| `khaelano` | −0.02 [−0.04, 0.00] (1) | +0.02 [0.00, 0.04] (3) | 0.00 [−0.01, 0.01] (2) |
| `khaelano`, all continuous | −0.01 [−0.03, 0.01] (0) | +0.03 [0.01, 0.05] (4) | 0.00 [−0.01, 0.01] (1) |

- **The tiny model matches `tonepool_tcn`.** It was better when tested on `akmal`
  and slightly worse on `khaelano`, with 13 times fewer parameters. Its seeds
  varied more on `akmal` (attempt AUC SD 0.04 against 0.02).
- **One signal is enough.** Spread and coverage added nothing consistent.
- **Dilation beat striding, modestly.** `tiny_tcn3` exceeded `tiny_cnn3` in all
  four tests, with intervals excluding zero in three. On `akmal` the CNN was higher
  in three of four seeds; the mean favoured the TCN because one CNN run reached
  only 0.73.
- **Cost.** One ONNX window took a median 0.25 ms (`tiny_tcn1`, 48 KiB) against
  4.35 ms (`tonepool_tcn`, 319 KiB) on the Intel i7-14700F with ONNX Runtime
  1.31.1, four non-spinning threads, batch 1. The export's logit check passed in
  every run.

## Interpretation and limits

- Most of `tonepool_tcn`'s separation of falls from transitions comes from how the
  overall motion energy develops over about 2 s. The per-tone encoder adds little
  here, and inputs that keep per-tone or per-frequency detail (signed difference,
  multi-lag) shift performance between the two training directions rather than
  raising it. Whether more participants change this is unknown.
- The fast part of the amplitude (30–60 Hz) separates falls best in the untrained
  screens; the squared difference already weights fast changes most
  (4 sin²(πf/120): 0.27 at 10 Hz, 2 at 30 Hz, 4 at 60 Hz), which may explain why
  smoothing hurt and why a frequency view added little to a trained model. Not
  tested directly.
- Thresholds remain specific to the person: neither the quiet baseline nor any
  input here aligned how strongly the two participants move. The installation
  calibration stays necessary.
- Limits: two participants and one room; falls only after non-falls with the
  mattress in place; untrained screens with band choices made after viewing; the
  tiny models were motivated by a screen on the same sessions; paired intervals
  cover the tested attempts, not training randomness; recorded history covers only
  attempts (21 % and 45 % of the two participant sessions' time).

## Next steps

1. Done the same day: `tiny_tcn1-4s` is selectable in the live detector and
   matched the offline chain on replay; `tonepool_tcn` stays the default until a
   new participant confirms the result
   ([live tiny-TCN report](live-tiny-tcn-2026-11-26.md)).
2. Not run: collect sessions from more participants, with non-falls on the
   mattress and interleaved trial order; this addresses threshold portability
   and the direction dependence that every representation change met.

## Runs and files

Diagnostics under `artifacts/notebooks/diagnostics/`; training runs under
`artifacts/notebooks/03_training/`, tracked by `artifacts/notebooks.dvc`.

| Experiment | Directory or runs |
| --- | --- |
| Noise, smoothing, level shift | `20261125-noise-and-smoothing/` |
| Spectrograms | `notebooks/latest/01_03_amplitude_spectral.ipynb` |
| Signed difference | `20261125-signed-difference/`; control `20261125T165348233165Z`; 16 runs `20261125T165508340783Z` to `20261125T171324045068Z` (`signed_runs.json`) |
| Quiet baseline | `20261126-quiet-baseline/` |
| Receiver and tone collapse | `20261126-receiver-collapse/` |
| Tiny models | `20261126-tiny-tcn/`; 16 runs `20261125T181658450435Z` to `20261125T182746090897Z` (`tiny_runs.json`) |
| Baseline `tonepool_tcn` runs | `20261123-tone-pooling/burst_seed_runs.json` |
