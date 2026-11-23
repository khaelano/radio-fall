# Tone-averaged input for the sequence models, 23 November 2026

This report follows the [generalization report](generalization-2026-11-22.md),
where the sequence models fell to near chance on a held-out participant session
while FallDeFi kept attempt balanced accuracy 0.68–0.73. It asks which part of
our input identifies a session, and whether removing it helps across sessions.
A linear screen pointed to the per-tone layout. Averaging over tones removed
almost all idle false alarms and fixed the `khaelano` holdout, but it made the
`akmal` holdout worse. A model that encodes every tone with shared weights and
then pools over tones kept window AUC 0.76–0.82 at 4 s in both directions, but
it flagged up to 39 % of idle data from a new day. Its max pooling caused
that. Generalized-mean pooling, or a per-session quiet-floor input, brought
idle alarms to about 1 % without lowering window AUC. Window AUC, however,
mostly measured motion against stillness. On windows of the action cue, where
non-falls are posture transitions, no input separated falls from transitions
in both directions (best medians about 0.52–0.70 depending on input and
direction), and a threshold chosen on validation attempts could not
compensate. Giving the tone-pooled model a seconds-long temporal view
changed that: at 4–6 s it separated falls from transitions at 0.78–0.91 in
both directions. It ranked attempts at least as well as FallDeFi (attempt
AUC 0.77–0.88) and scored the attempts FallDeFi drops, with idle alarms
about 1 % (one seed; the mattress confound applies).

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

