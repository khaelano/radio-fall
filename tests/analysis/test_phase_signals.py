"""Check phase decoding, detrending, and event-clock alignment on synthetic CSI."""

import numpy as np
import polars as pl
import pytest

pytest.importorskip("pyarrow")

from journal_builder import FOREIGN, RX1, RX2, TX, write_session

from fall_detection.analysis.phase_signals import (
    load_capture_packets,
    load_phase_signal,
    phase_signal_from_packets,
)
from fall_detection.analysis.session_frames import load_analysis_session
from fall_detection.radio.preprocessing.phase import HE20_COMPACT_SLOT_INDICES

ORIGIN = 1_000_000_000


def _payload(index: int) -> bytes:
    slots = np.asarray(HE20_COMPACT_SLOT_INDICES)
    phase = 0.02 * slots + 0.3
    if index == 1:
        phase += 0.4 * np.sin(slots / 15)
    values = 40 * np.exp(1j * phase)
    values[slots == 20] = 1
    flat = np.column_stack((np.rint(values.imag), np.rint(values.real))).astype(int)
    return bytes(int(value) & 0xFF for value in flat.ravel())


def _frames(captures=None, **overrides):
    captures = captures or [
        ORIGIN + 100_000_000 + index * 100_000_000 for index in range(4)
    ]
    return [
        {
            "receiver": RX1,
            "sequence": index,
            "capture_ns": capture,
            "payload": _payload(index),
            "sig_mode": 4,
            "radio_us": 100_000 + index * 100_000,
            "transmitter": TX if index < 3 else FOREIGN,
            **overrides.get(index, {}),
        }
        for index, capture in enumerate(captures)
    ]


def _open(tmp_path, frames):
    root = write_session(
        tmp_path / "data/raw/sessions/phase",
        attempts=[
            {
                "trial_ordinal": 1,
                "activity_label": "sit",
                "status": "accepted",
                "started_monotonic_ns": ORIGIN,
                "ended_monotonic_ns": ORIGIN + 500_000_000,
            }
        ],
        frames=frames,
        receivers=(RX1, RX2),
    )
    return load_analysis_session(root, tmp_path / "derived")


@pytest.fixture
def phase_capture(tmp_path):
    return _open(tmp_path, _frames())


def test_load_phase_signal_preserves_physical_axis_and_canonical_calibration(
    phase_capture,
):
    signal = load_phase_signal(phase_capture, "001/01", "rx-1")
    assert signal.raw_phase.shape == signal.calibrated_phase.shape == (3, 245)
    np.testing.assert_array_equal(signal.subcarriers, np.arange(-122, 123))
    assert np.isnan(
        signal.raw_phase[:, np.isin(signal.subcarriers, [-1, 0, 1, 20])]
    ).all()
    assert signal.removed_slope[0] == pytest.approx(0.02, abs=0.001)
    for index in range(3):
        valid = np.isfinite(signal.raw_phase[index])
        unwrapped = np.unwrap(signal.raw_phase[index, valid])
        residual = (
            unwrapped
            - signal.removed_slope[index] * signal.subcarriers[valid]
            - signal.removed_offset[index]
        )
        expected = np.angle(np.exp(1j * residual))
        np.testing.assert_allclose(
            expected, signal.calibrated_phase[index, valid], atol=1e-12
        )
    assert np.nanstd(signal.calibrated_phase[1]) > np.nanstd(signal.calibrated_phase[0])
    np.testing.assert_allclose(signal.time_seconds, [0.1, 0.2, 0.3], atol=1e-12)
    assert "gateway" in signal.time_source
    assert signal.skipped_layout_rows == 0
    assert signal.attempt_id == "001/01" and signal.receiver_id == "rx-1"
    assert signal.started_monotonic_ns == ORIGIN
    assert signal.nominal_rate_hz == 100


def test_load_phase_signal_rejects_mixed_transmitter_epochs(tmp_path):
    frames = _frames()
    frames[-1]["run"] = 0xABC  # a second transport run inside one attempt
    session = _open(tmp_path, frames)
    with pytest.raises(ValueError, match="mixes transmitter epochs"):
        load_phase_signal(session, "001/01", "rx-1")


