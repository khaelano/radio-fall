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

## Prior research used as baselines

Two published Wi-Fi CSI fall detectors are adapted as comparison points for
our sequence approach. Both papers used commodity 802.11n cards reporting 30
subcarriers per antenna pair, with several antennas on one card (FallDeFi
names the Intel 5300; WiFall does not name its card). Their reported results are the authors' own, measured
on their hardware and data, and are not reproduced here.

| Paper | Method | Reported by the authors |
| --- | --- | --- |
| WiFall: Wang, Wu and Ni, IEEE TMC 16(2), 2017 ([text](../resources/Papers/md/wifall-2017.md), [DOI](https://doi.org/10.1109/TMC.2016.2557792)) | Time domain: smoothed amplitude, LOF activity detection, window statistics and singular values, one-class SVM or random forest | 90 % precision with a 15 % false-alarm rate (one-class SVM) and 94 % with 13 % (random forest), averaged over three indoor scenarios |
| FallDeFi: Palipana, Rojas, Agrawal and Pesch, PACM IMWUT 1(4) 155, 2017 ([text](../resources/Papers/md/falldefi-2017.md), [DOI](https://doi.org/10.1145/3161183), [code](https://github.com/dmsp123/FallDeFi)) | Time-frequency: STFT spectrograms at 1000 Hz, power-burst events, features chosen by sequential forward selection, SVM | 93 % accuracy when trained in the test environment; close to 80 % on average after the environment changed |

- **Where they live:** code in `analysis/baselines/{wifall,falldefi}/`,
  guides in [`docs/baselines/`](baselines/), and run outputs in
  `artifacts/baselines/<name>/<run>/` (DVC). They run as modules
  (`uv run python -m fall_detection.analysis.baselines.<name>`) or through
  `notebooks/latest/04_wifall.ipynb` and `05_falldefi.ipynb`. Our adaptations
  and their smoke results are listed under [Implemented](#implemented).
- **Why adapted rather than reproduced:** the C5 receivers sample at 120 Hz
  (FallDeFi lost accuracy below 400 Hz), are four separate single-antenna
  radios with their own gain and noise, report 245 tones instead of 30, and
  each loses a 0.1 s burst about every 0.57 s. Each adaptation keeps the
  paper's structure and changes only what this hardware requires; the guides
  list every deviation.
- **Comparison with our approach:**
  `analysis/comparison.py`, the baselines' `assignment` option and
  `06_comparison.ipynb` put every approach on the attempt split of a
  `03_training` run, with validation
  attempts joining baseline training. Each approach is scored on its own unit
  (sequence window, WiFall window, FallDeFi trace) and per attempt, where an
  attempt is predicted a fall when any of its units is. This any-unit rule
  favours approaches with more units per attempt in recall and penalises them
  in false alarms. First full run (22 November, all three sessions, one
  seed-42 split of 475 attempts, 95 held out): CNN attempt F1 0.85–0.88 at
  every duration, GRU 0.68–0.71, LSTM 2 s 0.71 (4 s and 6 s training
  collapsed), FallDeFi 0.64 with an attempt false-positive rate of 0.44, and
  WiFall near zero because its gate passed under 2 % of windows
  ([report](reports/detector-comparison-2026-11-22.md)). That split is
  confounded: the equipment-ordered protocol records every fall late in the
  session with the mattress in the room, and static levels identify that block.
  Holding out a whole participant session (22 November), the sequence models
  fell to attempt balanced accuracy 0.45–0.52 (median of nine), while FallDeFi
  kept 0.68–0.71 and was the best approach in both directions
  ([generalization report](reports/generalization-2026-11-22.md)).
  `HELD_OUT_SESSION` in `03`–`06` (one dataset or a tuple) runs that holdout
  from the committed notebooks; `06` matches baseline runs to the training
  split by hash. Holding out `akmal` together with the same-day
  `continuous_non_fall` (training on `khaelano` only), FallDeFi reached 0.73
  and flagged 7 % of continuous traces (21 alarms in 1.0 h); the sequence
  models flagged 39–100 % of idle continuous time. Reversed (training on
  `akmal` and all continuous data, `KEEP_SPLIT = ()`, testing on `khaelano`),
  FallDeFi reached 0.69 and the best sequence model 0.57 (median 0.44).
- **Speed from CSI (considered 22 November, not pursued):** DeFall
  ([text](../resources/Papers/md/defall-2022.md)) and FallDar
  ([text](../resources/Papers/md/falldar-2023.md)) estimate movement speed
  from the autocorrelation of CSI magnitude. No implementation is planned.

## Implemented

- **WiFall adaptation (rewritten 22 November):** `analysis/baselines/wifall/` keeps
  WiFall's structure (smoothing, LOF activity gate on training countdowns,
  seven statistics and singular values, random forest or fall-inlier one-class
  SVM) adapted to the C5 receivers like FallDeFi: receivers judged per 2 s
  window, relative amplitude, the first principal component instead of the
  tone mean for the gate (the mean cancels motion), features pooled over
  present receivers, balanced random forest. Representations are computed at
  load time. A smoke run on the 9 November 13:15 session kept 848 windows
  (134 before) but the gate passed no held-out window and the classifiers
  alone were near chance (balanced accuracy 0.52–0.56)
  ([report](reports/wifall-smoke-2026-11-22.md)). On all sessions the gate
  passed under 2 % of held-out windows, and the features separate activity
  from idle data but not falls from sit/stand transitions (ROC AUC 0.54–0.60)
  ([generalization report](reports/generalization-2026-11-22.md)). See the
  [implementation guide](baselines/wifall.md). Session reading, gap filling,
  per-receiver checks and the grouped holdout are shared with FallDeFi
  (`analysis/baselines/_recorded_attempts.py`, `analysis/baselines/_grouped_holdout.py`).
- **FallDeFi adaptation:** `analysis/baselines/falldefi/` keeps FallDeFi's structure
  (one trace per action cue ± 1 s, STFT spectrograms, power-burst events, RBF
  SVM on duration, two spectral entropies and fractal dimension) but adapts it
  to the C5 receivers rather than reproducing the paper: receivers are judged
  and dropped per trace, amplitudes are relative, each receiver is whitened by
  its training resting spectrum before averaging, `k` is calibrated on
  training traces, and the SVM is class-balanced. On 22 November a smoke run on
  the 9 November 13:15 session (attempt holdout, 46 held-out traces) detected
  13 of 16 falls with 9 of 30 non-falls flagged; that session informed the
  design, so it is development data
  ([report](reports/falldefi-smoke-2026-11-22.md)). Across the two
  participant sessions it kept attempt balanced accuracy 0.68–0.71, with
  false-positive rates of 0.42–0.45 driven by sit/stand transitions; it scored
  79–91 % of test attempts ([generalization report](reports/generalization-2026-11-22.md)).
  Unverified: other rooms, participants and continuous monitoring. See the
  [implementation guide](baselines/falldefi.md).
- **Receiver gap schedule (measured 22 November on the 9 November 13:15
  session):** each receiver loses a 0.1 s burst about every 0.57 s (about
  18 % of samples), staggered across receivers; all four are complete only
  26 % of the time. Rules that require every receiver at once discard most
  windows ([report](reports/falldefi-smoke-2026-11-22.md#receiver-gaps-in-this-session)).

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
  holds an advisory lock on `<frames_dir>.lock` (as do `storage_convert` and
  `radio_storage convert`), so concurrent conversions of one session run one at a
  time and later callers reuse the result. It reuses tables only if they still
  match the sizes and SHA-256 hashes in `conversion.json`, hashing each written
  file once (`verified.json` remembers checked files), and rebuilds tables that
  do not. The analysis
  pipeline, phase and integrity analysis, and the session inspector read the
  tables. One Rust-era hardware session (18 November, two one-minute collector
  segments, four receivers) passed `tools/processing/check_storage_equivalence.py`
  (retired afterwards; last present at `af07916`): all 45,824 frames matched
  their CSV rows with no mismatch
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
  (`analysis/sequence/alignment.py`) remains Python and is mirrored by the
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
  On 18 November, live sessions of up to ten minutes ran on the gateway and
  recovered from gateway USB loss and companion relay power loss
  ([hardware check](automatic-radio-recovery.md#hardware-check-18-november-2026));
  35–78% of windows per session were unknown because receiver coverage,
  mainly `rx-3` and `rx-4`, fell below 70% (cause undiagnosed).
  Unverified: sustained operation and detection accuracy. Since 24 November the
  default live model is the 4 s `tonepool_tcn` bundle (burst-label positives,
  seed 45, full-data split `20261123T153725520115Z`), with unchanged
  preprocessing. Its live inputs matched the offline chain bit for bit and its
  logits matched PyTorch to 2.4e-6. WebGPU placement was checked on an NVIDIA
  GPU, not the AMD laptop. Since 26 November `tiny_tcn1-4s` (seed 45 of
  `20261126T005404382343Z`, same split and labels) is selectable but not the
  default; its live inputs matched the offline chain bit for bit, its Rust
  logits equalled ONNX Runtime exactly, and every operator ran on WebGPU on the
  NVIDIA GPU ([live tiny-TCN report](reports/live-tiny-tcn-2026-11-26.md)).
  Since 26 November `pcspec_gru-4s` (seed 45 of `20261126T104817208746Z`, same
  split and labels, signed difference) is selectable but not the default. Each
  family declares its representation and whether the Rust principal-component
  spectrum front end precedes its ONNX head. On capture C its signed-difference
  inputs matched the offline chain bit for bit, its live logits equalled ONNX
  Runtime on the same features exactly and the float64 PyTorch checkpoint to
  2.3e-6, and the front end took a median 2.29 ms per window on the CPU. The
  GRU head passed the WebGPU placement rule on the NVIDIA GPU
  ([live PC-spectrum report](reports/live-pcspec-2026-11-26.md)). The recorded
  sessions have not been replayed through the detector with it.
  Without a calibration it displays
  alarms at 0.5. `fall-detect` records ten prompted non-fall movements and sets
  each model's threshold from them. Under live conditions (250 ms hop, 70 %
  gate) on the held-out sessions, this held the attempt false-positive rate at
  0.18–0.23 with recall 0.63–0.73 when the movements were drawn at random over the
  session. Replaying the recorded sessions through the real detector (25 November)
  gave the same rates and reproduced the offline scores (median difference 1e-5), but
  movements early in a session score higher (partly because the protocol starts with walking
  transitions, partly a fall within a kind, −0.15 and −0.33 Spearman on average):
  calibrating on the first ten movements of a session gave recall 0.63 on `akmal` and 0.35 on
  `khaelano` (false-positive rate 0.15 and 0.03). Recalibrating on newer movements held
  the non-fall rate near the target, but its effect on falls cannot be judged on these sessions
  (every fall follows every non-fall). Unknown
  windows (receiver coverage) were 34 %, 12 % and 32 % of the three recordings. Falls
  were alarmed a median 2.1–2.6 s after the burst. The CPU backend's ONNX Runtime
  sessions are limited to four non-spinning threads since 25 November (0.64 cores
  instead of 20). The
  calibration has not been tried with a person. See the
  [replay report](reports/live-replay-evaluation-2026-11-25.md). The 70 % gate, which the offline evaluation does not
  use, leaves 20 of 231 (`akmal`) and 9 of 232 (`khaelano`) attempts without
  a scored window at the live hop. See the
  [live tone-pool report](reports/live-tonepool-2026-11-24.md), the
  [calibration report](reports/live-calibration-2026-11-24.md)
  and the [detector guide](live-fall-detection.md).

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
  `02_preprocess` `EXPORT_VARIANTS` write alternative signals for the same
  windows to `amplitude_sequence/<rate>hz-<variant>/`, and `03_training`
  `REPRESENTATION` selects one; only the default log1p squared difference is
  published to `artifacts/model/`. The `filtered_amplitude` variant (no
  difference transform) scored higher on the random split only through static
  levels and failed across sessions
  ([generalization report](reports/generalization-2026-11-22.md)). The
  `tone_mean_log_ratio` variant (`[time, 4, 1]`: per receiver, the mean over
  tones of the squared log-amplitude change) removed the per-tone session
  fingerprint. Across sessions it cut idle false alarms from 39–100 % to
  under 8 % of continuous windows for seven of nine models. It raised median
  window AUC on `khaelano` from 0.38 to 0.79 but lowered it on `akmal` from
  0.70 to 0.59. It did not reach FallDeFi's attempt score. The
  `03_training` model `tonepool` encodes each per-tone series with shared
  weights and pools over tones and receivers on the default input. Its 4 s
  model kept window AUC 0.76–0.82 in all four holdouts; that mostly measured
  motion against stillness. On action-cue windows (falls against posture
  transitions), every input stayed at or below about 0.70 in at least one
  direction. Its max pooling made
  it flag 9–39 % of idle continuous windows from an unseen day.
  Generalized-mean pooling (`tonepool_gem`) or the per-session
  `quiet_floor_squared_difference` input brought that below 5 % at 2 s and
  4 s. All variants stayed below FallDeFi at attempt level
  ([tone-pooling report](reports/tone-pooling-2026-11-23.md)).
  Both 96 Hz and 120 Hz exports remain current; version-1 exports are retired.
  Notebooks must record dataset versions, split policy, and seeds. See
  [amplitude preprocessing](amplitude-preprocessing.md) and the notebook index.
- **Detection:** `fall-detect` can score four-receiver windows with exported
  experimental models, trained on two participants' sessions and one hour of
  continuous non-fall data from one room. Continuous accuracy, false alarms per
  hour, and event latency are not qualified. Collection-phase scores are not fall probabilities. See the
  [live detector guide](live-fall-detection.md) and
  [model pilot summary](reports/fall-model-pilots.md).

## Research limits and rules

- No production signal representation, causal filter, feature set, classifier,
  or decision threshold has been selected.
- Scope: the detector is trained and used in one room setup; transfer between
  rooms or receiver placements is not a research goal. All current sessions
  were recorded in the same room with the same receiver positions (confirmed
  by the collector; the manifests' `location` field is empty). Session
  holdouts therefore test a new day and participant in the same room.
- Existing model results do not establish independent-session or
  participant-level generalization. Collection cues are not measured movement
  onset times.
- Random attempt splits within a session are confounded by the
  equipment-ordered protocol (all falls follow all non-falls and share the
  mattress setup) and by slow signal drift; compare approaches on held-out
  sessions ([generalization report](reports/generalization-2026-11-22.md)).
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
  sessions without erasing short fall-related motion? Neither the log1p
  squared difference nor the filtered amplitude did across the two current
  participant sessions; FallDeFi's event features did best. Averaging over
  tones transferred to `khaelano` but not to `akmal`; why the direction
  matters is unresolved. The shared-weight tone-pooled encoder detected motion
  consistently in both directions and, with generalized-mean pooling, stayed
  quiet on idle data from an unseen day. It still did not separate falls from
  posture transitions on `khaelano` (action-cue window AUC about 0.53). A
  validation-chosen threshold could not make up for that, and neither did
  weighting transition windows in training (one seed). Attempt-level burst
  features transferred in both directions: logistic regression on burst
  prominence, duration, post-burst quiet, posture displacement and receiver
  agreement reached 0.62–0.72, well below FallDeFi's SVM (0.70–0.77). A
  sudden stop did not distinguish falls in these mattress-only recordings.
  The `03_training` model `tonepool_tcn` adds dilated temporal convolutions
  (about 2.2 s) after GeM tone pooling. At 4–6 s it separated falls from
  transitions in both directions (action-cue window AUC 0.78–0.91, attempt
  AUC 0.77–0.88) and matched or exceeded FallDeFi on the same attempts.
  Over four model seeds the action-cue window AUC stayed at 0.71 or above
  (6 s: 0.80 or above), and 15 of 16 runs ranked attempts above FallDeFi.
  A threshold chosen on the training sessions drifted on a new
  session, mostly with how the person moves. Calibrating it on about ten
  known non-fall movements of the new session held the false-positive rate
  near 0.2. At that rate, the 6 s model matched FallDeFi testing on `akmal`
  and beat it testing on `khaelano` (balanced accuracy 0.74 against 0.69).
  Training on positives centred on each fall's main burst
  (`POSITIVE_LABELS = "burst"`) raised the 4 s model's attempt AUC by
  0.05–0.07 in three of four holdouts. Its calibrated recall became
  0.63–0.73 at a false-positive rate of about 0.22; at 6 s the labels gave no
  gain. A multi-lag frequency view per tone (`tonepool_tcn_lags`) helped
  only when trained on `akmal` (attempt AUC 0.88–0.90 on `khaelano`). Trained
  on `khaelano` it lost 0.17–0.21, so the 4 s burst-label `tonepool_tcn`
  stays the most consistent model.
  The fall windows reach the lying phase on the mattress, so the setup
  confound applies
  ([tone-pooling report](reports/tone-pooling-2026-11-23.md)).
  Explorations on 25–26 November (offline, no source change;
  [energy-inputs report](reports/energy-inputs-2026-11-26.md)): in
  spectrograms of the filtered amplitude, falls reach 60 Hz and 30–60 Hz
  separates them from transitions best, while the squared difference is flat
  over frequency. The signed difference keeps that structure but, as model
  input, did not beat the squared difference (7 of 16 paired runs). A causal
  quiet baseline (lowest 75 % of the last 60 s) removed level drift within a
  session but did not make thresholds portable between the participants. A
  5,345-parameter model on the mean energy over tones and receivers
  (`tiny_tcn1`) matched `tonepool_tcn` (mean attempt
  AUC 0.846 against 0.836; better testing on `akmal`, slightly worse on
  `khaelano`), so most of the separation comes from how overall motion energy
  develops over about 2 s. The tiny models are now defined in `03_training`;
  `tiny_tcn1-4s` is selectable in the live detector but not the default
  ([live tiny-TCN report](reports/live-tiny-tcn-2026-11-26.md)).
  Explorations on 26 November (offline, no source or notebook change; classes
  only in the diagnostic harnesses;
  [principal-component spectrum report](reports/pc-spectrum-2026-11-26.md)):
  projecting each receiver's 238 interior tones of the signed difference on the
  window's five leading principal components, then taking the masked STFT power
  summed over the components, raised mean attempt AUC to 0.903 with a GRU
  (`pcspec_gru`) and 0.886 with `tonepool_tcn`'s temporal convolutions (`pctcn`),
  against 0.836 (`tonepool_tcn`) and 0.846 (`tiny_tcn1`). The GRU was higher than
  `tonepool_tcn` in 15 of 16 paired runs, so most of the gain comes from the
  input. The STFT of the distance moved in component space lost it (0.654),
  because a norm rectifies the signal. Edge tone index 243 (physical +121)
  fluctuates far more than interior tones (relative change 22–23 times the
  median tone's spread) and alone forms the first component of an all-tone PCA.
  The FallDeFi and WiFall adaptations already exclude it. The per-window
  eigendecomposition has no ONNX operator. A live path (Rust computes the
  53 × 65 features, ONNX runs only the head) is a proposal in that report, not
  implemented. Emulating the live hop, gate and ten-movement calibration
  offline ([evaluation](reports/pcspec-gru-evaluation-2026-11-26.md)),
  `pcspec_gru` caught 73–90 % of falls at a false-positive rate of 0.20–0.21
  with random movements (`tonepool_tcn` 65–73 %), and 63–72 % with a session's
  first ten (`tonepool_tcn` 33–55 %). It beat FallDeFi by 0.11–0.21 attempt
  AUC on the same attempts. It raised about twice `tonepool_tcn`'s alarm
  episodes on the held-out idle hour, and walking transitions caused most of its
  false alarms. Its PCA and STFT front end is now implemented in Rust
  (`radio_signal::pc_spectrum`, Python `PcSpectrumFrontEnd`; float64 sliding
  covariance sums, a top-5 tridiagonal solver, AVX2). It matched PyTorch's
  float64 features to 9e-6 in logits and took 2.2 ms per window on one core
  (0.86 ms on four), against 5.1 ms for `tonepool_tcn` (which can run on
  WebGPU) and 0.33 ms for `tiny_tcn1`. The live detector runs it for
  `pcspec_gru-4s` (see "Native sequence detection"). Training ran cuDNN's GRU with TF32
  (PyTorch's default); saved probabilities differ from exact float32 by up to
  0.012.
- How should collection separate falls from setup, for example non-fall
  activity with the mattress in place or interleaved trial order?
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
(I/Q kernels, LTF layouts, phase calibration, the offline amplitude and
Hampel kernels, and the `pcspec` principal-component spectrum front end). The extension crate in
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
| `analysis/` | `session_frames.py` plus `preprocessing/` (shared amplitude), `sequence/` (our approach), `baselines/`, `diagnostics/` | `protocol`, `radio`, `session` |
| `apps/` | collector, CSI viewer, session inspector, detector, and `common/` shared Qt code | all of the above |

The inspector backend (frame loading, review, export, video) lives in
`apps/session_inspector/` beside its `ui/` package, where the main window is
split into concern mixins (`ui/window_*.py`). `analysis/` keeps its
private helpers (`_io`, `_cache_keys`, `_frames`) at the top level, and no
package `__init__.py` re-exports names; import from the defining module
(`tests/test_architecture.py` enforces this; only the root package sets
`__version__`).
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
