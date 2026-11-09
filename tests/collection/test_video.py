"""Real codec/timestamp checks without a camera, network or inference model."""

from fractions import Fraction
import csv
import json
import multiprocessing
from queue import Queue
import time
from types import SimpleNamespace

import numpy as np
import pytest

from fall_detection.collection.video import (
    VideoConfig,
    VideoRecorder,
    _AttemptVideo,
    _VideoPreview,
    _video_worker,
)


def frame(av, index=0):
    value = av.VideoFrame.from_ndarray(
        np.full((48, 64, 3), index * 20, dtype=np.uint8), format="rgb24"
    )
    value.pts, value.time_base = index, Fraction(1, 30)
    return value


def test_video_pts_preserve_elapsed_time_and_frame_sidecar(tmp_path):
    av = pytest.importorskip("av")
    start = 5_000_000_000
    recorder = _AttemptVideo(
        tmp_path, start, VideoConfig("/dev/video-test", 64, 48, 30)
    )
    offsets = (50_000_000, 90_000_000, 250_000_000)
    for index, offset in enumerate(offsets):
        recorder.write(frame(av, index), start + offset - 1_000_000, start + offset)
    result = recorder.finish(start + 300_000_000)
    assert result["status"] == "complete" and result["frames"] == 3
    with av.open(str(tmp_path / "camera.mp4")) as video:
        decoded = list(video.decode(video=0))
    assert len(decoded) == 3
    assert [float(f.pts * f.time_base) for f in decoded] == pytest.approx(
        [0.05, 0.09, 0.25], abs=0.0001
    )
    rows = list(csv.DictReader((tmp_path / "camera_frames.csv").open()))
    assert [
        int(row["host_read_completed_monotonic_ns"]) - start for row in rows
    ] == list(offsets)
    assert [int(row["source_pts"]) for row in rows] == [0, 1, 2]
    assert (
        json.loads((tmp_path / "video.json").read_text())["configuration"][
            "phone_pipeline_latency_ns"
        ]
        is None
    )
    with pytest.raises(FileExistsError):
        _AttemptVideo(tmp_path, start, VideoConfig("/dev/video-test", 64, 48))


def test_video_empty_clip_is_failed_not_accepted(tmp_path):
    pytest.importorskip("av")
    video = _AttemptVideo(tmp_path, 100, VideoConfig("/dev/video-test", 64, 48))
    assert video.finish(200)["status"] == "failed"


def test_video_worker_keeps_attempt_boundaries_and_retries_separate(
    tmp_path, monkeypatch
):
    av = pytest.importorskip("av")
    from fall_detection.collection import video as module

    original_open = av.open
    commands, events = Queue(), Queue()
    preview = _VideoPreview(multiprocessing.get_context("spawn"))
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    clock = [1_000_000_000]
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: clock[0])

    def frames():
        clock[0] += 1_000_000
        yield frame(av, 0)  # Warm-up viewfinder, before any attempt is started.
        assert preview.read(0) is not None
        assert not list(first.iterdir()) and not list(second.iterdir())
        commands.put(("begin", str(first), clock[0] + 1))
        clock[0] += 10_000_000
        yield frame(av, 0)
        clock[0] += 10_000_000
        commands.put(("end", str(first), clock[0]))
        yield frame(av, 1)  # Exactly at the end: excluded.
        clock[0] += 10_000_000
        commands.put(("begin", str(second), clock[0]))
        yield frame(av, 2)
        clock[0] += 10_000_000
        commands.put(("end", str(second), clock[0]))
        commands.put(("shutdown", "", clock[0]))
        yield frame(av, 3)

    source = SimpleNamespace(
        streams=SimpleNamespace(
            video=[
                SimpleNamespace(
                    width=64,
                    height=48,
                    average_rate=30,
                    codec_context=SimpleNamespace(),
                )
            ]
        ),
        decode=lambda **kw: frames(),
        close=lambda: None,
    )
    monkeypatch.setattr(
        av,
        "open",
        lambda path, **kwargs: (
            source
            if kwargs.get("format") == "video4linux2"
            else original_open(path, **kwargs)
        ),
    )
    _video_worker(
        VideoConfig("/dev/video-test", 64, 48),
        commands,
        events,
        SimpleNamespace(value=0),
        preview,
    )
    image = preview.read(0)
    assert image is not None
    assert (image.width, image.height) == (64, 48)
    assert image.observed_ns == 1_001_000_000
    for path in (first, second):
        metadata = json.loads((path / "video.json").read_text())
        assert metadata["status"] == "complete" and metadata["frames"] == 1
        with original_open(str(path / "camera.mp4")) as container:
            assert len(list(container.decode(video=0))) == 1
    assert [events.get()[0] for _ in range(events.qsize())] == [
        "opened",
        "finished",
        "finished",
    ]


