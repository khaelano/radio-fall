"""Bounded, columnar amplitude preprocessing from Parquet to atomic NPZ files."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import polars as pl
import pyarrow.parquet as pq

from .amplitude import hampel_subcarriers

COLUMNS = [
    "attempt_key", "attempt_id", "receiver_id", "is_sensing", "time_source",
    "time_seconds", "capture_time_ns", "phase", "driver_valid",
    "sig_mode", "bandwidth", "stbc", "first_word", "len", "csi_i", "csi_q",
    "attempt_started_monotonic_ns",
]


@dataclass(frozen=True)
class AmplitudeSession:
    """Validated shared export with Polars selection tables."""

    path: Path
    manifest: dict
    attempts: pl.DataFrame


def load_amplitude_session(
    raw_dir: str | Path, parquet_dir: str | Path, *, progress=print,
) -> AmplitudeSession:
    """Validate/reuse the shared export and load the preprocessing table in Polars."""
    from .session_parquet import SCHEMA_VERSION, _source_fingerprint, load_parquet_session
    from ..session_inspector.models import load_session

    raw_dir, parquet_dir = Path(raw_dir), Path(parquet_dir).resolve()
    if raw_dir.is_file():
        manifest = load_parquet_session(raw_dir, parquet_dir, progress=progress).manifest
        return AmplitudeSession(parquet_dir, manifest, pl.read_parquet(parquet_dir / "attempts.parquet"))
    raw_session = load_session(raw_dir)
    raw_root = (raw_session.path.parent.parent
                if raw_session.path.parent.name == "sessions" else raw_session.path)
    if parquet_dir.is_relative_to(raw_root):
        raise ValueError("Place Parquet exports outside raw session data")
    if raw_session.active:
        raise ValueError("Parquet export requires a closed session")
    try:
        manifest = json.loads((parquet_dir / "session.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    if not (
        manifest.get("schema_version") == SCHEMA_VERSION
        and manifest.get("source_fingerprint") == _source_fingerprint(raw_session)
        and all((parquet_dir / name).is_file() for name in (
            "attempts.parquet", "phases.parquet", "packets.parquet",
        ))
    ):
        # Keep the shared raw CSV exporter as the only cache writer. Existing
        # valid exports take the Polars path without materializing pandas tables.
        manifest = load_parquet_session(raw_dir, parquet_dir, progress=progress).manifest
    return AmplitudeSession(
        parquet_dir, manifest, pl.read_parquet(parquet_dir / "attempts.parquet"),
    )


@dataclass(frozen=True)
class AmplitudeRecording:
    """One receiver's masked and scaled physical HE20 subcarrier matrices."""

    metadata: pl.DataFrame
    masked: np.ndarray
    normalized: np.ndarray | None
    lower: np.ndarray
    upper: np.ndarray

    @property
    def time_seconds(self) -> np.ndarray:
        """Return capture-relative times without synthesizing missing packets."""
        return self.metadata["time_seconds"].to_numpy()

    @property
    def subcarriers(self) -> np.ndarray:
        """Return signed physical indices, including masked null subcarriers."""
        return np.arange(-122, 123)


class AmplitudePacketReader:
    """Reuse Parquet metadata and read only candidate row groups and columns."""

    def __init__(self, path: str | Path, *, columns: list[str] | None = None):
        self.columns = COLUMNS if columns is None else columns
        self.path = Path(path)
        self.file = pq.ParquetFile(self.path)
        names = self.file.schema.names
        self.groups = {}
        self.unknown = []
        for index in range(self.file.num_row_groups):
            group = self.file.metadata.row_group(index)
            key = []
            for name in ("attempt_key", "receiver_id"):
                stats = group.column(names.index(name)).statistics
                if stats is None or not stats.has_min_max or stats.min != stats.max or stats.null_count:
                    break
                key.append(stats.min)
            if len(key) == 2:
                self.groups.setdefault(tuple(key), []).append(index)
            else:
                self.unknown.append(index)

    def read(self, attempt_key: str, receiver_id: str) -> pl.DataFrame:
        """Read one recording, also supporting mixed/unknown row-group statistics."""
        groups = sorted(self.groups.get((attempt_key, receiver_id), []) + self.unknown)
        table = self.file.read_row_groups(groups, columns=self.columns, use_threads=False)
        return pl.from_arrow(table).filter(
            (pl.col("attempt_key") == attempt_key) & (pl.col("receiver_id") == receiver_id)
        )

    def close(self) -> None:
        """Close the reusable Parquet file."""
        self.file.close()


