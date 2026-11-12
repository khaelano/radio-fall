# Project knowledge base

This file records current implementation boundaries and research decisions. Use
linked guides and dated reports for schemas, commands, measurements, and
experiment detail. Keep this page brief; treat proposals and open questions as
unimplemented until code or verified evidence resolves them.

## Project and data

The project studies fall detection from Wi-Fi channel state information (CSI)
recorded with ESP32-C5 radios. Current research notebooks are under
[`notebooks/latest/`](../notebooks/README.md). Retired experiment notebooks and
their generated outputs have been removed from the repository;
retained model-pilot results are summarized in
[fall model pilots](reports/fall-model-pilots.md).

Raw participant recordings are immutable. Recordings and reusable derived
datasets belong under `data/` and are versioned with DVC. Local notebook runs,
metrics, and figures belong under ignored `artifacts/notebooks/`.
Model bundles belong under `models/sequence/`, tracked by `models/sequence.dvc`.
Use the safe-prune utility to inspect eligible local cleanup candidates. See
the [data layout](../data/README.md) and [dataset format](dataset-format.md).

## Implemented

- **Collection:** the desktop collector supports protocol-driven trials,
  continuous activity segments, session resume, synchronized video, and
  automatic radio recovery. Accepted recordings are finalized before an attempt
  is accepted. See the [collector guide](../src/fall_detection/collection/README.md),
  [recovery notes](automatic-radio-recovery.md), and
  [video guide](video-recording.md).
- **Radio:** Retired live BLE and UDP experiment acquisition code has been
  removed, along with historical BLE decoding tools. Gateway envelopes and
  CSI1 v3 records are decoded by Rust; the host accepts gateway policy
  version 7 and operational inventory/profile schema 2 only.
  `configs/radio.json` is the shared operational settings file.
  C5 receivers send scheduled ESP-NOW batches to a C6 USB gateway; hardware
  qualification evidence and limitations are in the
  [gateway guide](espnow-gateway.md) and [dated reports](reports/README.md).
- **Storage:** closed sessions use verified ZIP64 archives. New collector
  streams are written as independent Zstandard frames and retained in version-2
  archives; newly created archives use version 2 even when files are plain.
  Readers accept version 2 only. Existing version-1 raw archives are retained
  unchanged; verified derived copies are stored in `data/normalized/sessions/`.
  The archive contract documents integrity checks, resume behavior, and
  durability limits.
- **Analysis:** shared code owns verified session reads, alignment primitives,
  native signal operations, memory-mapped storage, export validation, and
  leakage-safe training inputs. `notebooks/latest/02_preprocess.ipynb` owns
  session selection, filtering settings, transformations, cue labels, windowing,
  and figures; `03_training.ipynb` owns the model definitions and training loop.
  The duplicate standalone PyTorch trainer is removed. Experiment parameters,
  notebook code, and numerical-helper fingerprints invalidate stage checkpoints.
  CUDA training first attempts a bounded segment cache in VRAM, retaining
  float32 normalized signals and boolean masks once per covered segment span.
  Windows are assembled on the consumer's CUDA stream. Partitions that do not fit
  fall back to a bounded RAM window cache, then streaming. Cache preparation
  preserves seeded batch order and uses the existing training-only normalizer. See the
  [timing check](reports/training-input-cache-2026-11-12.md) for measured scope.
  The training notebook exports checkpoints to ONNX with normalizer sidecars and
  verifies CPU-runtime logits against PyTorch at batch sizes 1 and 2. ONNX takes
  prepared model inputs; it does not embed signal preprocessing.
  Both 96 Hz and 120 Hz exports remain current; version-1 exports are retired.
  Notebooks must record dataset versions, split policy, and seeds. See
  [amplitude preprocessing](amplitude-preprocessing.md) and the notebook index.
- **Detection:** `fall-detect` can score four-receiver windows with exported
  experimental models. Training data comes from one participant/session, and
  continuous accuracy, false alarms per hour, and event latency are not
  qualified. Collection-phase scores are not fall probabilities. See the
  [live detector guide](live-fall-detection.md) and
  [model pilot summary](reports/fall-model-pilots.md).

## Research limits and rules

- No production signal representation, causal filter, feature set, classifier,
  or decision threshold has been selected.
- Existing model results do not establish independent-session or
  participant-level generalization. Collection cues are not measured movement
  onset times.
- Preserve raw CSI. Treat derived caches as reproducible outputs, and record
  parameters, dataset version, split definition, and random seed for each
  experiment.
- Do not claim improvement without an independent held-out evaluation. Keep
  measurements with their conditions, denominators, and limitations in
  [`docs/reports/`](reports/README.md).

## Open questions

- Does gateway performance repeat across room placements, power supplies, and
  fault conditions?
- Which signal representation and temporal filtering generalize to new
  sessions without erasing short fall-related motion?
- How should irregular timestamps and packet loss shape model windows?
- How should multiple receivers be combined while retaining receiver-specific
  quality and avoiding data leakage?
- What independent-session protocol, label alignment, model, and metrics should
  define the first fall-detection baseline?

## Package organization

`src/native/radio_core/src/low_level/` contains native transport, decoding
and recording machinery. The Rust workspace has separate `radio_signal` and
`radio_preprocessing` crates for numeric kernels and signal preprocessing;
the extension crate composes them with detector preprocessing. Python domain
and query code sits
between those native operations and application workflows.

`src/fall_detection/apps/` contains the collector, CSI viewer, session
inspector, and detector application entry points and presentation code.
`radio/`, `storage/`, `analysis/`, `collection/`, `session_inspector/`,
`detection/`, and `contracts/` contain the reusable radio, data, and domain
components used by these applications and research tools. The viewer and
collector share the dashboard in `presentation/radio/`.

## Sources of truth

| Subject | Source |
| --- | --- |
| Project commands and status | [`README.md`](../README.md) |
| Repository and notebook layout | [`notebooks/README.md`](../notebooks/README.md) |
| Collection protocols | [`configs/collection/`](../configs/collection/README.md) |
| Operational radio settings | [`configs/radio.json`](../configs/radio.json), `src/fall_detection/radio/settings.py` |
| Session/archive format | [`dataset-format.md`](dataset-format.md), [`session-archive-pilot.md`](session-archive-pilot.md) |
| Acquisition and radio processing | `src/fall_detection/radio/` and `src/native/radio_core/` |
| Experiment procedures | `notebooks/latest/` |
| Shared analysis and data primitives | `src/fall_detection/analysis/` |
| Live applications | [`live-applications.md`](live-applications.md), [`live-fall-detection.md`](live-fall-detection.md) |
| Verified behavior | `tests/` |
| Thesis drafts | Local `draft/` directory; ignored by Git |
