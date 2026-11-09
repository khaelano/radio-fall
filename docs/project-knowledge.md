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

## System snapshot

- Goal: detect human falls from Wi-Fi channel state information (CSI) for a
  bachelor's thesis.
- Historical CSI cohort: one ESP32-C5 transmitter and two ESP32-C5 receivers.
  New gateway transport tests use four C5 receivers and one C6 gateway; this
  does not add four-view activity recordings or detector evaluation to the
  historical cohort. ESP32-C6 supports the 2.4 GHz backhaul.
- Sensing link: ESP-NOW, 802.11ax HE20, MCS0, 20 MHz, long guard interval, and
  50–100 configured sensing rounds per second per receiver in historical
  profile schema v1; explicit 5 GHz profile v2 supports up to 120 Hz with CGCF-v6.
  Historical profiles remain at 100 Hz; normal gateway sensing uses 80 Hz.
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
  or post-switch phase stability. See `docs/espnow-hardware-probe-2026-11-01.md`.
- Incremental gateway changes: early next-grant announcement after verified
  return, unique slot-entry ACK polls and per-round pending-return notices are
  implemented. A matched 30 s warm-up/60 s single-RX pair delivered 34.28→40.47
  records/s and 472.62→52.34 ms median latency, but observed median recovery
  intervals grew 35.78→42.86 ms. Queue stability and complete timing evidence
  failed; four-RX qualification remains open. Callback-based send waiting was
  tested and reverted. See `docs/espnow-incremental-2026-11-01.md`.
- Eight-batch storage and work-dependent early return are implemented as opt-in
  CGCF-v2 trials. Host acceptance ACKs remain on 2.4 GHz. Normal policy stays at
  four batches/deadline return because early-return trials shortened median
  conservative recovery from 42.63 to 29.18–31.08 ms but delivered 46.23 then
  30.15 records/s, with median latency worsening from 53.33 to 468.86–489.86 ms.
  Rate/timing qualification remains failed; see
  `docs/espnow-window-return-2026-11-02.md` for memory, faults and evidence limits.
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
  limits are recorded in `docs/espnow-cadence-2026-11-02.md`; failed MAC sends
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
  shutdown verified. See `docs/espnow-retention-2026-11-02.md` for fault scope,
  counts, queue/timing failures and limitations; this is an experimental candidate.
- Four-receiver bring-up (2 November 2026): all four real C5s delivered through
  the C6 gateway with three receivers on power-only USB. The transmitter's old
  one-peer roster required explicit reprovisioning; the canonical live inventory
  is `configs/radio/gateway_inventory.json`. The 30 s warm-up/300 s paced-retry
  trial failed qualification at 12.85–13.00 timely records/s per receiver despite
  all delivered records arriving within one second. Thirty observed recoveries
  were after slot deadline; one grant remained unproven. No mapped overlap was
  observed, but complete timing evidence failed. Defaults were restored and
  transmitter shutdown verified. See `docs/espnow-four-receivers-2026-11-02.md`.
- Burst/ACK experiments: an opt-in event-driven worker on the USB-accessible
  rx-1 raised its rate from 13.20 to 18.53 records/s while three unchanged
  receivers stayed near 13.3. A 5 ms gateway ACK-activity window reduced MAC
  failures but did not increase throughput; combined rx-1 delivery was 15.27/s.
  All delivered records were subsecond, but no treatment met 50 records/s.
  Exact original applications and default transport policy were restored.
  Flags remain opt-in; see `docs/espnow-burst-ack-2026-11-02.md`. These results
  implicate firmware scheduling/pacing, with MAC/driver timing still a constraint.
- Larger-burst tests used only the powered rx-1, with controlled revisits to
  approximate four-receiver timing. Increasing 50 ms/300 ms window/revisit to
  125 ms/600 ms raised delivery from 18.27 to 49.53 records/s, then 49.33 in a
  60 s repeat; every delivered record was subsecond. The 50-record/s target and
  complete timing evidence remained unmet. A separate four-lane planning model
  checks grant interlocking, not RF contention or synthetic CSI. Diagnostic
  event loss appeared in longer bursts. The four-peer TX roster and original
  defaults were restored; see `docs/espnow-bulk-timing-2026-11-02.md`.
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
  `docs/espnow-ackless-2026-11-02.md`; normal collection remains acknowledged.
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
  builds passed; see `docs/espnow-throughput-2026-11-02.md`.
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
  remains unproven. See `docs/espnow-four-optimized-2026-11-02.md` and its raw
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
  `docs/espnow-four-optimized-2026-11-02.md` for raw artifacts and limits.
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
  CNN pilot is available under `notebooks/03_cnn_baseline/`; a production fall
  detector and independent-session evaluation are not implemented.

The high-level path is:

```text
transmitter -> radio channel/person -> receivers -> 2.4 GHz gateway -> USB host acquisition
            -> immutable raw session -> derived preprocessing -> offline CNN pilot
```

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

## Isolated CNN pilot

- `notebooks/03_cnn_baseline/03_cnn_experiment.ipynb` provides an executed
  walkthrough of the saved EDA, preprocessing choices, training selection, and
  test results. Run All reads saved outputs by default; an explicit switch
  reruns stages into a separate local artifact folder. The manual action mark
  anchors one fixed window per attempt; timing-shift augmentation is not yet
  implemented or evaluated.
- `notebooks/03_cnn_baseline/` contains an independent environment/lock,
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
  phase-burst mechanism; see `notebooks/03_cnn_baseline/results/pilot_v1/REPORT.md`.
- Versionable reports, plots, and metrics go to the pilot's `results/`; large
  derived arrays, checkpoints, and the CPU environment stay locally ignored
  inside the same folder. `README.md` documents commands and limits. Cue-aligned
  windows may include recovery or truncate longer actions; impact timing,
  continuous detection, and independent-session generalization remain untested.

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
  defaults were restored. See `docs/ble-c6-delivery-2026-11-01.md`.
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
  `docs/ble-c6-timing-2026-11-01.md`.
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
  `csi-radio-provision --sequential` provisions exactly one connected, verified
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
  `docs/ble-c6-quality-2026-11-01.md` for conditions, flagged records and artifacts.
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
- How should the two receivers be combined without hiding receiver-specific
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
| Isolated CNN pilot | `notebooks/03_cnn_baseline/README.md` and its `results/` |
| Collection protocols | `configs/collection/README.md` and JSON configs |
| Radio profiles and receivers | `configs/radio/` |
| Phase calibration | `src/fall_detection/radio/preprocessing/phase.py` |
| Acquisition and CSI parsing | `src/fall_detection/radio/acquisition/` |
| Synthetic transport replay and masked CNN comparison | `notebooks/trash/04_transport_simulation/README.md` |
| Verified behavior | `tests/` |
| Thesis prose | `draft/` |
