"""Neutral model and reader of recorded collection sessions.

This package is the one place that knows how a session directory or version-3
archive is laid out: the manifest-level models (:func:`load_session`), the
directory/archive reader (:class:`SessionSource`) and the on-disk schema
version. Analysis, collection and the session inspector all depend on it, and it
does not import any of them except ``collection.protocol`` (for the planned
trials). Importing that module runs ``collection/__init__``, so ``collection``
must not import ``fall_detection.session`` from its package ``__init__``.
"""

from .models import (
    RecordedAttempt,
    RecordedTrial,
    SessionBundle,
    SessionReadError,
    attempt_indices,
    load_session,
    read_json_object,
    scan_sessions,
    session_frames_directory,
)
from .schema import ARTIFACT_SCHEMA_VERSION
from .source import SessionSource

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "RecordedAttempt",
    "RecordedTrial",
    "SessionBundle",
    "SessionReadError",
    "SessionSource",
    "attempt_indices",
    "load_session",
    "read_json_object",
    "scan_sessions",
    "session_frames_directory",
]
