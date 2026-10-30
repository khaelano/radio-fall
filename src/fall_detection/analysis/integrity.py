"""Read-only dataset integrity analysis with optional derived-result caching."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from ..collection.protocol import load_protocol
from ..radio.preprocessing import phase as phase_module
from . import _receiver, _timeline


@dataclass(frozen=True)
class SessionIntegrity:
    """Integrity tables for one session; all CSI metrics describe the sensing link.

    ``receivers`` contains pooled receiver totals. ``receiver_attempts`` and
    ``phase_attempts`` retain attempt-level detail for investigation. Sequence
    loss covers only gaps between received packets within each attempt. Phase
    packet counts use host receipt times and include transport latency.
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
        """Return missing, empty, malformed, misaligned, or reset recordings."""
        frame = self.receiver_attempts
        if frame.empty:
            return frame
        bad = (
            ~frame["receiver_dir_exists"]
            | ~frame["csi_file_exists"]
            | ~frame["timing_file_exists"]
            | frame["sensing_link_rows"].eq(0)
            | frame["row_count_difference"].ne(0)
            | frame["read_error"].ne("")
        )
        for name in (
            "csi_timing_sequence_mismatches",
            "csi_timing_timestamp_mismatches",
            "timestamp_resets",
            "sequence_out_of_order",
            "sequence_duplicates",
            "phase_mask_unreadable_rows",
            "phase_mask_unsupported_rows",
            "malformed_sensing_metadata_rows",
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
    *,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    workers: int = 1,
) -> SessionIntegrity:
    """Analyze the session with the newest recorded UTC start time.

    Args:
        sessions_dir: Directory containing schema-2 session bundles.
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
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            parsed = datetime.strptime(path.parent.name, "%Y%m%dT%H%M%S%fZ")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), path.parent.name

    latest = max(manifests, key=start_time).parent
    return analyze_session(
        latest, cache_dir=cache_dir, refresh=refresh, workers=workers
    )


def analyze_session(
    session_dir: str | Path,
    *,
    cache_dir: str | Path | None = None,
    refresh: bool = False,
    workers: int = 1,
) -> SessionIntegrity:
    """Measure collection integrity without modifying the session bundle.

    CSI is processed in bounded batches. Optional caches retain only receiver
    summaries and phase counts, never raw CSI. Cache entries depend on source
    paths, size/mtime/ctime, analysis code, radio settings, and phase intervals.
    Active sessions bypass caching. Set ``refresh=True`` to force a full scan.

    Args:
        session_dir: One schema-2 session directory.
        cache_dir: Optional derived-artifact directory outside raw data; ``None``
            disables caching.
        refresh: Ignore existing cache entries and rebuild them.
        workers: Positive number of processes for uncached scans. Cached results
            are read in the caller without starting worker processes.

    Returns:
        Session, attempt, receiver, and reconstructed-phase integrity tables.

    Raises:
        ValueError: Schema/radio metadata is invalid or cache location is in raw data.
        OSError: Required manifests cannot be read or a cache cannot be written.
    """
    started = perf_counter()
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1:
        raise ValueError("workers must be a positive integer")
    root = Path(session_dir).resolve()
    manifest = _read_json(root / "session.json")
    if manifest.get("artifact_schema_version") != 2:
        raise ValueError(f"Only schema-2 sessions are supported: {root}")
    cache = Path(cache_dir).resolve() if cache_dir is not None else None
    raw_root = (
        root.parent.parent
        if root.parent.name == "sessions" and root.parent.parent.name == "raw"
        else root
    )
    if cache is not None and cache.is_relative_to(raw_root):
        raise ValueError("Place integrity caches outside raw session data")
    protocol = load_protocol(root / "protocol.json")
    trials = {trial.ordinal: trial for trial in protocol.trials}
    environment = manifest.get("environment", {})
    transmitter = (
        environment.get("radio_inventory", {})
        .get("transmitter", {})
        .get("mac", "")
        .strip()
        .lower()
    )
    if not transmitter:
        raise ValueError("Session radio inventory must specify a transmitter MAC")
    rate = environment.get("nominal_rate_hz") or environment.get(
        "radio_profile", {}
    ).get("nominal_rate_hz")
    if rate is None or not np.isfinite(float(rate)) or float(rate) <= 0:
        raise ValueError("Session must specify a positive nominal sampling rate")
    rate = float(rate)
    events = [
        json.loads(line)
        for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    review = (
        _read_json(root / "session_review.json")
        if (root / "session_review.json").exists()
        else {}
    )
    if review and (
        review.get("session_id") != manifest.get("session_id")
        or review.get("protocol_hash") != manifest.get("protocol_hash")
    ):
        raise ValueError("Review sidecar does not match the session identity/protocol")
    records = []
    for path in sorted(root.glob("trials/*/attempt_*/attempt.json")):
        attempt = _read_json(path)
        ordinal = int(attempt["trial_ordinal"])
        number = int(path.parent.name.removeprefix("attempt_"))
        override = review.get("attempts", {}).get(
            path.parent.relative_to(root).as_posix(), {}
        )
        records.append(
            {
                "key": (ordinal, number),
                "attempt_id": f"{ordinal:03d}/{number:02d}",
                "trial_ordinal": ordinal,
                "attempt_number": number,
                "activity_label": attempt.get("reference_truth_label")
                or override.get("activity_label")
                or attempt.get("activity_label"),
                "planned_activity_label": attempt.get("activity_label"),
                "status": attempt.get("status", "unknown"),
                "directory": path.parent,
                "manifest": attempt,
            }
        )
    expected = set(environment.get("receiver_bindings", {})) or set(
        environment.get("receiver_ids", {}).values()
    )
    actual = {
        path.name
        for record in records
        for path in (record["directory"] / "receivers").glob("*")
        if path.is_dir()
    }
    receiver_ids = sorted(expected | actual)
    phases, phase_attempts, intervals = _timeline.reconstruct_phases(
        records, events, trials
    )
    code_hash = hashlib.sha256(
        b"".join(
            Path(module.__file__).read_bytes()
            for module in (phase_module, _receiver, _timeline)
        )
        + Path(__file__).read_bytes()
    ).hexdigest()
    active = manifest.get("status") == "open" or any(
        record["status"] == "recording" for record in records
    )
    jobs = [
        (record, receiver_id, record["directory"] / "receivers" / receiver_id)
        for record in records
        for receiver_id in receiver_ids
    ]
    requests = [
        (directory, transmitter, rate, intervals[record["key"]])
        for record, _, directory in jobs
    ]
    entries = [
        _cache_entry(*request, cache if not active else None, code_hash)
        for request in requests
    ]
    results = [
        _load_cached(path, fingerprint) if not refresh else None
        for _, fingerprint, path in entries
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
        source, fingerprint, path = entries[index]
        if path is not None and source == _source_signature(jobs[index][2]):
            _store_cached(path, fingerprint, results[index])
    receiver_rows, packet_rows = [], []
    for (record, receiver_id, _), result in zip(jobs, results):
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
                "session_id": manifest.get("session_id", root.name),
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
                key: value
                for key, value in record.items()
                if key not in ("key", "directory", "manifest")
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
        root,
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
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _source_signature(directory: Path) -> list:
    values = [directory.is_dir()]
    for name in ("csi.csv", "radio_timing.csv"):
        path = directory / name
        if path.is_file():
            stat = path.stat()
            values.append([name, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns])
        else:
            values.append([name, None])
    return values


def _cache_entry(directory, transmitter, rate, intervals, cache, code_hash):
    source = _source_signature(directory)
    fingerprint = hashlib.sha256(
        json.dumps(
            [code_hash, source, transmitter, rate, intervals], sort_keys=True
        ).encode()
    ).hexdigest()
    name = hashlib.sha256(str(directory).encode()).hexdigest()
    path = cache / f"{name}.json" if cache is not None else None
    return source, fingerprint, path


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
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    payload = {
        "fingerprint": fingerprint,
        "checksum": hashlib.sha256(encoded.encode()).hexdigest(),
        "result": result,
    }
    temporary = None
    try:
        with NamedTemporaryFile(
            "w", dir=path.parent, suffix=".tmp", encoding="utf-8", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
                "attempt_receiver_dirs_missing": int(
                    (~group["receiver_dir_exists"]).sum()
                ),
                "csi_files_missing": int((~group["csi_file_exists"]).sum()),
                "timing_files_missing": int((~group["timing_file_exists"]).sum()),
                "empty_csi_attempts": int(
                    (group["csi_file_exists"] & group["raw_csi_rows"].eq(0)).sum()
                ),
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
                "csi_timing_sequence_mismatches": int(
                    group["csi_timing_sequence_mismatches"].sum()
                ),
                "csi_timing_timestamp_mismatches": int(
                    group["csi_timing_timestamp_mismatches"].sum()
                ),
                "attempts_with_csi_timing_row_count_difference": int(
                    group["row_count_difference"].ne(0).sum()
                ),
                "unassigned_phase_rows": int(group["unassigned_phase_rows"].sum()),
                "recordings_with_read_errors": int(group["read_error"].ne("").sum()),
            }
        )
    return pd.DataFrame(rows)
