# Synchronized collection video

The collector can record an optional phone-camera video for every attempt.
The operator still confirms and labels the activity. Video recording does not
run YOLO, pose estimation, or another inference model, and does not change
radio firmware or transport settings.

## DroidCam over USB

On Linux the collector opens the local V4L2 webcam created by the DroidCam
client. Connect the phone by USB, start the phone app, and select USB in the
DroidCam desktop client. Android USB mode requires USB debugging and an
authorized ADB connection; the Linux client uses a V4L2 loopback driver to
provide the webcam. Follow the [official Linux instructions](https://www.dev47apps.com/droidcam/linux/)
for the appropriate app/client version and driver setup.

Select the DroidCam device explicitly, for example `/dev/video2`. Device
numbers can change, so verify its identity in the client or with
`v4l2-ctl --list-devices` if that utility is installed. The collector does not
choose the integrated webcam automatically or manage the phone's USB link.
A V4L2 device alone does not prove whether the upstream client uses USB or Wi-Fi.

Install the optional recording dependency:

```sh
uv sync --extra radio --extra video
```

Add video options to the existing collection command. For the currently
provisioned four-C5 120 Hz setup:

```sh
uv run --extra radio --extra video fall-collection \
  --config configs/radio.json \
  --protocol configs/collection/fall_v1.json \
  --video-device /dev/video2 \
  --video-width 1280 --video-height 720 --video-fps 30
```

Match the requested camera size/rate to the DroidCam virtual webcam's supported
settings. The example requests 720p/30 fps; it is not a measured phone result.
`--video-fps` is independent of the dashboard's `--fps`. Omitting
`--video-device` keeps CSI-only collection and does not require PyAV.

The camera warms up while the collection window is open. No video is saved
until an attempt begins. With `--video-device` enabled, a live camera viewfinder
appears below the operator's CSI plots, including during warm-up and between
attempts. Drag the divider to resize the camera area; images retain their aspect
ratio. The preview uses the recorder's existing camera connection. It clears
the last image and shows camera status when the frame stream becomes stale or
the worker fails. The health strip must show video ready before starting
an enabled-video attempt. It records countdown, action and recovery, then
finishes the clip on review, abort or session end. Retries use separate files.
A stale frame stream or camera worker failure invalidates an active attempt.
An attempt cannot be accepted while its video is finalizing or after a failed
or empty clip. Finalization that cannot complete within three seconds fails
the recorder instead of leaving review waiting indefinitely. Reconnect the phone and restart the collector after a camera
worker failure; partial attempts are retained.

## Timing and alignment

Both video observations and CSI reference mappings use host monotonic time.
For each video frame, the recorder retains read-start/read-completion timestamps
and the original decoder PTS/time base. Source PTS are preserved as evidence;
they are not assumed to be phone exposure times or mapped to the host clock.
The encoded presentation timestamp uses:

```text
presentation_pts = floor((host_read_completed_ns - attempt_start_ns) / 1000)
host_observation_ns ≈ attempt_start_ns + presentation_pts × 1000
```

The encoder time base is one microsecond. Presentation gaps remain gaps rather
than compressing the timeline to an assumed constant frame rate. Player
interfaces may rebase a clip to its first frame; use `camera_frames.csv` for
alignment. CSI keeps its sensing/capture timestamp and clock uncertainty;
USB arrival time is not substituted for sensing time.

Recording and encoding run in a separate process. A bounded 100 ms observation
buffer allows in-flight attempt markers to trim clip boundaries; its maximum
is 32 frames. That encoder holdback does not change recorded observation times.
Camera/encoder failure does not block CSI callbacks, and shutdown terminates a
camera process that cannot finish a blocked read. File-buffer acceptance is
not power-loss durability.

The viewfinder downsamples images to fit within 480×270 pixels at at most ten
updates per second. A single shared-memory image slot replaces older preview
frames; capture and the UI skip a busy slot instead of waiting. Preview pixels
do not pass through the recording control/status queues. Preview resolution and
refresh rate do not change the requested recording dimensions, frame rate or
timestamps. Omitting `--video-device` keeps the CSI-only window layout.

DroidCam can buffer or repeat images before the laptop receives them. Therefore
this is synchronization on the host observation timeline, not measured
exposure-level synchronization. Phone pipeline latency is recorded as unknown.
Before using video for precise fall-onset labels, measure end-to-end camera
latency with a visible timing reference in the intended setup. The current
health gate detects missing host frames, not fresh phone exposure or duplicate
images.

## Artifacts and validation

Each enabled attempt adds `camera.mp4`, `camera_frames.csv` and `video.json`
beside `attempt.json`; CSI remains under the receiver directories. See the
[dataset format](dataset-format.md#34-optional-video-recording) for the fields.
H.264 video contains no audio, inference results, or model annotations.
Rejected, aborted and incomplete attempts retain their video artifacts.

Software tests cover real codec output, presentation timestamps with gaps,
attempt boundaries, retries, acceptance gating, input loss and bounded process
shutdown without opening a physical camera. The target DroidCam USB phone was
not connected during implementation. Phone capture, USB coexistence with the
radios, sustained recording performance and end-to-end synchronization accuracy
remain to be measured with that hardware.
Viewfinder tests also cover the spawned-process image handoff, bounded latest
image storage, warm-up before recording, aspect-preserving display and clearing
the image after camera health loss. These offline checks do not qualify camera
preview load alongside live radio acquisition.

## Recorded-session playback

Open a recording in the session inspector and select an attempt's **Signals**
tab. The video appears beside the six CSI plots. Play/pause advances a shared
attempt-time cursor; the slider scrubs, and the frame buttons step between
actual recorded observations. Click a plot or drag its orange cursor to seek
the video. Changing receivers retains the video position. Changing attempts
stops playback and clears the previous clip.

```sh
uv sync --extra radio --extra video
uv run --extra radio --extra video fall-session-inspector --sessions-dir data/raw/sessions
```

Playback reads `video.json`, `camera_frames.csv` and `camera.mp4` without editing
them. It uses the sidecar's host observation times and exact presentation PTS,
including a delayed first frame and irregular gaps. It does not assume constant
FPS or rebase the first frame to zero. During a gap the latest earlier frame
remains visible; its recorded time and age relative to the cursor are shown.
An incomplete but finalized clip is marked as incomplete. Missing video,
unfinalized clips and invalid timing produce an explicit message while CSI
inspection remains available.

CSI plot times use mapped capture timestamps from the gateway/BLE timing
sidecar, or a saved USB receiver-to-host clock fit. Derived plots are sorted on
that clock and start at the attempt's host start time; raw table order stays
unchanged. If only host receipt timestamps are available, the plot explicitly
labels them as receipt time rather than sensing time. Without a validated host
timeline, plots retain their receiver-relative axis and no shared video cursor
is shown. Heatmap display cells retain missing time intervals instead of
compressing packet gaps.

A dedicated decoder thread retains one pending seek, one result and one RGB
preview bounded to 640×360. Sequential playback reuses the decoder; backward
or distant seeks use keyframes and verify the decoded frame's PTS. Codec work
does not run in the GUI thread, and stale results cannot restore a previous
attempt's image. PyAV is loaded only when opening video; CSI-only sessions do
not require it.

Tests cover real H.264 decoding with delayed/irregular frame PTS, backward and
forward seeks, scrubbing, frame stepping, invalid timing, missing video, clock
alignment and cursor/worker lifecycle. A read-only check of attempt `001/02`
in `20261104T081805521126Z` opened its 471-frame clip and all four receiver
views, verified frame stepping and shared cursors, and left all 12 checked raw
files hash-identical. Local evidence is in
`data/experiments/session_inspector/video-smoke/`. These checks establish saved
host-timeline playback, not exposure-level camera synchronization.
