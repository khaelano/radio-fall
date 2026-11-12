"""Create a verified version-2 copy of a version-1 session archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

from fall_detection.storage.session_archive import verify_archive

_FORMAT = "fall-detection-session-archive"
_CHUNK = 1024 * 1024


def upgrade_archive(source: Path, destination: Path) -> dict:
    """Copy and validate every source member without modifying the raw archive.

    Args:
        source: Closed version-1 archive.
        destination: New derived archive, outside the source path.

    Returns:
        The verified version-2 manifest.

    Raises:
        FileExistsError: The destination already exists.
        ValueError: The source format, inventory, or member checksum is invalid.
    """
    source = source.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    raw_root = Path(__file__).resolve().parents[2] / "data/raw"
    if destination.is_relative_to(raw_root):
        raise ValueError("derived archives cannot be written under data/raw")
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = source.stat()
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    fd, name = tempfile.mkstemp(
        prefix=".archive-upgrade-", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(name)
    try:
        with (
            zipfile.ZipFile(source) as old,
            zipfile.ZipFile(temporary, "w", allowZip64=True) as new,
        ):
            names = old.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise ValueError("duplicate members or missing manifest")
            manifest_bytes = old.read("manifest.json")
            manifest = json.loads(manifest_bytes)
            if manifest.get("format") != _FORMAT or manifest.get("version") != 1:
                raise ValueError("expected a version-1 session archive")
            entries = manifest["files"] + manifest["tables"]
            declared = {entry["path"]: entry for entry in entries}
            if len(declared) != len(entries) or set(names) != set(declared) | {
                "manifest.json"
            }:
                raise ValueError("source archive inventory mismatch")
            for name, entry in declared.items():
                info = zipfile.ZipInfo(name)
                info.compress_type = old.getinfo(name).compress_type
                if info.compress_type == zipfile.ZIP_DEFLATED:
                    info._compresslevel = 1
                digest = hashlib.sha256()
                size = 0
                with (
                    old.open(name) as src,
                    new.open(info, "w", force_zip64=True) as dst,
                ):
                    while data := src.read(_CHUNK):
                        dst.write(data)
                        digest.update(data)
                        size += len(data)
                if size != entry["size"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError(f"source member checksum mismatch: {name}")
            manifest["version"] = 2
            manifest["normalized_from"] = {
                "archive_version": 1,
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            }
            new.writestr(
                "manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n"
            )
        after = source.stat()
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != identity:
            raise ValueError("source archive changed during conversion")
        verified = verify_archive(temporary)
        after = source.stat()
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != identity:
            raise ValueError("source archive changed during verification")
        os.link(temporary, destination)
        return verified
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    """Convert explicit source archives into a separate output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    for source in args.sources:
        destination = args.destination / source.name
        print(f"Converting {source} to {destination}", flush=True)
        manifest = upgrade_archive(source, destination)
        print(
            f"Verified {manifest['session_id']}: {len(manifest['files'])} files",
            flush=True,
        )


if __name__ == "__main__":
    main()
