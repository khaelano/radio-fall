"""Per-attempt capture sinks and session artifact persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any, TextIO

from ..contracts import ARTIFACT_SCHEMA_VERSION
from ..radio.acquisition.clock_sync import ClockSyncEstimate, ClockSyncSample
from ..radio.acquisition.protocol import CSI_HEADER, CsiRecord, format_csi_record
from .protocol import CollectionProtocol, Trial


TIMING_HEADER = (
    "sequence,receiver_mac,transport_sequence,tx_enqueue_timestamp_us,"
    "rx_radio_timestamp_us,rx_callback_timestamp_us,host_receive_monotonic_ns"
)
CLOCK_SYNC_HEADER = (
    "host_receive_monotonic_ns,receiver_mac,sync_id,sensing_sequence,receiver_boot_id,"
    "tx_t1_us,rx_t2_us,rx_t3_us,tx_t4_us,rx_radio_t2_us,tx_radio_t4_us,"
    "round_trip_us,receiver_minus_transmitter_us,drift_ppm,uncertainty_us"
)


def _slug(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return result or "unnamed"


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _receiver_bindings(environment: dict[str, Any] | None) -> dict[str, str]:
    """Return the MAC-to-receiver binding required by artifact schema 2."""

    raw = (environment or {}).get("receiver_ids")
    if not isinstance(raw, dict) or not raw:
        raise ValueError(
            "session environment must provide a non-empty receiver_ids map"
        )
    bindings = {str(mac).lower(): str(receiver_id) for mac, receiver_id in raw.items()}
    if not all(mac and receiver_id for mac, receiver_id in bindings.items()):
        raise ValueError("receiver_ids must map MAC strings to receiver id strings")
    return bindings


class TrialCapture:
    """Thread-safe, receiver-split writers for one trial attempt."""

    def __init__(
        self,
        path: Path,
        initial_metadata: dict[str, Any],
        *,
        receiver_ids: dict[str, str],
    ) -> None:
        if not receiver_ids:
            raise ValueError("TrialCapture requires at least one receiver binding")
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._metadata = dict(initial_metadata)
        self._metadata["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
        self._metadata["status"] = "recording"
        _write_json(self.path / "attempt.json", self._metadata)
        self.receiver_ids = {
            mac.lower(): receiver_id for mac, receiver_id in receiver_ids.items()
        }
        self._receiver_streams: dict[str, tuple[TextIO, TextIO]] = {}
        for receiver_id in sorted(set(self.receiver_ids.values())):
            receiver_path = self.path / "receivers" / _slug(receiver_id)
            receiver_path.mkdir(parents=True, exist_ok=True)
            csi_file = (receiver_path / "csi.csv").open(
                "w", encoding="utf-8", newline=""
            )
            timing_file = (receiver_path / "radio_timing.csv").open(
                "w", encoding="utf-8", newline=""
            )
            csi_file.write(CSI_HEADER + "\n")
            timing_file.write(TIMING_HEADER + "\n")
            (receiver_path / "usb_clock_sync.csv").write_text(
                CLOCK_SYNC_HEADER + "\n", encoding="utf-8"
            )
            self._receiver_streams[receiver_id] = (csi_file, timing_file)

    def write_radio(self, record: CsiRecord, host_receive_monotonic_ns: int) -> None:
        """Append one decoded radio record and its timing sidecar row."""

        with self._lock:
            receiver_id = self.receiver_ids.get(record.receiver_mac.lower())
            if receiver_id is None:
                return
            tx_timestamp = "" if record.tx_timestamp_us is None else record.tx_timestamp_us
            rx_callback = (
                ""
                if record.rx_callback_timestamp_us is None
                else record.rx_callback_timestamp_us
            )
            csi_file, timing_file = self._receiver_streams[receiver_id]
            csi_file.write(format_csi_record(record).rstrip("\r\n") + "\n")
            timing_file.write(
                f"{record.sequence},{record.receiver_mac},{record.transport_sequence},"
                f"{tx_timestamp},{record.timestamp_us},{rx_callback},"
                f"{host_receive_monotonic_ns}\n"
            )

    def write_clock_sync(
        self,
        sample: ClockSyncSample,
        estimate: ClockSyncEstimate,
        host_receive_monotonic_ns: int,
    ) -> None:
        """Append one clock-sync exchange and its current fit."""

        with self._lock:
            receiver_id = self.receiver_ids.get(sample.receiver_mac.lower())
            if receiver_id is None:
                return
            receiver_path = self.path / "receivers" / _slug(receiver_id)
            clock_path = receiver_path / "usb_clock_sync.csv"
            with clock_path.open("a", encoding="utf-8") as stream:
                stream.write(
                    f"{host_receive_monotonic_ns},{sample.receiver_mac},{sample.sync_id},"
                    f"{sample.sensing_sequence},{sample.receiver_boot_id},"
                    f"{sample.tx_t1_us},{sample.rx_t2_us},{sample.rx_t3_us},"
                    f"{sample.tx_t4_us},{sample.rx_radio_t2_us},{sample.tx_radio_t4_us},"
                    f"{sample.round_trip_us},{sample.receiver_minus_transmitter_us:.6f},"
                    f"{estimate.drift_ppm:.6f},{estimate.uncertainty_us:.6f}\n"
                )

    def finish(self, status: str, **updates: Any) -> dict[str, Any]:
        """Close all streams and atomically publish final attempt metadata."""

        with self._lock:
            for csi_file, timing_file in self._receiver_streams.values():
                csi_file.flush()
                timing_file.flush()
                csi_file.close()
                timing_file.close()
            self._metadata.update(updates)
            self._metadata["status"] = status
            _write_json(self.path / "attempt.json", self._metadata)
            return dict(self._metadata)

    def update_status(self, status: str, **updates: Any) -> dict[str, Any]:
        """Update disposition after the streams have already been closed."""

        with self._lock:
            self._metadata.update(updates)
            self._metadata["status"] = status
            _write_json(self.path / "attempt.json", self._metadata)
            return dict(self._metadata)


@dataclass(frozen=True)
class SessionMetadata:
    """Human-supplied metadata identifying one collection session."""

    participant_id: str
    operator: str = ""
    location: str = ""
    notes: str = ""


class SessionArtifactStore:
    """Persist a session manifest, append-only event log, and trial bundles."""

    def __init__(
        self,
        output_dir: Path,
        protocol: CollectionProtocol,
        metadata: SessionMetadata,
        session_id: str,
        environment: dict[str, Any] | None = None,
    ) -> None:
        self._receiver_ids = _receiver_bindings(environment)
        self.root = output_dir / _slug(session_id)
        self.root.mkdir(parents=True, exist_ok=False)
        self.protocol = protocol
        self.metadata = metadata
        self.session_id = session_id
        self._event_file = (self.root / "events.jsonl").open("w", encoding="utf-8")
        self._closed = False
        self._session = {
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "session_id": session_id,
            "participant_id": metadata.participant_id,
            "operator": metadata.operator,
            "location": metadata.location,
            "notes": metadata.notes,
            "protocol_id": protocol.protocol_id,
            "protocol_hash": protocol.source_hash,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "open",
            "environment": environment or {},
        }
        _write_json(self.root / "protocol.json", protocol.source)
        _write_json(self.root / "session.json", self._session)

    def event(self, kind: str, monotonic_ns: int, **data: Any) -> None:
        """Append an event with a host monotonic timestamp."""

        if self._closed:
            return
        payload = {"kind": kind, "monotonic_ns": monotonic_ns, **data}
        self._event_file.write(json.dumps(payload, sort_keys=True) + "\n")
        self._event_file.flush()

    def begin_attempt(
        self,
        trial: Trial,
        attempt_number: int,
        start_ns: int,
        extra_metadata: dict[str, Any] | None = None,
    ) -> TrialCapture:
        """Create a new numbered attempt bundle for a trial."""

        scenario_dir = self.root / "trials" / f"{trial.ordinal:03d}_{_slug(trial.scenario.id)}"
        attempt_dir = scenario_dir / f"attempt_{attempt_number:02d}"
        metadata = {
            "session_id": self.session_id,
            "trial_ordinal": trial.ordinal,
            "repetition": trial.repetition,
            "scenario_id": trial.scenario.id,
            "activity_label": trial.scenario.activity_label,
            "started_monotonic_ns": start_ns,
            "status": "recording",
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        self.event(
            "attempt_started",
            start_ns,
            trial_ordinal=trial.ordinal,
            scenario_id=trial.scenario.id,
            attempt=attempt_number,
        )
        return TrialCapture(
            attempt_dir,
            metadata,
            receiver_ids=self._receiver_ids,
        )

    def finish(self, status: str, monotonic_ns: int, **updates: Any) -> None:
        """Close the session manifest and its event stream."""

        if self._closed:
            return
        self._session.update(updates)
        self._session.update({"status": status, "ended_monotonic_ns": monotonic_ns})
        _write_json(self.root / "session.json", self._session)
        self._event_file.flush()
        self._event_file.close()
        self._closed = True
