# Tone-averaged input for the sequence models, 23 November 2026

This report follows the [generalization report](generalization-2026-11-22.md),
where the sequence models fell to near chance on a held-out participant session
while FallDeFi kept attempt balanced accuracy 0.68–0.73. It asks which part of
our input identifies a session, and whether removing it helps across sessions.
A linear screen pointed to the per-tone layout. Averaging over tones removed
almost all idle false alarms and fixed the `khaelano` holdout, but it made the
`akmal` holdout worse. A model that encodes every tone with shared weights and
then pools over tones ranked windows well in both directions (window AUC
0.76–0.82 at 4 s), but it flagged up to 39 % of idle data from a new day. Its
max pooling caused that. Generalized-mean pooling, or a per-session quiet-floor
input, brought idle alarms below 5 % at 2 s and 4 s without losing ranking.
Across sessions, FallDeFi still has the best attempt score.

## Screen: which representation carries the session

The screen used the 2 s windows of the filtered-amplitude export
(`03_training/20261122T132757410153Z`, action attempts of `akmal` and
`khaelano`, 4600 windows). Each candidate was computed per window from the
Hampel-filtered amplitude `A`. A logistic or ridge model was then fitted to
each channel's median, 90th percentile and standard deviation:

- **Drift:** ridge R² of trial number on non-fall windows, attempt-grouped
  5-fold.
- **Session:** balanced accuracy of telling `akmal` from `khaelano` on
  non-fall windows.
- **Transfer:** window AUC of a fall probe trained on one session and tested
  on the other.
- **Within:** attempt-grouped 5-fold window AUC inside one session.

| Representation | Drift R² (akmal / khaelano) | Session | Transfer AUC (→akmal / →khaelano) | Within AUC |
| --- | --- | --- | --- | --- |
| `log1p(ΔA²)` per tone (current) | 0.07 / 0.44 | 1.00 | 0.72 / 0.24 | 0.98 / 1.00 |
| `(Δ ln A)²` per tone | 0.28 / 0.52 | 1.00 | 0.20 / 0.00 | 1.00 / 1.00 |
| `(Δ ln A)²`, 8 tone bands | 0.35 / 0.53 | 1.00 | 0.38 / 0.00 | 1.00 / 1.00 |
| `(Δ ln A)²`, 10/50/90 % over tones | 0.04 / 0.35 | 0.98 | 0.76 / 0.57 | 0.91 / 0.98 |
| `ΔA²`, mean over tones per receiver | −0.01 / 0.11 | 0.70 | 0.62 / 0.65 | 0.76 / 0.85 |
| `(Δ ln A)²`, mean over tones per receiver | 0.01 / 0.27 | 0.81 | 0.66 / 0.77 | 0.78 / 0.92 |
| `(Δ ln A)²`, mean over tones and receivers | −0.00 / 0.01 | 0.61 | 0.77 / 0.83 | 0.77 / 0.84 |

Every row is already a difference signal. Removing each tone's gain (the
log-ratio rows) did not reduce the session signature; only collapsing the tone
axis did. Our reading is that each tone's sensitivity and noise floor depend on
the room's multipath on that day. The pattern across tones then acts as a
session fingerprint, and the per-tone models can use it instead of motion. The
screen shows that the fingerprint is learnable, not that the deep models used
it. A per-window z-score (`log1p(ΔA²)` standardized per channel) did not remove
it either (session 0.96).

## Implementation

- `analysis/sequence/transforms.py` adds `tone_mean_squared_log_ratio`: for
  each receiver and sample, the mean over finite tones of
  `(ln A[t] − ln A[t−1])²`. Gaps are never differenced across.
- `02_preprocess` exports it as the variant `tone_mean_log_ratio`,
  `log1p(1000 · x)`, shape `[time, 4, 1]`, with the default export's windows,
  labels and presence masks. In the first 40 segments of each session
  the values have a median of about 1.4 and a 99th percentile of about 3.5.
- The sequence storage, training and GPU-cache code accept a tone axis of
  either 245 physical tones or one averaged value (`segments.TONE_LAYOUTS`).
  A run cannot mix the two. `03_training` takes its model input width from the
  normalizer: 12 features (4 signals, 4 validity flags, 4 presence flags)
  instead of 1964.
