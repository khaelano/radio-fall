"""Validated, optimistic review overlays for immutable session artifacts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from .models import SessionBundle


REVIEW_SCHEMA_VERSION = 1
INCLUSION_VALUES = ("unreviewed", "include", "exclude")
QUALITY_VALUES = ("unreviewed", "good", "questionable", "bad")
METADATA_FIELDS = ("participant_id", "operator", "location", "notes")


class ReviewError(ValueError):
    """Raised when a review sidecar is invalid or cannot be saved."""


class ReviewConflictError(ReviewError):
    """Raised when another process changed the sidecar since it was loaded."""


@dataclass
class AttemptReview:
    """Curated fields for one recorded attempt."""

    activity_label: str | None = None
    inclusion: str = "unreviewed"
    quality: str = "unreviewed"
    notes: str = ""

    def validate(self) -> None:
        """Validate fields before persistence or export."""

        if self.activity_label is not None:
            if (
                not isinstance(self.activity_label, str)
                or not self.activity_label.strip()
            ):
                raise ReviewError("corrected activity label must be non-empty")
            self.activity_label = self.activity_label.strip()
        if self.inclusion not in INCLUSION_VALUES:
            raise ReviewError(f"invalid inclusion value: {self.inclusion!r}")
        if self.quality not in QUALITY_VALUES:
            raise ReviewError(f"invalid quality value: {self.quality!r}")
        if not isinstance(self.notes, str):
            raise ReviewError("attempt review notes must be text")

    def to_mapping(self) -> dict[str, Any]:
        """Render this review into the sidecar schema."""

        self.validate()
        return {
            "activity_label": self.activity_label,
            "inclusion": self.inclusion,
            "quality": self.quality,
            "notes": self.notes,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], path: str) -> AttemptReview:
        """Validate and construct one attempt review."""

        allowed = {"activity_label", "inclusion", "quality", "notes"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ReviewError(f"{path}: unknown field(s): {', '.join(unknown)}")
        review = cls(
            activity_label=value.get("activity_label"),
            inclusion=value.get("inclusion", "unreviewed"),
            quality=value.get("quality", "unreviewed"),
            notes=value.get("notes", ""),
        )
        review.validate()
        return review


@dataclass
class ReviewDocument:
    """Current session review state plus its persisted revision history."""

    session_id: str
    protocol_hash: str
    revision: int = 0
    updated_at_utc: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    attempts: dict[str, AttemptReview] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def clone(self) -> ReviewDocument:
        """Return an independent editable copy."""

        return deepcopy(self)

    def validate(self, session: SessionBundle | None = None) -> None:
        """Validate the document and, when supplied, bind it to ``session``."""

        if not self.session_id:
            raise ReviewError("session_id must be non-empty")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise ReviewError("revision must be a non-negative integer")
        if self.updated_at_utc is not None and not isinstance(self.updated_at_utc, str):
            raise ReviewError("updated_at_utc must be text or null")
        unknown_metadata = sorted(set(self.metadata) - set(METADATA_FIELDS))
        if unknown_metadata:
            raise ReviewError(
                "metadata: unknown field(s): " + ", ".join(unknown_metadata)
            )
        if not all(isinstance(value, str) for value in self.metadata.values()):
            raise ReviewError("metadata overrides must be text")
        known_attempts = (
            {attempt.key for attempt in session.attempts} if session else None
        )
        for key, review in self.attempts.items():
            pure = PurePosixPath(key)
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or not key.startswith("trials/")
            ):
                raise ReviewError(f"invalid attempt key: {key!r}")
            if known_attempts is not None and key not in known_attempts:
                raise ReviewError(f"review references unknown attempt: {key}")
            review.validate()
        if session is not None:
            if self.session_id != session.session_id:
                raise ReviewError(
                    f"review belongs to session {self.session_id!r}, not {session.session_id!r}"
                )
            if self.protocol_hash != session.protocol_hash:
                raise ReviewError("review protocol hash does not match the session")
        if not isinstance(self.history, list) or not all(
            isinstance(item, dict) for item in self.history
        ):
            raise ReviewError("history must be an array of objects")

    def to_mapping(self) -> dict[str, Any]:
        """Render the complete sidecar document."""

        self.validate()
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "session_id": self.session_id,
            "protocol_hash": self.protocol_hash,
            "revision": self.revision,
            "updated_at_utc": self.updated_at_utc,
            "metadata": dict(sorted(self.metadata.items())),
            "attempts": {
                key: review.to_mapping()
                for key, review in sorted(self.attempts.items())
            },
            "history": deepcopy(self.history),
        }

    @classmethod
    def empty(cls, session: SessionBundle) -> ReviewDocument:
        """Create an unsaved review for ``session``."""

        return cls(session_id=session.session_id, protocol_hash=session.protocol_hash)

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], session: SessionBundle | None = None
    ) -> ReviewDocument:
        """Validate and construct a review document."""

        allowed = {
            "schema_version",
            "session_id",
            "protocol_hash",
            "revision",
            "updated_at_utc",
            "metadata",
            "attempts",
            "history",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ReviewError("review: unknown field(s): " + ", ".join(unknown))
        if value.get("schema_version") != REVIEW_SCHEMA_VERSION:
            raise ReviewError("review: only schema version 1 is supported")
        raw_metadata = value.get("metadata", {})
        raw_attempts = value.get("attempts", {})
        if not isinstance(raw_metadata, dict):
            raise ReviewError("review.metadata must be an object")
        if not isinstance(raw_attempts, dict):
            raise ReviewError("review.attempts must be an object")
        attempts: dict[str, AttemptReview] = {}
        for key, raw_review in raw_attempts.items():
            if not isinstance(key, str) or not isinstance(raw_review, dict):
                raise ReviewError("review.attempts must map paths to objects")
            attempts[key] = AttemptReview.from_mapping(
                raw_review, f"review.attempts[{key!r}]"
            )
        document = cls(
            session_id=value.get("session_id", ""),
            protocol_hash=value.get("protocol_hash", ""),
            revision=value.get("revision", 0),
            updated_at_utc=value.get("updated_at_utc"),
            metadata=dict(raw_metadata),
            attempts=attempts,
            history=deepcopy(value.get("history", [])),
        )
        document.validate(session)
        return document


@dataclass(frozen=True)
class LoadedReview:
    """A review document and its optimistic-concurrency token."""

    document: ReviewDocument
    token: str | None


def _token(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _serialized(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten(child, child_prefix))
        return result
    return {prefix: value}


def _changes(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[dict[str, Any]]:
    left = _flatten(before)
    right = _flatten(after)
    return [
        {"path": path, "old": left.get(path), "new": right.get(path)}
        for path in sorted(set(left) | set(right))
        if left.get(path) != right.get(path)
    ]


class ReviewStore:
    """Read and atomically update one session's review sidecar."""

    def __init__(self, session: SessionBundle) -> None:
        self.session = session
        self.path = session.path / "session_review.json"

    def load(self) -> LoadedReview:
        """Load the current sidecar or return a new empty document."""

        if not self.path.exists():
            return LoadedReview(ReviewDocument.empty(self.session), None)
        try:
            raw = self.path.read_bytes()
            value = json.loads(raw.decode("utf-8"))
        except OSError as exc:
            raise ReviewError(f"unable to read {self.path}: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReviewError(f"invalid review sidecar {self.path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ReviewError("review sidecar must contain an object")
        return LoadedReview(
            ReviewDocument.from_mapping(value, self.session),
            _token(raw),
        )

    def save(
        self, document: ReviewDocument, expected_token: str | None
    ) -> LoadedReview:
        """Save a changed review, rejecting concurrent modifications."""

        if not self.session.editable:
            raise ReviewError("active sessions are read-only")
        document.validate(self.session)
        current = self.load()
        if current.token != expected_token:
            raise ReviewConflictError(
                "session_review.json changed since it was loaded; reload before saving"
            )

        before = current.document.to_mapping()
        after = document.to_mapping()
        relevant_before = {
            "metadata": before["metadata"],
            "attempts": before["attempts"],
        }
        relevant_after = {
            "metadata": after["metadata"],
            "attempts": after["attempts"],
        }
        changes = _changes(relevant_before, relevant_after)
        if not changes:
            return current

        saved = document.clone()
        saved.revision = current.document.revision + 1
        saved.updated_at_utc = datetime.now(timezone.utc).isoformat()
        saved.history = deepcopy(current.document.history)
        saved.history.append(
            {
                "revision": saved.revision,
                "saved_at_utc": saved.updated_at_utc,
                "changes": changes,
            }
        )
        payload = _serialized(saved.to_mapping())
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(self.path)
        except OSError as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ReviewError(f"unable to save {self.path}: {exc}") from exc
        return LoadedReview(saved, _token(payload))
