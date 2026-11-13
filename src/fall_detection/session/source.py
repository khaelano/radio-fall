"""Read a recorded session from a directory or a version-3 archive alike.

A directory is read with plain file access. An archive is read in place through
the Rust ``radio_storage`` library: manifests come straight from the archive and
nothing is extracted, except a single media file when a reader needs a real file
(see :meth:`SessionSource.materialize`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .._radio_native import (
    storage_extract_member,
    storage_files,
    storage_read,
    storage_read_file,
    storage_read_many,
    storage_source_fingerprint,
)

_ATTEMPT_DIRECTORY = re.compile(r"^(trials/[^/]+/attempt_[^/]+)(?:/|$)")


@lru_cache(maxsize=8)
def _listing(path: str, size: int, modified_ns: int) -> frozenset[str]:
    """List an archive's logical files; the key makes a changed archive miss."""
    return frozenset(storage_files(path))


@dataclass(frozen=True)
class SessionSource:
    """Where a session's files live: a directory or an archive.

    Paths passed to the methods are relative to the session root, with ``/``
    separators and without any ``original/`` wrapper.
    """

    path: Path
    _fingerprint: list[str] = field(default_factory=list, repr=False, compare=False)
    _loaded: dict[str, bytes] = field(default_factory=dict, repr=False, compare=False)

    @property
    def is_archive(self) -> bool:
        """Return whether the session is stored as an archive file."""
        return self.path.is_file()

    @property
    def name(self) -> str:
        """Return the session's folder name, or the archive name without ``.zip``."""
        return self.path.stem if self.is_archive else self.path.name

    def _files(self) -> frozenset[str]:
        stat = self.path.stat()
        return _listing(str(self.path), stat.st_size, stat.st_mtime_ns)

    def exists(self, relative: str) -> bool:
        """Return whether the file exists."""
        if self.is_archive:
            return relative in self._files()
        path = self.path / relative
        return path.is_file() or path.with_name(path.name + ".zst").is_file()

    def read_bytes(self, relative: str) -> bytes:
        """Read a file's decoded bytes.

        A directory file stored as ``<name>.zst`` is decoded like a plain one.

        Raises:
            OSError: If the file cannot be read.
        """
        if not self.is_archive:
            try:
                return storage_read_file(self.path / relative)
            except RuntimeError as exc:
                raise OSError(str(exc)) from exc
        if relative in self._loaded:
            return self._loaded[relative]
        try:
            return storage_read(str(self.path), relative)
        except RuntimeError as exc:
            raise OSError(str(exc)) from exc

    def prefetch(self, relatives: list[str]) -> None:
        """Read many small files of an archive with one open of it.

        Later reads of these files come from memory. Opening an archive lists its
        whole directory, so loading hundreds of manifests one by one is slow.
        Directories read files directly and ignore this call.
        """
        if self.is_archive and relatives:
            self._loaded.update(storage_read_many(str(self.path), list(relatives)))

    def read_text(self, relative: str) -> str:
        """Read a UTF-8 file."""
        return self.read_bytes(relative).decode("utf-8")

    def attempt_keys(self) -> list[str]:
        """Return the relative directory of every attempt, sorted."""
        if self.is_archive:
            keys = {
                match.group(1)
                for name in self._files()
                if (match := _ATTEMPT_DIRECTORY.match(name))
            }
        else:
            keys = {
                item.relative_to(self.path).as_posix()
                for item in (self.path / "trials").glob("*/attempt_*")
                if item.is_dir()
            }
        return sorted(keys)

    def fingerprint(self) -> str:
        """Return a cheap identity of the archive, used to key extracted media."""
        if not self._fingerprint:
            self._fingerprint.append(storage_source_fingerprint(str(self.path)))
        return self._fingerprint[0]

    def materialize(self, relative: str, cache_dir: Path) -> Path:
        """Return a real file for ``relative``, extracting it only when needed.

        A directory session returns its own file; when only ``<name>.zst`` is
        stored, the decoded file is written under ``cache_dir`` instead. An
        archive session writes just this one member under ``cache_dir`` and
        reuses it on later calls. The cache path includes the source
        fingerprint, so a changed session never reuses a stale file.

        Args:
            relative: File relative to the session root.
            cache_dir: Directory that may hold extracted media.

        Returns:
            The path of a readable file.

        Raises:
            OSError: If the member is missing or cannot be written.
        """
        if not self.is_archive:
            plain = self.path / relative
            if plain.is_file() or not self.exists(relative):
                return plain
            target = cache_dir / self.fingerprint()[:16] / relative
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                partial = target.with_name(target.name + ".partial")
                partial.write_bytes(self.read_bytes(relative))
                partial.replace(target)
            return target
        target = cache_dir / self.fingerprint()[:16] / relative
        if not target.is_file():
            try:
                storage_extract_member(str(self.path), relative, str(target))
            except RuntimeError as exc:
                raise OSError(str(exc)) from exc
        return target
