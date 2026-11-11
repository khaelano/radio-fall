# tinygrad sequence-training optimization, 11 November 2026

This is a historical report. The tinygrad notebook and profiling tools have since been removed.

The training notebook now runs a stratified subset pilot before full-data
training. The pilot exercises loading, normalization, weighted BCE updates,
validation-based checkpoint selection, restoration, held-out predictions, and
synchronized inference. Full-data training remains an explicit notebook setting.
Raw recordings and exported source shards are unchanged.

## Conditions and implementation

The local artifacts are under
`data/processed/tinygrad_binary_v1/20261111T041429520431Z/profile/`.
Each duration contains 76 selected training and test windows. Validation contains
76 windows at 2 and 4 seconds, and 75 at 6 seconds. Sampling selects up to four
windows within every existing duration/split/dataset/activity/target stratum,
using seed 42. Attempts retain the original 60/20/20 split; no window moves
between partitions. Pilot normalizers use selected training windows only.

All models retain 1,960 input channels, 64 hidden units, and the complete
192/384/576-step input. Training uses 32-window effective batches and recurrent
microbatches, with 32-step recomputation and gradient propagation across every
boundary. Three pilot epochs provide an initial schedule-construction epoch and
two repeat epochs. The final partial recurrent microbatch uses sample weights;
evaluation pads only the batch dimension and excludes added slots from metrics.
No time samples are removed or pooled in the recurrent models.

