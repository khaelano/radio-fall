"""Version 2 sequence signals: one memory-mappable float32 array per segment."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import polars as pl

from .sequence_cache import file_hash

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
    return {
        "signal": str(path.relative_to(path.parent.parent)),
        "samples": len(signal),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
        "btrfs_compression_disabled": uncompressed,
    }


def _atomic_table(frame: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and pl.read_parquet(path).equals(frame):
        return
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
    destination: Path,
    index: pl.DataFrame,
    segments: pl.DataFrame,
    signal_rows: list[dict],
    *,
    seconds: float,
    source_metadata: dict | None = None,
    parameters: dict | None = None,
) -> None:
    """Write metadata only after every signal has been published."""
    format_parameters = dict(parameters or {})
    format_parameters.update(dtype="float32", tensor_order="time,receiver,subcarrier")
    ledger = pl.DataFrame(
        [{k: v for k, v in row.items() if k != "subcarriers"} for row in signal_rows]
    ).sort("segment_id")
    _atomic_table(index, destination / "window_index.parquet")
    _atomic_table(segments, destination / "segments.parquet")
    _atomic_table(ledger, destination / "signals.parquet")
    _atomic_json(
        {
            "schema": "amplitude_sequence",
            "dataset": destination.name,
            "version": 3 if format_parameters.get("target_hz") == 120 else 2,
            "source": source_metadata,
            "parameters": format_parameters,
            "provenance": {
                "method": "direct-preprocessing",
                "export_code_sha256": {
                    name: file_hash(Path(__file__).with_name(name))
                    for name in ("sequence_segments.py", "sequence_preprocessing.py")
                },
            },
            "coordinates": {
                "receivers": ["rx-1", "rx-2", "rx-3", "rx-4"],
                "subcarriers": signal_rows[0]["subcarriers"],
            },
            "representation": format_parameters.get(
                "representation", "float32 log1p(squared_difference); NaN means invalid"
            ),
            "labels": {
                "fall": 1,
                "non_fall": 0,
                "rule": format_parameters.get(
                    "label_policy",
                    "fall window center in action cue; other fall windows omitted",
                ),
            },
            "counts": {
                "segments": len(ledger),
                "windows": len(index),
                "classes": index.group_by("duration", "target")
                .len()
                .sort("duration", "target")
                .to_dicts(),
            },
            "signal_bytes": int(ledger["bytes"].sum()),
            "conversion_seconds": seconds,
            "timings_seconds": {"v2_conversion": seconds},
            "metadata_sha256": {
                name: file_hash(destination / name)
                for name in (
                    "window_index.parquet",
                    "segments.parquet",
                    "signals.parquet",
                )
            },
        },
        destination / "manifest.json",
    )
