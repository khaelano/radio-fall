# Live four-receiver fall scoring

`fall-detect` is a separate desktop program. It reads all four receivers through
the existing gateway acquisition service, prepares model inputs in Rust, and
runs an exported three-seed CNN ensemble in a separate CPU process. Bundles
support the earlier normalized amplitude input or unscaled phase-change input.
The default window is four seconds, advanced every 250 ms. The GUI shows the
score, current coverage, receiver/transport health and a score history. Headless
mode emits JSON. A score at or above 0.5 is displayed as a **fall candidate**.

Both models come from the single-participant/session experiment. The earlier
amplitude model's collection-order control matched its held-out balanced
accuracy, and the operator reported confident standing false alarms and missed
falls. The phase model is a separate retraining experiment, not a validated
repair. Continuous detection accuracy, false alarms
per hour and event latency have not been established. The program does not
send notifications or treat unavailable data as a non-fall decision.

## Install and run

Run from the repository root. Installation requires Rust and builds the native
extension; the detection extra includes CPU PyTorch 2.14.1 for both the fall
scorer and notebook-trained phase models.
Keep `--extra video` when also using the camera-enabled collector.

```sh
uv sync --inexact --extra radio --extra detection --extra analysis
```

The unscaled phase-change bundle is `data/models/phase_random20_v1/`. Its
historical training experiment materialized 20 random shifts plus the central
window for every training attempt; the experiment notebook and generated
artifacts have been removed from the repository. The model bundle is a local,
Git-ignored artifact and is not included in a clean checkout. See the
[historical pilot summary](reports/fall-model-pilots.md) for retained results
and limitations. Exporting a new bundle still requires an external copy of the
original experiment artifacts with `--export-model <new-directory>
--experiment <artifact-directory>`. The earlier amplitude bundle, when
available, is `data/models/four_rx_v1/`.

With the gateway connected and all boards powered:

```sh
.venv/bin/fall-detect --model data/models/phase_random20_v1
```

To show the notebook-trained phase models alongside the existing fall score:

```sh
.venv/bin/fall-detect --model data/models/phase_random20_v1 \
  --phase-models data/experiments/phase_models_v1/20261104T081805521126Z
```

When the default phase model directory exists, the GUI enables it automatically;
use `--no-phase-models` to disable it or `--phase-models` to choose a different
trusted directory. If the default directory is absent, the fall detector starts
without the phase table.

The optional phase table has one row per receiver, window length (2, 4, or
6 seconds), and model (CNN, LSTM, GRU, random forest): 48 rows for four
receivers. Each row reports preparation, action and resting probabilities and
coverage. These are **collection-phase scores at the window center**, not
fall probabilities. The window centers are respectively 1, 2, and 3 seconds
before the displayed window end. An asterisk marks a model with absent training
classes; hovering over its name shows the missing classes. In the earlier
one-session evaluation, the six-second models had no preparation examples
and predicted only action in the held-out evaluation.
The scores are experimental and have not been validated for live use.

The trusted model directory must contain each
`<2|4|6>s/<cnn|lstm|gru>/model.pt`,
and each `<2|4|6>s/random_forest/model.joblib`, plus
`metrics.json` for its pooling configuration. The notebook's phase model
checkpoints do not contain a verified radio identity; the existing fall bundle's
radio validation still applies, but it does not authenticate the phase models'
training setup or receiver placement. Joblib files must come from a trusted
source because loading them executes pickle deserialization.

Legacy phase-model checkpoints require the PyTorch format.

Phase scores use the shared amplitude normalization, centered Hampel,
80 Hz linear interpolation and mask-aware temporal pooling routines. Live
normalization is fitted separately to each completed rolling window, whereas
training normalized the entire recording. Filtering also has only the completed
window's context. This is an approximation, not an exact reproduction of the
offline inputs. Live sample grids are anchored to the monotonic clock rather
than an attempt start, and native I/Q magnitudes can differ in floating-point
rounding from the offline decoder. The existing 25 ms maximum interpolation gap and a 70% valid
time/tone coverage gate apply per receiver; unavailable windows show no score.
They do not use an anti-alias filter. A bounded background thread processes
native records and all four models for each receiver/window. The default
`--phase-hop-ms 2000` is independently configurable; a shorter interval can
overload the worker. The GUI reports its queue and drop count. Queue overflow,
radio interruption, boot/run changes and stale results invalidate phase scores.
The fall model remains a separate worker with its own preprocessing and
freshness rules.
Each phase window admits only packets received by its end plus the configured
delivery grace; later packets cannot revise that window.

Each fresh phase result is logged to `predictions.jsonl` as
`phase_prediction`, with receiver, duration, model, center/end timestamps,
coverage, class probabilities and generation. Headless status also includes
phase worker state. Phase worker errors suppress its scores without reclassifying
them as fall or non-fall decisions.

