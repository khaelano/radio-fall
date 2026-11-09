# Project knowledge base

This file is the compact, current description of how the project works. It
records implementation facts and important decisions that are easy to lose
across code, experiments, and conversations. Detailed schemas and procedures
remain in their dedicated documents.

## How to use this file

- Treat statements under **Implemented** as descriptions of the current code.
- Treat statements under **Not implemented** and **Open questions** as pending
  work, not established project behavior.
- When code or an experimental decision makes an entry inaccurate, update this
  file in the same change. Link to the source of truth instead of copying long
  schemas, commands, or algorithms here.
- Do not record tentative conversation conclusions as facts. Add them under
  **Open questions** until code, configuration, or experimental evidence
  resolves them.

The primary research notebooks are in `notebooks/latest/`. Earlier CNN
experiments and their helpers are under `notebooks/trash/`; the separately
exported phase-change model remains the live detector's default.

## Operational configuration

- Continuous activity collection: `fall-collection --continuous` automatically
  records bounded, timed CSI segments through the existing attempt pipeline.
  Segments carry the `non_fall` activity label; collector pauses are journaled,
  and interrupted attempts are retained as invalid and retried after recovery.
  Saving introduces gaps, partial final segments remain incomplete, and video
  and long-duration hardware validation are not yet supported. See the
  [collector guide](../src/fall_detection/collection/README.md).

- Rust processing (4 November 2026): live POSIX acquisition uses native USB/
  dispatch threads and two Rayon workers for framing, CRC, decode, statistics,
  HE20 phase and CSV preparation, with runtime AVX2/scalar I/Q dispatch. The
  200 ms guard covers native raw/preparation stages; a bounded 16 MiB completed
  handoff measures Python wait separately. The 32 MiB/five-second recording
  writer also runs in Rust. Raw encodings, capture timing, finalized bins and
  firmware remain unchanged. All 571 Python/integration tests, native numeric
  tests and strict Clippy pass; an sdist-built wheel imports successfully.
  Preparation measured 18.2x faster than Python; AVX2 I/Q was 2.7x scalar Rust.
  Six minutes of four-RX GUI stress, including seven 350 ms GIL holds, had no
  buffer/framing failure, maximum native preparation 4.46 ms and zero gateway
  USB-error increase. The fixed 30 s warm-up/300 s window accepted 96.31–98.70
  records/s per RX (not driver-quality-filtered); twelve rx-4 records were late
  beyond one second, max 1.098 s. A separate 151 s recording test exercised 52
  starts/51 retries; all 39,381 saved rows across 208 CSVs matched raw-envelope
  reconstructions and timing rows. Queues drained; validation attempts stayed
  outside the participant dataset. Phone video was omitted at user request.
  See [native processing](rust-radio-pipeline.md) for ownership and evidence;
  these checks do not establish detector accuracy or fix C6 RF faults.

- Collector continuity (4 November 2026): the exact gateway USB buffer-age
  failures now invalidate the old run/attempt and enter existing automatic
  recovery; the 200 ms guard stays unchanged. `fall-collection --resume-session
  <directory>` restores the saved queue and first unresolved trial, retains
  accepted recordings, reserves prior attempt numbers and establishes fresh
  radio clocks. POSIX session locks reject concurrent writers. Collection now
  batches CSV/timing and gateway/session journals through a shared bounded
  32 MiB memory writer with a five-second background flush. Closed attempts must
  finish saving before acceptance, shutdown drains, and enabled application
  ACKs wait for file-buffer flushing; power-loss durability is not promised.
  All 559 tests pass. The real session resumed at trial 33/232 with all four
  receivers delivering; all 640 accepted files were hash-identical. Startup
  validation did not start an activity or establish extended GUI/video endurance.
  See `docs/automatic-radio-recovery.md` and `collection/resume.py`.

- Fifteen-minute room observation (4 November 2026): 30 s warm-up followed by
  a fixed 900 s headless window delivered 349,772 usable records at
  96.284–97.561/s per receiver; all delivered usable records were subsecond
  with clock uncertainty included. Stable-boot receiver capture-ID spans show
  0.499–1.743% post-capture loss, excluding uncaptured sensing and unobserved
  span edges. Expiry counter increases were 446/619/1,339/420 for rx-1 through
  rx-4. One reference `peer_timeout` recovered into a second radio run and left
  7.582 s without usable host acceptance across all receivers. This is not an
  uninterrupted qualification: causal bins cover only 891.54 s of the window.
  Gateway USB error increases were zero; maximum dequeued host wait was
  120.46 ms. MCS3, firmware and timing policies were unchanged; sensing stopped
  cleanly. GUI/video load and detector accuracy remain untested. Raw data and
  derived denominators are documented in `docs/reports/loss-15min-2026-11-04.md`.

- Room follow-up (4 November 2026): the shared live preview now rejects a cold
  record in its exact captured snapshot, closing a race where an upload arriving
  after bounded preparation caused unbudgeted phase calibration. A regression
  failed before and passes after. The C6 relay source also moves compression
  outside its queue mutex; an injected UART-admission test reproduces the old
  `queue_lock` fault and verifies ordered preservation with the correction.
  All 546 tests and both C6 builds pass. The C6 correction is **not flashed**:
  companion USB data was unavailable. MCS2/MCS3 room trials, including headless
  runs, all aborted before qualification on reference packet expiry or queue
  contention. Host queue age did not fail in those short attempts; a sustained
  host fix and PHY ranking remain unverified. Operational MCS3 and all timing/
  retention criteria remain unchanged. See `docs/reports/room-transport-2026-11-04.md`.

- `configs/radio.json` is the single radio settings file for viewer, collector,
  gateway benchmark, provisioning and transmitter control. It holds verified
  inventory, sensing profile, upload policy and stable connection paths.
  Defaults select the C6 UART relay, 120 Hz/channel-44 sensing, and the measured
  CGCF-v7 MCS3/125 ms/96-record ACK-less policy. USB reference remains an override.
- `radio/settings.py` validates the file before hardware access. Unknown fields
  are rejected. Connection paths do not enter radio/transport fingerprints;
  the existing sensing fingerprint remains `8b28a906a0fbcd1f`. Session manifests
  retain the resolved profile, inventory and transport settings.
- Obsolete radio preset JSON files were removed. Earlier dated observations
  below describe the policies used then, including their historical defaults;
  they do not select today's defaults. Raw recordings and their settings remain
  unchanged. Collection protocols/scenarios still define experiment activities
  separately. See `docs/radio-configuration.md` for edits and migration.

## System snapshot

- The live detector optionally displays 12 notebook-trained phase models for
  each receiver alongside its separate fall score. The local v1 model directory
  is used when present; `--phase-models` selects another trusted directory and
  `--no-phase-models` disables it. Labels from the 2/4/6-second CNN/LSTM/GRU/forest files are collection
  phases, not falls. A bounded background worker reuses shared normalization,
  Hampel, 80 Hz interpolation and pooling with rolling-window normalization,
  which approximates rather than reproduces whole-recording training inputs.
  A 16-second synthetic combined run produced 48 phase rows and 44 fall scores
  without overflow at 119.80/s per receiver against requested 120/s, with three
  missed producer rounds.
  Hardware throughput and live phase accuracy remain unverified. See
  [live inference](live-fall-detection.md).
- `notebooks/latest/03_training.ipynb` provides an exploratory collection-phase
  classifier comparison for CNN, LSTM, GRU and random forest across 2/4/6-second
  windows. Each model has separate settings and a training section in the
  notebook; reusable
  data indexing and loading live in `analysis/window_data.py`. An attempt-grouped split
  keeps receiver views and overlapping windows together. This one-session,
  one-participant dataset cannot measure session or participant generalization;
  phase labels are collection cues, not fall events. The 6-second training
  split contains no preparation-labeled windows. A single seed-42 run on 9
  November found 4-second GRU validation/test macro-F1 0.572/0.604; all
  6-second models predicted the majority action phase for every test window.
  These results are not fall detection or independent-session evidence.
  Preprocessing uses whole-recording scaling and centered filtering. See
  [evaluation and limitations](reports/phase-model-evaluation-2026-11-09.md).
- Exploratory amplitude windows: `analysis/windows.py` resamples to 80 Hz,
  creates 2/4/6-second windows with 50% overlap, and labels each by its center
  collection phase. Linear interpolation is limited to 25 ms gaps; unsupported
  samples remain masked. Grids and window boundaries use the attempt clock.
  These settings are exploratory, not a validated detection protocol. The
  underlying recording-wide scaling and centered Hampel filter use future data.
- `notebooks/latest/02_preprocess.ipynb` uses Polars and
  `analysis/amplitude_pipeline.py` for projected row-group reads, Rust HE20
  I/Q decoding/masking, scaling and Hampel filtering, and bounded overlapping
  atomic NPZ saves. AVX2/FMA magnitudes and AVX2 deviations dispatch at runtime;
  Rayon parallelizes numeric work. Unused phase calibration is skipped.
  All 928 outputs in `data/interim/amplitude_preprocessed_v3/` matched previous
  saved arrays exactly. Full processing took 33.00 s locally (0.95 s startup),
  versus about 1,186 s in the earlier notebook execution. Whole-recording
  scaling and centered filtering still use future samples. The shared raw
  CSV-to-Parquet cache builder retains pandas; cached preprocessing uses
  Polars. See [implementation, benchmark and limits](amplitude-preprocessing.md).
