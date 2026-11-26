# Live `pcspec_gru` path, 26 November 2026

Follows the [principal-component spectrum report](pc-spectrum-2026-11-26.md)
and the [evaluation of `pcspec_gru`](pcspec-gru-evaluation-2026-11-26.md).
On the session holdouts, `pcspec_gru` reached a mean attempt AUC of 0.903
against 0.836 for `tonepool_tcn`. Its front end, per-window principal
components and STFT power, has no ONNX operator. It now runs in Rust in the live
detector, followed by an ONNX head. This report records how the model was moved
into `03_training`, published and made selectable as `pcspec_gru-4s`, and what
was checked. It contains no new detection-accuracy result. `tonepool_tcn-4s`
stays the default until a new participant confirms the holdout result.

## Notebook

`03_training` now defines `TorchPCSpectrum` (cell `e7b4c2a9`; registry key
`pcspec_gru`), with its own training cell (`a6f2d8c4`, tone-pool settings). The
cell trains only when `REPRESENTATION = "signed_difference"`. That export is
written by `20261125-signed-difference/export_signed.py`, not by
`02_preprocess`. The class is the harness's code with no change to the
computation. Retraining seed 42, tested on `akmal`, reproduced all 1,352 test
probabilities of the earlier run exactly (`20261126T104508504810Z` against
`20261126T015943831550Z`), so the earlier results apply to the notebook code.

The export cell now handles models with a front end ONNX cannot express:

- **Head only.** It exports `head_module()`: the GRU and linear layer on the
  53 × 65 frame features, with the batch norm folded into the GRU's input
  weights, an affine map per feature. The export therefore has no batch-norm
  operator.
- **Two checks.** ONNX Runtime logits must match the full PyTorch model at batch
  sizes 1 and 2. They must also match it on features computed from the same
  windows by the live detector's Rust front end (`PcSpectrumFrontEnd`).
- **Manifest.** Each export records its `representation`, the `front_end`
  definition (kind, version, components, window, hop, bins, thresholds,
  interior tones, log floor) and the head's input shape `[batch, 53, 65]`.
- **Publication.** A model is published to `artifacts/model/` only on the
  representation its live family computes: the default, or the signed
  difference for `pcspec_gru`. Runs with `HELD_OUT_SESSION` are still not
  published.

## Published model

`artifacts/model/pcspec_gru/` holds the head (128 KiB) and normalizer of
`03_training` run `20261126T104817208746Z`:
- 4 s windows, burst-centred training positives, model seed 45;
- the signed difference of all three datasets;
- the 22 November random attempt split (`SPLIT_SEED` 42). Its 3,739 windows and
  their assignments equal those of the published `tonepool_tcn` and `tiny_tcn1`.
  The split file's hash differs only because it records the signed export's
  paths.

The normalizer holds signed-difference statistics, so it differs from the other
bundles'. The random split is confounded by the equipment-ordered protocol. It
only defines which attempts trained the bundle; the evidence for the model is
the session holdouts.

Four seeds were trained (`20261126-pcspec-live/full_split_runs.py`). The rule,
fixed before training, was the one used for `tonepool_tcn` and `tiny_tcn1`:
publish the lowest validation balanced log loss at the chosen checkpoint. The
values were 0.1265 (seed 42), 0.1376 (43), 0.1683 (44) and 0.1242 (45). Test
scores were not read for the choice. The export's logits matched PyTorch to
1.4e-6, and so did the head on the Rust front end's features.

## Implementation

- **Families.** In `radio_detection::bundle`, each family now declares the
  representation it reads and whether the front end precedes ONNX.
  `pcspec_gru` is the sixth family: main operator `GRU`, signed difference,
  front end. The resident-model limit follows from the list (18).
- **Manifest checks.** The loader requires a front-end export's `front_end`
  block to equal the definition compiled into `radio_signal::pc_spectrum`, its
  `representation` to match the family (bundles without the field read the
  default), and its input shape to be `[batch, 53, 65]`.
- **Signed input.** `window::prepare` also keeps the float64 difference cast to
  float32 when a selected model needs it, which is how the offline export
  computes it. Each model assembles its input from its own representation with
  its own normalizer; assembled inputs are shared only between models with the
  same window length, normalizer and representation.
- **Front end.** A front-end model keeps a `PcSpectrum` on the coordinator
  thread, between assembly and the ONNX call. When the window continues the
  same generation, the shift since the model's previous window is passed. The
  front end verifies the overlap bit for bit before updating its covariance
  sums, so a stale shift costs time, never accuracy. A new segment resets it,
  and a window already late for publication skips it.
- **Inference.** `Job` and `Runtime::infer_view` carry the ONNX input shape
  instead of assuming `[time, 1964]`; the warm-up uses each export's shape.
  The `qualify` examples follow.