- The live detector computes only the default representation, so the variant
  stays offline.

## Holdouts

Each holdout repeats one from 22 November with `REPRESENTATION =
"tone_mean_log_ratio"`, the same split, seed 42 and model settings (CUDA,
RTX 4070 SUPER). `06_comparison` scored each run next to the 22 November
per-tone run and FallDeFi on the same test attempts. Sequence models use
threshold 0.5 and the any-window attempt rule. FallDeFi's attempt score covers
only the attempts it scored.

| Test | Per-tone median window AUC | Tone-mean median window AUC (range) | Best tone-mean attempt BA | FallDeFi attempt BA |
| --- | --- | --- | --- | --- |
| `akmal` | 0.70 | 0.59 (0.50–0.72) | 0.568 (GRU 2 s) | 0.678 |
| `khaelano` | 0.38 | 0.79 (0.58–0.86) | 0.678 (CNN 4 s) | 0.709 |
| `akmal` + continuous | 0.68 | 0.61 (0.43–0.67) | 0.530 (LSTM 2 s) | 0.732 |
| `khaelano`, all continuous in training | 0.41 | 0.78 (0.56–0.88) | 0.659 (CNN 4 s) | 0.688 |

Per-model values are in `window_auc.csv` (below).

- **`khaelano`.** The per-tone CNNs ranked `khaelano` windows almost exactly
  backwards (window AUC 0.04–0.11). On tone-mean input they reached 0.80–0.88.
  Seventeen of the 18 model results over both `khaelano` holdouts improved;
  LSTM 4 s held level (0.72 → 0.70). The best attempt
  score (CNN 4 s, 0.678) approaches FallDeFi's 0.709, but at a false-positive
  rate of 0.51 against FallDeFi's 0.42.
- **`akmal`.** Eight of nine models lost window AUC (0.70 → 0.59 median); only
  GRU 2 s gained (0.70 → 0.72). The
  per-tone models had transferred in this direction, as had the per-tone
  linear probe (0.72). Why the transfer is asymmetric is not known.
- **Idle continuous data, held out with `akmal`.** With per-tone input the
  models flagged 39–100 % of the continuous windows as falls. With tone-mean
  input, seven models flagged 0.6–7.5 %, while GRU 6 s and LSTM 6 s flagged 96 %
  and 90 %.
- **Attempt false positives.** At threshold 0.5, tone-mean models had attempt
  false-positive rates of 0.30–1.00, above 0.60 for 31 of the 36 models. Most non-fall attempts are
  cued transitions with real motion, and the any-window rule flags an attempt
  when one window crosses the threshold. A threshold calibrated on held-out
  sessions might help but was not tried.

## Tone-pooled encoder

Averaging over tones discards each tone's temporal detail. `TorchTonePool` in
`03_training` keeps it and still removes tone identity:

- **Shared encoder.** Each of the 980 tone-receiver series of the default
  per-tone input passes through the same two strided temporal convolutions
  (16 channels; inputs: value, validity flag, receiver presence flag).
- **Pooling and head.** Mean and max over all tones and receivers feed a
  temporal convolution and the binary head.
- **Dropout.** In training, 20 % of tones and 25 % of receivers are dropped at
  random.
- **Size and order.** The model has 7.8k parameters. Shuffling tones and
  receivers changes its output by about 4e-9, which is now a test.
- **Training settings.** Batch size 32; other settings as for the CNN.
- **Live fit.** It reads the same `[batch, time, 1964]` input as the live
  models. Its ONNX exports matched PyTorch to within 1e-6.

Only this model was trained; the CNN, LSTM and GRU rows are the 22 November
per-tone runs and the tone-mean runs above, on the same test attempts.

