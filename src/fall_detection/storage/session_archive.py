"""Verified ZIP64 raw storage of closed collection sessions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from .compressed import physical_path, open_binary, decoded_stream
from .tables import convert_csv_to_parquet

_FORMAT = "fall-detection-session-archive"
_TABLES = {"csi.csv", "radio_timing.csv", "usb_clock_sync.csv"}
_CHUNK = 1024 * 1024


def _inventory(root: Path) -> dict[str, tuple[int, int, int, int]]:
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f"symbolic link in session: {path}")
        for name in files:
            path = Path(directory) / name
            if not path.is_file():
                raise ValueError(f"not a regular file: {path}")
            stat = path.stat()
            result[path.relative_to(root).as_posix()] = (
                stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
            )
    return result


def _add_file(archive: zipfile.ZipFile, source: Path, name: str, method: int) -> dict:
    digest = hashlib.sha256()
    count = 0
    info = zipfile.ZipInfo(name)
    info.compress_type = method
    info._compresslevel = 1 if method == zipfile.ZIP_DEFLATED else None
    with source.open("rb") as src, archive.open(info, "w", force_zip64=True) as out:
        while data := src.read(_CHUNK):
            digest.update(data)
            count += len(data)
            out.write(data)
    return {"path": name, "size": count, "sha256": digest.hexdigest()}


def verify_archive(path: str | Path) -> dict:
    """Verify archive inventory and all member checksums; return its manifest."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or "manifest.json" not in names:
            raise ValueError("duplicate members or missing manifest")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != _FORMAT or manifest.get("version") not in {1, 2}:
            raise ValueError("unsupported archive format")
        entries = manifest["files"] + manifest["tables"]
        declared = []
        for entry in entries:
            name = entry["path"]
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith("/") or ".." in parts or "." in parts
                    or "\\" in name or name != PurePosixPath(name).as_posix()):
                raise ValueError("unsafe member path")
            declared.append(name)
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as stream:
                while data := stream.read(_CHUNK):
                    size += len(data)
                    digest.update(data)
            if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                raise ValueError(f"checksum mismatch: {name}")
        if len(set(declared)) != len(declared) or set(names) != set(declared) | {"manifest.json"}:
            raise ValueError("archive inventory mismatch")
        original = set()
        for entry in manifest["files"]:
            logical = entry.get("logical_path", entry["path"].removeprefix("original/"))
            if (not entry["path"].startswith("original/") or not logical
                    or logical.startswith("/") or "\\" in logical
                    or ".." in PurePosixPath(logical).parts
                    or logical != PurePosixPath(logical).as_posix()
                    or "original/" + logical in original):
                raise ValueError("invalid original path")
            original.add("original/" + logical)
            if entry.get("encoding") == "zstd":
                digest = hashlib.sha256()
                size = 0
                with archive.open(entry["path"]) as raw, decoded_stream(raw) as stream:
                    while data := stream.read(_CHUNK):
                        size += len(data)
                        digest.update(data)
                if size != entry["logical_size"] or digest.hexdigest() != entry["logical_sha256"]:
                    raise ValueError("logical checksum mismatch")
            elif entry.get("encoding") is not None:
                raise ValueError("unsupported member encoding")
        if "original/session.json" not in original:
            raise ValueError("missing session manifest")
        session = json.loads(archive.read("original/session.json"))
        if session.get("session_id") != manifest.get("session_id"):
            raise ValueError("session identity mismatch")
        for entry in manifest["tables"]:
            if not entry["path"].startswith("tables/") or "original/" + entry["source"] not in original:
                raise ValueError("invalid table mapping")
        return manifest


def create_archive(source: str | Path, destination: str | Path, *, progress=None) -> dict:
    """Export and fully verify a closed session without modifying its files."""
    events = physical_path(Path(source) / "events.jsonl")
    if not events.exists():
        return _create_archive(source, destination, progress=progress)
    with events.open("rb") as lock:
        if os.name == "posix":
            import fcntl

            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("session is open in another collector or exporter") from exc
        return _create_archive(source, destination, progress=progress)


def _create_archive(source: str | Path, destination: str | Path, *, progress=None) -> dict:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    if destination.is_relative_to(source):
        raise ValueError("destination must be outside the session")
    session = json.loads((source / "session.json").read_text(encoding="utf-8"))
    if session.get("artifact_schema_version") != 2 or session.get("status") in {None, "open", "recording"}:
        raise ValueError("expected a closed schema-2 session")
    initial = _inventory(source)
    manifest = {"format": _FORMAT, "version": 2 if any(p.endswith(".zst") for p in initial) else 1, "session_id": session["session_id"],
                "files": [], "tables": []}
    fd, name = tempfile.mkstemp(prefix=".session-archive-", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with tempfile.TemporaryDirectory(prefix=".table-", dir=destination.parent) as staging:
            table_path = Path(staging) / "table.parquet"
            with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
                for index, relative in enumerate(sorted(initial), 1):
                    path = source / relative
                    if progress:
                        progress(index, len(initial), relative)
                    method = zipfile.ZIP_STORED if path.suffix.lower() in {".mp4", ".zst"} else zipfile.ZIP_DEFLATED
                    entry = _add_file(archive, path, "original/" + relative, method)
                    logical = relative.removesuffix(".zst") if path.suffix == ".zst" else relative
                    if path.suffix == ".zst":
                        digest = hashlib.sha256()
                        size = 0
                        with open_binary(path) as decoded:
                            while data := decoded.read(_CHUNK):
                                digest.update(data)
                                size += len(data)
                        entry.update(encoding="zstd", logical_path=logical,
                                     logical_sha256=digest.hexdigest(), logical_size=size)
                    manifest["files"].append(entry)
                    if Path(logical).name in _TABLES and "receivers" in path.parts:
                        rows = convert_csv_to_parquet(path, table_path)
                        member = "tables/" + str(PurePosixPath(logical).with_suffix(".parquet"))
                        entry = _add_file(archive, table_path, member, zipfile.ZIP_STORED)
                        entry.update(source=logical, rows=rows)
                        manifest["tables"].append(entry)
                        table_path.unlink()
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        if _inventory(source) != initial:
            raise ValueError("session changed during export")
        verify_archive(temporary)
        if _inventory(source) != initial:
            raise ValueError("session changed during verification")
        os.link(temporary, destination)
        return manifest
    finally:
        temporary.unlink(missing_ok=True)
