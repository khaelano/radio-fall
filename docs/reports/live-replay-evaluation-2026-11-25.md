# Replaying the sessions through the live detector, 25 November 2026

This report evaluates the Rust detector end to end on the recorded sessions,
following the [calibration report](live-calibration-2026-11-24.md). The
gateway envelopes of the akmal, khaelano and continuous recordings were replayed
through the real detector (acquisition, preprocessing, scheduling, gating and logs),
and its rows were compared with the offline scores and used to measure the
attempt rates, alarms and delays.

The 4 November and 9 November sessions lack the `batch_acceptance` events that the replay feed
reads. Their `record` events hold each record's capture and availability times as
measured while recording, so `convert.py` writes the acceptance events from them and
copies the envelopes unchanged (4.6 million batches, none dropped). The detector is
the committed source with two evaluation edits (see `evaluation_build.py`): ONNX
Runtime uses two non-spinning threads per session, and a result up to 5 s later than
the product's age limit still counts. Windows, inputs and the delivery deadline are the
product's. The seeds of a holdout run as four bundle slots sharing one preprocessing.

## Replay and live scores agree

- **Completeness.** 109 pieces (cut between attempts, about 4 min each, 399 minutes)
  ran at recording speed or twice it. Speeds 1× and 2× give identical scores on two
  pieces (no score or state changed); 4× and 8× drop windows and are not used. Every piece
  published at least 96 % of its expected windows. Stale results were under 0.1 % of
  windows; no records were dropped.
- **Fidelity.** On 20 segments per session, 733 (`akmal`) and 819 (`khaelano`) live
  windows per seed were compared with the offline score of the same window: the
  median difference was at most 1.1e-5 (90th percentile at most 5e-4, worst 0.0095)
  and never on opposite sides of 0.5. Placement by capture time is uncertain by one
  sample, so each segment's best offset of at most one sample is used. Coverage was
  identical.

| Session | Windows scored | Unknown (receiver coverage) | Attempts without a scored window |
| --- | --- | --- | --- |
| `akmal` | 66 % | 34 % | 19.8 of 231 (mean over seeds) |
| `khaelano` | 88 % | 12 % | 7 of 232 |
| continuous hour | 68 % | 32 % | not applicable |

The coverage gate costs the live detector a third of the windows in two of three
recordings, as the hardware sessions of 18 November suggested. Late results cost
nothing here.

## Detection on held-out sessions

Attempt rates use the cued attempts of the offline export (231 and 232). A non-fall's score
is its highest window overlapping the cue and a fall's its highest window centred in it. Values are
means over four seeds; the model weights are the holdout models of the 24 November
report, not the deployed bundle (which trained on both participants).

| Threshold | `akmal`: FPR / recall | `khaelano`: FPR / recall |
| --- | --- | --- |
| Uncalibrated, 0.5 | 0.59 / 0.93 | 0.25 / 0.69 |
| Prompted 10, random over the session (200 sets) | 0.18 / 0.71 | 0.23 / 0.66 |
| Prompted 10, the first ten in the session | 0.15 / 0.63 | 0.03 / 0.35 |

- **Random sampling matches the simulation.** Live, the random calibration gives the same
  rates as the 24 November simulation did (0.19 / 0.71 and 0.22 / 0.67), so the live path
  reproduces the offline result.
- **Starting the calibration at the beginning of the session gives much stricter
  thresholds.** The first ten movements give thresholds of 0.95 (`akmal`) and 0.97
  (`khaelano`) (random: 0.96 and 0.62), and the recall after calibration is then 0.63 and 0.35 at
  false-positive rates of 0.15 and 0.03. Per seed the `akmal` recall is 0.39–0.89
  and the false-positive rate 0.05–0.32; `khaelano` recall is 0.30–0.46 (false-positive
  rate 0.03–0.05).
- **Why.** Early movements score higher, so the first ten set a higher threshold than a
  random ten of the same kinds. Part of this is the protocol: it starts with walking
  transitions, which score highest (the first 24 attempts are 16 walking transitions of
  24). A plain trend over time mixes that with time and looks steeper (an earlier version of
  this report quoted `khaelano` medians of 0.51 falling to 0.006, which is mostly this). Within a
  kind, the Spearman correlation of score with time is −0.15 on `akmal` and −0.33 on
  `khaelano` on average over six kinds (mean over seeds; −0.68 to +0.06 per kind,
  `drift_by_kind.csv`): falling for most kinds, for example `khaelano` sit to stand
  (median 0.13 to 0.01), and near zero for two `akmal` kinds. Offline scores show the
  same, so this is not the replay. The cause is not known (signal, participant or
  protocol order).
