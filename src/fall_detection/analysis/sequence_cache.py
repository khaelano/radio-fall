"""Cheap checkpoints and uncompressed, memory-mapped preprocessing storage."""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np


def fingerprint(value: object) -> str:
    """Hash small provenance metadata, never signal arrays."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def stamp(path: Path) -> dict:
    """Identify an unchanged local file without reading its contents."""
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": stat.st_ino,
        "device": stat.st_dev,
    }


def file_hash(path: Path) -> str:
    """Stream an encoded-file checksum without decompressing it."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def read_segment(path: str | Path):
    """Map the current directory of NPY arrays without decompression."""
    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(f"segment directory not found: {directory}")
    yield {
        p.stem: np.load(p, mmap_mode="r", allow_pickle=False)
        for p in directory.glob("*.npy")
    }


def save_segment(path: Path, arrays: dict) -> None:
    """Atomically write only new arrays; retain existing read-only memory maps."""
    directory = path
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


def restore_stage(output: Path, name: str, key: str) -> dict | None:
    """Restore metadata tables only when every checkpointed file is unchanged."""
    import polars as pl

    try:
        receipt = json.loads((output / ".cache" / f"{name}.json").read_text())
        if receipt["key"] != key or not all(
            stamp(Path(p)) == expected for p, expected in receipt["files"].items()
        ):
            return None
        return {
            attribute: pl.read_parquet(output / filename)
            for attribute, filename in receipt["tables"].items()
        }
    except (OSError, ValueError, KeyError):
        return None


def checkpoint_stage(
    output: Path, name: str, key: str, tables: dict, files: list[Path]
) -> None:
    """Publish a receipt after all stage arrays and tables have been written."""
    from .sequence_preprocessing import atomic_json

    atomic_json(
        {"key": key, "tables": tables, "files": {str(p): stamp(p) for p in files}},
        output / ".cache" / f"{name}.json",
    )
