"""Check score semantics, phase-boundary guards, and derived cache invalidation."""

import os
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest
from polars.testing import assert_frame_equal

pytest.importorskip("pyarrow")

from journal_builder import RX1, TX, write_session

from fall_detection.analysis import phase_motion
from fall_detection.analysis.phase_motion import (
    load_phase_motion_samples,
    phase_change_matrix,
    phase_motion_score,
)
from fall_detection.analysis.session_frames import load_analysis_session
from fall_detection.radio.preprocessing.phase import HE20_COMPACT_SLOT_INDICES


def test_phase_change_matrix_keeps_localized_signed_motion_separate():
    seconds = np.array([0.0, 0.1, 0.2])
    values = np.zeros((3, 20))
    values[1:, 2] = 0.6
    values[1:, 5] = -0.4
    changes = phase_change_matrix(values, seconds, 0.1)
    assert changes.shape == values.shape
    assert np.isnan(changes[0]).all()
    assert changes[1, 2] == pytest.approx(0.6)
    assert changes[1, 5] == pytest.approx(-0.4)
    assert np.count_nonzero(changes[1]) == 2
    assert phase_motion_score(values, seconds, 0.1)[1] == 0


def test_phase_change_matrix_uses_circular_difference_and_per_tone_masks():
    seconds = np.array([0.0, 0.1])
    values = np.array([[3.12, -3.12, np.nan, 0], [-3.12, 3.12, 0, np.nan]])
    changes = phase_change_matrix(values, seconds, 0.1)
    np.testing.assert_allclose(changes[1, :2], [2 * np.pi - 6.24, 6.24 - 2 * np.pi])
    assert np.isnan(changes[1, 2:]).all()


def test_phase_change_matrix_excludes_phase_transitions_and_unsupported_gaps():
    seconds = np.array([0.0, 0.125, 0.25, 0.375, 1.0, 1.125])
    values = np.tile(seconds[:, None], (1, 4))
    codes = np.array([0, 0, 1, 1, 1, -1])
    changes = phase_change_matrix(values, seconds, 0.125, phase_codes=codes)
    np.testing.assert_allclose(changes[[1, 3]], 0.125)
    assert np.isnan(changes[[0, 2, 4, 5]]).all()


def test_phase_change_matrix_retains_supported_same_phase_pairs():
    seconds = np.arange(31) / 100
    values = np.tile(seconds[:, None], (1, 4))
    codes = np.where(seconds < 0.15, 0, 1)
    changes = phase_change_matrix(values, seconds, 0.1, phase_codes=codes)
    assert np.isnan(changes[15:25]).all()
    assert np.isfinite(changes[26:]).all()


@pytest.mark.parametrize("codes", [np.zeros((2, 2)), np.zeros(3), [0.0, 1.0]])
def test_phase_change_matrix_rejects_invalid_phase_codes(codes):
    with pytest.raises(ValueError, match="phase_codes"):
        phase_change_matrix(
            np.zeros((2, 4)), np.array([0.0, 0.1]), 0.1, phase_codes=codes
        )


def test_phase_motion_score_handles_circular_wrap_and_known_rate():
    seconds = np.arange(101) / 100
    values = np.tile(np.angle(np.exp(1j * (3.12 + 0.5 * seconds)))[:, None], (1, 6))
    scores = phase_motion_score(values, seconds, 0.1)
    assert np.isnan(scores[:10]).all()
    assert np.nanmin(scores) >= 0.049999999
    assert np.nanmax(scores) <= 0.055000001


def test_phase_motion_score_does_not_invent_values_for_missing_tones_or_endpoints():
    seconds = np.array([0.0, 0.1, 0.2, 1.0])
    values = np.tile(seconds[:, None], (1, 6))
    assert np.isnan(phase_motion_score(values, seconds, 0.1)[-1])
    values[:, :4] = np.nan
    assert np.isnan(phase_motion_score(values, seconds, 0.1)).all()


