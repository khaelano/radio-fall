"""Capture-time gap display without hardware, phase work or journal mutation."""

import os
from types import SimpleNamespace

import numpy as np
import pytest

from fall_detection.radio.acquisition.availability import AvailabilityGrid
from fall_detection.radio.visualization.gaps import (
    GAP,
    PENDING,
    RECEIVED,
    UNKNOWN,
    CsiGapPanel,
    gap_values,
)


def test_gap_snapshot_matches_deadlines_and_never_backfills_late_delivery():
    emitted = []
    grid = AvailabilityGrid(("rx-1", "rx-2"), 1_000_000_000, emit=emitted.append)
    assert grid.observe("rx-1", 1_005_000_000, 1_120_000_000)
    grid.advance(1_120_000_000)
    before = (grid.next_bin, dict(grid.timely), dict(grid.late), len(emitted))
    snapshot = grid.snapshot(seconds=0.2, now_ns=1_120_000_000)
    values = gap_values(snapshot, 1_120_000_000)
    # Visible bins -4..6 include both partially visible time bins.
    np.testing.assert_array_equal(values[0], [UNKNOWN] * 4 + [RECEIVED] + [PENDING] * 6)
    np.testing.assert_array_equal(values[1], [UNKNOWN] * 4 + [GAP] + [PENDING] * 6)
    assert before == (grid.next_bin, dict(grid.timely), dict(grid.late), len(emitted))
    assert not grid.observe("rx-2", 1_005_000_000, 1_130_000_000)
    later = grid.snapshot(seconds=0.2, now_ns=1_120_000_000)
    assert gap_values(later, 1_120_000_000)[1, 4] == GAP
    assert snapshot.packet_counts[1][4] == 0
    assert snapshot.receivers == ("rx-1", "rx-2")


def test_gap_snapshot_advances_during_all_receiver_silence_and_stays_bounded():
    grid = AvailabilityGrid(("rx-1", "rx-2"), 0, grace_ms=900)
    snapshot = grid.snapshot(now_ns=10_000_000)
    assert np.all(gap_values(snapshot, 10_000_000)[:, -1] == PENDING)
    # Reading after silence does not require a successor CSI packet or GUI writes.
    snapshot = grid.snapshot(now_ns=2_000_000_000, seconds=1)
    values = gap_values(snapshot, 2_000_000_000)
    assert np.all(values[:, :4] == GAP)
    assert np.all(values[:, -1] == PENDING)
    assert grid.next_bin == 0
    grid.advance(12_000_000_000)
    assert len(grid._history) <= 501
    snapshot = grid.snapshot(now_ns=12_000_000_000)
    assert len(snapshot.packet_counts[0]) == 501
    assert np.all(gap_values(snapshot, 12_000_000_000)[:, :400] == GAP)
    for seconds in (0, -1, 11):
        with pytest.raises(ValueError):
            grid.snapshot(now_ns=12_000_000_000, seconds=seconds)


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
    from fall_detection.radio.visualization.dashboard import qt_modules

    grid = AvailabilityGrid(("rx-1", "rx-2", "rx-3", "rx-4"), 0)
    panel = CsiGapPanel(
        *qt_modules(),
        receivers=grid.receivers,
        snapshot=lambda seconds, now_ns: grid.snapshot(seconds=seconds, now_ns=now_ns),
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
    from fall_detection.radio.visualization.live import LiveDashboard
    from fall_detection.radio.visualization.state import LiveState

    state = LiveState(120)
    for method in ("snapshot", "prepare_phase_views"):
        monkeypatch.setattr(
            state.buffer, method, lambda **kw: pytest.fail("phase work")
        )
    grid = AvailabilityGrid(("rx-1", "rx-2"), 0)
    radio = SimpleNamespace(
        state=state,
        bindings=[SimpleNamespace(receiver_id=r) for r in grid.receivers],
        manager=SimpleNamespace(grid=grid, preview_ready=True),
    )
    panel = LiveDashboard(radio, fps=24).panel
    try:
        panel.tabs.setCurrentIndex(2)
        assert panel.tabs.tabText(2) == "CSI gaps"
        assert panel.refresh()
        assert panel.gaps.image.image.shape[0] == 2
        radio.manager.preview_ready = False
        panel.mark_dirty()
        assert not panel.refresh()
        assert panel.preview_status.text() == "Preview paused"
        radio.manager = SimpleNamespace(
            grid=AvailabilityGrid(("rx-3",), 0, bin_hz=10, grace_ms=400),
            preview_ready=True,
        )
        assert panel.refresh()
        assert panel.gaps.image.image.shape == (1, 31)
        assert "400 ms" in panel.gaps.caption.text()
        radio.manager.grid = None
        panel.mark_dirty()
        assert panel.refresh()
        assert np.all(panel.gaps.image.image == UNKNOWN)
        assert panel.gaps.caption.text() == "Waiting for acquisition timing"
    finally:
        panel.widget.close()
