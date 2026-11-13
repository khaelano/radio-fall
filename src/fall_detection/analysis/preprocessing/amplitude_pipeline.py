"""Columnar amplitude packet reading and native preparation from Parquet frames."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from ..session_frames import AnalysisSession, load_analysis_session

COLUMNS = [
    "attempt_key",
    "attempt_id",
    "receiver_id",
    "is_sensing",
    "time_source",
    "time_seconds",
    "capture_time_ns",
    "phase",
    "driver_valid",
    "sig_mode",
    "bandwidth",
    "stbc",
    "first_word",
    "len",
    "csi_i",
    "csi_q",
    "attempt_started_monotonic_ns",
]


@dataclass(frozen=True)
class AmplitudeSession:
    """Validated session tables with Polars selection tables.

    Attributes:
        path: Directory of the converted frame tables.
        manifest: Source identity; ``source_fingerprint`` joins raw data, review
            decisions, and analysis semantics to derived exports.
        attempts: One row per attempt.
        analysis: The pandas-based analysis session that serves packets.
    """

    path: Path
    manifest: dict
    attempts: pl.DataFrame
    analysis: AnalysisSession | None = None


def load_amplitude_session(
    source: str | Path,
    frames_dir: str | Path,
    *,
    annotations_dir: str | Path | None = None,
    progress=print,
) -> AmplitudeSession:
    """Open a session for preprocessing, converting its journals when needed.

    Args:
        source: Raw session archive or directory containing journals.
        frames_dir: Derived directory for the typed frame tables, outside raw data.
        annotations_dir: Directory of reviews; see ``load_analysis_session``.
        progress: Optional status callback.

    Returns:
        The session with its attempt table loaded in Polars.
    """
    analysis = load_analysis_session(
        source, frames_dir, annotations_dir=annotations_dir, progress=progress
    )
    return AmplitudeSession(
        analysis.path,
        analysis.manifest,
        pl.from_pandas(analysis.attempts, nan_to_null=True),
        analysis,
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
    """Read one attempt/receiver recording at a time from converted frames."""

    def __init__(
        self,
        session: AmplitudeSession | AnalysisSession,
        *,
        columns: list[str] | None = None,
    ):
        # Accept an AmplitudeSession or anything exposing ``packets``.
        analysis = getattr(session, "analysis", session)
        if analysis is None or not hasattr(analysis, "packets"):
            raise ValueError("Session has no analysis tables to read packets from")
        self.columns = COLUMNS if columns is None else columns
        self.session = analysis

    def read(self, attempt_key: str, receiver_id: str) -> pl.DataFrame:
        """Read one recording with the requested columns, sorted by capture time."""
        table = self.session.packets(attempt_key, receiver_id, self.columns)
        return pl.from_arrow(table)

    def close(self) -> None:
        """Release resources; the frame tables are opened per read."""


def prepare_recording(
    packets: pl.DataFrame, *, magnitude_only: bool = False
) -> AmplitudeRecording:
    """Decode, physically align, mask and normalize a recording in Rust.

    Args:
        packets: Polars rows of one recording from the analysis packet contract.
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
        "sig_mode",
        "bandwidth",
        "stbc",
        "len",
        "csi_i",
        "csi_q",
        "first_word",
        "time_seconds",
        "capture_time_ns",
    ]
    if any(frame[name].null_count() for name in required):
        raise ValueError("Null CSI payload, layout or timestamp")
    if any(frame.schema[name] != pl.List(pl.Int16) for name in ("csi_i", "csi_q")):
        raise ValueError("CSI arrays must use the Parquet signed-int16 contract")
    if frame.filter(
        (pl.col("sig_mode") != 4)
        | (pl.col("bandwidth") != 0)
        | (pl.col("stbc") != 0)
        | ~pl.col("csi_i").list.len().is_in([245, 256])
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
        i.values.slice(start, stop - start)
        .to_numpy()
        .astype(np.int16, copy=False)
        .tobytes(),
        q.values.slice(qstart, qstop - qstart)
        .to_numpy()
        .astype(np.int16, copy=False)
        .tobytes(),
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
        (
            None
            if magnitude_only
            else np.frombuffer(normalized, dtype=np.float64).reshape(shape, order="F")
        ),
        np.frombuffer(lower, dtype=np.float64),
        np.frombuffer(upper, dtype=np.float64),
    )
