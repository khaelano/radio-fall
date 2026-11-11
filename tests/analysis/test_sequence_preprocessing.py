"""Checks for exploratory sequence-grid preprocessing."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.amplitude_pipeline import prepare_recording, save_recording
from fall_detection.analysis.sequence_preprocessing import (
    RECEIVERS,
    SequenceDataset,
    align_epoch,
    align_samples,
    filter_and_difference,
    label_windows,
    sequence_offsets,
    source_rounds,
    split_packet_epochs,
    squared_difference,
    window_starts,
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
    filtered, mask, diff = filter_and_difference(values, min_periods=5)
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
    actual, replaced, _ = filter_and_difference(values)
    np.testing.assert_array_equal(actual, expected)
    assert replaced[50, 0] and not replaced[51, 0]


@pytest.mark.parametrize("seconds", [2, 4, 6])
def test_window_starts_respects_boundaries(seconds):
    size = seconds * 96
    np.testing.assert_array_equal(window_starts(size - 1, seconds), [])
    np.testing.assert_array_equal(
        window_starts(size * 2, seconds), [0, size // 2, size]
    )


def epoch_frame():
    rows = []
    for r in range(3):  # rx-4 is entirely absent.
        for index, sequence in enumerate([2**32 - 2, 2**32 - 1, 0, 0, 1, 2, 3, 4]):
            if r == 1 and index == 2:
                continue
            count = 245 if index % 2 else 256
            rows.append(
                dict(
                    attempt_key="trial/attempt",
                    attempt_id="001/01",
                    receiver_id=f"rx-{r + 1}",
                    is_sensing=True,
                    time_source="test",
                    time_seconds=index / 120,
                    capture_time_ns=1_000_000_000 + index * 8_333_333,
                    phase="action",
                    driver_valid=index != 6,
                    sig_mode=4,
                    bandwidth=0,
                    stbc=0,
                    first_word=index % 2,
                    len=count * 2,
                    csi_i=[10 + index] * count,
                    csi_q=[5] * count,
                    attempt_started_monotonic_ns=1_000_000_000,
                    attempt_ended_monotonic_ns=2_000_000_000,
                    sequence=sequence,
                    run_id="run",
                    transmitter_boot_id="tx",
                    receiver_boot_id=f"rx-{r}",
                    nominal_rate_hz=120.0,
                    source_row=index,
                    clock_uncertainty_us=0.0,
                )
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
def test_center_cue_labels_omit_other_fall_windows_and_keep_nonfalls(seconds):
    times = np.rint(np.arange(seconds * 96 * 3) / 96 * 1e9).astype(np.int64)
    all_starts, _ = label_windows(times, seconds, "non_fall", [])
    assert len(all_starts) == 5
    selected, omitted = label_windows(
        times,
        seconds,
        "stand_to_fall",
        [(seconds * 1_000_000_000, seconds * 2_000_000_000)],
    )
    np.testing.assert_array_equal(selected, all_starts[1:3])
    assert omitted == 3
    assert len(label_windows(times[:100], seconds, "non_fall", [])[0]) == 0
    with pytest.raises(ValueError, match="Unknown"):
        label_windows(times, seconds, "mystery", [])


def test_windows_export_reload_and_segment_difference_isolation(tmp_path, monkeypatch):
    w = SequenceDataset(tmp_path, "test", "session", shard_windows=2, format_version=1)
    n = 6 * 96
    values = np.random.default_rng(2).normal(20, 1, (n, 4, 245))
    values[10:15, 1] = np.nan
    times = np.rint(np.arange(n) / 96 * 1e9).astype(np.int64)
    arrays = dict(
        amplitude=values,
        filtered_amplitude=values,
        valid=np.isfinite(values),
        filtered_valid=np.isfinite(values),
        hampel_replaced=np.zeros_like(values, dtype=bool),
        squared_difference=squared_difference(values),
        sequence=np.arange(n, dtype=np.uint32),
        sequence_offset=np.arange(n),
        time_ns=times,
        capture_time_ns=np.tile(times[:, None], (1, 4)),
        phase=np.full(n, "action"),
        subcarriers=np.arange(-122, 123),
        receivers=np.asarray(RECEIVERS),
    )
    arrays["difference_valid"] = np.isfinite(arrays["squared_difference"])
    path = w.output / "segments/one.npz"
    save_recording(path, arrays)
    segment = dict(
        participant_id="p",
        session_id="session",
        attempt_key="trial/attempt",
        attempt_id="001/01",
        trial_ordinal=1,
        attempt=1,
        activity_label="non_fall",
        scenario_id="activity",
        segment_id="one",
        run_id="r",
        transmitter_boot_id="b",
        path=str(path),
        samples=n,
    )
    short_path = w.output / "segments/short.npz"
    save_recording(
        short_path, {"time_ns": times[:10], "valid": np.isfinite(values[:10])}
    )
    w.segments = pl.DataFrame(
        [segment, dict(segment, segment_id="short", path=str(short_path), samples=10)]
    )
    w.phases = pl.DataFrame(
        {
            "attempt_key": ["trial/attempt"],
            "phase": ["action"],
            "start_ns": [0],
            "end_ns": [10**10],
        }
    )
    w.attempts = pl.DataFrame({"attempt_key": ["trial/attempt"]})
    w.selected = w.attempts
    w.selection = w.attempts.with_columns(pl.lit(True).alias("selected"))
    w.recordings = pl.DataFrame({"packets": [n] * 4})
    w.session = SimpleNamespace(manifest={"source_fingerprint": "test"})
    w.windows()
    from fall_detection.analysis import sequence_preprocessing as module

    w.workers = 16
    w.memory_budget_mb = 64
    reserved = {"bytes": 0, "peak": 0}

    class DeferredWriter:
        def __init__(self, max_workers, **kwargs):
            assert max_workers == 16

        def __enter__(self):
            return self

        def __exit__(self, *args):
            assert reserved["bytes"] == 0

        def submit(self, function, path, arrays, metadata, **kwargs):
            size = metadata["windows"] * metadata["duration"] * 96 * 4 * 245 * 35
            reserved["bytes"] += size
            reserved["peak"] = max(reserved["peak"], reserved["bytes"])
            assert reserved["bytes"] <= w.memory_budget_mb * 1024**2

            class Pending:
                def result(self):
                    reserved["bytes"] -= size
                    return function(path, arrays, metadata, **kwargs)

            return Pending()

    with monkeypatch.context() as patch:
        patch.setattr(module, "ThreadPoolExecutor", DeferredWriter)
        w.export()
    assert reserved["peak"] > 0
    assert not short_path.exists() and path.exists()
    assert w.segments["cached"].sum() == 1
    assert w.index.group_by("duration").len().sort("duration")["len"].to_list() == [
        5,
        2,
        1,
    ]
    assert sum(w.shards["windows"]) == 8
    assert max(w.shards["windows"]) <= 2
    assert (w.output / "manifest.json").exists()
    for row in w.index.iter_rows(named=True):
        with np.load(w.output / row["shard"]) as d:
            assert d["amplitude"].dtype == np.float64
            assert d["amplitude"].flags.f_contiguous
            np.testing.assert_array_equal(
                d["amplitude"][row["shard_row"]], values[row["start"] : row["stop"]]
            )
            assert d["target"][row["shard_row"]] == 0
    # A completed export can be reloaded after its disposable cache is reclaimed.
    w.load_exported()
    assert len(w.index) == 8
    w.gap_seconds = 2.0
    with pytest.raises(ValueError, match="parameters differ"):
        w.load_exported()
    w.gap_seconds = 1.0
    shard_path = w.output / w.index["shard"][0]
    with shard_path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="hash or path differs"):
        w.load_exported()
    assert np.isnan(arrays["squared_difference"][0]).all()
    assert np.isnan(arrays["squared_difference"][10:16, 1]).all()
    np.testing.assert_array_equal(
        squared_difference(values[:2])[0], np.full((4, 245), np.nan)
    )


def test_short_segment_exports_empty_index_and_manifest(tmp_path):
    w = SequenceDataset(tmp_path, "short", "s", format_version=1)
    path = w.output / "segments/short.npz"
    save_recording(
        path, {"time_ns": np.arange(10), "valid": np.zeros((10, 4, 245), bool)}
    )
    w.segments = pl.DataFrame(
        [
            dict(
                path=str(path),
                segment_id="short",
                attempt_key="a",
                activity_label="non_fall",
                samples=10,
            )
        ]
    )
    w.phases = pl.DataFrame(
        {"attempt_key": ["a"], "phase": ["action"], "start_ns": [0], "end_ns": [10]}
    )
    w.attempts = w.selected = pl.DataFrame({"attempt_key": ["a"]})
    w.selection = w.attempts.with_columns(pl.lit(True).alias("selected"))
    w.recordings = pl.DataFrame({"packets": [10]})
    w.session = SimpleNamespace(manifest={})
    w.windows()
    w.export()
    assert w.index.is_empty() and w.shards.is_empty()
    assert w.omissions["candidates"].sum() == 0
    assert (w.output / "manifest.json").exists()


def test_nominal_clock_edges_cannot_cross_recorded_attempt_bounds():
    times = np.rint(np.arange(6 * 96) / 96 * 1e9).astype(np.int64) - 100
    starts, omitted = label_windows(times, 2, "non_fall", [], (0, 5_000_000_000))
    np.testing.assert_array_equal(starts, [96, 192, 288])
    assert (
        omitted == 0
    )  # This counter is cue omissions, separate from boundary omissions.
    assert np.all(times[starts] >= 0)
    assert np.all(times[starts] + 2_000_000_000 <= 5_000_000_000)


def test_verified_shards_use_provenance_receipts_and_invalidate_changed_inputs(
    tmp_path, monkeypatch
):
    from fall_detection.analysis import sequence_preprocessing as module

    arrays = {"values": np.asfortranarray([[1.0, np.nan], [2.0, 3.0]])}
    path = tmp_path / "shard.npz"
    first = module._verified_shard(path, arrays, {"windows": 2}, resume_key="original")
    stamp = path.stat().st_mtime_ns
    with monkeypatch.context() as patch:
        patch.setattr(
            module.np,
            "load",
            lambda *args, **kwargs: pytest.fail("decompressed cache hit"),
        )
        patch.setattr(
            module,
            "save_recording",
            lambda *args, **kwargs: pytest.fail("rewrote identical shard"),
        )
        assert (
            module._verified_shard(path, arrays, {"windows": 2}, resume_key="original")
            == first
        )
    assert path.stat().st_mtime_ns == stamp
    changed = {"values": np.asfortranarray([[9.0, np.nan], [2.0, 3.0]])}
    second = module._verified_shard(path, changed, {"windows": 2}, resume_key="changed")
    assert second["sha256"] != first["sha256"]
    path.write_bytes(b"corrupt zip")
    module._verified_shard(path, arrays, {"windows": 2}, resume_key="original")
    with np.load(path) as saved:
        np.testing.assert_array_equal(saved["values"], arrays["values"])


def test_uncompressed_stage_cache_skips_numeric_io_and_invalidates_parameters(
    tmp_path, monkeypatch
):
    from fall_detection.analysis import sequence_preprocessing as module
    from fall_detection.analysis.sequence_cache import read_segment

    source = tmp_path / "parquet"
    source.mkdir()
    epoch_frame().write_parquet(source / "packets.parquet")
    w = SequenceDataset(tmp_path, "stages", "s", format_version=1)
    w.session = SimpleNamespace(path=source, manifest={"source_fingerprint": "source"})
    w.selected = pl.DataFrame(
        [
            dict(
                attempt_key="trial/attempt",
                participant_id="p",
                session_id="s",
                attempt_id="001/01",
                trial_ordinal=1,
                attempt=1,
                activity_label="non_fall",
                scenario_id="activity",
                review_revision=0,
                started_monotonic_ns=1_000_000_000,
                ended_monotonic_ns=2_000_000_000,
            )
        ]
    )
    w.attempts = w.selected
    w.phases = pl.DataFrame(
        dict(
            attempt_key=["trial/attempt"],
            phase=["action"],
            start_ns=[1_000_000_000],
            end_ns=[2_000_000_000],
        )
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            module,
            "save_recording",
            lambda *a, **k: pytest.fail("compressed intermediate"),
        )
        w.align()
        w.filter()
        w.difference()
        w.windows()
    path = Path(w.segments["path"][0])
    assert path.is_dir() and not list(path.glob("*.npz"))
    with read_segment(path) as values:
        assert isinstance(values["amplitude"], np.memmap)
        np.testing.assert_array_equal(
            values["squared_difference"],
            squared_difference(values["filtered_amplitude"]),
        )
    stamp = (path / "amplitude.npy").stat().st_mtime_ns
    with monkeypatch.context() as patch:
        patch.setattr(
            module.np, "load", lambda *a, **k: pytest.fail("opened cached signal")
        )
        patch.setattr(
            module,
            "prepare_recording",
            lambda *a, **k: pytest.fail("decoded cached signal"),
        )
        w.align()
        w.filter()
        w.difference()
        w.windows()
    assert w.cache_hits == ["align_decode", "hampel", "difference", "window_index"]
    assert (path / "amplitude.npy").stat().st_mtime_ns == stamp
    w.gap_seconds = 2.0
    w.align()
    assert (path / "amplitude.npy").stat().st_mtime_ns != stamp


def test_new_shard_verification_is_opt_in_and_runs_once(tmp_path, monkeypatch):
    from fall_detection.analysis import sequence_preprocessing as module

    arrays = {"values": np.asfortranarray([[1.0, np.nan], [2.0, 3.0]])}
    original = module.np.load
    calls = []

    def tracked(*a, **k):
        calls.append(a[0])
        return original(*a, **k)

    monkeypatch.setattr(module.np, "load", tracked)
    module._verified_shard(tmp_path / "normal.npz", arrays, {}, resume_key="normal")
    assert not calls
    path = tmp_path / "audit.npz"
    module._verified_shard(path, arrays, {}, resume_key="audit", verify_new=True)
    assert len(calls) == 1
    module._verified_shard(path, arrays, {}, resume_key="audit", verify_new=True)
    assert len(calls) == 1


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

    w = SequenceDataset(tmp_path, "source", "session", format_version=1)
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
    w._load_session_cached()
    w._load_session_cached()
    # Even a replaced/backdated archive must invalidate an established receipt.
    raw.write_bytes(raw.read_bytes() + b"changed")
    os.utime(raw, ns=(1, 1))
    with pytest.raises(RuntimeError, match="full loader required"):
        w._load_session_cached()