def _publish_preview(preview):
    """Exercise the same spawn/shared-memory path used by the camera worker."""
    import av

    image = av.VideoFrame.from_ndarray(
        np.full((480, 640, 3), 80, dtype=np.uint8), format="rgb24"
    )
    preview.publish(image, 10_000_000_000)
    image = av.VideoFrame.from_ndarray(
        np.full((480, 640, 3), 160, dtype=np.uint8), format="rgb24"
    )
    preview.publish(image, 10_200_000_000)
    # A third observation inside the 100 ms interval must be skipped.
    preview.publish(image, 10_250_000_000)


def test_video_preview_shared_slot_keeps_only_latest_bounded_image():
    pytest.importorskip("av")
    context = multiprocessing.get_context("spawn")
    preview = _VideoPreview(context)
    assert preview.read(0) is None
    worker = context.Process(target=_publish_preview, args=(preview,))
    worker.start()
    try:
        worker.join(10)
        assert worker.exitcode == 0
        image = preview.read(0)
        assert (image.width, image.height) == (360, 270)
        assert image.observed_ns == 10_200_000_000
        assert image.rgb == bytes([160]) * (360 * 270 * 3)
        assert preview.read(image.observed_ns) is None
        # Neither side waits on a busy slot, including one held by a dead worker.
        with preview._lock:
            assert preview.read(0) is None
            preview.publish(None, 11_000_000_000)
        assert preview.read(0) == image
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(2)


def test_video_recorder_preview_consumes_new_images_only_when_ready(monkeypatch):
    av = pytest.importorskip("av")
    camera = VideoRecorder(VideoConfig("/dev/video-test", 64, 48))
    try:
        camera._preview.publish(frame(av), 10_000_000_000)
        assert camera.latest_preview() is None
        monkeypatch.setattr(VideoRecorder, "ready", property(lambda self: True))
        assert camera.latest_preview().observed_ns == 10_000_000_000
        assert camera.latest_preview() is None
    finally:
        camera.stop()


def test_video_missing_device_fails_health_and_stops_process():
    pytest.importorskip("av")
    camera = VideoRecorder(
        VideoConfig("/dev/nonexistent-collection-test-camera", 64, 48)
    )
    try:
        camera.start()
        deadline = time.monotonic() + 10
        while not camera.failure and time.monotonic() < deadline:
            assert not camera.ready
            time.sleep(0.02)
        assert camera.failure and not camera.ready
    finally:
        camera.stop()
    assert not camera._process.is_alive()


def test_video_configuration_requires_explicit_valid_camera():
    for kwargs in (
        {"device": "0"},
        {"device": "/dev/video2", "fps": 0},
        {"device": "/dev/video2", "width": 1279},
    ):
        with pytest.raises(ValueError):
            VideoConfig(**kwargs)


def test_video_blocked_camera_shutdown_is_bounded_and_keeps_failed_sidecar(tmp_path):
    pytest.importorskip("av")
    import multiprocessing

    camera = VideoRecorder(VideoConfig("/dev/video-test", 64, 48))
    # A process that never answers camera commands reproduces a blocked read,
    # without opening any real camera or relying on device timing.
    context = multiprocessing.get_context("spawn")
    camera._process = context.Process(target=time.sleep, args=(30,), daemon=True)
    camera.start()
    camera._last_frame.value = time.monotonic_ns()
    camera.begin_attempt(tmp_path, time.monotonic_ns())
    started = time.monotonic()
    camera.stop()
    assert time.monotonic() - started < 6
    assert not camera._process.is_alive() and not camera.ready
    metadata = json.loads((tmp_path / "video.json").read_text())
    assert metadata["status"] == "failed"
    camera.stop()  # Safe when both close paths run.


def test_video_finalization_timeout_fails_pending_clip_instead_of_waiting_forever(
    tmp_path, monkeypatch
):
    pytest.importorskip("av")
    import multiprocessing
    from fall_detection.collection import video as module

    camera = VideoRecorder(VideoConfig("/dev/video-test", 64, 48))
    context = multiprocessing.get_context("spawn")
    camera._process = context.Process(target=time.sleep, args=(30,), daemon=True)
    camera.start()
    now = time.monotonic_ns()
    camera._last_frame.value = now
    try:
        camera.begin_attempt(tmp_path, now)
        camera.end_attempt(tmp_path, now + 1)
        monkeypatch.setattr(module.time, "monotonic_ns", lambda: now + 4_000_000_000)
        result = camera.result(tmp_path)
        assert result["status"] == "failed"
        assert "finalization timed out" in result["error"]
        assert not camera.ready
    finally:
        camera.stop()
