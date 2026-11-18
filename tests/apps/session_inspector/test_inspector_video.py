"""Frame-accurate saved-video and CSI synchronization checks without a camera."""

import csv
import json
import os
import subprocess
import sys
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from inspector_sessions import FrameSpec, attempt_origin

from fall_detection.apps.session_inspector.video import VideoReader, load_video_timeline
from fall_detection.session import load_session


@pytest.fixture
def video_attempt(session_factory):
    av = pytest.importorskip("av")
    from fall_detection.collection.video import VideoConfig, _AttemptVideo

    root = session_factory(attempts=((1, 1, "accepted"),))
    path = next(root.glob("trials/*/attempt_01"))
    metadata = json.loads((path / "attempt.json").read_text())
    origin = metadata["started_monotonic_ns"]
    assert metadata["ended_monotonic_ns"] == origin + 2_000_000_000
    recorder = _AttemptVideo(path, origin, VideoConfig("/dev/video-test", 64, 48, 30))
    for i, offset in enumerate([50_000_000, 100_000_000, 450_000_000, 1_300_000_000]):
        frame = av.VideoFrame.from_ndarray(
            np.full((48, 64, 3), i * 60, dtype=np.uint8), format="rgb24"
        )
        recorder.write(frame, origin + offset - 1_000_000, origin + offset)
    recorder.finish(origin + 2_000_000_000)
    return load_session(root).attempts[0]


def test_video_preserves_initial_offset_and_recorded_gaps(video_attempt):
    timeline = load_video_timeline(video_attempt)
    assert timeline.duration == 2.0
    assert timeline.frame_at(0.049) is None
    assert timeline.frame_at(0.05) == 0
    assert timeline.frame_at(0.4) == 1
    assert timeline.frame_at(0.45) == 2
    assert timeline.frame_at(1.299) == 2
    assert timeline.frame_seconds(3) == 1.3
    reader = VideoReader(timeline)
    try:
        for index in [0, 1, 3, 2, 0, 3]:
            width, height, rgb = reader.read(index)
            assert (width, height) == (64, 48)
            assert np.frombuffer(rgb, dtype=np.uint8).mean() == pytest.approx(
                index * 60, abs=3
            )
    finally:
        reader.close()


def test_video_rejects_wrong_clock_and_corrupt_timing(video_attempt):
    path = video_attempt.path / "video.json"
    metadata = json.loads(path.read_text())
    metadata["attempt_started_monotonic_ns"] += 1000
    path.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="start clocks differ"):
        load_video_timeline(video_attempt)
    metadata["attempt_started_monotonic_ns"] -= 1000
    path.write_text(json.dumps(metadata))
    timing = video_attempt.path / "camera_frames.csv"
    with timing.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[1]["host_read_completed_monotonic_ns"] = rows[0][
        "host_read_completed_monotonic_ns"
    ]
    with timing.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="frame timing"):
        load_video_timeline(video_attempt)


def _wait(application, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_csi_plots_use_attempt_clock_and_sort_only_derived_views(video_attempt):
    from fall_detection.apps.session_inspector.data import load_attempt_data

    data = load_attempt_data(video_attempt, "rx-1", prepare_signals=True)
    assert data.signal_times == (1.2, 0.2)
    assert [record.sequence for record in data.records] == [1, 2]
    assert data.csi.rows[0][1] == "1"
    np.testing.assert_array_equal(data.prepared_frame.timestamps, [0.2, 1.2])
    np.testing.assert_array_equal(data.prepared_frame.mean_i, [2, 1])
    assert "capture" in data.time_source


def test_frames_outside_the_attempt_window_are_not_plotted(session_factory):
    from fall_detection.apps.session_inspector.data import load_attempt_data

    origin = attempt_origin(0)
    root = session_factory(
        attempts=((1, 1, "accepted"),),
        frames=(
            FrameSpec(1, origin + 200_000_000),
            FrameSpec(2, origin + 2_500_000_000),
            FrameSpec(3, origin - 100_000_000),
        ),
    )
    data = load_attempt_data(
        load_session(root).attempts[0], "rx-1", prepare_signals=True
    )
    assert data.signal_times == (0.2,)
    assert data.csi.row_count == 1
    assert "capture" in data.time_source


def test_phase_heatmap_keeps_empty_time_cells_missing():
    from fall_detection.apps.session_inspector.data import timed_phase_image

    times = np.array([0.0, 0.1, 0.2, 1.0])
    phase = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])
    image = timed_phase_image(times, phase)
    np.testing.assert_array_equal(image[:, 0], [5.0, 6.0])
    assert np.isnan(image[:, 1:3]).all()
    np.testing.assert_array_equal(image[:, 3], [7.0, 8.0])


