# Historical fall model pilots

These results describe exploratory, single-participant experiments. They do not
establish live fall-detection accuracy or generalization to new sessions or
participants. The original experiment notebooks and their generated result
directories have been removed from the repository; the metrics below are
retained as historical context and cannot be reproduced from this checkout
alone. Local model bundles, when present under `data/models/`, are ignored by
Git.

## Two-receiver pilot

The pilot used 154 accepted attempts from one session. It assigned complete
activity/direction scenarios to fixed train, validation, and test partitions
before applying coverage exclusions. Validation selected calibrated-phase
sine/cosine input. On 30 held-out attempts, the three-seed ensemble classified
28 correctly, with balanced accuracy 0.929, 16/16 falls detected, and 2/14
non-falls marked positive. A missingness-only control reached balanced accuracy
0.647 and ROC AUC 0.844, so acquisition-related confounding remained unresolved.

## Four-receiver amplitude pilot

The later experiment used four receiver views from one completed session and
held out whole activity/direction scenarios. Quality filtering left 128
training, 42 validation, and 36 test attempts. The selected amplitude models
classified 35/36 test attempts correctly at each of five correlated timing
offsets, with 11/12 falls and 24/24 non-falls correct (balanced accuracy
0.958). Predictions were unchanged across offsets. A collection-order control
also reached balanced accuracy 0.958 (ROC AUC 1.000); the quality-only control
reached 0.521. These results do not isolate fall motion from chronology or
equipment effects, and the test offsets are repeated measurements of the same
attempts.

## Phase-change retraining

The phase-change model used the same four-receiver cohort and scenario split.
Its 128 training attempts contributed 20 seeded random shifts plus one central
window each; validation and test used one central window per attempt. The
representation used 100 ms wrapped calibrated-phase differences, four
receivers, 242 tones, finite-value masks, and no fitted standardization. The
exported three-seed model remains an experimental scoring option. Its source
experiment was removed, so retraining and export from the original run are not
available in this checkout. See the [live detector guide](../live-fall-detection.md)
for the deployment interface and operational limits.

## Interpretation

All three pilots used data from one participant. Scenario grouping reduces
overlap between related attempts, but it does not provide independent-session
or participant validation. Collection order, equipment, cue-aligned windows,
and signal quality can still explain apparent performance. Fall labels are
experimental attempt labels rather than verified movement-onset timestamps.
The models are not production detector choices; accuracy, false alarms per
hour, and event latency remain unqualified.
