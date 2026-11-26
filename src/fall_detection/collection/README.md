# CSI and optional video collection

The collector records operator-confirmed attempts from four C5 sensing
receivers through the C6 ESP-NOW gateway. The default C6 UART relay carries
transmitter control and timing. Only the gateway needs laptop USB data;
receivers, transmitter and companion need power.

The current ports, inventory, 120 Hz profile and upload policy all come from
`configs/radio.json`:

```sh
uv sync --extra radio
uv run csi-sessions
```

`csi-sessions` opens on the session browser. Press **New session** (Ctrl+N) in
the toolbar, or start with `csi-sessions --new`. One form asks for the
recording mode, the scenario protocol, the session details, the scenario blocks
and the camera, and shows the radio profile and gateway in use. The protocol
list offers the JSON files beside `configs/collection/fall_simple.json`, the
four-direction, nine-transition protocol with 116 conditions and 232 trials;
**Browse…** opens another file. Its queue groups clear-floor, chair,
chair-and-mattress, and mattress setups, with chair orientations grouped across
activities. See the [collection configuration](../../../configs/collection/README.md)
for the matrix and setup order. Canceling the form opens no radio or camera.
Command-line options such as `--protocol <file>` only preselect values in the
form. New sessions are written to `--sessions-dir` (default
`data/raw/sessions`), the folder the browser lists. Use `--config <file>` for
another radio setup.

The inventory and profile are read-only session inputs. Use a profile matching
the provisioned hardware; band/channel/profile changes require provisioning.
The operator confirms the planned activity during ACTION and accepts, retries
or skips each attempt after recovery. The session manifest pins the inventory,
profile, transport policy and receiver identities. Attempts remain artifact
schema 2; each attempt directory holds only `attempt.json` (and video files when
a camera is enabled).

During recording, the native writer compresses the session event log directly
into complete Zstandard frames in `.zst` files. Compression
happens on the disk worker at each configured flush; no plain stream copy is
written. Small mutable JSON metadata and video frame indexes remain plain.

