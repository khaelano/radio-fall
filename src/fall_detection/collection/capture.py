"""Per-attempt capture sinks and session artifact persistence."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, TextIO

from .._radio_native import storage_read_file
from ..protocol.model import CollectionProtocol, Trial
from ..radio.recording_io import RecordingIO
from ..session.schema import ARTIFACT_SCHEMA_VERSION


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


class TrialCapture:
    """Metadata of one trial attempt.

    The radio data of every attempt lives in the Rust transport journal in the
    session directory; conversion assigns frames to attempts by capture time. The
    capture only keeps ``attempt.json``. The per-receiver CSV and timing sidecars
    that earlier collectors wrote beside it were removed after a hardware session
    matched them frame for frame (see
    ``docs/reports/architecture-rehaul-status-2026-11-13.md``).
    """

    def __init__(
        self,
        path: Path,
        initial_metadata: dict[str, Any],
        *,
        recording_io: RecordingIO | None = None,
    ) -> None:
        self.path = path
        self.path.mkdir(parents=True, exist_ok=False)
        self._lock = RLock()
        self._metadata = dict(initial_metadata)
        self._metadata["artifact_schema_version"] = ARTIFACT_SCHEMA_VERSION
        self._metadata["status"] = "recording"
        self._io = recording_io
        _write_json(self.path / "attempt.json", self._metadata)

    @property
    def writes_complete(self) -> bool:
        """Return true once background session writes have not failed.

        Raises:
            OSError: If the background writer reported a failed write.
        """
        if self._io:
            self._io.check()
        return True

    def finish(self, status: str, **updates: Any) -> dict[str, Any]:
        """Publish final metadata."""

        with self._lock:
            self._metadata.update(updates)
            self._metadata["status"] = status
            _write_json(self.path / "attempt.json", self._metadata)
            return dict(self._metadata)

    def update_status(self, status: str, **updates: Any) -> dict[str, Any]:
        """Update the attempt disposition without finishing it."""

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
        _receiver_bindings(environment)
        self.root = output_dir / _slug(session_id)
        self.root.mkdir(parents=True, exist_ok=False)
        self.protocol = protocol
        self.metadata = metadata
        self.session_id = session_id
        self._io = recording_io
        self._event_file = (
            recording_io.open(self.root / "events.jsonl", "x")
            if recording_io
            else (self.root / "events.jsonl").open("x", encoding="utf-8")
        )
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
            "started_at_utc": datetime.now(UTC).isoformat(),
            "status": "open",
            "environment": environment or {},
        }
        _write_json(self.root / "protocol.json", protocol.source)
        _write_json(self.root / "session.json", self._session)

    @classmethod
    def reopen(
        cls,
        root: Path,
        environment: dict[str, Any],
        recording_io=None,
    ):
        """Lock and validate an existing session before allowing any mutation."""
        from .resume import load_session_resume

        stream = (
            recording_io.open(root / "events.jsonl", "a")
            if recording_io
            else (root / "events.jsonl").open("a", encoding="utf-8")
        )
        try:
            _lock_events(stream)
            saved = load_session_resume(root)
            old = saved.manifest.get("environment", {})
            for key in (
                "receiver_ids",
                "radio_profile_fingerprint",
                "gateway_transport_fingerprint",
            ):
                if old.get(key) != environment.get(key):
                    raise ValueError(f"cannot resume with changed {key}")
            if bool(old.get("video")) != bool(environment.get("video")):
                raise ValueError("resume must retain the session's enabled video mode")
            store = cls.__new__(cls)
            store.root, store.protocol, store.metadata = (
                saved.root,
                saved.protocol,
                saved.metadata,
            )
            store.session_id = saved.manifest["session_id"]
            store._session = dict(saved.manifest)
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
        value = {
            "resumed_at_utc": datetime.now(UTC).isoformat(),
            "resumed_monotonic_ns": monotonic_ns,
            "previous_status": previous,
            "previous_ended_monotonic_ns": ended,
            "environment": environment,
        }
        boot = Path("/proc/sys/kernel/random/boot_id")
        value["host_boot_id"] = boot.read_text().strip() if boot.exists() else None
        self._session.setdefault("resumptions", []).append(value)
        self._session["status"] = "open"
        _write_json(self.root / "session.json", self._session)
        # A fully written last JSON value may lack its final newline after exit.
        data = storage_read_file(self.root / "events.jsonl")
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
        return TrialCapture(attempt_dir, metadata, recording_io=self._io)

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
