# Evaluation of `pcspec_gru`, 26 November 2026

`pcspec_gru` reads each receiver's 238 interior tones of the signed difference,
projects them per 4 s window on their five leading principal components, and
feeds the masked STFT power summed over the components to a GRU. The
[principal-component spectrum report](pc-spectrum-2026-11-26.md) defines it and
compares it with other inputs. This report evaluates the model itself:

- how it ranks and classifies attempts in each held-out session;
- which activities it confuses;
- how it compares with FallDeFi on the same attempts;
- how it would behave under the live detector's conditions, emulated offline:
  250 ms hop, coverage gate, ten-movement calibration, alarm delay and idle
  alarms.

In short, on the two participant sessions:

- **Ranking.** It ranks falls above posture transitions with a mean attempt AUC
  of 0.90; 15 of 16 runs reached at least 0.88.
- **Against FallDeFi.** On the same attempts it beats FallDeFi by 0.11–0.21,
  with every interval excluding zero.
- **Emulated live conditions.** With ten random calibration movements it holds
  the false-positive rate at 0.20–0.21 and catches 73–90 % of falls, against
  65–73 % for `tonepool_tcn`. Calibrated on a session's first ten movements, it
  keeps 63–72 % recall, against 33–55 %.
- **Weaknesses.** It raises more alarm episodes on the unseen idle hour (about 4
  against 2 per scored hour). Its threshold differs most between the two people
  (median 0.91 against 0.16). Walking transitions cause most of its false
  alarms. One of the 16 runs failed.
- **Cost.** The PCA and STFT front end is almost the whole cost. In PyTorch it
  takes 5–15 ms per window on the CPU. A Rust implementation with identical
  results (logits within 9e-6) takes 2.2 ms on one core and 0.86 ms on four,
  against 5.1 ms for `tonepool_tcn` and 0.33 ms for `tiny_tcn1`. Unlike those,
  the front end cannot run on the GPU through ONNX.
- **Scope.** The live behaviour here is an offline emulation. The live detector
  now runs the model, and on a short capture it reproduced the offline features
  and logits ([live PC-spectrum report](live-pcspec-2026-11-26.md)). The
  participant sessions have not been replayed through it, and no third
  participant has been recorded.

## Conditions

- **Model and runs.** `pcspec_gru` as trained on 26 November: 16 runs, seeds
  42–45 × four session holdouts (`pcspec_runs.json` in
  `20261126-pc-spectrum/`), the burst-label `tonepool_tcn` training settings,
  4 s windows, untuned. No new training was done for this report.
- **Test sessions.**
  - `akmal`: 87 falls and 144 posture transitions; trained on `khaelano`.
  - `khaelano`: 88 falls and 144 transitions; trained on `akmal`.
  - Each is tested twice. Once with the continuous non-fall hour wholly in the
    test (`akmal` + continuous) or wholly in training (`khaelano`, all
    continuous in training); once with that hour divided across training,
    validation and test by its own split.
- **Attempts.** Every non-fall attempt is a posture transition (sit, stand and
  walk in six combinations); falls start from sitting, standing or walking. All
  were recorded in one room, every fall after every non-fall, with the mattress
  in place.
- **Offline scores** are the runs' saved test predictions: windows every 2 s,
  falls only on windows centred in the action cue, attempt score = highest
  window.
- **Live emulation.** `live_eval.py` rescores every cued test attempt at the
  detector's 250 ms hop in exact float32. A window counts only if every receiver
  covers at least 70 % of it. Calibration uses the detector's own `Recorder` and
  `install_threshold`. This repeats `20261124-live-calibration/live_calibration.py`
  for `tonepool_tcn` (whose 24 November window scores it reuses) and adds
  `tiny_tcn1`. The PC-spectrum front end is not in the live detector, so these
  are offline estimates of live behaviour, not measurements of the detector.
