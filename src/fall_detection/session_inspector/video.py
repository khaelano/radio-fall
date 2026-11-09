"""Read-only frame timing and bounded background decoding of attempt video."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import csv
from fractions import Fraction
import json
from pathlib import Path
from threading import Condition, Thread

from .models import RecordedAttempt


@dataclass(frozen=True)
class VideoTimeline:
    """Recorded frame observations on the attempt's host monotonic clock."""

    path: Path
    origin_ns: int
    end_ns: int
    observations: tuple[int, ...]
    presentation: tuple[Fraction, ...]
    status: str

    @property
    def duration(self) -> float:
        """Return attempt duration, including time before the first frame."""
        return (self.end_ns - self.origin_ns) / 1e9

    def frame_at(self, seconds: float) -> int | None:
        """Select the most recent observed frame, preserving presentation gaps."""
        index = (
            bisect_right(self.observations, self.origin_ns + round(seconds * 1e9)) - 1
        )
        return index if index >= 0 else None

    def frame_seconds(self, index: int) -> float:
        """Return a frame's observed time relative to attempt start."""
        return (self.observations[index] - self.origin_ns) / 1e9


def load_video_timeline(attempt: RecordedAttempt) -> VideoTimeline:
    """Validate saved video timing without assuming a constant frame rate."""
    path = attempt.path
    if not (path / "video.json").is_file():
        raise ValueError("No video recorded for this attempt")
    metadata = json.loads((path / "video.json").read_text())
    if attempt.active or metadata.get("status") == "recording":
        raise ValueError("Video is still recording; refresh after finalization")
    if metadata.get("schema_version") != 1:
        raise ValueError("Unsupported video timing schema")
    if metadata.get("status") not in {"complete", "failed"}:
        raise ValueError("No finalized video for this attempt")
    for key, expected in [
        ("video_file", "camera.mp4"),
        ("frame_timing_file", "camera_frames.csv"),
    ]:
        if metadata.get(key) != expected:
            raise ValueError("Unsupported video artifact filename")
    origin = metadata["attempt_started_monotonic_ns"]
    if not isinstance(origin, int) or isinstance(origin, bool):
        raise ValueError("Missing video host clock")
    if attempt.metadata.get("started_monotonic_ns", origin) != origin:
        raise ValueError("Video and attempt start clocks differ")
    observations, presentation = [], []
    with (path / "camera_frames.csv").open(newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            observed = int(row["host_read_completed_monotonic_ns"])
            pts = int(row["presentation_pts"]) * Fraction(
                int(row["time_base_num"]), int(row["time_base_den"])
            )
            if (
                int(row["frame_index"]) != index
                or observed < origin
                or int(row["host_read_started_monotonic_ns"]) > observed
                or abs(pts - Fraction(observed - origin, 1_000_000_000))
                >= Fraction(1, 1_000_000)
                or (
                    observations
                    and (observed <= observations[-1] or pts <= presentation[-1])
                )
            ):
                raise ValueError("Invalid or nonmonotonic video frame timing")
            observations.append(observed)
            presentation.append(pts)
    if not observations or not (path / "camera.mp4").is_file():
        raise ValueError("Video has no readable frames or media file")
    if metadata.get("frames") != len(observations):
        raise ValueError("Video frame count differs from timing sidecar")
    end = metadata.get(
        "ended_monotonic_ns",
        attempt.metadata.get("ended_monotonic_ns", observations[-1]),
    )
    if not isinstance(end, int) or end < observations[-1]:
        raise ValueError("Video end precedes recorded frames")
    return VideoTimeline(
        path / "camera.mp4",
        origin,
        end,
        tuple(observations),
        tuple(presentation),
        metadata["status"],
    )


class VideoReader:
    """Seek/decode on demand, retaining only one aspect-preserving RGB frame."""

    def __init__(self, timeline: VideoTimeline) -> None:
        try:
            import av
        except ImportError as exc:
            raise ValueError(
                "Install video playback support: uv sync --extra radio --extra video"
            ) from exc
        self.timeline = timeline
        self.container = av.open(str(timeline.path))
        try:
            self.stream = self.container.streams.video[0]
            self.stream.codec_context.thread_count = 2
        except Exception:
            self.container.close()
            raise
        self.iterator = None
        self.index = -1
        self.cached = None

    def read(self, index: int) -> tuple[int, int, bytes]:
        """Return the exact sidecar frame; never rebase to a player's first PTS."""
        if self.index == index and self.cached is not None:
            return self.cached
        target = self.timeline.presentation[index]
        if self.iterator is None or index < self.index or index > self.index + 60:
            self.container.seek(
                int(target / self.stream.time_base), stream=self.stream, backward=True
            )
            self.iterator = iter(self.container.decode(self.stream))
        for frame in self.iterator:
            if frame.pts is None:
                raise ValueError("Decoded frame has no presentation timestamp")
            actual = frame.pts * frame.time_base
            if actual < target - Fraction(1, 1_000_000):
                continue
            if abs(actual - target) > Fraction(1, 1_000_000):
                raise ValueError("Decoded video PTS differs from frame timing sidecar")
            scale = min(640 / frame.width, 360 / frame.height, 1)
            rgb = frame.reformat(
                width=max(1, int(frame.width * scale)),
                height=max(1, int(frame.height * scale)),
                format="rgb24",
            )
            self.cached = (rgb.width, rgb.height, rgb.to_ndarray().tobytes())
            self.index = index
            return self.cached
        raise ValueError("Video ended before the requested timed frame")

    def close(self) -> None:
        """Release the read-only decoder."""
        self.container.close()


class VideoWorker:
    """One decoder thread, one pending seek and one result; no Qt objects here."""

    def __init__(self) -> None:
        self.condition = Condition()
        self.pending = None
        self.result = None
        self.stopped = False
        self.thread = Thread(target=self._run, name="session-video", daemon=True)
        self.thread.start()

    def request(
        self, generation: int, attempt: RecordedAttempt | None, seconds: float
    ) -> None:
        """Replace obsolete requests instead of building a decoding backlog."""
        with self.condition:
            self.pending = (generation, attempt, seconds)
            self.condition.notify()

    def poll(self) -> tuple | None:
        """Take the newest completed seek without waiting on I/O."""
        with self.condition:
            value, self.result = self.result, None
            return value

    def _run(self) -> None:
        reader, generation = None, None
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(
                        lambda: self.stopped or self.pending is not None
                    )
                    if self.stopped:
                        return
                    token, attempt, seconds = self.pending
                    self.pending = None
                try:
                    if token != generation:
                        if reader is not None:
                            reader.close()
                        reader, generation = None, token
                    if attempt is None:
                        continue
                    if reader is None:
                        reader = VideoReader(load_video_timeline(attempt))
                    index = reader.timeline.frame_at(seconds)
                    pixels = reader.read(index) if index is not None else None
                    result = (token, seconds, reader.timeline, index, pixels, "")
                except Exception as exc:
                    result = (token, seconds, None, None, None, str(exc))
                with self.condition:
                    if not self.stopped:
                        self.result = result
        finally:
            if reader is not None:
                reader.close()

    def close(self) -> None:
        """Bound UI shutdown even if media I/O has not returned yet."""
        with self.condition:
            self.stopped = True
            self.pending = None
            self.result = None
            self.condition.notify()
        self.thread.join(timeout=0.5)
