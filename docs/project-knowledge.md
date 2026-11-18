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
datasets belong under `data/` and are versioned with DVC. Notebook run history
(including checkpoints and normalizers) belongs under
`artifacts/notebooks/<notebook-name>/<run-id>/`. Latest verified ONNX bundles
belong under `artifacts/model/<model-name>/`. The two directories are versioned
independently by `artifacts/notebooks.dvc` and `artifacts/model.dvc`, with contents
excluded from Git.
CSI viewer journals default to `data/experiments/viewer/`, outside the
DVC-tracked `data/raw/`. Git ignores detector run folders
(`data/experiments/detector/native-*`); runs worth keeping are added with DVC,
as the 12 November runs are in `runs-20261112`.
Retired `data/processed/amplitude_sequence_v2/` and `_v3/` were removed from
the workspace; current exports use `amplitude_sequence/{96,120}hz/`. Historical
split tables can still reference the retired paths and require the earlier DVC
snapshot/cache for replay. Their cache was retained during cleanup.
Use the safe-prune utility to inspect eligible local cleanup candidates. See
the [data layout](../data/README.md) and [dataset format](dataset-format.md).

## Implemented

- **Reviews and archive resolution (13 November 2026):** the mutable review
  lives at `data/annotations/<session-id>/session_review.json`, tracked in Git.
  The `radio_storage` crate resolves the archive in `data/raw/sessions` (checking
  its predecessor in `data/old_raw/sessions`) together with the review and
  returns effective attempts; the analysis loader and notebooks use it through
  `fall_detection._radio_native`. The Python `fall_detection.storage` package is retired. Reviews change a derived export's identity but never `frames.parquet`.
  The session inspector opens session directories and version-3 archives
  alike. An archive is read in place; only the selected attempt's video clip is
  extracted, to `data/interim/inspector_media/`. Reviews are saved to
  `data/annotations`.
  See [storage layout specification](storage-layout-spec.md#43-resolving-a-recording-and-its-review).
- **Typed frame storage and version-3 archives (13 November 2026):** the Rust
  `radio_storage` crate converts raw journals and events into
  `data/interim/frames/<session-id>/{frames,attempts,phases}.parquet` and writes
  version-3 archives in `data/raw/sessions/` (the pre-schema-3 originals moved to `data/old_raw/sessions/`). On the three non-empty
  archives 4,527,879 CSV rows matched the tables with no mismatch, and the
  archives shrank from 11.9 GB to 6.63 GB (video unchanged). `FrameStore.ensure`
  holds an advisory lock on `<frames_dir>.lock`, so concurrent conversions of
  one session run one at a time and later callers reuse the result. The analysis
  pipeline, phase and integrity analysis, and the session inspector read the
  tables. One Rust-era hardware session (18 November, two one-minute collector
  segments, four receivers) passed `tools/processing/check_storage_equivalence.py`:
  all 45,824 frames matched their CSV rows with no mismatch
  ([status report](reports/architecture-rehaul-status-2026-11-13.md#update-18-november)).
  The collector then stopped writing the sidecars, which made up 47% of that
  session's archive; the transport journal is now the only raw radio record, and
  older sessions keep their sidecars. Journals in the
  session directory are included in the finalized archive. See the
  [specification](storage-layout-spec.md) and
  [report](reports/storage-layout-migration-2026-11-13.md).
- **Rust-owned live path (12 November 2026):** one Rust transport session
  (`radio_transport::session`) runs gateway startup, relay recovery,
  journal-before-ACK acceptance, capture mapping, availability bins,
  duplicate-capture removal and restarts for the viewer, collector and detector.
  Python apps receive accepted records and health through `NativeAcquisition`
  and only display and run the collection workflow; the viewer's own CSV
  recorder was removed, and the collector no longer writes CSV sidecars (see
  the storage entry above). The Python acquisition modules, Python detector, USB transmitter
  link and `csi-gateway-benchmark` were removed. Phase calibration and clock
  fitting have one Rust implementation; independent NumPy/Python references
  remain in tests only. ACKs now certify the native envelope journal rather
  than the CSV write. Offline sequence alignment for training
  (`analysis/preprocessing/sequence_preprocessing.py`) remains Python and is mirrored by the
  live Rust window builder, guarded by the replay parity test; moving it would
  change published preprocessing. Tested offline against a fake gateway on a
  pseudo-terminal and, on 18 November, in one two-minute four-receiver collector
  session on radio hardware; sustained operation is unverified, and the 300 s
  qualification evaluator has not been ported. See
  [native processing](rust-radio-pipeline.md) and
  [automatic recovery](automatic-radio-recovery.md).
- **Native sequence detection:** Rust owns acquisition, sequence alignment,
  preprocessing, resident ONNX Runtime sessions (WebGPU/Vulkan or CPU) and
  serial inference scheduling; `fall-detect` (Python) supplies controls through
  PyO3. Deployment is model-only: the
  current exports, their saved normalizers and the documented operational
  preprocessing settings; no training dataset is required. A replay feed
  streams recorded native captures in real time. On capture C, live inputs
  matched the offline Python chain bit for bit, and CPU and WebGPU `cnn-4s`
  scores agreed ([replay report](reports/native-replay-2026-11-12.md)).
  Recurrent models exceed the 250 ms hop on the Vega 7
  ([GPU report](reports/native-webgpu-smoke-2026-11-12.md)). Ten-second
  hardware captures are in the [capture report](reports/native-capture-2026-11-12.md).
  Unverified: live gateway operation of the full pipeline, radio-failure
  restart, sustained operation, and detection accuracy. See the
  [detector guide](live-fall-detection.md).

- **Collection:** the desktop collector supports protocol-driven trials,
  continuous activity segments, session resume, synchronized video, and
  automatic radio recovery (performed by the native session). Accepted recordings are finalized before an attempt
  is accepted. See the [collector guide](../src/fall_detection/collection/README.md),
  [recovery notes](automatic-radio-recovery.md), and
  [video guide](video-recording.md).
- **Radio:** Retired live BLE and UDP experiment acquisition code has been
  removed, along with historical BLE decoding tools. Gateway envelopes and
  CSI1 v3 records are decoded by Rust; the host accepts gateway policy
  version 7, operational inventory/profile schema 2 and the `espnow_uart`
  reference link only. `configs/radio.json` is the shared operational settings
  file and the only source of transport values: `EspnowTransportConfig` has no
  defaults for them. `CsiRecord` is the only Python record type; it wraps a Rust
  record built by decoding or from Python values, so both origins derive the
  same I/Q means, calibrated phase, and CSV line.
  C5 receivers send scheduled ESP-NOW batches to a C6 USB gateway; hardware
  qualification evidence and limitations are in the
  [gateway guide](espnow-gateway.md) and [dated reports](reports/README.md).
- **Storage:** closed sessions use verified ZIP64 archives. The collector
  finalizes version-3 archives (raw journals and manifests) into
  `data/raw/sessions/`; readers go through `fall_detection._radio_native`.
  Version-1 and version-2 originals are retained unchanged in `data/old_raw/`
  and are no longer read by Python. See the [dataset format](dataset-format.md)
  and [storage layout specification](storage-layout-spec.md) for integrity
  checks, resume behavior, and durability limits.
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

The Python-free crates are `radio_transport` (framing, CSI decoding, serial
I/O, gateway preparation and startup, clock and reference maintenance,
acceptance, journals, availability, quality counters, replay and the live
`session`), `radio_detection` (feeds, aligned history, window building, ONNX
Runtime sessions, scheduler, worker and the live coordinator) and `radio_signal`
(I/Q kernels, LTF layouts, phase calibration, and the offline amplitude and
Hampel kernels). The extension crate in
`src/native/radio_core/src/` exposes `NativeAcquisition`, `NativeDetector`,
the recording writer, record views and offline kernels to Python.
`tests/test_architecture.py` rejects Python serial I/O or retired acquisition
modules in live application code.

`src/fall_detection/` is layered; imports run from the top down, and
`tests/test_architecture.py` enforces the order:

| Package | Role | May import |
| --- | --- | --- |
| `protocol/` | planned trials and scenarios (model, loader) | none |
| `radio/` | settings, profiles, live delivery, records, buffers, provisioning, Rust-backed `phase.py` | none |
| `session/` | session manifests, directory/archive reader, schema version | `protocol` |
| `collection/` | collection controller, capture, resume, video | `protocol`, `radio`, `session` |
| `analysis/` | `session_frames.py` plus `preprocessing/`, `diagnostics/`, `training/` | `protocol`, `radio`, `session` |
| `apps/` | collector, CSI viewer, session inspector, detector, and `common/` shared Qt code | all of the above |

The inspector backend (frame loading, review, export, video) lives in
`apps/session_inspector/` beside its `ui/` package, where the main window is
split into concern mixins (`ui/window_*.py`). `analysis/` keeps its
private helpers (`_io`, `_cache_keys`, `_frames`) at the top level, and no
package `__init__.py` re-exports names; import from the defining module.
Core dependencies exclude pandas and zstandard, which come with the `analysis`
extra. The grant-timing model is a tool (`tools/radio/grant_timing.py`), not a
package module.

## Sources of truth

| Subject | Source |
| --- | --- |
| Project commands and status | [`README.md`](../README.md) |
| Repository and notebook layout | [`notebooks/README.md`](../notebooks/README.md) |
| Collection protocols | [`configs/collection/`](../configs/collection/README.md) |
| Operational radio settings | [`configs/radio.json`](../configs/radio.json), `src/fall_detection/radio/settings.py` |
| Session/archive format | [`dataset-format.md`](dataset-format.md), [`session-archive-pilot.md`](archive/session-archive-pilot.md) |
| Acquisition and radio processing | `src/fall_detection/radio/` and `src/native/radio_core/` |
| Experiment procedures | `notebooks/latest/` |
| Shared analysis and data primitives | `src/fall_detection/analysis/` |
| Live applications | [`live-applications.md`](live-applications.md), [`live-fall-detection.md`](live-fall-detection.md) |
| Verified behavior | `tests/` |
| Thesis drafts | Local `draft/` directory; ignored by Git |