- **Training precision.** Training ran cuDNN's GRU with TF32 tensor cores
  (PyTorch's default). The saved predictions therefore differ from exact float32,
  which agreed with float64 to about 3e-6: 2.1 % of the 24,048 saved test
  probabilities by more than 1e-4, 0.09 % by more than 1e-3, the largest by
  0.012. The features are unaffected. The live emulation is exact float32, as a
  deployed ONNX head would be. Recomputed from the exact scores, no run's attempt
  AUC changed by more than 8e-5.

## Offline results (published protocol)

`20261126-pcspec-evaluation/offline_summary.py`; calibrated rates use ten random
non-fall attempts and a 0.2 target, 200 sets (`compare_pc_models.py`'s rule).

| Test | Attempt AUC (seeds) | Action-cue window AUC | Calibrated FPR / recall | Balanced accuracy |
| --- | --- | --- | --- | --- |
| `akmal` | 0.93 (0.88–0.95) | 0.89 | 0.26 / 0.90 | 0.82 |
| `akmal` + continuous | 0.86 (0.68–0.96) | 0.86 | 0.25 / 0.77 | 0.76 |
| `khaelano` | 0.91 (0.90–0.94) | 0.83 | 0.22 / 0.84 | 0.81 |
| `khaelano`, all continuous in training | 0.91 (0.90–0.92) | 0.83 | 0.22 / 0.82 | 0.80 |

- **Falls against transitions.** Over 16 runs, the attempt AUC was at least 0.88
  in 15. The exception, seed 45 on `akmal` + continuous (0.684), stopped after
  11 epochs with the highest validation loss of the 16 runs (0.336, against
  0.005–0.27). Without it, `akmal` + continuous averages 0.92.
- **Against the other models,** on the same attempts: mean attempt AUC 0.903
  against 0.836 for `tonepool_tcn` and 0.846 for `tiny_tcn1`, higher than
  `tonepool_tcn` in 15 of 16 paired runs (see the pc-spectrum report for the
  intervals).
- **Ranking at fixed false-positive rates.** Choosing each run's threshold with
  the test labels, which a deployment cannot do, gives the recall the ranking
  allows (means over seeds):

  | Test | Recall at FPR 0.05 | 0.1 | 0.2 |
  | --- | --- | --- | --- |
  | `akmal` | 0.55 | 0.71 | 0.93 |
  | `akmal` + continuous | 0.44 | 0.60 | 0.76 |
  | `khaelano` | 0.65 | 0.76 | 0.86 |
  | `khaelano`, all continuous in training | 0.65 | 0.73 | 0.83 |

  Even with this hindsight, a false-positive rate of 0.05 misses 35–56 % of the
  falls.

## Against FallDeFi on the same attempts

`falldefi_compare.py`. FallDeFi is the 22 November holdout runs, each attempt
scored by the SVM decision of its strongest power-burst event. It scored 182 of
231 `akmal` and 211 of 232 `khaelano` attempts; the rest have no trace. "All"
counts unscored attempts as no alarm; "common" keeps only FallDeFi's. Model AUCs
are means over seeds 42–45 of the plain holdouts.

| Test | Attempts | `pcspec_gru` | FallDeFi | Difference [95 % interval] | Seeds above FallDeFi |
| --- | --- | --- | --- | --- | --- |
| `akmal` | all (87 / 144) | 0.93 | 0.77 | +0.16 [0.09, 0.23] | 4 of 4 |
| `akmal` | common (77 / 105) | 0.92 | 0.79 | +0.13 [0.07, 0.20] | 4 of 4 |
| `khaelano` | all (88 / 144) | 0.91 | 0.70 | +0.21 [0.13, 0.30] | 4 of 4 |
| `khaelano` | common (76 / 135) | 0.91 | 0.80 | +0.11 [0.03, 0.19] | 4 of 4 |

On the common attempts, `tonepool_tcn` (+0.06 and +0.05) and `tiny_tcn1` (+0.09
and +0.03) also exceeded FallDeFi, but only `tiny_tcn1` on `akmal` excluded zero;
`pcspec_gru`'s intervals exclude zero in all four comparisons. FallDeFi's own
trace rule reached balanced accuracy 0.68 (`akmal`) and 0.71 (`khaelano`) on the
common attempts ([tone-pooling report](tone-pooling-2026-11-23.md)).

## Under live conditions (emulated)

`live_eval.py`. A non-fall attempt alarms if any scored window overlapping its
action cue reaches the threshold; a fall alarms if a scored window centred in
its cue does. Attempts with no such window cannot alarm: 6 falls and 16
non-falls of 231 on `akmal`, 6 and 3 of 232 on `khaelano`, the same for every
model. The prompted mix is the detector's ten prompts (two each of walk to sit,
sit to stand, stand to sit and sit to walk; one each of stand to walk and walk
to stand). "First in session" takes the earliest attempts that satisfy that mix
and scores only the attempts after them, as the replay report did with the real
detector.

Attempt false-positive rate / recall, target 0.2 (means over 200 calibration
sets, then four seeds):

| Test | Calibration | `tonepool_tcn` | `tiny_tcn1` | `pcspec_gru` |
| --- | --- | --- | --- | --- |
| `akmal` | random 10 | 0.21 / 0.73 | 0.20 / 0.75 | 0.21 / 0.90 |
| | first 10 in session | 0.11 / 0.55 | 0.07 / 0.59 | 0.04 / 0.63 |
| | none (0.5) | 0.60 / 0.93 | 0.68 / 0.93 | 0.41 / 0.93 |
| `akmal` + continuous | random 10 | 0.21 / 0.65 | 0.20 / 0.76 | 0.20 / 0.81 |
| | first 10 in session | 0.07 / 0.36 | 0.23 / 0.79 | 0.05 / 0.71 |
| | none (0.5) | 0.53 / 0.92 | 0.62 / 0.93 | 0.36 / 0.93 |
| `khaelano` | random 10 | 0.21 / 0.65 | 0.21 / 0.58 | 0.20 / 0.78 |
| | first 10 in session | 0.03 / 0.33 | 0.03 / 0.29 | 0.11 / 0.72 |
| | none (0.5) | 0.24 / 0.70 | 0.33 / 0.74 | 0.07 / 0.67 |
| `khaelano`, all continuous in training | random 10 | 0.21 / 0.68 | 0.22 / 0.62 | 0.20 / 0.73 |
| | first 10 in session | 0.04 / 0.44 | 0.05 / 0.37 | 0.11 / 0.64 |
| | none (0.5) | 0.26 / 0.74 | 0.28 / 0.71 | 0.08 / 0.60 |

`pcspec_gru` under every calibration, with the spread over calibration sets
(90th percentile of the false-positive rate / 10th percentile of recall) and the
median threshold:

| Calibration | `akmal` | `akmal` + continuous | `khaelano` | `khaelano`, all continuous |
| --- | --- | --- | --- | --- |
| Published rule (2 s stride, no gate), random 10 | 0.26 / 0.90 (0.45 / 0.72), 0.93 | 0.25 / 0.77 (0.40 / 0.61), 0.84 | 0.22 / 0.84 (0.41 / 0.71), 0.07 | 0.22 / 0.82 (0.42 / 0.69), 0.05 |
| Live, random 10 | 0.21 / 0.90 (0.34 / 0.85), 0.91 | 0.20 / 0.81 (0.32 / 0.73), 0.79 | 0.20 / 0.78 (0.38 / 0.70), 0.17 | 0.20 / 0.73 (0.37 / 0.61), 0.16 |
| Live, random 20 | 0.19 / 0.90 (0.29 / 0.87), 0.93 | 0.18 / 0.81 (0.28 / 0.74), 0.83 | 0.20 / 0.78 (0.32 / 0.72), 0.15 | 0.20 / 0.75 (0.32 / 0.64), 0.11 |
| Live, prompted 10 | 0.19 / 0.88 (0.31 / 0.76), 0.92 | 0.19 / 0.81 (0.31 / 0.72), 0.81 | 0.19 / 0.77 (0.34 / 0.69), 0.16 | 0.19 / 0.73 (0.32 / 0.62), 0.17 |
| Live, first 10 in session | 0.04 / 0.63, 0.98 | 0.05 / 0.71, 0.95 | 0.11 / 0.72, 0.31 | 0.11 / 0.64, 0.40 |

- **The calibration target holds and recall stays highest.** With ten random
  movements, the false-positive rate was 0.20–0.22 for every model. `pcspec_gru`
  then caught 73–90 % of the falls, against 65–73 % for `tonepool_tcn` and
  58–76 % for `tiny_tcn1`.
- **An unlucky calibration costs it less.** Over the random sets, its 10th
  percentile of recall was 0.61–0.85, against 0.34–0.55 for `tonepool_tcn`. The
  false-positive rate's 90th percentile was 0.32–0.38, like the other models';
  twenty movements narrowed it to 0.28–0.32.
- **It suffers least from calibrating at the start of a session.** Early
  movements score higher (replay report), so the first ten set strict
  thresholds. `tonepool_tcn` then kept only 33–55 % recall, and on `khaelano`
  `pcspec_gru` kept 64–72 % at false-positive rates of 0.11. On `akmal` its
  threshold rose to 0.95–0.98, leaving recall at 0.63–0.71 with false-positive
  rates of 0.04–0.05.
- **Its threshold is the most person-specific.** The median calibrated
  threshold was 0.79–0.93 on `akmal` and 0.11–0.17 on `khaelano` (`tonepool_tcn`:
  0.96 and 0.61–0.70). Uncalibrated at 0.5, it alarmed on 36–41 % of `akmal`'s
  non-falls and caught 60–67 % of `khaelano`'s falls. A calibration at
  installation remains necessary.

### Which activities

Prompted-10 calibration; alarm rate over the attempts outside the calibration
set, range over the two tests of each session:

| Activity (attempts per session) | `pcspec_gru`, `akmal` | `pcspec_gru`, `khaelano` | `tonepool_tcn`, `akmal` | `tonepool_tcn`, `khaelano` |
| --- | --- | --- | --- | --- |
| Sit to stand (32) | 0.00–0.03 | 0.04–0.05 | 0.04–0.05 | 0.23–0.26 |
| Stand to sit (32) | 0.06 | 0.05–0.07 | 0.09–0.12 | 0.18–0.23 |
| Sit to walk (32) | 0.39–0.40 | 0.28–0.29 | 0.29–0.30 | 0.21–0.22 |
| Walk to sit (32) | 0.21–0.22 | 0.32–0.34 | 0.20–0.25 | 0.25 |
| Stand to walk (8) | 0.30–0.32 | 0.39–0.40 | 0.31–0.34 | 0.23–0.29 |
| Walk to stand (8) | 0.40–0.45 | 0.12–0.14 | 0.39–0.42 | 0.04–0.09 |
| Sit to fall (24) | 0.80–0.90 | 0.70–0.74 | 0.62–0.74 | 0.67–0.74 |
| Stand to fall (31 / 32) | 0.79–0.86 | 0.70–0.75 | 0.57–0.74 | 0.69–0.72 |
| Walk to fall (32) | 0.84–0.89 | 0.78–0.82 | 0.68 | 0.61–0.64 |

- **False alarms come from transitions that involve walking.** `pcspec_gru` almost
  never alarmed on sitting down or standing up (at most 7 %). Each walking
  transition alarmed on 12–45 %. `tonepool_tcn` spread its false alarms more
  evenly and flagged a quarter of `khaelano`'s sit-to-stand attempts.
- **Every kind of fall gained.** `pcspec_gru` caught 70–90 % of each kind, and
  walking falls most (78–89 %), which `tonepool_tcn` caught at 61–68 %.

### Alarm delay

From the main burst peak of each detected fall to the end of its first alarming
window (prompted 10; medians over the pooled detected falls of 200 sets, then the
median over seeds). The live detector publishes a window about 1.2 s after its
end ([replay report](live-replay-evaluation-2026-11-25.md)), which these figures
do not include.

| Test | `tonepool_tcn`: median (10th–90th percentile) | `tiny_tcn1` | `pcspec_gru` |
| --- | --- | --- | --- |
| `akmal` | 0.92 s (0.46–2.01) | 0.85 s (0.28–2.05) | 0.87 s (0.26–2.05) |
| `akmal` + continuous | 1.12 s (0.68–2.19) | 0.93 s (0.48–2.03) | 0.88 s (0.21–2.00) |
| `khaelano` | 0.85 s (0.47–2.43) | 0.83 s (0.31–2.46) | 0.74 s (0.18–2.22) |
| `khaelano`, all continuous | 0.96 s (0.53–2.44) | 0.91 s (0.51–2.46) | 0.63 s (0.11–2.22) |

With publication, a `pcspec_gru` alarm would follow the burst by about 1.8–2.1 s
(median), slightly earlier than `tonepool_tcn`. With first-in-session thresholds
its delay on `akmal` rose to 1.36–1.63 s before publication, because the
threshold rose to 0.95–0.98. `tonepool_tcn`'s first-ten delays here (1.01–1.31 s,
2.2–2.5 s with publication) agree with the real detector's 2.1–2.6 s.

