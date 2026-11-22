# Representation, setup confound and cross-session tests, 22 November 2026

This report follows the [all-session comparison](detector-comparison-2026-11-22.md).
It asks three questions: why the baselines scored below our sequence models,
whether feeding the Hampel-filtered amplitude directly (no squared difference)
helps, and whether any result survives testing on a session the model never
saw. The random attempt split turned out to reward session-specific
regularities. Across sessions, FallDeFi was the strongest approach and the
sequence models were near chance.

## Conditions

- Sessions `khaelano` (`20261104T081805521126Z`), `akmal`
  (`20261109T131546367822Z`) and `continuous_non_fall`
  (`20261109T161519702956Z`); 120 Hz exports, 2, 4 and 6 s windows, the
  model settings of the comparison report, seed 42, CUDA training on an
  RTX 4070 SUPER.
- **Random split:** the `03_training` attempt split (475 attempts, 95 held out).
- **Cross-session split:** the same split, except that every attempt of one
  participant session is held out and the other session's test attempts join
  training; `continuous_non_fall` keeps its split. The two directions test 233
  attempts (231 `akmal` and 2 continuous) or 234 (232 `khaelano` and 2
  continuous). Runs came from
  in-memory copies of `03_training`, `04_wifall` and `05_falldefi` with those
  settings; each run directory stores its executed notebook.
- **Filtered amplitude:** `02_preprocess` `EXPORT_VARIANTS = ("filtered_amplitude",)`
  writes the Hampel-filtered amplitude, without difference or log1p, for the
  same windows; `03_training` `REPRESENTATION = "filtered_amplitude"` trains on it.
- Code: the working tree on top of `472933a`. Runs and diagnostics are tracked
  with `artifacts/notebooks.dvc`:

| Run | Directory under `artifacts/notebooks/` |
| --- | --- |
| Filtered amplitude, random split | `03_training/20261122T132757410153Z` |
| Comparison with filtered amplitude | `06_comparison/20261122T135423365712Z` |
| Squared difference, test `akmal` / `khaelano` | `03_training_cross_session/20261122T133601324422Z` / `…134245434562Z` |
| Filtered amplitude, test `akmal` / `khaelano` | `03_training_cross_session/20261122T134706972245Z` / `…135010227315Z` |
| FallDeFi, test `akmal` / `khaelano` | `05_falldefi_cross_session/20261122T135415056107Z` / `…140451334141Z` |
| WiFall, test `akmal` / `khaelano` | `04_wifall_cross_session/20261122T135653534973Z` / `…140715314692Z` |
| Probe scripts and tables | `diagnostics/20261122-generalization/` |

## Why the baselines scored lower on the random split

**WiFall.** Its activity gate passed 1.7 % of held-out fall windows and 0.3 %
of non-fall windows, so its gated output found almost no falls. On the
`akmal` session, LOF scores of fall samples had a median of 1.02 and a 99th
percentile of 1.22–1.30 against the threshold 1.5. The training countdowns
were not quiet: 48 % of them varied more, on some receiver, than a typical
action window. Lowering the threshold, gating on a 0.25 s rolling standard
deviation, or counting receivers active anywhere in the window did not make
the gate select falls (it passed 0–3 % of windows, or 75–80 % of both classes
at threshold 1.1).
Without the gate, the window features measure activity, not falls. Over all
4900 windows, the receiver-mean features separated falls from all other
windows with ROC AUC 0.76–0.81 (signal entropy 0.43), because 3121 negatives are
near-idle `continuous_non_fall` windows. Against sit-to-stand and stand-to-sit
windows the same features reached only 0.54–0.60. The median normalized
standard deviation was 0.030–0.037 for every cued transition, falls included,
and 0.020 for continuous non-fall data.

**FallDeFi.** Of the held-out attempts it scored, it flagged 9 of 11
sit-to-stand and 6 of 10 stand-to-sit attempts, but only 2 of 12 sit-to-walk
and 1 of 11 walk-to-sit attempts. Of its four features on held-out main events, only the
10–30 Hz spectral entropy separated falls (AUC 0.739); event duration (0.530),
1–10 Hz entropy (0.535) and fractal dimension (0.559) did not, because posture
changes last about as long as falls (median 2.4 s for both classes). Event
detection itself fired in 82 of 88 non-fall traces. It produced no trace for
11 of the 95 test attempts. Both continuous attempts were counted as false
alarms because 3 of their 38 interval traces were flagged.

