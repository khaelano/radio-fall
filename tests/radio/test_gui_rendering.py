import numpy as np

from fall_detection.radio.acquisition.buffer import BufferSnapshot, RollingCsiBuffer
from fall_detection.radio.acquisition.protocol import CsiRecord, parse_csi_line
from fall_detection.radio.preprocessing.rendering import (
    VALID_SUBCARRIERS,
    RenderGate,
    phase_column,
    prepare_frame,
    representative_subcarriers,
)

PHASE_MODE_CALIBRATED = "Calibrated phase"
PHASE_MODE_CHANGE = "Phase change"
PHASE_MODE_RAW = "Raw phase (diagnostic)"


def test_dashboard_defers_plot_work_until_acquisition_catches_up(monkeypatch):
    import os

    import pytest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.presentation.radio.dashboard import CsiDashboardPanel
    from fall_detection.radio.state import LiveState

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state = LiveState(120)
    allowed = False
    calls = []
    snapshot = state.buffer.snapshot

    def capture(*args, **kwargs):
        calls.append(True)
        return snapshot(*args, **kwargs)

    monkeypatch.setattr(state.buffer, "snapshot", capture)
    panel = CsiDashboardPanel(state, fps=24, can_render=lambda: allowed)
    try:
        assert panel.refresh() is False
        assert not calls
        allowed = True
        assert panel.refresh() is True
        assert len(calls) == 1
    finally:
        panel.widget.close()
        application.processEvents()


def test_phase_display_snapshot_preserves_frames_without_raw_csi_matrices():
    buffer = RollingCsiBuffer(nominal_rate=120)
    records = [
        CsiRecord(
            sequence,
            "02:00:00:00:00:01",
            -40,
            -95,
            sequence * 10000,
            tuple(complex(4 + k % 9, 2 + k % 7) for k in range(245)),
            sig_mode=4,
            bandwidth=0,
            csi_length=490,
        )
        for sequence in range(4)
    ]
    for record in records:
        buffer.append(record)
    light = buffer.snapshot(seconds=3, include_raw_views=False)
    assert not light.real and not light.imaginary and not light.amplitudes
    assert all(record._derived_views_cache is None for record in records)
    full = buffer.snapshot(seconds=3)
    for mode in (PHASE_MODE_CALIBRATED, PHASE_MODE_CHANGE, PHASE_MODE_RAW):

        def frame(snapshot, mode=mode):
            return prepare_frame(
                snapshot,
                phase_mode=mode,
                phase_mode_change=PHASE_MODE_CHANGE,
                phase_mode_raw=PHASE_MODE_RAW,
                window_seconds=3,
            )

        expected, actual = frame(full), frame(light)
        assert actual.sequence == expected.sequence
        assert actual.subcarriers == expected.subcarriers
        for name in (
            "timestamps",
            "amplitudes",
            "raw_phases",
            "calibrated_phases",
            "selected_phases",
            "mean_i",
            "mean_q",
            "rssi",
            "noise_floor",
        ):
            np.testing.assert_allclose(
                getattr(actual, name),
                getattr(expected, name),
                rtol=1e-6,
                atol=1e-6,
                equal_nan=True,
            )


def _snapshot() -> BufferSnapshot:
    indices = tuple(range(32)) + tuple(range(-32, 0))
    row = tuple(float(index) for index in indices)
    return BufferSnapshot(
        timestamps=(0.0, 0.1),
        amplitudes=(row, row),
        start_sequence=10,
        end_sequence=11,
        max_subcarriers=64,
        real=(row, row),
        imaginary=(row, row),
        rssi=(-40, -41),
        noise_floor=(-90, -91),
        phase_subcarriers=indices,
        phase_amplitudes=(row, row),
        raw_phases=(row, row),
        calibrated_phases=(row, row),
    )


def test_representative_subcarriers_are_even_and_physical():
    assert representative_subcarriers(8)[0] == -122
    assert representative_subcarriers(8)[-1] == 122
    assert representative_subcarriers(12)[0] == -122
    assert representative_subcarriers(12)[-1] == 122
    assert set(representative_subcarriers(16)) <= set(VALID_SUBCARRIERS)


def test_representative_subcarriers_use_he20_range_when_available():
    available = tuple(range(-128, 128))

    selected = representative_subcarriers(8, available)

    assert selected[0] == -122
    assert selected[-1] == 122
    assert not set(selected) & {-1, 0, 1}
    assert set(selected) <= set(VALID_SUBCARRIERS)


def test_prepare_frame_reorders_serialized_slots_to_physical_order():
    frame = prepare_frame(
        _snapshot(),
        phase_mode=PHASE_MODE_CALIBRATED,
        phase_mode_change=PHASE_MODE_CHANGE,
        phase_mode_raw=PHASE_MODE_RAW,
        window_seconds=3.0,
    )

    assert frame.sequence == 11
    assert frame.subcarriers == tuple(range(-32, 0)) + tuple(range(32))
    assert np.array_equal(frame.timestamps, np.array([-0.1, 0.0]))
    assert frame.amplitudes[0, 0] == -32.0
    assert frame.amplitudes[0, -1] == 31.0
    assert frame.mean_i.shape == (2,)