- `notebooks/latest/01_exploration.ipynb` uses a derived session Parquet export
  from `analysis/session_parquet.py`, stored under `data/interim/parquet/`.
  Attempts and cue intervals have small tables; the packet table repeats
  scenario/attempt/receiver/review identifiers and phase labels for direct
  filtering, retaining raw I/Q arrays and capture-clock provenance. The names
  preparation/action/resting map to countdown/action/recovery collection cues,
  not measured movement boundaries. Export fingerprints invalidate stale source
  or review snapshots; raw recordings remain unchanged. See the
  [Parquet export contract](dataset-format.md#derived-session-parquet-export).
  The notebook loads only packet metadata for session summaries, reuses display
  bin positions across heatmaps, and limits variance decoding to action packets.
  Its analysis and plotting helpers remain inside the notebook.
- Goal: detect human falls from Wi-Fi channel state information (CSI) for a
  bachelor's thesis.
- Historical CSI cohort: one ESP32-C5 transmitter and two ESP32-C5 receivers.
  Completed activity session `20261104T081805521126Z` adds four real C5 receiver
  views through the C6 gateway, from one participant and 232 accepted attempts.
  Its separate experiment is in `notebooks/trash/05_four_rx_cnn/`; it does not change
  the historical cohort. ESP32-C6 supports the 2.4 GHz backhaul.
- Sensing link: ESP-NOW, 802.11ax HE20, MCS0, 20 MHz, long guard interval, and
  50–100 configured sensing rounds per second per receiver in historical
  profile schema v1; explicit 5 GHz profile v2 supports up to 120 Hz with CGCF-v6.
  Historical schema-v1 profiles retain their 100 Hz maximum; current defaults use 120 Hz.
- Host transport on `codex/espnow-gateway`: live BLE is replaced by scheduled
  2.4 GHz ESP-NOW uploads from C5 receivers to a C6 USB gateway. Initial policy:
  80 Hz 5 GHz sensing, 50 ms slots, explicit return interlock, bounded queues,
  CRC-protected complete batches and processor-acceptance ACKs. Hardware
  qualification remains separate from implementation; see `docs/espnow-gateway.md`.
  Historical BLE/USB decoding, reports and replay inputs remain available.
- Hardware probe (1 November 2026): one C5 receiver delivered 33.5 valid records/s
  within one second; delivered latency p99 was 517.9 ms. The fixed rate and queue
  stability checks failed. All 444 observed recovery intervals in that probe
  were conservatively before slot expiry; this does not qualify four receivers
  or post-switch phase stability. See `docs/reports/espnow-hardware-probe-2026-11-01.md`.
- Incremental gateway changes: early next-grant announcement after verified
  return, unique slot-entry ACK polls and per-round pending-return notices are
  implemented. A matched 30 s warm-up/60 s single-RX pair delivered 34.28→40.47
  records/s and 472.62→52.34 ms median latency, but observed median recovery
  intervals grew 35.78→42.86 ms. Queue stability and complete timing evidence
  failed; four-RX qualification remains open. Callback-based send waiting was
  tested and reverted. See `docs/reports/espnow-incremental-2026-11-01.md`.
- Eight-batch storage and work-dependent early return are implemented as opt-in
  CGCF-v2 trials. Host acceptance ACKs remain on 2.4 GHz. Normal policy stays at
  four batches/deadline return because early-return trials shortened median
  conservative recovery from 42.63 to 29.18–31.08 ms but delivered 46.23 then
  30.15 records/s, with median latency worsening from 53.33 to 468.86–489.86 ms.
  Rate/timing qualification remains failed; see
  `docs/reports/espnow-window-return-2026-11-02.md` for memory, faults and evidence limits.
  After USB reconnection, the restored-default ten-second smoke completed at
  40.1 records/s, 41.31 ms median latency, stable queues and complete observed
  return evidence. Transmitter shutdown was verified; four-RX qualification
  remains pending. Receiver USB discovery required a reset despite working CSI
  delivery; its cause is unisolated, with all three identities visible afterward.
- CGCF-v3 cadence/ACK trials are implemented: per-receiver minimum revisit time,
  separate send guard, selective eight-ID ACK polling on the existing 2.4 GHz
  gateway path, and optional per-grant MAC timing summaries. A separate 100 Hz
  profile supports controlled trials. These are opt-in; the default policy,
  50 ms slots and 10 ms return reserve remain unchanged. Hardware screens and
  limits are recorded in `docs/reports/espnow-cadence-2026-11-02.md`; failed MAC sends
  reached about 88 ms, so a 5 ms send guard is not qualified.
  Single-RX screens delivered 40.00 records/s at baseline, 38.63 with 150 ms
  revisit, 32.23 with bitmap ACKs, and 36.80 with 100 Hz sensing/150 ms revisit.
  None met 50 records/s; new policies remain experimental and both C5 boards
  were restored to 80 Hz. The new-firmware default smoke delivered 40.1 records/s
  with 41.34 ms median latency; all three USB identities and transmitter radio
  shutdown were verified. Those trials did not measure four-receiver operation.
- Retention/retry experiments (2 November 2026): CGCF-v4 permits at most three
  retries; older versions retain one. The opt-in 750 ms/two-retry/150 ms ACK
  timeout policy recovered 60/60 deliberately withheld records within one second
  in a 30 s single-RX loss screen, versus 20/77 for default. Maximum delivered
  delay was 454.58 ms, with unchanged retransmitted bytes. Retention alone did
  not improve that recovery. Healthy delivery remains about 40 records/s;
  four-RX qualification is still pending. Original defaults were restored and
  shutdown verified. See `docs/reports/espnow-retention-2026-11-02.md` for fault scope,
  counts, queue/timing failures and limitations; this is an experimental candidate.
- Four-receiver bring-up (2 November 2026): all four real C5s delivered through
  the C6 gateway with three receivers on power-only USB. The transmitter's old
  one-peer roster required explicit reprovisioning; the canonical live inventory
  is now the `inventory` section of `configs/radio.json`. The 30 s warm-up/300 s paced-retry
  trial failed qualification at 12.85–13.00 timely records/s per receiver despite
  all delivered records arriving within one second. Thirty observed recoveries
  were after slot deadline; one grant remained unproven. No mapped overlap was
  observed, but complete timing evidence failed. Defaults were restored and
  transmitter shutdown verified. See `docs/reports/espnow-four-receivers-2026-11-02.md`.
- Burst/ACK experiments: an opt-in event-driven worker on the USB-accessible
  rx-1 raised its rate from 13.20 to 18.53 records/s while three unchanged
  receivers stayed near 13.3. A 5 ms gateway ACK-activity window reduced MAC
  failures but did not increase throughput; combined rx-1 delivery was 15.27/s.
  All delivered records were subsecond, but no treatment met 50 records/s.
  Exact original applications and default transport policy were restored.
  Flags remain opt-in; see `docs/reports/espnow-burst-ack-2026-11-02.md`. These results
  implicate firmware scheduling/pacing, with MAC/driver timing still a constraint.
- Larger-burst tests used only the powered rx-1, with controlled revisits to
  approximate four-receiver timing. Increasing 50 ms/300 ms window/revisit to
  125 ms/600 ms raised delivery from 18.27 to 49.53 records/s, then 49.33 in a
  60 s repeat; every delivered record was subsecond. The 50-record/s target and
  complete timing evidence remained unmet. A separate four-lane planning model
  checks grant interlocking, not RF contention or synthetic CSI. Diagnostic
  event loss appeared in longer bursts. The four-peer TX roster and original
  defaults were restored; see `docs/reports/espnow-bulk-timing-2026-11-02.md`.
- An opt-in CGCF-v5 ACK-less mode removes host acceptance ACKs, polls and
  application retries while retaining CRCs, unicast MAC feedback, bounded sender
  ownership, clock exchanges and the 5 GHz return interlock. Local completion
  is not proof of host delivery. Transmitter USB control/timing remains required.
  Paced single-RX 50 ms screens delivered 16.80/s with ACKs versus 16.87/s
  without; 125 ms windows with 600 ms revisits delivered 43.13/s versus 42.87/s
  in 60 s repeats. All delivered records were subsecond, but ACK-less queue
  growth failed. A corrected 30 s ACK-less screen reached 50.93/s versus 49.07/s
  with ACKs, but failed queue growth and complete timing evidence. There is no
  consistent demonstrated gain. Initial bring-up stalled once and recovered
  after restoration/reflash; its cause remains unidentified. Local-completion
  accounting is separate from expiry. Originals/defaults and the four-peer TX
  roster were restored, sensing stopped, and 383 tests passed. See
  `docs/reports/espnow-ackless-2026-11-02.md`; normal collection remains acknowledged.
- CGCF-v6 adds opt-in HT20 long-GI backhaul MCS0–3 and 120 Hz sensing support,
  preserving the HE20 MCS0 sensing PHY and older transport/profile contracts.
  Event-worker and fixed-160-MHz CPU overlays are available; the latter disables
  DFS while normal 80 MHz defaults remain unchanged. A bounded 128-entry
  diagnostic queue retains longer burst evidence. CGCF-v7 adds an opt-in
  96-slot record pool; old policies/defaults retain active capacity 64. Sized
  control queues keep depth 32 while reserving 180/96-byte receiver/transmitter
  payloads; the gateway retains complete 1400-byte envelopes. Net receiver heap
  increased from 42,360 to 58,344 bytes despite the larger reserved record pool.
  Benchmark reports can explicitly require 80 records/s. A paced single-RX
  30 s warm-up/300 s ACK-less trial at 120 Hz, MCS3 and fixed 160 MHz delivered
  95.77/s with every delivered record subsecond, stable queues (peak 79/96,
  growth +1) and no diagnostic loss. The ACK variant delivered 93.84/s but
  failed growth (+13). Each report retains one unproven grant; four-radio
  qualification remains open. Original applications, 80 Hz/default policy and
  four-peer TX roster were restored and sensing stopped. All 401 tests/eight
  builds passed; see `docs/reports/espnow-throughput-2026-11-02.md`.
- Subsequent deployment (2 November): rx-2, rx-3 and rx-4 now run the tested
  event-worker/fixed-160-MHz/v7 receiver image and have the full four-peer
  inventory's 120 Hz profile (`8b28a906a0fbcd1f`), verified after hardware reset.
  TX, rx-1 and the XIAO C6 were subsequently upgraded to the matching tested
  fixed-160-MHz/v7 images; TX/rx-1 have the same persistent 120 Hz profile.
  All six boards have now been upgraded in two USB batches. Original
  applications/NVS were backed up and all connected boards verified after
  reset. TX accepted the complete four-peer v7 configuration; C6 accepted
  channel 6/MCS3. Both were stopped afterward, with TX radio-off verified.
  Transport policy is applied at run startup, not by profile provisioning.
  No four-receiver run was performed; rx-2–4 were disconnected during the
  second batch. See the throughput report's deployment section for artifacts.
- Optimized four-receiver bring-up: three MCS3 attempts stopped on rx-3 boot
  changes before completing warm-up. Initial gateway receipt stayed zero;
  an MCS0 control also timed out. Resetting the identified C6 restored all four
  streams (452 records in an 8.78 s partial sensing span), then rx-3 restarted
  again. No sustained rate/latency/queue qualification is available. USB data
  access to rx-3 was requested for reset logging; supply versus firmware cause
  remains unproven. See `docs/reports/espnow-four-optimized-2026-11-02.md` and its raw
  attempt directories. Restart guards and test criteria were retained.
- Replacement-hub comparison: with all four receivers powered from a different
  hub on a phone charger adapter, the unchanged 120 Hz/MCS3/v7 ACK-less setup
  completed 30 s warm-up/300 s measurement at 98.82–98.86 valid records/s each.
  Every delivered record was subsecond (p99 about 474 ms, maximum 639.37 ms),
  queues passed (peaks 60–64/96, growth -1 to +1), and no boot changes occurred.
  Complete grant evidence showed no cross-receiver overlap; 117 individual
  return/deadline comparisons remained uncertain, none was classified late.
  All 15,000 finalized 50 Hz/900 ms-grace bins had at least three receivers.
  The sustained transport benchmark passed its explicit 80-record/s target;
  fault, phase-stability and detector qualification remain separate. This
  comparison supports investigating the previous power path but does not prove
  the old hub caused resets: boards were power-cycled and gateway boot changed
  too. TX radio-off/gateway stopped were verified. See
  `docs/reports/espnow-four-optimized-2026-11-02.md` for raw artifacts and limits.
- The connectionless BLE transmitter reference is deferred at the user's
  request (3 November 2026); active control/timing returns to USB. Its opt-in code
  bridges commands, wireless profile setup, clock exchanges and original round/
  event logs through the C6's sole USB connection, without receiver changes.
  USB pairing stores a per-pair HMAC key in NVS; bounded ARQ, persisted boot
  counters and nonce echoes retain reference integrity. Host/CLI mode is
  `--transmitter-link ble`; normal mode stays USB. CWL2 uses independent bounded
  lossless blocks and whole-frame prefix packing. Wireless profile commit/reboot/
  readback worked on the identified pair. Initial four-RX trials exhausted BLE
  buffers or expired packets; a later no-RX preflight carried 1,682 round logs
  without bridge faults. Shorter transmitter scanning improved sensing sends
  but expired the BLE stream. Periodic gateway control is implemented to cancel
  ordinary transmitter scanning during sensing; synchronization worked, but
  its first probe also expired. A 10 s minimum clock-fit baseline guards startup
  jitter. Wireless four-RX throughput remains unqualified. Backups precede the
  required 1500 KiB factory-partition transition. See
  `docs/wireless-transmitter.md` for protocol, setup and current limitations.
- A dedicated UART/ESP-NOW transmitter reference is implemented as the opt-in
  `--transmitter-link espnow_uart`. Native UART0 connects the sensing C5
  (TX11/RX12) to a separate C6 (TX16/RX17) at 921600 baud. Only that companion
  and the gateway enable the new encrypted ESP-NOW reference radio; the C5
  keeps its sensing profile and does not scan or retune for host transport.
  The gateway multiplexes the original C5 control, clock and round frames over
  its existing USB connection. Pairing, bounded ordered ARQ, explicit faults,
  boot/session checks and the existing host-control lease are implemented.
  USB discovery/recovery remains available and USB reference stays the default.
  The companion now selects its confirmed built-in antenna; reference peers
  use MCS0 and bounded 64 KiB queues. A 30 s warm-up/300 s four-receiver run
  passed the 80-record/s qualification at 97.73–98.88/s each, with every
  delivered record subsecond. All 39,786 observed sensing rounds were retained
  with no skipped rounds, boot change or log loss; UART/reference/USB errors
  were zero and the companion reference queue peaked at 1,297 bytes.
  Conservative bounds showed no cross-receiver overlap; 2,100 individual
  return/deadline comparisons remained uncertain. Host-control loss stopped
  sensing in 3.125 s; gateway reset stopped it in 1.078 s without resetting C5.
  Earlier incorrect-antenna/16 KiB trials failed; separate causal effects and
  longer unattended/room/GUI-load reliability remain unqualified. All 454 tests
  and three firmware builds pass. See `docs/uart-transmitter-relay.md`.
- USB restoration (3 November 2026): the identified transmitter and C6 gateway
  were restored to their exact pre-BLE full-flash images and original partition
  layouts. Transmitter readback verifies the four-peer 120 Hz profile
  `8b28a906a0fbcd1f` and fixed 160 MHz. All four receiver images/provisioning
  remain untouched; CSI delivery still uses the 2.4 GHz ESP-NOW gateway path.
  The experimental source, raw trials and private flash snapshots are retained.
  The 5 s warm-up/30 s restoration smoke delivered 67.90–76.43 valid records/s
  per receiver, every delivered record subsecond, with stable queues. It failed
  the 80-record/s target and classified one return after deadline; this does
  not repeat the previous sustained pass. TX radio-off/gateway shutdown were
  verified. See the wireless report's restoration notes for raw artifacts.
- USB endurance (3 November 2026): unchanged restored firmware and the four-C5
  120 Hz/MCS3/v7 ACK-less policy completed 30 s warm-up/1,800 s measurement.
  Excluding four observations with nonzero driver receive status leaves 710,274
  usable records at 98.465–98.755/s per receiver; every delivered record was
  subsecond (maximum conservative delay 792.71 ms). All queues passed, with
  sampled five-minute medians 26–28/96 and no device boot changes. Complete
  grant evidence showed no overlapping upload intervals; 31 individual return
  deadline comparisons were uncertain, none classified late. One gateway USB
  forwarding failure and increasing expiry counters prevent a loss-free claim.
  Individual one-second rates dipped to 54–58/s despite passing the average
  target. Of 90,000 finalized 50 Hz/900 ms-grace bins, none was all-missing and
  99.608% had at least three receivers; these masks describe delivered-data
  availability, not RF occupancy. Host ingestion preserves flagged CSI rather
  than rejecting it; raw data and finalized masks remain unchanged. Phone video,
  GUI rendering, fault recovery and detector accuracy were not tested. Sensing
  and gateway shutdown were verified. See
  [`espnow-endurance-2026-11-03.md`](reports/espnow-endurance-2026-11-03.md).
- Firmware defaults cap both roles at 80 MHz with automatic dynamic frequency
  scaling initialization. Transmitter power is initially capped at 44 quarter-dBm
  (11 dBm), reported after driver quantization. Its Wi-Fi radio is stopped while
  idle and after a 3 s host-control lease expires; receivers retain continuous
  capture. Automatic light sleep is not enabled. Existing local `sdkconfig`
  files and flashed binaries must be updated explicitly.
  Power savings and delivered-rate impact are unmeasured; see
  `src/firmware/radio/README.md` for operating notes.
- Current state: acquisition, synchronized recording, live visualization,
  session inspection, and operator review are implemented. An isolated offline
  CNN pilot is available under `notebooks/trash/03_cnn_baseline/`; `fall-detect` adds
  experimental live scoring with the four-receiver ensemble. A production fall
  detector and independent-session evaluation are not implemented.

The high-level path is:

```text
transmitter -> radio channel/person -> receivers -> 2.4 GHz gateway -> USB host acquisition
            -> immutable raw session -> derived preprocessing -> offline CNN pilot
```

## Collection scenarios

- The collector defaults to `configs/collection/fall_simple.json`, protocol id
  `fall-collection-simple-v2`: nine transitions, 116 four-direction conditions,
  two repetitions each (232 trials). `wd` has no end direction; `dw` has no start
  direction; `sd` has four end orientations. Seated backward falls are excluded.
- Equipment ordering groups clear floor → chair → chair and mattress → mattress.
  Chair orientations are grouped across activities; the seated-fall stage
  reverses the chair traversal to avoid a reset. Matching `wf`/`df` direction
  pairs and each condition's repetitions stay together. Block selection and
  saved snapshots preserve the ordering policy. This is setup grouping, not a
  room-geometry optimizer. The earlier eight-direction protocol remains
  available. See `configs/collection/README.md` and `collection/protocol.py`.

## Data handling

- Raw sessions live under `data/raw/sessions/<session-id>/` and must not be
  modified during review or preprocessing.
- A session pins its protocol and records events, attempts, receiver-specific
  CSI, radio timing, and transport-specific clock synchronization data.
- The same transmitted frame is retained separately for every receiver that
  heard it. Receiver rows must not be merged as duplicates.
- Ambient Wi-Fi frames can be present. Analysis of the sensing link must filter
  by transmitter MAC and, for the Wi-Fi 6 HE20 link, `sig_mode == 4`.
- Reviews are written to `session_review.json`; curated or processed outputs
  are derived artifacts rather than replacements for raw recordings.
- Exact directory layouts and column definitions are maintained in
  `docs/dataset-format.md`.

## Live transport diagnostics

- Viewer reference-overload fix (3 November 2026): transmitter USB draining
  runs independently of event processing through a bounded 256-chunk FIFO.
  Ingestion reuses a validated decoded envelope and applies metadata once;
  phase displays use cached I/Q means rather than unused raw matrices. Both
  GUIs defer plots while reference backlog exceeds 16 chunks; this does not
  relax acquisition checks. Rejected rounds retain sequence/raw-byte evidence
  and first failures remain visible. A visible Wayland viewer completed the
  unchanged 30 s warm-up/300 s benchmark at 98.207–98.673 valid records/s each,
  all delivered records subsecond (max 784.54 ms), with 39,764 contiguous
  reference rounds and host queue peak 69/256. All 431 tests passed. Gateway
  counters nevertheless recorded 167 failed USB forwards (0.255%) across the
  full run before its host reader was buffered. ACK-less delivery cannot
  recover those failed batches. See
  [`usb-reference-overload-2026-11-03.md`](reports/usb-reference-overload-2026-11-03.md)
  for controlled failures, partial fixes, timing evidence and limits.
- Gateway host buffering/grouping (3 November 2026): a dedicated USB reader
  uses 4 KiB requests / 5 ms timeout, a 256 KiB / 256-chunk FIFO, 200 ms maximum
  queued age and groups of at most four available chunks. Overflow/stale work
  fails explicitly; per-envelope storage/ACK rules and capture timestamps are
  preserved. Both GUIs defer plots for reference or gateway backlog. The first
  buffered five-minute trial had three USB forwarding failures; the bulk-read
  trial had zero across 65,256 received/forwarded envelopes. Its rate/latency
  checks passed at 98.293–98.597 usable records/s each, all delivered records
  subsecond (max 826.14 ms), but full qualification failed rx-2's +2-record
  endpoint median growth against the +1 limit. No criterion was relaxed. One
  driver-flagged CSI observation was excluded only in derived quality analysis.
  The host FIFO peaked at 45,987 bytes / 13 chunks, waited at most 194.60 ms
  and drained to zero. All 440 tests passed; shutdown was verified. See
  [`gateway-usb-buffer-2026-11-03.md`](reports/gateway-usb-buffer-2026-11-03.md).
- Viewer and collector use one shared `GatewayStatusPanel` and immutable
  `GatewayReceiverManager.diagnostics()` snapshot. Each fixed receiver row shows
  the last control-report state, host-delivered records/s in a trailing 1 s
  window, data age, queued records/capacity, expiry, combined drops and send
  errors. Rates count unique ingested records after recorder acceptance; they
  decay to zero without packets and exclude duplicate/rejected batches.
- Sensing Hz, delivered records/s, plot refresh FPS and UI FPS are separate.
  Headers expose the selected policy/PHY/slot/queue/ACK mode, reference health
  and gateway freshness. Missing firmware fields stay pending, stale reports
  retain their old counters, and receiver online status requires a control
  report less than 2.5 s old. UI freshness does not change acquisition gates.
- The report's state is not a live channel observation; data age is not capture
  latency. Sequence gaps do not establish a loss cause, and the GUI rate window
  is not qualification evidence. Native gateway journals remain authoritative
  for transport audit; legacy telemetry artifact fields are not reinterpreted.
  See `docs/espnow-gateway.md` for counter meanings.

## Live application organization

- Viewer/collector automatic recovery is implemented in `radio/live.py` and
  `radio/acquisition/recovery.py`: transient link/reboot faults close the old run,
  invalidate an active attempt immediately, reconnect with 3–30 s backoff and
  create fresh run IDs/clocks/buffers/journals. Recovered attempts remain invalid
  until retry/skip. The updated C6s recover ended relay epochs; the C5 clears UART
  faults only when idle. Profiles, keys and buffer/expiry guards are unchanged.
  Controlled C5/companion/gateway restarts restored all four receivers in
  9.113–11.620 s including reception verification; a 12 s C5 application outage
  recovered in 20.241 s. Electrical power removal and camera recovery remain
  unqualified. Benchmarks remain strict single-run checks. See
  `docs/automatic-radio-recovery.md` for scope, artifacts and failure limits.
- `radio/live.py` owns common settings/binding, receiver buffers and session radio
  snapshots. `visualization/live.py` shares plots and four-Hz diagnostics;
  `visualization/pacing.py` defines display pacing for both applications.
- Collection startup is composed in `collection/app.py`; `collection/views/`
  contains the windows and `collection/runtime.py` owns presentation ticks and
  run cleanup. Cleanup is registered before input startup and runs on failed
  startup or UI exit. Operator-window closure also ends performer guidance.
- Collector startup opens a scenario-protocol JSON picker before radio/camera
  initialization. The existing loader validates the chosen file; invalid input
  can be corrected and cancellation exits without creating a session. Explicit
  `--protocol <file>` bypasses the picker. Session setup shows the selected
  protocol title and retains per-block selection; saved protocol identity/hash
  and manifest resolution are unchanged. See `collection/views/dialogs.py`.
- Radio/video health is checked each display tick; unchanged health is not
  republished. Filesystem readiness is sampled once per second. Actual write
  failures remain authoritative. The preview cache holds one snapshot/frame,
  invalidated by receiver, append counter, window and phase mode; it does not
  change raw recordings, clock mapping or preprocessing.
- Viewer and collector share a **CSI gaps** tab with all receivers as rows and
  synchronized capture-time bins as columns. `visualization/gaps.py` reads a
  bounded ten-second count snapshot from the existing availability grid:
  green received by deadline, red empty after deadline, amber still pending,
  gray before the run/no timing. Bin width/grace follow radio settings (currently
  20/900 ms). Late packets do not backfill finalized bins; gaps include scheduled
  capture/upload pauses and are not packet-loss estimates. The active tab updates
  at four Hz without CSI/phase decoding, respects preview backlog deferral and
  follows replacement grids after recovery. Offline tests cover these rules;
  live hardware load is unmeasured. See `docs/live-applications.md`.
- An offscreen synthetic unchanged-data/control-refresh comparison measured
  20.50→5.59 ms median across 80 refreshes. This excludes painting/acquisition
  and does not establish live hardware throughput. Complete GUI entry points,
  failure cleanup, cache invalidation and health responsiveness have offline
  tests. See `docs/live-applications.md` for ownership, benchmark and limits.

- Live preview backlog correction (3 November 2026): a real viewer reproduced
  the 200 ms USB-age failure after 5.60 s; a cold 360-record phase window alone
  took about 210 ms. Wireless pending-envelope ingestion now reuses validated
  decoding. LTF scalar NumPy calls became array operations with the same masks.
  The dashboard warms at most 16 fresh records / about 8 ms per tick, clears old
  receiver traces during switching, and yields at 25 ms queued age or >8 chunks.
  The 200 ms failure limit and raw/ACK contracts remain unchanged. POSIX native
  USB reads now use a bounded process handoff to isolate them from Qt/GIL pauses;
  control writes stay in the parent. A 150 ms parent-GIL test verifies independent
  draining and preserved timestamps. Longer testing separated gateway USB write
  stalls from channel-6 RF peer timeouts. The default backhaul and C6 pairing
  now use channel 11. A five-minute visible receiver/tab-switching run accepted
  114,990 timely records with zero new USB errors, relay drops or UART errors;
  maximum queue wait was 109.80 ms. A separate collector preview minute passed
  with no activity attempts; all 507 tests passed. Sensing was stopped and the
  paired relay ready afterward. This is GUI stability evidence, not the
  separate throughput/camera qualification. Details and failed
  intermediate runs: `docs/reports/gateway-preview-backlog-2026-11-03.md`.

- Receiver-retention diagnosis (3 November 2026): queue-event/envelope joins
  show expiry includes already delivered receiver-side copies (1,616 observed
  records in the earlier viewer soak; 2,156 in the newer collection run, versus
  70 observed unsent expiries). Median upload revisits are ~567 ms; built batches
  submit in ~0.29 ms median. A native regression reproduces an ACK-less ownership
  race: completion between loop-entry cleanup and upload admission lets the next
  send replace an unreaped owner. Admission now reaps and requires a clear owner.
  The 96-record/750 ms policy is unchanged. All 509 tests and the C5 receiver build
  pass. App-only deployment to rx-2 preserved its NVS/profile; matched 60 s probes
  reduced its expiry increase from 154 to zero at similar record counts, while
  three unchanged controls still increased by 74–144. All four receivers have
  now been backed up, updated app-only and verified with the same corrected
  image/profile. The first combined run had zero owned-copy expiries over
  312.76 s; rx-4's eight unsent expiries occurred during warm-up after slow MAC
  completions. That run and a 43.67 s repeat aborted on a separate C6 reference
  `peer_timeout`. After coordinated C6 reset, a full 30 s warm-up/300 s monitored
  repeat passed the fixed 80-record/s transport target: 118,614 records,
  98.797–98.887/s per receiver, all subsecond, with zero new receiver expiries,
  drops, send errors, USB/UART errors or relay drops. Sensing stopped and both
  relay endpoints were ready afterward. Both C6s used laptop USB power and the
  companion was polled every two seconds; the earlier timeout cause and prior
  power-path reliability remain unisolated. Individual return/deadline bounds
  remained uncertain despite complete observed grant evidence without overlap.
  Exact batch-slot occupancy cannot be inferred from potentially lost radio
  diagnostics. See `docs/reports/receiver-expiry-2026-11-03.md` for evidence and limits.

## Optional collection video

- Recorded playback (5 November 2026): the inspector's Signals tab now places
  video beside CSI, with play/pause, scrubbing, actual-frame stepping and linked
  plot cursors. `session_inspector/video.py` validates frame host clocks/PTS and
  decodes in a dedicated thread with latest-only requests/results and a bounded
  RGB preview. Attempt changes invalidate old results; receiver changes keep
  the video position. CSI-only sessions work without PyAV.
- Inspector plots use saved gateway/BLE capture clocks or USB affine clock
  fits relative to attempt start. Receipt-only timing is explicitly labeled;
  unavailable/invalid alignment retains the receiver-relative plots without
  video cursors. Only derived views are sorted; exact table/raw order is kept.
  Heatmap display cells preserve temporal gaps. Playback preserves the initial
  frame offset and gaps; frame age is displayed. It is host-observation sync,
  not measured exposure-level sync. See `docs/video-recording.md` for operation.
- A read-only real-recording check opened the 471-frame `001/02` clip in
  session `20261104T081805521126Z` with all four receiver plots and shared
  cursors; all 12 checked raw files were hash-identical afterward. Local
  evidence is under `data/experiments/session_inspector/video-smoke/`.
- All 608 repository tests pass, including saved-video codec/gap/seek checks,
  gateway and USB time alignment, missing/corrupt timing, linked plot cursors,
  and stale-worker/shutdown behavior. These are offline checks; no collector
  timing, radio policy, training artifacts or raw recordings were changed.
- The inspector explicitly closes the plot canvas while Qt is alive. An
  isolated GUI test previously passed its assertions then crashed during
  interpreter teardown; the native process-exit regression now repeats that
  lifecycle in six child processes. Three reruns of the original inspector
  suite and the full suite exit cleanly after the cleanup correction.

- The collector accepts an explicit `--video-device` V4L2 source from DroidCam's
  external USB client. The optional `video` extra adds PyAV; recording does not
  load an inference model. CSI-only operation and radio firmware are unchanged.
- A separate process writes one H.264 MP4, frame timing CSV and video status
  sidecar per attempt across countdown/action/recovery. Host monotonic frame
  observations share the CSI reference timeline; original source PTS are kept
  separately. Phone exposure time and pipeline latency remain unknown. Variable
  presentation timestamps preserve observed gaps. A bounded 100 ms/32-frame
  holdback lets start/end markers trim attempt boundaries.
- Enabled video participates in readiness/active-attempt health checks. Empty,
  failed or unfinalized clips cannot be accepted. Retries retain separate raw
  files, and camera shutdown is bounded. Schema 2 gains optional video sidecars;
  the historical camera comparator is not restored. See `docs/video-recording.md`
  and `docs/dataset-format.md` for operation and fields.
- The operator's optional camera viewfinder reuses that process's capture stream
  during warm-up, attempts and review. It displays aspect-preserving RGB images
  below the CSI plots through a resizable divider. One shared-memory slot holds
  only the latest image, bounded to 480×270 and ten updates/s; both sides skip a
  busy slot. Lost camera health clears the image. This does not change recording
  resolution/timing or the CSI-only layout. See `collection/views/camera.py` and
  `collection/video.py`; live camera/radio load remains unqualified.
- Codec/timestamp, boundary, retry, failure and shutdown behavior are tested
  without physical camera access. The intended phone was disconnected during
  implementation. DroidCam USB operation, concurrent radio throughput and
  exposure-to-CSI alignment accuracy remain unmeasured on that hardware.

## Dataset integrity analysis

- `fall_detection.analysis.analyze_session()` and `analyze_latest_session()`
  return session, attempt, receiver, and reconstructed-phase tables. The EDA
  notebook, `notebooks/trash/01_data_exploration.ipynb`, keeps pandas aggregation and
  quality filters explicit while the shared module handles file processing.
- CSI scans use bounded NumPy batches and the cached physical-slot masks in
  `radio/preprocessing/phase.py`; optional worker processes scan independent
  receiver recordings. The notebook stores derived JSON summaries under
  `data/interim/integrity/`. Source file metadata, analysis code, radio settings,
  and phase intervals invalidate stale entries. Active sessions bypass caching.
- Sequence loss estimates cover only gaps between received packets within an
  attempt. Phase packet counts use host receive time and therefore include USB
  buffering latency. These diagnostics do not establish model trainability or
  define acceptance thresholds. See `src/fall_detection/analysis/integrity.py`.

## Phase signal sanity

- Gateway timing sidecars use the same capture-time alignment discipline as BLE;
  unavailable alignment never falls back to gateway USB arrival time.
- `analysis/phase_signals.py` loads one attempt/receiver using the canonical
  LTF decoder and phase masks. BLE recordings use their mapped enqueue-time
  sidecar and refuse an arrival-time fallback. USB recordings map receiver
  callback times through the recorded affine fit; missing or inapplicable USB
  sync data falls back explicitly to host receive time.
- The EDA notebook plots raw phase, calibrated phase, change from a circular
  baseline over the first second of countdown, a subcarrier/time heatmap,
  a median absolute circular phase-change score at a 100 ms lag, and the
  removed slope/offset. Parameters and calculations remain visible in the
  notebook; these are diagnostic representations, with no temporal filtering
  or resampling. Figures are exported under `docs/figures/phase-sanity/`.
- The default pair is the first eligible accepted `walk_to_fall` and
  `walk_to_sit` attempt, excluding bad/excluded reviews. This selection does
  not use observed phase disturbance. Plotting requires the `analysis` extra.

## Comparing activity phases

- `analysis/phase_motion.py` provides the shared circular phase-motion score
  and loads packet-level measurements across selected attempt/receiver pairs.
  The notebook compares all eligible accepted attempts, with explicit labels
  for the three fall and three non-fall activity families.
- Phase comparisons exclude lag windows crossing a phase boundary. Missing
  scores remain missing. The default pilot coverage rule requires 20 valid
  scores in each phase and retains the same attempt/receiver pairs across
  countdown, action, and recovery; this is not a training acceptance threshold.
- The notebook shows ECDFs with equal weight per attempt, per-attempt medians
  and action 90th percentiles, activity counts, and paired action-minus-static
  contrasts. Receivers remain separate. These are descriptive results from one
  session, not independent samples or evidence of held-out discrimination.
- Derived score caches and CSV summaries live in `data/interim/phase-motion/`;
  cache keys cover raw CSI/timing/sync metadata, phase intervals, code, and
  parameters. Figures are exported to `docs/figures/activity-phases/`.

## Exploratory phase bursts

- Section 5 of `notebooks/trash/02_simple_eda.ipynb` reuses the shared 100 ms
  phase-motion loader for all usable attempts with complete phase events. It
  shows cue-aligned traces and per-attempt measurements separately for raw and
  calibrated phase and each receiver. Sections 0–4 retain their direct-file
  overview and illustrative heatmaps.
- `analysis/phase_bursts.py` measures action strength, observed burst duration,
  supported active fraction, peak-burst rise time/censoring, and initial
  recovery relative to each recording's countdown. The exploratory threshold
  is the countdown 95th percentile; missing scores and gaps above 50 ms break
  runs. Durations require supported endpoints and are lower bounds, not exact
  movement durations. Unobserved rises and sparse recovery remain missing.
- The pilot usability rule requires 20 countdown/action scores and positive
  action time support. Recovery uses at least 20 scores in its first second.
  No classifier or trained fall threshold is defined. Walking comparisons
  match start/end directions, taking medians over repetitions before computing
  fall-minus-sit differences; these remain descriptive within-session contrasts.
- Tables, coverage/read diagnostics, source-metadata fingerprint, code hashes,
  and parameters are exported under `data/interim/simple-eda/<session-id>/`;
  figures go to `docs/figures/simple-eda/<session-id>/`. Raw data is preserved.

## Separate-subcarrier phase changes

- Section 6 of `notebooks/trash/02_simple_eda.ipynb` retains signed 100 ms circular
  changes as packet-by-physical-subcarrier matrices. The shared
  `analysis/phase_motion.py:phase_change_matrix()` also underlies the aggregate
  score, so both use identical lag selection and the 150 ms maximum actual lag.
  Optional phase codes mask cross-boundary pairs without combining tones.
- The notebook uses the canonical signed-frequency axis and a common finite
  mask for raw/calibrated phase. Each tone needs only its own paired values;
  there is no initial-baseline tone eligibility filter, tone reduction,
  temporal filter, or trace resampling in this representation.
- Default galleries select the first two usable repetitions per activity for
  start/end front. Start-matched `sit_to_stand` is explicitly included with its
  undefined end direction. Receiver streams and repetitions remain separate.
  Parameters allow other direction conditions; no observed signal ranks trials.
- Shared full-range plots use ±pi radians; calibrated detail uses fixed ±0.25
  radians with visible saturation fractions. Missing data and gaps above 50 ms
  remain masked. Full signed matrices are exported as float32 NPZ files with
  original times, subcarrier indices, and phase codes under
  `data/interim/simple-eda/<session-id>/subcarrier-phase-changes/`. Selection,
  read diagnostics, and parameters accompany condition-specific figures under
  `docs/figures/simple-eda/<session-id>/subcarriers/`. These are descriptive
  galleries of a chosen condition, not evidence of held-out discrimination.

## Archived two-receiver CNN pilot

- Active four-receiver experiments use the extracted helpers and pinned CPU
  environment in `notebooks/trash/shared_cnn/`. Historical selection manifests retain
  their original code paths; prepare and train again before a new evaluation.

- `notebooks/trash/03_cnn_baseline/03_cnn_experiment.ipynb` provides an executed
  walkthrough of the saved EDA, preprocessing choices, training selection, and
  test results. Run All reads saved outputs by default; an explicit switch
  reruns stages into a separate local artifact folder. The manual action mark
  anchors one fixed window per attempt; that historical pilot does not implement
  timing-shift augmentation. The separate four-receiver experiment below does.
- `notebooks/trash/03_cnn_baseline/` contains an independent environment/lock,
  configuration, EDA, preprocessing, CNN training, and evaluation scripts. Local
  snapshots of canonical decoding, clock alignment, and phase-change code have
  provenance hashes; the pilot has no runtime dependency on the repository
  Python package. Raw recordings remain an external read-only input.
- The configured cohort is the same 154 accepted usable attempts from session
  `20261026T174653764289Z`. Entire activity/direction scenarios, including
  repetitions, retakes, and both receivers, stay in one seeded partition.
  Membership freezes before label-independent coverage exclusions. This is a
  within-session/participant pilot, not the session-independent experiment
  required to select production preprocessing.
- Inputs preserve 242 valid HE20 tones and both receiver streams as channels.
  Fixed [0, 4) second action-cue windows are binned at 25 Hz without gap
  interpolation. Missing values have explicit masks. Four representations
  (log amplitude, raw phase, calibrated phase, and 100 ms calibrated phase
  change) plus a three-bin smoothing ablation are predefined. Phase components
  use sine/cosine; normalizers fit training attempts only. Both receivers must
  have at least 70% finite phase-change time/tone coverage.
- A small three-layer 2D CNN uses class-weighted BCE, AdamW, validation-loss
  early stopping, and three fixed training seeds. Validation selects one
  representation; the ensemble uses threshold 0.5. Evaluation includes
  majority, signal-summary logistic, and missingness-only logistic baselines,
  per-attempt predictions, activity errors, and scenario-cluster bootstrap
  intervals. Code, source files, splits, arrays, and checkpoints are hashed.
- The executed `pilot_v1` retains all 154 attempts (94 train, 30 validation,
  30 test). Validation selects calibrated-phase sine/cosine input. On 30 held-out
  attempts across 15 scenarios, the three-seed ensemble obtains 28/30 correct,
  balanced accuracy 0.929, 16/16 detected falls, and 2/14 false-positive non-falls.
  The missingness-only baseline obtains balanced accuracy 0.647 and ROC AUC
  0.844, so acquisition confounding remains unresolved. These are one fixed
  within-session pilot's measurements, not generalization or a confirmed
  phase-burst mechanism; see `notebooks/trash/03_cnn_baseline/results/pilot_v1/REPORT.md`.
- Versionable reports, plots, and metrics go to the pilot's `results/`; large
  derived arrays, checkpoints, and the CPU environment stay locally ignored
  inside the same folder. `README.md` documents commands and limits. Cue-aligned
  windows may include recovery or truncate longer actions; impact timing,
  continuous detection, and independent-session generalization remain untested.

## Four-receiver CNN experiment

- `notebooks/trash/05_four_rx_cnn/` reads completed session
  `20261104T081805521126Z` without modifying raw data. Its 255 attempts comprise
  232 accepted, 22 invalid and one rejected attempt across nine activities.
  Canonical gateway capture-time alignment/HE20 decoding and explicit driver
  status masking retain 242 tones, all four real receivers and missing-value
  masks. Large derived arrays/checkpoints remain locally ignored.
- Whole activity/direction scenarios are assigned before quality filtering.
  Four-second action-cue windows at 25 Hz start at offsets −0.50, −0.25, 0,
  +0.25 and +0.50 seconds. The fixed 70% phase-change coverage rule applies to
  every receiver/offset; 26 accepted attempts fail, leaving 128 training,
  42 validation and 36 test attempts. Exclusions affect 16/88 falls and
  10/144 non-falls, so scores condition on a class-dependent retained subset.
- Fixed and shift-augmented CNNs compare five predefined representations and
  three seeds with the same maximum optimizer-update budget. Augmentation
  samples one configured shift per training attempt/epoch. Scalers fit training
  data only; validation uses central windows. Test offsets are correlated
  sensitivity measurements of the same attempts. Activity/equipment/order
  confounding, uncertain impact alignment and new-participant/session
  generalization remain unresolved. See the experiment README and its report
  for completed execution results and control baselines.
- Executed `four_rx_v1`: validation selects amplitude for both schemes. Each
  three-seed ensemble scores 35/36 test attempts correctly at every offset:
  11/12 detected falls, 24/24 correct non-falls, balanced accuracy 0.958.
  Predictions do not change across offsets; augmentation adds no observed
  classification benefit here. Collection order alone also scores balanced
  accuracy 0.958 (ROC AUC 1.000), while the quality-only control scores 0.521.
  These results do not isolate fall motion from chronology/equipment effects.
  The test set is now inspected; see
  `notebooks/trash/05_four_rx_cnn/results/four_rx_v1/REPORT.md` for limits and intervals.

## Phase-change CNN with explicit random shifts

- `notebooks/trash/06_phase_shifted/` preserves the 206-attempt four-RX cohort and
  its frozen scenario split. Each of 128 training attempts has 20 distinct
  seeded random shifts within ±0.5 s plus the central window: 2,688 training
  examples, all visited each epoch. The 69 training scenarios each contribute
  at least 20 shifts. Validation/test retain 42/36 central windows; no scenario
  crosses partitions. These overlapping windows are correlated, not new trials.
- Inputs use 100 ms wrapped calibrated phase differences, actual lag at most
  150 ms, and unsmoothed sine/cosine means in 25 Hz bins. Four receivers and
  242 tones yield eight feature planes plus eight masks. Finite features stay
  in [−1, 1], with no fitted standardization, recentering or normalization layer.
  Phase calibration and the decoder's amplitude validity floor remain active.
- The same Rust builder creates training and live inputs. Integer nanoseconds
  resolve lag/bin boundaries; an exact 150 ms lag in `007/01` can be rejected by
  the older Python calculation after floating-point subtraction. Old artifacts
  remain unchanged. Independent NumPy lag/bin calculations checked all 2,766
  generated windows (max error 1.17e−10, identical masks); no random candidates
  failed coverage. All 3,947 original source hashes matched before preparation.
- Three fresh seeds retain SmallCNN with 16 input channels, AdamW and weighted
  BCE. Each seed chooses its epoch by central validation loss; the ensemble
  averages three probabilities at threshold 0.5. The previously inspected test
  split remains exploratory; new-session/live generalization is unqualified.
  Commands and measured outputs are kept with the experiment.
- Executed `phase_random20_v1`: training took 12.14 minutes; checkpoint epochs
  are 22/31/3 for seeds 17/29/43. Validation balanced accuracy is 0.807; reused
  test balanced accuracy is 0.771 (TP 8, FN 4, FP 3, TN 21). Seed 43 remains
  nearly constant (validation BA 0.500), so the three fits are not equally
  informative. The full-validity synthetic zero-change score is 0.263; this is
  not recorded standing accuracy. No live-accuracy improvement is established.
- All 598 Python tests and seven native tests pass (one timing test ignored);
  Clippy passes. Twenty-three real phase replay windows match saved tensors
  and scores exactly across scalar/SIMD and worker settings. Cached native phase
  windows measured 6.89 ms scalar/one worker and 4.13 ms AVX2/two workers median;
  these exclude packet feature preparation, disk and inference. The eight-second
  synthetic phase run produced 11 scores with zero overflow/skips; two native
  windows completed during a 350 ms GIL hold. Offscreen GUI lifecycle passed.

## Experimental live CNN scoring

- `fall-detect` is a separate GUI/headless program in
  `src/fall_detection/detection/`. A portable hash-checked bundle exports the
  selected three weights, preprocessing contract and radio identities without
  editing the research experiment. The detection extra pins CPU PyTorch 2.14.1.
  The default is now `data/models/phase_random20_v1/` (schema 2, no scaler).
  The earlier `data/models/four_rx_v1/` amplitude bundle remains available.
- `src/native/radio_core/src/detector.rs` reuses native acquisition records;
  a Rust scheduling/feature thread plus a two-worker Rayon pool builds 4 s,
  25 Hz, 242-tone amplitude or unscaled phase-change inputs every 250 ms.
  Runtime AVX2/scalar kernels handle masked bin accumulation and identity or
  saved amplitude scaling. Missing values retain masks;
  current-window phase-change support must reach 70% per receiver. A separate
  Python process runs the exact saved CNN ensemble.
- Input/history queues are bounded. Overflow, run/boot changes and radio
  interruptions invalidate all four views; stale/old-generation results and
  low-coverage data cannot become current candidates. Default window delivery
  grace is 900 ms; unavailable packets cannot backfill completed windows.
  These windows do not alter gateway availability masks or the 200 ms USB guard.
- All 588 Python tests, native numeric/window tests and strict Clippy pass.
  Twenty real replay windows match saved inputs/coverage and scores within
  documented tolerances. A cached AVX2/two-worker window measured 1.38 ms median
  versus 46.77 ms for cached NumPy binning/normalization; scopes differ from an
  end-to-end acquisition benchmark. Eight seconds of synthetic input had zero
  overflows; two native windows completed during a 350 ms GIL hold. Offscreen
  GUI startup/exit passed. Subsequent live operation and its observed failure
  are described below; continuous detection accuracy remains unqualified. See
  [live scoring](live-fall-detection.md) for commands, bounds and local evidence.
- Live failure diagnosis (4 November): run `20261104T143017Z` has 907 scored
  windows; the operator reports candidates while standing and missed falls,
  without timed activity labels. Twelve reconstructed live inputs/scores match
  Rust and NumPy exactly. Rx-4's mean standardized feature reached −6.918,
  compared with training-window values −0.431 to +0.140. Removing temporal
  variation preserved all 36 original held-out binary decisions and a live
  score of 1.0. This supports static-profile dependence and distribution shift,
  not a confirmed normalization arithmetic bug or a validated repair.
  The unscaled phase-change retraining is described above; it does not establish
  that this live failure is resolved.
  See [diagnosis](reports/live-model-diagnosis-2026-11-04.md) for ablation limits/evidence.

## Scheduled BLE transport

- `src/fall_detection/radio/ble_config.py` defines the default round-robin policy and opt-in seeded
  random experiment policy. Receiver order is fixed for each run; an ordered-MAC
  CRC binds on-air grant indices to provisioned board inventories. Radio and
  transport fingerprints remain distinct. The versioned default inventory is the
  historical two-receiver C5 cohort; use the setup's complete provisioned inventory.
  Collection requires four verified identities; development supports one to four.
- ESP32-C5/C6 firmware uses ESP-IDF 6.1 NimBLE, repeated future grants, absolute
  transmitter timer deadlines, bounded recording queues, partial transfers,
  batch ACKs, expiry and one application retry. Valid captures are retained
  during upload windows. Application windows do not reserve exclusive RF time.
  C6 and mixed C5/C6 inventories require 2.4 GHz; the 80 Hz starting profile is
  `configs/radio/profiles/indonesia_2g_ch6_80hz.json`. BLE identity reports the
  compiled target and host verification checks it against the inventory.
- The C6 test boards were identified as Seeed XIAO ESP32-C6. Board-specific
  initialization enables the RF switch and selects built-in or external antenna;
  generic boards receive no GPIO writes. The active test receiver uses its
  built-in ceramic antenna; the transmitter selects its attached external antenna.
  Both selections are recorded in status. See `common/radio_board.c` and the
  `.xiao_esp32c6` default overlays.
- Hardware smoke tests exposed inconsistent sensing metadata and BLE backlog.
  Sensing protocol v3 adds CRC32; both roles must be upgraded together. The host
  verifies v3 before collection. Notification completion wakes the worker;
  accepted-batch ACKs use write commands. Reassembly counts bounded oldest-partial
  eviction rather than allowing expired batches to block fresh transfers. Wi-Fi
  RX buffering is capped at 32. These are implementation changes, not throughput
  guarantees; measured hardware limits must remain separate from replay results.
- Explicit development timing experiments use CBLC v2 for continuous uploads,
  multi-round turns, batch size, submission pacing, and requested connection
  interval. Normal collection rejects experimental configurations; defaults and
  their fingerprints are unchanged. The NimBLE notification callback signals a
  submission attempt, not RF completion. Optional CBTM snapshots fit one read
  at MTU 247 and sample four recent batch timelines; host journals separately
  record reassembly, acceptance and ACK-write times. See
  `radio/experiments/ble_timing.py` and `docs/ble-transport.md`.
- CBLC v3 adds opt-in delivery admission (initial target 100 ms minus a 60 ms
  completion estimate), a separate 150 ms started-transfer lifetime, and an
  eight-fragment host-receipt window. The independent C ledger retains debt
  after application expiry; full CRC/recorder acceptance still gates batch ACKs.
  CBL2/CBPR scope and limits are in `docs/ble-delivery-policy.md`. Collection
  defaults stay unchanged. The queue expiry check now guards future timestamps
  and samples worker time under the queue lock.
- A five-minute pair on that revision (one RX4, four fixed slots, verified
  7.5 ms BLE) delivered 20.92 versus 21.05 records/s: no sustained throughput
  gain. Median delay fell 263.34→108.44 ms and 100 ms-grace timely delivery rose
  0.04→10.46 records/s; partial evictions fell 3,401→0. Capture fell 63.70→44.84
  records/s and p99 delay worsened 322.68→378.88 ms; causes are not isolated.
  Replay with 250 ms grace accepts 20.25 records/s, 18.08 available bins/s, for
  the candidate. The user's priority remains live detection, with delayed
  processing acceptable; neither 100 ms nor 50 Hz is a proven model requirement.
  Raw integrity passed, but 16 candidate records had driver state 65. Normal
  defaults were restored. See `docs/reports/ble-c6-delivery-2026-11-01.md`.
- Ten one-receiver hardware timing screens (5 s warm-up, 30 s measurement;
  receiver approximately 20 cm from laptop) retained four fixed slots. Baseline
  delivery was 24.20 records/s with zero timely records and 265.53 ms median
  delay; sampled capture-to-first-submission median was 228.77 ms. An 80 ms age
  limit delivered 17.17 records/s, 11.67 timely, at 97.53 ms median delay.
  Continuous uploads improved delivery but reduced capture. The 25 ms interval
  request negotiated 7.5 ms and is not a valid 25 ms comparison. Integrity checks
  found no CRC/round-metadata errors, but 33/6,980 records had driver state 65.
  A later matched 7.5 ms pair (30 s warm-up, 300 s measurement each) delivered
  20.61 records/s, 0.11 timely, at 262.24 ms median with 250 ms retention;
  80 ms retention delivered 10.56 records/s, 8.79 timely, at 88.78 ms median.
  The latter provided only 6.86 available 50 Hz bins/s. Both had no CRC/round
  mismatches, no restart and zero new send errors. Shorter retention is not a
  collection candidate. Experimental preflight now rejects unnegotiated intervals
  before sensing. Normal policy was restored and transmitter radio-off verified;
  four-link and room qualification remain untested. See
  `docs/reports/ble-c6-timing-2026-11-01.md`.
- Benchmark development mode can start with missing registered receivers while
  retaining the complete configured order and grant rotation. Missing startup IDs
  are journaled; normal collection still requires every configured receiver.
- Boot diagnostics include reset reason and uptime over provisioning USB and
  receiver BLE identity/status. No cause has been established for the reported
  power-offs; power-on after supply loss cannot establish why the supply stopped.
  Initial transmitter USB preflight found raw ROM statistics disrupting framing;
  framed statistics fixed the fault, with 40 hardware clock exchanges verified.
  See `docs/ble-transport.md` for the operating and power notes.
- USB provisioning defaults to requiring every registered board together.
  `csi-radio provision --sequential` provisions exactly one connected, verified
  board using the complete inventory; disconnected slots are preserved. Discover
  all identities first and use unchanged files for every board in a pass. A
  sequential success verifies only that board, not the rest of the system.
- `src/fall_detection/radio/acquisition/ble_reader.py` owns independent BLE clients and a USB transmitter
  reference. Additive journals preserve envelopes, rounds, counters, clock fits,
  capture/arrival/processing times and causal availability bins. Receiver loss
  leaves its stream missing; reference loss ends the run. No delivered-rate or
  four-view detector accuracy claim has been established.
- BLE attempt assignment uses mapped transmitter enqueue time, with a 300 ms
  writer drain. Per-receiver `ble_timing.jsonl` carries epochs and uncertainty.
  Canonical phase analysis validates this sidecar, sorts derived views only and
  refuses an arrival-time fallback for BLE. USB data retains its existing clock
  behavior. Bins finalize at 50 Hz with 100 ms grace and are not backfilled.
- `csi-ble-benchmark` provides measured run/report commands and a rate/scheduler
  matrix; `csi-ble-discover` reports actual GATT identities. A five-minute XIAO C6
  development test with one active receiver and four fixed grant slots delivered
  23.48 records/s from a 61.36 Hz capture counter rate, but only 2/7,044 delivered
  records met the configured input deadline (median latency 262 ms). No restart
  was observed; all measurement record identities/timestamps matched round logs.
  This does not qualify four-receiver collection. See
  `docs/reports/ble-c6-quality-2026-11-01.md` for conditions, flagged records and artifacts.
  Four simultaneous receivers, hub-powered stability, movement tests and the soak
  remain outstanding. `report --signal-quality` verifies bytes and raw-slot quality.
  Commands, defaults and wire contracts are in `docs/ble-transport.md`.

## Transport replay pilot

- `notebooks/trash/04_transport_simulation/` reuses the isolated pilot's pinned
  environment, decoder, clock mapper and small CNN. It reads raw sessions
  without modification. Four-slot cases add two virtual byte workloads, never
  extra CSI views. All BLE service and synthetic loss settings are assumptions.
- Replay distinguishes scheduled capture gaps, independent/burst loss, finite
  queues, expiry, partial service and bounded retries. Original sequence IDs,
  packet values and capture timestamps remain intact. Approximate 80 Hz input
  retains four of five source rounds with 10/20 ms spacing; uniform simulated
  upload grants avoid assigning the thinning gap repeatedly to one receiver.
  This does not emulate BLE connection anchors or measured RF coexistence.
- The same 154 pilot attempts and frozen scenario split are retained without
  post-loss quality exclusions. Four-second cue windows use 50 bins/s with
  a 100 ms delivery grace, calibrated-phase sine/cosine, finite masks, packet
  counts and sample ages. No temporal interpolation/filtering is introduced.
  Late packets cannot fill their original finalized input bins.
- Clean and missingness-trained CNNs use three training seeds, matched maximum
  update budgets, train-only normalization, validation early stopping, and
  separate training/validation/test replay seeds. Signal-summary logistic,
  missingness-only and majority baselines diagnose what the scores capture.
  The earlier pilot test set has already been inspected, so comparisons remain
  exploratory within-session attempt classification, not new-session evidence
  or a continuous detector. See its README and executed report for assumptions.
- Executed `replay_v1`: both CNN ensembles obtain 28/30 correct (balanced
  accuracy 0.929, 16/16 falls, 2/14 false-positive non-falls) in seven of eight
  conditions. Missingness training shows no extra threshold-score benefit in
  those conditions. The overloaded assumed 1.0 Mbit/s case misses many 100 ms
  deadlines and yields balanced accuracy 0.500/0.536 for clean/missingness
  training. These are synthetic, reused-split results; no minimum hardware
  throughput, four-view performance or augmentation improvement is established.

## CSI preprocessing

### Implemented

The implemented phase path is in
`src/fall_detection/radio/preprocessing/phase.py`.

1. Decode the CSI payload into its physical long-training-field (LTF) layout.
   The channel-estimate path selects HE-LTF when available, otherwise HT-LTF.
2. Preserve complex CSI. Magnitude is `abs(CSI)` and raw phase is
   `angle(CSI)` in radians.
3. Mask unusable samples as `NaN`: invalid slots, non-finite values, null or
   guard subcarriers, and samples with magnitude below `4.0`.
4. For each packet, order valid phase samples by signed physical subcarrier
   index and unwrap phase across frequency.
5. Fit a magnitude-weighted straight line to phase versus subcarrier index.
   Subtract its slope and offset, then wrap the residual to `[-pi, pi]`. This
   is the project's current meaning of **calibrated phase**.
6. For the live viewer's **phase change** mode, subtract each subcarrier's
   median calibrated phase from the oldest part of the visible window. The
   baseline duration is the smaller of 0.5 seconds and one quarter of the
   visible window; the result is wrapped to `[-pi, pi]`.

Calibration is relative, not an absolute physical phase reference. It removes
the packet-wise linear trend associated with phase offset and frequency slope.
Because it may also remove useful motion information, raw phase, calibrated
phase, and phase-change representations must be compared experimentally.

### Planned phase-calibration process

The planned offline preprocessing path will preserve the raw complex CSI and
produce each later representation as a derived artifact. Its stages are:

1. Select sensing-link packets using the expected transmitter MAC and radio
   format, then decode the physical subcarrier layout without altering the raw
   recording.
2. Calculate magnitude and wrapped raw phase from each complex CSI value. Mask
   invalid slots, null and guard subcarriers, non-finite samples, and samples
   below the recorded amplitude threshold.
3. Unwrap each packet's valid phase samples in signed physical-subcarrier
   order. This removes artificial jumps at the `-pi` and `pi` boundary; it does
   not remove radio drift.
4. Estimate a magnitude-weighted straight line across the valid subcarriers of
   each packet. Subtract its offset and slope to obtain calibrated phase, then
   wrap the residual to `[-pi, pi]`. This remains a relative measurement, not
   an estimate of absolute propagation phase.
5. Align packets to their synchronized timestamps and quantify missing or
   irregular samples. A later experiment must choose and record a resampling
   method before applying filters that assume regular spacing.
6. Remove isolated temporal spikes and reduce unwanted temporal noise. The
   denoising method, motion passband, filter order, and edge handling will be
   selected from the observed sampling rate and validation data rather than
   fixed in advance.
7. Derive motion-sensitive representations, such as wrapped change from a
   local static baseline or change between consecutive samples. Baselines must
   be computed within each trial or model window and must not use future test
   data.
8. Construct fixed model windows and retain masks or quality indicators for
   missing and rejected values. Record every preprocessing parameter with the
   derived dataset version.

The first session-independent preprocessing experiment must compare at least amplitude, raw phase,
calibrated phase, and a temporal phase-change representation under the same
session-independent split. It must also include an ablation of temporal
filtering. The project will adopt a phase representation or filter only when
held-out results show that it improves generalization without erasing the
short motion pattern associated with a fall.

### Not implemented

- No production temporal denoising filter, motion-band filter, resampling
  pipeline, windowing scheme, feature extractor, classifier, or trained model
  has been selected. The isolated CNN pilot does not establish those choices.
- The live-view baseline transformation is a visualization mode; it is not yet
  the documented input representation of a fall detector.
- No claim has been established that calibrated phase outperforms amplitude,
  raw phase, relative phase, or combined representations.

## Experimental rules

- Preserve raw complex CSI and create preprocessing outputs as derived data.
- Split data by independent session and participant where applicable; avoid
  placing closely related windows from one trial on both sides of a train/test
  split.
- Record preprocessing parameters, dataset version, split definition, and
  random seed for every reproducible experiment.
- Compare proposed preprocessing against simple baselines. Do not report an
  improvement without evaluation on held-out sessions.
- Do not invent measurements or treat a visualization as an experiment result.

## Open questions

- Gateway optimization decision (1 November 2026): prioritize small changes to
  the existing scheduling, send pacing and 2.4 GHz ACK path. Transmitter-relayed
  host ACKs over 5 GHz are a deferred, unimplemented fallback, to reconsider only
  after measured limits of smaller changes. Preserve the single-departure/return
  interlock; see `docs/espnow-gateway.md`, “Optimization direction”.
- Does the successful four-C5 120 Hz/MCS3 transport trial repeat across room
  placements, supplies and fault checks, and do replay-trained models retain
  performance on new hardware recordings and independent sessions?
- Which signal representation generalizes best: magnitude, calibrated phase,
  baseline-relative phase, another relative-phase construction, or a fusion?
- Which temporal filter and passband retain fall motion while rejecting radio
  noise at the observed sampling rate?
- How should irregular timestamps and dropped frames be handled before model
  input windows are constructed?
- How should multiple receivers be combined without hiding receiver-specific
  quality or creating data leakage?
- What window length, label alignment, features/model, and evaluation metrics
  should define the first detection baseline?

## Sources of truth

| Subject | Source |
| --- | --- |
| Project status and commands | `README.md` |
| Session and CSV format | `docs/dataset-format.md` |
| Dataset integrity analysis | `src/fall_detection/analysis/integrity.py` and `notebooks/trash/01_data_exploration.ipynb` |
| Phase sanity loading and plots | `src/fall_detection/analysis/phase_signals.py` and `notebooks/trash/01_data_exploration.ipynb` |
| Activity-phase motion comparisons | `src/fall_detection/analysis/phase_motion.py` and `notebooks/trash/01_data_exploration.ipynb` |
| Exploratory phase bursts | `src/fall_detection/analysis/phase_bursts.py` and section 5 of `notebooks/trash/02_simple_eda.ipynb` |
| Separate-subcarrier phase changes | `src/fall_detection/analysis/phase_motion.py` and section 6 of `notebooks/trash/02_simple_eda.ipynb` |
| Isolated CNN pilot | `notebooks/trash/03_cnn_baseline/README.md` and its `results/` |
| Four real receiver CNNs and shifted windows | `notebooks/trash/05_four_rx_cnn/README.md` and its `results/` |
| Unscaled phase-change CNN with 20 explicit random shifts | `notebooks/trash/06_phase_shifted/README.md` and its `results/` |
| Experimental live CNN program and native input building | `docs/live-fall-detection.md` and `src/fall_detection/detection/` |
| Collection protocols | `configs/collection/README.md` and JSON configs |
| Operational radio settings | `configs/radio.json` and `radio/settings.py` |
| Phase calibration | `src/fall_detection/radio/preprocessing/phase.py` |
| Acquisition and CSI parsing | `src/fall_detection/radio/acquisition/` |
| Synthetic transport replay and masked CNN comparison | `notebooks/trash/04_transport_simulation/README.md` |
| Verified behavior | `tests/` |
| Thesis prose | `draft/` |