def prepare_recording(packets: pl.DataFrame, *, magnitude_only: bool = False) -> AmplitudeRecording:
    """Decode, physically align, mask and normalize a recording in Rust.

    Args:
        packets: Polars rows from the enriched session Parquet contract.
        magnitude_only: Skip normalization; normalized is None and extrema empty.

    Returns:
        Masked and normalized float64 matrices and aligned sensing metadata.

    Raises:
        ValueError: Mixed identities, unsupported layouts or corrupt payloads/times.
    """
    from fall_detection._radio_native import prepare_amplitude, prepare_magnitude

    if packets.is_empty() or any(
        packets[name].n_unique() != 1 or packets[name].null_count()
        for name in ("attempt_id", "receiver_id", "attempt_started_monotonic_ns")
    ):
        raise ValueError("Expected one nonempty attempt/receiver recording")
    frame = packets.filter(pl.col("is_sensing"))
    if frame.is_empty():
        raise ValueError("No sensing-link CSI")
    required = [
        "sig_mode", "bandwidth", "stbc", "len", "csi_i", "csi_q",
        "first_word", "time_seconds", "capture_time_ns",
    ]
    if any(frame[name].null_count() for name in required):
        raise ValueError("Null CSI payload, layout or timestamp")
    if any(frame.schema[name] != pl.List(pl.Int16) for name in ("csi_i", "csi_q")):
        raise ValueError("CSI arrays must use the Parquet signed-int16 contract")
    if frame.filter(
        (pl.col("sig_mode") != 4) | (pl.col("bandwidth") != 0)
        | (pl.col("stbc") != 0) | ~pl.col("csi_i").list.len().is_in([245, 256])
    ).height:
        raise ValueError("Unsupported CSI layout; expected compact/full HE20")
    if frame.filter(
        (pl.col("csi_i").list.len() != pl.col("csi_q").list.len())
        | (pl.col("len") != 2 * pl.col("csi_i").list.len())
    ).height:
        raise ValueError("Invalid CSI payload length")
    times = frame["time_seconds"].to_numpy()
    if not np.isfinite(times).all() or np.any(np.diff(times) < 0):
        raise ValueError("Capture times must be finite and sorted")
    i, q = (frame[name].to_arrow() for name in ("csi_i", "csi_q"))
    if i.values.null_count or q.values.null_count:
        raise ValueError("Null I/Q sample")
    start, stop = int(i.offsets[0].as_py()), int(i.offsets[-1].as_py())
    qstart, qstop = int(q.offsets[0].as_py()), int(q.offsets[-1].as_py())
    result = (prepare_magnitude if magnitude_only else prepare_amplitude)(
        i.values.slice(start, stop-start).to_numpy().astype(np.int16, copy=False).tobytes(),
        q.values.slice(qstart, qstop-qstart).to_numpy().astype(np.int16, copy=False).tobytes(),
        (i.offsets.to_numpy() - start).tolist(),
        frame["first_word"].cast(pl.Boolean).to_list(),
        frame["driver_valid"].fill_null(False).to_list(),
    )
    if magnitude_only:
        raw, normalized, lower, upper = result, b"", b"", b""
    else:
        raw, normalized, lower, upper = result
    shape = (len(frame), 245)
    return AmplitudeRecording(
        frame,
        np.frombuffer(raw, dtype=np.float64).reshape(shape),
        (None if magnitude_only else
         np.frombuffer(normalized, dtype=np.float64).reshape(shape, order="F")),
        np.frombuffer(lower, dtype=np.float64), np.frombuffer(upper, dtype=np.float64),
    )