@pytest.fixture
def motion_source(tmp_path, monkeypatch):
    root = write_session(
        tmp_path / "data/raw/sessions/session",
        attempts=[
            {
                "trial_ordinal": 1,
                "activity_label": "sit",
                "status": "accepted",
                "started_monotonic_ns": 0,
                "ended_monotonic_ns": 3_000_000_000,
            }
        ],
        frames=[
            {
                "receiver": RX1,
                "sequence": index,
                "capture_ns": 1_000_000 * index,
                "transmitter": TX,
                "sig_mode": 4,
            }
            for index in range(3)
        ],
    )
    session = load_analysis_session(root, tmp_path / "derived")
    seconds = np.arange(300) / 100
    values = np.tile((0.02 * seconds)[:, None], (1, 6))
    signal = SimpleNamespace(
        time_seconds=seconds,
        raw_phase=values.copy(),
        calibrated_phase=values.copy(),
        started_monotonic_ns=0,
        time_source="synthetic host clock",
    )
    calls = []

    def load(*args):
        calls.append(args)
        return signal

    monkeypatch.setattr(phase_motion.phase_signals, "load_phase_signal", load)
    intervals = pl.DataFrame(
        {
            "attempt_id": ["001/01"] * 3,
            "phase": ["countdown", "action", "recovery"],
            "phase_start_monotonic_ns": [0, 1_000_000_000, 2_000_000_000],
            "phase_end_monotonic_ns": [1_000_000_000, 2_000_000_000, 3_000_000_000],
        }
    )
    return session, signal, calls, intervals


def test_load_phase_motion_samples_marks_cross_boundary_lags(motion_source):
    session, _, calls, intervals = motion_source
    result = load_phase_motion_samples(session, ["001/01"], ["rx-1"], intervals)
    frame = result.samples
    assert calls[0][:3] == (session, "001/01", "rx-1")
    assert dict(frame["phase"].value_counts().iter_rows()) == {
        "action": 100,
        "countdown": 100,
        "recovery": 100,
    }
    assert not frame.filter(pl.col("seconds") == 1.0)["within_phase_lag"].item()
    assert frame.filter(pl.col("seconds") == 1.2)["within_phase_lag"].item()
    early = frame.filter(pl.col("seconds") < 0.1)["calibrated_score"]
    assert early.is_null().all()
    assert not frame["raw_score"].is_nan().any()
    assert not frame["calibrated_score"].is_nan().any()
    assert result.recordings[0, "baseline_tones"] == 6


def test_load_phase_motion_samples_keeps_failed_recordings_visible(motion_source):
    session, signal, _, intervals = motion_source
    signal.calibrated_phase[:100, :4] = np.nan
    result = load_phase_motion_samples(session, ["001/01"], ["rx-1"], intervals)
    assert result.samples.is_empty()
    assert "baseline tones" in result.recordings[0, "read_error"]


def test_load_phase_motion_samples_invalidates_frame_tables_and_parameters(
    motion_source, tmp_path
):
    session, _, calls, intervals = motion_source
    cache = tmp_path / "derived-cache"
    initial = load_phase_motion_samples(
        session, ["001/01"], ["rx-1"], intervals, cache_dir=cache
    )
    cached = load_phase_motion_samples(
        session, ["001/01"], ["rx-1"], intervals, cache_dir=cache
    )
    assert len(calls) == 1
    assert cached.recordings[0, "cache_hit"]
    assert_frame_equal(initial.samples, cached.samples)
    for count, name in enumerate(
        ("frames.parquet", "attempts.parquet", "phases.parquet", "conversion.json"),
        start=2,
    ):
        path = session.path / name
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        load_phase_motion_samples(
            session, ["001/01"], ["rx-1"], intervals, cache_dir=cache
        )
        assert len(calls) == count
    changed = intervals.with_columns(
        pl.Series(
            "phase_end_monotonic_ns", [900_000_000, 2_000_000_000, 3_000_000_000]
        ),
        pl.Series("phase_start_monotonic_ns", [0, 900_000_000, 2_000_000_000]),
    )
    load_phase_motion_samples(session, ["001/01"], ["rx-1"], changed, cache_dir=cache)
    assert len(calls) == 6
    load_phase_motion_samples(
        session, ["001/01"], ["rx-1"], changed, lag_seconds=0.2, cache_dir=cache
    )
    assert len(calls) == 7


