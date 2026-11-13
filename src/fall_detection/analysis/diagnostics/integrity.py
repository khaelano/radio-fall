"""Read-only dataset integrity analysis with optional derived-result caching."""

import hashlib
import json
import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import polars as pl

from ..._radio_native import storage_read as read_session_file
from ...protocol import protocol_from_mapping
from ...radio import phase as phase_module
from .. import _cache_keys, _frames, session_frames
from .._frames import as_polars
from .._io import atomic_bytes
from ..session_frames import AnalysisSession, load_analysis_session
from . import _receiver, _timeline

_IDENTITY_SCHEMA = {
    "attempt_id": pl.String,
    "trial_ordinal": pl.Int64,
    "attempt_number": pl.Int64,
    "activity_label": pl.String,
    "status": pl.String,
    "receiver_id": pl.String,
}
_RECEIVER_ATTEMPT_SCHEMA = {**_IDENTITY_SCHEMA, **_receiver.METRIC_SCHEMA}
_PHASE_PACKET_SCHEMA = {
    **_IDENTITY_SCHEMA,
    "phase": pl.String,
    "sensing_link_csi_rows": pl.Int64,
}
_ATTEMPT_SCHEMA = {
    "attempt_id": pl.String,
    "trial_ordinal": pl.Int64,
    "attempt_number": pl.Int64,
    "activity_label": pl.String,
    "planned_activity_label": pl.String,
    "status": pl.String,
}
_OVERVIEW_SCHEMA = {
    "session_id": pl.String,
    "started_at_utc": pl.String,
    "session_status": pl.String,
    "planned_trials": pl.Int64,
    "attempts_recorded": pl.Int64,
    "nominal_rate_hz": pl.Float64,
    "expected_receivers": pl.String,
    "unexpected_receivers": pl.String,
    "transmitter_mac": pl.String,
    "cached_receiver_recordings": pl.Int64,
    "scanned_receiver_recordings": pl.Int64,
    "analysis_seconds": pl.Float64,
}
_COVERAGE_SCHEMA = {
    "planned_trials": pl.Int64,
    "trials_with_attempts": pl.Int64,
    "planned_trials_never_started": pl.Int64,
    "trial_ordinals_never_started": pl.List(pl.Int64),
}
_RECEIVER_SUMMARY_SCHEMA = {
    "receiver_id": pl.String,
    "attempts_without_frames": pl.Int64,
    "raw_csi_rows": pl.Int64,
    "sensing_link_csi_rows": pl.Int64,
    "sequence_gap_missing_frames": pl.Int64,
    "sequence_gap_loss_pct": pl.Float64,
    "timestamp_gap_intervals": pl.Int64,
    "estimated_timestamp_gap_missing_frames": pl.Int64,
    "timestamp_resets": pl.Int64,
    "effective_sampling_rate_hz": pl.Float64,
    "median_attempt_rate_hz": pl.Float64,
    "median_interval_ms": pl.Float64,
    "median_attempt_p95_interval_ms": pl.Float64,
    "max_interval_ms": pl.Float64,
    "phase_mask_supported_rows": pl.Int64,
    "phase_mask_unsupported_rows": pl.Int64,
    "phase_mask_unreadable_rows": pl.Int64,
    "mean_usable_subcarriers_per_packet": pl.Float64,
    "usable_phase_subcarrier_fraction": pl.Float64,
    "unassigned_phase_rows": pl.Int64,
    "recordings_with_read_errors": pl.Int64,
}


def _numpy_reduce(
    column: str, function: Callable[[np.ndarray], float], name: str | None = None
) -> pl.Expr:
    """Reduce the non-null values of a column per group with a NumPy function.

    The summaries use NumPy's summation order and interpolation, which differ
    from polars' own reductions in the last floating-point bit, so reports
    stay identical to those computed before the migration to polars.

    Args:
        column: Float column to reduce.
        function: Reduction of a one-dimensional array, such as ``np.median``.
        name: Output name; defaults to ``column``.

    Returns:
        An aggregation expression that is null for a group without values.
    """

    def reduce(values: pl.Series) -> pl.Series:
        array = values.drop_nulls().to_numpy()
        return pl.Series(
            [float(function(array)) if array.size else None], dtype=pl.Float64
        )

    return (
        pl.col(column)
        .map_batches(reduce, returns_scalar=True, return_dtype=pl.Float64)
        .alias(name or column)
    )