Per session, FallDeFi reached attempt balanced accuracy 0.707 (`akmal`) and
0.696 (`khaelano`), against 0.817 and 0.948 for CNN 2 s.

## Filtered amplitude on the random split

All nine models trained on the filtered amplitude scored held-out window F1
0.945–0.971 and attempt F1 0.946–0.986 (false-positive rate 0.017–0.068),
above every squared-difference model (window F1 0.227–0.902).

| Approach (attempts) | Squared difference F1 / FPR | Filtered amplitude F1 / FPR |
| --- | --- | --- |
| CNN 2 s | 0.853 / 0.119 | 0.959 / 0.034 |
| CNN 6 s | 0.882 / 0.034 | 0.959 / 0.034 |
| GRU 2 s | 0.707 / 0.288 | 0.946 / 0.051 |
| LSTM 2 s | 0.705 / 0.356 | 0.986 / 0.017 |
| LSTM 4 s | 0.430 / 1.000 | 0.959 / 0.034 |

## The collection order confounds the random split

The collection protocol orders trials by equipment
([collection guide](../../configs/collection/README.md#collection-order-and-equipment)):
in both participant sessions, trials 1–144 are the non-fall transitions with
a chair, and trials 145–232 are all falls, with a mattress in the room.
No non-fall attempt was recorded with the mattress, and no fall without it.

Two probes on the 2 s windows of the random split show that static signal
levels identify that block:

| Probe | Squared difference | Filtered amplitude |
| --- | --- | --- |
| Logistic regression on each window's time-mean (no motion information), held-out window F1 / balanced accuracy | 0.612 / 0.820 | 0.933 / 0.993 |
| Same on each window's time standard deviation | 0.667 / 0.838 | 0.682 / 0.860 |
| Ridge regression of trial number from the time-mean, attempt-grouped 5-fold R² (`akmal` non-fall block / fall block) | −0.072 / 0.287 | 0.742 / 0.883 |
| Same for `khaelano` | 0.360 / 0.201 | 0.856 / 0.940 |

The filtered amplitude drifts with trial order (median error 3.9–13.8 trials)
and its time-mean alone matches the deep models, so the random split cannot
distinguish fall motion from "late in the session, mattress present". The
squared difference removes most of the drift, but its time-mean still reached
balanced accuracy 0.82; motion energy and setup effects are not separable here.

## Cross-session results

Sequence models, all nine per cell:

| Representation | Test | Median window F1 | Median window AUC | Median attempt balanced accuracy |
| --- | --- | --- | --- | --- |
| Squared difference | random split | 0.656 | 0.943 | 0.759 |
| Squared difference | `akmal` | 0.279 | 0.724 | 0.524 |
| Squared difference | `khaelano` | 0.193 | 0.458 | 0.452 |
| Filtered amplitude | random split | 0.954 | 0.999 | 0.969 |
| Filtered amplitude | `akmal` | 0.000 | 0.440 | 0.500 |
| Filtered amplitude | `khaelano` | 0.065 | 0.274 | 0.141 |

Filtered-amplitude models predicted no fall in `akmal` and ranked `khaelano`
windows worse than chance. Squared-difference models kept some ranking on
`akmal` but not on `khaelano`; at threshold 0.5, CNN 2–6 s flagged 98–99 % of
`khaelano` non-fall attempts.

On the attempts FallDeFi scored (184 of 233 for `akmal`, 213 of 234 for
`khaelano`), FallDeFi was the best approach in both directions:

| Test | Approach | Balanced accuracy | Recall | False-positive rate | F1 |
| --- | --- | --- | --- | --- | --- |
| `akmal` | FallDeFi SVM | 0.678 | 0.805 | 0.449 | 0.663 |
| `akmal` | best sequence model (GRU 2 s, squared difference) | 0.590 | 0.610 | 0.430 | 0.553 |
| `khaelano` | FallDeFi SVM | 0.709 | 0.842 | 0.423 | 0.646 |
| `khaelano` | best sequence model (GRU 4 s, squared difference) | 0.549 | 0.237 | 0.139 | 0.319 |

FallDeFi's cross-session balanced accuracy matched its random-split value
(0.685). WiFall stayed near chance: gated attempt balanced accuracy
0.459–0.500, classifier-only 0.425–0.513.

Rerunning the holdout from the committed notebooks (`HELD_OUT_SESSION` in
`03`–`06`) reproduced these results: FallDeFi 0.678 (`akmal`) and 0.709
(`khaelano`), best sequence model CNN 2 s 0.592 and GRU 4 s 0.543. Runs:
`06_comparison/20261122T144148567986Z` (test `akmal`) and
`06_comparison/20261122T145709625213Z` (test `khaelano`), which name their
`03`, `04` and `05` runs.

## Continuous data held out with `akmal`

`continuous_non_fall` was recorded three hours after `akmal` on the same day,
so the holdouts above still trained on 8 of its 12 segments. Holding out both
(`HELD_OUT_SESSION = ("akmal", "continuous_non_fall")`) trains on `khaelano`
alone (186 training, 46 validation attempts) and tests on all 231 `akmal`
attempts and all 12 continuous segments (1.0 h). Runs:
`06_comparison/20261122T162421842557Z`, which names its `03`, `04` and `05`
runs; `continuous_false_alarms.csv` there gives alarms per hour.

| Approach | Attempt balanced accuracy (243 attempts) | Continuous units flagged | Alarms per hour of continuous data |
| --- | --- | --- | --- |
| FallDeFi SVM | 0.732 (194 scored) | 21 of 285 traces (7.4 %) | 21 |
| GRU 2 s | 0.585 | 38.6 % of 2 s windows | 414 |
| LSTM 2 s | 0.573 | 63.4 % | 316 |
| CNN 2 s / 4 s / 6 s | 0.529 / 0.535 / 0.515 | 100 % / 98.7 % / 99.9 % | 12 / 20 / 12 (flagged throughout) |
| WiFall random forest, gated / classifier only | 0.442 | 0.3 % / 54.3 % of windows | 6 / 341 |
| WiFall one-class SVM, gated / classifier only | 0.457 | 0.1 % / 46.3 % | 2 / 305 |

Alarms merge overlapping or adjacent flagged windows within a segment, so a
detector that flags a whole segment counts one alarm; the CNN rows are such
cases. Without same-day continuous data in training, every sequence model
flagged 39–100 % of idle continuous time as falls, while the earlier holdouts,
which trained on part of that recording, flagged none of it. FallDeFi kept the
best attempt score and flagged 7.4 % of continuous traces; WiFall's gate kept
its alarms low only because it rarely passes any window.

## Interpretation and limits

- Under the random split, the sequence models' advantage over FallDeFi came
  from regularities within a session. One likely contributor is the
  equipment-ordered protocol, which ties falls to the mattress block and to
  late trials; the probes show this is learnable, but not which shortcut the
  models used.
- FallDeFi's features (relative amplitude, whitening by each receiver's
  resting spectrum, one event per trace) transferred between these two
  sessions; its weakness is posture changes of fall-like duration and a high
  false-positive rate (0.42–0.45).
- The filtered amplitude should not be used as evidence of better detection.
  Its random-split scores reflect static levels.
- All sessions share one room setup (same receivers, placements and channel),
  which is the project's scope; the cross-session tests change day and
  participant, not room. The deployed models were trained on all three
  sessions, including continuous data; the continuous false-alarm figures
  above apply only to models trained without it.
- Limits: two participant sessions, so each cross-session test also changes
  participant and date; the mattress confound remains inside both sessions,
  so cross-session scores can still contain setup effects; FallDeFi left 9–21 %
  of test attempts unscored; one seed; threshold 0.5 for the sequence models;
  attempt metrics use the any-unit rule.
- One hour of continuous data from one session is too little for a reliable
  false-alarm rate; the numbers show orders of magnitude, not rates.
- Implications: evaluate on held-out sessions rather than random attempt
  splits, and collect non-fall activity with the mattress in place (or
  interleave trial order) before comparing representations.
