"""Fingerprints that decide whether cached analysis results are still valid."""

import hashlib
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

from .session_frames import AnalysisSession

_FRAME_TABLE_FILES = (
    "conversion.json",
    "frames.parquet",
    "attempts.parquet",
    "phases.parquet",
)


def frame_signature(session: AnalysisSession) -> list:
    """Describe the converted frame tables of a session by path, size and times.

    Args:
        session: Analysis session whose converted tables are inspected.

    Returns:
        A JSON-serializable list with one entry per frame table file, followed
        by the source fingerprint of the analysis session (which also changes
        with review decisions and protocol edits).
    """
    values: list = []
    for name in _FRAME_TABLE_FILES:
        path = session.path / name
        if path.is_file():
            stat = path.stat()
            values.append([str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns])
        else:
            values.append([str(path), None])
    values.append(str(session.manifest.get("source_fingerprint", "")))
    return values


def code_hash(modules: Iterable[ModuleType], *extra: str | Path) -> str:
    """Hash the source files of the modules an analysis result depends on.

    Args:
        modules: Imported modules whose source files are hashed.
        *extra: Additional source files, usually the caller's own ``__file__``.

    Returns:
        A hexadecimal SHA-256 digest.
    """
    sources = [Path(str(module.__file__)) for module in modules]
    sources.extend(Path(path) for path in extra)
    return hashlib.sha256(b"".join(path.read_bytes() for path in sources)).hexdigest()


def raw_root_of(session: AnalysisSession) -> Path:
    """Return the raw data tree that derived caches must stay outside of."""
    source = Path(str(session.manifest["source_directory"]))
    return source.parent.parent if source.parent.name == "sessions" else source
