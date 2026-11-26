# Principal-component spectrum, 26 November 2026

This report follows the [energy-inputs report](energy-inputs-2026-11-26.md). Its
untrained screens found that the amplitude's 30–60 Hz fluctuations separate falls
from posture transitions best, while a trained model that sees only overall motion
energy (`tiny_tcn1`) matched `tonepool_tcn`. Here each receiver's tones are
collapsed per window into their five leading principal components before a
short-time Fourier transform (STFT), and the power spectrum summed over the
components is the model's input. A GRU on that input (`pcspec_gru`) reached a mean
attempt AUC of 0.903 over four holdouts, against 0.836 for `tonepool_tcn` and 0.846
for `tiny_tcn1`, and ranked attempts better than `tonepool_tcn` in 15 of 16 paired
runs. The same input read by `tonepool_tcn`'s temporal convolutions (`pctcn`)
reached 0.886, so most of the lead comes from the input and the GRU adds a smaller
part. Taking the STFT of the distance moved in component space instead lost most
of the gain (0.654). Nothing here is deployed; the report ends with a plan for the
live detector.

## Conditions

- Sessions `khaelano` (`20261104T081805521126Z`), `akmal`
  (`20261109T131546367822Z`) and `continuous_non_fall`
  (`20261109T161519702956Z`), as in the energy-inputs report.
- Code: the working tree on top of `71e505b`. No source file and no notebook
  changed. The model classes live in the training harnesses (`MODEL_CODE` in
  `pcspec_holdouts.py`, `pcdist_holdouts.py` and `pctcn_holdouts.py`), which run
  in-memory copies of `03_training` with the other models' training cells
  disabled.
- Trained models read the signed difference export
  (`amplitude_sequence/120hz-signed_difference/`, written by
  `20261125-signed-difference/export_signed.py`), standardized per tone by the
  training normalizer. Training uses the burst-label `tonepool_tcn` configuration:
  4 s windows, seeds 42–45, the four session holdouts, checkpoint by validation
  balanced log loss. Settings were fixed before training, not tuned. The ONNX
  export was skipped because `torch.linalg.eigh` has no ONNX operator.
