"""Version 2 sequence signals: one memory-mappable float32 array per segment."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import NamedTemporaryFile
from time import perf_counter

import numpy as np
import polars as pl

from .sequence_cache import array_directory, file_hash, read_segment

SCHEMA = "amplitude_sequence_v2"
FEATURES = 4 * 245


def _no_btrfs_compression(path: Path) -> bool:
    """Disable compression on a new file when its filesystem supports it."""
    if (
        subprocess.run(
            ["stat", "-f", "-c", "%T", str(path.parent)],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        != "btrfs"
    ):
        return False
    result = subprocess.run(
        ["btrfs", "property", "set", "-ti", str(path), "compression", "none"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise OSError(f"Cannot disable Btrfs compression for {path}: {result.stderr}")
    return True


def write_signal(path: Path, signal: np.ndarray) -> dict:
    """Publish a complete NPY atomically, with a hash and logical dimensions."""
    if signal.dtype != np.float32 or signal.ndim != 3 or signal.shape[1:] != (4, 245):
        raise ValueError("Expected float32 [time,4,245] signal")
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".npy", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        uncompressed = _no_btrfs_compression(temporary)
        with temporary.open("wb") as stream:
            np.save(stream, signal, allow_pickle=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(
        signal=str(path.relative_to(path.parent.parent)),
        samples=len(signal),
        bytes=path.stat().st_size,
        sha256=file_hash(path),
        btrfs_compression_disabled=uncompressed,
    )


def log_signal(raw: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Match the v1 training transform exactly at valid positions."""
    mask = np.asarray(valid, dtype=bool) & np.isfinite(raw)
    if np.any(raw[mask] < 0):
        raise ValueError("Negative squared difference")
    values = np.log1p(np.where(mask, raw, 0)).astype(np.float32)
    values[~mask] = np.nan
    return values


