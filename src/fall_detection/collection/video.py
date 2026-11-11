"""Optional V4L2 video recording on the collector's host monotonic timeline.

The phone's exposure clock is not available through DroidCam. Read completion
is an observation time, not a measured exposure timestamp. Encoding runs in an
isolated process so a blocked camera/encoder cannot block CSI ingestion.
"""

from __future__ import annotations

import csv
from collections import deque
from dataclasses import asdict, dataclass
from fractions import Fraction
import importlib.util
import json
import multiprocessing
from pathlib import Path
from queue import Empty, Full
import time
from typing import Any

from .capture import _write_json

VIDEO_TIME_BASE = Fraction(1, 1_000_000)
PREVIEW_WIDTH = 480
PREVIEW_HEIGHT = 270
PREVIEW_INTERVAL_NS = 100_000_000


@dataclass(frozen=True)
class VideoPreviewFrame:
    """Small RGB image copied from the camera's latest host observation."""

    width: int
    height: int
    rgb: bytes
    observed_ns: int


class _VideoPreview:
    """One shared image slot; neither process waits for the other to use it."""

    def __init__(self, context: Any) -> None:
        self._pixels = context.RawArray("B", PREVIEW_WIDTH * PREVIEW_HEIGHT * 3)
        self._metadata = context.RawArray("q", 3)
        self._lock = context.Lock()
        self._published_ns = 0

    def publish(self, frame: Any, observed_ns: int) -> None:
        """Downsample at most ten times a second, skipping a busy image slot."""
        if observed_ns - self._published_ns < PREVIEW_INTERVAL_NS:
            return
        if not self._lock.acquire(False):
            return
        try:
            scale = min(PREVIEW_WIDTH / frame.width, PREVIEW_HEIGHT / frame.height, 1)
            width = max(1, int(frame.width * scale))
            height = max(1, int(frame.height * scale))
            rgb = frame.reformat(width=width, height=height, format="rgb24")
            pixels = rgb.to_ndarray().tobytes()
            memoryview(self._pixels).cast("B")[: len(pixels)] = pixels
            self._metadata[:] = (width, height, observed_ns)
            self._published_ns = observed_ns
        finally:
            self._lock.release()

    def read(self, after_ns: int) -> VideoPreviewFrame | None:
        """Copy a new image without waiting on capture or returning old frames."""
        if not self._lock.acquire(False):
            return None
        try:
            width, height, observed_ns = self._metadata
            if observed_ns <= after_ns:
                return None
            return VideoPreviewFrame(
                width,
                height,
                bytes(memoryview(self._pixels).cast("B")[: width * height * 3]),
                observed_ns,
            )
        finally:
            self._lock.release()


@dataclass(frozen=True)
class VideoConfig:
    """Requested DroidCam virtual-webcam settings; hardware negotiation is saved."""

    device: str
    width: int = 1280
    height: int = 720
    fps: int = 30

    def __post_init__(self) -> None:
        if not self.device.startswith("/dev/"):
            raise ValueError("video device must be an explicit /dev/ V4L2 camera path")
        if any(
            type(v) is not int or v <= 0 for v in (self.width, self.height, self.fps)
        ):
            raise ValueError(
                "video width, height and frame rate must be positive integers"
            )
        if self.width % 2 or self.height % 2 or self.fps > 120:
            raise ValueError("video dimensions must be even and frame rate at most 120")

    def metadata(self) -> dict[str, Any]:
        """Describe requested settings and the limits of host-side synchronization."""
        return {
            **asdict(self),
            "backend": "pyav-v4l2",
            "codec": "libx264",
            "timing_source": "host_monotonic_read_complete",
            "exposure_time_known": False,
            "phone_pipeline_latency_ns": None,
            "audio": False,
            "inference": False,
        }