@dataclass(frozen=True)
class SessionIntegrity:
    """Integrity tables for one session; all CSI metrics describe the sensing link.

    ``receivers`` contains pooled receiver totals. ``receiver_attempts`` and
    ``phase_attempts`` retain attempt-level detail for investigation. Sequence
    loss covers only gaps between received packets within each attempt, in
    delivery (journal) order. Phase packet counts assign sensing frames to
    phases by capture time on the host clock, the clock of the analysis packets.
    """

    session_dir: Path
    overview: pl.DataFrame
    attempts: pl.DataFrame
    trial_coverage: pl.DataFrame
    receivers: pl.DataFrame
    receiver_attempts: pl.DataFrame
    phase_intervals: pl.DataFrame
    phase_attempts: pl.DataFrame
    phase_packet_counts: pl.DataFrame

    @property
    def attempt_counts(self) -> pl.DataFrame:
        """Return attempt counts by effective activity label and capture status.

        Rows are sorted by label and end with an ``All`` total row; columns are
        the statuses sorted by name and an ``All`` total column.
        """
        if self.attempts.is_empty():
            return pl.DataFrame()
        counts = (
            self.attempts.pivot(
                on="status",
                index="activity_label",
                values="attempt_id",
                aggregate_function="len",
                sort_columns=True,
            )
            .fill_null(0)
            .sort("activity_label")
        )
        statuses = [name for name in counts.columns if name != "activity_label"]
        counts = counts.with_columns(
            pl.col(statuses).cast(pl.Int64),
            pl.sum_horizontal(statuses).cast(pl.Int64).alias("All"),
        )
        totals = counts.select(
            pl.lit("All").alias("activity_label"), pl.exclude("activity_label").sum()
        )
        return pl.concat([counts, totals])

    @property
    def receiver_issues(self) -> pl.DataFrame:
        """Return empty, unreadable, unsupported, or reset recordings."""
        frame = self.receiver_attempts
        if frame.is_empty():
            return frame
        bad = (
            ~pl.col("has_frames")
            | pl.col("sensing_link_rows").eq(0)
            | pl.col("read_error").ne("")
        )
        for name in (
            "timestamp_resets",
            "sequence_out_of_order",
            "sequence_duplicates",
            "phase_mask_unreadable_rows",
            "phase_mask_unsupported_rows",
        ):
            bad |= pl.col(name).ne(0)
        return frame.filter(bad)

    @property
    def phase_issues(self) -> pl.DataFrame:
        """Return inconsistent phase events; aborted partial sequences are allowed."""
        frame = self.phase_attempts
        if frame.is_empty():
            return frame
        bad = (
            ~pl.col("phase_order_valid")
            | ~pl.col("phase_bounds_valid")
            | ~pl.col("action_confirmation_matches")
            | pl.col("completed_attempt_has_all_phases").eq(False).fill_null(False)
            | pl.col("trial_resolution_matches_status").eq(False).fill_null(False)
            | pl.col("confirmation_occurs_during_action").eq(False).fill_null(False)
        )
        return frame.filter(bad)

    @property
    def phase_duration_summary(self) -> pl.DataFrame:
        """Compare observed durations with configured durations (action is a limit).

        Rows follow the collection order; a phase without intervals has nulls.
        """
        if self.phase_intervals.is_empty():
            return pl.DataFrame()
        summary = self.phase_intervals.group_by("phase").agg(
            pl.col("observed_seconds").count().cast(pl.Int64).alias("intervals"),
            _numpy_reduce("planned_seconds", np.median, "planned_seconds_median"),
            _numpy_reduce("observed_seconds", np.median, "observed_seconds_median"),
            _numpy_reduce(
                "observed_seconds",
                lambda values: np.quantile(values, 0.1),
                "observed_seconds_p10",
            ),
            _numpy_reduce(
                "observed_seconds",
                lambda values: np.quantile(values, 0.9),
                "observed_seconds_p90",
            ),
            _numpy_reduce("duration_delta_seconds", np.median, "median_delta_seconds"),
        )
        return pl.DataFrame({"phase": list(_timeline.PHASES)}).join(
            summary, on="phase", how="left"
        )

    @property
    def phase_packet_summary(self) -> pl.DataFrame:
        """Return CSI counts by receiver and reconstructed phase."""
        if self.phase_packet_counts.is_empty():
            return pl.DataFrame()
        return self.phase_packet_counts.group_by(
            ["receiver_id", "phase"], maintain_order=True
        ).agg(
            (pl.col("sensing_link_csi_rows") > 0)
            .sum()
            .cast(pl.Int64)
            .alias("attempts_with_packets"),
            pl.col("sensing_link_csi_rows").sum(),
        )


