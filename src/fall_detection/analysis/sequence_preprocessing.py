"""Sequence alignment primitives and verified source/export access.

Experiment selection, transformations, cue labeling, and stage orchestration
live in notebooks/latest/02_preprocess.ipynb.
"""

import hashlib
import itertools
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZipFile

import numpy as np
import polars as pl

from .amplitude_pipeline import (
    COLUMNS,
    AmplitudeSession,
    load_amplitude_session,
    prepare_recording,
)
from .sequence_cache import (
    file_hash,
    stamp,
)

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


RECEIVERS = ("rx-1", "rx-2", "rx-3", "rx-4")
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


def squared_difference(values: np.ndarray) -> np.ndarray:
    """Difference adjacent samples in one segment, preserving NaN propagation."""
    result = np.full_like(values, np.nan)
    result[1:] = np.square(values[1:] - values[:-1])
    return result


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
    return [frame.slice(a, b - a) for a, b in itertools.pairwise(bounds) if b > a]


def align_epoch(
    frame: pl.DataFrame, *, rate_hz: int = 96
) -> tuple[dict[str, np.ndarray], list[dict]]:
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
    rounds = (
        np.arange(highest - lowest + 1, dtype=np.int64)
        if rate_hz == 120
        else source_rounds(0, (highest - lowest) * 96 // 120 + 1)
    )
    amplitude = np.full((len(rounds), 4, 245), np.nan)
    capture = np.full((len(rounds), 4), -1, dtype=np.int64)
    origins = []
    for r, receiver in enumerate(RECEIVERS):
        if receiver not in decoded:
            stats.append(
                {
                    "receiver": receiver,
                    "packets": 0,
                    "duplicates": 0,
                    "wraps": 0,
                    "gap_rounds": [],
                    "gap_counts": [],
                }
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
    times = origin + np.rint(np.arange(len(rounds)) / rate_hz * 1e9).astype(np.int64)
    return {
        "amplitude": amplitude,
        "valid": np.isfinite(amplitude),
        "sequence": ((anchor + rounds) % _MODULUS).astype(np.uint32),
        "sequence_offset": rounds,
        "time_ns": times,
        "capture_time_ns": capture,
        "subcarriers": np.arange(-122, 123),
        "receivers": np.asarray(RECEIVERS),
    }, stats


@dataclass
class SequenceArtifacts:
    """Locate verified sources and validate a parameterized derived export."""

    root: Path
    name: str
    session_id: str
    parameters: dict
    cache_hits: list = field(default_factory=list)

    def load_source(self) -> AmplitudeSession:
        """Open verified session tables, reusing an unchanged local source receipt."""
        from ..storage import session_archive_path
        from . import phase_signals, session_parquet

        source = session_archive_path(self.root, self.session_id)
        directory = self.root / "data/interim/parquet" / self.session_id
        manifest_path = directory / "session.json"
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
            trusted = receipt == {"files": identities, "code": code}
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
                atomic_json({"files": identities, "code": code}, checkpoint)
                self.cache_hits.append("source")
                return AmplitudeSession(
                    directory, cached, pl.read_parquet(directory / "attempts.parquet")
                )
        except (OSError, ValueError, KeyError, BadZipFile):
            pass
        session = load_amplitude_session(source, directory)
        atomic_json(
            {
                "files": {str(p): stamp(p) for p in paths},
                "code": [
                    file_hash(Path(m.__file__))
                    for m in (session_parquet, phase_signals)
                ],
            },
            checkpoint,
        )
        return session

    @property
    def output(self) -> Path:
        """Return the derived directory for the explicitly selected sample rate."""
        rate = self.parameters["target_hz"]
        if rate not in (96, 120):
            raise ValueError("Unsupported sequence sample rate")
        return self.root / "data/processed/amplitude_sequence" / f"{rate}hz" / self.name

    def load_exported(self, *, verify_hashes: bool = False) -> pl.DataFrame:
        """Load completed metadata and optionally audit all signal hashes."""
        manifest = json.loads((self.output / "manifest.json").read_text())
        parameters = manifest.get("parameters", {})
        source = manifest.get("source")
        expected_source = self.session.manifest.get("source_fingerprint")
        expected_rate = self.parameters["target_hz"]
        if (
            manifest.get("schema") != "amplitude_sequence"
            or manifest.get("version")
            != (3 if self.parameters["target_hz"] == 120 else 2)
            or (not expected_source)
            or (not isinstance(source, dict))
            or (source.get("source_fingerprint") != expected_source)
            or (not isinstance(parameters, dict))
            or (parameters.get("dtype") != "float32")
            or (parameters.get("target_hz") != expected_rate)
            or (any(parameters.get(k) != v for k, v in self.parameters.items()))
        ):
            raise ValueError("Export source, schema or preprocessing parameters differ")
        for filename, digest in manifest["metadata_sha256"].items():
            if file_hash(self.output / filename) != digest:
                raise ValueError(f"Export metadata differs: {filename}")
        signals = pl.read_parquet(self.output / "signals.parquet")
        for row in signals.iter_rows(named=True):
            path = (self.output / row["signal"]).resolve()
            if (
                not path.is_relative_to(self.output.resolve())
                or path.stat().st_size != row["bytes"]
                or (verify_hashes and file_hash(path) != row["sha256"])
            ):
                raise ValueError(f"Export signal differs: {path}")
            if expected_rate == 120:
                presence = (self.output / row["presence"]).resolve()
                if (
                    not presence.is_relative_to(self.output.resolve())
                    or not presence.is_file()
                    or (verify_hashes and file_hash(presence) != row["presence_sha256"])
                ):
                    raise ValueError(f"Export presence mask differs: {presence}")
        self.index = pl.read_parquet(self.output / "window_index.parquet")
        self.segments = pl.read_parquet(self.output / "segments.parquet")
        if len(self.index) != manifest["counts"]["windows"]:
            raise ValueError("Export window count differs")
        self.signals = signals
        self.timings = manifest.get("timings_seconds", {})
        return (
            self.index.group_by("duration")
            .len()
            .rename({"len": "windows"})
            .sort("duration")
        )
