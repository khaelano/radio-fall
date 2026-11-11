"""Shared access to raw session archives and legacy session directories."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile
from typing import BinaryIO, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    import pyarrow as pa

from .compressed import open_binary, decoded_stream
from .session_archive import _inventory, verify_archive


class Recording:
    """Open a recording, verifying archive checksums before exposing its files.

    Use as a context manager. Paths passed to methods are relative to the
    original session root, without the archive's ``original/`` prefix.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.manifest = None if self.path.is_dir() else verify_archive(self.path)
        self._zip = None if self.manifest is None else zipfile.ZipFile(self.path)
        self.files = tuple(sorted(p.removesuffix(".zst") for p in _inventory(self.path))) if self.manifest is None else tuple(
            entry.get("logical_path", entry["path"].removeprefix("original/")) for entry in self.manifest["files"]
        )

    def __enter__(self) -> Recording:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close archive resources."""
        if self._zip:
            self._zip.close()

    @contextmanager
    def open(self, relative: str) -> Iterator[BinaryIO]:
        """Yield a binary stream for one original file."""
        if relative not in self.files:
            raise FileNotFoundError(relative)
        if self._zip:
            entry = next(e for e in self.manifest["files"] if e.get("logical_path", e["path"].removeprefix("original/")) == relative)
            with self._zip.open(entry["path"]) as stream:
                if entry.get("encoding") == "zstd":
                    with decoded_stream(stream) as decoded:
                        yield decoded
                else:
                    yield stream
        else:
            with open_binary(self.path / relative) as stream:
                yield stream

    def read_json(self, relative: str = "session.json") -> dict:
        """Read an original JSON document."""
        with self.open(relative) as stream:
            return json.load(stream)

    def read_table(self, relative: str, *, columns: list[str] | None = None) -> pa.Table:
        """Read a CSV's Parquet representation as an Arrow table of strings.

        Legacy CSV inputs use the same lossless string column contract.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq
        import csv
        import io

        if self.manifest:
            entry = next((e for e in self.manifest["tables"] if e["source"] == relative), None)
            if entry:
                with self._zip.open(entry["path"]) as stream:
                    return pq.read_table(stream, columns=columns)
        with self.open(relative) as stream:
            reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8", newline=""), strict=True)
            header = next(reader)
            rows = list(reader)
        if any(len(row) != len(header) for row in rows):
            raise ValueError("CSV row does not match header")
        table = pa.Table.from_arrays([
            pa.array([row[i] for row in rows], type=pa.string()) for i in range(len(header))
        ], names=header)
        return table.select(columns) if columns is not None else table

    def compare_source(self, source: str | Path) -> dict:
        """Verify exact file inventory and bytes against an original directory."""
        source = Path(source)
        before = _inventory(source)
        if {p.removesuffix(".zst") for p in before} != set(self.files):
            raise ValueError("source file inventory differs")
        total = 0
        for relative in self.files:
            with self.open(relative) as archived, open_binary(source / relative) as original:
                while True:
                    data = original.read(1024 * 1024)
                    other = archived.read(len(data) if data else 1)
                    if data != other:
                        raise ValueError(f"source bytes differ: {relative}")
                    if not data:
                        break
                    total += len(data)
        if before != _inventory(source):
            raise ValueError("source changed during comparison")
        return {"files": len(self.files), "bytes": total}

    def extract(self, destination: str | Path, *, members: list[str] | None = None) -> Path:
        """Atomically extract exact originals into a new directory.

        Extracted bytes are checked against archive hashes before publication.
        """
        destination = Path(destination).absolute()
        selected = self.files if members is None else tuple(members)
        if not set(selected).issubset(self.files):
            raise FileNotFoundError("unknown extraction member")
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".recording-extract-", dir=destination.parent) as tmp:
            staging = Path(tmp) / "session"
            staging.mkdir()
            hashes = {e.get("logical_path", e["path"].removeprefix("original/")): e.get("logical_sha256", e["sha256"]) for e in self.manifest["files"]} if self.manifest else {}
            for relative in selected:
                parts = PurePosixPath(relative).parts
                if not parts or any(p in {".", ".."} for p in parts) or relative.startswith("/"):
                    raise ValueError("unsafe recording path")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with self.open(relative) as src, target.open("xb") as dst:
                    while data := src.read(1024 * 1024):
                        dst.write(data)
                        digest.update(data)
                if hashes and digest.hexdigest() != hashes[relative]:
                    raise ValueError(f"extraction checksum mismatch: {relative}")
            if destination.exists():
                raise FileExistsError(destination)
            staging.rename(destination)
        return destination