def save_recording(path: Path, arrays: dict, *, compression_level: int = 1) -> None:
    """Atomically save NumPy-compatible compressed arrays without pickled objects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            with ZipFile(stream, "w", compression=ZIP_DEFLATED, compresslevel=compression_level) as archive:
                for name, array in arrays.items():
                    with archive.open(name + ".npy", "w", force_zip64=True) as member:
                        np.lib.format.write_array(member, np.asanyarray(array), allow_pickle=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def preprocess_dataset(
    session, recordings: pl.DataFrame, output_dir: str | Path, *,
    window_seconds: float = 0.1, min_periods: int = 5, threshold: float = 5.0,
    compression_level: int = 1, progress=print,
) -> pl.DataFrame:
    """Stream projected Polars recordings through Rust and overlap one NPZ save.

    Args:
        session: Validated ParquetSession; raw recordings are only read.
        recordings: Selected attempt rows with scalar receiver_ids, in output order.
        output_dir: Derived output directory, outside the raw session.
        window_seconds: Centered Hampel duration.
        min_periods: Minimum finite samples.
        threshold: Scaled MAD threshold.
        compression_level: ZIP deflate level (0–9); default favors throughput.
        progress: Optional status callback.

    Returns:
        Polars summary in selection order, including individual stage durations.
    """
    output_dir = Path(output_dir).resolve()
    raw_dir = Path(session.manifest["source_directory"]).resolve()
    raw_root = raw_dir.parent.parent if raw_dir.parent.name == "sessions" else raw_dir
    if output_dir == raw_root or raw_root in output_dir.parents:
        raise ValueError("Preprocessing outputs must be outside raw data")
    if not 0 <= compression_level <= 9:
        raise ValueError("compression_level must be between 0 and 9")
    reader = AmplitudePacketReader(session.path / "packets.parquet")
    summary = []
    pending = None
    # A single bounded writer overlaps compression with the next read/native
    # computation. No unbounded future queue or nested per-recording CPU pool.
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="amplitude-save") as writer:
            for row in recordings.iter_rows(named=True):
                attempt_key, receiver = row["attempt_key"], row["receiver_ids"]
                relative = Path(attempt_key) / f"{receiver}.npz"
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Invalid recording output identity")
                started = perf_counter()
                packets = reader.read(attempt_key, receiver)
                loaded = perf_counter()
                recording = prepare_recording(packets)
                prepared = perf_counter()
                filtered, replaced = hampel_subcarriers(
                    recording.normalized, recording.time_seconds,
                    window_seconds=window_seconds, min_periods=min_periods, threshold=threshold,
                )
                filtered_at = perf_counter()
                metadata = recording.metadata
                valid = np.isfinite(recording.masked)
                provenance = {
                    "session_id": session.manifest["session_id"], "attempt_key": attempt_key,
                    "attempt_id": metadata["attempt_id"][0], "receiver_id": receiver,
                    "activity_label": row["activity_label"], "scenario_id": row["scenario_id"],
                    "quality": str(row["quality"]), "time_source": str(metadata["time_source"][0]),
                    "source_parquet": str(session.path),
                    "normalization": "per-recording, per-subcarrier min-max before Hampel",
                    "hampel_backend": "rust-rayon-runtime-simd-v1",
                    "preprocessing_backend": "polars-rust-he20-v1",
                    "compression_level": compression_level,
                    "hampel_window_seconds": window_seconds, "hampel_min_periods": min_periods,
                    "hampel_threshold_scaled_mad": threshold,
                }
                arrays = dict(
                    amplitude=filtered.astype(np.float32), valid=valid,
                    hampel_replaced=replaced, time_seconds=recording.time_seconds,
                    capture_time_ns=metadata["capture_time_ns"].to_numpy().astype(np.int64),
                    phase=metadata["phase"].fill_null("unknown").to_numpy().astype(str),
                    subcarriers=recording.subcarriers, scale_min=recording.lower,
                    scale_max=recording.upper, provenance_json=np.asarray(json.dumps(provenance)),
                )
                if pending is not None:
                    pending.result()
                path = output_dir / relative
                pending = writer.submit(save_recording, path, arrays, compression_level=compression_level)
                summary.append(dict(
                    attempt=metadata["attempt_id"][0], receiver=receiver,
                    packets=len(metadata), subcarriers=245,
                    valid_values=int(valid.sum()), hampel_replaced=int(replaced.sum()),
                    output=str(path), read_seconds=loaded-started,
                    prepare_seconds=prepared-loaded, hampel_seconds=filtered_at-prepared,
                ))
                if progress and (len(summary) % 20 == 0 or len(summary) == len(recordings)):
                    progress(f"Processed {len(summary)}/{len(recordings)} recordings")
            if pending is not None:
                pending.result()
    finally:
        reader.close()
    return pl.DataFrame(summary)
