"""Validate saved collection progress without opening or changing recordings."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..storage.compressed import read_text
from ..contracts import ARTIFACT_SCHEMA_VERSION
from .capture import SessionMetadata
from .protocol import CollectionProtocol, load_protocol


@dataclass(frozen=True)
class SessionResume:
    """Validated saved queue, explicit dispositions and reserved attempt numbers."""

    root: Path
    protocol: CollectionProtocol
    metadata: SessionMetadata
    manifest: dict[str, Any]
    trial_index: int
    attempt_numbers: dict[int, int]
    abandoned: tuple[Path, ...]
    recovered_resolutions: tuple[int, ...]


def load_session_resume(root: Path) -> SessionResume:
    """Read the saved protocol and recover the first unresolved trial.

    Accepted/skipped trials must form a contiguous prefix. Incomplete attempts
    reserve their names and are retried under new numbers; old streams are never
    reopened. Malformed or conflicting progress fails before any file mutation.
    """
    root = root.resolve()
    manifest = json.loads((root / "session.json").read_text())
    if manifest.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ValueError("unsupported session artifact schema for resume")
    protocol = load_protocol(root / "protocol.json")
    if (manifest.get("protocol_hash"), manifest.get("protocol_id")) != (
        protocol.source_hash,
        protocol.protocol_id,
    ):
        raise ValueError("saved session protocol identity/hash mismatch")
    metadata = SessionMetadata(
        **{
            key: manifest.get(key, "")
            for key in ("participant_id", "operator", "location", "notes")
        }
    )
    if not metadata.participant_id.strip():
        raise ValueError("saved session has no participant identity")
    numbers: dict[int, int] = {}
    resolved: dict[int, str] = {}
    for line in read_text(root / "events.jsonl").splitlines():
        e = json.loads(line)
        if e.get("kind") not in {"attempt_started", "trial_resolved"}:
            continue
        ordinal = e["trial_ordinal"]
        if type(ordinal) is not int or not 1 <= ordinal <= len(protocol.trials):
            raise ValueError("saved trial ordinal is outside the protocol")
        attempt = e.get("attempt", 0)
        if type(attempt) is not int or attempt < 0:
            raise ValueError("invalid saved attempt number")
        numbers[ordinal] = max(numbers.get(ordinal, 0), attempt)
        if e["kind"] == "trial_resolved":
            disposition = e.get("disposition")
            if disposition not in {"accepted", "skipped"}:
                raise ValueError("invalid saved trial disposition")
            if ordinal in resolved and resolved[ordinal] != disposition:
                raise ValueError("conflicting saved trial resolutions")
            resolved[ordinal] = disposition
    abandoned = []
    accepted = set()
    for folder in sorted((root / "trials").glob("*/attempt_*")):
        if not folder.is_dir() or not folder.resolve().is_relative_to(root):
            raise ValueError("invalid saved attempt path")
        try:
            ordinal = int(folder.parent.name.split("_", 1)[0])
            attempt = int(folder.name.removeprefix("attempt_"))
        except ValueError as exc:
            raise ValueError("invalid saved attempt directory") from exc
        if not 1 <= ordinal <= len(protocol.trials) or attempt < 1:
            raise ValueError("saved attempt is outside the protocol")
        numbers[ordinal] = max(numbers.get(ordinal, 0), attempt)
        path = folder / "attempt.json"
        if not path.exists():
            continue  # A crash before metadata publication still reserves its name.
        value = json.loads(path.read_text())
        if (
            value.get("session_id") != manifest["session_id"]
            or value.get("trial_ordinal") != ordinal
            or value.get("scenario_id") != protocol.trials[ordinal - 1].scenario.id
            or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        ):
            raise ValueError("saved attempt identity does not match the session")
        status = value.get("status")
        if status == "accepted":
            accepted.add(ordinal)
        elif status in {"recording", "pending_review"}:
            abandoned.append(path)
        elif status not in {"invalid", "incomplete", "rejected", "skipped"}:
            raise ValueError("unsupported saved attempt status")
    recovered = tuple(sorted(accepted - resolved.keys()))
    for ordinal in accepted:
        if resolved.get(ordinal, "accepted") != "accepted":
            raise ValueError("accepted attempt conflicts with skipped trial")
        resolved[ordinal] = "accepted"
    if any(state == "accepted" and n not in accepted for n, state in resolved.items()):
        raise ValueError("accepted trial has no accepted attempt")
    index = 0
    while index + 1 in resolved:
        index += 1
    if len(resolved) != index:
        raise ValueError("saved progress is not a contiguous trial prefix")
    if index == len(protocol.trials):
        raise ValueError("all session trials are already resolved")
    return SessionResume(
        root, protocol, metadata, manifest, index, numbers, tuple(abandoned), recovered
    )
