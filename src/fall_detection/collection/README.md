# CSI and optional video collection

The collector records operator-confirmed attempts from four C5 sensing
receivers through the C6 ESP-NOW gateway. The default C6 UART relay carries
transmitter control and timing. Only the gateway needs laptop USB data;
receivers, transmitter and companion need power.

The current ports, inventory, 120 Hz profile and upload policy all come from
`configs/radio.json`:

```sh
uv sync --extra radio
uv run fall-collection
```

Use `--config <file>` for another setup. Collection protocol, output directory
and optional camera remain explicit session choices. At startup, choose a
scenario protocol JSON in the file picker, then enter session metadata and
select scenario blocks. The picker opens at `configs/collection/fall_simple.json`,
the four-direction, nine-transition protocol with 116 conditions and 232 trials.
Its queue groups clear-floor, chair, chair-and-mattress, and mattress setups,
with chair orientations grouped across activities. See the
[collection configuration](../../../configs/collection/README.md) for the matrix
and setup order. The earlier eight-direction `fall_v1.json` remains selectable. Canceling the picker
exits before radio or camera initialization. Use `--protocol <file>` to select
a protocol directly and skip the picker.

The inventory and profile are read-only session inputs. Use a profile matching
the provisioned hardware; band/channel/profile changes require provisioning.
The operator confirms the planned activity during ACTION and accepts, retries
or skips each attempt after recovery. The session manifest pins the inventory,
profile, transport policy and receiver identities. CSI attempts remain artifact
schema 2 with immutable receiver-specific recordings and timing sidecars.

An interrupted radio link reconnects automatically while the collector remains
open. Sensing resumes with a fresh run and timing reference; an active attempt
is retained as invalid and requires Retry or Skip. See
[automatic recovery](../../../docs/automatic-radio-recovery.md) for firmware
requirements and tested outage behavior.

Resume an existing session after closing its collector window:

```sh
uv run fall-collection --resume-session data/raw/sessions/<session-id>
```

This restores the saved protocol, metadata, camera settings and first unresolved
trial. Completed recordings remain unchanged, and retries get new attempt
directories. Radio timing always starts a fresh run. The specific USB-buffer
age interruption now reconnects automatically while the collector stays open.

Recording data is buffered in a bounded 32 MiB memory pool and written by a
background thread every five seconds. Adjust this with
`--recording-flush-seconds 5`. Attempt acceptance waits for saving to finish;
normal shutdown drains pending data. A crash can lose unflushed data. See the
[recovery guide](../../../docs/automatic-radio-recovery.md) for precise acceptance
and resume behavior.

To record a phone camera through DroidCam USB, install the `video` extra and
append `--video-device /dev/video2` (using the actual DroidCam V4L2 device).
Optional `--video-width`, `--video-height` and `--video-fps` default to
1280×720 at 30 requested fps. A live camera viewfinder appears below the CSI
plots during warm-up, recording and between attempts; drag its divider to resize
the view. The camera records every attempt's countdown,
action and recovery. It adds `camera.mp4`, `camera_frames.csv` and `video.json`
to the attempt root. Video uses the same host monotonic timeline as CSI, with
explicitly unknown phone exposure latency. No inference model is loaded.

See [video recording](../../../docs/video-recording.md) for USB setup,
synchronization limits and hardware validation, and the
[dataset format](../../../docs/dataset-format.md) for artifact fields.

Implementation ownership, shared modules, cleanup ordering and performance checks
are documented in [live applications](../../../docs/live-applications.md).

## Continuous activity recording

For CSI-only recording without trial prompts, run:

```sh
uv run fall-collection --continuous --segment-seconds 300 --segments 288
```

Enter the session metadata. Recording
starts when the inputs are ready. Each five-minute segment is saved and accepted
without an operator action; the default limit of 288 segments is 24 hours of
nominal segment time. End Session or closing the window stops collection. The
last partial attempt is retained as incomplete. Choose different positive
values for segment length and count as needed.

Segments use the usual session and attempt files. Their activity label is
`non_fall`; individual activities are not labeled. The label records the
intended session class and does not automatically verify that no fall occurred. The automatic action phase is a recording
interval, not an observed movement boundary.

Saving and draining take time between segments. `events.jsonl` records
`continuous_gap_started` and `continuous_gap_ended` with host monotonic
timestamps for these pauses and interruptions. An interrupted attempt remains
invalid, including any partial data; after recovery the collector retries with
a new attempt number. These events identify collector pauses, not individual
lost CSI packets or all radio outages. A crash may leave an open gap or an
unfinished attempt. Resume a session using the usual `--resume-session` command;
its saved protocol selects continuous mode automatically. Clock epochs across
host restarts must be interpreted using the session resumption metadata.
Continuous mode does not currently support video. Long-duration hardware and
GUI endurance for this mode remain unverified.