- **Published rows** gain `timings.front_end_ns` and `front_end_updates` (per
  receiver: `full`, `sliding` or `skipped`; null for other models). The preview
  and the input log still show the assembled window.
- **Desktop app.** `fall-detect` lists `pcspec_gru-4s`. Calibration is per
  model, as before.

## Checks

These are offline tests and replays of capture `native-capture-20261112-c`
(about ten seconds, no falls) on this machine (Intel i7-14700F, RTX 4070 SUPER).

- **Preprocessing.** The replay test now drives `cnn-4s`, `tonepool_tcn-4s`,
  `tiny_tcn1-4s` and `pcspec_gru-4s` together. Every live input matched the
  offline chain bit for bit, including the 26 signed-difference windows of
  `pcspec_gru-4s` with their own normalizer.
- **Front end and head.** In a replay at recording speed
  (`capture_replay.py`), 24 of 26 windows scored; two reported `coverage`, as for
  the other models on this capture. Over the 24 scored windows:
  - the live logits equalled Python ONNX Runtime exactly, on features the native
    front end recomputed from each saved window without stream state;
  - they matched the published checkpoint's PyTorch model in float64 to 2.3e-6;
  - the receivers' covariances slid in 92 of 96 receiver-windows and were
    computed in full in the 4 of the first window.

  The replay test now checks these logits too and fails if a model has no
  scored window.
- **Time on the CPU backend.**

  | Model | Front end | ONNX inference | Window end to publication |
  | --- | --- | --- | --- |
  | `pcspec_gru-4s` | 2.29 ms median (p90 2.46) | 0.16 ms | about 1.2 s, as for the other models |
  | `tonepool_tcn-4s` (same run) | — | 5.53 ms | about 1.2 s |
- **WebGPU.** Probed outside the detector (`20261126-pcspec-live/webgpu_probe.py`,
  ONNX Runtime 1.31.1, WebGPU plugin 0.5.0, RTX 4070 SUPER through Dawn/Vulkan),
  with the detector's placement rule:
  - the GRU, `Gemm`, `ReduceMax` and the shape operators ran on WebGPU; only
    allowed shape operators (`Concat`, `Gather`, `Slice`, `Mul`, `Reshape`) ran
    on the CPU, so the rule accepted the session;
  - GPU and CPU logits differed by at most 4.8e-6 over 64 real windows' features;
  - a batch-1 call took a median 1.42 ms from Python, more than on the CPU for
    this small head.

  The detector's AMD adapter selection and the laptop's Vega 7 were not
  exercised. The front end runs on the CPU in either case.
- **Suites.** `uv run pytest` passed (717). The workspace's Rust tests passed,
  including the ignored checks of every published bundle and normalizer and a
  check that the loader's front-end definition equals what `03_training` writes.
  Clippy reports only the two earlier `chunks_exact` findings in
  `radio_detection` lines this change did not touch.

## Limits

- **Thresholds are per model.** Calibrate `pcspec_gru-4s` on the installation
  movements like the other models. Its calibrated threshold differed most
  between the two participants (evaluation report).
- **The front end adds about 2.3 ms per window to the coordinator thread**, which
  also builds every model's inputs. The thread was not measured under several
  front-end models at once, or on the AMD laptop.
- **The real detector has not replayed the participant sessions** with this
  model. The live behaviour in the evaluation report (calibration, delay,
  idle alarms) is an offline emulation with the same hop, gate and calibration
  code. A session replay needs head exports of the holdout checkpoints.
- **The signed-difference export** is produced by a diagnostic script; adding it
  to `02_preprocess` would change that notebook's fingerprint and rebuild the
  default export.
- **The capture** has no falls and lasts ten seconds; it checks agreement, not
  accuracy.

## Files

| Item | Location |
| --- | --- |
| Model class and export path | `notebooks/latest/03_training.ipynb` (cells `e7b4c2a9`, `a6f2d8c4`, `b8ae7f37`) |
| Front end | `src/native/radio_core/crates/radio_signal/src/pc_spectrum.rs`, `symmetric_eigen.rs` |
| Detector | `src/native/radio_core/crates/radio_detection/src/{bundle,window,scheduler,runtime,backend}.rs` |
| Published bundle | `artifacts/model/pcspec_gru/` |
| Training, reproduction check, seed choice | `artifacts/notebooks/diagnostics/20261126-pcspec-live/full_split_runs.py`, `full_split_runs.json`; runs `20261126T104508504810Z` (check) and `20261126T104554564332Z` to `20261126T104817208746Z` (seeds 42–45) |
| Live checks | `capture_replay.py`, `webgpu_probe.py` and their `*_results.txt` in the same folder; `tests/apps/detector/test_native_replay.py` |
