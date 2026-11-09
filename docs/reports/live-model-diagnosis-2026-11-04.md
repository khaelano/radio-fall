# Live model diagnosis, 4 November 2026

The operator reports confident fall candidates while standing and little
response during attempted falls. Run `data/experiments/detector/20261104T143017Z/`
contains 907 scored windows and 25 insufficient-data events over approximately
four minutes. It has no time-aligned activity labels, so false-alarm counts,
missed-event rates and detection delays cannot be calculated from this log.
Candidate count alone is not a false-alarm count.

## Checked behavior

Twelve windows spaced across the run were reconstructed from raw gateway
envelopes and recorded capture/availability events. The native model tensors
and an independent NumPy binning/scaling calculation matched exactly, as did
replayed and logged ensemble scores. This check found no Rust/Python
normalization arithmetic mismatch on those windows. It does not establish
that the normalization strategy generalizes.

The model uses fixed training means and scales for each receiver/tone after
log1p amplitude binning. Training-window mean standardized values for rx-4
ranged from −0.431 to +0.140. Sampled later live windows reached −6.918; several
had scores close to one. These are means of per-tone standardized features,
not standardized deviations of the receiver's aggregate mean. The physical
cause of the changed signal profile is unverified.

Replacing each time bin with the same per-tone mean, and making its finite
mask constant over time, preserved all 36 original held-out binary decisions.
These synthetic inputs remove temporal variation while retaining each
window's amplitude profile. They are not newly labeled stationary recordings.
One similarly flattened live window retained a score of exactly 1.0. Thus the
model can issue a confident candidate without a changing input signal; static
profiles suffice for its decisions in these examples.

In the live window starting 103 seconds after the first logged window start,
replacing only rx-4's valid signal values with its training means changed the
score from 1.0 to 0.0000336. This counterfactual removes rx-4's dynamic and
static information together. Removing only its per-tone baseline left a score
of 0.9969 in that example. Baseline recentering is therefore not demonstrated
to repair the existing model. The ablations identify input dependence, not a
validated intervention or a physical cause of the operator's errors.

The evidence supports strong dependence on receiver signal conditions and a
large live/training distribution shift. It does not identify the exact
mechanism of each reported false alarm or miss without timed activity labels.
The earlier collection-order control already limited interpretation of the
35/36 offline result. The current amplitude ensemble should not be described
as a validated continuous fall detector.

## Proposed phase-change experiment

A phase-change-only model without fitted standardization is a proposal, not
an executed result. Compute signed wrapped changes over the existing 100 ms
lag, retain every physical tone/receiver, and feed sine/cosine components
directly with explicit missing-value masks. Their bounded encoding needs no
fitted mean/scale. Existing phase preparation and weak-signal validity rules
remain separate from feature standardization.

The previous phase-change candidates used fitted normalization: central
validation balanced accuracy was 0.670/0.719 for fixed/shift augmentation and
0.811/0.804 for their smoothing variants. Those results do not answer whether
the proposed unstandardized inputs work live. New weights must be trained with
the new input contract; switching preprocessing beneath existing weights is
not a valid comparison. Radio phase variation and window/label alignment
remain possible failure sources. Independent continuous recordings, including
ordinary stationary and non-fall activity, are needed to evaluate the proposal.

Raw recordings, saved model weights and production preprocessing were not
changed during this diagnosis. Derived sampled arrays and numerical findings
are under `data/experiments/detector/normalization-diagnosis/` in
`sampled-live-inputs.npz`, `parity.json` and `ablation.json`. Temporary diagnostic
harnesses are retained in the local `.codex-build/live-model-diagnosis/` folder.