- **Both directions.** (Window AUC here includes quiet windows; see
  [what window AUC measured](#what-window-auc-measured) for the action-cue
  windows alone.) Tone-pool 4 s reached window AUC 0.76–0.82 and 2 s
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
- **Window AUC.** Neither fix lowered it. The changes are within about ±0.03
  of tone-pool on default input, and 4 s stays at 0.76–0.84 in every holdout.
  Mostly this is motion against stillness; see
  [what window AUC measured](#what-window-auc-measured).
- **Attempts.** At threshold 0.5 with the any-window rule, no variant reached
  FallDeFi. The best attempt balanced accuracies were 0.64–0.65 on `akmal`
  and `khaelano` and 0.638 on `akmal` + continuous (GeM 4 s, quiet floor),
  against FallDeFi's 0.68–0.73. Attempt false-positive rates stayed at
  0.33–1.00, because most non-fall attempts contain cued motion. The decision
  rule, not idle data, now limits the attempt score.
- **Limits.** One seed. Checkpoint selection by in-session validation F1 kept
  degenerate checkpoints at 6 s.

## Decision rule chosen on validation

The attempt scores above use threshold 0.5, and an attempt alarms when any
window does. Step 2 replaced both:

- **Checkpoint.** The tone-pool models now choose their checkpoint by a
  balanced log loss on validation: the mean of the two classes' log losses.
  A model calling every window a fall cannot win it. CNN, LSTM and GRU keep
  validation F1.
- **Rule.** `comparison.debounce` raises an alarm only for a window that
  completes a run of `k` overlapping alarmed windows in one segment.
- **Threshold.** `comparison.choose_threshold` picks the threshold on
  validation attempts so that at most 20 % of non-fall attempts alarm. It
  returns the midpoint of the interval that gives that result.
  `comparison.attempt_scores` makes the choice exact.
- **Where.** `06_comparison` reports the result in `decision_rule.csv`, for
  `k` = 1 and 2.

`tonepool_gem` was retrained this way on the default and quiet-floor inputs
for the four holdouts (`decision_rule_holdouts.py`).

- **Checkpoints.** The degenerate 6 s models are gone. On the unseen idle day
  all six models flagged 0.5–1.0 % of continuous windows (6 s: 1.0 % and
  0.8 %, against 100 % with F1 checkpoints). Attempt balanced accuracy at 0.5
  for the 6 s models of that holdout rose from 0.50 to 0.66.
- **Thresholds made attempts worse.** At the 20 % target, the validation
  attempts reached a recall of only 0.00–0.33. Even inside the training
  sessions, the models could not separate fall attempts from transitions at
  low false-positive rates, so the chosen thresholds were 0.62–1.00. On the
  test attempts, balanced accuracy fell to 0.39–0.57, against 0.47–0.67 at
  0.5. The test false-positive rate was 0.25–0.33 in the two `akmal`
  holdouts and 0.01–0.05 in the two `khaelano` holdouts, where the models
  almost never alarmed (recall 0.03–0.06).
  `k` = 2 did not help.

### What window AUC measured

Fall attempts keep only windows centred in the action cue; non-fall attempts
keep every window, including still `preparation` and `resting` windows.
`attempt_span.py` and `window_auc.py` separate the two:

- **Attempt AUC.** With attempts scored by their highest window, attempt AUC
  was 0.50–0.67. It changed by at most 0.012 when non-fall attempts kept only
  their action windows, so the extra windows were not the cause.
- **Action-cue windows.** Restricted to windows centred in the action cue,
  window AUC fell sharply:

| Input | Test `akmal`: all / action windows | `khaelano` | `akmal` + continuous | `khaelano`, all continuous |
| --- | --- | --- | --- | --- |
| Per-tone (median of 9) | 0.70 / 0.59 | 0.38 / 0.40 | 0.68 / 0.57 | 0.41 / 0.39 |
| Tone mean (median of 9) | 0.59 / 0.50 | 0.79 / 0.68 | 0.61 / 0.52 | 0.79 / 0.70 |
| Tone-pool GeM, loss checkpoint (median of 3) | 0.79 / 0.65 | 0.73 / 0.53 | 0.80 / 0.69 | 0.73 / 0.53 |

The high window AUCs came mostly from telling motion from stillness. On
action-cue windows, falls and posture transitions are what remain. There the
best input depends on the direction: tone mean on `khaelano` (median 0.68 and
0.70, best model 0.75 and 0.77), and tone-pool on `akmal` (0.63–0.70). No input
separates them in both directions. A threshold cannot fix a ranking this
weak, which explains the step-2 result.

## Training for falls against transitions

`03_training` gained two options:

- **`hard_negative_weight`** multiplies the training loss of non-fall windows
  centred in a cued transition's action cue. Quiet windows and continuous data
  keep weight 1.
- **`checkpoint_metric = "action_balanced_log_loss"`** selects the checkpoint
  on validation windows of the action cue.

`06_comparison` now reports window AUC on all windows and on action-cue
windows (`window_auc.csv`, from `comparison.phase_window_auc`). Three
configurations ran on the four holdouts (`hard_negative_holdouts.py`), all
with action-cue checkpoints. Weight 5 was set in advance, not tuned.

| Median action-cue window AUC | `akmal` | `khaelano` | `akmal` + continuous | `khaelano`, all continuous |
| --- | --- | --- | --- | --- |
| Tone-pool GeM, balanced-loss checkpoint (step 2) | 0.65 | 0.53 | 0.69 | 0.53 |
| A: GeM, weight 1 | 0.56 | 0.53 | 0.70 | 0.53 |
| B: GeM, weight 5 | 0.68 | 0.52 | 0.29 | 0.50 |
| C: CNN/LSTM/GRU on tone mean, weight 5 | 0.50 | 0.55 | 0.48 | 0.57 |
| Tone mean (earlier, 9 models) | 0.50 | 0.68 | 0.52 | 0.70 |

- **Action-cue checkpoints.** They did not help. On `akmal` the median fell
  from 0.65 to 0.56, in a run that differs from step 2 only in which epoch was
  kept. Selection on the small action-cue validation set is noisy.
- **Weight 5.** It destabilized training. Trained on `khaelano` alone, the B
  models ranked `akmal` windows backwards (window AUC 0.17–0.22). At 0.5,
  many B and C models predicted no falls at all.
- **One direction only.** The best single model, tone-mean CNN 4 s with
  weight 5, reached 0.80 on `khaelano` and 0.45 on `akmal`. The better input
  depends on which session is trained on. With two sessions and one seed,
  such direction effects cannot be separated from noise.

## Burst features

`burst_screen.py` asked whether hand-made descriptions of a motion burst
separate falls from transitions. Each unit is one cued attempt of `akmal` (87
falls, 144 transitions) or `khaelano` (88, 144), from the staged
Hampel-filtered amplitude with gaps kept as NaN:

- **Envelope.** The envelope `m(t)` is `log1p(1000 ·` mean over present tones
  and receivers of `(Δ ln A)²)`, smoothed by a 0.125 s running median.
- **Floor and burst.** The quiet floor is the 20th percentile of `m` during
  `preparation`. The main burst is the peak of `m` from 0.5 s before to 1 s
  after the action cue.
- **Envelope features.** Eleven features of that burst.
- **Spectral features.** A per-tone Lomb–Scargle spectrum over the burst, at
  least 1 s and at most 2 s. Each tone's spectrum is normalized and the
  results are averaged. It is computed with gaps kept and, for comparison,
  after linear interpolation.

| Feature (AUC, fall positive) | `akmal` | `khaelano` |
| --- | --- | --- |
| Peak prominence above the floor | 0.60 | 0.78 |
| Burst duration above half prominence | 0.64 | 0.72 |
| Post-burst level (1–3 s after) ÷ prominence | 0.31 | 0.41 |
| Posture displacement (per-tone change of mean `ln A`, 1 s before vs after) | 0.63 | 0.63 |
| Receiver agreement (share of receivers peaking within ±0.3 s) | 0.61 | 0.61 |
| Stop ratio (0.5 s after ÷ before the peak) | 0.49 | 0.51 |
| Asymmetry (decay ÷ rise time) | 0.50 | 0.51 |
| Steepest drop after the peak ÷ prominence | 0.61 | 0.68 |
| Lag-1 ÷ lag-8 change energy | 0.61 | 0.37 |
| Spectral, gaps kept: power above 10 Hz / centroid | 0.57 / 0.58 | 0.61 / 0.58 |
| Spectral, gaps kept: entropy 10–30 Hz | 0.54 | 0.49 |

Logistic regression (balanced classes) trained on one session and tested on
the other:

| Feature set | → `akmal` | → `khaelano` | Within (5-fold) `akmal` / `khaelano` |
| --- | --- | --- | --- |
| Envelope (11) | 0.62 | 0.62 | 0.73 / 0.75 |
| Spectral, gaps kept (4) | 0.54 | 0.56 | 0.48 / 0.70 |
| Spectral, interpolated (4) | 0.54 | 0.58 | 0.54 / 0.69 |
| Envelope + spectral, gaps kept (15) | 0.64 | 0.66 | 0.72 / 0.82 |
| Duration + entropies 1–10 and 10–30 Hz (3) | 0.64 | 0.72 | 0.61 / 0.76 |

- **Both directions.** These attempt-level features transferred at 0.62–0.72
  in both directions. The sequence models reached attempt AUC 0.50–0.67, each
  in one direction.
- **No sudden stop.** The stop features did not differ (stop ratio,
  asymmetry), or pointed the other way (steepest drop relative to
  prominence). Instead, falls were larger and longer bursts, followed by a
  relatively deeper quiet. They moved the body further from its earlier
  position and were seen by more receivers at once. All falls landed on a
  mattress, which may soften the end of a fall, so the stop features remain
  untested for hard landings.
- **Spectral features.** They added little. Keeping gaps cost nothing
  compared with interpolation. FallDeFi's 10–30 Hz entropy did not separate
  these bursts.
- **Uncertainty.** With about 230 attempts per session, an AUC has a standard
  error of about 0.035. Differences below about 0.05 between rows are not
  reliable.

## Burst features against FallDeFi

`burst_vs_falldefi.py` scored the burst features and FallDeFi on the same cued
attempts. FallDeFi's attempt score is the SVM decision of its strongest event,
recomputed from the saved 22 November holdout models. FallDeFi's own attempt
rule reproduced its reported scores on these attempts (balanced accuracy
0.679 and 0.714). FallDeFi left 49 of 231 `akmal` and 21 of 232 `khaelano`
attempts unscored.

| Attempt AUC (all cued / FallDeFi-scored) | → `akmal` | → `khaelano` |
| --- | --- | --- |
| FallDeFi SVM | 0.77 / 0.79 | 0.70 / 0.80 |
| Burst, 5 features | 0.63 / 0.64 | 0.63 / 0.64 |
| FallDeFi's 4 features, logistic | 0.77 / 0.86 | 0.68 / 0.69 |
| Burst 5 + FallDeFi 4, logistic | 0.75 / 0.83 | 0.69 / 0.71 |
| Rank fusion of FallDeFi SVM and burst 5 | 0.76 / 0.75 | 0.73 / 0.79 |

On FallDeFi-scored attempts, burst 5 minus FallDeFi was −0.15 [−0.25, −0.05]
and −0.15 [−0.26, −0.04] (95 % bootstrap intervals). Combining the two did not
help reliably (+0.04 [−0.03, +0.11] and −0.09 [−0.15, −0.03]). FallDeFi's own
features carry the fall information; the burst screen's Lomb–Scargle
entropies, computed on one pooled envelope, did not.

## A seconds-long temporal view (phase 1)

The CNNs so far could not see a fall's shape:

- **`TorchCNN`:** each output position saw about 0.06 s (7 samples), and the
  model averaged those positions over the window.
- **`TorchTonePool`:** each position saw about 0.18 s, with the same averaging.

So they were short-texture detectors. Phase 1 adds two `03_training` models
on the default per-tone input, with balanced-log-loss checkpoints:

- **`tonepool_tcn`:** after GeM tone pooling, five residual dilated temporal
  convolutions (dilations 1–16) at a quarter of the sample rate, reaching
  about 2.2 s, with max plus mean over time into the head.
- **`tonepool_tcn_center`:** the same model, with each tone's value minus its
  own mean over the window, as FallDeFi normalizes each trace.

Both models keep tone and receiver order invariance and export to ONNX. The
runs are listed in `temporal_runs.json`.

| Action-cue window AUC, 2 / 4 / 6 s | `akmal` | `khaelano` | `akmal` + cont. | `khaelano`, all cont. |
| --- | --- | --- | --- | --- |
| GeM, step 2 | 0.62 / 0.69 / 0.65 | 0.53 / 0.56 / 0.52 | 0.66 / 0.71 / 0.69 | 0.53 / 0.56 / 0.51 |
| TCN | 0.75 / 0.90 / 0.87 | 0.68 / 0.79 / 0.82 | 0.79 / 0.87 / 0.91 | 0.68 / 0.78 / 0.86 |
| TCN, centred | 0.74 / 0.91 / 0.83 | 0.68 / 0.80 / 0.79 | 0.77 / 0.86 / 0.84 | 0.66 / 0.78 / 0.81 |

| Attempt AUC, 4 / 6 s | `akmal` | `khaelano` | `akmal` + cont. | `khaelano`, all cont. |
| --- | --- | --- | --- | --- |
| GeM, step 2 | 0.60 / 0.58 | 0.58 / 0.51 | 0.63 / 0.63 | 0.58 / 0.51 |
| TCN | 0.84 / 0.82 | 0.79 / 0.84 | 0.81 / 0.88 | 0.77 / 0.87 |
| TCN, centred | 0.85 / 0.76 | 0.82 / 0.82 | 0.82 / 0.78 | 0.78 / 0.83 |
| FallDeFi SVM (all cued attempts) | 0.77 | 0.70 | not computed | not computed |

- **Both directions.** Falls separated from posture transitions at 0.78–0.91
  (4 and 6 s), against 0.51–0.71 before. The direction dependence of every
  earlier input disappeared. The 2 s models gained less, because a 2 s
  window cannot hold a burst and its aftermath.
- **Against FallDeFi** (`temporal_vs_falldefi.py`, attempt AUC difference with
  95 % bootstrap interval). Over all cued attempts:
  - TCN 6 s on `khaelano`: +0.14 [+0.05, +0.22];
  - centred TCN 4 s: +0.09 [+0.00, +0.17] on `akmal` and +0.12
    [+0.02, +0.21] on `khaelano`.

  On FallDeFi-scored attempts only, the differences were +0.02 to +0.06 with
  intervals including zero. The temporal models rank attempts at least as
  well as FallDeFi, and they also score the attempts FallDeFi drops.
- **Centring.** It did not change the result consistently.
- **Idle data.** The models flagged 0.3–2.2 % of the unseen day's continuous
  windows (2 s: about 2 %).
- **Decisions.** With the threshold chosen on validation (`k` = 1), TCN 6 s
  reached attempt balanced accuracy 0.77, 0.65, 0.79 and 0.77, against
  FallDeFi's 0.68, 0.71, 0.73 and 0.69. In the `khaelano` holdout the chosen
  threshold was too strict (recall 0.33, false-positive rate 0.03).
  Calibration across sessions remains open.
- **Limits.**
  - One seed and two participants.
  - The 4–6 s windows of a fall reach into the lying phase after it, and
    every fall ended on the mattress. The model may use "lying on the
    mattress" as well as the fall itself. Posture after a fall is a real
    signature, but here it cannot be separated from the setup.
  - Non-fall recordings with the mattress in place are needed to tell the
    two apart.

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

1. Repeat `tonepool_tcn` over several seeds (3–5) on the four holdouts
   before building on it.
2. Phase 2–4 of the model plan: per-receiver PCA within the window (gaps
   kept), a frequency view of those components, and positive labels from
   the detected main burst.
3. Calibrate the decision threshold across sessions.
3. For live use, register the `tonepool` families in the Rust detector. The
   quiet-floor variant would also need a still-room calibration step.
4. Record non-fall activity with the mattress in place, and if it can be done
   safely, some falls onto a harder surface.

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
and one default `03_training` run plus one `06_comparison` per holdout). The
step-2 runs (loss checkpoints, validation predictions, decision-rule table)
are listed in `decision_rule_runs.json`.

`diagnostics/20261123-tone-pooling/` holds the screen scripts and results
(`level_screen*.py`, `screen_results.txt`, `stft_screen*`, `gap_screen*`), the
holdout runners (`tone_mean_holdouts.py` with `runs.json`,
`tonepool_holdouts.py` with `tonepool_runs.json`, `floor_gem_holdouts.py` with
`floor_gem_runs.json`, `decision_rule_holdouts.py` with
`decision_rule_runs.json`, `hard_negative_holdouts.py` with
`hard_negative_runs.json`, `temporal_holdouts.py` with
`temporal_runs.json`), the FallDeFi comparisons (`burst_vs_falldefi.py`,
`temporal_vs_falldefi.py`, `temporal_attempts.py` and their CSVs), the burst screen (`burst_screen.py`,
`burst_features.csv`, `burst_feature_auc.csv`, `burst_model_auc.csv`,
`burst_screen_results.txt`), the idle diagnosis (`idle_diagnosis.py`,
`idle_diagnosis.json`), `attempt_span.py` with `attempt_span.csv`, and
`window_auc.py` with `window_auc.csv` (window and action-cue window AUC and
idle flags for every model). The export is
`data/processed/amplitude_sequence/120hz-tone_mean_log_ratio/` (not
DVC-tracked; regenerate with `02_preprocess`).