def analyze_latest_session(
    sessions_dir: str | Path,
    frames_root: str | Path,
    *,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    workers: int = 1,
) -> SessionIntegrity:
    """Analyze the session with the newest recorded UTC start time.

    Args:
        sessions_dir: Directory containing schema-2 session bundles.
        frames_root: Directory outside raw data that receives (or already holds)
            the converted frame tables, one subdirectory per session.
        cache_dir: Optional directory for derived JSON summaries, outside raw data.
        refresh: Recompute summaries even if unchanged source files are cached.
        workers: Number of processes for uncached receiver recordings.

    Returns:
        Tables for the newest session, regardless of its lifecycle status.

    Raises:
        FileNotFoundError: No session manifests exist under ``sessions_dir``.
        ValueError: The selected session is unsupported or lacks required metadata.
    """
    manifests = list(Path(sessions_dir).glob("*/session.json"))
    if not manifests:
        raise FileNotFoundError(f"No session manifests under {sessions_dir}")

    def start_time(path: Path) -> tuple[datetime, str]:
        value = _read_json(path).get("started_at_utc")
        if value:
            parsed = datetime.fromisoformat(value)
        else:
            parsed = datetime.strptime(path.parent.name, "%Y%m%dT%H%M%S%fZ")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC), path.parent.name

    latest = max(manifests, key=start_time).parent
    session = load_analysis_session(latest, Path(frames_root) / latest.name)
    return analyze_session(
        session, cache_dir=cache_dir, refresh=refresh, workers=workers
    )


