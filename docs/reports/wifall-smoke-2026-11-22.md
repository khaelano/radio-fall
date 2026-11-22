# WiFall smoke runs on one session, 22 November 2026

These runs checked the rewritten [WiFall adaptation](../wifall.md) end to end
on the same subset as the [FallDeFi smoke runs](falldefi-smoke-2026-11-22.md).
They are not an evaluation: one session, an attempt holdout and correlated
windows cannot establish detection performance, and the session informed the
design.

## Conditions

- Session `20261109T131546367822Z` (9 November, 13:15); 231 accepted
  attempts; the same fall and non-fall labels as the FallDeFi runs.
- Current defaults: 2 s windows with a 1 s hop, 120 interior tones, coverage
  0.7 and gaps up to 0.25 s judged per receiver, at least two receivers,
  relative amplitude, `m = 5` smoothing, LOF with 20 neighbors and threshold
  1.5 on at most 128 training countdown chunks, 20 pooled features.
- Random forest (200 trees, balanced class weights) and fall-inlier one-class
  SVM (`ν = 0.1`); attempt holdout, test fraction 0.25, seed 42.
- Code at the working tree on top of commit `67e5039`; hashes are in each
  run's `report.json`. Outputs under `artifacts/wifall/`, not versioned.

## Data

848 action windows and 649 countdown windows survived; 157 action windows had
fewer than two usable receivers. The first implementation, which required all
four receivers, kept 134 action and 99 countdown windows from this session at
0.7 coverage and 0.15 s gaps. The holdout had 639 training and 209 test windows
(62 fall), from 56 test attempts (21 falls). Held-out windows used two
receivers (151), three (35) or four (23).

## Run A: tone-mean activity stream

The first rewrite fed the LOF gate WiFall's tone average (equation 8). The gate
passed 1.6 % of held-out fall windows and no non-fall windows, so gated
predictions found no falls.

| Classifier only, held-out windows | Falls found | Non-falls correct | Balanced accuracy |
| --- | --- | --- | --- |
| Random forest | 18 / 62 | 107 / 147 | 0.509 |
| One-class SVM | 57 / 62 | 25 / 147 | 0.545 |

Outputs: `artifacts/wifall/subset-20261109-adapted-{random_forest,one_class_svm}-seed42/`.

## Diagnosis

LOF scores of held-out countdown, fall and non-fall samples had nearly the
same distribution on every receiver (median 1.01–1.02, 99th percentile
1.21–1.27). Comparing three activity signals per receiver over all 2 s windows
of the session:

| Signal (standard deviation per window) | Rest median | Fall | Non-fall |
| --- | --- | --- | --- |
| Tone mean of relative amplitude | 0.0126 | 1.14× | 1.15× |
| First principal component | 0.244 | 1.54× | 1.40× |
| Mean per-tone deviation | 0.0369 | 1.29× | 1.22× |

The tone mean cancels motion, because motion raises some tones while lowering
others. The first principal component separates activity best, but the
distributions overlap: its 75th percentile at rest (0.376) equals the fall
median (0.375). Every pooled feature of Run A had a fall-versus-non-fall ROC
AUC between 0.446 and 0.507 over all 848 windows.

## Run B: principal-component activity stream

The current code feeds the gate each window's first principal component.

The gate passed no held-out window, so gated predictions again found no
falls.

| Classifier only, held-out windows | Falls found | Non-falls correct | Balanced accuracy |
| --- | --- | --- | --- |
| Random forest | 20 / 62 | 106 / 147 | 0.522 |
| One-class SVM | 57 / 62 | 29 / 147 | 0.558 |

Counting an attempt as a fall when any of its windows is classified as one,
the random forest found 14 of 21 fall attempts and flagged 28 of 35 non-fall
attempts; the one-class SVM flagged all 56.

Outputs: `artifacts/wifall/subset-20261109-pc1-{random_forest,one_class_svm}-seed42/`.

## Interpretation and limits

On this subset the adapted WiFall uses six times as many windows as before,
but neither its gate nor its classifiers work: the gate never fires, and the
window features do not separate falls from the other cued transitions. Three
observations may explain this, none tested: countdowns vary nearly as much as
activity, so a resting profile cannot single out motion; windows are labelled
by their center in the action cue, so many "fall" windows show walking or
lying rather than the fall; and both classes are activities of similar
intensity. On the same session FallDeFi, which localizes one main event per
attempt, separated the classes mainly by event duration.

Possible next steps: inspect countdown video for movement; score WiFall's
features on the main event that FallDeFi detects instead of on every window;
or calibrate the gate on training windows as FallDeFi calibrates `k`.