def test_missing_video_is_explicit_and_keeps_csi_available(video_attempt):
    from fall_detection.apps.session_inspector.data import load_attempt_data

    (video_attempt.path / "video.json").unlink()
    with pytest.raises(ValueError, match="No video recorded"):
        load_video_timeline(video_attempt)
    data = load_attempt_data(video_attempt, "rx-1", prepare_signals=True)
    assert data.record_count == 2 and data.signal_times is not None


def test_video_and_all_signal_cursors_share_attempt_time(video_attempt):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    from PySide6 import QtWidgets

    from fall_detection.apps.session_inspector.data import load_attempt_data
    from fall_detection.apps.session_inspector.ui.signals_panel import SignalsPanel

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = SignalsPanel()
    try:
        panel.video.set_attempt(video_attempt)
        panel.set_data(load_attempt_data(video_attempt, "rx-1", prepare_signals=True))
        _wait(application, lambda: panel.video.timeline is not None)
        panel.video.seek(1.3)
        assert all(
            line.value() == 1.3 and line.isVisible() for line in panel.video_cursors
        )
        # Changing the CSI view must not rebase/reset the shared video playhead.
        panel.clear("Loading another receiver")
        panel.set_data(load_attempt_data(video_attempt, "rx-1", prepare_signals=True))
        assert panel.video.position == 1.3
        assert all(line.value() == 1.3 for line in panel.video_cursors)
    finally:
        panel.close()


def test_video_viewer_shutdown_process_exits_cleanly():
    """Catch native Qt teardown failures occurring after GUI assertions pass."""
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    pytest.importorskip("av")
    target = f"{__file__}::test_video_and_all_signal_cursors_share_attempt_time"
    # The failure is native interpreter teardown: ordinary in-process assertions
    # all pass. Exercise that actual lifecycle in independent test processes.
    for _ in range(6):
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-m", "pytest", "-q", target],
            check=False,
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen", OPENBLAS_NUM_THREADS="1"),
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_video_panel_seeks_steps_and_clears_previous_attempt(video_attempt):
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.apps.session_inspector.ui.video_panel import VideoPanel

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = VideoPanel()
    try:
        panel.set_attempt(video_attempt)
        _wait(application, lambda: panel.timeline is not None)
        assert panel.position == 0.0
        assert panel._pixmap is None
        panel.seek(0.8)
        _wait(application, lambda: panel._frame_index == 2)
        assert "at 0.450 s" in panel.caption.text()
        panel.step(-1)
        assert panel.position == 0.1
        _wait(application, lambda: panel._frame_index == 1)
        panel.step(1)
        assert panel.position == 0.45
        panel.toggle_play()
        assert panel.playing
        panel.set_attempt(None)
        assert not panel.playing and panel.timeline is None and panel._pixmap is None
        assert not panel.play.isEnabled()
        # A delayed old decode cannot revive the previous attempt.
        application.processEvents()
        panel._tick()
        assert panel.timeline is None
    finally:
        panel.shutdown()
        panel.close()
    assert not panel.worker.thread.is_alive()
