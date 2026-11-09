"""Per-attempt capture sinks and session artifact persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import os
import re
from threading import RLock
from typing import Any, TextIO

from ..contracts import ARTIFACT_SCHEMA_VERSION
from ..radio.acquisition.clock_sync import ClockSyncEstimate, ClockSyncSample
from ..radio.acquisition.protocol import CSI_HEADER, CsiRecord, format_csi_record
from ..radio.acquisition.recording_io import RecordingIO
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


def _lock_events(stream: TextIO) -> None:
    """Hold a POSIX session writer lock until the event stream closes."""
    if os.name == "posix":
        import fcntl

        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("session is already open in another collector") from exc


def _reject_legacy_writer(path: Path) -> None:
    """Detect Linux writers launched before session locks were introduced."""
    if not Path("/proc").is_dir():
        return
    target = path.stat()
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            for descriptor in (process / "fd").iterdir():
                try:
                    value = descriptor.stat()
                    if (value.st_dev, value.st_ino) != (target.st_dev, target.st_ino):
                        continue
                    for line in (process / "fdinfo" / descriptor.name).read_text().splitlines():
                        if line.startswith("flags:") and int(line.split()[1], 8) & os.O_ACCMODE:
                            raise ValueError("session is already open in another collector")
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue


class TrialCapture:
    """Thread-safe, receiver-split writers for one trial attempt."""

    def __init__(
        self,
        path: Path,
        initial_metadata: dict[str, Any],
        *,
        receiver_ids: dict[str, str],
        recording_io: RecordingIO | None = None,
    ) -> None:
        if not receiver_ids:
            raise ValueError("TrialCapture requires at least one receiver binding")
        self.path = path
        self.path.mkdir(parents=True, exist_ok=False)
        self._lock = RLock()
        self._metadata = dict(initial_metadata)
        self._metadata["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
        self._metadata["status"] = "recording"
        self._io = recording_io
        _write_json(self.path / "attempt.json", self._metadata)
        self.receiver_ids = {
            mac.lower(): receiver_id for mac, receiver_id in receiver_ids.items()
        }
        self._receiver_streams: dict[str, tuple[TextIO, TextIO]] = {}
        self._ble_streams: dict[str, TextIO] = {}
        self._clock_streams: dict[str, TextIO] = {}
        for receiver_id in sorted(set(self.receiver_ids.values())):
            receiver_path = self.path / "receivers" / _slug(receiver_id)
            receiver_path.mkdir(parents=True, exist_ok=True)
            csi_file = self._open(receiver_path / "csi.csv",
                "w", encoding="utf-8", newline=""
            )
            timing_file = self._open(receiver_path / "radio_timing.csv",
                "w", encoding="utf-8", newline=""
            )
            csi_file.write(CSI_HEADER + "\n")
            timing_file.write(TIMING_HEADER + "\n")
            clock = self._clock_streams[receiver_id] = self._open(
                receiver_path / "usb_clock_sync.csv", "w", encoding="utf-8", buffering=1)
            clock.write(CLOCK_SYNC_HEADER + "\n")
            self._receiver_streams[receiver_id] = (csi_file, timing_file)

    def _open(self, path: Path, mode: str, **kwargs):
        return self._io.open(path, mode, **kwargs) if self._io else path.open(mode, **kwargs)

    @property
    def writes_complete(self) -> bool:
        """Return true once all closed attempt streams have reached file buffers."""
        if self._io:
            self._io.check()
        streams = [s for pair in self._receiver_streams.values() for s in pair]
        streams += list(self._clock_streams.values()) + list(self._ble_streams.values())
        return all(getattr(s, "saved", s.closed) for s in streams)

    def write_radio(self, record: CsiRecord, host_receive_monotonic_ns: int) -> None:
        """Append one decoded radio record and its timing sidecar row."""

        with self._lock:
            receiver_id = self.receiver_ids.get(record.receiver_mac.lower())
            if receiver_id is None:
                return
            tx_timestamp = (
                "" if record.tx_timestamp_us is None else record.tx_timestamp_us
            )
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
            if record.run_id is not None:
                self._write_ble_timing(receiver_id, record, host_receive_monotonic_ns)

    def _write_ble_timing(
        self, receiver_id: str, record: CsiRecord, arrival_ns: int
    ) -> None:
        if receiver_id not in self._ble_streams:
            filename = "gateway_timing.jsonl" if record.transport == "espnow_gateway" else "ble_timing.jsonl"
            path = self.path / "receivers" / _slug(receiver_id) / filename
            self._ble_streams[receiver_id] = self._open(path, "x", encoding="utf-8")
        value = dict(
            schema_version=1,
            sequence=record.sequence,
            receiver_mac=record.receiver_mac,
            run_id=str(record.run_id),
            transmitter_boot_id=record.transmitter_boot_id,
            receiver_boot_id=record.receiver_boot_id,
            rx_radio_timestamp_us=record.timestamp_us,
            tx_enqueue_timestamp_us=record.tx_timestamp_us,
            capture_host_monotonic_ns=record.capture_host_monotonic_ns,
            clock_uncertainty_us=record.capture_clock_uncertainty_us,
            host_receive_monotonic_ns=arrival_ns,
        )
        self._ble_streams[receiver_id].write(
            json.dumps(value, separators=(",", ":")) + "\n"
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
            self._clock_streams[receiver_id].write(
                    f"{host_receive_monotonic_ns},{sample.receiver_mac},{sample.sync_id},"
                    f"{sample.sensing_sequence},{sample.receiver_boot_id},"
                    f"{sample.tx_t1_us},{sample.rx_t2_us},{sample.rx_t3_us},"
                    f"{sample.tx_t4_us},{sample.rx_radio_t2_us},{sample.tx_radio_t4_us},"
                    f"{sample.round_trip_us},{sample.receiver_minus_transmitter_us:.6f},"
                    f"{estimate.drift_ppm:.6f},{estimate.uncertainty_us:.6f}\n"
            )

    def close_streams(self) -> None:
        """Close writers after the optional BLE drain interval."""
        with self._lock:
            for csi_file, timing_file in self._receiver_streams.values():
                if not csi_file.closed:
                    csi_file.flush()
                    timing_file.flush()
                    csi_file.close()
                    timing_file.close()

            for stream in (*self._ble_streams.values(), *self._clock_streams.values()):
                if not stream.closed:
                    stream.flush()
                    stream.close()

    def finish(
        self, status: str, *, defer_close: bool = False, **updates: Any
    ) -> dict[str, Any]:
        """Publish final metadata, optionally deferring stream closure for BLE."""

        with self._lock:
            if not defer_close:
                self.close_streams()
            self._metadata.update(updates)
            self._metadata["status"] = status
            _write_json(self.path / "attempt.json", self._metadata)
            return dict(self._metadata)

    def update_status(self, status: str, **updates: Any) -> dict[str, Any]:
        """Update disposition independently of the optional file-drain interval."""

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
        recording_io: RecordingIO | None = None,
    ) -> None:
        self._receiver_ids = _receiver_bindings(environment)
        self.root = output_dir / _slug(session_id)
        self.root.mkdir(parents=True, exist_ok=False)
        self.protocol = protocol
        self.metadata = metadata
        self.session_id = session_id
        self._io = recording_io
        self._event_file = (
            recording_io.open(self.root / "events.jsonl", "x") if recording_io
            else (self.root / "events.jsonl").open("x", encoding="utf-8"))
        _lock_events(self._event_file)
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

    @classmethod
    def reopen(cls, root: Path, environment: dict[str, Any], recording_io=None):
        """Lock and validate an existing session before allowing any mutation."""
        from .resume import load_session_resume

        _reject_legacy_writer(root / "events.jsonl")
        stream = (recording_io.open(root / "events.jsonl", "a") if recording_io
                  else (root / "events.jsonl").open("a", encoding="utf-8"))
        try:
            _lock_events(stream)
            saved = load_session_resume(root)
            old = saved.manifest.get("environment", {})
            for key in ("receiver_ids", "radio_profile_fingerprint", "gateway_transport_fingerprint"):
                if old.get(key) != environment.get(key):
                    raise ValueError(f"cannot resume with changed {key}")
            if bool(old.get("video")) != bool(environment.get("video")):
                raise ValueError("resume must retain the session's enabled video mode")
            store = cls.__new__(cls)
            store.root, store.protocol, store.metadata = saved.root, saved.protocol, saved.metadata
            store.session_id = saved.manifest["session_id"]
            store._session = dict(saved.manifest)
            store._receiver_ids = _receiver_bindings(environment)
            store._event_file, store._closed = stream, False
            store._io = recording_io
            return store, saved
        except BaseException:
            stream.close()
            raise

    def mark_resumed(self, monotonic_ns: int, environment: dict[str, Any]) -> None:
        """Append the new process epoch while retaining original session inputs."""
        previous = self._session.get("status")
        ended = self._session.pop("ended_monotonic_ns", None)
        value = dict(resumed_at_utc=datetime.now(timezone.utc).isoformat(),
                     resumed_monotonic_ns=monotonic_ns, previous_status=previous,
                     previous_ended_monotonic_ns=ended, environment=environment)
        boot = Path("/proc/sys/kernel/random/boot_id")
        value["host_boot_id"] = boot.read_text().strip() if boot.exists() else None
        self._session.setdefault("resumptions", []).append(value)
        self._session["status"] = "open"
        _write_json(self.root / "session.json", self._session)
        # A fully written last JSON value may lack its final newline after exit.
        data = (self.root / "events.jsonl").read_bytes()
        if data and not data.endswith(b"\n"):
            self._event_file.write("\n")
        self.event("session_resumed", monotonic_ns, **value)

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

        scenario_dir = (
            self.root / "trials" / f"{trial.ordinal:03d}_{_slug(trial.scenario.id)}"
        )
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
            recording_io=self._io,
        )

    def finish(self, status: str, monotonic_ns: int, **updates: Any) -> None:
        """Close the session manifest and its event stream."""

        if self._closed:
            return
        self._session.update(updates)
        self._session.update({"status": status, "ended_monotonic_ns": monotonic_ns})
        _write_json(self.root / "session.json", self._session)
        self._event_file.flush()
        if self._io is None:
            self._event_file.close()
        self._closed = True
