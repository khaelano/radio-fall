"""Checks for exploratory sequence-grid preprocessing."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.amplitude import hampel_subcarriers
from fall_detection.analysis.amplitude_pipeline import prepare_recording
from fall_detection.analysis.sequence_preprocessing import (
    RECEIVERS,
    SequenceArtifacts,
    align_epoch,
    align_samples,
    sequence_offsets,
    source_rounds,
    split_packet_epochs,
    squared_difference,
)


def test_sequence_offsets_wrap_duplicates_and_reset():
    offsets, anomalies = sequence_offsets(
        np.array([2**32 - 2, 2**32 - 1, 0, 0, 2]), 2**32 - 2
    )
    np.testing.assert_array_equal(offsets, [0, 1, 2, 2, 4])
    assert anomalies == {"duplicates": 1, "wraps": 1}
    with pytest.raises(ValueError, match="reset or out-of-order"):
        sequence_offsets(np.array([100, 101, 0]), 100)


def test_align_samples_point_sampling_and_missing():
    rounds = source_rounds(0, 8)
    np.testing.assert_array_equal(rounds, [0, 1, 3, 4, 5, 6, 8, 9])
    values, duplicates = align_samples(
        np.array([0, 1, 1, 4]), np.array([[0], [1], [9], [4]]), rounds
    )
    np.testing.assert_array_equal(
        values[:, 0], [0, 1, np.nan, 4, np.nan, np.nan, np.nan, np.nan]
    )
    assert duplicates == 1


def test_filter_and_difference_preserves_gaps():
    values = np.array([[1.0], [2.0], [np.nan], [4.0], [5.0]])
    filtered, mask = hampel_subcarriers(
        values,
        np.arange(len(values)) / 96,
        window_seconds=0.5,
        threshold=3,
        min_periods=5,
    )
    diff = squared_difference(filtered)
    np.testing.assert_array_equal(filtered, values)
    assert not mask.any()
    np.testing.assert_array_equal(diff[:, 0], [np.nan, 1, np.nan, np.nan, 1])


def test_filter_and_difference_matches_reference_hampel():
    values = np.tile(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), 20)[:, None]
    values[50, 0] = 100
    values[51, 0] = np.nan
    expected = values.copy()
    times = np.arange(len(values)) / 96
    for i, time in enumerate(times):
        neighborhood = values[np.abs(times - time) <= 0.25, 0]
        neighborhood = neighborhood[np.isfinite(neighborhood)]
        middle = np.median(neighborhood)
        mad = np.median(np.abs(neighborhood - middle))
        if (
            np.isfinite(values[i, 0])
            and mad
            and abs(values[i, 0] - middle) > 3 * 1.4826 * mad
        ):
            expected[i, 0] = middle
    actual, replaced = hampel_subcarriers(
        values, times, window_seconds=0.5, threshold=3, min_periods=5
    )
    np.testing.assert_array_equal(actual, expected)
    assert replaced[50, 0] and not replaced[51, 0]


def epoch_frame():
    rows = []
    for r in range(3):  # rx-4 is entirely absent.
        for index, sequence in enumerate([2**32 - 2, 2**32 - 1, 0, 0, 1, 2, 3, 4]):
            if r == 1 and index == 2:
                continue
            count = 245 if index % 2 else 256
            rows.append(
                {
                    "attempt_key": "trial/attempt",
                    "attempt_id": "001/01",
                    "receiver_id": f"rx-{r + 1}",
                    "is_sensing": True,
                    "time_source": "test",
                    "time_seconds": index / 120,
                    "capture_time_ns": 1_000_000_000 + index * 8_333_333,
                    "phase": "action",
                    "driver_valid": index != 6,
                    "sig_mode": 4,
                    "bandwidth": 0,
                    "stbc": 0,
                    "first_word": index % 2,
                    "len": count * 2,
                    "csi_i": [10 + index] * count,
                    "csi_q": [5] * count,
                    "attempt_started_monotonic_ns": 1_000_000_000,
                    "attempt_ended_monotonic_ns": 2_000_000_000,
                    "sequence": sequence,
                    "run_id": "run",
                    "transmitter_boot_id": "tx",
                    "receiver_boot_id": f"rx-{r}",
                    "nominal_rate_hz": 120.0,
                    "source_row": index,
                    "clock_uncertainty_us": 0.0,
                }
            )
    return pl.DataFrame(rows).with_columns(
        pl.col("csi_i", "csi_q").cast(pl.List(pl.Int16))
    )


def test_native_magnitude_only_matches_independent_physical_decoder():
    from fall_detection.analysis.phase_signals import phase_signal_from_packets

    for receiver in RECEIVERS[:3]:
        frame = epoch_frame().filter(pl.col("receiver_id") == receiver)
        actual = prepare_recording(frame, magnitude_only=True)
        reference = phase_signal_from_packets(frame.to_pandas())
        expected = np.abs(reference.complex_csi)
        expected[
            ~(
                np.isfinite(reference.raw_phase)
                & frame["driver_valid"].to_numpy()[:, None]
            )
        ] = np.nan
        np.testing.assert_array_equal(actual.masked, expected)
        assert actual.normalized is None and not len(actual.lower)


def test_four_view_alignment_rollover_duplicates_losses_and_missing_receiver():
    data, audit = align_epoch(epoch_frame())
    assert data["amplitude"].shape == (5, 4, 245)
    assert not data["valid"][:, 3].any()
    assert np.isnan(data["amplitude"][:, 3]).all()
    np.testing.assert_array_equal(data["sequence"], [2**32 - 2, 2**32 - 1, 1, 2, 3])
    assert sum(r["duplicates"] for r in audit) == 2
    assert sum(r["wraps"] for r in audit) == 3
    assert not data["valid"][-1].any()  # driver invalid on sequence 3
    # Selected-round receiver-specific loss remains absent without borrowing.
    f = epoch_frame().filter(
        ~((pl.col("receiver_id") == "rx-2") & (pl.col("sequence") == 1))
    )
    loss, _ = align_epoch(f)
    assert not loss["valid"][2, 1].any() and loss["valid"][2, 0].any()


def test_full_rate_alignment_retains_every_round_and_receiver_loss():
    frame = epoch_frame().filter(
        ~((pl.col("receiver_id") == "rx-2") & (pl.col("sequence") == 0))
    )
    data, _ = align_epoch(frame, rate_hz=120)
    np.testing.assert_array_equal(
        data["sequence"], [2**32 - 2, 2**32 - 1, 0, 1, 2, 3, 4]
    )
    assert data["amplitude"].shape == (7, 4, 245)
    assert data["capture_time_ns"][2, 1] == -1
    assert data["capture_time_ns"][2, 0] > 0
    assert not data["valid"][:, 3].any()


def test_epoch_boundaries_isolate_runs_boots_gaps_and_reject_unresolved_reset():
    frame = epoch_frame().filter(pl.col("receiver_id") == "rx-1").head(3)
    next_run = frame.with_columns(
        pl.lit("new-run").alias("run_id"),
        (pl.col("capture_time_ns") + 100_000_000).alias("capture_time_ns"),
    )
    assert len(split_packet_epochs(pl.concat([frame, next_run]))) == 2
    next_boot = next_run.with_columns(
        pl.lit("run").alias("run_id"), pl.lit("new-boot").alias("receiver_boot_id")
    )
    assert len(split_packet_epochs(pl.concat([frame, next_boot]))) == 2
    gap = frame.with_columns(
        (pl.col("capture_time_ns") + 2_000_000_000).alias("capture_time_ns")
    )
    assert len(split_packet_epochs(pl.concat([frame, gap]))) == 2
    reset = frame.with_columns(pl.Series("sequence", [100, 101, 0]))
    with pytest.raises(ValueError, match="reset or out-of-order"):
        align_epoch(reset)
    missing = frame.with_columns(
        pl.lit(None).cast(pl.String).alias("transmitter_boot_id")
    )
    with pytest.raises(ValueError, match="identity"):
        split_packet_epochs(missing)


@pytest.mark.parametrize("seconds", [2, 4, 6])
def test_center_cue_labels_omit_other_fall_windows_and_keep_nonfalls(
    seconds, notebook_label_windows
):
    label_windows = notebook_label_windows
    times = np.rint(np.arange(seconds * 96 * 3) / 96 * 1e9).astype(np.int64)
    all_starts, _ = label_windows(times, seconds, "non_fall", [], rate_hz=96)
    assert len(all_starts) == 5
    selected, omitted = label_windows(
        times,
        seconds,
        "stand_to_fall",
        [(seconds * 1_000_000_000, seconds * 2_000_000_000)],
        rate_hz=96,
    )
    np.testing.assert_array_equal(selected, all_starts[1:3])
    assert omitted == 3
    assert len(label_windows(times[:100], seconds, "non_fall", [], rate_hz=96)[0]) == 0
    with pytest.raises(ValueError, match="Unknown"):
        label_windows(times, seconds, "mystery", [], rate_hz=96)


def test_nominal_clock_edges_cannot_cross_recorded_attempt_bounds(
    notebook_label_windows,
):
    label_windows = notebook_label_windows
    times = np.rint(np.arange(6 * 96) / 96 * 1e9).astype(np.int64) - 100
    starts, omitted = label_windows(
        times, 2, "non_fall", [], (0, 5_000_000_000), rate_hz=96
    )
    np.testing.assert_array_equal(starts, [96, 192, 288])
    assert (
        omitted == 0
    )  # This counter is cue omissions, separate from boundary omissions.
    assert np.all(times[starts] >= 0)
    assert np.all(times[starts] + 2_000_000_000 <= 5_000_000_000)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": 3},
        {"source": None},
        {"source": {}},
        {"parameters": None},
        {
            "parameters": {
                "dtype": "float32",
                "target_hz": 120,
                "recording_gap_seconds": 1.0,
            }
        },
        {
            "parameters": {
                "dtype": "float32",
                "target_hz": 96,
                "recording_gap_seconds": 2.0,
            }
        },
    ],
)
def test_completed_export_rejects_changed_preprocessing(tmp_path, changes):
    import json

    workflow = SequenceArtifacts(
        tmp_path, "cached", "session", {"target_hz": 96, "recording_gap_seconds": 1.0}
    )
    workflow.session = SimpleNamespace(manifest={"source_fingerprint": "source"})
    workflow.output.mkdir(parents=True)
    manifest = {
        "schema": "amplitude_sequence",
        "version": 2,
        "source": {"source_fingerprint": "source"},
        "parameters": {
            "dtype": "float32",
            "target_hz": 96,
            "recording_gap_seconds": 1.0,
        },
    }
    manifest.update(changes)
    (workflow.output / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="preprocessing parameters"):
        workflow.load_exported()


def test_segment_reader_rejects_obsolete_npz_files(tmp_path):
    from fall_detection.analysis.sequence_cache import read_segment

    path = tmp_path / "old.npz"
    np.savez(path, amplitude=np.ones((1, 1)))
    with (
        pytest.raises(FileNotFoundError, match="segment directory"),
        read_segment(path),
    ):
        pass


def test_new_segment_stages_preserve_existing_array_files(tmp_path):
    from fall_detection.analysis.sequence_cache import read_segment, save_segment

    path = tmp_path / "segment"
    save_segment(path, {"amplitude": np.array([[1.0, np.nan], [2.0, 3.0]])})
    stamp = (path / "amplitude.npy").stat().st_mtime_ns
    with read_segment(path) as data:
        arrays = dict(data)
        arrays["difference"] = squared_difference(arrays["amplitude"])
        save_segment(path, arrays)
    assert (path / "amplitude.npy").stat().st_mtime_ns == stamp
    assert (path / "difference.npy").is_file()


def test_source_cache_invalidates_changed_archive_identity(tmp_path, monkeypatch):
    import hashlib
    import json
    import os
    from zipfile import ZipFile

    from fall_detection.analysis import phase_signals, session_parquet
    from fall_detection.analysis import sequence_preprocessing as module

    w = SequenceArtifacts(tmp_path, "source", "session", {"target_hz": 96})
    raw = tmp_path / "data/raw/sessions/session.zip"
    raw.parent.mkdir(parents=True)
    manifest = {
        "format": "fall-detection-session-archive",
        "version": 2,
        "files": [],
        "tables": [],
    }
    with ZipFile(raw, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    os.utime(raw, ns=(1, 1))
    directory = tmp_path / "data/interim/parquet/session"
    directory.mkdir(parents=True)
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode())
    for m in (session_parquet, phase_signals):
        digest.update(Path(m.__file__).read_bytes())
    (directory / "session.json").write_text(
        json.dumps(
            {
                "schema_version": session_parquet.SCHEMA_VERSION,
                "archive_fingerprint": digest.hexdigest(),
            }
        )
    )
    for name in ["attempts", "phases", "packets"]:
        pl.DataFrame({"id": [1]}).write_parquet(directory / f"{name}.parquet")

    def fallback(*args, **kwargs):
        raise RuntimeError("source changed; full loader required")

    monkeypatch.setattr(module, "load_amplitude_session", fallback)
    w.load_source()
    w.load_source()
    # Even a replaced/backdated archive must invalidate an established receipt.
    raw.write_bytes(raw.read_bytes() + b"changed")
    os.utime(raw, ns=(1, 1))
    with pytest.raises(RuntimeError, match="full loader required"):
        w.load_source()