Headless operation, optionally bounded to a fixed duration:

```sh
.venv/bin/fall-detect --model data/models/phase_random20_v1 --headless --duration 60
```

The program reads `configs/radio.json`, with the same `--config`,
`--gateway-port`, `--port` and `--transmitter-link` overrides as the viewer.
It checks the sensing-profile fingerprint, transmitter and ordered receiver
identities against the bundle before acquisition starts. Physical receiver
placement cannot be checked automatically and must match the recording setup.
The model is loaded before radio startup. Failed startup and normal exit both
close the acquisition, inference process and native preprocessing workers.

Do not open the collector/viewer on the same gateway simultaneously. This
program owns the acquisition connection while it runs. No firmware changes or
reprovisioning are required.

## Timing and input contract

- Each window is `[start, start + 4 s)` on mapped transmitter enqueue time.
  USB arrival order does not determine bins. The scheduler preserves the exact
  250 ms hop, including shifts that are not multiples of the 40 ms bin width.
- The 900 ms default delivery grace must match radio settings. The first
  scheduled window also reserves 150 ms of preceding context for the 100 ms lag
  coverage check. The initial score therefore needs approximately 5.05 seconds
  after the first input, plus model/radio startup and processing time. This is
  a context requirement, not a measured fall-to-alarm latency.
- Native preprocessing records when a packet reaches its feature worker.
  Packets unavailable by a window's end plus grace cannot fill that window.
  Completed windows are immutable. A replay of an offline training window uses
  all saved packets, so its missingness can differ from a live deadline-limited
  window. Gateway 50 Hz availability bins remain a separate unchanged contract.
- The canonical Rust acquisition backend already validates/fragments/decodes
  envelopes, prepares physical HE20 phase masks and dispatches signed I/Q
  magnitudes through AVX2 where supported. The detector reuses those native
  records rather than converting CSI into Python lists.
- The detector filters sensing-link metadata, excludes nonzero driver receive
  status, and uses the common raw/calibrated phase finite mask. It retains all
  242 valid physical tones in ascending order. For amplitude inputs, log1p magnitudes are
  computed once, followed by double-precision sums/counts in 25 Hz bins and the
  original float32 cast before normalization. There is no interpolation.
- Amplitude normalization uses the saved training mean/scale for each receiver and tone.
  Missing normalized values become zero, with four explicit mask planes. The
  CPU model input has shape `[1, 8, 100, 242]`: four amplitude channels followed
  by their four masks. No live normalization fitting occurs.
- The phase bundle uses signed calibrated phase differences to the packet at
  or before 100 ms earlier, with actual lag at most 150 ms. Rust averages the
  sine and cosine in each bin without smoothing or fitted normalization.
  Input shape is `[1, 16, 100, 242]`: sin/cos for rx-1 through rx-4, followed
  by eight corresponding masks. Finite values stay in [−1, 1]; missing values
  become zero. Amplitude is used only by the existing phase validity floor.
  Packet calibration is retained and is distinct from feature standardization.
- New phase training and live inference both use integer nanoseconds for the
  lag cutoff and bin assignment. The older Python analysis can reject an exact
  150 ms lag after floating-point subtraction; the new experiment records this
  difference and leaves the old checkpoints and analysis artifacts unchanged.
- At least 70% finite phase-change time/tone support is required in every
  receiver's current window. The coverage calculation reproduces the original
  100–150 ms lag support using each tone's finite masks; the amplitude CNN does
  not need the phase-change values themselves. Unlike the offline common-cohort
  filter, live gating cannot inspect future offset windows.

Run IDs and transmitter/receiver boot changes invalidate every receiver's
history together. Link interruption clears pending decisions immediately.
Old-generation results, low-coverage windows, unavailable radio health and
stale scores are suppressed. An older in-flight score cannot replace a newer
low-coverage decision. At the default hop/grace, a score older than 1.9 seconds
relative to its capture-window end becomes unknown.

## Native scheduling and bounds

The record callback only validates context and queues an `Arc` reference.
A dedicated Rust thread prepares packet features and schedules windows; two
Rayon workers process receivers concurrently. AVX2 kernels accelerate masked
bin accumulation and float32 normalization/mask construction. Scalar tails and
a runtime scalar fallback preserve the same calculations. Scalar log1p and
the existing phase preparation keep the training conventions; no fast-math or
approximate logarithm is introduced.

`--kernel scalar` disables the detector's vector kernels for comparison;
`--kernel auto` selects AVX2 on the tested machine. `--workers 1` through `4`
controls native receiver processing, and `--inference-threads 1` through `4`
controls the isolated CPU scorer. The acquisition worker/USB guards remain
unchanged.

The native input queue holds at most 4,096 record references, each receiver
retains at most 2,048 feature records, and the native output holds only the
latest window. Input/history overflow increments diagnostics and invalidates
the generation. The model process has one queued input and four output slots;
the UI skips inference submissions when that input slot is occupied. The
freshness rule prevents delayed results from becoming current decisions. The
GUI retains at most 240 plotted scores.

