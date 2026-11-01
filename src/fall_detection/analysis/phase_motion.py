"""Packet-level phase-motion measurements for within-session exploratory plots."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Sequence
from zipfile import BadZipFile

import numpy as np
import pandas as pd

from ..radio.acquisition import clock_sync
from ..radio.preprocessing import phase as phase_module
from . import phase_signals

_PHASES = ("countdown", "action", "recovery")
_ARRAY_FIELDS = (
    "seconds",
    "raw_score",
    "calibrated_score",
    "phase_code",
    "within_phase_lag",
)


@dataclass(frozen=True)
class PhaseMotionSamples:
    """Packet measurements plus recording coverage/cache diagnostics, without pooling."""

    samples: pd.DataFrame
    recordings: pd.DataFrame


def phase_change_matrix(
    values: np.ndarray,
    seconds: np.ndarray,
    lag_seconds: float,
    *,
    phase_codes: np.ndarray | None = None,
) -> np.ndarray:
    """Keep the signed circular change of every supplied subcarrier separately.

    Select the packet at or just before ``t - lag_seconds`` without resampling.
    Actual lag must not exceed 1.5 times the requested lag. No absolute value,
    subcarrier reduction, temporal filter, or interpolation is applied.

    Args:
        values: Masked phase matrix, shape (packets, subcarriers).
        seconds: Finite nondecreasing packet times in seconds.
        lag_seconds: Positive requested lag; changes are radians per lag.
        phase_codes: Optional integer code per packet. Negative means outside
            the analyzed phases. When supplied, both lag endpoints must have
            the same nonnegative code.

    Returns:
        A matrix matching values, containing signed changes in [-pi, pi].
        Missing endpoints affect only their own subcarrier. Unsupported lags
        and excluded phase transitions remain all-NaN rows.

    Raises:
        ValueError: Shapes, times, lag, or phase codes are invalid.
    """
    values, seconds = np.asarray(values), np.asarray(seconds)
    if values.ndim != 2 or seconds.ndim != 1 or len(values) != len(seconds):
        raise ValueError("Expected a phase matrix and matching one-dimensional times")
    if not np.isfinite(lag_seconds) or lag_seconds <= 0:
        raise ValueError("lag_seconds must be finite and positive")
    if not np.isfinite(seconds).all() or np.any(np.diff(seconds) < 0):
        raise ValueError("Packet times must be finite and nondecreasing")
    previous = np.searchsorted(seconds, seconds - lag_seconds, side="right") - 1
    current = np.flatnonzero(previous >= 0)
    current = current[
        (seconds[current] - seconds[previous[current]]) <= 1.5 * lag_seconds
    ]
    if phase_codes is not None:
        phase_codes = np.asarray(phase_codes)
        if phase_codes.shape != seconds.shape or not np.issubdtype(
            phase_codes.dtype, np.integer
        ):
            raise ValueError("phase_codes must be matching one-dimensional integers")
        current = current[
            (phase_codes[current] >= 0)
            & (phase_codes[current] == phase_codes[previous[current]])
        ]
    changes = np.full(values.shape, np.nan)
    changes[current] = np.angle(
        np.exp(1j * (values[current] - values[previous[current]]))
    )
    return changes


def phase_motion_score(
    values: np.ndarray, seconds: np.ndarray, lag_seconds: float
) -> np.ndarray:
    """Measure median absolute circular change at a requested time lag.

    Args:
        values: Masked phase matrix, shape (packets, eligible subcarriers).
        seconds: Finite nondecreasing packet times in seconds.
        lag_seconds: Positive requested lag; the result is radians per lag.

    Returns:
        One score per packet; unavailable endpoints/insufficient tones are NaN.
        A score requires at least half the supplied tones and at least three.
        Use identical baseline-eligible tones for raw/calibrated comparison.

    Raises:
        ValueError: Shapes, times, or lag are invalid.
    """
    changes = np.abs(phase_change_matrix(values, seconds, lag_seconds))
    enough = np.isfinite(changes).sum(axis=1) >= max(
        3, int(np.ceil(changes.shape[1] / 2))
    )
    score = np.full(len(seconds), np.nan)
    if enough.any():
        score[enough] = np.nanmedian(changes[enough], axis=1)
    return score


def load_phase_motion_samples(
    session_dir: str | Path,
    attempt_ids: Sequence[str],
    receiver_ids: Sequence[str],
    phase_intervals: pd.DataFrame,
    *,
    baseline_seconds: float = 1.0,
    lag_seconds: float = 0.1,
    cache_dir: str | Path | None = None,
    workers: int = 1,
    refresh: bool = False,
) -> PhaseMotionSamples:
    """Load per-packet scores for selected recordings with optional derived caches.

    Eligibility of attempts and fall/non-fall labels belongs to the caller.
    Tones qualify using the first ``baseline_seconds`` of countdown, with the
    same circular-resultant and three-sample criteria as the sanity notebook.
    Scores are not pooled. ``within_phase_lag`` marks packets whose two lag
    endpoints belong to the same phase; filter it before phase comparisons.
    Unavailable scores remain NaN rather than becoming stationary zeros.

    Args:
        session_dir: One schema-2 raw session bundle.
        attempt_ids: Trial/attempt identifiers such as ``"001/01"``.
        receiver_ids: Receiver identifiers to retain separately.
        phase_intervals: Integrity table with attempt_id, phase, and host
            phase_start_monotonic_ns/phase_end_monotonic_ns columns.
        baseline_seconds: Positive duration at the start of countdown.
        lag_seconds: Positive phase-motion lag in seconds.
        cache_dir: Optional directory outside raw data for NumPy summaries.
        workers: Positive process count for uncached recordings only.
        refresh: Ignore valid cache entries and recompute.

    Returns:
        Packet measurements and per-recording diagnostics. Failed recordings
        appear in ``recordings.read_error`` and contribute no sample rows.

    Raises:
        ValueError: Parameters or the cache directory are invalid.
    """
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1:
        raise ValueError("workers must be a positive integer")
    if not np.isfinite(baseline_seconds) or baseline_seconds <= 0:
        raise ValueError("baseline_seconds must be finite and positive")
    if not np.isfinite(lag_seconds) or lag_seconds <= 0:
        raise ValueError("lag_seconds must be finite and positive")
    root = Path(session_dir).resolve()
    cache = Path(cache_dir).resolve() if cache_dir is not None else None
    raw_root = (
        root.parent.parent
        if root.parent.name == "sessions" and root.parent.parent.name == "raw"
        else root
    )
    if cache is not None and cache.is_relative_to(raw_root):
        raise ValueError("Place phase-motion caches outside raw session data")
    manifest = json.loads((root / "session.json").read_text())
    if manifest.get("status") == "open":
        cache = None
    code_hash = hashlib.sha256(
        b"".join(
            Path(module.__file__).read_bytes()
            for module in (phase_signals, phase_module, clock_sync)
        )
        + Path(__file__).read_bytes()
    ).hexdigest()
    attempt_paths = {}
    for path in root.glob("trials/*/attempt_*/attempt.json"):
        metadata = json.loads(path.read_text())
        number = int(path.parent.name.removeprefix("attempt_"))
        attempt_paths[f"{int(metadata['trial_ordinal']):03d}/{number:02d}"] = path
    jobs = []
    for attempt_id in dict.fromkeys(attempt_ids):
        rows = phase_intervals.loc[phase_intervals["attempt_id"].eq(attempt_id)]
        intervals = [
            (
                row.phase,
                int(row.phase_start_monotonic_ns),
                int(row.phase_end_monotonic_ns),
            )
            for row in rows.itertuples()
        ]
        for receiver_id in dict.fromkeys(receiver_ids):
            jobs.append(
                (
                    root,
                    attempt_id,
                    receiver_id,
                    intervals,
                    baseline_seconds,
                    lag_seconds,
                )
            )
    entries = [_cache_entry(job, cache, code_hash, attempt_paths) for job in jobs]
    results = [
        _read_cache(path, fingerprint) if not refresh else None
        for _, fingerprint, path in entries
    ]
    pending = [index for index, result in enumerate(results) if result is None]
    if workers > 1 and len(pending) > 1:
        with ProcessPoolExecutor(
            max_workers=min(workers, len(pending)),
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            futures = [pool.submit(_score_recording, jobs[index]) for index in pending]
            for index, future in zip(pending, futures):
                results[index] = future.result()
    else:
        for index in pending:
            results[index] = _score_recording(jobs[index])
    for index in pending:
        source, fingerprint, path = entries[index]
        if (
            path is not None
            and not results[index]["read_error"]
            and source == _source_files(jobs[index], attempt_paths)
        ):
            _write_cache(path, fingerprint, results[index])
    samples, diagnostics = [], []
    for index, (job, result) in enumerate(zip(jobs, results)):
        _, attempt_id, receiver_id, _, _, _ = job
        info = {key: value for key, value in result.items() if key not in _ARRAY_FIELDS}
        info.update(
            attempt_id=attempt_id,
            receiver_id=receiver_id,
            cache_hit=index not in pending,
        )
        diagnostics.append(info)
        if result["read_error"]:
            continue
        frame = pd.DataFrame({key: result[key] for key in _ARRAY_FIELDS})
        frame["phase"] = frame.pop("phase_code").map(dict(enumerate(_PHASES)))
        frame["attempt_id"], frame["receiver_id"] = attempt_id, receiver_id
        samples.append(frame)
    columns = [
        "seconds",
        "raw_score",
        "calibrated_score",
        "within_phase_lag",
        "phase",
        "attempt_id",
        "receiver_id",
    ]
    table = (
        pd.concat(samples, ignore_index=True)
        if samples
        else pd.DataFrame(columns=columns)
    )
    return PhaseMotionSamples(table, pd.DataFrame(diagnostics))


def _score_recording(job):
    root, attempt_id, receiver_id, intervals, baseline_seconds, lag_seconds = job
    try:
        by_phase = {name: (start, stop) for name, start, stop in intervals}
        if len(intervals) != 3 or set(by_phase) != set(_PHASES):
            raise ValueError(
                "Exactly one countdown/action/recovery interval is required"
            )
        if any(stop <= start for start, stop in by_phase.values()):
            raise ValueError("Phase intervals must have positive duration")
        signal = phase_signals.load_phase_signal(root, attempt_id, receiver_id)
        start, stop = by_phase["countdown"]
        baseline_start = (start - signal.started_monotonic_ns) / 1e9
        baseline_end = min(
            baseline_start + baseline_seconds,
            (stop - signal.started_monotonic_ns) / 1e9,
        )
        times = signal.time_seconds
        baseline = signal.calibrated_phase[
            (times >= baseline_start) & (times < baseline_end)
        ]
        counts = np.isfinite(baseline).sum(axis=0)
        resultant = np.nansum(np.exp(1j * baseline), axis=0)
        eligible = (counts >= 3) & (np.abs(resultant) > 1e-6 * counts)
        if eligible.sum() < 3:
            raise ValueError("Too few valid countdown baseline tones")
        labels = np.full(len(times), -1, dtype=np.int8)
        for code, name in enumerate(_PHASES):
            start, stop = by_phase[name]
            start_s, stop_s = (
                np.asarray([start, stop]) - signal.started_monotonic_ns
            ) / 1e9
            mask = (times >= start_s) & (times < stop_s)
            if np.any(labels[mask] >= 0):
                raise ValueError("Overlapping phase intervals")
            labels[mask] = code
        previous = np.searchsorted(times, times - lag_seconds, side="right") - 1
        same_phase = np.zeros(len(times), dtype=bool)
        paired = np.flatnonzero(previous >= 0)
        same_phase[paired] = (labels[paired] >= 0) & (
            labels[paired] == labels[previous[paired]]
        )
        raw = phase_motion_score(signal.raw_phase[:, eligible], times, lag_seconds)
        calibrated = phase_motion_score(
            signal.calibrated_phase[:, eligible], times, lag_seconds
        )
        return {
            "seconds": times,
            "raw_score": raw,
            "calibrated_score": calibrated,
            "phase_code": labels,
            "within_phase_lag": same_phase,
            "packet_count": len(times),
            "baseline_tones": int(eligible.sum()),
            "baseline_start_s": baseline_start,
            "baseline_end_s": baseline_end,
            "unassigned_packets": int((labels < 0).sum()),
            "time_source": signal.time_source,
            "read_error": "",
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"read_error": str(exc)}


def _source_files(job, attempt_paths):
    root, attempt_id, receiver_id, _, _, _ = job
    paths = [root / "session.json"]
    path = attempt_paths.get(attempt_id)
    if path is not None:
        paths.append(path)
        paths.extend(
            path.parent / "receivers" / receiver_id / name
            for name in (
                "csi.csv",
                "radio_timing.csv",
                "usb_clock_sync.csv",
                "ble_timing.jsonl",
            )
        )
    return [
        (
            str(path),
            path.stat().st_size,
            path.stat().st_mtime_ns,
            path.stat().st_ctime_ns,
        )
        if path.is_file()
        else (str(path), None)
        for path in paths
    ]


def _cache_entry(job, cache, code_hash, attempt_paths):
    source = _source_files(job, attempt_paths)
    root, attempt_id, receiver_id, intervals, baseline_seconds, lag_seconds = job
    fingerprint = hashlib.sha256(
        json.dumps(
            [code_hash, source, intervals, baseline_seconds, lag_seconds],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    name = hashlib.sha256(f"{root}/{attempt_id}/{receiver_id}".encode()).hexdigest()
    return source, fingerprint, cache / f"{name}.npz" if cache is not None else None


def _read_cache(path, fingerprint):
    if path is None or not path.is_file():
        return None
    try:
        with np.load(path, allow_pickle=False) as stored:
            if str(stored["fingerprint"].item()) != fingerprint:
                return None
            info = json.loads(str(stored["metadata"].item()))
            return {**info, **{name: stored[name].copy() for name in _ARRAY_FIELDS}}
    except (OSError, ValueError, KeyError, BadZipFile, EOFError):
        return None


def _write_cache(path, fingerprint, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {key: value for key, value in result.items() if key not in _ARRAY_FIELDS}
    temporary = None
    try:
        with NamedTemporaryFile(
            "wb", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(
                stream,
                fingerprint=fingerprint,
                metadata=json.dumps(metadata),
                **{key: result[key] for key in _ARRAY_FIELDS},
            )
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