### Idle time

The held-out continuous hour exists only in the `akmal` + continuous test: 12
exported idle segments, 0.64 scored hours after the gate. Alarmed windows less
than 4 s apart count as one episode.

| Threshold | `tonepool_tcn`: episodes (per seed) | `tiny_tcn1` | `pcspec_gru` |
| --- | --- | --- | --- |
| Prompted 10 | 1.4 (1.0–2.0) | 1.4 (0.8–2.3) | 2.6 (1.1–4.3) |
| First 10 in session | 0.5 (0–2) | 1.8 (0–3) | 1.0 (0–2) |
| Uncalibrated 0.5 | 8.3 (4–14) | 2.5 (2–3) | 8.3 (1–22) |

With the prompted calibration, `pcspec_gru` raised about 4.0 alarm episodes per
scored idle hour, against 2.2 for both other models; its two highest seeds
(3.3 and 4.3 episodes) drive this. At 0.5, the failed seed 45 alone raised 22
episodes, the other seeds 1–5. These rates come from one hour of one day and
cannot predict false alarms per day.

## Computational cost

`inference_cost.py`. Each live hop scores one 4 s window per model after the
shared preprocessing (alignment, Hampel filter, difference), which is not timed
here. Setup:

- Intel i7-14700F, ONNX Runtime 1.31.1 on the CPU with the detector's settings
  (four intra-op threads, no spinning), batch 1, median over 300 calls.
