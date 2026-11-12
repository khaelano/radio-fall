# Training input cache check, 12 November 2026

The sequence loader repeatedly normalized overlapping windows each epoch.
`SequenceDataset.prepare()` now prepares float32 inputs once within a RAM budget;
the existing prefetch thread supplies batches concurrently with training. Inputs,
validity and presence channels, metadata, and seeded ordering match streaming in
deterministic tests at 96 and 120 Hz. No split or normalizer fitting policy changed.

The notebook defaults to a 12 GiB combined train/validation cache for one duration.
On Linux, this is additionally capped at 60% of available memory at preparation.
Partitions that do not fit stream instead; test inputs stream. The budget excludes
transient batches, models, and filesystem cache. Set `input_cache_gib=0` to stream.
Preparation time and actual allocation are recorded separately in metrics.

CUDA now attempts compact device storage before preparing RAM windows.
`device_cache_gib=4` limits resident signal/mask tensors; `device_reserve_gib=4`
is subtracted from currently free VRAM before allocating. These are configurable
budgets, not guarantees that every model/batch shape will fit. Set the device
cache budget to zero to use the RAM path alone. Each partition stores the covered
span of each segment once, with normalized float32 signals, boolean validity,
and optional boolean packet-presence masks. Only a gathered batch expands masks
to float32. Normalization stays in bounded CPU chunks to preserve NumPy rounding.
The GPU gathers windows on the training stream, avoiding cross-thread CUDA stream
handoffs. Allocation failure or an oversized partition falls back to RAM, then
streaming; malformed inputs still raise errors. Test data streams as before.
The source helper is `src/fall_detection/analysis/sequence_device_cache.py`.
Before measuring free VRAM, preparation releases unused PyTorch allocator blocks
from earlier models once with `torch.cuda.empty_cache()`. Without this, a warm
notebook can unnecessarily fall back to RAM despite low live tensor allocation.

## Measurements

The check reused the 120 Hz split and 2-second normalizer from run
`20261112T043926419689Z`. Its split and metrics now live under
`artifacts/notebooks/03_training/<run-id>/`, together with normalizers and
checkpoints. These files were moved from the former
`data/processed/pytorch_sequence_pilot/notebook/` location with hashes verified.
Train, validation, and test contained 5,133, 1,522, and 1,525 windows respectively.
Split SHA-256: `418b9a8ec2bd4ca40b91bfcffd8c1960a2c4f2ef612a1615de9068e473dd4bc9`.
Normalizer SHA-256: `dcfd2b804aa1884841a12e43ac7f59dcf82d68b2a0d688230ff1ce1e4d1d3426`.

At batch size 128, loader-only passes over training took 7.113 and 6.645 seconds
streaming, versus 1.744 and 1.155 seconds prepared (seeds 43 and 44). Preparing
training inputs took 9.661 seconds once and allocated 9,677,963,520 bytes.

A two-epoch CNN check through the notebook bridge used CUDA, batch size 128,
seed 42, 64 hidden channels, and the existing deterministic training procedure.
Train/validation preparation took 11.466 seconds once and allocated 11.68 GiB.
Epochs including validation/checkpointing took 2.234 and 1.829 seconds; validation
took 0.553 and 0.428 seconds. The earlier saved batch-32 CNN run had a median
epoch time of 8.683 seconds after its first epoch. This is not a controlled
batch-size comparison, and two epochs do not establish convergence or accuracy.
Validation now transfers probabilities to the CPU once per evaluation.

Hardware: RTX 4070 SUPER, 12 GiB VRAM; i7-14700F; 32 GiB RAM. The baseline runtime
records Python 3.12.3 and PyTorch 2.14.1+cu130. Benchmark checkpoints were temporary
and removed; no experimental model was replaced. Other models, durations, larger
datasets, and machines with less RAM require their own timing checks.

## Compact VRAM cache check

Two-epoch checks through the bridge reused the same split, each duration's saved
normalizer, batch size 128, seed 42, 64 hidden channels, and deterministic training.
The table reports both epochs including validation and checkpointing. RAM timings
were measured immediately before correcting allocator accounting and activating
the device cache; they used the same batch size and temporary-check procedure.

| Model | Window | RAM epochs (s) | VRAM epochs (s) | VRAM preparation (s) | Peak allocated VRAM (GiB) |
| --- | --- | --- | --- | --- | --- |
| CNN | 2 s | 1.769, 1.806 | 0.545, 0.530 | 1.912 | 4.98 |
| CNN | 6 s | 1.648, 1.689 | 0.496, 0.489 | 1.890 | 6.87 |
| LSTM | 6 s | 1.706, 1.694 | 0.693, 0.683 | 2.054 | 9.24 |
| GRU | 6 s | 1.681, 1.670 | 0.674, 0.669 | 1.937 | 9.30 |

Train/validation segment caches occupied 3.86 GiB combined for 2-second windows
and 3.93 GiB for 6-second windows, versus 11.68 and 10.60 GiB of expanded RAM
windows. GPU masks remained boolean. Tests verify exact input/metadata/order
parity at 96 and 120 Hz on CPU and CUDA, budget refusal, simulated allocation
failure after a partial allocation, and rejection of malformed presence masks.
Two epochs establish execution and timing only, not convergence or classification
quality. CUDA event step timings exclude batch gathering, which happens during
iteration; load-wait time on this path includes submission of GPU gather work.
