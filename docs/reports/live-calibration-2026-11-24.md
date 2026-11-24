# Installation calibration in the live detector, 24 November 2026

The [tone-pooling report](tone-pooling-2026-11-23.md#why-the-decision-threshold-drifts-and-an-installation-calibration)
found that a threshold chosen on the training sessions drifts on a new one, and
that about ten known non-fall movements correct it. Its figures use windows every
2 s and no coverage gate. The live detector scores every 250 ms and reports a
window as unknown when a receiver covers less than 70 % of it. This report
describes the calibration step added to `fall-detect` and tests its rule under
those two conditions. Use the
[guide](../live-fall-detection.md#installation-calibration) for operation.

## Rule

- **Movement.** The operator marks the start and end. Its score is the highest
  among the scored windows that overlap it, because any of them can alarm. For
  4 s windows this is close to the offline non-fall score, which takes every
  window of an attempt of about 15 s.
- **Unknown windows.** They are skipped. A movement with no scored window is
  rejected, not counted as a low score.
- **Separation.** After a movement the recorder waits until every overlapping
  window has been published (5.9 s for 4 s models), so no window spans two
  movements. A restarted acquisition rejects the movement.
- **Threshold.** The midpoint between the third and second highest of ten
  scores: at most 20 % of the movements alarm. It equalled the offline
  function on 19,844 random inputs.
- **Source.** Rows come from `predictions.jsonl`. The frontend poll keeps only
  the latest row per model and could miss windows.
- **Reuse.** `calibration.json` stores the bundle hashes, hop, delivery grace,
  coverage gate and source. Another bundle or setting is refused.

## Test under live conditions

`live_calibration.py` rescored every cued attempt of the two held-out sessions
(`akmal` 231, `khaelano` 232) at a 250 ms hop with the 16 burst-label runs (four
holdouts, seeds 42–45). Probabilities on the offline windows differ from the
saved ones by at most 1.1e-4. The detector's own recorder and threshold
function computed the calibration. Each value is the mean over 200 random
calibration sets and then four seeds. Rates cover the cued attempts outside the
calibration set. A fall alarms if a window centred in its action cue does (the
offline rule); an attempt without a scored window cannot alarm.

| Test | 2 s stride, no gate (as published) | 250 ms hop and gate, random 10 | 250 ms hop and gate, prompted 10 | Uncalibrated 0.5 |
| --- | --- | --- | --- | --- |
| `akmal` | 0.24 / 0.73 | 0.21 / 0.73 | 0.19 / 0.71 | 0.60 / 0.93 |
| `akmal` + continuous | 0.24 / 0.62 | 0.21 / 0.65 | 0.18 / 0.63 | 0.53 / 0.92 |
| `khaelano` | 0.22 / 0.68 | 0.21 / 0.65 | 0.22 / 0.67 | 0.24 / 0.70 |
| `khaelano`, all continuous | 0.22 / 0.69 | 0.21 / 0.68 | 0.23 / 0.70 | 0.26 / 0.74 |

Cells are attempt false-positive rate / recall, for a target of 0.2.

- **The target holds at the live hop and gate.** The false-positive rate was
  0.21 in every holdout with random movements and 0.18–0.23 with the prompted
  mix.
- **Calibrate at the live hop.** An offline threshold (2 s stride, no gate)
  used live gave 0.31 and 0.32 in the `khaelano` holdouts.
- **Uncalibrated, the detector alarms far more on `akmal`:** 0.53–0.60 of its
  non-fall movements at 0.5. The median calibrated threshold was 0.96 on
  `akmal` and 0.63–0.70 on `khaelano`, so one fixed value suits neither.
- **Idle time.** On the held-out continuous hour (`akmal` + continuous),
  calibrated thresholds gave 1.5 alarm episodes and 0.5 gave 8.3. Alarmed
  windows less than 4 s apart count as one episode.
- **One calibration is noisy.** Over the random sets of ten, the 90th
  percentile of the false-positive rate was 0.34–0.36, and the 10th
  percentile of recall was 0.34–0.55. Twenty movements narrowed the
  former to 0.28–0.31; five widened it to 0.38–0.47.

### Which movements

| Calibrated on ten of one kind | `akmal` | `akmal` + continuous | `khaelano` | `khaelano`, all continuous |
| --- | --- | --- | --- | --- |
| Sit to stand | 0.50 | 0.44 | 0.19 | 0.16 |
| Sit to walk | 0.12 | 0.13 | 0.23 | 0.26 |
| Stand to sit | 0.29 | 0.30 | 0.26 | 0.23 |
| Walk to sit | 0.20 | 0.16 | 0.20 | 0.22 |

Cells are the false-positive rate over all non-fall attempts. Stand-to-walk and
walk-to-stand had too few attempts. The kind of movement moved the rate between
0.12 and 0.50 on `akmal`. The detector therefore prompts a fixed mix: two
each of walk to sit, sit to stand, stand to sit and sit to walk, and one each of
stand to walk and walk to stand. The order forms a chain that starts and ends
standing, so no unrecorded movement is needed in between.

### Coverage gate

Coverage here is the live definition, the finite tones of the differenced
signal. The export's `receiver_coverage` is measured before differencing and is
up to 0.037 higher.

| Test | Offline windows passing | Fall windows passing | Attempts with a scored window (2 s stride / 250 ms hop) |
| --- | --- | --- | --- |
| `akmal` (both holdouts) | 65 % | 88 % | 205 / 211 of 231 |
| `khaelano` (both holdouts) | 91 % | 84 % | 219 / 223 of 232 |

On action-cue windows, failing windows separated falls from transitions as
well as passing ones on `akmal` (AUC 0.88 against 0.87; 0.84 against 0.81 with
the continuous hour), and worse on `khaelano` (0.69 against 0.80; 0.63 against
0.79). They contain 20 falls on `akmal` and 32 on `khaelano`. The gate stays at
70 %. This replaces the gate analysis in the
[live tone-pool report](live-tonepool-2026-11-24.md#coverage-gate).

## Checks

- Unit tests cover the threshold rule, the overlap rule, rejections, discarding,
  files and refusals. The full suite passed (705).
- The window was driven offscreen through a calibration of ten movements on a
  replay of capture C, with `cnn-2s` because its windows fit the 10 s capture.
  Acquisition restarts between loops rejected movements as intended. A second
  run applied the saved file, and a different hop was refused. The capture holds
  no movement, so this checks the mechanism and not the threshold.

## Limits

- The calibration has not run on radio hardware or with a person. The
  9 November sessions lack the journal events that replay needs, so their
  movements entered through recorded signals, not through live timing.
- Calibration and test attempts come from the same session and day. How long a
  calibration lasts is untested.
- The held-out sessions are two participants in one room. The mattress confound
  applies, and the published bundle itself was trained on both participants.
- The operator's marks stand in for the action cue. How precisely they must be
  set is untested.
- The 0.2 target is a chosen setting, and recall at it is 0.63–0.73.

## Files

`artifacts/notebooks/diagnostics/20261124-live-calibration/` holds
`live_calibration.py`, the dense window scores (`dense/`), `gate.csv`,
`calibration.csv` and their summaries.
