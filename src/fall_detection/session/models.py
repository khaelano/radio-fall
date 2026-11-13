"""Manifest-level models for recorded collection sessions.

Loading and scanning read only the small JSON manifests.  The receivers of an
attempt come from the typed frame tables derived from the raw journals (see
the Rust ``radio_storage`` library); they are resolved explicitly when a
single session is opened.  The session inspector loads a selected attempt
on demand (:mod:`fall_detection.session_inspector.data`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pyarrow as pa

from .._radio_native import FrameStore
from ..collection.protocol import (
    CollectionProtocol,
    ProtocolError,
    Trial,
    protocol_from_mapping,
)
from .schema import ARTIFACT_SCHEMA_VERSION
from .source import SessionSource


class SessionReadError(ValueError):
    """Raised when a directory is not a readable collection session."""


def session_frames_directory(session_path: Path, session_id: str) -> Path:
    """Return where the converted frame tables of a session are cached.

    The cache lives in the project ``data`` directory, never inside the raw
    session. For the standard layout ``<data>/raw/sessions/<session>`` the data
    root is ``<data>``; for any other parent directory it is that directory's
    parent, so ``<root>/<session>`` caches under ``<root>/../interim/frames``.

    Args:
        session_path: Session directory.
        session_id: Recorded session identifier, a single path component.

    Returns:
        ``<data_root>/interim/frames/<session_id>``.

    Raises:
        ValueError: If ``session_id`` is not a plain directory name.
    """

    sessions_dir = session_path.resolve().parent
    if sessions_dir.name == "sessions" and sessions_dir.parent.name == "raw":
        data_root = sessions_dir.parent.parent
    else:
        data_root = sessions_dir.parent
    if (
        not session_id
        or session_id in {".", ".."}
        or Path(session_id).name != session_id
    ):
        raise ValueError(f"invalid session id: {session_id!r}")
    return data_root / "interim" / "frames" / session_id


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
    session_path: Path
    frames_path: Path
    receiver_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        """Return whether acquisition may still be writing this attempt."""

        return self.status.lower() == "recording"


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
    receivers_resolved: bool = True

    @property
    def session_id(self) -> str:
        """Return the recorded session identifier."""

        return str(self.manifest.get("session_id") or SessionSource(self.path).name)

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

    def with_receivers(
        self, progress: Callable[[str], None] | None = None
    ) -> SessionBundle:
        """Return this bundle with each attempt's receivers filled in.

        The receivers are those with frames inside the attempt window. The frame
        tables are converted from the raw journals when missing or stale, which
        can take a while for a large session. A session whose tables cannot be
        built keeps empty receiver lists and gains a warning instead of failing.

        Args:
            progress: Optional callback receiving conversion status messages.

        Returns:
            A bundle with ``receivers_resolved`` set; ``self`` if it already is.
        """

        if self.receivers_resolved:
            return self
        warnings = list(self.warnings)
        receivers: dict[str, tuple[str, ...]] = {}
        if self.attempts:
            try:
                receivers = _receivers_by_attempt(self.attempts, progress)
            except (OSError, RuntimeError, ValueError) as exc:
                warnings.append(f"frame tables unavailable: {exc}")
        updated = {
            attempt.key: replace(attempt, receiver_ids=receivers.get(attempt.key, ()))
            for attempt in self.attempts
        }
        return replace(
            self,
            trials=tuple(
                replace(
                    trial,
                    attempts=tuple(updated[item.key] for item in trial.attempts),
                )
                for trial in self.trials
            ),
            attempts=tuple(updated[attempt.key] for attempt in self.attempts),
            warnings=tuple(dict.fromkeys(warnings)),
            receivers_resolved=True,
        )


_ATTEMPT_NUMBER = re.compile(r"attempt_(\d+)$")


def read_json_object(
    source: SessionSource, relative: str, description: str
) -> dict[str, Any]:
    """Read one JSON object of a session, directory or archive alike.

    Args:
        source: Where the session lives.
        relative: File relative to the session root.
        description: Short noun used in error messages, e.g. ``"session manifest"``.

    Returns:
        The decoded object.

    Raises:
        SessionReadError: If the file is unreadable, not valid JSON, or not an
            object. It is a :class:`ValueError`.
    """

    path = source.path / relative
    try:
        value = json.loads(source.read_text(relative))
    except OSError as exc:
        raise SessionReadError(f"unable to read {description} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SessionReadError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise SessionReadError(f"{description} {path} must contain an object")
    return value


def _session_identifier(manifest: dict[str, Any], root: Path) -> str:
    """Return the manifest session id when usable as a directory name."""

    name = SessionSource(root).name
    identifier = str(manifest.get("session_id") or name)
    return identifier if Path(identifier).name == identifier else name


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def attempt_indices(frames: FrameStore) -> dict[tuple[int, int], int]:
    """Map ``(trial_ordinal, attempt_number)`` to rows of the attempts table."""

    table = pa.table(frames.attempts())
    return {
        (ordinal, number): index
        for index, (ordinal, number) in enumerate(
            zip(
                table.column("trial_ordinal").to_pylist(),
                table.column("attempt").to_pylist(),
                strict=True,
            )
        )
    }


def _receivers_by_attempt(
    attempts: tuple[RecordedAttempt, ...],
    progress: Callable[[str], None] | None,
) -> dict[str, tuple[str, ...]]:
    """Map attempt keys to the receivers with frames in each attempt window."""

    frames = FrameStore.ensure(
        str(attempts[0].session_path),
        str(attempts[0].frames_path),
        progress=progress,
    )
    indices = attempt_indices(frames)
    receivers: dict[str, tuple[str, ...]] = {}
    for attempt in attempts:
        index = indices.get((attempt.trial_ordinal, attempt.attempt_number))
        if index is not None:
            table = pa.table(frames.attempt_frames(index, columns=["receiver_id"]))
            receivers[attempt.key] = tuple(
                sorted(set(table.column("receiver_id").to_pylist()))
            )
    return receivers


def _load_attempt(
    source: SessionSource, key: str, session_root: Path, frames_path: Path
) -> RecordedAttempt:
    warnings: list[str] = []
    path = session_root / key
    manifest_relative = f"{key}/attempt.json"
    if source.exists(manifest_relative):
        try:
            metadata = read_json_object(source, manifest_relative, "attempt manifest")
        except SessionReadError as exc:
            metadata = {}
            warnings.append(str(exc))
    else:
        metadata = {}
        warnings.append(f"missing {manifest_relative}")

    match = _ATTEMPT_NUMBER.fullmatch(path.name)
    attempt_number = int(match.group(1)) if match else 0
    ordinal = _optional_int(metadata.get("trial_ordinal")) or 0
    if ordinal < 1:
        parent_prefix = path.parent.name.split("_", 1)[0]
        ordinal = int(parent_prefix) if parent_prefix.isdigit() else 0
    status = str(metadata.get("status") or "unknown")
    activity_label = str(metadata.get("activity_label") or "")
    schema_version = metadata.get("artifact_schema_version")
    if schema_version not in (None, ARTIFACT_SCHEMA_VERSION):
        warnings.append(
            f"{manifest_relative}: unsupported artifact schema {schema_version!r}"
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
        session_path=session_root,
        frames_path=frames_path,
        warnings=tuple(warnings),
    )


def _trial_from_protocol(
    trial: Trial, attempts: Iterable[RecordedAttempt]
) -> RecordedTrial:
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


def load_session(path: Path, *, resolve_receivers: bool = False) -> SessionBundle:
    """Load a session directory or archive and its manifests.

    By default only the small JSON manifests are read, so the call is cheap and
    never touches the frame cache; attempts then have no receivers.

    Args:
        path: Session directory containing ``session.json``, or a version-3
            session archive, which is read in place without extracting it.
        resolve_receivers: Also fill in each attempt's receivers from the frame
            tables, converting the raw journals when needed. Equivalent to
            calling :meth:`SessionBundle.with_receivers` on the result.

    Returns:
        The loaded session.

    Raises:
        SessionReadError: If the directory is not a readable session.
    """

    root = path.resolve()
    if not (root.is_dir() or root.is_file()):
        raise SessionReadError(f"session does not exist: {root}")
    source = SessionSource(root)
    manifest_path = root / "session.json"
    try:
        has_manifest = source.exists("session.json")
    except RuntimeError as exc:
        raise SessionReadError(f"unreadable session archive {root}: {exc}") from exc
    if not has_manifest:
        raise SessionReadError(f"missing session manifest: {manifest_path}")
    manifest = read_json_object(source, "session.json", "session manifest")
    schema_version = manifest.get("artifact_schema_version")
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise SessionReadError(
            f"{manifest_path}: unsupported artifact schema {schema_version!r}; "
            f"this build reads schema {ARTIFACT_SCHEMA_VERSION} only"
        )

    warnings: list[str] = []
    protocol_source: dict[str, Any] = {}
    protocol: CollectionProtocol | None = None
    if source.exists("protocol.json"):
        try:
            protocol_source = read_json_object(
                source, "protocol.json", "protocol snapshot"
            )
            protocol = protocol_from_mapping(protocol_source)
        except (SessionReadError, ProtocolError) as exc:
            warnings.append(str(exc))
    else:
        warnings.append("missing protocol.json")

    frames_path = session_frames_directory(root, _session_identifier(manifest, root))
    keys = source.attempt_keys()
    source.prefetch([f"{key}/attempt.json" for key in keys])
    attempts = tuple(_load_attempt(source, key, root, frames_path) for key in keys)
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
            trials.append(
                _trial_from_protocol(trial, by_ordinal.get(trial.ordinal, ()))
            )
    for ordinal in sorted(set(by_ordinal) - planned_ordinals):
        trials.append(_orphan_trial(ordinal, by_ordinal[ordinal]))
    trials.sort(key=lambda item: item.ordinal)

    bundle = SessionBundle(
        path=root,
        manifest=manifest,
        protocol_source=protocol_source,
        protocol=protocol,
        trials=tuple(trials),
        attempts=attempts,
        warnings=tuple(dict.fromkeys(warnings)),
        receivers_resolved=False,
    )
    return bundle.with_receivers() if resolve_receivers else bundle


def _is_session(path: Path) -> bool:
    """Return whether ``path`` is a session directory or a session archive."""

    if path.is_dir():
        return (path / "session.json").is_file()
    return path.is_file() and path.suffix == ".zip"


def scan_sessions(path: Path) -> tuple[SessionBundle, ...]:
    """Load a session path or every immediate session below a directory.

    Both session directories and ``.zip`` archives are listed. Sessions are
    listed from their manifests only, so browsing never converts a recording or
    extracts an archive; call :meth:`SessionBundle.with_receivers` on the one
    being opened.

    Invalid children are ignored so one damaged directory or archive does not
    hide the remaining dataset.  Passing an invalid individual session still
    raises a :class:`SessionReadError`.
    """

    root = path.resolve()
    if _is_session(root):
        return (load_session(root),)
    if not root.is_dir():
        raise SessionReadError(f"sessions directory does not exist: {root}")
    sessions: list[SessionBundle] = []
    for child in sorted(
        (item for item in root.iterdir() if _is_session(item)), reverse=True
    ):
        try:
            sessions.append(load_session(child))
        except SessionReadError:
            continue
    return tuple(sessions)