- The `pcspec_gru` and `pctcn` heads (batch normalization, GRU or TCN, linear
  layer on the 53 × 65 frame features) were exported like `03_training` does
  (dynamo, opset 18), from seed 42's `khaelano`-holdout checkpoints. Their ONNX
  Runtime logits equalled PyTorch's.
- The front end is PyTorch's own `frame_features` (all eigenvectors) on 64 real
  test windows.

| Model | Per window | Parts |
| --- | --- | --- |
| `tiny_tcn1` | 0.33 ms | ONNX model, 48 KiB |
| `tonepool_tcn` | 5.1 ms | ONNX model, 319 KiB |
| `pcspec_gru`, PyTorch front end | 5.4–14.9 ms | front end 5.3 ms (4 threads, float32), 7.4 ms (4 threads, float64), 9.4 ms (1 thread, float32) or 14.8 ms (1 thread, float64); ONNX head 0.06 ms, 140 KiB |
| `pcspec_gru`, Rust front end | 0.9–2.3 ms | front end 2.2 ms (1 thread) or 0.86 ms (4 threads), see below; ONNX head 0.06 ms |
| `pctcn` | the same front end + 0.09 ms | ONNX head, 270 KiB |

- **The front end is almost the whole cost.** The GRU head takes 0.06 ms. With a
  solver for the five leading eigenvectors only, the front end's parts took
  about 8 ms on one core in float64 (`20261126-pc-spectrum/live_cost.py`).
