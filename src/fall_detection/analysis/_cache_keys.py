"""Hashes and fingerprints that identify derived results and decide cache validity.

Shared by checkpointed sequence preprocessing, integrity scans, and phase-motion
caches so that every cache key is computed the same way.
"""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session_frames import AnalysisSession

_FRAME_TABLE_FILES = (
    "conversion.json",
    "frames.parquet",
    "attempts.parquet",
    "phases.parquet",
)


def fingerprint(value: object) -> str:
    """Hash small provenance metadata, never signal arrays.

    Args:
        value: JSON-serializable metadata; mapping key order does not matter.

    Returns:
        A hexadecimal SHA-256 digest of the canonical JSON encoding.
    """
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def stamp(path: Path) -> dict:
    """Identify an unchanged local file without reading its contents.

    Args:
        path: Existing file.

    Returns:
        Size, modification time, inode, and device of the file.
    """
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino,
        "device": stat.st_dev,
    }


def file_hash(path: Path) -> str:
    """Stream an encoded-file checksum without decompressing it.

    Args:
        path: Existing file.

    Returns:
        A hexadecimal SHA-256 digest of the file bytes.
    """
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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


def frame_signature(session: "AnalysisSession") -> list:
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


def cache_entry(
    parts: list, identity: str, cache: Path | None, suffix: str
) -> tuple[str, Path | None]:
    """Derive the validity fingerprint and the file location of one cache entry.

    Args:
        parts: JSON-serializable values that must match for a cached result to be
            reused, such as code hash, frame signature, and parameters.
        identity: Stable text naming the cached unit, such as session path,
            attempt, and receiver. The file name is its SHA-256 digest.
        cache: Cache directory, or ``None`` to disable caching.
        suffix: File suffix of the entry, including the dot.

    Returns:
        The fingerprint of ``parts`` and the entry path, or ``None`` without a cache.
    """
    key = fingerprint(parts)
    if cache is None:
        return key, None
    name = hashlib.sha256(identity.encode()).hexdigest()
    return key, cache / f"{name}{suffix}"


def raw_root_of(session: "AnalysisSession") -> Path:
    """Return the raw data tree that derived caches must stay outside of.

    Args:
        session: Analysis session whose manifest names its source directory.

    Returns:
        The raw archive root for sessions under ``sessions/``, else the source.
    """
    source = Path(str(session.manifest["source_directory"]))
    return source.parent.parent if source.parent.name == "sessions" else source
