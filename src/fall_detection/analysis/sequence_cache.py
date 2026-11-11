"""Cheap checkpoints and uncompressed, memory-mapped preprocessing storage."""

import hashlib
import json
import os
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np


def fingerprint(value: object) -> str:
    """Hash small provenance metadata, never signal arrays."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def stamp(path: Path) -> dict:
    """Identify an unchanged local file without reading its contents."""
    stat = path.stat()
    return dict(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        inode=stat.st_ino,
        device=stat.st_dev,
    )


def file_hash(path: Path) -> str:
    """Stream an encoded-file checksum without decompressing it."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def array_directory(path: Path) -> Path:
    """Locate a new array store, including legacy NPZ migration paths."""
    return path.with_suffix(".arrays") if path.suffix == ".npz" else path


@contextmanager
def read_segment(path: str | Path):
    """Map NPY files without decompression; support existing NPZ fixtures/reports."""
    path = Path(path)
    directory = array_directory(path)
    if directory.is_dir():
        yield {
            p.stem: np.load(p, mmap_mode="r", allow_pickle=False)
            for p in directory.glob("*.npy")
        }
    else:
        with np.load(path, allow_pickle=False) as data:
            yield data


def save_segment(path: Path, arrays: dict) -> None:
    """Atomically write only new arrays; retain existing read-only memory maps."""
    directory = array_directory(path)
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in arrays.items():
        target = directory / f"{name}.npy"
        if (
            isinstance(value, np.memmap)
            and value.filename is not None
            and Path(value.filename).resolve() == target.resolve()
        ):
            continue
        with NamedTemporaryFile(dir=directory, suffix=".npy", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with temporary.open("wb") as stream:
                np.lib.format.write_array(stream, np.asarray(value), allow_pickle=False)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def stage_cache(name: str, tables: dict[str, str], keys: tuple[str, ...] = ()):
    """Cache stage results using source/parameter keys and output file stamps."""

    def decorate(function):
        @wraps(function)
        def cached(self):
            if self._completed_cache_valid():
                self.cache_hits.append(name)
                return self._stage_summary(name)
            key = self._processing_key()
            checkpoint = self.output / ".cache" / f"{name}.json"
            try:
                receipt = json.loads(checkpoint.read_text())
                valid = receipt["key"] == key and all(
                    stamp(Path(p)) == expected
                    for p, expected in receipt["files"].items()
                )
            except (OSError, ValueError, KeyError):
                valid = False
            if valid:
                import polars as pl

                for attribute, filename in tables.items():
                    setattr(self, attribute, pl.read_parquet(self.output / filename))
                self.cache_hits.append(name)
                return self._stage_summary(name)
            result = function(self)
            files = [self.output / filename for filename in tables.values()]
            if keys:
                for segment in self.segments.iter_rows(named=True):
                    path = Path(segment["path"])
                    directory = array_directory(path)
                    files.extend(
                        directory / f"{k}.npy" for k in keys
                    ) if directory.is_dir() else files.append(path)
            from .sequence_preprocessing import atomic_json

            atomic_json(
                dict(key=key, files={str(p): stamp(p) for p in files}), checkpoint
            )
            return result

        return cached

    return decorate