def _atomic_table(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        frame.write_parquet(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(value: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_export(
    source: Path,
    destination: Path,
    index: pl.DataFrame,
    segments: pl.DataFrame,
    signal_rows: list[dict],
    *,
    method: str,
    seconds: float,
    source_metadata: dict | None = None,
    parameters: dict | None = None,
) -> None:
    """Write metadata only after every signal has been published."""
    v1 = (
        json.loads((source / "manifest.json").read_text())
        if (source / "manifest.json").exists()
        else {}
    )
    if v1.get("schema") != "amplitude_sequence_v1":
        v1 = {}
    format_parameters = dict(parameters or v1.get("parameters") or {})
    for obsolete in (
        "max_windows_per_shard",
        "npy_storage_order",
        "compression",
        "bounded_writer_tasks",
        "writer_memory_budget_mb",
        "reload_verification",
    ):
        format_parameters.pop(obsolete, None)
    format_parameters.update(dtype="float32", tensor_order="time,receiver,subcarrier")
    ledger = pl.DataFrame(
        [{k: v for k, v in row.items() if k != "subcarriers"} for row in signal_rows]
    ).sort("segment_id")
    _atomic_table(index, destination / "window_index.parquet")
    _atomic_table(segments, destination / "segments.parquet")
    _atomic_table(ledger, destination / "signals.parquet")
    _atomic_json(
        dict(
            schema="amplitude_sequence" if method == "direct-preprocessing" else SCHEMA,
            dataset=destination.name,
            version=3 if format_parameters.get("target_hz") == 120 else 2,
            source=source_metadata or v1.get("source"),
            parameters=format_parameters,
            provenance=dict(
                method=method,
                v1_manifest_sha256=(
                    file_hash(source / "manifest.json") if v1 else None
                ),
                export_code_sha256={
                    name: file_hash(Path(__file__).with_name(name))
                    for name in ("sequence_segments.py", "sequence_preprocessing.py")
                },
            ),
            coordinates=dict(
                receivers=["rx-1", "rx-2", "rx-3", "rx-4"],
                subcarriers=signal_rows[0]["subcarriers"],
            ),
            representation="float32 log1p(squared_difference); NaN means invalid",
            labels=dict(
                fall=1,
                non_fall=0,
                rule="fall window center in action cue; other fall windows omitted",
            ),
            counts=dict(
                segments=len(ledger),
                windows=len(index),
                classes=index.group_by("duration", "target")
                .len()
                .sort("duration", "target")
                .to_dicts(),
            ),
            signal_bytes=int(ledger["bytes"].sum()),
            conversion_seconds=seconds,
            timings_seconds=dict(v1.get("timings_seconds", {}), v2_conversion=seconds),
            metadata_sha256={
                name: file_hash(destination / name)
                for name in (
                    "window_index.parquet",
                    "segments.parquet",
                    "signals.parquet",
                )
            },
        ),
        destination / "manifest.json",
    )


def migrate_v1_dataset(source: Path, destination: Path) -> dict:
    """Reconstruct each segment from v1 windows and reject overlap conflicts."""
    started = perf_counter()
    v1 = json.loads((source / "manifest.json").read_text())
    if v1.get("schema") != "amplitude_sequence_v1":
        raise ValueError("Expected a v1 export")
    index = pl.read_parquet(source / "window_index.parquet")
    segments = pl.read_parquet(source / "segments.parquet")
    ledger = []
    for segment in segments.iter_rows(named=True):
        selected = index.filter(pl.col("segment_id") == segment["segment_id"])
        if selected.is_empty():
            continue
        path = destination / "signals" / f"{segment['segment_id']}.npy"
        length = segment["samples"]
        signal = np.full((length, 4, 245), np.nan, dtype=np.float32)
        covered = np.zeros((length, 4, 245), dtype=bool)
        coordinates = None
        for part in selected.partition_by("shard", maintain_order=True):
            shard = source / part["shard"][0]
            with np.load(shard, allow_pickle=False) as arrays:
                raw = arrays["squared_difference"]
                valid = arrays["difference_valid"]
                targets = arrays["target"]
                current = (arrays["receivers"].tolist(), arrays["subcarriers"].tolist())
            if coordinates is None:
                coordinates = current
            elif coordinates != current:
                raise ValueError(f"Coordinates differ in {shard}")
            for row in part.iter_rows(named=True):
                position = row["shard_row"]
                if int(targets[position]) != row["target"]:
                    raise ValueError(f"Target differs in {shard}")
                if (
                    row["stop"] > length
                    or row["stop"] - row["start"] != row["duration"] * 96
                ):
                    raise ValueError(f"Window bounds differ in {shard}")
                values = log_signal(raw[position], valid[position])
                view = signal[row["start"] : row["stop"]]
                used = covered[row["start"] : row["stop"]]
                if not np.array_equal(view[used], values[used], equal_nan=True):
                    raise ValueError(f"Overlapping windows disagree: {shard}")
                view[~used] = values[~used]
                used[:] = True
        receipt = write_signal(path, signal)
        ledger.append(
            dict(
                segment_id=segment["segment_id"], **receipt, subcarriers=coordinates[1]
            )
        )
    if not ledger:
        raise ValueError("No indexed segments")
    new_index = index.drop("shard", "shard_row").with_columns(
        pl.col("segment_id")
        .map_elements(
            lambda identifier: f"signals/{identifier}.npy", return_dtype=pl.String
        )
        .alias("signal")
    )
    new_segments = segments.with_columns(
        pl.col("segment_id")
        .map_elements(
            lambda identifier: str(destination / "segments" / f"{identifier}.npz"),
            return_dtype=pl.String,
        )
        .alias("path")
    )
    publish_export(
        source,
        destination,
        new_index,
        new_segments,
        ledger,
        method="verified-v1-window-migration",
        seconds=perf_counter() - started,
    )
    preserve_v1_audit(source, destination)
    return dict(
        dataset=destination.name,
        segments=len(ledger),
        windows=len(index),
        seconds=perf_counter() - started,
        allocated_bytes=sum(
            (destination / row["signal"]).stat().st_blocks * 512 for row in ledger
        ),
    )


def export_cached_segments(
    source: Path,
    destination: Path,
    index: pl.DataFrame,
    segments: pl.DataFrame,
    *,
    source_metadata: dict,
    parameters: dict,
) -> dict:
    """Export v2 directly from preprocessing's retained per-segment arrays."""
    started, ledger = perf_counter(), []
    for segment in segments.iter_rows(named=True):
        if index.filter(pl.col("segment_id") == segment["segment_id"]).is_empty():
            continue
        with read_segment(segment["path"]) as arrays:
            signal = log_signal(
                arrays["squared_difference"], arrays["difference_valid"]
            )
            coordinates = (arrays["receivers"].tolist(), arrays["subcarriers"].tolist())
            presence = (
                arrays["capture_time_ns"] >= 0
                if parameters["target_hz"] == 120
                else None
            )
        path = destination / "signals" / f"{segment['segment_id']}.npy"
        if presence is not None:
            presence_path = (
                destination / "signals" / f"{segment['segment_id']}.presence.npy"
            )
            presence_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(presence_path, presence, allow_pickle=False)
        ledger.append(
            dict(
                segment_id=segment["segment_id"],
                **write_signal(path, signal),
                **(
                    {
                        "presence": str(presence_path.relative_to(destination)),
                        "presence_sha256": file_hash(presence_path),
                    }
                    if presence is not None
                    else {}
                ),
                subcarriers=coordinates[1],
            )
        )
    new_index = index.with_columns(
        pl.col("segment_id")
        .map_elements(
            lambda identifier: f"signals/{identifier}.npy", return_dtype=pl.String
        )
        .alias("signal")
    )
    publish_export(
        source,
        destination,
        new_index,
        segments,
        ledger,
        method="direct-preprocessing",
        seconds=perf_counter() - started,
        source_metadata=source_metadata,
        parameters=parameters,
    )
    return dict(
        dataset=destination.name,
        segments=len(ledger),
        windows=len(index),
        seconds=perf_counter() - started,
    )


def preserve_v1_audit(source: Path, destination: Path) -> None:
    """Retain review tables, figures and the representative audit segment."""
    for name in (
        "selection.parquet",
        "recordings.parquet",
        "alignment.parquet",
        "hampel.parquet",
        "differences.parquet",
        "window_counts.parquet",
    ):
        if (source / name).exists():
            shutil.copy2(source / name, destination / name)
    if (source / "reports").exists():
        if not (destination / "reports").exists():
            shutil.copytree(source / "reports", destination / "reports")
        shutil.copytree(
            source / "reports", destination / "reports" / "v1", dirs_exist_ok=True
        )
    segments = pl.read_parquet(source / "segments.parquet")
    for row in segments.filter(pl.col("cached")).iter_rows(named=True):
        old = array_directory(Path(row["path"]))
        new = array_directory(destination / "segments" / f"{row['segment_id']}.npz")
        if old.is_dir():
            shutil.copytree(old, new, dirs_exist_ok=True)
        elif Path(row["path"]).is_file():
            target = destination / "segments" / f"{row['segment_id']}.npz"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["path"], target)
    updated = segments.with_columns(
        pl.col("segment_id")
        .map_elements(
            lambda identifier: str(
                destination.resolve() / "segments" / f"{identifier}.npz"
            ),
            return_dtype=pl.String,
        )
        .alias("path")
    )
    _atomic_table(updated, destination / "segments.parquet")
    manifest_path = destination / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["metadata_sha256"]["segments.parquet"] = file_hash(
        destination / "segments.parquet"
    )
    for obsolete in (
        "max_windows_per_shard",
        "npy_storage_order",
        "compression",
        "bounded_writer_tasks",
        "writer_memory_budget_mb",
        "reload_verification",
    ):
        manifest["parameters"].pop(obsolete, None)
    manifest["parameters"].update(
        dtype="float32", tensor_order="time,receiver,subcarrier"
    )
    if "labels" not in manifest:
        manifest["labels"] = dict(
            fall=1,
            non_fall=0,
            rule="fall window center in action cue; other fall windows omitted",
        )
    if "classes" not in manifest["counts"]:
        index = pl.read_parquet(destination / "window_index.parquet")
        manifest["counts"]["classes"] = (
            index.group_by("duration", "target")
            .len()
            .sort("duration", "target")
            .to_dicts()
        )
    if "timings_seconds" not in manifest:
        source_manifest = json.loads((source / "manifest.json").read_text())
        manifest["timings_seconds"] = dict(
            source_manifest.get("timings_seconds", {}),
            v2_conversion=manifest["conversion_seconds"],
        )
    _atomic_json(manifest, manifest_path)


def verify_v2_dataset(source: Path, destination: Path) -> dict:
    """Compare every v2 window, mask, target and identifier against v1."""
    started = perf_counter()
    manifest = json.loads((destination / "manifest.json").read_text())
    if manifest["schema"] != SCHEMA or manifest["provenance"][
        "v1_manifest_sha256"
    ] != file_hash(source / "manifest.json"):
        raise ValueError("Source manifest differs")
    old = pl.read_parquet(source / "window_index.parquet")
    new = pl.read_parquet(destination / "window_index.parquet")
    expected = old.drop("shard", "shard_row").with_columns(
        pl.col("segment_id")
        .map_elements(
            lambda identifier: f"signals/{identifier}.npy", return_dtype=pl.String
        )
        .alias("signal")
    )
    if not expected.equals(new):
        raise ValueError("Window identifiers or metadata differ")
    ledger = pl.read_parquet(destination / "signals.parquet")
    checked = 0
    for segment in ledger.iter_rows(named=True):
        path = destination / segment["signal"]
        if (
            path.stat().st_size != segment["bytes"]
            or file_hash(path) != segment["sha256"]
        ):
            raise ValueError(f"Signal hash differs: {path}")
        signal = np.load(path, mmap_mode="r", allow_pickle=False)
        if signal.shape != (segment["samples"], 4, 245) or signal.dtype != np.float32:
            raise ValueError(f"Signal shape differs: {path}")
        selected = old.filter(pl.col("segment_id") == segment["segment_id"])
        for part in selected.partition_by("shard", maintain_order=True):
            with np.load(source / part["shard"][0], allow_pickle=False) as archive:
                raw = archive["squared_difference"]
                valid = archive["difference_valid"]
                targets = archive["target"]
                for row in part.iter_rows(named=True):
                    if int(targets[row["shard_row"]]) != row["target"]:
                        raise ValueError("Target differs")
                    old_values = log_signal(
                        raw[row["shard_row"]], valid[row["shard_row"]]
                    )
                    actual = signal[row["start"] : row["stop"]]
                    if not np.array_equal(old_values, actual, equal_nan=True):
                        raise ValueError(
                            f"Window values or validity differ: {row['segment_id']} {row['start']}"
                        )
                    checked += 1
    if checked != len(old):
        raise ValueError("Not every window was verified")
    return dict(
        dataset=destination.name,
        windows=checked,
        segments=len(ledger),
        seconds=perf_counter() - started,
        identical=True,
    )