- **With the PyTorch front end, `pcspec_gru` costs one to three times
  `tonepool_tcn`** and 16–45 times `tiny_tcn1` per window: 2–6 % of the 250 ms
  hop. With the Rust front end it costs less than half of `tonepool_tcn`.
- **The arithmetic agrees.** Approximate multiply-accumulates per window from the
  layer shapes:
  - `tonepool_tcn`: 215 M, mostly its per-tone encoder;
  - `pcspec_gru`: 150 M, mostly the covariances and eigendecompositions, plus
    1.3 M for the GRU;
  - `tiny_tcn1`: 1.1 M.
- **Where it runs differs.** `tonepool_tcn` and `tiny_tcn1` can run wholly on the
  GPU through WebGPU. The PC-spectrum front end would run on the CPU in Rust,
  with only the small head on the GPU. On the AMD laptop, which was not
  measured, `pcspec_gru` would therefore load the CPU more.
- **Timings vary between runs.** The energy-inputs report measured 4.35 ms
  (`tonepool_tcn`) and 0.25 ms (`tiny_tcn1`) with saved live inputs; random
  inputs here gave 5.1 and 0.33 ms. The order is the same.

### The Rust front end

`src/native/radio_core/crates/radio_signal/src/pc_spectrum.rs` and
`symmetric_eigen.rs`, Python class `fall_detection._radio_native.PcSpectrumFrontEnd`;
checks in `rust_frontend.py`, `rust_benchmark_results.txt`, the crate's tests and
`tests/analysis/sequence/test_pc_spectrum.py`. The live detector runs it for
`pcspec_gru-4s` ([live PC-spectrum report](live-pcspec-2026-11-26.md)).