The Rust transport journal in the session directory is the only raw record of
the radio data and is included in the archive. Conversion assigns its frames to
attempts by capture time, so frames that arrive after an attempt ends still
belong to it. Collectors before 18 November 2026 also wrote per-receiver
`csi.csv`, `radio_timing.csv`, `usb_clock_sync.csv` and `gateway_timing.jsonl`
sidecars; they were removed after a hardware session matched them frame for frame
([status report](../../../docs/reports/architecture-rehaul-status-2026-11-13.md#update-18-november)),
which made new archives about half as large. The comparison tool,
`tools/processing/check_storage_equivalence.py`, was then retired (last present
at commit `af07916`). The session manifest records `environment.csv_sidecars:
false`. Older sessions keep their sidecars and can still be resumed. The journal writes and flushes each envelope to the operating system
before the gateway ACK (no fsync), so a process crash loses no accepted frame.
The live view of `csi-live` keeps no recording of its own.

When the operator closes the collection console, `csi-sessions` drains and
closes acquisition and video, then saves a verified `<session-id>.zip` raw
recording beside its working directory. Version-2 archives retain the `.zst` bytes directly and expose logical
file names through the shared reader. The archive includes every original file and compressed Parquet
receiver tables. Finalization may take several minutes for large sessions;
a progress dialog stays open until it finishes, and the browser then returns
with the new archive selected and `Saved raw recording` in its status bar. The working
directory is retained for recovery and resume. A resumed session saves a new
numbered archive revision. See the [raw archive contract](../../../docs/archive/session-archive-pilot.md)
and `fall_detection._radio_native.storage_extract_archive` for verified extraction.

An interrupted radio link reconnects automatically while the collector remains
open. Sensing resumes with a fresh run and timing reference; an active attempt
is retained as invalid and requires Retry or Skip. See
[automatic recovery](../../../docs/automatic-radio-recovery.md) for firmware
requirements and tested outage behavior.

## Editing the protocol while recording

Between trials, press **Edit…** above the protocol queue in the collection
console. The editor lists every trial; the trials already recorded, and the
current one once it has an attempt, are greyed out and stay as they are. For
the remaining trials you can:

- reorder them (**Do next**, **Move up**/**Move down** or Ctrl+↑/↓, **Move to end**),
- remove them (Delete) or add copies (**Duplicate**, Ctrl+D),
- add trials of scenarios the session does not contain (**Add from protocol…**):
  pick scenarios from this session's starting protocol, the file the session
  was set up from, any protocol in `configs/collection/`, or another file, for
  example a block not selected at setup; choose how many trials each adds,
- define a scenario by hand (**New scenario…**: title, label, instruction,
  block, timing and number of trials),
- change the label, title, instruction or countdown/action/recovery seconds of
  every selected trial at once.

New trials go after the selected trials, or at the end without a selection.
**Save as protocol file…** writes the queue as shown, including the recorded
trials, to a new protocol file with its own id for later sessions; it does not
change the session.

Add a reason and press **Save revision**. The revision is saved in the session
before it takes effect; the queue, the trial count and the performer cues follow
it at once. Removing every remaining trial completes the session. Editing is
disabled during countdown, action and recovery, and in continuous mode.

Recorded attempts keep the label that was planned when they ran; correct those
in the session review afterwards. The starting `protocol.json` and the session's
`protocol_hash` never change: each revision is a new file under
`protocol_revisions/`, listed with its reason and a summary of the changes in
`session.json` and the event log. When a scenario that already has a recorded
trial is relabeled for later trials, those trials get a new scenario id
`<id>__rev<n>` that names the original. An added scenario whose id or block id
is already used for something else gets a suffix naming its source protocol.
Resume continues from the last revision. See the [dataset format](../../../docs/dataset-format.md#protocol-revisions-made-while-recording).

To resume an existing session, select its working folder (not the `.zip`)
in the browser and press **Resume recording**, or run:

```sh
uv run csi-sessions --resume-session data/raw/sessions/<session-id>
```

This restores the saved protocol, metadata, camera settings and first unresolved
trial. Completed recordings remain unchanged, and retries get new attempt
directories. Radio timing always starts a fresh run. The specific USB-buffer
age interruption now reconnects automatically while the collector stays open.

Recording data is buffered in a bounded 32 MiB memory pool and written by a
background thread every five seconds. Adjust this with
`--recording-flush-seconds 5`. Clicking Accept while recording or video saves
are pending queues the decision immediately. The UI remains responsive, displays
the queued decision, and advances automatically when saving completes. The next
trial becomes available after that completion; accepted metadata is never
published before the recording has saved successfully. Retry, Skip and End
Session cancel the queued decision. A queued decision is in memory, so closing
the collection console before it completes leaves the attempt incomplete. Normal shutdown
drains pending data. A crash can lose unflushed data. See the
[recovery guide](../../../docs/automatic-radio-recovery.md) for precise acceptance
and resume behavior.

To record a phone camera through DroidCam USB, select its V4L2 device in the
**Camera** field of the setup form, or preselect it with
`--video-device /dev/video2` (using the actual DroidCam device). Optional
`--video-width`, `--video-height` and `--video-fps` default to 1280×720 at 30
requested fps. A live camera viewfinder appears below the CSI
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

For CSI-only recording without trial prompts, choose **Continuous activity
segments** in the setup form and set the segment length and count, or preselect
them:

```sh
uv run csi-sessions --new --continuous --segment-seconds 300 --segments 288
```

Enter the session details. Recording
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
unfinished attempt. Resume such a session like any other; its saved protocol
selects continuous mode automatically. Clock epochs across
host restarts must be interpreted using the session resumption metadata.
Continuous mode does not currently support video. Long-duration hardware and
GUI endurance for this mode remain unverified.