- **The consequence.** The 24 November figures (false-positive rate 0.18–0.23, recall
  0.63–0.71) assume the calibration movements were spread over the session. A detector
  calibrated once, at the start, was too strict later.

### Recalibrating later

`recalibrate.py` uses only the saved rows: a calibration takes the most recent non-fall
movements that satisfy the prompted mix, and each attempt uses the threshold current
at its time (means over four seeds):

| Schedule | `akmal`: FPR / recall | `khaelano`: FPR / recall | Alarms between attempts in the fall period, per hour (`akmal` / `khaelano`) |
| --- | --- | --- | --- |
| First ten, kept | 0.15 / 0.63 | 0.03 / 0.35 | 124 / 39 |
| Every 60 min | 0.17 / 0.89 | 0.20 / 0.92 | 272 / 317 |
| Every 15 min | 0.20 / 0.89 | 0.28 / 0.92 | 272 / 317 |
| Before every attempt | 0.20 / 0.89 | 0.28 / 0.92 | 272 / 317 |

- **Non-falls.** Recalibrating every 60 min held their false-positive rate at 0.17–0.20,
  near the target. More often was not better (0.28 on `khaelano`).
- **Recall is not a result here.** Every fall in these sessions follows every non-fall, so
  no non-fall movement exists near the falls. The last calibration before them gives a
  threshold of 0.865 (`akmal`) and 0.014 (`khaelano`) and catches 89 % and 92 % of the
  falls, but at those thresholds the unlabelled time between attempts in the fall period has
  2–8 times as many alarm episodes (124 to 272 and 39 to 317 per hour, including rest
  and set-up). Whether this is an improvement cannot be answered without non-fall
  movements recorded during the fall period.
- **What to do next.** Collect sessions with non-fall and fall movements interleaved,
  or make the score tolerant of the drift. Neither has been done.

## Alarms and delay

- **Delay.** From the main burst peak to the publication of the alarm, falls detected with
  the first-ten threshold alarmed after a median of 2.1–2.6 s (90th percentile
  3.2–3.7 s), over 26–77 falls per seed. The window ends 2 s after its centre and the
  detector publishes 1.2 s after that (1.19 s median for the unmodified build, single model).
- **Between attempts.** Scored windows that overlap no attempt (of any status) had
  326 and 95 alarm episodes per hour at 0.5 on the two attempt sessions (0.59 and
  1.57 scored hours), and 100 and 24 per hour at the first-ten threshold. This time is
  unlabelled (rest, set-up, the participant moving), so it is not a false-alarm rate.
- **Continuous hour.** Within the 12 exported idle segments (0.63 scored hours) there
  were 14 alarm episodes per hour at 0.5 and 2.0 per hour at 0.96; outside the
  exported segments (about 17 min of the recording, 0.22 scored hours) 16.7 and 11.1.

## CPU use of the product

One minute of the unmodified detector (CPU backend, default single model, default threads)
kept 20 of 28 cores busy although there were four inferences per second of 2.8 ms each:
ONNX Runtime's threads spin on every core. This was fixed on 25 November: a CPU session
now has at most four threads and no spinning. With capture C replayed repeatedly the
same build then used 0.64 cores on average (1.29 at most), with inference 5.3 ms and results
published 1.18 s after the window (before: 2.8 ms and 1.19 s).

## Limits

- The radio path is replayed: the recorded arrival times, gaps and losses are real, the live
  radio session, the AMD GPU (WebGPU) and the screen are not.
- The evaluation build differs from the product in threading and the 5 s longer age limit.
  The product's own timing is the separate one-minute run, on a quiet machine.
- Two participants, one room, one training seed-set; four model seeds. The mattress confound applies.
- The first-ten calibration is one realistic choice; the choice of movement times within
  a session was not compared with later recalibration.
- The continuous recording has no falls, and "between attempts" is unlabelled.

## Files

`artifacts/notebooks/diagnostics/20261125-live-replay/`: `convert.py` (journals
to replayable pieces), `evaluation_build.py`, `replay.py`, `offline.py`,
`analyze.py`, `recalibrate.py`, `drift_by_kind.py`, `runs/` (one condensed row table per
piece), and the result CSVs (`window_states`, `fidelity`, `rates`, `detail`, `recalibrate`, `drift_by_kind`). `limits.sh` caps
memory at 12 GB, no swap, low priority: the first attempt at this evaluation (24 November)
used about 16 GB for one recording and froze the shared machine.