It computes the same features as the model, exactly. What makes it fast:

- **Sliding covariance sums.** Each receiver keeps float64 sums of its usable
  samples and their products. When a window starts 30 samples after the
  previous one and the shared 450 samples are identical bit for bit (checked
  while gathering), only the 60 entering and leaving samples are added and
  removed. Otherwise, and every 1,024 updates, the sums are recomputed. The
  result therefore never depends on the stream's history.
- **Five eigenvectors, not all.** Householder reduction to tridiagonal form in
  float32, bisection of the five largest eigenvalues in float64, inverse
  iteration for their vectors, and back-transformation of those five only.
- **Kernels shaped for the cache.** The reduction makes one pass per step:
  each step's rank-2 update and the next step's matrix-vector product, two
  rows at a time. The column being reduced is captured contiguously. Partial
  sums never take narrow stores that later wide loads would stall on. Entries
  of the tridiagonal eigenvectors below 1e-30 are set to zero, because as
  float32 subnormals they made the back-transformation eight times slower.
- **AVX2 and FMA** with runtime detection and a scalar fallback. Receivers
  without a usable frame are skipped. A persistent pool can split the four
  receivers across threads.

On the 1,816 consecutive live-hop windows of 40 `khaelano` test segments
(seed 42's `khaelano`-holdout checkpoint), against `frame_features` in float64:

| Front end | Largest feature difference | Largest logit difference | Median time per window |
| --- | --- | --- | --- |
| Rust, each window from scratch | 2.5e-5 | 9e-6 | 3.49 ms |
| Rust, streaming (shift 30) | 2.5e-5 | 9e-6 | 2.22 ms |
| Rust, streaming, 4 threads | 2.5e-5 | 9e-6 | 0.86 ms |
| Rust, streaming, scalar fallback | 1.2e-5 | 2.4e-5 | 7.99 ms |
| PyTorch, float32 (training precision) | 7.4e-5 | 1.2e-5 | 9.4 ms (1 thread) |

The streaming results equalled the stateless ones. After each segment's first
window, every receiver used the sliding update. The kernel time excludes the
binding's copy of the input.

On synthetic windows (`benchmark_pc_spectrum`, one performance core), streaming
took 1.98 ms with one thread and 0.60 ms with four. Per receiver and window:

| Stage | Time |
| --- | --- |
| Tridiagonal reduction | 0.267 ms |
| Gather, overlap check, frame flags | 0.055 ms |
| Bisection | 0.053 ms |
| Sliding sums | 0.051 ms |
| Spectrum | 0.029 ms |
| Inverse iteration | 0.024 ms |
| Back-transformation and projection | 0.022 ms |
| Covariance | 0.006 ms |

- **The reduction dominates.** At 0.27 ms it is within about two times the
  arithmetic floor of about 0.11–0.15 ms for this matrix order. A blocked
  reduction might gain a further 10–20 %; that was not tried.
- **Bisection is limited by the latency of each division chain**, not by
  division throughput: fewer lanes did not help.
- **Efficiency cores** ran the reduction at about half speed (0.78 against
  0.41 ms, pinned, with an earlier version of the kernel), as 256-bit vectors
  are split there.
- **Recomputing from scratch** (stream start, after a gap, every 1,024 hops)
  costs 3.4 ms on one thread, mostly the float64 covariance of 480 samples.
- **Not measured:** the AMD laptop, and the front end inside the detector.

## Failure modes

- **One of 16 runs failed.** Seed 45 on `akmal` + continuous ranked attempts at
  0.684, caught 41 % of falls at the calibrated rate offline, and raised the
  most idle alarms. Its validation loss (0.336) was the highest of the 16 runs,
  so validation could have flagged it here. Whether that holds in general is
  unknown. A deployed model is a single seed, so its held-out score should be
  checked before it is used.
- **Walking transitions are the main confusion.** They make up 80 of the 144
  non-falls per session, and the calibration mix contains six of them in ten
  prompts.
- **Unscored attempts.** The 70 % coverage gate leaves 6 falls per session
  without a window that could alarm, a ceiling of about 93 % on live recall.
  The gate depends only on the radio data, not on the model.
- **Recall on `khaelano` is lower** (0.73–0.78 against 0.81–0.90 on `akmal`)
  when trained on `akmal`. The model was trained on one participant each time.

## Limits

- Two participants and one room. Every fall came after every non-fall, with the
  mattress in place. Still windows showed no setup signature (pc-spectrum
  report), but fall windows contain the landing on the mattress.
- The input was designed after screens on the same two sessions; the training
  settings were fixed beforehand, not tuned.
- Validation data come from the training participant.
- Live behaviour is emulated offline. It uses the recorded gaps and the
  detector's own calibration code, but the PC-spectrum front end does not exist
  in the live detector, and its time per hop and its parity with this emulation
  are unmeasured.
- Paired and calibration intervals cover the tested attempts and calibration
  draws, not training randomness beyond four seeds.
- The idle estimate rests on 0.64 scored hours from one day.

## Files

Under `artifacts/notebooks/diagnostics/20261126-pcspec-evaluation/`:

| File | Content |
| --- | --- |
| `offline_summary.py`, `offline_summary.csv`, `offline_summary_results.txt` | Per-seed results and ROC operating points |
| `falldefi_compare.py`, `falldefi_compare.csv`, `falldefi_compare_results.txt` | Against FallDeFi on the same attempts |
| `live_eval.py`, `live_eval*.csv`, `live_eval_results.txt` | Live-hop rescoring, calibrations, activities, delays, idle episodes and checks |
| `inference_cost.py`, `inference_cost.csv`, `inference_cost_results.txt` | Time and arithmetic per window for the three models |
| `frontend_speed.py`, `frontend_speed_*.csv`, `frontend_speed_results.txt` | Faster front-end variants (NumPy): time and logit effect |
| `rust_frontend.py`, `rust_frontend.csv`, `rust_frontend_results.txt`, `rust_benchmark_results.txt` | The Rust front end: parity with PyTorch and time |
| `dense/pcspec_gru/`, `dense/tiny_tcn1/` | Window scores at the live hop (`tonepool_tcn`'s are in `20261124-live-calibration/dense/`) |

The model runs are listed in `20261126-pc-spectrum/pcspec_runs.json`.
