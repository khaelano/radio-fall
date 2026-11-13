"""Atomic publication of derived files: write a sibling temporary file, then replace.

Readers see either the previous complete file or the new complete file, never a
partial one. Temporary files are created in the destination directory so that
``os.replace`` stays on one filesystem.
"""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import mkstemp
from typing import IO, Any

import polars as pl


@contextmanager
def temporary_sibling(path: Path, suffix: str = ".tmp") -> Iterator[Path]:
    """Yield a fresh empty temporary path beside ``path`` and publish it on success.

    The caller writes the temporary file and closes it before leaving the block.
    If the block raises, ``path`` is left unchanged. The temporary file is always
    removed when it still exists.

    Args:
        path: Destination file; its parent directory is created when missing.
        suffix: Suffix for the temporary name, which some writers require.

    Yields:
        Path of the temporary file, which exists and is empty.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = mkstemp(dir=path.parent, suffix=suffix)
    os.close(descriptor)
    temporary = Path(name)
    try:
        yield temporary
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_bytes(path: Path, data: bytes) -> None:
    """Publish raw bytes to ``path`` atomically.

    Args:
        path: Destination file.
        data: Complete file contents.
    """
    with temporary_sibling(path) as temporary:
        temporary.write_bytes(data)


def atomic_write(
    path: Path, write: Callable[[IO[bytes]], object], *, suffix: str = ".tmp"
) -> None:
    """Publish a file produced by a binary-stream writer, such as NumPy or ZipFile.

    Args:
        path: Destination file.
        write: Callable that writes the complete contents to the open stream.
        suffix: Suffix for the temporary name.
    """
    with temporary_sibling(path, suffix) as temporary, temporary.open("wb") as stream:
        write(stream)


def atomic_json(value: Any, path: Path) -> None:
    """Publish indented UTF-8 JSON with a trailing newline.

    Args:
        value: JSON-serializable object.
        path: Destination file.
    """
    atomic_bytes(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))


def atomic_table(
    frame: pl.DataFrame, path: Path, *, skip_if_equal: bool = False
) -> None:
    """Publish a Parquet table atomically.

    Args:
        frame: Table to write.
        path: Destination Parquet file.
        skip_if_equal: Leave an existing file untouched when it already holds an
            equal table, so its modification time and hash stay stable.
    """
    if skip_if_equal and path.is_file() and pl.read_parquet(path).equals(frame):
        return
    with temporary_sibling(path, ".parquet") as temporary:
        frame.write_parquet(temporary)
