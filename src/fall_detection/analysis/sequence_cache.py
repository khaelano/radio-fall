"""Cheap checkpoints and uncompressed, memory-mapped preprocessing storage."""

import json
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from ._cache_keys import file_hash, fingerprint, stamp
from ._io import atomic_json, temporary_sibling

__all__ = [
    "checkpoint_stage",
    "file_hash",
    "fingerprint",
    "read_segment",
    "restore_stage",
    "save_segment",
    "stamp",
]


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
        with (
            temporary_sibling(target, ".tmp") as temporary,
            temporary.open("wb") as stream,
        ):
            np.lib.format.write_array(stream, np.asarray(value), allow_pickle=False)


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
    atomic_json(
        {"key": key, "tables": tables, "files": {str(p): stamp(p) for p in files}},
        output / ".cache" / f"{name}.json",
    )