| Test | Per-tone median window AUC | Tone-mean median | Tone-pool 2 s / 4 s / 6 s window AUC | Best tone-pool attempt BA (FPR) | FallDeFi attempt BA (FPR) |
| --- | --- | --- | --- | --- | --- |
| `akmal` | 0.70 | 0.59 | 0.79 / 0.82 / 0.73 | 0.645 (0.70), 2 s | 0.678 (0.45) |
| `khaelano` | 0.38 | 0.79 | 0.72 / 0.76 / 0.67 | 0.642 (0.36), 2 s | 0.709 (0.42) |
| `akmal` + continuous | 0.68 | 0.61 | 0.79 / 0.82 / 0.72 | 0.553 (0.87), 6 s | 0.732 (0.39) |
| `khaelano`, all continuous in training | 0.41 | 0.78 | 0.71 / 0.76 / 0.65 | 0.628 (0.35), 2 s | 0.688 (0.47) |

- **Both directions.** Tone-pool 4 s reached window AUC 0.76–0.82 and 2 s
  0.71–0.79 in all four holdouts. Its 4 s worst case (0.76) is the best
  worst case of the 21 models compared. The next are tone-pool 2 s (0.71) and
  per-tone LSTM 4 s (0.69). The input medians fail in one direction each:
  per-tone input on `khaelano` and tone-mean input on `akmal`.
- **Per direction.** On `akmal`, tone-pool 4 s (0.82) beat every per-tone and
  tone-mean model. On `khaelano` it (0.76) sat below the tone-mean median
  (0.79).
- **Idle data.** Without continuous data from that day in training, tone-pool
  flagged 39 % (2 s), 31 % (4 s) and 9 % (6 s) of the continuous windows, more
  than seven of the nine tone-mean models (0.6–7.5 %). A likely contributor is
  the per-tone normalizer, fitted on the training sessions. In idle data the
  signal is mostly each tone's noise floor, which that normalizer does not
  match on a new day. This has not been tested.
- **Attempts.** At threshold 0.5 it stayed below FallDeFi in every holdout,
  with attempt false-positive rates of 0.35–1.00.
- **Limits.** One seed and three models per holdout. Early stopping on
  in-session validation stopped the 4 s model of the `akmal` run after ten
  epochs.

## Interpretation and limits

- Averaging over tones removed the failure that made the per-tone models
  unusable outside their training day: inverted ranking on `khaelano` and
  alarms throughout idle time. It does not yet beat FallDeFi at attempt level
  in any holdout. It also loses ranking quality on `akmal`, so per-tone input
  still carries something that transfers in that direction.
- The input now measures how much each receiver's signal changes, which
  separates "motion" from "stillness" better than "fall" from "posture
  change". FallDeFi adds what this lacks: event segmentation and features of
  how the motion unfolds in frequency (10–30 Hz entropy).
- Limits: two participant sessions in one room, one seed, one threshold, and
  `KEEP_SPLIT` and early stopping as on 22 November. Model selection still
  used validation attempts from the training sessions. The mattress confound
  remains inside both sessions.

### Why tone-pool flags idle data from an unseen day

`idle_diagnosis.py` reran the 2 s and 4 s tone-pool models of the `akmal` +
continuous holdout without retraining:

- **Training idle reference:** `khaelano` windows centred in `preparation` or
  `resting`.
- **Unseen idle:** the continuous hour.

| | 2 s | 4 s |
| --- | --- | --- |
| Continuous windows flagged | 39.5 % | 31.3 % |
| Pooled mean replaced by its training-idle average | 41.1 % | 31.2 % |
| Pooled max replaced by its training-idle average | 0.2 % | 0.0 % |
| Shift of pooled mean on the unseen day (training-idle SD, median) | 0.12 | 0.05 |
| Shift of pooled max | 1.02 | 1.15 |

The max branch alone produced the idle alarms. The normalized input of most
tones barely moved: the median shift was −0.04 SD. A minority shifted more,
with a 90th percentile of |shift| of 0.25 SD on the continuous hour and 0.14 SD
on `akmal`'s `preparation`/`resting` windows. Max pooling selects those tones.
So the per-tone training normalizer and max pooling together cause the alarms.

Aligning each tone's normalized input by the difference between its idle mean
on `akmal`'s `preparation`/`resting` windows and on `khaelano`'s fixed most of
it. This is a calibration from the protocol's quiet phases and uses no fall
labels.

