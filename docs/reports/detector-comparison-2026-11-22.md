# Sequence models and baselines on all sessions, 22 November 2026

These runs executed `02_preprocess` through `06_comparison` on every current
session, putting our sequence models, the [WiFall adaptation](../baselines/wifall.md)
and the [FallDeFi adaptation](../baselines/falldefi.md) on one attempt split.
They compare approaches on held-out attempts of the training sessions; they do
not establish generalization to new sessions, rooms or participants.

## Conditions

- Sessions: `khaelano` (`20261104T081805521126Z`), `akmal`
  (`20261109T131546367822Z`) and `continuous_non_fall`
  (`20261109T161519702956Z`); `SAMPLE = False` in `02_preprocess` and
  `03_training`.
- Sequence export: 120 Hz, Hampel 0.5 s / 3 MAD, log1p squared difference,
  2, 4 and 6 s windows with 50 % overlap, labels by cue center.
- Split: `split_sequence_attempts`, seed 42, test and validation fractions 0.2,
  one split across durations. 475 attempts: 285 training, 95 validation,
  95 test (46 `akmal`, 47 `khaelano`, 2 `continuous_non_fall`). Split SHA-256
  `418b9a8e…dd4bc9`.
- Sequence models: CNN, LSTM and GRU from `03_training`, hidden size 64,
  batch 128, learning rate 0.001, up to 30 epochs with patience 5, seed 42,
  trained with CUDA PyTorch 2.14.1 on an RTX 4070 SUPER; threshold 0.5.
- Baselines: default configurations with seed 42, fitted on training and
  validation attempts and scored on the test attempts.
- Code: commit `73045e3` with `SAMPLE = False`. Runs, tracked with
  `artifacts/notebooks.dvc`:
  `03_training/20261122T123844906038Z`, `04_wifall/20261122T124543607681Z`,
  `05_falldefi/20261122T125912793090Z`, `06_comparison/20261122T130150062342Z`.

## Attempt-level results

An attempt is a fall when any of its units is, and is predicted a fall when
any of its units is (`06_comparison`). All approaches scored the same 95 test
attempts (36 falls, 59 non-falls) except FallDeFi, which produced no trace for
11 of them.

| Approach | Attempts | Balanced accuracy | Precision | Recall | F1 | False-positive rate |
| --- | --- | --- | --- | --- | --- | --- |
| CNN 6 s | 95 | 0.900 | 0.938 | 0.833 | 0.882 | 0.034 |
| CNN 2 s | 95 | 0.885 | 0.821 | 0.889 | 0.853 | 0.119 |
| CNN 4 s | 95 | 0.885 | 0.821 | 0.889 | 0.853 | 0.119 |
| GRU 4 s | 95 | 0.765 | 0.675 | 0.750 | 0.711 | 0.220 |
| GRU 2 s | 95 | 0.759 | 0.630 | 0.806 | 0.707 | 0.288 |
| LSTM 2 s | 95 | 0.753 | 0.596 | 0.861 | 0.705 | 0.356 |
| GRU 6 s | 95 | 0.752 | 0.870 | 0.556 | 0.678 | 0.051 |
| FallDeFi SVM | 84 | 0.685 | 0.531 | 0.812 | 0.642 | 0.442 |
| LSTM 6 s | 95 | 0.473 | 0.357 | 0.556 | 0.435 | 0.610 |
| LSTM 4 s | 95 | 0.361 | 0.306 | 0.722 | 0.430 | 1.000 |
| WiFall random forest | 95 | 0.514 | 1.000 | 0.028 | 0.054 | 0.000 |
| WiFall one-class SVM | 95 | 0.500 | 0.000 | 0.000 | 0.000 | 0.000 |

## Unit-level results

Units differ, so these rows are not comparable across approaches.

| Approach | Unit | Test units | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- |
| CNN 2 / 4 / 6 s | window | 1525 / 725 / 455 | 0.890 / 0.849 / 0.958 | 0.755 / 0.805 / 0.852 | 0.817 / 0.827 / 0.902 |
| GRU 2 / 4 / 6 s | window | 1525 / 725 / 455 | 0.739 / 0.667 / 0.879 | 0.590 / 0.623 / 0.537 | 0.656 / 0.644 / 0.667 |
| LSTM 2 / 4 / 6 s | window | 1525 / 725 / 455 | 0.713 / 0.145 / 0.293 | 0.590 / 0.519 / 0.444 | 0.646 / 0.227 / 0.353 |
| WiFall random forest, gated | 2 s window | 854 | 1.000 | 0.008 | 0.017 |
| WiFall random forest, classifier only | 2 s window | 854 | 0.371 | 0.331 | 0.350 |
| WiFall one-class SVM, classifier only | 2 s window | 854 | 0.181 | 0.839 | 0.298 |
| FallDeFi SVM | trace | 120 | 0.520 | 0.813 | 0.634 |

FallDeFi found events in all 32 held-out fall traces and in 82 of 88 non-fall
traces; 24 events in non-fall traces were classified as falls, 116 per hour
of non-fall trace time. The WiFall gate passed 1.7 % of held-out fall windows
and 0.3 % of non-fall windows (classifier-only false-positive rates 0.090 for
the random forest and 0.609 for the one-class SVM).

## Interpretation and limits

- The CNN was the strongest approach at every duration. LSTM 4 s and 6 s
  stopped after 6.5 and 7.6 s of training (LSTM 2 s took 23 s), and LSTM 4 s
  flagged every non-fall attempt; these rows reflect failed training, not the
  architecture's capacity.
- The WiFall gate failed on all sessions as on the
  [smoke subset](wifall-smoke-2026-11-22.md), so its gated rows do not measure
  its classifiers.
- One seed and one split; the attempt rule favours approaches with more units
  per attempt in recall. Collection cues are not measured fall times. The
  `akmal` session informed both baseline adaptations.
