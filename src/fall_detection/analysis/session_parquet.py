"""Versioned, queryable Parquet exports of immutable collection sessions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..session_inspector.models import SessionBundle, load_session
from ..session_inspector.review import ReviewStore
from . import phase_signals

SCHEMA_VERSION = 1
PHASE_NAMES = {"countdown": "preparation", "action": "action", "recovery": "resting"}
_STRINGS = (
    "session_id", "participant_id", "attempt_key", "attempt_id", "scenario_id",
    "activity_label", "original_activity_label", "status", "inclusion", "quality",
    "start_direction", "end_direction", "receiver_id", "phase", "collection_phase",
    "annotation_source", "type", "mac", "receiver_mac", "time_source", "run_id",
    "transmitter_boot_id", "receiver_boot_id",
)
_INTEGERS = (
    "trial_ordinal", "attempt", "repetition", "review_revision", "source_row", "id",
    "sequence", "rssi", "rate", "sig_mode", "mcs", "bandwidth", "smoothing",
    "not_sounding", "aggregation", "stbc", "fec_coding", "sgi", "noise_floor",
    "ampdu_cnt", "channel", "secondary_channel", "local_timestamp", "ant", "sig_len",
    "rx_state", "len", "first_word", "transport_sequence", "tx_enqueue_timestamp_us",
    "rx_radio_timestamp_us", "rx_callback_timestamp_us", "host_receive_monotonic_ns",
    "capture_time_ns", "attempt_started_monotonic_ns", "attempt_ended_monotonic_ns",
)
PACKET_SCHEMA = pa.schema(
    [(name, pa.string()) for name in _STRINGS]
    + [(name, pa.int64()) for name in _INTEGERS]
    + [(name, pa.float64()) for name in (
        "time_seconds", "clock_uncertainty_us", "nominal_rate_hz"
    )]
    + [("is_sensing", pa.bool_()), ("driver_valid", pa.bool_())]
    + [("csi_i", pa.list_(pa.int16())), ("csi_q", pa.list_(pa.int16()))]
)
_ATTEMPT_COLUMNS = [
    "session_id", "participant_id", "attempt_key", "attempt_id", "trial_ordinal",
    "attempt", "repetition", "scenario_id", "activity_label", "original_activity_label",
    "status", "inclusion", "quality", "review_revision", "start_direction",
    "end_direction", "started_monotonic_ns", "ended_monotonic_ns", "receiver_ids",
]
_PHASE_COLUMNS = [
    "session_id", "attempt_key", "trial_ordinal", "attempt", "scenario_id", "phase",
    "collection_phase", "start_ns", "end_ns", "annotation_source", "review_revision",
]


@dataclass(frozen=True)
class ParquetSession:
    """Small session tables plus selective access to the enriched packet table."""

    path: Path
    manifest: dict
    attempts: pd.DataFrame
    phases: pd.DataFrame

    def read_packets(
        self, *, filters: list | None = None, columns: list[str] | None = None,
        arrow_backed: bool = False,
    ) -> pd.DataFrame:
        """Read packet rows with Parquet filters applied before materialization.

        Args:
            filters: Pandas/PyArrow filter tuples, for example
                ``[("phase", "==", "action"), ("receiver_id", "==", "rx-1")]``.
            columns: Optional projection; ``None`` includes I/Q arrays.
            arrow_backed: Retain Arrow arrays to reduce full-session memory use.

        Returns:
            One enriched row per recorded CSI packet, without aggregation.
        """
        options = {"dtype_backend": "pyarrow"} if arrow_backed else {}
        return pd.read_parquet(
            self.path / "packets.parquet", engine="pyarrow", filters=filters,
            columns=columns, **options,
        )


def _source_fingerprint(session: SessionBundle) -> str:
    paths = [session.path / name for name in (
        "session.json", "protocol.json", "events.jsonl", "session_review.json"
    )]
    for attempt in session.attempts:
        paths.append(attempt.path / "attempt.json")
        for files in attempt.receiver_files:
            directory = attempt.path / "receivers" / files.receiver_id
            paths.extend(directory / name for name in (
                "csi.csv", "radio_timing.csv", "usb_clock_sync.csv",
                "gateway_timing.jsonl", "ble_timing.jsonl",
            ))
    entries = []
    for path in paths:
        stat = path.stat() if path.exists() else None
        entries.append((
            str(path.relative_to(session.path)),
            stat.st_size if stat else None, stat.st_mtime_ns if stat else None,
        ))
    digest = hashlib.sha256(json.dumps(entries).encode())
    digest.update(str(session.path).encode())
    for path in (Path(__file__), Path(phase_signals.__file__)):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _attempt_table(session: SessionBundle) -> pd.DataFrame:
    review = ReviewStore(session).load().document
    trials = {trial.ordinal: trial for trial in session.trials}
    rows = []
    for attempt in session.attempts:
        decision = review.attempts.get(attempt.key)
        trial = trials.get(attempt.trial_ordinal)
        attributes = trial.attributes if trial else {}
        rows.append({
            "session_id": session.session_id,
            "participant_id": review.metadata.get(
                "participant_id", session.manifest.get("participant_id")
            ),
            "attempt_key": attempt.key,
            "attempt_id": f"{attempt.trial_ordinal:03d}/{attempt.attempt_number:02d}",
            "trial_ordinal": attempt.trial_ordinal, "attempt": attempt.attempt_number,
            "repetition": attempt.repetition, "scenario_id": attempt.scenario_id,
            "activity_label": (
                decision.activity_label if decision and decision.activity_label
                else attempt.activity_label
            ),
            "original_activity_label": attempt.activity_label, "status": attempt.status,
            "inclusion": decision.inclusion if decision else "unreviewed",
            "quality": decision.quality if decision else "unreviewed",
            "review_revision": review.revision,
            "start_direction": attributes.get("start_direction"),
            "end_direction": attributes.get("end_direction"),
            "started_monotonic_ns": attempt.metadata.get("started_monotonic_ns"),
            "ended_monotonic_ns": attempt.metadata.get("ended_monotonic_ns"),
            "receiver_ids": list(attempt.receiver_ids),
        })
    return pd.DataFrame(rows, columns=_ATTEMPT_COLUMNS)


def _phase_table(session: SessionBundle, attempts: pd.DataFrame) -> pd.DataFrame:
    transitions = {}
    events_path = session.path / "events.jsonl"
    if events_path.exists():
        with events_path.open(encoding="utf-8") as stream:
            for line in stream:
                event = json.loads(line)
                if event.get("kind") == "phase_changed":
                    key = (int(event["trial_ordinal"]), int(event["attempt"]))
                    transitions.setdefault(key, []).append(event)
    rows = []
    for attempt in attempts.to_dict("records"):
        events = sorted(
            transitions.get((attempt["trial_ordinal"], attempt["attempt"]), []),
            key=lambda event: event["monotonic_ns"],
        )
        states = [event["state"] for event in events]
        ranks = [list(PHASE_NAMES).index(state) if state in PHASE_NAMES else -1
                 for state in states]
        if ranks and (ranks[0] != 0 or ranks != sorted(set(ranks))):
            raise ValueError(f"Invalid collection phase sequence: {attempt['attempt_key']}")
        for index, event in enumerate(events):
            start = int(event["monotonic_ns"])
            stop = (int(events[index + 1]["monotonic_ns"])
                    if index + 1 < len(events) else attempt["ended_monotonic_ns"])
            if pd.isna(stop) or pd.isna(attempt["started_monotonic_ns"]):
                raise ValueError(f"Unbounded phase: {attempt['attempt_key']}")
            if (start < attempt["started_monotonic_ns"] or stop < start
                    or stop > attempt["ended_monotonic_ns"]):
                raise ValueError(f"Invalid phase bounds: {attempt['attempt_key']}")
            rows.append({
                **{name: attempt[name] for name in (
                    "session_id", "attempt_key", "trial_ordinal", "attempt",
                    "scenario_id", "review_revision"
                )},
                "phase": PHASE_NAMES[event["state"]],
                "collection_phase": event["state"], "start_ns": start,
                "end_ns": int(stop), "annotation_source": "collection_cue",
            })
    return pd.DataFrame(rows, columns=_PHASE_COLUMNS)


def _packet_table(frame: pd.DataFrame, attempt: dict, phases: pd.DataFrame) -> pa.Table:
    frame = frame.copy()
    for name in _ATTEMPT_COLUMNS:
        if name not in {"receiver_ids", "started_monotonic_ns", "ended_monotonic_ns"}:
            frame[name] = attempt[name]
    frame["phase"], frame["collection_phase"] = "unassigned", "unassigned"
    frame["annotation_source"] = "unassigned"
    for phase in phases.itertuples(index=False):
        selected = frame["capture_time_ns"].ge(phase.start_ns) & frame[
            "capture_time_ns"
        ].lt(phase.end_ns)
        frame.loc[selected, ["phase", "collection_phase", "annotation_source"]] = [
            phase.phase, phase.collection_phase, phase.annotation_source
        ]
    payloads = []
    for row in frame.itertuples(index=False):
        payload = np.asarray(json.loads(row.data))
        if (payload.ndim != 1 or len(payload) != row.len or len(payload) % 2
                or not np.issubdtype(payload.dtype, np.integer)
                or (len(payload) and (payload.min() < -32768 or payload.max() > 32767))):
            raise ValueError(f"Invalid CSI payload length or values in packet {row.id}")
        payloads.append(payload.astype(np.int16))
    frame["csi_i"] = [payload[1::2] for payload in payloads]
    frame["csi_q"] = [payload[0::2] for payload in payloads]
    frame["driver_valid"] = frame["rx_state"].eq(0)
    # Explicit types keep null-only recordings compatible with later row groups.
    return pa.Table.from_pydict({
        field.name: pa.array(
            frame[field.name] if field.name in frame else [None] * len(frame),
            type=field.type, from_pandas=True,
        ) for field in PACKET_SCHEMA
    }, schema=PACKET_SCHEMA)


def load_parquet_session(
    session_dir: str | Path, export_dir: str | Path, *, rebuild: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ParquetSession:
    """Build or reuse a derived session export, then load its small tables.

    Args:
        session_dir: Closed, immutable schema-2 raw session.
        export_dir: Derived directory outside the raw data tree.
        rebuild: Rebuild even when source files and exporter are unchanged.
        progress: Optional callback receiving recording conversion messages.

    Returns:
        Session tables and a filtered reader for ``packets.parquet``.

    Raises:
        ValueError: Session is active, export would write into raw data, or
            timing/payload/phase validation fails. Failed builds have no valid
            export manifest and are rebuilt on the next call.
    """
    if Path(session_dir).is_file():
        return _load_archive_session(Path(session_dir), Path(export_dir), rebuild=rebuild, progress=progress)
    session = load_session(session_dir)
    destination = Path(export_dir).resolve()
    raw_root = (session.path.parent.parent
                if session.path.parent.name == "sessions" else session.path)
    if destination.is_relative_to(raw_root):
        raise ValueError("Place Parquet exports outside raw session data")
    if session.active:
        raise ValueError("Parquet export requires a closed session")
    fingerprint = _source_fingerprint(session)
    manifest_path = destination / "session.json"
    cached = None
    if manifest_path.exists():
        try:
            cached = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    current = (
        cached is not None and cached.get("source_fingerprint") == fingerprint
        and cached.get("schema_version") == SCHEMA_VERSION
        and all((destination / name).is_file() for name in (
            "attempts.parquet", "phases.parquet", "packets.parquet"
        ))
    )
    if rebuild or not current:
        destination.mkdir(parents=True, exist_ok=True)
        manifest_path.unlink(missing_ok=True)
        attempts = _attempt_table(session)
        phases = _phase_table(session, attempts)
        metadata = attempts.set_index("attempt_key").to_dict("index")
        count = 0
        recordings = sum(len(attempt.receiver_files) for attempt in session.attempts)
        with TemporaryDirectory(prefix=".parquet-", dir=destination) as temporary:
            staging = Path(temporary)
            attempts.to_parquet(staging / "attempts.parquet", index=False)
            phases.to_parquet(staging / "phases.parquet", index=False)
            with pq.ParquetWriter(
                staging / "packets.parquet", PACKET_SCHEMA, compression="zstd"
            ) as writer:
                number = 0
                for attempt in session.attempts:
                    info = {"attempt_key": attempt.key, **metadata[attempt.key]}
                    intervals = phases.loc[phases["attempt_key"].eq(attempt.key)]
                    for files in attempt.receiver_files:
                        number += 1
                        if progress and (number == 1 or number % 40 == 0):
                            progress(f"Parquet: recording {number}/{recordings}")
                        frame = phase_signals.load_capture_packets(
                            session.path, info["attempt_id"], files.receiver_id
                        )
                        if frame.empty:
                            continue
                        table = _packet_table(frame, info, intervals)
                        writer.write_table(table)
                        count += len(table)
            if _source_fingerprint(load_session(session.path)) != fingerprint:
                raise ValueError("Source session changed during Parquet export")
            cached = {
                "schema_version": SCHEMA_VERSION, "session_id": session.session_id,
                "source_directory": str(session.path), "source_fingerprint": fingerprint,
                "protocol_hash": session.protocol_hash, "source_manifest": session.manifest,
                "packet_count": count, "recording_count": recordings,
                "phase_names": PHASE_NAMES, "phase_interval": "[start_ns, end_ns)",
                "annotation_source": "collection_cue", "compression": "zstd",
                "csi_layout": "raw slots; I=real, Q=imaginary; no aggregation",
            }
            for name in ("attempts.parquet", "phases.parquet", "packets.parquet"):
                (staging / name).replace(destination / name)
            (staging / "session.json").write_text(
                json.dumps(cached, indent=2) + "\n", encoding="utf-8"
            )
            (staging / "session.json").replace(manifest_path)
    return ParquetSession(
        destination, cached, pd.read_parquet(destination / "attempts.parquet"),
        pd.read_parquet(destination / "phases.parquet"),
    )


def _load_archive_session(source: Path, destination: Path, *, rebuild: bool, progress) -> ParquetSession:
    """Build from verified analysis members; keep temporary CSVs out of caches."""
    from ..storage import Recording

    source, destination = source.resolve(), destination.resolve()
    raw_root = source.parent.parent if source.parent.name == "sessions" else source
    if destination.is_relative_to(raw_root):
        raise ValueError("Place Parquet exports outside raw session data")
    with Recording(source) as recording:
        digest = hashlib.sha256(json.dumps(recording.manifest, sort_keys=True).encode())
        for module in (Path(__file__), Path(phase_signals.__file__)):
            digest.update(module.read_bytes())
        fingerprint = digest.hexdigest()
        manifest_path = destination / "session.json"
        try:
            cached = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            cached = {}
        if rebuild or not (
            cached.get("archive_fingerprint") == fingerprint
            and cached.get("schema_version") == SCHEMA_VERSION
            and all((destination / name).is_file() for name in (
                "attempts.parquet", "phases.parquet", "packets.parquet"))
        ):
            if progress:
                progress("Preparing temporary analysis members from raw archive")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".archive-analysis-", dir=destination.parent) as tmp:
                members = [name for name in recording.files if (
                    name in {"session.json", "protocol.json", "events.jsonl", "session_review.json"}
                    or name.startswith("trials/") and (
                        name.endswith("/attempt.json") or "/receivers/" in name))]
                root = recording.extract(Path(tmp) / "session", members=members)
                built = load_parquet_session(root, destination, rebuild=True, progress=progress)
                cached = dict(built.manifest, archive_fingerprint=fingerprint,
                              source_directory=str(source), source_fingerprint=fingerprint)
                temporary = destination / "session.json.tmp"
                temporary.write_text(json.dumps(cached, indent=2) + "\n")
                temporary.replace(manifest_path)
        return ParquetSession(destination, cached,
                              pd.read_parquet(destination / "attempts.parquet"),
                              pd.read_parquet(destination / "phases.parquet"))
