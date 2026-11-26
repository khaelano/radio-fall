# Live `tiny_tcn1` path, 26 November 2026

Follows the [energy-inputs report](energy-inputs-2026-11-26.md), where
`tiny_tcn1` (5,345 parameters, motion energy averaged over tones and receivers)
matched `tonepool_tcn` on the four session holdouts. This report records how it
was moved into `03_training`, published and made selectable in the live
detector, and what was checked. It contains no detection-accuracy result.
`tonepool_tcn-4s` stays the default until a new participant confirms the
holdout result.

## Notebook

The three tiny models (`TorchTinyTCN1`, `TorchTinyTCN3`, `TorchTinyCNN3`) are
now defined in `03_training` (cell `d4e7a1c3`) instead of being patched in by
`tiny_holdouts.py`, with their own training cells and the tone-pool settings.
The code is unchanged except that the input width also handles 96 Hz inputs
without presence flags. Retraining seed 42 tested on `akmal` with the
notebook's class reproduced all 1,352 test probabilities of the earlier run
exactly (`20261126T005246442236Z` against `20261125T181658450435Z`), so the
energy-inputs results apply to the notebook code.

## Published model

`artifacts/model/tiny_tcn1/` is the ONNX bundle (48 KiB) of `03_training` run
`20261126T005404382343Z`: 4 s windows, burst-centred training positives, all
three datasets, the 22 November random attempt split (`SPLIT_SEED` 42; split
hash `14c6d09c…`, as for the published `tonepool_tcn`), model seed 45. Its
normalizer is byte-identical to `tonepool_tcn`'s, because both were fitted on
the same training windows. The random split is confounded by the
equipment-ordered protocol ([generalization report](generalization-2026-11-22.md));
it only defines which attempts trained the bundle. The evidence for the model
is the session holdouts in the energy-inputs report.

Four seeds were trained (`full_split_runs.py`). The rule, fixed before
training, was the one used for `tonepool_tcn`: publish the lowest validation
balanced log loss at the chosen checkpoint. The values were 0.2095 (seed 42),
0.1842 (43), 0.1686 (44) and 0.1649 (45). Test scores were not read for the
choice. The bundle was copied from the run's `onnx/full/tiny_tcn1/`, as the
notebook would; the export's logit check against PyTorch gave at most 9.5e-7.

## Implementation

`tiny_tcn1` is a fifth entry in `bundle::FAMILIES` (main operator `Conv`) and
selectable as `tiny_tcn1-4s`. The resident-model limit follows from the list
(15). No preprocessing changed: the model reads the same `[batch, 480, 1964]`
input and averages it inside the graph. It does not read the four presence
flags.

## Checks

Offline tests and replays of capture `native-capture-20261112-c` (about ten
seconds, no falls) on this machine (Intel i7-14700F, RTX 4070 SUPER).

- **Preprocessing.** The replay test now drives `cnn-4s`, `tonepool_tcn-4s`
  and `tiny_tcn1-4s` together. Every live input matched the offline Python
  chain bit for bit. Because the tiny and tone-pool normalizers are the same
  file content, this does not test the tiny bundle's normalizer independently
  of `tonepool_tcn`'s.
- **Inference.** Over the 24 scored windows of one run, the Rust logits
  equalled Python ONNX Runtime exactly and the PyTorch checkpoint to 1.9e-6.
  The replay test now compares the logits of both `tonepool_tcn-4s` and
  `tiny_tcn1-4s` and fails if a model has no scored window to compare.
- **CPU.** 24 of 26 windows scored; the other two reported `coverage`, as
  for `tonepool_tcn` on this capture. Median inference was 0.63 ms alone
  and 0.60 ms with `tonepool_tcn-4s` alongside (5.51 ms for that model in the
  same run); window end to publication was 1.17–1.19 s. Scores were
  0.0011–0.054 on this quiet capture.
- **WebGPU.** Probed outside the detector (`webgpu_probe.py`) with ONNX
  Runtime 1.31.1 and WebGPU plugin 0.5.0 on the RTX 4070 SUPER through
  Dawn/Vulkan, applying the detector's placement rule to three warm-up calls.
  Every operator ran on WebGPU and none on the CPU. GPU and CPU logits
  differed by at most 2.4e-6 over the 26 saved windows; the median batch-1
  call took 2.2 ms from Python. The same probe on `tonepool_tcn` reproduced
  the earlier result (only an int64 `Concat` on the CPU, 3.1e-6). The
  detector's AMD adapter selection and the laptop's Vega 7 were not
  exercised.

`uv run pytest` passed (709). The `radio-detection` crate's tests passed,
including the ignored checks of every published bundle and normalizer.
Clippy still reports the two earlier `chunks_exact` findings in lines this
change did not touch.

## Limits

- Thresholds are per model. Calibrate `tiny_tcn1-4s` on the installation
  movements like the other models; an offline threshold does not transfer.
- A sample without any valid tone gives the model a mean of zero, the
  training average, and `tiny_tcn1` has no coverage input to tell such
  samples apart. In the exports this affects 0.24 % (`akmal`), 0.03 %
  (`khaelano`) and 0.01 % (continuous) of samples, in runs of at most 32
  samples (0.27 s). Its effect was not measured.
- Two participants, one room, the mattress confound and one training split,
  as in the energy-inputs report. Sustained live operation, AMD GPU inference
  and detection accuracy remain unverified.

## Runs and files

Under `artifacts/notebooks/diagnostics/20261126-tiny-tcn/`:
`full_split_runs.py` and `full_split_runs.json` (reproduction check and the
four seed runs, `20261126T005246442236Z` to `20261126T005404382343Z`) and
`webgpu_probe.py`.
