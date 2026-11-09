# CSI transport simulation experiment

This experiment replays the two recorded CSI views through hypothetical sensing
and BLE transport policies, then performs EDA, preprocessing, CNN training and
fixed-cohort evaluation. Raw recordings and the previous CNN pilot are read-only.
Four-slot conditions add two virtual byte workloads; they do not create two
additional CSI views. All loss and transport settings are assumptions.

Open `04_transport_experiment.ipynb` for the executed walkthrough and
`results/replay_v1/REPORT.md` for measurements and limits.

## Executed replay_v1 findings

Both three-seed CNN ensembles classify 28/30 test attempts correctly in seven
conditions, including the 1.4 Mbit/s simulation: balanced accuracy 0.929,
16/16 detected falls, and 2/14 false-positive non-falls. The clean-trained model
already tolerates those injected patterns; this run does not demonstrate an
extra benefit from missingness augmentation. Unchanged threshold decisions do
not mean unchanged probabilities or establish equivalence between policies.

The 1.0 Mbit/s service case saturates under the configured traffic, fragment
cost, grant guard and queue policy. Its median timely training-cohort rate is
zero despite approximately 54 captured records/s per real view before service.
Many records arrive after the 100 ms prediction grace. Test balanced accuracy
falls to 0.500 for clean training and 0.536 for missingness training, with 14/14
and 13/14 false-positive non-falls respectively. These scores do not support
claiming that augmentation solves severe delivery starvation.

This is evidence about the stated replay assumptions on the reused 30-attempt
scenario test partition, not a measured minimum adapter throughput or a
four-view detector result. The original-condition missingness-only baseline
also obtains balanced accuracy 0.647, so acquisition confounding remains open.

## Environment and execution

This experiment deliberately reuses the pinned environment, HE-LTF decoder,
clock mapper and small CNN from `../03_cnn_baseline/`. It is not standalone.
`manifest.json` fingerprints every reused Python source and raw input. No
existing pilot code, arrays, checkpoints or results are overwritten.

From this directory:

```bash
uv sync --project ../03_cnn_baseline --frozen --extra notebook
uv run --project ../03_cnn_baseline --frozen python run.py
uv run --project ../03_cnn_baseline --frozen python -m pytest tests -q
```

Individual stages: `python run.py --stage prepare`, `eda`, `train`, `evaluate`,
or `report`. `--config`, `--output` and `--results` select separate runs. The
default artifacts are `artifacts/replay_v1/`; small shareable exports are
`results/replay_v1/`. Preparation refuses an already prepared output. Config,
code, arrays, split and checkpoints are verified before training/evaluation.
Use new output/result directories when changing assumptions.

To execute the notebook with saved results:

```bash
uv run --project ../03_cnn_baseline --frozen --extra notebook jupyter nbconvert \
  --to notebook --execute --inplace 04_transport_experiment.ipynb
```

The notebook reads saved outputs by default. The explicit rerun cell uses a
separate output/result pair and can take several minutes and several GB.

## Fixed experimental design

- Reuse the original pilot's 154 attempts and scenario-group split. Every
  variant of an attempt remains in its original partition. No coverage-based
  exclusions after injecting loss. The test set was already inspected in the
  earlier pilot, so results are exploratory, within one session/participant.
- Compare original 100 Hz, approximate 80 Hz, two-slot round robin, four-slot
  round robin, four-slot random grants, assumed independent/burst losses, and
  two constrained transport capacities. Selection of an upload owner means
  that slot is blind for the corresponding retained sensing round.
- At 80 Hz, retain four of five original source rounds. Preserve the actual
  capture timestamps and 10/20 ms spacing. A real uniform 12.5 ms transmitter
  is not reproduced by this operation.
- Real-stream natural losses remain missing. Synthetic additional loss is
  label-independent and seeded. Shared synthetic capture losses remain paired
  between the loss-only and constrained-service conditions.
- Queues have finite capacity and expiry. A separate uniform target-rate grant
  clock gives equal service durations, with grants assumed announced ahead of
  time. Source capture timestamps retain thinning jitter; 20 ms thinning gaps
  are not assigned as longer grants to one receiver. Only the owner gets service;
  partial transfers can span its later grants. A shared application-service
  bit budget includes assumed record/fragment metadata and retries. It does
  not emulate BLE connection anchors, ACK timing or radio/controller behavior.
- Replay begins with the first available packet, including countdown before
  the action window. Queues therefore warm up before classification rather
  than being artificially reset to empty at the action cue.
- Capture time and delivery time remain separate. Finalize every 20 ms capture
  bin at bin end + 100 ms. Packets that arrive later stay missing for that bin;
  they may update subsequent age metadata without filling other capture bins.
- Decode/calibrate packets independently, then apply loss/deadlines before
  circular binning. Preserve 242 tones. No temporal interpolation or filtering.
  Model input: four sine/cosine phase channels, four finite masks, two delivered
  packet-count channels and two normalized ages. Normalization uses original
  training attempts only. Ages do not use future capture values.
- Train clean and missingness-augmented versions of the same small CNN, each
  with seeds 17/29/43. Both get one variant per original attempt per epoch and
  the same maximum steps. Augmented variants use replay seeds 101/202;
  validation uses 303, test uses 404. Early stopping uses validation BCE only.
  No test-based model or condition selection; fixed decision threshold 0.5.
- Report all conditions, signal-summary logistic, missingness-only logistic,
  majority baseline, scenario-cluster intervals, seed metrics, and predictions.
  A four-second cue window plus grace is attempt classification, not a measured
  continuous detector or alarm latency.

## Files

`replay.py` implements scheduling, loss, queues, service and input deadlines.
`prepare.py` binds that engine to immutable packets and frozen cohorts.
`experiment_models.py` trains/evaluates both regimes. `reporting.py` produces
training-cohort EDA and shareable results. `config.json` pins assumptions;
`tests/test_replay.py` checks conservation, causality, queues and seeded losses.
