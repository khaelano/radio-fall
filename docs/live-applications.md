# Live viewer and collection code

The viewer and collector share radio setup, buffer selection, plotting and
transport diagnostics. Rust owns the radio session; Python moves accepted
records to recording sinks and display buffers. Collection activities, artifact
writing and trial timing remain in the collection controller and capture modules.

| Module | Responsibility |
| --- | --- |
| `radio/live.py` | Resolve settings, start `NativeAcquisition`, deliver accepted records to sinks and receiver buffers, map native health to status, diagnostics and telemetry |
| `radio_transport::session` (`src/native/radio_core/`) | Gateway preparation and relay recovery, startup, journal-before-ACK acceptance, capture mapping, availability bins, restarts |
| `radio_transport::quality`, `radio/acquisition/native.py` | Duplicate-capture removal and delivery counters; Python record adapter with lazy array views |
| `radio/acquisition/recording_io.py` | Native bounded recording worker; periodic batched disk writes |
| `presentation/radio/live.py` | Compose the dashboard and transport panel; limit diagnostics to four updates per second |
| `presentation/radio/pacing.py` | Shared display rates and timer intervals |
| `radio/preprocessing/rendering.py` | Numerical preparation and a bounded one-snapshot/one-frame cache |
| `presentation/radio/gaps.py` | Receiver-by-time heatmap of CSI availability at delivery deadlines |
| `apps/collector/app.py` | Parse options, gather metadata, compose the controller and windows, enter the Qt event loop |
| `apps/collector/runtime.py` | Evaluate health, advance trial timing, update both windows and drain a run on exit |
| `apps/collector/views/` | Setup/detail dialogs, operator controls, performer cues and presentation styles |
| `collection/controller.py`, `capture.py` | Collection state transitions and immutable recording artifacts |

`LiveRadio` binds configured identities without opening hardware. Its `start`
method runs only after recording sinks and the UI are ready. Both applications
register cleanup before starting acquisition. The collector ends the current
attempt, stops/drains radio acceptance and flushes pending records before its
outer resource scope closes the camera. Cleanup continues if an earlier cleanup
raises. Canceling setup also releases an initialized camera. Closing the operator
console exits collection even while performer guidance is open.

During an interrupted live link, the native session ends the failed run and
starts a new run with a fresh identity, journal and clock fit. `LiveRadio`
keeps the receiver buffers and selected receiver. Its interruption callback
fires once per failed run, so an active collection attempt is invalidated
without depending on a display tick. Telemetry counters are cumulative across
runs. See [automatic radio recovery](automatic-radio-recovery.md) for retry
policy and transport journal links.

The collector's presenter checks current radio/video health every display tick.
Scheduled upload gaps retain their existing readiness semantics. Unchanged
health does not republish a duplicate controller notification. Diagnostics run
at most every 250 ms, with an immediate update when the selected receiver changes.
Filesystem readiness checks run once per second against the output directory or
its nearest existing parent. Actual recording failures remain authoritative;
this readiness check is advisory.

Preview work remains optional when acquisition falls behind. The render cache
holds only one receiver/window snapshot and one prepared frame. It reuses arrays
when display controls change without new CSI. Receiver, window, phase-mode or
buffer-content changes invalidate the appropriate cache. Cold LTF preparation is
spread across ticks (at most 16 records / about 8 ms per tick), so receiver
switches do not prepare a whole window at once. Old receiver traces are cleared
while the next window prepares. Optional plotting pauses while more than 512
accepted records await Python delivery; acquisition, journaling and ACKs do not
wait for Python. See the [live backlog investigation](reports/gateway-preview-backlog-2026-11-03.md)
for the earlier USB-queue policy and the
[native processing design](rust-radio-pipeline.md) for thread ownership.
Buffer receive counts
identify changes even when sequence IDs repeat or restart. Raw recording,
calibration, timestamp mapping, missing values and recorded CSI are independent
of the preview cache.

## CSI gap heatmap

Both `csi-viewer` and `fall-collection` include a **CSI gaps** tab. Each row is
one configured receiver; columns follow a common synchronized capture-time axis
relative to the current host monotonic time. The window control selects one to
ten seconds of history. The receiver selector still selects the phase/amplitude
stream; the gap tab always compares all receivers.

The heatmap reads the availability grid of the current native run. Its bin width and
delivery allowance come from `transport.bin_hz` and `transport.delivery_grace_ms`
in `configs/radio.json`: the current settings use 20 ms bins and a deadline
900 ms after each bin ends. Colors distinguish:

- Green: at least one CSI record for that capture interval arrived by its deadline.
- Red: no CSI record was available by the deadline.
- Amber: an empty interval is still within its delivery allowance.
- Gray: the interval precedes the run or no timing history is available.

This shows empty time intervals, not individual missing packets or invalid phase
subcarriers. A green bin may still contain packet loss. Empty bins can include
scheduled off-channel upload pauses and late delivery; they do not identify a
physical cause. A record arriving after the deadline does not recolor a red bin,
matching the immutable causal availability journal.

The Rust grid retains a bounded ten-second count history and journals each
finalized bin to `availability.jsonl`. The UI copies counts without advancing
the grid, changing recording or calculating phase. It updates only the active
gap tab, at most four times per second, and respects the preview pause. Time
advances during receiver silence while preview is allowed. A restarted run
publishes a new grid. Rust unit tests cover deadlines, late packets and bounded
history; Python tests cover display classification, backlog pauses and grid
replacement. Live hardware load remains unmeasured.

## Verification and performance scope

Tests exercise `LiveRadio` with a scripted native acquisition, complete Qt
entry points with real offscreen windows, partial startup and shutdown failures,
receiver selection, cache invalidation and immediate health-loss handling.
`tests/radio/test_native_session.py` runs the real Rust session against a fake
gateway on a pseudo-terminal: startup, journal-before-ACK, rounds, availability,
duplicate removal, restart after lost gateway status and fatal identity mismatch.
These tests do not exercise radio timing, USB behavior or firmware. The
collector entry point decreased from 1,076 to approximately 200 lines; the
extracted views retain their existing behavior tests.

A local offscreen comparison on 3 November 2026 used 1,200 synthetic HE20 records,
a three-second visible window and 80 forced display-control refreshes after
warming the data. Median refresh work decreased from 20.50 ms to 5.59 ms; p95
was 21.15 ms before and 7.45 ms after. This excludes painting, radio acquisition
and recording, and does not establish higher live throughput or frame rates.
The cache avoids repeated snapshot construction in this specific workload.
Reproduce the current implementation's check with:

```sh
QT_QPA_PLATFORM=offscreen uv run python \
  -m fall_detection.presentation.radio.benchmark \
  --view controls --frames 80 --points 1200

uv run pytest -q
```

The benchmark emits median/p95 refresh time and snapshot calls, including warmup.
It uses synthetic data without opening hardware or writing recordings. Fresh-data
and receiver-switching tests are separate from this warmed-cache benchmark; their
hardware evidence is in the backlog investigation. Camera load and longer hardware
soaks remain separate qualification tasks.