## Outputs and replay

Default outputs go to a new timestamped directory under
`data/experiments/detector/`. `--output-dir` selects a new empty directory.
`detector.json` records the model contract, runtime parameters and radio
snapshot; `predictions.jsonl` records valid scores, per-seed values, coverage,
window/run generation and processing time, plus insufficient-data/error events.
The acquisition service retains its original raw gateway journals there.
These are not participant collection sessions. Shutdown does not promise
power-loss durability or processing of every pending inference window.

Replay one accepted attempt without opening hardware:

```sh
.venv/bin/fall-detect --model data/models/four_rx_v1 \
  --replay-session data/raw/sessions/20261104T081805521126Z \
  --attempt 192/01 --offset 0
```

Replay verifies CSI/sidecar row alignment, transmitter/receiver identities,
profile, clock epochs and recording boundaries. It uses the production native
builder and the exact ensemble. It reads raw inputs without changing them.

## Verification and measured limits

The simultaneous model path was exercised with
`tools/processing/check_multi_phase_runtime.py --rate-hz 120` using synthetic native
records and both the existing fall scorer and all 12 phase models. A fixed-deadline
producer delivered 7,668 records in 16.0 s, about 119.80 records/s per receiver
against a requested 120/s, with three missed producer rounds. All 48 phase rows
were available, 44 fall predictions were produced, and both worker queues ended
empty with no reported overflows. The phase queue peaked at 543 entries and
combined callback p99 was 0.111 ms. An earlier producer that scheduled each
round relative to the last actual call reached only 110.6/s. Neither short
synthetic observation qualifies hardware acquisition, prolonged operation,
model accuracy or latency.
The phase table was also checked in an offscreen synthetic GUI. Shared
resampling reproduced every saved array and provenance for four real recordings
across all three durations.

The full repository suite passes **588 tests**. Native tests check vector/scalar
agreement, NaNs/infinities and tail elements, half-open windows, lag support,
mask/channel order and rejection of late availability; strict Clippy passes.
Python tests cover model hashes, radio order, isolated scoring, generation and
freshness rules, quality gating, startup cleanup and CLI modes.

The historical `tools/processing/benchmark_live_detector.py` run checked four accepted
attempts at all five trained offsets, including the missed fall `192/01`: raw
inputs matched saved arrays within 1e-6, normalized inputs within 1e-5,
phase-change coverage within 1e-12, and ensemble scores within 1e-6. The replay
score for `192/01` was 0.141641. The source experiment artifacts and saved
arrays are no longer in the repository, so this parity run needs an external
copy of that artifact directory.

On this Ryzen 7 PRO 4750U, 15 repetitions of the same cached recorded window
gave the following medians. Native-window times exclude one-time packet
feature preparation. Replay-call times include rebuilding those features and
the Python-to-Rust argument handoff, but exclude disk loading and CNN scoring.
The NumPy comparison starts from cached packet log amplitudes and times only
binning/normalization; it is not an end-to-end acquisition benchmark.

| Implementation | Native window | Replay call |
| --- | --- | --- |
| Scalar, one worker | 2.94 ms | 10.95 ms |
| AVX2, one worker | 2.36 ms | 10.56 ms |
| AVX2, two workers | 1.38 ms | 9.51 ms |
| Cached NumPy binning/normalization | 46.77 ms | — |

The eight-second synthetic runtime check submitted 2,872 record references,
produced 12 native windows and 11 scores, and observed zero overflows or
skipped inference jobs. Native processing continued for two windows during a
350 ms Python GIL hold. Median window construction was 1.44 ms and median
three-model inference was 3.04 ms. The real GUI also completed an offscreen
synthetic lifecycle check. These checks do not measure radio throughput or
fall-detection accuracy. A subsequent real live test exposed confident false
candidates and missed falls reported by the operator; see the
[live-model diagnosis](reports/live-model-diagnosis-2026-11-04.md). Its input arithmetic
matched offline replay, while receiver conditions shifted substantially.

Local evidence, when present, is saved under
`data/experiments/detector/parity-benchmark.json` and
`data/experiments/detector/runtime-check/`. Run the parity benchmark with an
external copy of the experiment artifacts; the synthetic runtime check needs
no experiment directory:

```sh
.venv/bin/python tools/processing/benchmark_live_detector.py --experiment /path/to/four_rx_v1
QT_QPA_PLATFORM=offscreen .venv/bin/python tools/processing/check_live_detector_runtime.py
```

Before interpreting candidates as alarms, evaluate independently annotated
continuous recordings from new sessions, with ordinary non-fall activity.
Select thresholds and any event persistence/cooldown policy on validation
recordings, then measure missed events, false alarms per hour and detection
delay on a separate evaluation set.
