# Native detector real-time replay, 2026-11-12

## Purpose

Check the complete native detection path without radio hardware: recorded
gateway batches → capture-time mapping → aligned history → preprocessing →
resident ONNX session → published result. Also check that the live input
builder reproduces the offline preprocessing for the same CSI.

## Setup

- Host: AMD Ryzen 7 PRO 4750U with integrated Radeon (Vega 7), release build.
- Input: DVC-tracked native captures `native-capture-20261112-b` and `-c`
  (about ten seconds each, four receivers). Capture C supplies its logged
  per-record capture times. Capture B's times are reconstructed from its
  reference events at USB arrival. Capture A has no reference evidence and
  cannot be replayed.
- Replay speed 1.0: batches are released when the replay clock reaches their
  recorded acceptance time. Consecutive captures are separated by 2 s and start
  a new segment.
- Model `cnn-4s` from `artifacts/model/cnn/` with its saved normalizer. Hop
  250 ms, delivery grace 900 ms, minimum receiver coverage 0.7.
- Preprocessing: `Preprocessing::operational()` (120 Hz, centered 0.5 s Hampel,
  threshold 3, minimum five values, squared difference, `log1p`, saved
  normalizer).

## Results

| Run | Backend | Windows | Scored | Inference median / max | Window end → publication median / max |
| --- | --- | --- | --- | --- | --- |
| C | CPU | 26 | 24 | 3.9 / 6.2 ms | 1.24 / 1.25 s |
| C | WebGPU/Vulkan | 26 | 24 | 14.8 / 17.3 ms | 1.24 / 1.25 s |
| B then C | WebGPU/Vulkan | 54 | 45 | 14.3 / 15.8 ms | 1.24 / 1.25 s |

The unscored windows reported `coverage`: at least one receiver had less than
70% of its samples in the window. In capture C they are the two windows that
extend past the end of the recording. There were no runtime errors, history
resets other than the run change, or scheduler replacements.

CPU and WebGPU scores were identical to the three printed decimals for all 24
capture C windows (range 0.078–0.299). Publication age is dominated by the
designed wait: 0.25 s of future filter context plus 0.9 s of delivery grace.
Preprocessing one four-second window took roughly 50–80 ms on this host.

In the GUI preview of capture C, missing rounds are not scattered: each
receiver loses a block of roughly 0.1 s about every 0.5 s, offset between
receivers. This is consistent with the scheduled batch delivery and explains
the steady ~80% per-receiver coverage. It was observed visually on one capture
and not measured further.

## Preprocessing parity

With `save_inputs`, the detector writes every submitted model input. An
independent reference recomputed each window from the capture C journal with
the offline Python functions (`sequence_offsets`, `align_samples`,
`hampel_subcarriers`, `squared_difference`, `Normalizer.transform`) and the
receiver-presence flags. All 26 capture C windows matched bit for bit,
including the two partial windows at the end. The test
`tests/detection/test_native_replay.py` repeats this check.

A repeated run of this test first exposed a coordinator race: windows could be
built while delivered batches were still queued, which changed Hampel output in
the final 0.25 s of a window. The coordinator now ingests every queued batch
before scheduling, and replay finalizes windows only up to the time the feed
has fully delivered. Afterwards the test passed 10 of 10 runs idle and 5 of 5
with all CPU cores saturated. Under that load most windows became `stale`
rather than scoring late, which is the intended behavior.

The reference shares two Rust kernels with the live path: magnitude decoding
and the Hampel filter. Parity therefore verifies the independently implemented
steps (alignment, differencing, transformation, normalization, presence and
window placement), not those kernels. The settings are the documented
operational values in
[amplitude preprocessing](../amplitude-preprocessing.md). They were not
re-read from `02_preprocess.ipynb` in this check.

## Limits

- Twenty seconds of recorded data with no falls; scores here say nothing about
  detection accuracy.
- Replay does not exercise the USB gateway, receiver startup or radio-failure
  restarts. Those need hardware.
- The acquisition-gap reset path was not triggered by these captures.