def test_c6_he20_256_slot_payload_populates_amplitude_and_phase_views():
    values = [component for pair in ([0, 20] for _ in range(256)) for component in pair]
    line = (
        'CSI_DATA,21,aa:bb:cc:dd:ee:ff,-40,11,4,0,0,0,0,0,0,0,0,-95,0,11,0,100,0,36,0,512,0,"'
        + str(values).replace("'", "")
        + '"'
    )
    buffer = RollingCsiBuffer(nominal_rate=100, seconds=3)
    buffer.append(parse_csi_line(line))

    frame = prepare_frame(
        buffer.snapshot(),
        phase_mode=PHASE_MODE_CALIBRATED,
        phase_mode_change=PHASE_MODE_CHANGE,
        phase_mode_raw=PHASE_MODE_RAW,
        window_seconds=3.0,
    )

    assert frame.subcarriers == tuple(range(-128, 128))
    assert frame.amplitudes.shape == (1, 256)
    assert frame.calibrated_phases.shape == (1, 256)
    assert np.isfinite(frame.calibrated_phases).sum() == 242


def test_phase_column_uses_physical_subcarrier_index():
    frame = prepare_frame(
        _snapshot(),
        phase_mode=PHASE_MODE_RAW,
        phase_mode_change=PHASE_MODE_CHANGE,
        phase_mode_raw=PHASE_MODE_RAW,
        window_seconds=3.0,
    )

    assert np.array_equal(phase_column(frame, -32), np.array([-32.0, -32.0]))
    assert phase_column(frame, 99).size == 0


def test_render_gate_is_independent_per_view_and_configuration():
    gate = RenderGate(view_count=2)

    assert gate.needs_render(0, 10, 0)
    gate.mark_rendered(0, 10, 0)
    assert not gate.needs_render(0, 10, 0)
    assert gate.needs_render(0, 11, 0)
    assert gate.needs_render(0, 10, 1)
    assert gate.needs_render(1, 10, 0)


def test_frame_cache_reuses_arrays_and_invalidates_on_buffer_window_or_mode_change(
    monkeypatch,
):
    from fall_detection.radio.preprocessing.rendering import CsiFrameCache

    first, second = RollingCsiBuffer(), RollingCsiBuffer()
    record = CsiRecord(7, "02:00:00:00:00:01", -40, -95, 1, (4 + 2j,) * 64)
    first.append(record)
    second.append(record)
    calls = []
    snapshot = first.snapshot
    monkeypatch.setattr(
        first, "snapshot", lambda *a, **kw: calls.append(True) or snapshot(*a, **kw)
    )
    cache = CsiFrameCache()

    def prepare(buffer=first, mode=PHASE_MODE_CALIBRATED, seconds=3):
        return cache.prepare(
            buffer,
            phase_mode=mode,
            phase_mode_change=PHASE_MODE_CHANGE,
            phase_mode_raw=PHASE_MODE_RAW,
            window_seconds=seconds,
        )

    frame = prepare()
    assert prepare() is frame
    raw = prepare(mode=PHASE_MODE_RAW)
    assert raw is not frame
    assert raw.selected_phases is raw.raw_phases
    assert len(calls) == 1  # mode changes reuse the snapshot
    assert prepare(seconds=2) is not raw
    assert len(calls) == 2
    first.append(record)  # even an identical sequence changes the buffer
    assert prepare(seconds=2).timestamps.size == 2
    assert len(calls) == 3
    assert prepare(second).timestamps.size == 1
    prepare()
    assert len(calls) == 4


def test_dashboard_renders_duplicate_sequence_appends_and_reuses_control_frames(
    monkeypatch,
):
    import os

    import pytest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.presentation.radio.dashboard import CsiDashboardPanel
    from fall_detection.radio.state import LiveState

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state = LiveState()
    record = CsiRecord(7, "02:00:00:00:00:01", -40, -95, 1, (4 + 2j,) * 64)
    state.buffer.append(record)
    calls = []
    snapshot = state.buffer.snapshot
    monkeypatch.setattr(
        state.buffer,
        "snapshot",
        lambda *a, **kw: calls.append(True) or snapshot(*a, **kw),
    )
    panel = CsiDashboardPanel(state, fps=24)
    try:
        assert panel.refresh()
        assert not panel.refresh()
        panel.mark_dirty()
        assert panel.refresh()
        assert len(calls) == 1
        state.buffer.append(record)
        assert panel.refresh()
        assert len(calls) == 2
    finally:
        panel.widget.close()
        application.processEvents()


