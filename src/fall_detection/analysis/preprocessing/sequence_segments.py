"""Version 2 sequence signals: one memory-mappable float32 array per segment."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import polars as pl

from .. import _cache_keys, _io
from .._cache_keys import file_hash
from .._io import atomic_json, atomic_table, temporary_sibling
from . import sequence_preprocessing

FEATURES = 4 * 245


def export_code_hashes() -> dict[str, str]:
    """Hash the source files that define the exported sequence format.

    The files are located through their imported modules, so the digests stay
    correct wherever the modules live in the package tree.

    Returns:
        File name to SHA-256 digest for the segment writer, the preprocessing
        module, and the shared I/O and cache-key helpers.
    """
    modules = (sys.modules[__name__], sequence_preprocessing, _io, _cache_keys)
    return {
        Path(str(module.__file__)).name: file_hash(Path(str(module.__file__)))
        for module in modules
    }


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
    with temporary_sibling(path, ".npy") as temporary:
        # Compression must be disabled before any bytes are written to the file.
        uncompressed = _no_btrfs_compression(temporary)
        with temporary.open("wb") as stream:
            np.save(stream, signal, allow_pickle=False)
    return {
        "signal": str(path.relative_to(path.parent.parent)),
        "samples": len(signal),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
        "btrfs_compression_disabled": uncompressed,
    }


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
    atomic_table(index, destination / "window_index.parquet", skip_if_equal=True)
    atomic_table(segments, destination / "segments.parquet", skip_if_equal=True)
    atomic_table(ledger, destination / "signals.parquet", skip_if_equal=True)
    atomic_json(
        {
            "schema": "amplitude_sequence",
            "dataset": destination.name,
            "version": 3 if format_parameters.get("target_hz") == 120 else 2,
            "source": source_metadata,
            "parameters": format_parameters,
            "provenance": {
                "method": "direct-preprocessing",
                "export_code_sha256": export_code_hashes(),
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
