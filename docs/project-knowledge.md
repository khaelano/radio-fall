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

Raw participant recordings are immutable. Derived datasets and local experiment
outputs belong under `data/`, which is Git-ignored except for directory guides.
Use the safe-prune utility to inspect eligible local cleanup candidates. See
the [data layout](../data/README.md) and [dataset format](dataset-format.md).

## Implemented

- **Collection:** the desktop collector supports protocol-driven trials,
  continuous activity segments, session resume, synchronized video, and
  automatic radio recovery. Accepted recordings are finalized before an attempt
  is accepted. See the [collector guide](../src/fall_detection/collection/README.md),
  [recovery notes](automatic-radio-recovery.md), and
  [video guide](video-recording.md).
- **Radio:** `configs/radio.json` is the shared operational settings file.
  C5 receivers send scheduled ESP-NOW batches to a C6 USB gateway; hardware
  qualification evidence and limitations are in the
  [gateway guide](espnow-gateway.md) and [dated reports](reports/README.md).
- **Storage:** closed sessions use verified ZIP64 archives. New collector
  streams are written as independent Zstandard frames and retained in version-2
  archives; readers also support version 1. The archive contract documents
  integrity checks, resume behavior, and durability limits.
- **Analysis:** the package contains integrity, phase, amplitude, session-table,
  sequence-preprocessing, and training helpers. Notebooks are exploratory and
  must record dataset versions, split policy, and seeds. See
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

## Sources of truth

| Subject | Source |
| --- | --- |
| Project commands and status | [`README.md`](../README.md) |
| Repository and notebook layout | [`notebooks/README.md`](../notebooks/README.md) |
| Collection protocols | [`configs/collection/`](../configs/collection/README.md) |
| Operational radio settings | [`configs/radio.json`](../configs/radio.json), `src/fall_detection/radio/settings.py` |
| Session/archive format | [`dataset-format.md`](dataset-format.md), [`session-archive-pilot.md`](session-archive-pilot.md) |
| Acquisition and radio processing | `src/fall_detection/radio/` and `src/native/radio_core/` |
| Analysis and preprocessing | `src/fall_detection/analysis/` |
| Live applications | [`live-applications.md`](live-applications.md), [`live-fall-detection.md`](live-fall-detection.md) |
| Verified behavior | `tests/` |
| Thesis drafts | Local `draft/` directory; ignored by Git |
