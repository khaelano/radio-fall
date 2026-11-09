# Live viewer and collection code

The viewer and collector share radio setup, buffer selection, plotting and
transport diagnostics. Their entry points compose those modules. Collection
activities, artifact writing and trial timing remain in the existing collection
controller and capture modules.

| Module | Responsibility |
| --- | --- |
| `radio/live.py` | Resolve settings, validate and bind acquisition, share receiver buffers, snapshot session settings, stop acquisition |
| `radio/acquisition/recovery.py` | Classify recoverable interruptions, verify gateway identity and request a fresh idle relay epoch |
| `src/native/radio_core/`, `radio/acquisition/native.py` | Native USB drain, ordered parallel decode, SIMD statistics/phase and bounded Python handoff |
| `radio/acquisition/recording_io.py` | Native bounded recording worker; periodic batched disk writes |
| `radio/visualization/live.py` | Compose the dashboard and transport panel; limit diagnostics to four updates per second |
| `radio/visualization/pacing.py` | Shared display rates and timer intervals |
| `radio/visualization/rendering.py` | Numerical preparation and a bounded one-snapshot/one-frame cache |
| `radio/visualization/gaps.py` | Receiver-by-time heatmap of CSI availability at delivery deadlines |
| `collection/app.py` | Parse options, gather metadata, compose the controller and windows, enter the Qt event loop |
| `collection/runtime.py` | Evaluate health, advance trial timing, update both windows and drain a run on exit |
| `collection/views/` | Setup/detail dialogs, operator controls, performer cues and presentation styles |
| `collection/controller.py`, `capture.py` | Collection state transitions and immutable recording artifacts |

`LiveRadio` binds configured identities without opening hardware. Its `start`
method runs only after recording sinks and the UI are ready. Both applications
register cleanup before starting acquisition. The collector ends the current
attempt, stops/drains radio acceptance and flushes pending records before its
outer resource scope closes the camera. Cleanup continues if an earlier cleanup
raises. Canceling setup also releases an initialized camera. Closing the operator
console exits collection even while performer guidance is open.

During an interrupted live link, `LiveRadio` retires the failed manager before
creating a new radio run. It replaces clock estimators and receiver buffers,
preserving selected receiver identity. Its failure callback invalidates an
active collection attempt immediately, without depending on a display tick.
The presenter reconciles current controller health after a paused GUI resumes;
telemetry reads the current manager rather than a method bound to an ended run.
See [automatic radio recovery](automatic-radio-recovery.md) for retry policy,
transport journal links and controlled hardware checks.

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
while the next window prepares. Optional plotting yields to USB input older than
25 ms or queues over eight chunks; the separate 200 ms acquisition limit remains.
See the [live backlog investigation](reports/gateway-preview-backlog-2026-11-03.md).
The live POSIX path now prepares CSI in Rust and measures the 200 ms deadline
there, with separate completed-frame wait diagnostics. See the
[native processing design](rust-radio-pipeline.md) for thread ownership,
build instructions and timing semantics.
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

The heatmap reads the existing acquisition availability grid. Its bin width and
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

The grid retains a bounded ten-second count history. The UI copies counts
without advancing the grid, changing recording or calculating phase. It updates
only the active gap tab, at most four times per second, and respects the existing
USB backlog pause. Time advances during receiver silence while preview is
allowed. Automatic recovery switches to the new run's grid and clears the old
history. Software tests cover deadlines, late packets, silence, bounded history,
receiver rows, backlog pauses and recovery; live hardware load remains unmeasured.

## Verification and performance scope

Tests exercise the shared radio interface with an offline manager, complete Qt
entry points with real offscreen windows, partial startup and shutdown failures,
receiver selection, cache invalidation and immediate health-loss handling. The
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
  -m fall_detection.radio.visualization.benchmark \
  --view controls --frames 80 --points 1200

uv run pytest -q
```

The benchmark emits median/p95 refresh time and snapshot calls, including warmup.
It uses synthetic data without opening hardware or writing recordings. Fresh-data
and receiver-switching tests are separate from this warmed-cache benchmark; their
hardware evidence is in the backlog investigation. Camera load and longer hardware
soaks remain separate qualification tasks.