`ModelPredictor` retains forward schedules across validation epochs. Recurrent
forward schedules operate on bounded chunks and live model parameters; the
classifier head has its own schedule. Initial states and carried states use the
same detached tensor representation, avoiding a reproduced OpenCL JIT argument
mismatch when starting a fresh batch. The existing deterministic tests also
exercise replay after parameter updates. This follows tinygrad's distinction
between schedule construction and kernel replay, documented in its
[performance guide](https://docs.tinygrad.org/developer/speed/).

The synthetic smoke test now configures its actual one-window microbatch rather
than padding it to 32 windows. Workers retain the enforced 3,000,000,000-byte
memory limit, zero swap, four-core CPU quota, and runtime limit. Polars, OpenBLAS,
and OpenMP thread limits match that CPU quota. A 64-step GRU pilot exceeded the
memory cap; the final settings reduce the chunk size instead of raising the cap.

The existing bounded prefetcher overlaps one ready batch with GPU work. Training
artifacts record loader wait, every optimizer-step duration, validation forward
durations, checkpoint time, final evaluation, first-call inference, and worker
memory peak. Pilot checkpoint and normalization paths are separate from the
complete-data training paths.

## Projection method

A scattered subset can decode nearly one source shard per selected window.
Complete-data iteration amortizes that decode across more rows. Therefore a
window-count multiple of pilot epoch wall time gives a misleading I/O estimate.
After each duration's GPU pilots, a bounded worker streams every complete-data
training, validation, and test window once, without training a model. It uses the
pilot normalizer only to measure transform cost. These read-only passes provide
the loading term independently of subset locality.

For each split, the compute estimate is the number of full-size batches, rounded
up, multiplied by median repeat-pilot batch time. Training excludes the pilot's
short final batch from this median; evaluation includes padded final batches.
For loading time L and compute time C, the split bounds are max(L, C) with ideal
overlap and L + C with serial execution. Training and validation bounds are
added for an epoch. The point estimate is their midpoint. The 30-epoch estimate
adds observed initial schedule overhead once. Checkpoint writes, startup, and
full-data normalization are separate small or one-time terms; final evaluation
and batch-one benchmarking are recorded separately.

These bounds describe overlap assumptions; they are not confidence intervals or
guaranteed runtime limits. Subset size cannot predict full-data accuracy, F1,
the selected checkpoint epoch, or early stopping. Thermal state, filesystem
cache, shard distribution, and different final-batch shapes can change rates.
The loader measurement is a single pass with the current OS cache state.

## Measured pilots and inferred full-data runtime

Hardware: AMD Radeon Renoir through Rusticl/Mesa 26.2.6, tinygrad 0.14.0. GPU workers used the same memory/CPU limits throughout. OS, driver, and compiler caches were not cleared. Each model used 76 training windows for three epochs; pilot metrics are saved separately from complete-data estimates.

| Model | Window (s) | Pilot training (s) | Full epoch (min) | 30 epochs (min, overlap–serial) | Peak (GB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| CNN | 2 | 50.2 | 2.83 | 67–103 | 1.09 |
| GRU | 2 | 84.3 | 3.51 | 90–122 | 2.00 |
| LSTM | 2 | 69.7 | 4.05 | 104–139 | 1.26 |
| CNN | 4 | 104.0 | 3.04 | 69–114 | 2.17 |
| GRU | 4 | 76.3 | 2.94 | 69–108 | 1.93 |
| LSTM | 4 | 149.7 | 5.37 | 139–184 | 2.09 |
| CNN | 6 | 55.8 | 1.70 | 39–63 | 2.50 |
| GRU | 6 | 82.3 | 2.86 | 70–102 | 2.02 |
| LSTM | 6 | 72.1 | 2.41 | 57–89 | 2.35 |

The nine-model, 30-epoch training budget is approximately **14.4 hours**, with overlap/serial bounds of **11.7–17.1 hours**. This includes per-epoch validation and initial schedule overhead, but excludes full-data normalization, worker startup, final evaluation and the final batch-one benchmark. Early stopping can shorten the run; its stopping epoch is unknown.

The 4-second LSTM had slower measured batch compute than the 6-second LSTM in this run. The two repeat epochs showed the same ordering, but the experiment does not isolate its cause. Treat this as a machine-state/throughput observation, not evidence that longer inputs are intrinsically faster. The overlap/serial bounds do not capture all variation between runs.

| Duration (s) | Full train windows | Train loader (s) | Validation loader (s) | Test loader (s) |
| --- | ---: | ---: | ---: | ---: |
| 2 | 5133 | 55.4 | 18.1 | 17.8 |
| 4 | 2444 | 70.5 | 19.7 | 18.3 |
| 6 | 1558 | 56.6 | 15.6 | 14.7 |

Earlier complete-data normalizer timings saved in the parent run total 173.3 seconds (including repeated metadata overhead). Those are historical preparation measurements, separate from this pilot and from the inferred training budget.

## Evaluation comparison and validation

Each forward comparison uses identical restored weights and a 32-window test batch. Four calls per implementation provide two warm-up/capture calls and two repeat calls. Timings include input transfer and host logits, excluding decoding. Every call agrees with the uncaptured reference at rtol 1e-4 and atol 1e-5. This measures evaluation forward acceleration, not a whole-training speedup.

| Model | Window (s) | Uncaptured median (ms) | Cached median (ms) | Speedup |
| --- | ---: | ---: | ---: | ---: |
| CNN | 2 | 413.4 | 375.7 | 1.10× |
| GRU | 2 | 1464.3 | 138.9 | 10.54× |
| LSTM | 2 | 1721.3 | 164.4 | 10.47× |
| GRU | 6 | 4243.0 | 406.5 | 10.44× |

Validation completed: the full suite passed 717 tests with three opt-in tests skipped (128.73 s). Running those OpenCL tests explicitly inside the 3 GB scope passed all three (10.29 s), including the CNN/NumPy loss check and recurrent replay across new-window boundaries. The existing full-gradient comparison checks uneven chunk boundaries and microbatch sizes on deterministic inputs. All nine real pilots completed checkpoint restoration, prediction export and inference timing. Prediction IDs/counts match the selected held-out partitions; probabilities are finite. A separate worker reloaded the 4-second GRU and reproduced its saved probability within 1e-6. The notebook has no editor error diagnostics, and all saved code cells compile.

## Reproduction

Install the notebook's optional dependencies and use its project kernel. Run
`notebooks/latest/03_training_tinygrad.ipynb` from the top; its default
`RUN_FULL_TRAINING=False` runs the pilots and estimates. Set that value to `True`
to fit full-data normalizers lazily and train the nine complete-data models
after profiling. Every notebook execution creates a separate results directory.

To profile a saved split from the command line:

```bash
PYTHONPATH=src .venv/bin/python tools/processing/profile_sequence_training.py \
  data/processed/tinygrad_binary_v1/20261111T041429520431Z
```

The CLI and notebook share
`src/fall_detection/analysis/sequence_training_profile.py` and the same guarded
worker entry point. `profile/selection.json` records sampling and counts;
`profile/loading-*s.json` records complete-data input timings;
`profile/*s/*/metrics.json` records phase timings and estimates;
`profile/comparison.csv` and `profile/results.json` consolidate completed pilots.
The parent run's `jobs/` directories retain requests, logs, responses, cgroup
resource measurements, and failed probes. No full-data model-quality result is
claimed by this report.
