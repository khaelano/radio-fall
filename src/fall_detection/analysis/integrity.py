"""Read-only dataset integrity analysis with optional derived-result caching."""

import hashlib
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from .._radio_native import storage_read as read_session_file
from ..collection.protocol import protocol_from_mapping
from ..radio.preprocessing import phase as phase_module
from . import _cache_keys, _receiver, _timeline, session_frames
from ._io import atomic_bytes
from .session_frames import AnalysisSession, load_analysis_session


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
    overview: pd.DataFrame
    attempts: pd.DataFrame
    trial_coverage: pd.DataFrame
    receivers: pd.DataFrame
    receiver_attempts: pd.DataFrame
    phase_intervals: pd.DataFrame
    phase_attempts: pd.DataFrame
    phase_packet_counts: pd.DataFrame

    @property
    def attempt_counts(self) -> pd.DataFrame:
        """Return attempt counts by effective activity label and capture status."""
        if self.attempts.empty:
            return pd.DataFrame()
        return pd.crosstab(
            self.attempts["activity_label"], self.attempts["status"], margins=True
        )

    @property
    def receiver_issues(self) -> pd.DataFrame:
        """Return empty, unreadable, unsupported, or reset recordings."""
        frame = self.receiver_attempts
        if frame.empty:
            return frame
        bad = (
            ~frame["has_frames"]
            | frame["sensing_link_rows"].eq(0)
            | frame["read_error"].ne("")
        )
        for name in (
            "timestamp_resets",
            "sequence_out_of_order",
            "sequence_duplicates",
            "phase_mask_unreadable_rows",
            "phase_mask_unsupported_rows",
        ):
            bad |= frame[name].ne(0)
        return frame.loc[bad]

    @property
    def phase_issues(self) -> pd.DataFrame:
        """Return inconsistent phase events; aborted partial sequences are allowed."""
        frame = self.phase_attempts
        if frame.empty:
            return frame
        bad = (
            ~frame["phase_order_valid"]
            | ~frame["phase_bounds_valid"]
            | ~frame["action_confirmation_matches"]
            | frame["completed_attempt_has_all_phases"].eq(False)
            | frame["trial_resolution_matches_status"].eq(False)
            | frame["confirmation_occurs_during_action"].eq(False)
        )
        return frame.loc[bad]

    @property
    def phase_duration_summary(self) -> pd.DataFrame:
        """Compare observed durations with configured durations (action is a limit)."""
        if self.phase_intervals.empty:
            return pd.DataFrame()
        return (
            self.phase_intervals.groupby("phase")
            .agg(
                intervals=("observed_seconds", "count"),
                planned_seconds_median=("planned_seconds", "median"),
                observed_seconds_median=("observed_seconds", "median"),
                observed_seconds_p10=(
                    "observed_seconds",
                    lambda values: values.quantile(0.1),
                ),
                observed_seconds_p90=(
                    "observed_seconds",
                    lambda values: values.quantile(0.9),
                ),
                median_delta_seconds=("duration_delta_seconds", "median"),
            )
            .reindex(_timeline.PHASES)
        )

    @property
    def phase_packet_summary(self) -> pd.DataFrame:
        """Return CSI counts by receiver and reconstructed phase."""
        if self.phase_packet_counts.empty:
            return pd.DataFrame()
        return (
            self.phase_packet_counts.groupby(["receiver_id", "phase"], sort=False)
            .agg(
                attempts_with_packets=(
                    "sensing_link_csi_rows",
                    lambda values: int((values > 0).sum()),
                ),
                sensing_link_csi_rows=("sensing_link_csi_rows", "sum"),
            )
            .reset_index()
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
        Session, attempt, receiver, and reconstructed-phase integrity tables.

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
    for row in session.attempts.itertuples(index=False):
        attempt = json.loads(
            read_session_file(source, f"{row.attempt_key}/attempt.json")
        )
        records.append(
            {
                "key": (int(row.trial_ordinal), int(row.attempt)),
                "attempt_key": row.attempt_key,
                "attempt_id": row.attempt_id,
                "trial_ordinal": int(row.trial_ordinal),
                "attempt_number": int(row.attempt),
                "activity_label": attempt.get("reference_truth_label")
                or row.activity_label,
                "planned_activity_label": row.original_activity_label,
                "status": row.status,
                "receiver_ids": list(row.receiver_ids),
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
        (phase_module, _receiver, _timeline, session_frames), __file__
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
    receiver_attempts = pd.DataFrame(receiver_rows)
    started_ordinals = {record["trial_ordinal"] for record in records}
    missing = sorted(set(trials) - started_ordinals)
    overview = pd.DataFrame(
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
        ]
    )
    attempts = pd.DataFrame(
        [
            {
                key: record[key]
                for key in (
                    "attempt_id",
                    "trial_ordinal",
                    "attempt_number",
                    "activity_label",
                    "planned_activity_label",
                    "status",
                )
            }
            for record in records
        ],
        columns=[
            "attempt_id",
            "trial_ordinal",
            "attempt_number",
            "activity_label",
            "planned_activity_label",
            "status",
        ],
    )
    coverage = pd.DataFrame(
        [
            {
                "planned_trials": len(trials),
                "trials_with_attempts": len(started_ordinals),
                "planned_trials_never_started": len(missing),
                "trial_ordinals_never_started": missing,
            }
        ]
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
        pd.DataFrame(packet_rows),
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


def _receiver_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if frame.empty:
        return pd.DataFrame()
    for receiver_id, group in frame.groupby("receiver_id", sort=True):
        sensing = int(group["sensing_link_rows"].sum())
        missing = int(group["sequence_missing_frames"].sum())
        supported = int(group["phase_mask_supported_rows"].sum())
        usable = int(group["phase_usable_subcarriers_sum"].sum())
        maximum = int(group["phase_max_subcarriers_sum"].sum())
        elapsed = float(group["timestamp_elapsed_seconds"].sum())
        rows.append(
            {
                "receiver_id": receiver_id,
                "attempts_without_frames": int((~group["has_frames"]).sum()),
                "raw_csi_rows": int(group["raw_csi_rows"].sum()),
                "sensing_link_csi_rows": sensing,
                "sequence_gap_missing_frames": missing,
                "sequence_gap_loss_pct": 100 * missing / (sensing + missing)
                if sensing + missing
                else np.nan,
                "timestamp_gap_intervals": int(group["timestamp_gap_intervals"].sum()),
                "estimated_timestamp_gap_missing_frames": int(
                    group["estimated_missing_from_timestamp_gaps"].sum()
                ),
                "timestamp_resets": int(group["timestamp_resets"].sum()),
                "effective_sampling_rate_hz": group["timestamp_interval_count"].sum()
                / elapsed
                if elapsed
                else np.nan,
                "median_attempt_rate_hz": group["effective_sampling_rate_hz"].median(),
                "median_interval_ms": group["median_interval_ms"].median(),
                "median_attempt_p95_interval_ms": group["p95_interval_ms"].median(),
                "max_interval_ms": group["max_interval_ms"].max(),
                "phase_mask_supported_rows": supported,
                "phase_mask_unsupported_rows": int(
                    group["phase_mask_unsupported_rows"].sum()
                ),
                "phase_mask_unreadable_rows": int(
                    group["phase_mask_unreadable_rows"].sum()
                ),
                "mean_usable_subcarriers_per_packet": usable / supported
                if supported
                else np.nan,
                "usable_phase_subcarrier_fraction": usable / maximum
                if maximum
                else np.nan,
                "unassigned_phase_rows": int(group["unassigned_phase_rows"].sum()),
                "recordings_with_read_errors": int(group["read_error"].ne("").sum()),
            }
        )
    return pd.DataFrame(rows)