- Calibrated rates use ten random non-fall attempts and a 0.2 target, with the
  same draws for every model (`20261126-tiny-tcn/compare_tiny.py`'s rule). Paired
  intervals resample test attempts and compare mean attempt AUC over the four
  seeds.
- Untrained screens use the STFT and score of `01_03_amplitude_spectral`: the 90th
  percentile of the band's change over the frames before the action cue, from
  0.5 s before to 1 s after the cue, averaged over receivers. Attempts with a
  detected main burst: 88 falls and 144 transitions (`khaelano`), 87 and 144
  (`akmal`). Unless stated, the screens fit components on the whole attempt
  (offline, non-causal); bands were chosen in the earlier report.
- Every number comes from two participant sessions in one room, with every fall
  recorded after every non-fall, mattress in place.

## Collapsing tones before the STFT

`20261126-pc-spectrum/`: `tone_pca_screen.py`, `tone_pca_followup.py`,
`pc1_edge_tone.py`.

Per receiver, each tone's amplitude is divided by its median over the attempt,
differenced from sample to sample, and projected on principal axes fitted on the
complete rows of the tones present on at least 90 % of received rows. Power is
summed over the components, so their arbitrary signs and order, and any rotation
within the subspace, do not matter. The reference is the per-tone STFT averaged
in dB over the 241 reported tones (the `01_03` rule).

Falls against transitions, attempt AUC (`khaelano` / `akmal`):

| Series per receiver | 30–45 Hz | 45–60 Hz | 2–60 Hz |
| --- | --- | --- | --- |
| Every tone, dB averaged (reference) | 0.83 / 0.80 | 0.78 / 0.80 | 0.74 / 0.71 |
| Tone mean | 0.68 / 0.53 | 0.61 / 0.55 | 0.79 / 0.52 |
| PC1 | 0.48 / 0.54 | 0.53 / 0.48 | 0.48 / 0.55 |
| PC1–3 | 0.69 / 0.67 | 0.62 / 0.59 | 0.74 / 0.65 |
| PC1–6 | 0.74 / 0.71 | 0.65 / 0.63 | 0.78 / 0.67 |
| PC2–3 | 0.74 / 0.73 | 0.71 / 0.73 | 0.71 / 0.68 |
| PC2–6 | 0.82 / 0.79 | 0.80 / 0.81 | 0.76 / 0.72 |
| PC2–11 | 0.82 / 0.80 | 0.81 / 0.81 | 0.77 / 0.72 |
| PC2–6 fitted on 4 s (cue −1 s to +3 s) | 0.81 / 0.83 | 0.78 / 0.86 | 0.72 / 0.76 |

- **PC1 is one unstable edge tone.** In 924 of 924 attempt-receivers (`akmal`)
  and 927 of 928 (`khaelano`), PC1 was tone index 243 (physical +121) alone
  (weight 1.00), with a median 62–63 % of the change variance. Its amplitude is
  not small (about twice the median tone's) but spans a factor of about 21
  between its 1st and 99th percentiles, against 1.3 for interior index 100, and
  its relative change has 22–23 times the median interior tone's spread. The
  FallDeFi and WiFall adaptations read only physical tones −120 to −2 and 2 to
  120 and are unaffected. The trained models below use the same 238 interior
  tones.
- **Five components keep the per-tone separation.** PC2–6 against the reference:
  −0.010 [−0.027, 0.008] (`khaelano`) and −0.012 [−0.025, 0.002] (`akmal`) at
  30–45 Hz, +0.020 [0.000, 0.043] and +0.010 [−0.005, 0.029] over 2–60 Hz. Two
  components lost 0.07–0.09 at 30–45 Hz; ten added nothing over five.
- **Averaging tones first loses the motion.** The tone mean lost 0.15 and 0.27
  at 30–45 Hz; tones move in different directions and cancel, as in WiFall's gate.
- **A per-window fit holds.** Fitted on the 4 s around the cue, PC2–6 changed by
  −0.017 [−0.051, 0.015] and +0.031 [0.005, 0.057] at 30–45 Hz, so the components
  need not come from the whole attempt.

## Models on the principal-component spectrum

`20261126-pc-spectrum/`: `pcspec_holdouts.py`, `pctcn_holdouts.py`,
`compare_pc_models.py`, `quiet_windows.py`.

Inside each model, without gradient: per receiver, the 238 interior tones of the
normalized signed difference; samples with at least 90 % of them valid are usable.
The covariance of the window's usable samples gives five leading axes. The scores
pass through a masked STFT (the inner 64 samples of a 66-point Hann window, hop 8,
weighted mean and slope removed, missing samples at weight zero, power divided by
the summed squared weights). Power is summed over the components and kept in 32
bins from 1.9 to 60 Hz as log power. A frame counts where at least 60 % of its
samples are usable. Mean and maximum over the usable receivers plus their coverage
give 53 frames × 65 features per 4 s window, batch-normalized. Receivers are
dropped at random (0.25) in training.

- `pcspec_gru`: GRU (hidden 64); its last output and its maximum over time feed a
  linear head. 25,411 parameters.
- `pcspec_lstm`: the same with an LSTM. 33,795 parameters.
- `energy_gru`: the same frames, pooling and network on one feature per frame,
  the log mean squared change over interior tones. 13,383 parameters. It asks
  whether the spectrum adds anything over energy.
- `pctcn`: the GRU replaced by `tonepool_tcn`'s temporal stage, an input
  convolution (kernel 3, 64 channels), residual convolutions with dilations 1, 2,
  4 and 8, and maximum plus mean over time into the head. At 15 frames per second
  it reaches about 2.7 s of signal including the 0.53 s STFT window, against
  `tonepool_tcn`'s 2.2 s; dilation 16 would exceed the 53-frame window. 62,211
  parameters. It separates the input's effect from the recurrent network's.

Attempt AUC, mean over four seeds (calibrated recall below each):

| Test | `tonepool_tcn` | `tiny_tcn1` | `pcspec_gru` | `pctcn` | `pcspec_lstm` | `energy_gru` |
| --- | --- | --- | --- | --- | --- | --- |
| `akmal` | 0.85 | 0.86 | 0.93 | 0.88 | 0.65 | 0.69 |
| | 0.73 | 0.76 | 0.90 | 0.78 | 0.43 | 0.42 |
| `akmal` + continuous | 0.81 | 0.87 | 0.86 | 0.92 | 0.94 | 0.67 |
| | 0.62 | 0.76 | 0.77 | 0.92 | 0.93 | 0.40 |
| `khaelano` | 0.84 | 0.82 | 0.91 | 0.87 | 0.87 | 0.73 |
| | 0.68 | 0.67 | 0.84 | 0.78 | 0.74 | 0.52 |
| `khaelano`, all continuous in training | 0.84 | 0.83 | 0.91 | 0.87 | 0.88 | 0.70 |
| | 0.69 | 0.69 | 0.82 | 0.78 | 0.77 | 0.50 |
| Mean attempt AUC | 0.836 | 0.846 | 0.903 | 0.886 | 0.834 | 0.701 |

Calibrated false-positive rates were 0.21–0.26 for every model.

Paired bootstrap over attempts, difference of mean attempt AUC over seeds (seeds in
which the first model was higher):

| Test | `pcspec_gru` − `tonepool_tcn` | `pcspec_gru` − `tiny_tcn1` | `pctcn` − `tonepool_tcn` | `pctcn` − `pcspec_gru` | `pcspec_gru` − `energy_gru` |
| --- | --- | --- | --- | --- | --- |
| `akmal` | +0.08 [0.04, 0.12] (4) | +0.06 [0.02, 0.11] (3) | +0.03 [−0.02, 0.07] (3) | −0.05 [−0.09, −0.02] (0) | +0.23 [0.19, 0.28] (4) |
| `akmal` + continuous | +0.05 [0.01, 0.10] (3) | 0.00 [−0.05, 0.05] (3) | +0.12 [0.08, 0.16] (4) | +0.06 [0.02, 0.10] (2) | +0.19 [0.14, 0.25] (4) |
| `khaelano` | +0.07 [0.04, 0.12] (4) | +0.09 [0.05, 0.14] (4) | +0.03 [−0.02, 0.09] (3) | −0.04 [−0.07, −0.01] (1) | +0.18 [0.14, 0.23] (4) |
| `khaelano`, all continuous | +0.07 [0.02, 0.11] (4) | +0.08 [0.03, 0.12] (4) | +0.03 [−0.02, 0.08] (4) | −0.04 [−0.06, −0.01] (0) | +0.20 [0.16, 0.25] (4) |

- **`pcspec_gru` ranks attempts best.** Its intervals against `tonepool_tcn` exclude
  zero in all four tests, and against `tiny_tcn1` in three; it was higher in 15 and
  14 of 16 seeds. On action-cue windows (falls against posture transitions) it
  reached 0.86–0.89 testing on `akmal` and 0.83 on `khaelano`, against 0.81–0.86
  and 0.76–0.78 for `tonepool_tcn`. At most 2.4 % of the unseen continuous
  windows were flagged at 0.5 (one seed; the others at most 0.2 %).
- **One GRU seed failed.** On `akmal` + continuous, seed 45 reached 0.684 (the
  others 0.905–0.959); its validation loss, 0.336, was the highest of the 16 runs.
  This seed alone makes the GRU's mean there equal `tiny_tcn1`'s.
- **The input carries most of the lead.** `pctcn` exceeded `tonepool_tcn` in 14 of
  16 seeds and `tiny_tcn1` in 13, by +0.025 to +0.115 against `tonepool_tcn`; only
  the `akmal` + continuous interval excludes zero. Over the four tests,
  `tonepool_tcn` → `pctcn` → `pcspec_gru` went 0.836 → 0.886 → 0.903, so about
  three quarters of the GRU's lead remains with the convolutional network. The
  `tonepool_tcn` comparison also changes the front end (no per-tone encoder), so
  this split is approximate.
- **The GRU adds a smaller, consistent part.** It beat `pctcn` in 13 of 16 seeds
  and by 0.04–0.05 in three tests. `pctcn` won on `akmal` + continuous only
  because of the failed GRU seed. Testing on `khaelano`, `pctcn`'s action-cue AUC
  (0.76–0.78) did not exceed `tonepool_tcn`'s, while its attempt AUC did. In the
  plain `khaelano` test its two lowest seeds (0.80 and 0.86) trained longest
  (25–29 epochs) to validation losses of 0.001–0.002 on the training participant.
  That suggests overfitting to `akmal`, but the pattern did not repeat in the
  other `khaelano` test.
- **The spectrum, not the frames, makes the difference.** `energy_gru`, on the
  same frames with only their energy, stayed at 0.70 and lost 0.09–0.19 to
  `tiny_tcn1`, which reads energy at 120 Hz. `pcspec_gru` beat it in all 16 seeds.
- **The LSTM was unstable.** On `akmal`, two seeds never improved on their first
  epoch's checkpoint and stopped at epoch 6 (attempt AUC SD 0.26); on `akmal` +
  continuous it was the best model (0.94).
- **No setup signature in still windows.** Scoring held-out attempts' first 4 s
  (wholly preparation; 30 falls and 64 non-falls on `akmal`, 35 and 50 on
  `khaelano`) and last 4 s (wholly resting; 81 and 137, 83 and 140), falls against
  non-falls gave mean AUCs of 0.48 and 0.49 (lead-in) and 0.50 and 0.44 (tail) for
  `pcspec_gru`. For `pctcn` the corresponding figures were 0.51 and 0.46, and 0.40
  and 0.37. Below 0.5, the still windows of falls scored lower. Of the four models
  checked, only `tonepool_tcn`'s lead-ins on `khaelano` leaned toward falls
  (0.60). On `akmal`, 14 % of fall and 9 % of non-fall lead-ins were flagged at
  0.5 by `pcspec_gru` (5 % and 4 % by `pctcn`, 20 % and 10 % by `tonepool_tcn`).

## Distances in component space

`20261126-pc-spectrum/`: `pc_distance_screen.py`, `pcdist_holdouts.py`.

The five scores form a vector that moves through component space. Instead of the
spectrum of each component, these inputs take the spectrum of a distance:

- `step_distance`: the length of the per-sample step |P(a(t) − a(t − 1))|, where
  P projects on the axes fitted on the change;
- `step4_distance`: the same over four samples;
- `displacement`: the distance from the attempt's mean state.

The screen fits the axes on the attempt's change, interior tones only.

Untrained screen, attempt AUC (`khaelano` / `akmal`):

| Series per receiver | 2–10 Hz | 30–45 Hz | 45–60 Hz | 2–60 Hz |
| --- | --- | --- | --- | --- |
| Every tone, dB averaged (reference) | 0.61 / 0.47 | 0.83 / 0.80 | 0.78 / 0.80 | 0.74 / 0.71 |
| Five components, power summed (`pcspec_gru`'s input) | 0.68 / 0.47 | 0.82 / 0.79 | 0.81 / 0.81 | 0.77 / 0.72 |
| `step_distance` | 0.75 / 0.68 | 0.76 / 0.71 | 0.77 / 0.71 | 0.77 / 0.73 |
| `step4_distance` | 0.62 / 0.53 | 0.71 / 0.70 | 0.78 / 0.76 | 0.71 / 0.68 |
| `displacement` | 0.55 / 0.39 | 0.71 / 0.77 | 0.70 / 0.78 | 0.65 / 0.68 |

`pcdist_gru` is `pcspec_gru` with one change before the STFT: the five component
series become one, the step length. Attempt AUC, mean over four seeds:

| Test | `pcdist_gru` | Action-cue window AUC | Calibrated recall | Unseen continuous windows flagged, per seed |
| --- | --- | --- | --- | --- |
| `akmal` | 0.65 | 0.71 | 0.32 | 2.4–11.1 % |
| `akmal` + continuous | 0.67 | 0.73 | 0.39 | 6.6–13.4 % |
| `khaelano` | 0.65 | 0.69 | 0.37 | at most 1.0 % |
| `khaelano`, all continuous in training | 0.65 | 0.68 | 0.36 | none in the test |

- **The step length's spectrum is flat.** Its AUC stayed at 0.74–0.77 (`khaelano`)
  and 0.68–0.73 (`akmal`) in all six screened bands. Against the reference it lost
  0.07 [0.04, 0.10] and 0.09 [0.06, 0.13] at 30–45 Hz and gained only below
  20 Hz, where the reference is weakest. Over 2–60 Hz it matched the summed
  component power. The other two distances were worse in most bands.
- **Trained, it lost most of the gain.** Against `pcspec_gru`: −0.28, −0.20,
  −0.26 and −0.26 (all intervals exclude zero), lower in 16 of 16 seeds. Against
  `energy_gru`, from −0.006 to −0.079, with intervals excluding zero in both
  `khaelano` tests. Its seeds agreed (attempt AUC 0.60–0.68). Training stopped
  after 6–16 epochs at validation losses of 0.30–0.59, against 0.005–0.34 for
  `pcspec_gru`. Longer training was not tried.
- **Why, probably.** A distance is a norm and rectifies the series: a fluctuation
  at frequency *f* appears at 2*f*, components above 30 Hz fold back below 60 Hz,
  and the result approaches an energy envelope, like the squared difference in
  the energy-inputs report. Summing the components' power after the STFT keeps
  each fluctuation's own frequency. The mechanism fits the flat screen but was
  not tested separately.

## Cost and numerical precision

`20261126-pc-spectrum/`: `bench_pca.py`, `live_cost.py`, `feature_precision.py`.

- **Work per window.** Each receiver needs one 238 × 238 covariance, five
  eigenvectors and five STFTs, instead of 241 per-tone STFTs.
- **Training on the GPU.** A batched `torch.linalg.eigh` of 128 matrices of
  237 × 237 took 17.1 ms on the RTX 4070 SUPER. Subspace iteration (12 steps,
  block 8) was slower (26.0 ms) and did not converge to the same subspace on that
  test data. Including notebook start and data loading, one `pctcn` run took
  about 1.2 minutes, and one run training the three `pcspec` models about
  1.9 minutes.
- **Live on one CPU core** (i7-14700F, NumPy 2.5.2 with LAPACK, float64, one
  thread). One hop scores one window of four receivers:

  | Step | Time |
  | --- | --- |
  | Four covariances of 480 samples × 238 tones | 3.41 ms |
  | Their five leading eigenvectors (subset solver) | 4.31 ms |
  | Same, all eigenvectors | 10.31 ms |
  | Projections | 0.21 ms |
  | STFT power of 4 × 53 frames × 5 components | 0.17 ms |

  About 8 ms per 250 ms hop, before the ONNX head (25,411 or 62,211 parameters on
  53 frames). The AMD laptop was not measured.
- **Precision.** For `pcspec_gru` (seed 45, tests `akmal` and `khaelano`, 512
  random test windows each), features were computed twice: in float32 on the GPU,
  as in training, and in float64 on the CPU, as a Rust implementation would.
  Both passed through the same head. Per window, the largest log-power change
  had a median of 8e-6 and a maximum of 2.6e-4. Logits changed by at most
  1.3e-4 and probabilities by at most 1.2e-5. The usable frames were identical.
  The fifth and sixth eigenvalues are close (median ratio 1.07–1.08, 1st
  percentile 1.007–1.009), but a float32-sized perturbation is far smaller than that gap, so the
  five-component subspace did not move.

## Plan for the live detector (proposal, not implemented)

The live detector feeds every model `[1, time, 1964]`: the Hampel-filtered
amplitude's squared difference after `log1p`, normalized, with validity and
presence flags (`radio_detection::window::prepare`, then
`Normalizer::assemble`). The PC-spectrum models need a different signal and a
front end that ONNX cannot express. The plan is to split them at the frame
features: Rust computes the 53 × 65 features, and ONNX runs only the head
(batch normalization, the temporal network and the linear layer).

1. **Choose and train the deployed model.** The GRU head is the first choice: it
   beat `pctcn` in 13 of 16 seeds. One of its seeds failed, though, so the
   deployed seed's held-out score should be checked before it is published. The
   TCN head is the fallback. It would reuse the convolution path that
   `tiny_tcn1` already runs on WebGPU, and it avoids a recurrent operator whose
   speed on the AMD laptop is unmeasured for this input (53 steps of 65 features,
   not 480 of 1964). Train it on the full-data split with the protocol used
   for `tiny_tcn1-4s` (`20261126-tiny-tcn/full_split_runs.py`). Add an export
   path to `03_training` for models with a non-ONNX front end. It should export
   the head with input `[batch, 53, 65]` and check ONNX Runtime logits against
   PyTorch at batch sizes 1 and 2. It should also write the front end's constants
   to the manifest and save a small parity fixture: a few test windows' assembled
   inputs, with the PyTorch features and logits.
2. **Emit the signed difference.** `window::prepare` already forms the float64
   difference before squaring. Add a second output, the difference cast to
   float32, which is exactly how `export_signed.py` built the training input.
   Each export declares its `representation` in the manifest, and existing
   bundles default to the squared difference. Only the representations that the
   resident models need are computed. The model's own normalizer and
   `Normalizer::assemble` stay unchanged.
3. **Rust front end** (a new `radio_detection` module, or a kernel in
   `radio_signal`), mirroring `PCSpectrum.frame_features` in evaluation mode:
   - interior tone indices 2–120 and 124–242, and usable samples (at least 90 %
     of those tones valid);
   - weighted centring and a float64 covariance per receiver, and its five leading
     eigenvectors;
   - projection, then the masked STFT: inner 64 samples of a 66-point Hann
     window, hop 8, weighted mean and slope removed, 64-point real DFT, bins 1–32,
     power divided by the summed squared weights and summed over the components,
     log(power + 1e-6);
   - frames usable at 60 %, then mean, maximum and coverage over usable receivers.

   For the eigenvectors, use `faer` (pure Rust, self-adjoint eigendecomposition)
   or `nalgebra`, not a LAPACK binding, which would add a system library to the
   wheel. Only the subspace matters, so differences in sign and order between
   solvers have no effect.
4. **Generalize the model contract.** Today the 1964 width is fixed in several
   places:
   - `bundle::inspect_exports` (`input_shape`);
   - `Prepared::into_job`;
   - `Runtime::infer_view`;
   - the warm-up inputs in `backend::load_models`.

   Each should take the shape from the export. The manifest gains a `features`
   block (kind `pc_spectrum`, version, components, window, hop, bins, minimum tone
   and frame shares, interior ranges, log floor), validated as strictly as
   `Preprocessing`. In `backend.rs` the front end runs on the coordinator thread
   after `assemble`. Its time counts as preprocessing, and its deduplication key
   adds the representation and feature kind. Register the family in
   `bundle::FAMILIES`: main operator `Conv` for a TCN head, `GRU` for a GRU head.
   The WebGPU placement audit then applies as before.
5. **Python and logs.** Add the model to the detector's choices in
   `apps/detector/gui.py`, as for `tiny_tcn1` in `9278fb5`. The GUI preview
   reshapes inputs to `[frames, 1964]`, so it keeps showing the assembled input.
   The input log records both the assembled input and the features, so replays
   can be checked at each stage. Threshold calibration is per model and needs no
   change.

Acceptance checks:

- **Signed input:** bit-for-bit equal to the offline chain on the replay capture,
  as for the current input.
- **Front end, unit tests:**
  - a sinusoid at a bin centre peaks in that bin;
  - the 12-in-68 gap pattern gives the Python reference's masked power;
  - flipping or rotating the axes changes nothing;
  - a missing receiver changes only the coverage.
- **Features and logits:** within a tolerance of PyTorch on the parity fixture, an
  ignored test that needs the DVC artifacts. On 1,024 test windows, float64
  features on the CPU moved `pcspec_gru` logits by at most 1.3e-4 from float32 on
  the GPU, so a logit tolerance of 1e-3 leaves margin. Bit-for-bit parity is not
  achievable across eigensolvers.
- **Real detector:** replay the recorded sessions through it, as on 25 November.
  Scores should reproduce the offline ones; record the time per hop on the
  i7-14700F and on the AMD laptop.

Cost: the front end took about 8 ms per hop on one i7-14700F core with LAPACK; a
Rust solver may differ. If the laptop needs less, the covariance can be kept as
sliding sums of the weights, the samples and their products. Each 250 ms hop adds
and removes 30 of the 480 samples, so it needs about an eighth of the work, with
an occasional exact recompute. Subspace iteration is not a good shortcut: the
fifth and sixth eigenvalues are close, so it converges slowly.

Not decided: whether to deploy at all. The gain is measured on the same two
participants and the same fall-after-non-fall recording order as every other
model, so `tonepool_tcn` would stay the default until a new participant's session
confirms the result, as for `tiny_tcn1`.

## Interpretation and limits

- The principal-component spectrum keeps the fast fluctuations that separate
  falls from transitions (30–60 Hz in the screens) and pools tones without
  learning which tone or receiver responded: the components are fitted afresh
  for every window. Trained, it ranked attempts better than `tonepool_tcn` and
  `tiny_tcn1` in both training directions. Most of that survives with a
  convolutional head, so the input is the main cause; the GRU adds about a
  quarter of the lead over `tonepool_tcn`.
- In the energy-inputs report, inputs with per-tone or per-frequency detail
  (signed difference, multi-lag) moved performance from one training direction
  to the other rather than raising it. Here the signed difference, read through
  per-window components, gained in both. A possible reason is that the
  components carry no fixed tone identity or level that could differ between
  sessions. This was not tested.
- Distances in component space rectify the signal and lose the frequency
  structure; the power summed over components after the STFT should be kept.
- Limits:
  - two participants and one room;
  - falls only after non-falls, with the mattress in place; still windows
    showed no setup signature for these models, but fall windows still contain
    the landing on the mattress;
  - the input was designed after the energy-inputs screens on the same sessions,
    and the screens here choose five components on them; training settings were
    fixed, not tuned;
  - validation comes from the training participant, so it cannot detect
    overfitting to that participant (see `pctcn` on `khaelano`);
  - paired intervals cover the tested attempts, not training randomness;
  - whether the input makes thresholds portable between participants was not
    tested, so the installation calibration stays necessary.

## Next steps

1. Not run: collect sessions from more participants, with non-falls on the
   mattress and interleaved trial order. Deploying the PC spectrum depends on a
   new participant confirming the gain, as for `tiny_tcn1`.
2. Not run: train a TCN that reaches the whole window, to tell whether the GRU's
   advantage over `pctcn` comes from recurrence or from its longer reach (the
   whole 4 s window against about 2.7 s).
3. Not run: move the model classes from the harnesses into `03_training`, with
   the export path described in the plan; this is the first step of the live
   implementation.

## Runs and files

Diagnostics under `artifacts/notebooks/diagnostics/20261126-pc-spectrum/`; training
runs under `artifacts/notebooks/03_training/`.

| Experiment | Files or runs |
| --- | --- |
| Tone collapse screen | `tone_pca_screen.py`, `tone_pca_followup.py`, `pc1_edge_tone.py` and their `*_results.txt` |
| `pcspec_gru`, `pcspec_lstm`, `energy_gru` | `pcspec_holdouts.py`; 16 runs `20261126T015943831550Z` to `20261126T022824063748Z` (`pcspec_runs.json`, three models per run) |
| `pctcn` | `pctcn_holdouts.py`; 16 runs `20261126T051810685687Z` to `20261126T053526326269Z` (`pctcn_runs.json`) |
| Distance screen and `pcdist_gru` | `pc_distance_screen.py`, `pc_distance_results.txt`, `pcdist_holdouts.py`; 16 runs `20261126T031239221975Z` to `20261126T032800597537Z` (`pcdist_runs.json`) |
| Comparison of trained models | `compare_pc_models.py`, `compare_pc_models_results.txt`, `compare_pc_models*.csv` |
| Quiet windows | `quiet_windows.py`, `quiet_windows_results.txt`, `quiet_windows.csv` |
| Cost and precision | `bench_pca.py`, `live_cost.py`, `feature_precision.py` and their `*_results.txt`, `feature_precision.csv` |
| Baseline `tonepool_tcn` and `tiny_tcn1` runs | `20261123-tone-pooling/burst_seed_runs.json`, `20261126-tiny-tcn/tiny_runs.json` |
