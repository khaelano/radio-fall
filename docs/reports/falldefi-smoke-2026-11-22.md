# FallDeFi smoke runs on one session, 22 November 2026

These runs checked the [FallDeFi adaptation](../falldefi.md) end to end on a
deliberately small subset on the data laptop. They are not an evaluation: one
session and 30–46 held-out traces cannot establish detection performance, and
the second run's design was informed by this same session.

## Common conditions

- Session `20261109T131546367822Z` (9 November, 13:15), protocol
  `fall-collection-simple-v2`; 246 attempts, of which 15 were not accepted or
  were excluded, leaving 231.
- Fall labels `walk_to_fall`, `sit_to_fall`, `stand_to_fall`; non-fall labels
  `sit_to_stand`, `sit_to_walk`, `stand_to_sit`, `stand_to_walk`,
  `walk_to_sit`, `walk_to_stand`.
- Traces of action cue ± 1 s; attempt holdout, test fraction 0.25, seed 42.
- Code at the working tree on top of commit `67e5039`; hashes are in each
  run's `report.json`. Outputs under `artifacts/falldefi/`, not versioned.

## Receiver gaps in this session

Over 81 attempts, each receiver lost a 0.1 s burst every 0.567 s (median gap
and interval), about 18 % of its samples; median coverage per receiver was
0.82. The 95th-percentile gap was 0.142, 0.242, 0.108 and 0.100 s for `rx-1`
to `rx-4`. Bursts are staggered across receivers: all four were complete
26 % of the time, at least three 89 %. No 64-sample STFT window was free of a
gap on any receiver, and about 30 % of 32-sample windows were.

## Run 1: close to the paper, one receiver

Settings: 30 tones, coverage 0.7, gaps up to 0.15 s interpolated, every
receiver required, raw amplitude, plain averaging, largest region, SVM
selected by accuracy without class weights. With all four receivers only 12 of
231 traces survived, so the run used `rx-4` alone, chosen for its gap profile
(not for labels or results): 118 traces (46 falls) and 165 countdown segments.

With the released code's `k = 4.3`, the 88 training traces produced one event.
In a diagnostic over 40 countdown segments that `k` gave a median threshold of
40.3, against a median 5–25 Hz resting magnitude of 5.1; the strongest frame
of a typical trace averaged about 13–14 over that band. Calibrating `k`
chose 0.3 (threshold 5.90) and gave 35 fall and 105 non-fall training events.
The grid search then selected `C = γ = 2⁻⁵` with cross-validation accuracy
0.75, the non-fall share: on 30 held-out traces it predicted no falls
(0 of 11 falls, 19 of 19 non-falls correct).

Output: `artifacts/falldefi/subset-20261109-rx4-attempt-seed42/`.

## Run 2: adapted to the receivers

Settings are the current defaults (see the [guide](../falldefi.md#pipeline)):
120 tones, coverage 0.7 and gaps up to 0.25 s judged per receiver with at
least two receivers per trace, relative amplitude, per-receiver whitening by
the resting spectrum, region ranked by 5–25 Hz magnitude, `k` calibrated to a
0.95 training detection target, balanced class weights and balanced-accuracy
selection.

182 traces and 199 countdown segments survived; 49 traces had fewer than two
usable receivers. Held-out traces used two receivers (21), three (22) or four
(3). The fitted resting floors fell across 5–25 Hz: at 24.4 Hz they were
0.33–0.47 of their 5.6 Hz value, depending on the receiver.

Calibration chose `k = 1.2`, a threshold of 1.85 times the resting floor
(median over 127 training segments; range 0.87–6.71), with events in 97.8 % of
136 training traces. Training gave 61 fall and 102 non-fall events. The grid
search selected `C = 0.5`, `γ = 64`, with cross-validation balanced accuracy
0.848.

| Held-out traces | Predicted non-fall | Predicted fall | With an event |
| --- | --- | --- | --- |
| Non-fall (30) | 21 | 9 | 28 |
| Fall (16) | 3 | 13 | 16 |

Fall recall was 0.81 (13/16; Wilson 95 % interval 0.57–0.93), specificity
0.70 (21/30; 0.52–0.83), precision 0.59 (13/22; 0.39–0.77), balanced accuracy
0.756 and F1 0.684. Ten non-fall events were classified as falls over 0.062 h
of held-out non-fall traces, 160 per hour; these cue traces are dense with
transitions, so the rate does not describe continuous monitoring.

Median features of held-out main events:

| Feature | Falls (16) | Non-falls (28) |
| --- | --- | --- |
| Event duration (s) | 1.33 | 2.40 |
| Spectral entropy 1–10 Hz (nats) | 1.31 | 1.37 |
| Spectral entropy 10–30 Hz (nats) | 2.27 | 2.11 |
| Fractal dimension | 1.17 | 1.30 |

Output: `artifacts/falldefi/subset-20261109-adapted-attempt-seed42/`.

## Interpretation and limits

The adapted pipeline kept 182 traces, against 12 when the first run required
every receiver, and produced a classifier that detects falls on this subset,
mainly through shorter fall events; the paper describes falls lasting
2–3 s. Several settings changed together, so the gain cannot be attributed to
any one of them. The hardware choices were made after inspecting this
session, which is therefore development data; the intervals above are wide,
and an attempt holdout within one session does not test new days, rooms or
participants. `γ = 64` on four min–max-scaled features may overfit.

Next: evaluate the current defaults with `--split-by session` across the
4 and 9 November sessions on the training device, add the continuous non-fall
session for false alarms per hour, and inspect a few event spectrograms
against the video.

## Reproduce

```bash
uv run python -m fall_detection.analysis.falldefi \
  --session data/raw/sessions/20261109T131546367822Z.zip \
  --fall-label walk_to_fall --fall-label sit_to_fall --fall-label stand_to_fall \
  --non-fall-label sit_to_stand --non-fall-label sit_to_walk \
  --non-fall-label stand_to_sit --non-fall-label stand_to_walk \
  --non-fall-label walk_to_sit --non-fall-label walk_to_stand \
  --output artifacts/falldefi/<new-run>
```

Run 1 used code from before the adaptation; its settings cannot be recreated
with the current command.
