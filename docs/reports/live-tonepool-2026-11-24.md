# Live `tonepool_tcn` path, 24 November 2026

Follows the [tone-pooling report](tone-pooling-2026-11-23.md), which found the
4 s `tonepool_tcn` trained on burst-centred positives the most consistent model.
This report records how it was put into the live detector, what was checked, and
what was not. It contains no detection-accuracy result.

## Published model

`artifacts/model/tonepool_tcn/` is the ONNX bundle of `03_training` run
`20261123T153725520115Z`: 4 s windows, burst-centred training positives, all
three datasets, the 22 November random attempt split (`SPLIT_SEED` 42), model
seed 45. The random split is confounded by the equipment-ordered protocol
([generalization report](generalization-2026-11-22.md)); it only defines which
attempts trained the bundle. The evidence for choosing this configuration is
the session holdouts in the tone-pooling report.

Four seeds of this configuration existed. Their best validation balanced log
loss, the metric that selected each run's checkpoint, was 0.2334 (seed 42),
0.1920 (43), 0.2285 (44) and 0.1919 (45). Seed 45 was published by that rule;
the difference to seed 43 is negligible. The rule does not use test scores, but
the seeds' test attempt AUCs (0.783, 0.812, 0.840 and 0.828 for seeds 42–45, on
the confounded random split) had been printed before the rule was fixed in
favour of the project's default seed 42.

The bundle was copied from the run's `onnx/full/tonepool_tcn/`, as the notebook
would, and added to `artifacts/model.dvc`. The manifest's integrity check passes.

## Implementation

Model families are declared once, in `bundle::FAMILIES` (name and the operator
that must run on the GPU); the bundle loader, backend, scheduler and runtime
read the list. `tonepool_tcn` is selectable as `tonepool_tcn-4s` and is the
default of `fall-detect`. No preprocessing changed: the model reads the same
`[batch, 480, 1964]` input (980 normalized signals, 980 validity flags,
four presence flags). The WebGPU warm-up audit expects `Conv` to run on the GPU.

## Checks

Offline tests and a replay of capture `native-capture-20261112-c` (about ten
seconds, no falls) on this machine (Intel i7-14700F, RTX 4070 SUPER).

- **Preprocessing.** The replay test now drives `cnn-4s` and `tonepool_tcn-4s`
  together. Every live input of both models matched the offline Python chain bit
  for bit, each with its own saved normalizer. Giving `tonepool_tcn` the CNN's
  normalizer makes the test fail, so it is not vacuous.
- **Inference.** Over the 24 scored windows of one run, the Rust logits equalled
  Python ONNX Runtime exactly and the original PyTorch checkpoint to
  2.4e-6.
- **CPU.** 24 of 26 windows scored; the other two, which extend past the end of
  the recording, reported `coverage`. Median inference was 8.8 ms with
  `cnn-4s` running alongside and 2.8 ms alone (the latter from 7 windows); window end to publication was
  about 1.2–1.3 s. The scores were 0.0015–0.025, as expected for quiet data.
- **WebGPU.** Probed outside the project with ONNX Runtime 1.31.1 and WebGPU
  plugin 0.5.0 on the RTX 4070 SUPER through Dawn/Vulkan. Placement passes the
  detector's own audit with the operators it allows on the CPU: only an int64
  `Concat` (shape arithmetic) ran there. GPU and CPU logits differed by at most
  3.1e-6 over the saved windows. The median inference call took 3.9 ms from
  Python. This machine has no AMD GPU, so the detector's adapter selection and
  the laptop's Vega 7 were not exercised.

`uv run pytest` passed (690). The Python-free Rust crates' tests passed. The
PyO3 crate's `cargo test` could not link here (no `libpython3.12` development
library), although the extension builds through uv. Two clippy findings
(`chunks_exact_to_as_chunks`) come from a newer toolchain in lines this change
did not touch.

## Coverage gate

The live detector reports a window as unknown if any receiver covers less than
70 % of it (`--minimum-coverage 0.7`). The offline export keeps every coverage
level, so the model was trained and evaluated without this gate. It stays at
70 %. Its effect on the held-out sessions is in the
[calibration report](live-calibration-2026-11-24.md#coverage-gate).

A first version of this section, written the same day, was wrong in three ways.
It joined windows by segment name across datasets, included continuous
windows in its AUCs, and used a coverage measured before differencing, which
the live gate does not use. Its statement that failing windows ranked falls
about as well in three of four holdouts does not hold: they rank worse on
`khaelano` and about as well on `akmal`.

Live sessions on 18 November lost 35–78 % of windows to this gate
([hardware check](../automatic-radio-recovery.md#hardware-check-18-november-2026)).

## Limits

- Without a calibration, the threshold for a "fall candidate" is 0.5. The
  published recall and false-positive rates of this configuration come from an
  installation calibration, which the detector gained later the same day
  ([calibration report](live-calibration-2026-11-24.md)). Live windows use a
  250 ms hop instead of 2 s, so an offline threshold does not transfer.
- One training split, one seed and two participants; room and mattress
  confounds as in the tone-pooling report.
- Sustained live operation, AMD GPU inference and detection accuracy remain
  unverified.
