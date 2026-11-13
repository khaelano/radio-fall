"""Capture-time gap display without hardware, phase work or journal mutation."""

import os
from types import SimpleNamespace

import numpy as np
import pytest

from fall_detection.presentation.radio.gaps import (
    GAP,
    PENDING,
    RECEIVED,
    UNKNOWN,
    CsiGapPanel,
    gap_values,
)
from fall_detection.radio.availability import AvailabilitySnapshot


def empty_snapshot(receivers, seconds, now_ns, *, bin_hz=50, grace_ms=100):
    """Return a pre-deadline snapshot with no deliveries, laid out like Rust's."""
    width = 1_000_000_000 // bin_hz
    first = (now_ns - round(seconds * 1e9)) // width
    last = now_ns // width
    counts = tuple(
        tuple(None if i < 0 else 0 for i in range(first, last + 1)) for _ in receivers
    )
    return AvailabilitySnapshot(
        tuple(receivers), first * width, width, grace_ms * 1_000_000, counts
    )


def test_gap_values_classify_deadlines_without_backfilling():
    snapshot = AvailabilitySnapshot(
        ("rx-1", "rx-2"),
        920_000_000,
        20_000_000,
        100_000_000,
        ((None,) * 4 + (1,) + (0,) * 6, (None,) * 4 + (0,) + (0,) * 6),
    )
    values = gap_values(snapshot, 1_120_000_000)
    # Visible bins -4..6 include both partially visible time bins.
    np.testing.assert_array_equal(values[0], [UNKNOWN] * 4 + [RECEIVED] + [PENDING] * 6)
    np.testing.assert_array_equal(values[1], [UNKNOWN] * 4 + [GAP] + [PENDING] * 6)


def test_gap_values_mark_silence_after_deadlines():
    snapshot = empty_snapshot(("rx-1", "rx-2"), 1, 2_000_000_000, grace_ms=900)
    values = gap_values(snapshot, 2_000_000_000)
    assert np.all(values[:, :4] == GAP)
    assert np.all(values[:, -1] == PENDING)


def test_snapshot_parses_native_json():
    value = (
        '{"receivers":["rx-1"],"first_bin_start_ns":-20,"width_ns":20,'
        '"grace_ns":5,"packet_counts":[[null,3]]}'
    )
    assert AvailabilitySnapshot.from_json(value) == AvailabilitySnapshot(
        ("rx-1",), -20, 20, 5, ((None, 3),)
    )


@pytest.fixture
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    app.processEvents()


def test_gap_panel_shows_all_receivers_and_refreshes_silence_at_four_hz(qt_app):
    from fall_detection.presentation.radio.dashboard import qt_modules

    receivers = ("rx-1", "rx-2", "rx-3", "rx-4")
    panel = CsiGapPanel(
        *qt_modules(),
        receivers=receivers,
        snapshot=lambda seconds, now_ns: empty_snapshot(receivers, seconds, now_ns),
    )
    try:
        assert panel.refresh(3, now_ns=1_000_000_000)
        assert panel.image.image.shape == (4, 151)
        assert not panel.refresh(3, now_ns=1_100_000_000)
        first = panel.image.image.copy()
        assert panel.refresh(3, now_ns=1_250_000_000)
        assert not np.array_equal(first, panel.image.image)
        assert "20 ms bins" in panel.caption.text()
        assert "100 ms after each bin" in panel.caption.text()
        assert panel.refresh(10, force=True, now_ns=1_250_000_000)
        assert panel.image.image.shape == (4, 501)
        assert panel.plot.viewRange()[0] == [-10, 0]
    finally:
        panel.widget.close()


def test_gap_tab_skips_phase_work_obeys_backlog_guard_and_rebinds_after_recovery(
    qt_app,
    monkeypatch,
):
    from fall_detection.presentation.radio.live import LiveDashboard
    from fall_detection.radio.state import LiveState

    state = LiveState(120)
    for method in ("snapshot", "prepare_phase_views"):
        monkeypatch.setattr(
            state.buffer, method, lambda **kw: pytest.fail("phase work")
        )
    layout = {"receivers": ("rx-1", "rx-2"), "bin_hz": 50, "grace_ms": 100}

    def availability(seconds, now_ns):
        if layout["receivers"] is None:
            return None
        return empty_snapshot(
            layout["receivers"],
            seconds,
            now_ns,
            bin_hz=layout["bin_hz"],
            grace_ms=layout["grace_ms"],
        )

    radio = SimpleNamespace(
        state=state,
        bindings=[SimpleNamespace(receiver_id=r) for r in ("rx-1", "rx-2")],
        availability=availability,
        preview_ready=True,
    )
    panel = LiveDashboard(radio, fps=24).panel
    try:
        panel.tabs.setCurrentIndex(2)
        assert panel.tabs.tabText(2) == "CSI gaps"
        assert panel.refresh()
        assert panel.gaps.image.image.shape[0] == 2
        radio.preview_ready = False
        panel.mark_dirty()
        assert not panel.refresh()
        assert panel.preview_status.text() == "Preview paused"
        layout.update(receivers=("rx-3",), bin_hz=10, grace_ms=400)
        radio.preview_ready = True
        assert panel.refresh()
        assert panel.gaps.image.image.shape == (1, 31)
        assert "400 ms" in panel.gaps.caption.text()
        layout["receivers"] = None
        panel.mark_dirty()
        assert panel.refresh()
        assert np.all(panel.gaps.image.image == UNKNOWN)
        assert panel.gaps.caption.text() == "Waiting for acquisition timing"
    finally:
        panel.widget.close()