def test_load_phase_motion_samples_rejects_cache_inside_raw_data(motion_source):
    session, _, _, intervals = motion_source
    root = session.manifest["source_directory"]
    with pytest.raises(ValueError, match="outside raw"):
        load_phase_motion_samples(
            session, ["001/01"], ["rx-1"], intervals, cache_dir=f"{root}/cache"
        )


def test_load_phase_motion_samples_recovers_corrupt_cache(motion_source, tmp_path):
    session, _, calls, intervals = motion_source
    cache = tmp_path / "derived-cache"
    load_phase_motion_samples(session, ["001/01"], ["rx-1"], intervals, cache_dir=cache)
    next(cache.glob("*.npz")).write_bytes(b"broken")
    result = load_phase_motion_samples(
        session, ["001/01"], ["rx-1"], intervals, cache_dir=cache
    )
    assert len(calls) == 2
    assert not result.recordings[0, "cache_hit"]


def test_load_phase_motion_samples_decodes_journaled_csi_in_worker_processes(
    tmp_path,
):
    slots = np.asarray(HE20_COMPACT_SLOT_INDICES)
    values = 40 * np.exp(1j * (0.02 * slots + 0.3))
    pairs = np.column_stack((np.rint(values.imag), np.rint(values.real)))
    payload = bytes(int(value) & 0xFF for value in pairs.astype(int).ravel())
    root = write_session(
        tmp_path / "data/raw/sessions/real",
        attempts=[
            {
                "trial_ordinal": 1,
                "activity_label": "sit",
                "status": "accepted",
                "started_monotonic_ns": 0,
                "ended_monotonic_ns": 3_000_000_000,
            }
        ],
        frames=[
            {
                "receiver": RX1,
                "sequence": index,
                "capture_ns": index * 10_000_000,
                "payload": payload,
                "transmitter": TX,
                "sig_mode": 4,
            }
            for index in range(300)
        ],
    )
    session = load_analysis_session(root, tmp_path / "derived")
    intervals = pl.DataFrame(
        {
            "attempt_id": ["001/01"] * 3,
            "phase": ["countdown", "action", "recovery"],
            "phase_start_monotonic_ns": [0, 1_000_000_000, 2_000_000_000],
            "phase_end_monotonic_ns": [1_000_000_000, 2_000_000_000, 3_000_000_000],
        }
    )
    serial = load_phase_motion_samples(session, ["001/01"], ["rx-1"], intervals)
    parallel = load_phase_motion_samples(
        session, ["001/01", "001/01"], ["rx-1", "rx-2"], intervals, workers=2
    )
    assert serial.recordings[0, "read_error"] == ""
    assert serial.samples.height == 300
    assert dict(serial.samples["phase"].value_counts().iter_rows()) == dict.fromkeys(
        ("countdown", "action", "recovery"), 100
    )
    # A constant-phase channel has zero circular change wherever a lag exists.
    calibrated = serial.samples["calibrated_score"]
    assert not calibrated.is_nan().any()
    assert calibrated.null_count() > 0
    known = calibrated.filter(calibrated.is_not_null())
    assert known.len() > 0
    assert known.abs().max() < 1e-9
    assert parallel.recordings["read_error"][0] == ""
    assert "rx-2" in parallel.recordings["read_error"][1]
    assert_frame_equal(
        serial.samples, parallel.samples.filter(pl.col("receiver_id") == "rx-1")
    )