class _AttemptVideo:
    """Encode frames with actual elapsed time, retaining gaps in presentation PTS."""

    def __init__(
        self,
        path: Path,
        start_ns: int,
        config: VideoConfig,
        source_metadata: dict[str, Any] | None = None,
    ) -> None:
        import av

        self.path, self.start_ns, self.config = path, start_ns, config
        self.source_metadata = source_metadata or {}
        self.output = None
        self.stream = None
        self.count = 0
        self.first_ns = self.last_ns = None
        self.last_pts = -1
        self.closed = False
        if (path / "camera.mp4").exists() or (path / "camera_frames.csv").exists():
            raise FileExistsError("attempt video already exists")
        self.csv_file = (path / "camera_frames.csv").open(
            "x", newline="", encoding="utf-8"
        )
        self.rows = csv.writer(self.csv_file)
        self.rows.writerow(
            (
                "frame_index",
                "presentation_pts",
                "time_base_num",
                "time_base_den",
                "host_read_started_monotonic_ns",
                "host_read_completed_monotonic_ns",
                "source_pts",
                "source_time_base_num",
                "source_time_base_den",
            )
        )
        try:
            self.output = av.open(str(path / "camera.mp4"), mode="w", format="mp4")
            self.stream = self.output.add_stream("libx264", rate=config.fps)
            self.stream.width, self.stream.height = config.width, config.height
            self.stream.pix_fmt = "yuv420p"
            self.stream.time_base = VIDEO_TIME_BASE
            self.stream.codec_context.time_base = VIDEO_TIME_BASE
            self.stream.codec_context.thread_count = 2
            self.stream.options = {
                "preset": "ultrafast",
                "tune": "zerolatency",
                "crf": "23",
                "bf": "0",
            }
        except Exception:
            self.csv_file.close()
            if self.output:
                self.output.close()
            raise
        self._publish("recording")

    def _publish(self, status: str, **updates: Any) -> dict[str, Any]:
        value = {
            "schema_version": 1,
            "status": status,
            "configuration": self.config.metadata(),
            "source": self.source_metadata,
            "video_file": "camera.mp4",
            "frame_timing_file": "camera_frames.csv",
            "attempt_started_monotonic_ns": self.start_ns,
            "frames": self.count,
            "first_frame_host_monotonic_ns": self.first_ns,
            "last_frame_host_monotonic_ns": self.last_ns,
            "time_base_num": VIDEO_TIME_BASE.numerator,
            "time_base_den": VIDEO_TIME_BASE.denominator,
            **updates,
        }
        _write_json(self.path / "video.json", value)
        return value

    def write(self, frame: Any, read_started_ns: int, read_completed_ns: int) -> None:
        """Write one frame, preserving source timing without assigning it a host clock."""
        if self.closed or read_completed_ns < self.start_ns:
            return
        pts = (read_completed_ns - self.start_ns) // 1000
        if pts <= self.last_pts:
            raise ValueError("non-increasing video observation time")
        source_pts, source_base = frame.pts, frame.time_base
        # Retain source timing before assigning output presentation timestamps.
        encoded_frame = frame.reformat(
            width=self.config.width, height=self.config.height, format="yuv420p"
        )
        encoded_frame.pts, encoded_frame.time_base = pts, VIDEO_TIME_BASE
        for packet in self.stream.encode(encoded_frame):
            self.output.mux(packet)
        self.rows.writerow(
            (
                self.count,
                pts,
                1,
                1_000_000,
                read_started_ns,
                read_completed_ns,
                "" if source_pts is None else source_pts,
                "" if source_base is None else source_base.numerator,
                "" if source_base is None else source_base.denominator,
            )
        )
        self.first_ns = read_completed_ns if self.first_ns is None else self.first_ns
        self.last_ns, self.last_pts = read_completed_ns, pts
        self.count += 1

    def finish(self, end_ns: int, error: str | None = None) -> dict[str, Any]:
        """Finalize the container before publishing a complete video sidecar."""
        if self.closed:
            raise RuntimeError("attempt video already closed")
        self.closed = True
        try:
            for packet in self.stream.encode():
                self.output.mux(packet)
            self.output.close()
        except Exception as exc:
            error = error or str(exc)
        finally:
            self.csv_file.flush()
            self.csv_file.close()
        if not self.count:
            error = error or "no video frames recorded"
        if self.last_ns is not None and self.last_ns >= end_ns:
            error = error or "frame observation exceeded the attempt end boundary"
        return self._publish(
            "failed" if error else "complete", ended_monotonic_ns=end_ns, error=error
        )


