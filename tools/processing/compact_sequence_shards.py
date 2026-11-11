"""Losslessly compact completed sequence NPZ shards and refresh their metadata."""

import argparse
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from zipfile import ZIP_LZMA, ZipFile

import polars as pl

from fall_detection.analysis.sequence_preprocessing import atomic_json, atomic_table


def _digest_members(path: Path) -> dict[str, str]:
    result = {}
    with ZipFile(path) as archive:
        for name in archive.namelist():
            digest = hashlib.sha256()
            with archive.open(name) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[name] = digest.hexdigest()
    return result


def compact_shard(path: Path) -> dict:
    """Atomically replace a shard only if smaller and every NPY byte agrees."""
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    before = _digest_members(path)
    with NamedTemporaryFile(
        dir=path.parent, prefix=".repack-", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        with (
            ZipFile(path) as source,
            ZipFile(temporary, "w", compression=ZIP_LZMA) as target,
        ):
            for name in source.namelist():
                with (
                    source.open(name) as incoming,
                    target.open(name, "w", force_zip64=True) as outgoing,
                ):
                    for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                        outgoing.write(chunk)
        if _digest_members(temporary) != before:
            raise ValueError(f"Uncompressed NPY member changed: {path}")
        saving = path.stat().st_size - temporary.stat().st_size
        if saving > 0:
            os.replace(temporary, path)
        else:
            saving = 0
        return dict(
            path=str(path),
            saved_bytes=saving,
            bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            original_sha256=original_hash,
            array_member_sha256=before,
            compression="zip_lzma" if saving else "zip_deflate",
        )
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    """Compact the largest completed shards across the given dataset directories."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", type=Path, nargs="+")
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.limit < 1 or not 1 <= args.workers <= 6:
        parser.error("limit must be positive and workers between one and six")
    started = perf_counter()
    manifests, tables, candidates = {}, {}, []
    for directory in args.datasets:
        root = directory.resolve()
        manifest = json.loads((root / "manifest.json").read_text())
        if manifest.get("schema") != "amplitude_sequence_v1":
            raise ValueError(f"Unexpected dataset schema: {root}")
        manifests[root] = manifest
        tables[root] = pl.read_parquet(root / "shards.parquet")
        for row in tables[root].iter_rows(named=True):
            path = root / row["shard"]
            if path.resolve().parent.parent != root:
                raise ValueError(
                    "Shard must stay inside its dataset duration directory"
                )
            with ZipFile(path) as archive:
                already_compact = all(
                    entry.compress_type == ZIP_LZMA for entry in archive.infolist()
                )
            if not already_compact:
                candidates.append(path)
    candidates.sort(key=lambda p: (-p.stat().st_size, str(p)))
    outcomes = {}
    with ThreadPoolExecutor(
        max_workers=args.workers, thread_name_prefix="npz-compact"
    ) as workers:
        for number, outcome in enumerate(
            workers.map(compact_shard, candidates[: args.limit]), 1
        ):
            outcomes[Path(outcome["path"])] = outcome
            if number % 10 == 0 or number == min(args.limit, len(candidates)):
                print(
                    f"Compacted {number}/{min(args.limit, len(candidates))}; "
                    f"saved {sum(r['saved_bytes'] for r in outcomes.values()) / 2**20:.1f} MiB",
                    flush=True,
                )
    for root, manifest in manifests.items():
        rows = []
        changed = []
        for row in tables[root].iter_rows(named=True):
            path = root / row["shard"]
            outcome = outcomes.get(path)
            with ZipFile(path) as archive:
                row["compression"] = (
                    "zip_lzma"
                    if all(i.compress_type == ZIP_LZMA for i in archive.infolist())
                    else "zip_deflate"
                )
            if not outcome and row["compression"] == "zip_lzma":
                size = path.stat().st_size
                outcome = dict(
                    bytes=size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    original_sha256=row["sha256"],
                    saved_bytes=max(0, row["bytes"] - size),
                    array_member_sha256=_digest_members(path),
                    compression="zip_lzma",
                )
            if outcome:
                row.update(bytes=outcome["bytes"], sha256=outcome["sha256"])
                changed.append(
                    dict(
                        shard=row["shard"],
                        **{k: v for k, v in outcome.items() if k != "path"},
                    )
                )
            rows.append(row)
        atomic_table(pl.DataFrame(rows), root / "shards.parquet")
        manifest["shards"] = rows
        manifest["parameters"]["compression"] = (
            "deflate level 6 and lossless ZIP_LZMA; see per-shard compression"
        )
        manifest["artifact_compaction"] = dict(
            tool="tools/processing/compact_sequence_shards.py",
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            verification="SHA256 of every uncompressed NPY member before and after; exact header, shape, dtype, storage order and values",
            saved_bytes=sum(row["saved_bytes"] for row in changed),
            shards=changed,
        )
        manifest["timings_seconds"]["artifact_compaction_batch"] = (
            perf_counter() - started
        )
        atomic_json(manifest, root / "manifest.json")
        print(root.name, "metadata refreshed", flush=True)


if __name__ == "__main__":
    main()