def test_load_capture_packets_rejects_bad_payload_length(phase_capture):
    packets = load_capture_packets(phase_capture, "001/01", "rx-1")
    packets = packets.with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(12)
        .otherwise(pl.col("len"))
        .alias("len")
    )
    with pytest.raises(ValueError, match="payload length"):
        phase_signal_from_packets(packets)


def test_load_phase_signal_retains_only_supported_packets(phase_capture):
    packets = load_capture_packets(phase_capture, "001/01", "rx-1")
    # Six int16 values cannot hold an HE-LTF block, so the row is skipped.
    short = {"csi_i": [20, 20, 20], "csi_q": [0, 0, 0], "len": 6}
    packets = pl.concat(
        [
            packets.head(1).with_columns(
                pl.lit(value, dtype=packets.schema[name]).alias(name)
                for name, value in short.items()
            ),
            packets.tail(-1),
        ]
    )
    signal = phase_signal_from_packets(packets)
    assert signal.skipped_layout_rows == 1
    np.testing.assert_allclose(signal.time_seconds, [0.2, 0.3])


def test_load_phase_signal_requires_existing_receiver_and_attempt(phase_capture):
    with pytest.raises(FileNotFoundError, match="rx-2"):
        load_phase_signal(phase_capture, "001/01", "rx-2")
    with pytest.raises(FileNotFoundError, match="Expected one attempt"):
        load_phase_signal(phase_capture, "002/01", "rx-1")
    with pytest.raises(ValueError, match="look like"):
        load_phase_signal(phase_capture, "1-1", "rx-1")


def test_load_capture_packets_keeps_non_sensing_rows_and_identity(phase_capture):
    packets = load_capture_packets(phase_capture, "001/01", "rx-1")
    assert set(packets["attempt_id"]) == {"001/01"}
    assert set(packets["receiver_id"]) == {"rx-1"}
    assert packets["is_sensing"].to_list() == [True, True, True, False]


def test_gateway_phase_uses_capture_clock_and_sorts_derived_view(tmp_path):
    captures = [1_100_000_000, 1_050_000_000, 1_200_000_000, 1_300_000_000]
    session = _open(tmp_path, _frames(captures))
    signal = load_phase_signal(session, "001/01", "rx-1")
    np.testing.assert_allclose(signal.time_seconds, [0.05, 0.1, 0.2])
    assert "gateway" in signal.time_source and signal.sync_uncertainty_us == 100
    # The view is sorted by capture time; source_row keeps journal (delivery) order.
    packets = load_capture_packets(session, "001/01", "rx-1")
    assert packets["source_row"].to_list() == [1, 0, 2, 3]
    assert packets["id"].to_list() == [1, 0, 2, 3]


def test_phase_signal_from_packets_accepts_pandas_frames_like_notebooks(phase_capture):
    pytest.importorskip("pandas")
    packets = load_capture_packets(phase_capture, "001/01", "rx-1")
    expected = phase_signal_from_packets(packets)
    actual = phase_signal_from_packets(packets.to_pandas())
    for name in (
        "time_seconds",
        "subcarriers",
        "complex_csi",
        "raw_phase",
        "calibrated_phase",
        "removed_slope",
        "removed_offset",
    ):
        np.testing.assert_array_equal(getattr(actual, name), getattr(expected, name))
    assert actual.sync_uncertainty_us == expected.sync_uncertainty_us == 100


def test_phase_signal_from_packets_keeps_missing_nominal_rate_as_nan(phase_capture):
    pytest.importorskip("pandas")
    packets = load_capture_packets(phase_capture, "001/01", "rx-1")
    missing = packets.with_columns(
        pl.lit(None, dtype=packets.schema["nominal_rate_hz"]).alias("nominal_rate_hz")
    )
    assert np.isnan(phase_signal_from_packets(missing).nominal_rate_hz)
    pandas_missing = packets.to_pandas()
    pandas_missing["nominal_rate_hz"] = np.nan
    assert np.isnan(phase_signal_from_packets(pandas_missing).nominal_rate_hz)
