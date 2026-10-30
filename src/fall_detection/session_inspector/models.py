"""Manifest-only models for recorded collection sessions.

Scanning deliberately avoids opening CSV files.  A selected attempt is loaded
by :mod:`fall_detection.session_inspector.data` on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

from ..collection.protocol import (
    CollectionProtocol,
    ProtocolError,
    Trial,
    protocol_from_mapping,
)
from ..contracts import ARTIFACT_SCHEMA_VERSION


class SessionReadError(ValueError):
    """Raised when a directory is not a readable collection session."""


@dataclass(frozen=True)
class AttemptFiles:
    """Data files belonging to one receiver within an attempt."""

    receiver_id: str
    csi: Path | None = None
    radio_timing: Path | None = None
    clock_sync: Path | None = None

    @property
    def available(self) -> tuple[Path, ...]:
        """Return the files that exist, in display order."""

        return tuple(
            path
            for path in (self.csi, self.radio_timing, self.clock_sync)
            if path is not None
        )


@dataclass(frozen=True)
class RecordedAttempt:
    """One recorded attempt and its small metadata manifest."""

    path: Path
    key: str
    attempt_number: int
    trial_ordinal: int
    scenario_id: str
    repetition: int | None
    activity_label: str
    status: str
    metadata: dict[str, Any]
    receiver_files: tuple[AttemptFiles, ...]
    warnings: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        """Return whether acquisition may still be writing this attempt."""

        return self.status.lower() == "recording"

    @property
    def receiver_ids(self) -> tuple[str, ...]:
        """Return receiver identifiers in stable display order."""

        return tuple(files.receiver_id for files in self.receiver_files)

    def files_for(self, receiver_id: str) -> AttemptFiles:
        """Return the files for ``receiver_id``."""

        for files in self.receiver_files:
            if files.receiver_id == receiver_id:
                return files
        raise KeyError(receiver_id)


@dataclass(frozen=True)
class RecordedTrial:
    """A planned protocol trial plus any attempts recorded for it."""

    ordinal: int
    scenario_id: str
    repetition: int | None
    activity_label: str
    title: str
    instruction: str
    block_title: str
    attributes: dict[str, Any]
    attempts: tuple[RecordedAttempt, ...] = ()


@dataclass(frozen=True)
class SessionBundle:
    """Manifest-level view of a collection session directory."""

    path: Path
    manifest: dict[str, Any]
    protocol_source: dict[str, Any]
    protocol: CollectionProtocol | None
    trials: tuple[RecordedTrial, ...]
    attempts: tuple[RecordedAttempt, ...]
    warnings: tuple[str, ...] = ()

    @property
    def session_id(self) -> str:
        """Return the recorded session identifier."""

        return str(self.manifest.get("session_id") or self.path.name)

    @property
    def protocol_hash(self) -> str:
        """Return the acquisition-time protocol hash when available."""

        return str(self.manifest.get("protocol_hash") or "")

    @property
    def status(self) -> str:
        """Return the normalized session status."""

        return str(self.manifest.get("status") or "unknown")

    @property
    def active(self) -> bool:
        """Return whether the collector may still be writing this bundle."""

        return self.status.lower() in {"open", "recording"} or any(
            attempt.active for attempt in self.attempts
        )

    @property
    def editable(self) -> bool:
        """Return whether review edits are safe for this session."""

        return not self.active

    @property
    def labels(self) -> tuple[str, ...]:
        """Return known activity labels for correction suggestions."""

        labels = {attempt.activity_label for attempt in self.attempts}
        labels.update(trial.activity_label for trial in self.trials)
        labels.discard("")
        return tuple(sorted(labels))

    def attempt_for_key(self, key: str) -> RecordedAttempt:
        """Return an attempt addressed by its stable relative key."""

        for attempt in self.attempts:
            if attempt.key == key:
                return attempt
        raise KeyError(key)


_ATTEMPT_NUMBER = re.compile(r"attempt_(\d+)$")


def _read_object(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SessionReadError(f"unable to read {description} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SessionReadError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise SessionReadError(f"{description} {path} must contain an object")
    return value


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _file_if_present(path: Path) -> Path | None:
    return path if path.is_file() else None


def _attempt_files(path: Path) -> tuple[AttemptFiles, ...]:
    receivers = path / "receivers"
    result: list[AttemptFiles] = []
    if receivers.is_dir():
        for receiver in sorted(item for item in receivers.iterdir() if item.is_dir()):
            result.append(
                AttemptFiles(
                    receiver_id=receiver.name,
                    csi=_file_if_present(receiver / "csi.csv"),
                    radio_timing=_file_if_present(receiver / "radio_timing.csv"),
                    clock_sync=_file_if_present(receiver / "usb_clock_sync.csv"),
                )
            )
    return tuple(result)


def _load_attempt(session_root: Path, path: Path) -> RecordedAttempt:
    warnings: list[str] = []
    manifest_path = path / "attempt.json"
    if manifest_path.is_file():
        try:
            metadata = _read_object(manifest_path, "attempt manifest")
        except SessionReadError as exc:
            metadata = {}
            warnings.append(str(exc))
    else:
        metadata = {}
        warnings.append(f"missing {manifest_path.relative_to(session_root)}")

    match = _ATTEMPT_NUMBER.fullmatch(path.name)
    attempt_number = int(match.group(1)) if match else 0
    ordinal = _optional_int(metadata.get("trial_ordinal")) or 0
    if ordinal < 1:
        parent_prefix = path.parent.name.split("_", 1)[0]
        ordinal = int(parent_prefix) if parent_prefix.isdigit() else 0
    key = path.relative_to(session_root).as_posix()
    status = str(metadata.get("status") or "unknown")
    activity_label = str(metadata.get("activity_label") or "")
    schema_version = metadata.get("artifact_schema_version")
    if schema_version not in (None, ARTIFACT_SCHEMA_VERSION):
        warnings.append(
            f"{manifest_path.relative_to(session_root)}: unsupported artifact "
            f"schema {schema_version!r}"
        )
    return RecordedAttempt(
        path=path,
        key=key,
        attempt_number=attempt_number,
        trial_ordinal=ordinal,
        scenario_id=str(metadata.get("scenario_id") or path.parent.name),
        repetition=_optional_int(metadata.get("repetition")),
        activity_label=activity_label,
        status=status,
        metadata=metadata,
        receiver_files=_attempt_files(path),
        warnings=tuple(warnings),
    )


def _trial_from_protocol(trial: Trial, attempts: Iterable[RecordedAttempt]) -> RecordedTrial:
    scenario = trial.scenario
    return RecordedTrial(
        ordinal=trial.ordinal,
        scenario_id=scenario.id,
        repetition=trial.repetition,
        activity_label=scenario.activity_label,
        title=scenario.title,
        instruction=scenario.instruction,
        block_title=scenario.block_title,
        attributes=dict(scenario.attributes),
        attempts=tuple(attempts),
    )


def _orphan_trial(ordinal: int, attempts: list[RecordedAttempt]) -> RecordedTrial:
    first = attempts[0]
    return RecordedTrial(
        ordinal=ordinal,
        scenario_id=first.scenario_id,
        repetition=first.repetition,
        activity_label=first.activity_label,
        title=first.scenario_id or f"Trial {ordinal}",
        instruction="",
        block_title="",
        attributes={},
        attempts=tuple(attempts),
    )


def load_session(path: Path) -> SessionBundle:
    """Load session and attempt manifests without reading recorded CSV data."""

    root = path.resolve()
    if not root.is_dir():
        raise SessionReadError(f"session directory does not exist: {root}")
    manifest_path = root / "session.json"
    if not manifest_path.is_file():
        raise SessionReadError(f"missing session manifest: {manifest_path}")
    manifest = _read_object(manifest_path, "session manifest")
    schema_version = manifest.get("artifact_schema_version")
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise SessionReadError(
            f"{manifest_path}: unsupported artifact schema {schema_version!r}; "
            f"this build reads schema {ARTIFACT_SCHEMA_VERSION} only"
        )

    warnings: list[str] = []
    protocol_source: dict[str, Any] = {}
    protocol: CollectionProtocol | None = None
    protocol_path = root / "protocol.json"
    if protocol_path.is_file():
        try:
            protocol_source = _read_object(protocol_path, "protocol snapshot")
            protocol = protocol_from_mapping(protocol_source)
        except (SessionReadError, ProtocolError) as exc:
            warnings.append(str(exc))
    else:
        warnings.append("missing protocol.json")

    attempt_paths = sorted(
        item
        for item in (root / "trials").glob("*/attempt_*")
        if item.is_dir()
    ) if (root / "trials").is_dir() else []
    attempts = tuple(_load_attempt(root, item) for item in attempt_paths)
    for attempt in attempts:
        warnings.extend(attempt.warnings)

    by_ordinal: dict[int, list[RecordedAttempt]] = {}
    for attempt in attempts:
        by_ordinal.setdefault(attempt.trial_ordinal, []).append(attempt)
    for grouped in by_ordinal.values():
        grouped.sort(key=lambda item: (item.attempt_number, item.key))

    trials: list[RecordedTrial] = []
    planned_ordinals: set[int] = set()
    if protocol is not None:
        for trial in protocol.trials:
            planned_ordinals.add(trial.ordinal)
            trials.append(_trial_from_protocol(trial, by_ordinal.get(trial.ordinal, ())))
    for ordinal in sorted(set(by_ordinal) - planned_ordinals):
        trials.append(_orphan_trial(ordinal, by_ordinal[ordinal]))
    trials.sort(key=lambda item: item.ordinal)

    return SessionBundle(
        path=root,
        manifest=manifest,
        protocol_source=protocol_source,
        protocol=protocol,
        trials=tuple(trials),
        attempts=attempts,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def scan_sessions(path: Path) -> tuple[SessionBundle, ...]:
    """Load a session path or every immediate session below a directory.

    Invalid children are ignored so one damaged directory does not hide the
    remaining dataset.  Passing an invalid individual session still raises a
    :class:`SessionReadError`.
    """

    root = path.resolve()
    if (root / "session.json").is_file():
        return (load_session(root),)
    if not root.is_dir():
        raise SessionReadError(f"sessions directory does not exist: {root}")
    sessions: list[SessionBundle] = []
    for child in sorted((item for item in root.iterdir() if item.is_dir()), reverse=True):
        if not (child / "session.json").is_file():
            continue
        try:
            sessions.append(load_session(child))
        except SessionReadError:
            continue
    return tuple(sessions)
