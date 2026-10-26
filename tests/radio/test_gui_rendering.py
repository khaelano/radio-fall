import numpy as np

from fall_detection.radio.acquisition.buffer import BufferSnapshot, RollingCsiBuffer
from fall_detection.radio.acquisition.protocol import parse_csi_line
from fall_detection.radio.visualization.rendering import (
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
    assert frame.subcarriers == tuple(range(-32, 0)) + tuple(range(0, 32))
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