| | 2 s raw → aligned | 4 s raw → aligned |
| --- | --- | --- |
| Continuous windows flagged | 39.5 % → 4.8 % | 31.3 % → 2.6 % |
| `akmal` window AUC | 0.785 → 0.793 | 0.815 → 0.826 |
| `akmal` non-fall windows flagged | 56 % → 32 % | 56 % → 36 % |
| `akmal` fall windows flagged | 89 % → 83 % | 98 % → 95 % |

The calibration windows come from the continuous hour's day, recorded about
3 h earlier. That matches an install-time calibration but does not show that
one calibration lasts across days. The model already flagged 5–7 % of
`khaelano`'s own quiet windows. The alignment was applied at test time only, in
one holdout with one seed.

### Fixes: quiet-floor input and generalized-mean pooling

Two fixes target the two causes:

- **Quiet floor** (`02_preprocess` variant `quiet_floor_squared_difference`).
  Each session's default `log1p(ΔA²)` has its own per receiver/tone mean
  subtracted. The mean is taken over the session's still samples: the
  `preparation` and `resting` phases of non-fall attempts, with gaps skipped.
  The variant is used in training as well as testing. `continuous_non_fall`
  has no such phases and takes `akmal`'s floor (same day). The two days'
  floors differ by a median of 0.003 and a 90th percentile |difference| of
  0.068.
- **Generalized-mean pooling** (`tonepool_gem`). A power mean with p = 3
  replaces the max over tones and receivers. Top-k and quantile pooling were
  not used because their CUDA backward passes are not deterministic. A first
  run produced NaN in every `tonepool_gem` model: when dropout removed all
  four receivers of a window, the root's gradient at zero was infinite. A
  floor of 1e-12 under the root fixed it (and is tested), and those runs were
  deleted and repeated.

Three variants ran in every holdout, with one seed, next to the earlier
tone-pool runs: `tonepool` on the quiet-floor input, and `tonepool_gem` on the
quiet-floor and on the default input.

**Idle continuous windows flagged** (`akmal` + continuous holdout, unseen day):

| Variant | 2 s | 4 s | 6 s |
| --- | --- | --- | --- |
| Tone-pool (max), default input | 39.5 % | 31.3 % | 9.2 % |
| Tone-pool (max), quiet floor | 4.6 % | 2.6 % | 6.5 % |
| GeM, default input | 2.6 % | 3.8 % | 100 %* |
| GeM, quiet floor | 0.8 % | 0.8 % | 100 %* |

\* Both 6 s GeM models of this holdout never learned. Their training loss
stayed at 1.055, and early stopping kept epoch 2, a checkpoint that calls
every window a fall (validation F1 0.385, the all-positive value). This is a
failed training on `khaelano` alone, not idle behaviour.

**Window AUC** (2 s / 4 s / 6 s):

| Variant | `akmal` | `khaelano` | `akmal` + continuous | `khaelano`, all continuous |
| --- | --- | --- | --- | --- |
| Tone-pool (max), default | 0.79 / 0.82 / 0.73 | 0.72 / 0.76 / 0.67 | 0.79 / 0.82 / 0.72 | 0.71 / 0.76 / 0.65 |
| Tone-pool (max), quiet floor | 0.79 / 0.82 / 0.73 | 0.72 / 0.77 / 0.68 | 0.79 / 0.83 / 0.75 | 0.71 / 0.77 / 0.66 |
| GeM, default | 0.79 / 0.83 / 0.75 | 0.75 / 0.76 / 0.66 | 0.80 / 0.84 / 0.75 | 0.73 / 0.76 / 0.65 |
| GeM, quiet floor | 0.78 / 0.82 / 0.74 | 0.75 / 0.77 / 0.67 | 0.80 / 0.84 / 0.75 | 0.73 / 0.76 / 0.66 |

- **Idle alarms.** Either fix alone brought the 2 s and 4 s models below 5 %
  of idle windows on the unseen day, and both together to 0.8 %. GeM needs no
  calibration and no change to live preprocessing. The quiet floor needs a
  still-room calibration.
- **Ranking.** Neither fix cost window AUC. The changes are within ±0.03 of
  tone-pool on default input, and 4 s stays at 0.76–0.84 in every holdout.
