import numpy as np

from radio_processor.buffer import BufferSnapshot
from radio_processor.gui.rendering import (
    VALID_SUBCARRIERS,
    RenderGate,
    phase_column,
    prepare_frame,
    representative_subcarriers,
)


PHASE_MODE_CALIBRATED = "Calibrated phase"
PHASE_MODE_CHANGE = "Phase change"
PHASE_MODE_RAW = "Raw phase (diagnostic)"


def _snapshot() -> BufferSnapshot:
    indices = tuple(range(0, 32)) + tuple(range(-32, 0))
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
    assert representative_subcarriers(8) == (-28, -20, -12, -4, 4, 12, 20, 28)
    assert representative_subcarriers(12)[0] == -28
    assert representative_subcarriers(12)[-1] == 28
    assert set(representative_subcarriers(16)) <= set(VALID_SUBCARRIERS)


def test_prepare_frame_reorders_serialized_slots_to_physical_order():
    frame = prepare_frame(
        _snapshot(),
        phase_mode=PHASE_MODE_CALIBRATED,
        phase_mode_change=PHASE_MODE_CHANGE,
        phase_mode_raw=PHASE_MODE_RAW,
        window_seconds=3.0,
    )

    assert frame.sequence == 11
    assert frame.subcarriers == tuple(range(-32, 0)) + tuple(range(0, 32))
    assert np.array_equal(frame.timestamps, np.array([-0.1, 0.0]))
    assert frame.amplitudes[0, 0] == -32.0
    assert frame.amplitudes[0, -1] == 31.0
    assert frame.mean_i.shape == (2,)


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
