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
- Hardware: one ESP32-C5 transmitter and two ESP32-C5 receivers. ESP32-C6 is
  also supported for 2.4 GHz operation.
- Sensing link: ESP-NOW, 802.11ax HE20, MCS0, 20 MHz, long guard interval, and
  100 transmitted frames per second per receiver.
- Host transport: each receiver streams CRC-protected, COBS-framed binary
  batches over USB Serial/JTAG.
- Firmware defaults cap both roles at 80 MHz with automatic dynamic frequency
  scaling initialization. Wi-Fi stays in `WIFI_PS_NONE`; automatic light sleep
  is not enabled. Existing local `sdkconfig` files must be updated explicitly.
  Power savings and delivered-rate impact are unmeasured; see
  `src/firmware/radio/README.md` for the comparison procedure.
- Current state: acquisition, synchronized recording, live visualization,
  session inspection, and operator review are implemented. An isolated offline
  CNN pilot is available under `notebooks/03_cnn_baseline/`; a production fall
  detector and independent-session evaluation are not implemented.

The high-level path is:

```text
transmitter -> radio channel/person -> receivers -> USB -> host acquisition
            -> immutable raw session -> derived preprocessing -> offline CNN pilot
```

## Data handling

- Raw sessions live under `data/raw/sessions/<session-id>/` and must not be
  modified during review or preprocessing.
- A session pins its protocol and records events, attempts, receiver-specific
  CSI, radio timing, and USB clock synchronization data.
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
  notebook, `notebooks/01_data_exploration.ipynb`, keeps pandas aggregation and
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

- `analysis/phase_signals.py` loads one attempt/receiver using the canonical
  LTF decoder and phase masks. It maps receiver callback times to host events
  with the recorded USB affine clock fit when one boot is present; missing or
  inapplicable sync data falls back explicitly to host receive time.
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

- Section 5 of `notebooks/02_simple_eda.ipynb` reuses the shared 100 ms
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

- Section 6 of `notebooks/02_simple_eda.ipynb` retains signed 100 ms circular
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
| Dataset integrity analysis | `src/fall_detection/analysis/integrity.py` and `notebooks/01_data_exploration.ipynb` |
| Phase sanity loading and plots | `src/fall_detection/analysis/phase_signals.py` and `notebooks/01_data_exploration.ipynb` |
| Activity-phase motion comparisons | `src/fall_detection/analysis/phase_motion.py` and `notebooks/01_data_exploration.ipynb` |
| Exploratory phase bursts | `src/fall_detection/analysis/phase_bursts.py` and section 5 of `notebooks/02_simple_eda.ipynb` |
| Separate-subcarrier phase changes | `src/fall_detection/analysis/phase_motion.py` and section 6 of `notebooks/02_simple_eda.ipynb` |
| Isolated CNN pilot | `notebooks/03_cnn_baseline/README.md` and its `results/` |
| Collection protocols | `configs/collection/README.md` and JSON configs |
| Radio profiles and receivers | `configs/radio/` |
| Phase calibration | `src/fall_detection/radio/preprocessing/phase.py` |
| Acquisition and CSI parsing | `src/fall_detection/radio/acquisition/` |
| Verified behavior | `tests/` |
| Thesis prose | `draft/` |