- **Attempts.** At threshold 0.5 with the any-window rule, no variant reached
  FallDeFi. The best attempt balanced accuracies were 0.64–0.65 on `akmal`
  and `khaelano` and 0.638 on `akmal` + continuous (GeM 4 s, quiet floor),
  against FallDeFi's 0.68–0.73. Attempt false-positive rates stayed at
  0.33–1.00, because most non-fall attempts contain cued motion. The decision
  rule, not idle data, now limits the attempt score.
- **Limits.** One seed. Checkpoint selection by in-session validation F1 kept
  degenerate checkpoints at 6 s.

## Frequency features without gap filling

Two further linear screens (`stft_screen.py`, `gap_screen.py`) tested
frequency information on the tone- and receiver-averaged signal. The baseline
is lag-1 energy averaged over tones and receivers, with transfer AUC
0.77 / 0.83:

| Input | Gaps | Transfer AUC (→akmal / →khaelano) |
| --- | --- | --- |
| Lags 1, 2, 4, 8, 16 | Left empty | 0.77 / 0.85 |
| STFT on complete 0.27 s frames | Left empty | 0.74 / 0.83 |
| Same STFT, plus band shape | Left empty | 0.77 / 0.84 |
| 0.53 s STFT, bands plus shape | Interpolated | 0.78 / 0.87 |

- **Respecting gaps,** frequency detail added at most 0.02.
- **Frame-based spectra fit poorly.** Only 33 % of 0.27 s tone frames were
  complete.
- **Interpolation adds its own structure.** The receivers lose 0.1 s bursts
  every 0.57 s, so interpolation adds a repeating pattern near 1.8 Hz. No
  spectral transform was added to the pipeline.

## Next steps (not yet run)

1. Replace threshold 0.5 and the any-window attempt rule with a debounced
   rule, and choose the threshold for a target false-positive rate. Select
   checkpoints by validation loss or a fixed epoch count, which would avoid
   the degenerate 6 s checkpoints.
2. Repeat tone-pool GeM over several seeds before comparing it with FallDeFi
   or the nine-model medians.
3. For live use, register the `tonepool` families in the Rust detector. The
   quiet-floor variant would also need a still-room calibration step.
4. Record non-fall activity with the mattress in place.

## Runs and diagnostics

All under `artifacts/notebooks/`, tracked by `artifacts/notebooks.dvc`. Each
03 and 06 run directory holds its executed notebook.

| Test | Tone-mean `03_training` | `06_comparison` | Per-tone `03_training` (22 Nov) |
| --- | --- | --- | --- |
| `akmal` | `20261123T015131839289Z` | `20261123T015311577831Z` | `20261122T142645580923Z` |
| `khaelano` | `20261123T015313318646Z` | `20261123T015450559319Z` | `20261122T144153598173Z` |
| `akmal` + continuous | `20261123T015452308462Z` | `20261123T015623488873Z` | `20261122T161026536973Z` |
| `khaelano`, `KEEP_SPLIT = ()` | `20261123T015625318735Z` | `20261123T015805516190Z` | `20261122T165919454776Z` |

Tone-pool `03_training` runs (each with its `06_comparison`) are listed in
`tonepool_runs.json`: `20261123T031331740106Z` (`akmal`),
`20261123T031715857223Z` (`khaelano`), `20261123T032030242464Z` (`akmal` +
continuous) and `20261123T032219481778Z` (`khaelano`, `KEEP_SPLIT = ()`).

Quiet-floor and GeM runs are listed in `floor_gem_runs.json` (one quiet-floor
and one default `03_training` run plus one `06_comparison` per holdout).

`diagnostics/20261123-tone-pooling/` holds the screen scripts and results
(`level_screen*.py`, `screen_results.txt`, `stft_screen*`, `gap_screen*`), the
holdout runners (`tone_mean_holdouts.py` with `runs.json`,
`tonepool_holdouts.py` with `tonepool_runs.json`, `floor_gem_holdouts.py` with
`floor_gem_runs.json`), the idle diagnosis (`idle_diagnosis.py`,
`idle_diagnosis.json`), and `window_auc.py` with `window_auc.csv`. The export is
`data/processed/amplitude_sequence/120hz-tone_mean_log_ratio/` (not
DVC-tracked; regenerate with `02_preprocess`).