def test_cold_preview_prepares_bounded_work_without_changing_full_snapshot():
    from dataclasses import replace

    buffer = RollingCsiBuffer(120)
    base = CsiRecord(
        0, "02:00:00:00:00:01", -40, -95, 0, (4 + 2j,) * 245, sig_mode=4, csi_length=490
    )
    records = [replace(base, sequence=i, timestamp_us=i * 8333) for i in range(5)]
    for record in records:
        buffer.append(record)
    options = {
        "seconds": 3,
        "max_records": 2,
        "budget_ns": 8_000_000,
        "clock_ns": lambda: 0,
    }
    assert not buffer.prepare_phase_views(**options)
    assert sum(record.phase_views_ready for record in records) == 2
    assert not buffer.prepare_phase_views(**options)
    assert sum(record.phase_views_ready for record in records) == 4
    assert buffer.prepare_phase_views(**options)
    snapshot = buffer.snapshot(seconds=3, include_raw_views=False)
    assert len(snapshot.timestamps) == 5
    assert buffer.received_records == 5
    assert all(record.phase_views_ready for record in records)
    assert all(record._derived_views_cache is None for record in records)


def test_preview_phase_preparation_yields_at_time_budget():
    from dataclasses import replace

    buffer = RollingCsiBuffer(120)
    base = CsiRecord(
        0, "02:00:00:00:00:01", -40, -95, 0, (4 + 2j,) * 245, sig_mode=4, csi_length=490
    )
    records = [replace(base, sequence=i, timestamp_us=i * 8333) for i in range(3)]
    for record in records:
        buffer.append(record)
    times = iter((0, 0, 9_000_000))
    assert not buffer.prepare_phase_views(seconds=3, clock_ns=lambda: next(times))
    assert [record.phase_views_ready for record in records] == [True, False, False]


def test_receiver_switch_clears_old_traces_and_waits_for_bounded_preparation(
    monkeypatch,
):
    import os
    from dataclasses import replace

    import pytest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.presentation.radio.dashboard import CsiDashboardPanel
    from fall_detection.radio.state import LiveState

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    first, second = RollingCsiBuffer(), RollingCsiBuffer()
    record = CsiRecord(
        1, "02:00:00:00:00:01", -40, -95, 1, (4 + 2j,) * 245, sig_mode=4, csi_length=490
    )
    first.append(record)
    for index in range(3):
        second.append(replace(record, sequence=index + 2, timestamp_us=10_000 + index))
    prepare = second.prepare_phase_views
    monkeypatch.setattr(
        second,
        "prepare_phase_views",
        lambda **kw: prepare(
            **kw,
            max_records=1,
            clock_ns=lambda: 0,
        ),
    )
    calls = []
    snapshot = second.snapshot
    monkeypatch.setattr(
        second, "snapshot", lambda *a, **kw: calls.append(True) or snapshot(*a, **kw)
    )
    state = LiveState()
    state.configure_receivers({"rx-1": first, "rx-2": second})
    panel = CsiDashboardPanel(state, fps=24, receivers=["rx-1", "rx-2"])
    try:
        assert panel.refresh()
        assert panel.amplitude_curves[0].xData is not None
        panel.receiver_combo.setCurrentIndex(1)
        assert panel.amplitude_curves[0].xData is None
        assert not panel.refresh()
        assert not panel.refresh()
        assert not calls
        assert panel.refresh()
        assert calls == [True]
        assert len(panel.amplitude_curves[0].xData) == 3
    finally:
        panel.widget.close()
        application.processEvents()


def test_preview_defers_records_arriving_after_budgeted_preparation(monkeypatch):
    """A radio burst between warmup and snapshot must not bypass the GUI budget."""
    import os
    from dataclasses import replace

    import pytest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.presentation.radio.dashboard import CsiDashboardPanel
    from fall_detection.radio.state import LiveState

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state = LiveState(120)
    record = CsiRecord(
        0,
        "02:00:00:00:00:01",
        -40,
        -95,
        0,
        (4 + 2j,) * 245,
        sig_mode=4,
        csi_length=490,
    )
    state.buffer.append(record)
    arrivals = [
        replace(record, sequence=i, timestamp_us=i * 8333) for i in range(1, 33)
    ]
    warm = state.buffer.prepare_phase_views
    injected = False

    def prepare(**options):
        nonlocal injected
        ready = warm(**options, max_records=16, clock_ns=lambda: 0)
        if ready and not injected:
            injected = True
            for item in arrivals:
                state.buffer.append(item)
        return ready

    monkeypatch.setattr(state.buffer, "prepare_phase_views", prepare)
    panel = CsiDashboardPanel(state, fps=24)
    try:
        assert not panel.refresh(), (
            "new radio burst bypassed preview preparation budget"
        )
        assert not any(item.phase_views_ready for item in arrivals)
        assert not panel.refresh()
        assert sum(item.phase_views_ready for item in arrivals) == 16
        assert panel.refresh()
        assert len(panel.amplitude_curves[0].xData) == 33
        assert state.buffer.received_records == 33
    finally:
        panel.widget.close()
        application.processEvents()
