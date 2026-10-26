from math import isclose, isnan

import numpy as np

from fall_detection.radio.preprocessing.phase import (
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HE20_VALID_SUBCARRIERS,
    HT20_SLOT_INDICES,
    calibrate_phase,
    decode_ltf_blocks,
    phase_change_from_baseline,
)


def _synthetic_ht20(*, slope: float = 0.07, offset: float = 1.1) -> tuple[complex, ...]:
    values = []
    for index in HT20_SLOT_INDICES:
        phase = slope * index + offset
        values.append(complex(20.0 * np.cos(phase), 20.0 * np.sin(phase)))
    return tuple(values)


def _synthetic_he20(*, slope: float = 0.01, offset: float = 0.4) -> tuple[complex, ...]:
    values = []
    for index in HE20_SLOT_INDICES:
        phase = slope * index + offset
        values.append(complex(20.0 * np.cos(phase), 20.0 * np.sin(phase)))
    return tuple(values)


def test_ht20_payload_decodes_lltf_and_htltf_with_signed_slots():
    csi = _synthetic_ht20() * 2

    blocks = decode_ltf_blocks(
        csi,
        sig_mode=1,
        bandwidth=0,
        stbc=0,
        first_word_invalid=True,
    )

    assert [block.name for block in blocks] == ["LLTF", "HT-LTF"]
    assert [len(block.csi) for block in blocks] == [64, 64]
    assert blocks[1].subcarrier_indices[:3] == (0, 1, 2)
    assert blocks[1].subcarrier_indices[-3:] == (-3, -2, -1)
    assert all(isnan(value) for value in blocks[0].raw_phases[:2])
    assert not isnan(blocks[1].raw_phases[2])


def test_he20_payload_decodes_one_256_slot_he_ltf():
    blocks = decode_ltf_blocks(
        _synthetic_he20(),
        sig_mode=4,
        bandwidth=0,
        stbc=0,
        first_word_invalid=False,
    )

    assert [block.name for block in blocks] == ["HE-LTF"]
    assert len(blocks[0].csi) == 256
    assert blocks[0].subcarrier_indices[:3] == (-128, -127, -126)
    assert blocks[0].subcarrier_indices[-3:] == (125, 126, 127)
    assert blocks[0].valid_subcarriers == HE20_VALID_SUBCARRIERS
    assert isnan(blocks[0].raw_phases[0])
    assert isnan(blocks[0].raw_phases[-1])
    assert not isnan(blocks[0].raw_phases[6])
    assert isnan(blocks[0].raw_phases[128])
    assert not isnan(blocks[0].raw_phases[250])
    finite = [value for value in blocks[0].calibrated_phases if np.isfinite(value)]
    assert len(finite) == 242
    assert max(abs(value) for value in finite) < 1e-8


def test_he20_compact_payload_remains_supported():
    csi = tuple(complex(20.0, 0.0) for _ in HE20_COMPACT_SLOT_INDICES)

    blocks = decode_ltf_blocks(
        csi,
        sig_mode=4,
        bandwidth=0,
        stbc=0,
        first_word_invalid=False,
    )

    assert [block.name for block in blocks] == ["HE-LTF"]
    assert blocks[0].subcarrier_indices == HE20_COMPACT_SLOT_INDICES


def test_calibration_removes_known_offset_and_slope_and_masks_invalid_values():
    csi = list(_synthetic_ht20(slope=0.04, offset=2.0))
    invalid = [False] * len(csi)
    invalid[5] = True
    csi[10] = 0j

    calibrated = calibrate_phase(
        csi,
        HT20_SLOT_INDICES,
        invalid_slots=invalid,
    )

    valid = [
        value
        for index, value in enumerate(calibrated)
        if index not in (5, 10) and np.isfinite(value)
    ]
    assert max(abs(value) for value in valid) < 1e-8
    assert isnan(calibrated[5])
    assert isnan(calibrated[10])

    blocks = decode_ltf_blocks(
        tuple(csi) * 2,
        sig_mode=1,
        bandwidth=0,
        stbc=0,
        first_word_invalid=False,
    )
    assert isnan(blocks[1].raw_phases[10])


def test_phase_change_uses_oldest_visible_median_baseline():
    timestamps = np.array([0.0, 0.1, 0.2, 0.8])
    phases = np.array([[0.4, np.nan], [0.4, 0.2], [0.4, 0.2], [1.0, 0.7]])

    changed = phase_change_from_baseline(
        phases,
        timestamps,
        window_seconds=2.0,
    )

    assert isclose(changed[0, 0], 0.0, abs_tol=1e-9)
    assert isclose(changed[-1, 0], 0.6, abs_tol=1e-9)
    assert isnan(changed[0, 1])
    assert isclose(changed[-1, 1], 0.5, abs_tol=1e-9)