def _flush_frames(attempt: _AttemptVideo, pending: deque, before_ns: int) -> None:
    """Commit observations before a boundary; later frames stay outside the clip."""
    while pending and pending[0][2] < before_ns:
        frame, started, completed = pending.popleft()
        attempt.write(frame, started, completed)


def _video_worker(
    config: VideoConfig,
    commands: Any,
    events: Any,
    last_frame: Any,
    preview: _VideoPreview | None = None,
) -> None:
    """Own capture/encoding and publish optional images outside the control queues."""
    source = attempt = None
    try:
        import av

        source = av.open(
            config.device,
            format="video4linux2",
            options={
                "video_size": f"{config.width}x{config.height}",
                "framerate": str(config.fps),
            },
        )
        stream = source.streams.video[0]
        stream.thread_type = "SLICE"
        stream.codec_context.thread_count = 1
        source_metadata = {
            "width": stream.width,
            "height": stream.height,
            "rate": str(stream.average_rate),
            "pyav_version": av.__version__,
        }
        events.put_nowait(("opened", source_metadata))
        pending: deque = deque()
        frames = source.decode(video=0)
        while True:
            read_started = time.monotonic_ns()
            frame = next(frames)
            read_completed = time.monotonic_ns()
            last_frame.value = read_completed
            pending.append((frame, read_started, read_completed))
            if len(pending) > 32:
                raise BufferError("video boundary buffer overflow")
            # Apply start/end boundaries before writing the just-read frame.
            # A frame arriving after an end marker never leaks into that attempt.
            while True:
                try:
                    command = commands.get_nowait()
                except Empty:
                    break
                kind, path, boundary = command
                if kind == "begin":
                    if attempt is not None:
                        raise RuntimeError("video attempt overlap")
                    attempt = _AttemptVideo(
                        Path(path), boundary, config, source_metadata
                    )
                elif kind == "end":
                    if attempt is None or str(attempt.path) != path:
                        raise RuntimeError(
                            "video end marker does not match active attempt"
                        )
                    _flush_frames(attempt, pending, boundary)
                    result = attempt.finish(boundary)
                    attempt = None
                    events.put_nowait(("finished", {"path": path, "result": result}))
                elif kind == "shutdown":
                    if attempt is not None:
                        _flush_frames(attempt, pending, boundary)
                        attempt.finish(boundary, "recorder stopped during attempt")
                    return
                else:
                    raise ValueError("unknown video command")
            # Hold observations briefly so in-flight start/end markers can trim
            # boundaries. Encoding delay never replaces the observation time.
            cutoff = read_completed - 100_000_000
            if attempt is not None:
                _flush_frames(attempt, pending, cutoff)
            else:
                while pending and pending[0][2] < cutoff:
                    pending.popleft()
            if preview is not None:
                preview.publish(frame, read_completed)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if attempt is not None and not attempt.closed:
            attempt.finish(time.monotonic_ns(), error)
        try:
            events.put_nowait(("failed", {"error": error}))
        except Full:
            pass
    finally:
        if source is not None:
            source.close()