def analyze_session(
    session: AnalysisSession,
    *,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    workers: int = 1,
) -> SessionIntegrity:
    """Measure collection integrity without modifying the session bundle.

    Frames are read one recording at a time. Optional caches retain only
    receiver summaries and phase counts, never raw CSI. Cache entries depend on
    the frame table files, analysis code, radio settings, and phase intervals.
    Set ``refresh=True`` to force a full scan.

    Args:
        session: Closed analysis session (see ``load_analysis_session``).
        cache_dir: Optional derived-artifact directory outside raw data; ``None``
            disables caching.
        refresh: Ignore existing cache entries and rebuild them.
        workers: Positive number of processes for uncached scans. Cached results
            are read in the caller without starting worker processes.

    Returns:
        Session, attempt, receiver, and reconstructed-phase integrity tables as
        polars frames; unavailable ratios and durations are null, not NaN.

    Raises:
        ValueError: Radio metadata is invalid or the cache location is in raw data.
        OSError: A cache cannot be written.
        RuntimeError: Session manifests or events cannot be read.
    """
    started = perf_counter()
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1:
        raise ValueError("workers must be a positive integer")
    source = Path(str(session.manifest["source_directory"]))
    manifest = session.manifest["source_manifest"]
    cache = Path(cache_dir).resolve() if cache_dir is not None else None
    if cache is not None and cache.is_relative_to(_cache_keys.raw_root_of(session)):
        raise ValueError("Place integrity caches outside raw data")
    protocol = protocol_from_mapping(
        json.loads(read_session_file(source, "protocol.json"))
    )
    trials = {trial.ordinal: trial for trial in protocol.trials}
    environment = manifest.get("environment", {})
    transmitter = session.transmitter_mac.strip().lower()
    if not transmitter:
        raise ValueError("Session radio inventory must specify a transmitter MAC")
    rate = session.nominal_rate_hz
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError("Session must specify a positive nominal sampling rate")
    events = [
        json.loads(line)
        for line in read_session_file(source, "events.jsonl")
        .decode("utf-8")
        .splitlines()
        if line.strip()
    ]
    records = []
    for row in as_polars(session.attempts).iter_rows(named=True):
        attempt = json.loads(
            read_session_file(source, f"{row['attempt_key']}/attempt.json")
        )
        records.append(
            {
                "key": (int(row["trial_ordinal"]), int(row["attempt"])),
                "attempt_key": row["attempt_key"],
                "attempt_id": row["attempt_id"],
                "trial_ordinal": int(row["trial_ordinal"]),
                "attempt_number": int(row["attempt"]),
                "activity_label": attempt.get("reference_truth_label")
                or row["activity_label"],
                "planned_activity_label": row["original_activity_label"],
                "status": row["status"],
                "receiver_ids": list(row["receiver_ids"]),
                "manifest": attempt,
            }
        )
    expected = set(environment.get("receiver_bindings", {})) or set(
        environment.get("receiver_ids", {}).values()
    )
    actual = {name for record in records for name in record["receiver_ids"]}
    receiver_ids = sorted(expected | actual)
    phases, phase_attempts, intervals = _timeline.reconstruct_phases(
        records, events, trials
    )
    code_hash = _cache_keys.code_hash(
        (phase_module, _receiver, _timeline, session_frames, _frames), __file__
    )
    signature = _cache_keys.frame_signature(session)
    jobs = [(record, receiver_id) for record in records for receiver_id in receiver_ids]
    requests = [
        (
            session,
            record["attempt_key"],
            receiver_id,
            rate,
            intervals[record["key"]],
        )
        for record, receiver_id in jobs
    ]
    entries = [
        _cache_keys.cache_entry(
            [code_hash, signature, transmitter, rate, intervals],
            f"{session.path}/{attempt_key}/{receiver_id}",
            cache,
            ".json",
        )
        for session, attempt_key, receiver_id, rate, intervals in requests
    ]
    results = [
        _load_cached(path, fingerprint) if not refresh else None
        for fingerprint, path in entries
    ]
    pending = [index for index, result in enumerate(results) if result is None]
    hits = len(results) - len(pending)
    if workers > 1 and len(pending) > 1:
        with ProcessPoolExecutor(
            max_workers=min(workers, len(pending)),
            mp_context=multiprocessing.get_context("spawn"),
        ) as executor:
            futures = [
                executor.submit(_receiver.scan_receiver, *requests[index])
                for index in pending
            ]
            for index, future in zip(pending, futures):
                results[index] = future.result()
    else:
        for index in pending:
            results[index] = _receiver.scan_receiver(*requests[index])
    for index in pending:
        fingerprint, path = entries[index]
        # Only store results if the tables did not change while scanning.
        if path is not None and signature == _cache_keys.frame_signature(session):
            _store_cached(path, fingerprint, results[index])
    receiver_rows, packet_rows = [], []
    for (record, receiver_id), result in zip(jobs, results):
        identity = {
            name: record[name]
            for name in (
                "attempt_id",
                "trial_ordinal",
                "attempt_number",
                "activity_label",
                "status",
            )
        }
        identity["receiver_id"] = receiver_id
        receiver_rows.append({**identity, **result["metrics"]})
        packet_rows.extend(
            {**identity, "phase": phase, "sensing_link_csi_rows": count}
            for phase, count in result["phase_counts"].items()
        )
    receiver_attempts = pl.DataFrame(receiver_rows, schema=_RECEIVER_ATTEMPT_SCHEMA)
    started_ordinals = {record["trial_ordinal"] for record in records}
    missing = sorted(set(trials) - started_ordinals)
    overview = pl.DataFrame(
        [
            {
                "session_id": manifest.get("session_id", source.name),
                "started_at_utc": manifest.get("started_at_utc"),
                "session_status": manifest.get("status"),
                "planned_trials": len(trials),
                "attempts_recorded": len(records),
                "nominal_rate_hz": rate,
                "expected_receivers": ", ".join(sorted(expected)),
                "unexpected_receivers": ", ".join(sorted(actual - expected)),
                "transmitter_mac": transmitter,
                "cached_receiver_recordings": hits,
                "scanned_receiver_recordings": len(receiver_rows) - hits,
                "analysis_seconds": perf_counter() - started,
            }
        ],
        schema=_OVERVIEW_SCHEMA,
    )
    attempts = pl.DataFrame(
        [{key: record[key] for key in _ATTEMPT_SCHEMA} for record in records],
        schema=_ATTEMPT_SCHEMA,
    )
    coverage = pl.DataFrame(
        [
            {
                "planned_trials": len(trials),
                "trials_with_attempts": len(started_ordinals),
                "planned_trials_never_started": len(missing),
                "trial_ordinals_never_started": missing,
            }
        ],
        schema=_COVERAGE_SCHEMA,
    )
    return SessionIntegrity(
        source,
        overview,
        attempts,
        coverage,
        _receiver_summary(receiver_attempts),
        receiver_attempts,
        phases,
        phase_attempts,
        pl.DataFrame(packet_rows, schema=_PHASE_PACKET_SCHEMA),
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def _load_cached(path, fingerprint):
    if path is not None and path.is_file():
        try:
            stored = _read_json(path)
            result = stored["result"]
            encoded = json.dumps(result, sort_keys=True, allow_nan=False)
            if (
                stored["fingerprint"] == fingerprint
                and stored["checksum"] == hashlib.sha256(encoded.encode()).hexdigest()
            ):
                return result
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return None


def _store_cached(path, fingerprint, result):
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    payload = {
        "fingerprint": fingerprint,
        "checksum": hashlib.sha256(encoded.encode()).hexdigest(),
        "result": result,
    }
    atomic_bytes(path, json.dumps(payload, allow_nan=False).encode("utf-8"))


def _receiver_summary(frame: pl.DataFrame) -> pl.DataFrame:
    """Pool the per-attempt receiver metrics by receiver.

    Unavailable ratios and medians are null rather than NaN.
    """
    if frame.is_empty():
        return pl.DataFrame(schema=_RECEIVER_SUMMARY_SCHEMA)
    pooled = frame.group_by("receiver_id").agg(
        (~pl.col("has_frames")).sum().cast(pl.Int64).alias("attempts_without_frames"),
        pl.col("raw_csi_rows").sum(),
        pl.col("sensing_link_rows").sum().alias("sensing_link_csi_rows"),
        pl.col("sequence_missing_frames").sum().alias("sequence_gap_missing_frames"),
        pl.col("timestamp_gap_intervals").sum(),
        pl.col("estimated_missing_from_timestamp_gaps")
        .sum()
        .alias("estimated_timestamp_gap_missing_frames"),
        pl.col("timestamp_resets").sum(),
        pl.col("timestamp_interval_count").sum().alias("_interval_count"),
        _numpy_reduce("timestamp_elapsed_seconds", np.sum, "_elapsed"),
        _numpy_reduce(
            "effective_sampling_rate_hz", np.median, "median_attempt_rate_hz"
        ),
        _numpy_reduce("median_interval_ms", np.median),
        _numpy_reduce("p95_interval_ms", np.median, "median_attempt_p95_interval_ms"),
        pl.col("max_interval_ms").max(),
        pl.col("phase_mask_supported_rows").sum(),
        pl.col("phase_mask_unsupported_rows").sum(),
        pl.col("phase_mask_unreadable_rows").sum(),
        pl.col("phase_usable_subcarriers_sum").sum().alias("_usable"),
        pl.col("phase_max_subcarriers_sum").sum().alias("_maximum"),
        pl.col("unassigned_phase_rows").sum(),
        (pl.col("read_error") != "")
        .sum()
        .cast(pl.Int64)
        .alias("recordings_with_read_errors"),
    )
    sensing, missing = (
        pl.col("sensing_link_csi_rows"),
        pl.col("sequence_gap_missing_frames"),
    )
    return pooled.sort("receiver_id").select(
        "receiver_id",
        "attempts_without_frames",
        "raw_csi_rows",
        "sensing_link_csi_rows",
        "sequence_gap_missing_frames",
        pl.when(sensing + missing != 0)
        .then(100 * missing / (sensing + missing))
        .alias("sequence_gap_loss_pct"),
        "timestamp_gap_intervals",
        "estimated_timestamp_gap_missing_frames",
        "timestamp_resets",
        pl.when(pl.col("_elapsed") != 0)
        .then(pl.col("_interval_count") / pl.col("_elapsed"))
        .alias("effective_sampling_rate_hz"),
        "median_attempt_rate_hz",
        "median_interval_ms",
        "median_attempt_p95_interval_ms",
        "max_interval_ms",
        "phase_mask_supported_rows",
        "phase_mask_unsupported_rows",
        "phase_mask_unreadable_rows",
        pl.when(pl.col("phase_mask_supported_rows") != 0)
        .then(pl.col("_usable") / pl.col("phase_mask_supported_rows"))
        .alias("mean_usable_subcarriers_per_packet"),
        pl.when(pl.col("_maximum") != 0)
        .then(pl.col("_usable") / pl.col("_maximum"))
        .alias("usable_phase_subcarrier_fraction"),
        "unassigned_phase_rows",
        "recordings_with_read_errors",
    )
