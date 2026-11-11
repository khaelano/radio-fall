"""Offline four-receiver, sequence-aligned raw-magnitude dataset preparation.

A 96 Hz grid derived from a 120 Hz source selects nearest source rounds,
without interpolation or anti-alias filtering. Centered Hampel uses future
samples. This representation has not been validated as a detector input.
"""

import hashlib
import json
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from zipfile import BadZipFile, ZipFile

import numpy as np
import polars as pl

from .amplitude import hampel_subcarriers
from .amplitude_pipeline import (
    COLUMNS,
    AmplitudePacketReader,
    load_amplitude_session,
    prepare_recording,
    save_recording,
)
from .sequence_cache import (
    array_directory,
    file_hash,
    fingerprint,
    read_segment,
    save_segment,
    stage_cache,
    stamp,
)

os.environ.setdefault("RAYON_NUM_THREADS", str(os.cpu_count() or 1))

_MODULUS = 1 << 32


def sequence_offsets(
    sequences: np.ndarray, anchor: int
) -> tuple[np.ndarray, dict[str, int]]:
    """Unwrap one ordered transmitter epoch relative to a shared sequence anchor.

    Duplicate rounds are retained and counted; backward jumps are rejected so
    that resets and reordering cannot silently become long gaps or cross epochs.
    Each epoch must span less than half the sequence counter range.
    """
    raw = np.asarray(sequences)
    if raw.ndim != 1 or not np.issubdtype(raw.dtype, np.integer):
        raise ValueError("sequences must be a one-dimensional integer array")
    if not 0 <= anchor < _MODULUS or np.any(raw < 0) or np.any(raw >= _MODULUS):
        raise ValueError("sequence out of uint32 range")
    if len(raw) == 0:
        return np.empty(0, dtype=np.int64), {"duplicates": 0, "wraps": 0}
    values = raw.astype(np.int64)
    first = (int(values[0]) - anchor) % _MODULUS
    if first >= _MODULUS // 2:
        first -= _MODULUS
    steps = np.diff(values) % _MODULUS
    if np.any(steps >= _MODULUS // 2):
        raise ValueError(
            "sequence reset or out-of-order packet; split or resolve epoch"
        )
    offsets = np.r_[first, first + np.cumsum(steps, dtype=np.int64)]
    if offsets[-1] - offsets[0] >= _MODULUS // 2:
        raise ValueError("sequence epoch spans half the counter range")
    return offsets, {
        "duplicates": int(np.count_nonzero(steps == 0)),
        "wraps": int(np.count_nonzero((np.diff(values) < 0) & (steps > 0))),
    }


def source_rounds(
    start: int, stop: int, *, source_hz: int = 120, target_hz: int = 96
) -> np.ndarray:
    """Select source-round offsets on a target grid, with ties rounded upward.

    The range is target-grid indices [start, stop); all receivers must use the
    same sequence anchor and grid indices. No interpolation is performed.
    """
    if source_hz < target_hz or target_hz <= 0 or start < 0 or stop < start:
        raise ValueError("invalid sampling rates or grid bounds")
    ticks = np.arange(start, stop, dtype=np.int64)
    return (ticks * source_hz * 2 + target_hz) // (2 * target_hz)


def align_samples(
    offsets: np.ndarray, values: np.ndarray, rounds: np.ndarray
) -> tuple[np.ndarray, int]:
    """Select exact source rounds; retain first duplicate and mask missing rows."""
    offsets, values, rounds = (
        np.asarray(offsets),
        np.asarray(values),
        np.asarray(rounds),
    )
    if (
        offsets.ndim != 1
        or rounds.ndim != 1
        or values.ndim != 2
        or len(offsets) != len(values)
    ):
        raise ValueError("incompatible alignment shapes")
    if np.any(np.diff(offsets) < 0) or np.any(np.diff(rounds) <= 0):
        raise ValueError("offsets and rounds must be ordered")
    result = np.full((len(rounds), values.shape[1]), np.nan)
    indexes = np.searchsorted(offsets, rounds, side="left")
    found = indexes < len(offsets)
    found[found] &= offsets[indexes[found]] == rounds[found]
    result[found] = values[indexes[found]]
    return result, int(len(offsets) - len(np.unique(offsets)))


def filter_and_difference(
    amplitude: np.ndarray,
    *,
    rate_hz: int = 96,
    window_seconds: float = 0.5,
    threshold: float = 3.0,
    min_periods: int = 5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply centered native Hampel and differences only across adjacent valid samples."""
    values = np.asarray(amplitude, dtype=float)
    if values.ndim != 2 or rate_hz <= 0:
        raise ValueError("expected a matrix and positive rate")
    times = np.arange(len(values), dtype=float) / rate_hz
    filtered, replaced = hampel_subcarriers(
        values,
        times,
        window_seconds=window_seconds,
        threshold=threshold,
        min_periods=min_periods,
    )
    delta = np.full_like(filtered, np.nan)
    delta[1:] = np.square(filtered[1:] - filtered[:-1])
    return filtered, replaced, delta


def window_starts(length: int, seconds: int, *, rate_hz: int = 96) -> np.ndarray:
    """Return complete 50%-overlap window starts within one recording segment."""
    if length < 0 or seconds not in (2, 4, 6) or rate_hz <= 0:
        raise ValueError("invalid length, window size or rate")
    size = seconds * rate_hz
    if size % 2:
        raise ValueError("window must have an even number of samples")
    return np.arange(0, max(0, length - size + 1), size // 2, dtype=np.int64)


RECEIVERS = ("rx-1", "rx-2", "rx-3", "rx-4")
DURATIONS = (2, 4, 6)
SEQUENCE_COLUMNS = list(
    dict.fromkeys(
        COLUMNS
        + [
            "sequence",
            "run_id",
            "transmitter_boot_id",
            "receiver_boot_id",
            "nominal_rate_hz",
            "source_row",
        ]
    )
)
DATASETS = {
    "khaelano": "20261104T081805521126Z",
    "akmal": "20261109T131546367822Z",
    "continuous_non_fall": "20261109T161519702956Z",
}


WINDOW_SCHEMA = {
    **{
        key: pl.String
        for key in (
            "participant_id",
            "session_id",
            "attempt_key",
            "attempt_id",
            "activity_label",
            "scenario_id",
            "segment_id",
            "run_id",
            "transmitter_boot_id",
            "center_phase",
            "group",
        )
    },
    **{
        key: pl.Int64
        for key in (
            "trial_ordinal",
            "attempt",
            "duration",
            "start",
            "stop",
            "start_ns",
            "center_ns",
            "target",
        )
    },
    "coverage": pl.Float64,
    "receiver_coverage": pl.List(pl.Float64),
}
SHARD_SCHEMA = {
    "duration": pl.Int64,
    "shard": pl.String,
    "windows": pl.Int64,
    "shape": pl.List(pl.Int64),
    "bytes": pl.Int64,
    "sha256": pl.String,
    "compression": pl.String,
}


def atomic_table(frame: pl.DataFrame, path: Path) -> None:
    """Publish a complete Parquet table atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as f:
        temporary = Path(f.name)
    try:
        frame.write_parquet(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(value: dict, path: Path) -> None:
    """Publish JSON without leaving a partial manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        json.dump(value, f, indent=2)
        f.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _completed_shard(path: Path, key: str, metadata: dict) -> dict | None:
    """Resume using provenance and file identity, without opening NPZ tensors."""
    try:
        receipt = json.loads(path.with_suffix(".verified.json").read_text())
        if (
            receipt["key"] == key
            and receipt["stamp"] == stamp(path)
            and all(receipt["result"].get(k) == v for k, v in metadata.items())
        ):
            return receipt["result"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def _verified_shard(
    path: Path,
    arrays: dict,
    metadata: dict,
    *,
    resume_key: str,
    compression_level: int = 1,
    verify_new: bool = False,
) -> dict:
    """Write once; only an explicit audit reloads new tensors. Resume uses receipts."""
    completed = _completed_shard(path, resume_key, metadata)
    if completed is not None:
        return completed
    save_recording(path, arrays, compression_level=compression_level)
    if verify_new:
        with np.load(path, allow_pickle=False) as saved:
            if set(saved.files) != set(arrays):
                raise ValueError(f"Shard keys differ: {path}")
            for key, value in arrays.items():
                actual = saved[key]
                if (
                    actual.shape != value.shape
                    or actual.dtype != value.dtype
                    or actual.tobytes(order="F") != value.tobytes(order="F")
                ):
                    raise ValueError(f"Shard reload differs: {path}")
    result = dict(
        metadata,
        compression="zip_deflate",
        bytes=path.stat().st_size,
        sha256=file_hash(path),
    )
    atomic_json(
        dict(key=resume_key, stamp=stamp(path), result=result),
        path.with_suffix(".verified.json"),
    )
    return result


def squared_difference(values: np.ndarray) -> np.ndarray:
    """Difference adjacent samples in one segment, preserving NaN propagation."""
    result = np.full_like(values, np.nan)
    result[1:] = np.square(values[1:] - values[:-1])
    return result


def label_windows(
    times_ns: np.ndarray,
    seconds: int,
    activity: str,
    action_intervals: list[tuple[int, int]],
    bounds_ns: tuple[int, int] | None = None,
) -> tuple[np.ndarray, int]:
    """Select complete windows by cue-center labels, returning omitted count."""
    starts = window_starts(len(times_ns), seconds)
    if bounds_ns is not None:
        begin, end = bounds_ns
        starts = starts[
            (times_ns[starts] >= begin)
            & (times_ns[starts] + seconds * 1_000_000_000 <= end)
        ]
    if activity.endswith("_to_fall") or activity == "fall":
        centers = times_ns[starts] + int(seconds * 1e9 / 2)
        keep = np.zeros(len(starts), dtype=bool)
        for start, end in action_intervals:
            keep |= (centers >= start) & (centers < end)
        return starts[keep], int((~keep).sum())
    if activity not in {
        "non_fall",
        "stand_to_walk",
        "walk_to_stand",
        "sit_to_walk",
        "walk_to_sit",
        "sit_to_stand",
        "stand_to_sit",
    }:
        raise ValueError(f"Unknown binary activity: {activity}")
    return starts, 0


def split_packet_epochs(
    frame: pl.DataFrame, *, gap_seconds: float = 1.0
) -> list[pl.DataFrame]:
    """Keep run/TX boots, receiver reboots and all-receiver recording gaps apart.

    A recording gap is >= gap_seconds without any sensing packet in the union
    of receivers. Shorter packet losses remain holes on the shared grid. This
    boundary rule is independent of validity/coverage and is not a quality cut.
    """
    if gap_seconds <= 0:
        raise ValueError("gap_seconds must be positive")
    if frame.is_empty():
        return []
    required = ["sequence", "run_id", "transmitter_boot_id", "receiver_boot_id"]
    if any(frame[c].null_count() for c in required):
        raise ValueError("Missing sequence/run/boot identity")
    frame = frame.sort("capture_time_ns", maintain_order=True)
    times = frame["capture_time_ns"].to_numpy()
    cuts = {0, len(frame)}
    # Chronological transitions, rather than group_by, also isolate a reused ID.
    for name in ("run_id", "transmitter_boot_id"):
        values = frame[name].to_numpy()
        cuts.update((np.flatnonzero(values[1:] != values[:-1]) + 1).tolist())
    cuts.update((np.flatnonzero(np.diff(times) >= gap_seconds * 1e9) + 1).tolist())
    for receiver in RECEIVERS:
        subset = frame.with_row_index("_index").filter(
            pl.col("receiver_id") == receiver
        )
        boots = subset["receiver_boot_id"].to_numpy()
        changes = np.flatnonzero(boots[1:] != boots[:-1]) + 1
        # Split all views at the reboot's timestamp, including tied packets.
        for index in changes:
            time = subset["capture_time_ns"][int(index)]
            cuts.add(int(np.searchsorted(times, time, side="left")))
    bounds = sorted(cuts)
    return [frame.slice(a, b - a) for a, b in zip(bounds, bounds[1:]) if b > a]


def align_epoch(frame: pl.DataFrame) -> tuple[dict[str, np.ndarray], list[dict]]:
    """Decode four receiver views onto one 120-to-96 Hz sequence grid."""
    if frame.is_empty() or set(frame["receiver_id"].unique()) - set(RECEIVERS):
        raise ValueError("Empty epoch or unknown receiver identity")
    if frame["nominal_rate_hz"].null_count() or set(frame["nominal_rate_hz"]) != {
        120.0
    }:
        raise ValueError("This dataset version requires nominal 120 Hz")
    anchor = int(frame["sequence"][0])
    decoded, offsets, stats = {}, {}, []
    for receiver in RECEIVERS:
        part = frame.filter(pl.col("receiver_id") == receiver)
        if part.is_empty():
            continue
        off, anomalies = sequence_offsets(part["sequence"].to_numpy(), anchor)
        offsets[receiver] = off
        decoded[receiver] = prepare_recording(part, magnitude_only=True)
        gaps, counts = np.unique(np.diff(np.unique(off)), return_counts=True)
        stats.append(
            dict(
                receiver=receiver,
                packets=len(part),
                **anomalies,
                gap_rounds=gaps.tolist(),
                gap_counts=counts.tolist(),
            )
        )
    lowest = min(int(v.min()) for v in offsets.values())
    highest = max(int(v.max()) for v in offsets.values())
    anchor = (anchor + lowest) % _MODULUS
    rounds = source_rounds(0, (highest - lowest) * 96 // 120 + 1)
    amplitude = np.full((len(rounds), 4, 245), np.nan)
    capture = np.full((len(rounds), 4), -1, dtype=np.int64)
    origins = []
    for r, receiver in enumerate(RECEIVERS):
        if receiver not in decoded:
            stats.append(
                dict(
                    receiver=receiver,
                    packets=0,
                    duplicates=0,
                    wraps=0,
                    gap_rounds=[],
                    gap_counts=[],
                )
            )
            continue
        recording = decoded[receiver]
        off = offsets[receiver] - lowest
        amplitude[:, r], _ = align_samples(off, recording.masked, rounds)
        source_times = recording.metadata["capture_time_ns"].to_numpy()
        mapped, _ = align_samples(off, source_times[:, None], rounds)
        found = np.isfinite(mapped[:, 0])
        capture[found, r] = mapped[found, 0].astype(np.int64)
        origins.append(source_times - off / 120 * 1e9)
    # Nominal grid time is distinct from retained actual per-receiver captures.
    origin = int(np.median(np.concatenate(origins)))
    times = origin + np.rint(np.arange(len(rounds)) / 96 * 1e9).astype(np.int64)
    return dict(
        amplitude=amplitude,
        valid=np.isfinite(amplitude),
        sequence=((anchor + rounds) % _MODULUS).astype(np.uint32),
        sequence_offset=rounds,
        time_ns=times,
        capture_time_ns=capture,
        subcarriers=np.arange(-122, 123),
        receivers=np.asarray(RECEIVERS),
    ), stats


@dataclass
class SequenceDataset:
    """Stage-oriented offline workflow, storing bounded per-segment artifacts."""

    root: Path
    name: str
    session_id: str
    gap_seconds: float = 1.0
    shard_windows: int = 12
    timings: dict = field(default_factory=dict)
    workers: int = field(default_factory=lambda: os.cpu_count() or 1)
    memory_budget_mb: int = 2048
    compression_level: int = 1
    verify_new_shards: bool = False
    cache_hits: list = field(default_factory=list)
    format_version: int = 2

    def _processing_key(self) -> str:
        return fingerprint(
            dict(
                version=1,
                source=self.session.manifest,
                gap=self.gap_seconds,
                windows=self.shard_windows,
                code=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            )
        )

    def _completed_cache_valid(self) -> bool:
        return getattr(self, "_completed_parameters", None) == (
            self.gap_seconds,
            self.shard_windows,
        ) and getattr(self, "_completed_source", None) == fingerprint(
            self.session.manifest
        )

    def _stage_summary(self, stage: str) -> pl.DataFrame:
        if stage == "align_decode":
            return (
                self.alignment.group_by("receiver")
                .agg(
                    pl.col(
                        "packets",
                        "duplicates",
                        "wraps",
                        "retained",
                        "missing",
                        "available_rounds",
                    ).sum()
                )
                .sort("receiver")
            )
        if stage == "hampel":
            return (
                self.hampel.group_by("receiver")
                .agg(pl.col("replaced", "valid").sum())
                .with_columns(
                    (pl.col("replaced") / pl.col("valid")).alias("replacement_rate")
                )
                .sort("receiver")
            )
        if stage == "difference":
            return (
                self.differences.group_by("receiver")
                .agg(pl.col("valid", "missing").sum())
                .sort("receiver")
            )
        return (
            self.index.group_by("duration", "target")
            .agg(
                pl.len().alias("windows"),
                pl.col("coverage").mean().alias("mean_coverage"),
            )
            .sort("duration", "target")
        )

    def _load_session_cached(self):
        from . import phase_signals, session_parquet
        from .amplitude_pipeline import AmplitudeSession

        source = self.root / "data/raw/sessions" / f"{self.session_id}.zip"
        directory = self.root / "data/interim/parquet" / self.session_id
        manifest_path = directory / "session.json"
        # The canonical Parquet cache was built from checksum-verified originals.
        # Bootstrap old caches by comparing the small archive manifest and code key;
        # subsequent calls use file identity receipts. Changed archives take the
        # original full validation path.
        checkpoint = self.output / ".cache" / "source.json"
        paths = [source, manifest_path] + [
            directory / f"{name}.parquet" for name in ("attempts", "phases", "packets")
        ]
        try:
            identities = {str(p): stamp(p) for p in paths}
            cached = json.loads(manifest_path.read_text())
            try:
                receipt = json.loads(checkpoint.read_text())
            except (OSError, ValueError):
                receipt = {}
            code = [
                file_hash(Path(m.__file__)) for m in (session_parquet, phase_signals)
            ]
            trusted = receipt == dict(files=identities, code=code)
            if (
                not receipt
                and source.stat().st_mtime_ns <= manifest_path.stat().st_mtime_ns
            ):
                with ZipFile(source) as archive:
                    digest = hashlib.sha256(
                        json.dumps(
                            json.loads(archive.read("manifest.json")), sort_keys=True
                        ).encode()
                    )
                for m in (session_parquet, phase_signals):
                    digest.update(Path(m.__file__).read_bytes())
                trusted = cached.get("archive_fingerprint") == digest.hexdigest()
            if (
                trusted
                and cached.get("schema_version") == session_parquet.SCHEMA_VERSION
            ):
                atomic_json(dict(files=identities, code=code), checkpoint)
                self.cache_hits.append("source")
                return AmplitudeSession(
                    directory, cached, pl.read_parquet(directory / "attempts.parquet")
                )
        except (OSError, ValueError, KeyError, BadZipFile):
            pass
        session = load_amplitude_session(source, directory)
        atomic_json(
            dict(
                files={str(p): stamp(p) for p in paths},
                code=[
                    file_hash(Path(m.__file__))
                    for m in (session_parquet, phase_signals)
                ],
            ),
            checkpoint,
        )
        return session

    @property
    def output(self) -> Path:
        """Return this dataset's derived directory."""
        if self.format_version not in (1, 2):
            raise ValueError("Unknown sequence format version")
        return self.root / f"data/processed/amplitude_sequence_v{self.format_version}" / self.name

    def load(self) -> pl.DataFrame:
        """Load reviewed metadata and report every selected/excluded attempt."""
        start = perf_counter()
        self._completed_parameters = None
        self.session = self._load_session_cached()
        self.attempts = self.session.attempts
        selected = (pl.col("status") == "accepted") & (pl.col("inclusion") != "exclude")
        self.selection = self.attempts.with_columns(selected.alias("selected"))
        self.selected = self.selection.filter("selected").sort("attempt_key")
        if self.selected.is_empty():
            raise ValueError("No accepted, non-excluded attempts")
        self.phases = pl.read_parquet(self.session.path / "phases.parquet")
        if (self.output / "manifest.json").is_file():
            try:
                self.load_exported()
            except (OSError, ValueError, KeyError):
                pass
            else:
                self.recordings = pl.read_parquet(self.output / "recordings.parquet")
                for attribute in ("alignment", "hampel", "differences"):
                    setattr(
                        self,
                        attribute,
                        pl.read_parquet(self.output / f"{attribute}.parquet"),
                    )
                self.omissions = pl.read_parquet(self.output / "window_counts.parquet")
                self.timings["load_cached"] = perf_counter() - start
                return (
                    self.selection.group_by(
                        "selected", "status", "inclusion", "activity_label"
                    )
                    .len()
                    .sort("activity_label")
                )
        metadata = (
            pl.scan_parquet(self.session.path / "packets.parquet")
            .filter(
                pl.col("is_sensing")
                & pl.col("attempt_key").is_in(self.selected["attempt_key"].implode())
            )
            .group_by("attempt_key", "receiver_id")
            .agg(
                pl.len().alias("packets"),
                pl.col("driver_valid").sum().alias("driver_valid_packets"),
                pl.col("capture_time_ns").min().alias("first_ns"),
                pl.col("capture_time_ns").max().alias("last_ns"),
            )
            .collect()
        )
        expected = self.selected.select("attempt_key").join(
            pl.DataFrame({"receiver_id": RECEIVERS}), how="cross"
        )
        self.recordings = expected.join(
            metadata, on=["attempt_key", "receiver_id"], how="left"
        ).with_columns(pl.col("packets", "driver_valid_packets").fill_null(0))
        self.output.mkdir(parents=True, exist_ok=True)
        atomic_table(self.selection, self.output / "selection.parquet")
        atomic_table(self.recordings, self.output / "recordings.parquet")
        self.timings["load"] = perf_counter() - start
        return (
            self.selection.group_by("selected", "status", "inclusion", "activity_label")
            .len()
            .sort("activity_label")
        )

    @stage_cache(
        "align_decode",
        {"segments": "segments.parquet", "alignment": "alignment.parquet"},
        (
            "amplitude",
            "valid",
            "sequence",
            "sequence_offset",
            "time_ns",
            "capture_time_ns",
            "phase",
            "subcarriers",
            "receivers",
        ),
    )
    def align(self) -> pl.DataFrame:
        """Stream selected attempts to aligned segment files and audit tables."""
        started = perf_counter()
        reader = AmplitudePacketReader(
            self.session.path / "packets.parquet", columns=SEQUENCE_COLUMNS
        )
        segments, summaries = [], []
        try:
            for attempt in self.selected.iter_rows(named=True):
                frames = [reader.read(attempt["attempt_key"], r) for r in RECEIVERS]
                frame = pl.concat(frames).filter(
                    pl.col("is_sensing")
                    & (pl.col("capture_time_ns") >= attempt["started_monotonic_ns"])
                    & (pl.col("capture_time_ns") < attempt["ended_monotonic_ns"])
                )
                for number, epoch in enumerate(
                    split_packet_epochs(frame, gap_seconds=self.gap_seconds)
                ):
                    arrays, audit = align_epoch(epoch)
                    identifier = f"{attempt['trial_ordinal']:03d}-{attempt['attempt']:02d}-{number:03d}"
                    phase = np.full(len(arrays["time_ns"]), "unassigned", dtype="<U12")
                    intervals = self.phases.filter(
                        pl.col("attempt_key") == attempt["attempt_key"]
                    )
                    for cue in intervals.iter_rows(named=True):
                        phase[
                            (arrays["time_ns"] >= cue["start_ns"])
                            & (arrays["time_ns"] < cue["end_ns"])
                        ] = cue["phase"]
                    arrays["phase"] = phase
                    info = {
                        k: attempt[k]
                        for k in (
                            "participant_id",
                            "session_id",
                            "attempt_key",
                            "attempt_id",
                            "trial_ordinal",
                            "attempt",
                            "activity_label",
                            "scenario_id",
                            "review_revision",
                        )
                    }
                    info.update(
                        segment_id=identifier,
                        run_id=epoch["run_id"][0],
                        transmitter_boot_id=epoch["transmitter_boot_id"][0],
                        receiver_boot_ids=epoch.select(
                            "receiver_id", "receiver_boot_id"
                        )
                        .unique()
                        .to_dicts(),
                    )
                    path = self.output / "segments" / identifier
                    save_segment(path, arrays)
                    segments.append(
                        dict(
                            **info,
                            path=str(path),
                            samples=len(phase),
                            start_ns=int(arrays["time_ns"][0]),
                            end_ns=int(arrays["time_ns"][-1]),
                        )
                    )
                    for row in audit:
                        r = RECEIVERS.index(row["receiver"])
                        summaries.append(
                            dict(
                                segment_id=identifier,
                                **row,
                                retained=int(arrays["valid"][:, r].sum()),
                                missing=int((~arrays["valid"][:, r]).sum()),
                                available_rounds=int(
                                    arrays["valid"][:, r].any(axis=1).sum()
                                ),
                            )
                        )
                if not len(frame):
                    # A selected empty attempt must remain visible in reconciliation.
                    summaries.append(
                        dict(
                            segment_id=attempt["attempt_key"],
                            receiver="all",
                            packets=0,
                            duplicates=0,
                            wraps=0,
                            gap_rounds=[],
                            gap_counts=[],
                            retained=0,
                            missing=0,
                            available_rounds=0,
                        )
                    )
        finally:
            reader.close()
        self.segments = pl.DataFrame(segments)
        self.alignment = pl.DataFrame(summaries)
        atomic_table(self.segments, self.output / "segments.parquet")
        atomic_table(self.alignment, self.output / "alignment.parquet")
        self.timings["align_decode"] = perf_counter() - started
        return (
            self.alignment.group_by("receiver")
            .agg(
                pl.col(
                    "packets",
                    "duplicates",
                    "wraps",
                    "retained",
                    "missing",
                    "available_rounds",
                ).sum()
            )
            .sort("receiver")
        )

    @stage_cache(
        "hampel",
        {"hampel": "hampel.parquet"},
        ("filtered_amplitude", "hampel_replaced", "filtered_valid"),
    )
    def filter(self) -> pl.DataFrame:
        """Apply centered Hampel independently to all segment receiver/subcarriers."""
        started, summary = perf_counter(), []
        for segment in self.segments.iter_rows(named=True):
            path = Path(segment["path"])
            with read_segment(path) as saved:
                arrays = dict(saved)
            values = arrays["amplitude"]
            filtered, replaced = hampel_subcarriers(
                values.reshape(len(values), -1),
                np.arange(len(values)) / 96,
                window_seconds=0.5,
                threshold=3,
                min_periods=5,
            )
            arrays["filtered_amplitude"] = filtered.reshape(values.shape)
            arrays["hampel_replaced"] = replaced.reshape(values.shape)
            arrays["filtered_valid"] = np.isfinite(arrays["filtered_amplitude"])
            save_segment(path, arrays)
            for r, receiver in enumerate(RECEIVERS):
                summary.append(
                    dict(
                        segment_id=segment["segment_id"],
                        receiver=receiver,
                        replaced=int(arrays["hampel_replaced"][:, r].sum()),
                        valid=int(arrays["valid"][:, r].sum()),
                    )
                )
        self.hampel = pl.DataFrame(summary)
        atomic_table(self.hampel, self.output / "hampel.parquet")
        self.timings["hampel"] = perf_counter() - started
        return (
            self.hampel.group_by("receiver")
            .agg(pl.col("replaced", "valid").sum())
            .with_columns(
                (pl.col("replaced") / pl.col("valid")).alias("replacement_rate")
            )
            .sort("receiver")
        )

    @stage_cache(
        "difference",
        {"differences": "differences.parquet"},
        ("squared_difference", "difference_valid"),
    )
    def difference(self) -> pl.DataFrame:
        """Compute consecutive squared differences without crossing segments."""
        started, rows = perf_counter(), []
        for segment in self.segments.iter_rows(named=True):
            path = Path(segment["path"])
            with read_segment(path) as saved:
                arrays = dict(saved)
            arrays["squared_difference"] = squared_difference(
                arrays["filtered_amplitude"]
            )
            arrays["difference_valid"] = np.isfinite(arrays["squared_difference"])
            save_segment(path, arrays)
            for r, receiver in enumerate(RECEIVERS):
                valid = arrays["difference_valid"][:, r]
                rows.append(
                    dict(
                        segment_id=segment["segment_id"],
                        receiver=receiver,
                        valid=int(valid.sum()),
                        missing=int((~valid).sum()),
                    )
                )
        self.differences = pl.DataFrame(rows)
        atomic_table(self.differences, self.output / "differences.parquet")
        self.timings["difference"] = perf_counter() - started
        return (
            self.differences.group_by("receiver")
            .agg(pl.col("valid", "missing").sum())
            .sort("receiver")
        )

    @stage_cache(
        "window_index",
        {"index": "window_index.parquet", "omissions": "window_counts.parquet"},
    )
    def windows(self) -> pl.DataFrame:
        """Index complete 2/4/6 s synchronized windows and cue-center targets."""
        started, rows, omissions = perf_counter(), [], []
        attempt_bounds = {
            r["attempt_key"]: (r["started_monotonic_ns"], r["ended_monotonic_ns"])
            for r in self.attempts.iter_rows(named=True)
            if "started_monotonic_ns" in r and "ended_monotonic_ns" in r
        }
        for segment in self.segments.iter_rows(named=True):
            with read_segment(segment["path"]) as arrays:
                times, valid = arrays["time_ns"], arrays["valid"]
                intervals = self.phases.filter(
                    (pl.col("attempt_key") == segment["attempt_key"])
                    & (pl.col("phase") == "action")
                )
                actions = list(intervals.select("start_ns", "end_ns").iter_rows())
                for duration in DURATIONS:
                    starts, omitted = label_windows(
                        times,
                        duration,
                        segment["activity_label"],
                        actions,
                        attempt_bounds.get(segment["attempt_key"]),
                    )
                    candidates = len(window_starts(len(times), duration))
                    boundary_omitted = candidates - len(starts) - omitted
                    omissions.append(
                        dict(
                            segment_id=segment["segment_id"],
                            duration=duration,
                            candidates=candidates,
                            omitted=omitted + boundary_omitted,
                            boundary_omitted=boundary_omitted,
                            label_omitted=omitted,
                            retained=len(starts),
                        )
                    )
                    for start in starts:
                        stop = int(start) + duration * 96
                        coverage = valid[start:stop].mean(axis=(0, 2))
                        info = {
                            k: segment[k]
                            for k in (
                                "participant_id",
                                "session_id",
                                "attempt_key",
                                "attempt_id",
                                "trial_ordinal",
                                "attempt",
                                "activity_label",
                                "scenario_id",
                                "segment_id",
                                "run_id",
                                "transmitter_boot_id",
                            )
                        }
                        rows.append(
                            dict(
                                **info,
                                duration=duration,
                                start=int(start),
                                stop=stop,
                                start_ns=int(times[start]),
                                center_ns=int(times[start]) + duration * 500_000_000,
                                target=int(
                                    segment["activity_label"].endswith("_to_fall")
                                    or segment["activity_label"] == "fall"
                                ),
                                center_phase=str(
                                    arrays["phase"][int(start) + duration * 48]
                                ),
                                group=f"{self.session_id}::{segment['attempt_key']}",
                                coverage=float(coverage.mean()),
                                receiver_coverage=coverage.tolist(),
                            )
                        )
        self.index = pl.DataFrame(rows, schema=WINDOW_SCHEMA)
        self.omissions = pl.DataFrame(omissions)
        atomic_table(self.omissions, self.output / "window_counts.parquet")
        atomic_table(self.index, self.output / "window_index.parquet")
        self.timings["window_index"] = perf_counter() - started
        return (
            self.index.group_by("duration", "target")
            .agg(
                pl.len().alias("windows"),
                pl.col("coverage").mean().alias("mean_coverage"),
            )
            .sort("duration", "target")
        )

    def load_exported(self, *, verify_hashes: bool = False) -> pl.DataFrame:
        """Load completed metadata and optionally audit all signal hashes."""
        manifest = json.loads((self.output / "manifest.json").read_text())
        if self.format_version == 2:
            if manifest.get("schema") != "amplitude_sequence_v2" or (
                manifest.get("source", {}).get("source_fingerprint")
                != self.session.manifest.get("source_fingerprint")
            ) or manifest.get("parameters", {}).get("dtype") != "float32":
                raise ValueError("Export source or schema differs")
            for filename, digest in manifest["metadata_sha256"].items():
                if file_hash(self.output / filename) != digest:
                    raise ValueError(f"Export metadata differs: {filename}")
            signals = pl.read_parquet(self.output / "signals.parquet")
            for row in signals.iter_rows(named=True):
                path = (self.output / row["signal"]).resolve()
                if not path.is_relative_to(self.output.resolve()) or (
                    path.stat().st_size != row["bytes"]
                ) or (verify_hashes and file_hash(path) != row["sha256"]):
                    raise ValueError(f"Export signal differs: {path}")
            self.index = pl.read_parquet(self.output / "window_index.parquet")
            self.segments = pl.read_parquet(self.output / "segments.parquet")
            if len(self.index) != manifest["counts"]["windows"]:
                raise ValueError("Export window count differs")
            self.signals = signals
            self.timings = manifest.get("timings_seconds", {})
            self._completed_source = fingerprint(self.session.manifest)
            self._completed_parameters = (self.gap_seconds, self.shard_windows)
            return self.index.group_by("duration").len().rename({"len": "windows"}).sort("duration")
        expected = dict(
            source_hz=120,
            target_hz=96,
            normalization=None,
            recording_gap_seconds=self.gap_seconds,
            hampel_seconds=0.5,
            threshold=3,
            min_periods=5,
            durations=list(DURATIONS),
            overlap=0.5,
            dtype="float64",
            tensor_order="window,time,receiver,subcarrier",
            max_windows_per_shard=self.shard_windows,
        )
        if (
            manifest.get("schema") != "amplitude_sequence_v1"
            or not manifest.get("source", {}).get("source_fingerprint")
            or manifest.get("session_id") != self.session_id
            or manifest.get("source", {}).get("source_fingerprint")
            != self.session.manifest.get("source_fingerprint")
            or any(
                manifest.get("parameters", {}).get(k) != v for k, v in expected.items()
            )
        ):
            raise ValueError("Export source or parameters differ; rebuild the dataset")
        shards = pl.read_parquet(self.output / "shards.parquet")
        for row in shards.iter_rows(named=True):
            path = self.output / row["shard"]
            if (
                path.parent.parent.resolve() != self.output.resolve()
                or path.stat().st_size != row["bytes"]
                or (verify_hashes and file_hash(path) != row["sha256"])
            ):
                raise ValueError(f"Export shard hash or path differs: {path}")
        index = pl.read_parquet(self.output / "window_index.parquet")
        if len(index) != manifest["counts"]["windows"] or len(index) != sum(
            shards["windows"]
        ):
            raise ValueError("Export window counts differ")
        self._completed_source = fingerprint(self.session.manifest)
        self._completed_parameters = (self.gap_seconds, self.shard_windows)
        self.shards, self.index = shards, index
        self.segments = pl.read_parquet(self.output / "segments.parquet")
        self.timings = manifest["timings_seconds"]
        return (
            self.shards.group_by("duration")
            .agg(pl.col("windows", "bytes").sum(), pl.len().alias("shards"))
            .sort("duration")
        )

    def export(self) -> pl.DataFrame:
        """Publish v2 signals, or legacy v1 shards when explicitly requested."""
        if self.format_version == 2:
            return self.export_v2()
        from fall_detection._radio_native import BACKEND_VERSION

        if self._completed_cache_valid():
            self.cache_hits.append("export")
            return (
                self.shards.group_by("duration")
                .agg(pl.col("windows", "bytes").sum(), pl.len().alias("shards"))
                .sort("duration")
            )
        if self.workers < 1 or self.memory_budget_mb < 1:
            raise ValueError("workers and memory_budget_mb must be positive")
        processing_key = self._processing_key()
        memory_limit = self.memory_budget_mb * 1024**2
        inflight_bytes = 0
        if self.shard_windows <= 0:
            raise ValueError("shard_windows must be positive")
        cache_directory = (self.output / "segments").resolve()
        if any(
            Path(p).parent.resolve() != cache_directory for p in self.segments["path"]
        ):
            raise ValueError("Segment cache must be inside this dataset output")
        started, exported, shards = perf_counter(), [], []
        tensor_keys = (
            "amplitude",
            "filtered_amplitude",
            "squared_difference",
            "valid",
            "filtered_valid",
            "difference_valid",
            "hampel_replaced",
            "sequence",
            "sequence_offset",
            "time_ns",
            "capture_time_ns",
            "phase",
        )
        pending = deque()
        with ThreadPoolExecutor(
            max_workers=self.workers, thread_name_prefix="sequence-save"
        ) as writer:
            for duration in DURATIONS:
                number = 0
                for segment in self.segments.iter_rows(named=True):
                    selected = self.index.filter(
                        (pl.col("duration") == duration)
                        & (pl.col("segment_id") == segment["segment_id"])
                    )
                    if selected.is_empty():
                        continue
                    source = None
                    per_window = duration * 96 * 4 * 245 * 35
                    if memory_limit < per_window:
                        raise ValueError("Writer memory budget cannot hold one window")
                    chunk_limit = min(self.shard_windows, memory_limit // per_window)
                    for offset in range(0, len(selected), chunk_limit):
                        chunk = selected.slice(offset, chunk_limit)
                        relative = f"{duration}s/shard-{number:05d}.npz"
                        path = self.output / relative
                        metadata = dict(
                            duration=duration,
                            shard=relative,
                            windows=len(chunk),
                            shape=[len(chunk), duration * 96, 4, 245],
                        )
                        resume_key = fingerprint(
                            [
                                processing_key,
                                segment["segment_id"],
                                duration,
                                chunk["start"].to_list(),
                            ]
                        )
                        exported.extend(
                            dict(row, shard=relative, shard_row=i)
                            for i, row in enumerate(chunk.iter_rows(named=True))
                        )
                        number += 1
                        cached = _completed_shard(path, resume_key, metadata)
                        if cached is not None:
                            shards.append(cached)
                            continue
                        estimated = len(chunk) * duration * 96 * 4 * 245 * 35
                        while pending and (
                            len(pending) >= self.workers
                            or inflight_bytes + estimated > memory_limit
                        ):
                            future, size = pending.popleft()
                            shards.append(future.result())
                            inflight_bytes -= size
                        if source is None:
                            with read_segment(segment["path"]) as data:
                                source = {key: data[key] for key in tensor_keys}
                                subcarriers, receivers = (
                                    data["subcarriers"],
                                    data["receivers"],
                                )
                        arrays = {
                            key: np.asfortranarray(
                                np.stack(
                                    [
                                        value[r["start"] : r["stop"]]
                                        for r in chunk.iter_rows(named=True)
                                    ]
                                )
                            )
                            for key, value in source.items()
                        }
                        arrays.update(
                            subcarriers=subcarriers,
                            receivers=receivers,
                            target=chunk["target"].to_numpy().astype(np.int8),
                        )
                        pending.append(
                            (
                                writer.submit(
                                    _verified_shard,
                                    path,
                                    arrays,
                                    metadata,
                                    resume_key=resume_key,
                                    compression_level=self.compression_level,
                                    verify_new=self.verify_new_shards,
                                ),
                                estimated,
                            )
                        )
                        inflight_bytes += estimated
            while pending:
                future, _ = pending.popleft()
                shards.append(future.result())
        self.index = pl.DataFrame(
            exported,
            schema={**WINDOW_SCHEMA, "shard": pl.String, "shard_row": pl.Int64},
        )
        atomic_table(self.index, self.output / "window_index.parquet")
        self.shards = pl.DataFrame(shards, schema=SHARD_SCHEMA)
        atomic_table(self.shards, self.output / "shards.parquet")
        assert (
            sum(self.omissions["retained"])
            == len(self.index)
            == sum(self.shards["windows"])
        )
        self.timings["export_verify"] = perf_counter() - started
        segment_rows = self.segments.to_dicts()
        falls = [r for r in segment_rows if r["activity_label"].endswith("_to_fall")]
        representative_id = sorted(
            falls or segment_rows, key=lambda r: (-r["samples"], r["segment_id"])
        )[0]["segment_id"]
        code_files = [
            Path(__file__),
            Path(__file__).with_name("amplitude_pipeline.py"),
            Path(__file__).with_name("amplitude.py"),
            self.root / "src/native/radio_core/src/amplitude.rs",
            self.root / "src/native/radio_core/src/hampel.rs",
        ]
        code_hashes = {
            str(p.relative_to(self.root))
            if p.is_relative_to(self.root)
            else p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in code_files
            if p.exists()
        }
        atomic_json(
            dict(
                schema="amplitude_sequence_v1",
                dataset=self.name,
                session_id=self.session_id,
                source=self.session.manifest,
                code_sha256=code_hashes,
                backend=dict(
                    name="rust-rayon-he20-magnitude-centered-hampel",
                    version=BACKEND_VERSION,
                    numpy=np.__version__,
                    polars=pl.__version__,
                ),
                parameters=dict(
                    source_hz=120,
                    target_hz=96,
                    normalization=None,
                    amplitude_floor=4.0,
                    attempt_boundary="full [window_start, window_start+duration) inside recorded attempt",
                    sampling="nearest source round; ties upward; no interpolation or anti-alias filter",
                    recording_gap_seconds=self.gap_seconds,
                    hampel_seconds=0.5,
                    threshold=3,
                    min_periods=5,
                    zero_mad="unchanged",
                    durations=list(DURATIONS),
                    overlap=0.5,
                    max_windows_per_shard=self.shard_windows,
                    npy_storage_order="Fortran; logical tensor axes unchanged",
                    compression=f"ZIP deflate level {self.compression_level} for new shards; cached encodings preserved",
                    bounded_writer_tasks=self.workers,
                    writer_memory_budget_mb=self.memory_budget_mb,
                    reload_verification=(
                        "once for new shards"
                        if self.verify_new_shards
                        else "explicit audit only; receipts on resume"
                    ),
                    dtype="float64",
                    tensor_order="window,time,receiver,subcarrier",
                ),
                labels=dict(
                    fall=1,
                    non_fall=0,
                    rule="fall window center in [action cue start,end); omit other fall windows",
                    limitation="approximate action cues, not impact annotations; centered offline filtering uses future samples",
                ),
                counts=dict(
                    attempts=len(self.attempts),
                    selected_attempts=len(self.selected),
                    selected_recordings=len(self.recordings),
                    nonempty_recordings=self.recordings.filter(
                        pl.col("packets") > 0
                    ).height,
                    segments=len(self.segments),
                    windows=len(self.index),
                    candidates=int(self.omissions["candidates"].sum()),
                    omitted=int(self.omissions["omitted"].sum()),
                    classes=self.index.group_by("duration", "target")
                    .len()
                    .sort("duration", "target")
                    .to_dicts(),
                ),
                segment_cache="representative only after export; regenerate earlier stages to rebuild all segments",
                representative_segment=representative_id,
                exclusions=self.selection.filter(~pl.col("selected")).to_dicts(),
                timings_seconds=self.timings,
                split="not assigned; preserve participant/session/trial/attempt groups",
                shards=shards,
            ),
            self.output / "manifest.json",
        )
        for segment in segment_rows:
            if segment["segment_id"] != representative_id:
                import shutil

                segment_path = Path(segment["path"])
                directory = array_directory(segment_path)
                if directory.is_dir() and not directory.is_symlink():
                    shutil.rmtree(directory)
                else:
                    segment_path.unlink(missing_ok=True)
        self.segments = self.segments.with_columns(
            (pl.col("segment_id") == representative_id).alias("cached")
        )
        atomic_table(self.segments, self.output / "segments.parquet")
        self._completed_source = fingerprint(self.session.manifest)
        self._completed_parameters = (self.gap_seconds, self.shard_windows)
        return (
            self.shards.group_by("duration")
            .agg(pl.col("windows", "bytes").sum(), pl.len().alias("shards"))
            .sort("duration")
        )

    def export_v2(self) -> pl.DataFrame:
        """Write the training signal once per segment from staged audit arrays."""
        from .sequence_segments import export_cached_segments

        if self._completed_cache_valid() and (self.output / "manifest.json").exists():
            self.cache_hits.append("export")
            return self.index.group_by("duration").len().rename({"len": "windows"}).sort("duration")
        if not hasattr(self, "segments") or not hasattr(self, "index"):
            raise ValueError("Run preprocessing stages and window indexing first")
        source_metadata = self.session.manifest
        parameters = dict(
            source_hz=120, target_hz=96, normalization=None,
            sampling="nearest source round; ties upward; no interpolation",
            recording_gap_seconds=self.gap_seconds, hampel_seconds=0.5,
            threshold=3, min_periods=5, durations=list(DURATIONS), overlap=0.5,
            dtype="float32", tensor_order="time,receiver,subcarrier",
        )
        result = export_cached_segments(
            self.output, self.output, self.index, self.segments,
            source_metadata=source_metadata, parameters=parameters,
        )
        self.index = pl.read_parquet(self.output / "window_index.parquet")
        self.signals = pl.read_parquet(self.output / "signals.parquet")
        self.timings["export_verify"] = result["seconds"]
        rows = self.segments.to_dicts()
        falls = [r for r in rows if r["activity_label"].endswith("_to_fall")]
        representative = sorted(falls or rows, key=lambda r: (-r["samples"], r["segment_id"]))[0]["segment_id"]
        for segment in rows:
            if segment["segment_id"] != representative:
                import shutil

                directory = array_directory(Path(segment["path"]))
                if directory.is_dir() and not directory.is_symlink():
                    shutil.rmtree(directory)
        self._completed_source = fingerprint(self.session.manifest)
        self._completed_parameters = (self.gap_seconds, self.shard_windows)
        return self.index.group_by("duration").len().rename({"len": "windows"}).sort("duration")