class VideoRecorder:
    """Isolate phone capture and encoding from CSI callbacks and the GUI thread."""

    def __init__(self, config: VideoConfig) -> None:
        if importlib.util.find_spec("av") is None:
            raise RuntimeError(
                "Install video support with: uv sync --extra radio --extra video"
            )
        self.config = config
        context = multiprocessing.get_context("spawn")
        self._commands = context.Queue(maxsize=8)
        self._events = context.Queue(maxsize=32)
        self._last_frame = context.Value("q", 0)
        self._preview = _VideoPreview(context)
        self._preview_seen_ns = 0
        self._process = context.Process(
            target=_video_worker,
            args=(
                config,
                self._commands,
                self._events,
                self._last_frame,
                self._preview,
            ),
            daemon=True,
        )
        self.failure: str | None = None
        self.negotiated: dict[str, Any] = {}
        self._pending: dict[str, int] = {}
        self._finishing: dict[str, int] = {}
        self._started = False
        self._closed = False
        self._stopping = False

    def start(self) -> None:
        """Begin camera warm-up; no video is saved until an attempt starts."""
        self._process.start()
        self._started = True

    def _poll(self) -> None:
        if self._closed:
            return
        while True:
            try:
                kind, values = self._events.get_nowait()
            except Empty:
                break
            if kind == "opened":
                self.negotiated = values
            elif kind == "failed":
                self.failure = values["error"]
            elif kind == "finished":
                self._pending.pop(values["path"], None)
                self._finishing.pop(values["path"], None)
        if (
            self._started
            and not self._stopping
            and not self._process.is_alive()
            and not self.failure
        ):
            self.failure = "camera worker stopped"
        if not self.failure and any(
            time.monotonic_ns() - ended > 3_000_000_000
            for ended in self._finishing.values()
        ):
            self.failure = "video finalization timed out; camera may have stopped delivering frames"
            if self._process.is_alive():
                self._process.terminate()
        if self.failure:
            self._fail_pending(self.failure)

    def _fail_pending(self, error: str) -> None:
        for name in self._pending:
            path = Path(name) / "video.json"
            value = json.loads(path.read_text())
            if value["status"] not in ("complete", "failed"):
                value.update(status="failed", error=error)
                _write_json(path, value)
        self._pending.clear()
        self._finishing.clear()

    @property
    def ready(self) -> bool:
        """Require an alive worker and a frame observed in the last two seconds."""
        self._poll()
        return bool(
            self._started
            and not self.failure
            and self._last_frame.value
            and 0 <= time.monotonic_ns() - self._last_frame.value < 2_000_000_000
        )

    @property
    def detail(self) -> str:
        """Return an operator-readable camera health message."""
        return self.failure or (
            "video ready" if self.ready else "waiting for camera frames"
        )

    def latest_preview(self) -> VideoPreviewFrame | None:
        """Return a new viewfinder image, or None when no fresh image is available."""
        if not self.ready:
            return None
        frame = self._preview.read(self._preview_seen_ns)
        if frame is not None:
            self._preview_seen_ns = frame.observed_ns
        return frame

    def begin_attempt(self, path: Path, start_ns: int) -> dict[str, Any]:
        """Queue a start marker without blocking a CSI callback on camera I/O."""
        if not self.ready:
            raise RuntimeError(self.detail)
        value = {
            "schema_version": 1,
            "status": "queued",
            "configuration": self.config.metadata(),
            "attempt_started_monotonic_ns": start_ns,
            "frames": 0,
        }
        _write_json(path / "video.json", value)
        self._pending[str(path)] = start_ns
        try:
            self._commands.put_nowait(("begin", str(path), start_ns))
        except Full:
            self.failure = "video control queue full"
            self._fail_pending(self.failure)
            raise RuntimeError(self.failure) from None
        return {
            "video_file": "camera.mp4",
            "frame_timing_file": "camera_frames.csv",
            "metadata_file": "video.json",
        }

    def end_attempt(self, path: Path, end_ns: int) -> None:
        """Queue the exact attempt end boundary; retain all partial artifacts."""
        self._poll()
        if self.failure:
            raise RuntimeError(self.failure)
        try:
            self._commands.put_nowait(("end", str(path), end_ns))
            self._finishing[str(path)] = time.monotonic_ns()
        except Full:
            self.failure = "video control queue full"
            self._process.terminate()
            raise RuntimeError(self.failure) from None

    def result(self, path: Path) -> dict[str, Any] | None:
        """Read finalized status; pending finalization cannot be accepted as complete."""
        self._poll()
        value = json.loads((path / "video.json").read_text())
        return value if value["status"] in ("complete", "failed") else None

    def stop(self) -> None:
        """Bound shutdown even if the phone is unplugged during a blocking read."""
        if self._closed:
            return
        self._stopping = True
        if self._started:
            try:
                self._commands.put_nowait(("shutdown", "", time.monotonic_ns()))
            except Full:
                pass
            self._process.join(3)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(2)
            self._poll()
        self._fail_pending(
            self.failure or "video worker did not finalize before shutdown"
        )
        self._closed = True
        self._started = False
        self._commands.close()
        self._commands.cancel_join_thread()
        self._events.close()
        self._events.cancel_join_thread()
