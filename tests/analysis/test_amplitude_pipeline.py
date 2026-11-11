"""Check native physical CSI preparation and the Polars/NPZ pipeline."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.amplitude import hampel_subcarriers, normalize_subcarriers
from fall_detection.analysis.amplitude_pipeline import (
    AmplitudePacketReader,
    prepare_recording,
    preprocess_dataset,
    save_recording,
)
from fall_detection.analysis.phase_signals import phase_signal_from_packets


def packets(counts=(245, 256, 245, 256, 245, 256)):
    rng = np.random.default_rng(91)
    rows = []
    for row, count in enumerate(counts):
        i = rng.integers(-128, 128, size=count, dtype=np.int16)
        q = rng.integers(-128, 128, size=count, dtype=np.int16)
        i[:3], q[:3] = [0, 3, 4], [0, 0, 0]
        rows.append(
            dict(
                attempt_key="trials/001_walk/attempt_01",
                attempt_id="001/01",
                receiver_id="rx-1",
                is_sensing=True,
                time_source="test",
                time_seconds=row / 100,
                capture_time_ns=row * 10000000,
                phase="action",
                driver_valid=row != 2,
                sig_mode=4,
                bandwidth=0,
                stbc=0,
                first_word=row % 2,
                len=count * 2,
                csi_i=i.tolist(),
                csi_q=q.tolist(),
                attempt_started_monotonic_ns=0,
                attempt_ended_monotonic_ns=100000000,
                nominal_rate_hz=100.0,
                clock_uncertainty_us=0.0,
            )
        )
    return pl.DataFrame(rows).with_columns(
        pl.col("csi_i", "csi_q").cast(pl.List(pl.Int16))
    )


def test_prepare_recording_matches_canonical_decoder():
    frame = packets()
    signal = phase_signal_from_packets(frame.to_pandas())
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


def test_packet_reader_handles_mixed_row_groups_and_projection(tmp_path):
    frame = packets()
    other = frame.with_columns(pl.lit("rx-2").alias("receiver_id"))
    path = tmp_path / "packets.parquet"
    pl.concat([frame, other]).write_parquet(path, row_group_size=7)
    reader = AmplitudePacketReader(path)
    try:
        actual = reader.read(frame["attempt_key"][0], "rx-1")
        assert len(actual) == len(frame)
        assert actual["receiver_id"].unique().to_list() == ["rx-1"]
        assert "nominal_rate_hz" not in actual.columns
    finally:
        reader.close()


def test_preprocess_dataset_saves_arrays_and_summary_in_order(tmp_path):
    source = tmp_path / "parquet"
    source.mkdir()
    frame = packets()
    frame.write_parquet(source / "packets.parquet")
    session = SimpleNamespace(
        path=source,
        manifest={
            "source_directory": str(tmp_path / "raw/session"),
            "session_id": "test",
        },
    )
    recordings = pl.DataFrame(
        [
            dict(
                attempt_key=frame["attempt_key"][0],
                receiver_ids="rx-1",
                activity_label="walk",
                scenario_id="walk",
                quality="good",
            )
        ]
    )
    summary = preprocess_dataset(
        session, recordings, tmp_path / "derived", progress=None
    )
    actual = prepare_recording(frame)
    filtered, replaced = hampel_subcarriers(actual.normalized, actual.time_seconds)
    with np.load(summary["output"][0]) as saved:
        np.testing.assert_array_equal(saved["amplitude"], filtered.astype(np.float32))
        np.testing.assert_array_equal(saved["hampel_replaced"], replaced)
        np.testing.assert_array_equal(saved["valid"], np.isfinite(actual.masked))
        np.testing.assert_array_equal(saved["scale_min"], actual.lower)
        assert saved["phase"].dtype.kind == "U"
    with pytest.raises(ValueError, match="outside raw"):
        preprocess_dataset(session, recordings, tmp_path / "raw/session", progress=None)


def test_save_recording_failure_preserves_previous_file(tmp_path):
    path = tmp_path / "recording.npz"
    save_recording(path, {"value": np.arange(3)})
    previous = path.read_bytes()
    with pytest.raises(ValueError, match="Object arrays"):
        save_recording(path, {"value": np.array([object()])})
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]
