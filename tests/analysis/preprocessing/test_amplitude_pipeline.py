"""Check native physical CSI preparation and the packet reader contract."""

from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.diagnostics.phase_signals import phase_signal_from_packets
from fall_detection.analysis.preprocessing.amplitude import normalize_subcarriers
from fall_detection.analysis.preprocessing.amplitude_pipeline import (
    AmplitudePacketReader,
    prepare_recording,
)


def packets(counts=(245, 256, 245, 256, 245, 256)):
    rng = np.random.default_rng(91)
    rows = []
    for row, count in enumerate(counts):
        i = rng.integers(-128, 128, size=count, dtype=np.int16)
        q = rng.integers(-128, 128, size=count, dtype=np.int16)
        i[:3], q[:3] = [0, 3, 4], [0, 0, 0]
        rows.append(
            {
                "attempt_key": "trials/001_walk/attempt_01",
                "attempt_id": "001/01",
                "receiver_id": "rx-1",
                "is_sensing": True,
                "time_source": "test",
                "time_seconds": row / 100,
                "capture_time_ns": row * 10000000,
                "phase": "action",
                "driver_valid": row != 2,
                "sig_mode": 4,
                "bandwidth": 0,
                "stbc": 0,
                "first_word": row % 2,
                "len": count * 2,
                "csi_i": i.tolist(),
                "csi_q": q.tolist(),
                "attempt_started_monotonic_ns": 0,
                "attempt_ended_monotonic_ns": 100000000,
                "nominal_rate_hz": 100.0,
                "clock_uncertainty_us": 0.0,
            }
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("csi_i", "csi_q").cast(pl.List(pl.Int16))
    )


def test_prepare_recording_matches_canonical_decoder():
    frame = packets()
    signal = phase_signal_from_packets(frame)
    expected = np.abs(signal.complex_csi)
    valid = np.isfinite(signal.raw_phase) & frame["driver_valid"].to_numpy()[:, None]
    expected[~valid] = np.nan
    actual = prepare_recording(frame)
    np.testing.assert_array_equal(actual.masked, expected)
    expected_normalized, lower, upper = normalize_subcarriers(expected)
    np.testing.assert_array_equal(actual.normalized, expected_normalized)
    np.testing.assert_array_equal(actual.lower, lower)
    np.testing.assert_array_equal(actual.upper, upper)
    np.testing.assert_array_equal(actual.subcarriers, signal.subcarriers)
    np.testing.assert_array_equal(actual.time_seconds, signal.time_seconds)


@pytest.mark.parametrize(
    "column,value",
    [
        ("sig_mode", 1),
        ("bandwidth", 1),
        ("stbc", 1),
        ("len", 10),
        ("time_seconds", float("nan")),
    ],
)
def test_prepare_recording_rejects_corrupt_metadata(column, value):
    with pytest.raises(ValueError):
        prepare_recording(packets().with_columns(pl.lit(value).alias(column)))


def test_prepare_recording_rejects_mixed_identity_and_backwards_time():
    frame = packets()
    with pytest.raises(ValueError, match="recording"):
        prepare_recording(
            frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 0)
                .then(pl.lit("other"))
                .otherwise(pl.col("receiver_id"))
                .alias("receiver_id")
            )
        )
    with pytest.raises(ValueError, match="sorted"):
        prepare_recording(frame.reverse())


class FakeAnalysis:
    """Serve in-memory recordings through the analysis ``packets`` contract."""

    def __init__(self, recordings):
        self.recordings = recordings

    def packets(self, attempt_key, receiver_id, columns=None):
        frame = self.recordings[(attempt_key, receiver_id)]
        return (frame if columns is None else frame.select(columns)).to_arrow()


def test_packet_reader_returns_one_recording_with_projection():
    frame = packets()
    other = frame.with_columns(pl.lit("rx-2").alias("receiver_id"))
    key = frame["attempt_key"][0]
    reader = AmplitudePacketReader(
        FakeAnalysis({(key, "rx-1"): frame, (key, "rx-2"): other})
    )
    try:
        actual = reader.read(key, "rx-1")
        assert len(actual) == len(frame)
        assert actual["receiver_id"].unique().to_list() == ["rx-1"]
        assert "nominal_rate_hz" not in actual.columns
        assert reader.read(key, "rx-2")["receiver_id"].unique().to_list() == ["rx-2"]
    finally:
        reader.close()
    with pytest.raises(ValueError, match="packets"):
        AmplitudePacketReader(SimpleNamespace(analysis=None))
