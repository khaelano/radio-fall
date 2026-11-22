"""Read accepted, explicitly labelled attempts as 120 Hz amplitude epochs.

The classical baselines (``analysis.baselines.wifall`` and
``analysis.baselines.falldefi``) share this adapter. It reads closed sessions
through the native session loader and keeps the recorded 120 Hz grid, treating
the four C5 receivers as four streams. It never reads the neural models'
log-squared-difference exports and never modifies raw recordings; only the
shared ``data/interim/frames`` caches may be created or reused.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .._cache_keys import file_hash
from ..preprocessing import amplitude_pipeline
from ..preprocessing.amplitude_pipeline import (
    AmplitudePacketReader,
    load_amplitude_session,
)
from ..sequence import alignment
from ..sequence.alignment import (
    RECEIVERS,
    SEQUENCE_COLUMNS,
    align_epoch,
    split_packet_epochs,
)

SAMPLE_RATE_HZ = 120
SUBCARRIER_SPACING_HZ = 78125
USABLE_TONES = np.r_[np.arange(-122, -1), np.arange(2, 123)]
"""HE20 physical tone indices excluding the null tones −1, 0 and 1."""
_INTERIOR_TONES = np.r_[np.arange(-120, -1), np.arange(2, 121)]


def interior_subcarriers(count: int) -> tuple[int, ...]:
    """Return ``count`` evenly spaced interior HE20 tones.

    Args:
        count: Number of tones, from 1 to the 238 interior tones.

    Returns:
        Physical tone indices in ascending order, excluding nulls and edges.

    Raises:
        ValueError: If the count is out of range.
    """
    if not 1 <= count <= len(_INTERIOR_TONES):
        raise ValueError(f"count must be between 1 and {len(_INTERIOR_TONES)}")
    positions = np.linspace(0, len(_INTERIOR_TONES) - 1, count, dtype=int)
    return tuple(int(value) for value in _INTERIOR_TONES[positions])


DEFAULT_SUBCARRIERS = interior_subcarriers(30)
"""Thirty fixed interior HE20 tones, excluding nulls and edge indices.

The interior schema avoids edge tones that are zero in inspected C5 captures;
it is fixed across sources and is not fitted to held-out labels or accuracy.
"""


@dataclass(frozen=True)
class AttemptEpoch:
    """One recording epoch of an accepted, mapped attempt.

    Attributes:
        session_id: Recorded session identity.
        group: ``<session_id>/<attempt_key>``, keeping an attempt's data together.
        label: Exact recorded activity label.
        attempt: Attempt row from the resolved session, including review fields.
        phases: Collection cues of this attempt as ``phase``, ``start_ns`` and
            ``end_ns`` dictionaries, with exclusive end times.
        epoch: Index of this epoch within the attempt.
        amplitude: Float amplitudes ``[time, receiver, subcarrier]``; NaN
            marks a missing sample on the nominal grid.
        time_ns: Monotonic time of each grid sample.
    """

    session_id: str
    group: str
    label: str
    attempt: dict[str, Any]
    phases: list[dict[str, Any]]
    epoch: int
    amplitude: np.ndarray
    time_ns: np.ndarray


def fill_short_gaps(
    values: np.ndarray,
    *,
    sample_rate_hz: float = SAMPLE_RATE_HZ,
    max_gap_seconds: float = 0.025,
) -> np.ndarray:
    """Interpolate only short, internally bracketed gaps in one window.

    Args:
        values: Nonnegative amplitude array with time on axis zero. NaN denotes
            missing data. Inputs are never modified.
        sample_rate_hz: Sampling frequency of the nominal time grid.
        max_gap_seconds: Maximum separation of finite bracketing samples;
            zero disables interpolation. There is no extrapolation.

    Returns:
        A copy with eligible gaps filled independently for each signal.

    Raises:
        ValueError: If the shape, rates or observed amplitudes are invalid.
    """
    array = np.asarray(values, dtype=np.float64)
    if (
        array.ndim < 2
        or not array.size
        or not np.isfinite(sample_rate_hz)
        or sample_rate_hz <= 0
        or not np.isfinite(max_gap_seconds)
        or max_gap_seconds < 0
        or np.isinf(array).any()
        or np.any(array[np.isfinite(array)] < 0)
    ):
        raise ValueError(
            "Expected nonnegative amplitudes and finite valid gap settings"
        )
    result = array.copy()
    columns = result.reshape(len(result), -1)
    for column in columns.T:
        finite = np.flatnonzero(np.isfinite(column))
        for left, right in pairwise(finite):
            if (
                right - left > 1
                and (right - left) / sample_rate_hz <= max_gap_seconds + 1e-12
            ):
                column[left : right + 1] = np.linspace(
                    column[left], column[right], right - left + 1
                )
    return result


def usable_receivers(
    values: np.ndarray,
    *,
    minimum_coverage: float,
    max_gap_seconds: float,
    counts: Counter,
    prefix: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Fill short gaps and blank receivers that fail coverage or gap limits.

    The C5 receivers lose short bursts at different times, so each receiver is
    judged on its own instead of requiring all of them at once.

    Args:
        values: Amplitudes ``[time, receiver, tone]`` with NaN for missing data.
        minimum_coverage: Observed fraction a receiver needs before filling.
        max_gap_seconds: Longest finite-bracket separation to interpolate.
        counts: Counter updated with ``<prefix>_receivers_low_coverage`` and
            ``<prefix>_receivers_unfilled_gaps``.
        prefix: Name of the kind of interval being checked.

    Returns:
        A filled copy in which failing receivers are all NaN, and the observed
        coverage of every receiver before filling.
    """
    coverage = np.isfinite(values).mean(axis=(0, 2))
    filled = fill_short_gaps(values, max_gap_seconds=max_gap_seconds)
    usable = coverage >= minimum_coverage
    counts[f"{prefix}_receivers_low_coverage"] += int(np.sum(~usable))
    gaps = ~np.isfinite(filled).all(axis=(0, 2)) & usable
    counts[f"{prefix}_receivers_unfilled_gaps"] += int(np.sum(gaps))
    usable &= ~gaps
    filled[:, ~usable] = np.nan
    return filled, coverage


def sample_count(seconds: float, name: str) -> int:
    """Convert a duration to a positive whole number of 120 Hz samples.

    Args:
        seconds: Duration in seconds.
        name: Parameter name for the error message.

    Returns:
        The number of grid samples.

    Raises:
        ValueError: If the duration is not a positive multiple of 1/120 s.
    """
    value = seconds * SAMPLE_RATE_HZ
    if not np.isfinite(value) or value <= 0 or not np.isclose(value, round(value)):
        raise ValueError(f"{name} must be a positive whole number of 120 Hz samples")
    return round(value)


def loader_code_hashes() -> dict[str, str]:
    """Return SHA-256 hashes of the modules that define epoch reading."""
    return {
        Path(str(module.__file__)).name: file_hash(Path(str(module.__file__)))
        for module in (amplitude_pipeline, alignment)
    } | {Path(__file__).name: file_hash(Path(__file__))}


class RecordedAttempts:
    """Iterate accepted attempts whose labels appear in an explicit mapping.

    The iterator can run once. While it runs, ``identities`` collects source
    provenance, ``channel`` records the shared 5 GHz channel, and ``counts``
    accumulates attempt-level exclusions.

    Args:
        sources: Explicit closed session directories or version-3 archives.
        root: Repository root, containing ``data/annotations`` and derived
            ``data/interim/frames`` caches.
        labels: Exact activity labels to read; other attempts are counted and
            skipped without guessing.
        subcarriers: Fixed physical tone indices; null tones cannot be selected.
        counts: Optional counter to update, so callers can add their own
            exclusion counts to one record.

    Raises:
        ValueError: If sources, labels or tones are invalid.
    """

    def __init__(
        self,
        sources: list[Path],
        *,
        root: Path,
        labels: set[str],
        subcarriers: tuple[int, ...] = DEFAULT_SUBCARRIERS,
        counts: Counter | None = None,
    ) -> None:
        tones = np.asarray(subcarriers)
        if (
            not sources
            or not labels
            or not all(isinstance(label, str) and label for label in labels)
            or tones.ndim != 1
            or not len(tones)
            or not np.issubdtype(tones.dtype, np.integer)
            or len(np.unique(tones)) != len(tones)
            or not np.isin(tones, USABLE_TONES).all()
        ):
            raise ValueError("Invalid sources, label mapping or tones")
        self.sources = [Path(source).resolve() for source in sources]
        self.root = Path(root).resolve()
        self.labels = frozenset(labels)
        self.tones = tones
        self.counts = Counter() if counts is None else counts
        self.identities: list[dict[str, Any]] = []
        self.channel: int | None = None
        self._consumed = False

    @property
    def center_frequency_hz(self) -> float:
        """Return the recorded channel's center frequency after iteration."""
        if self.channel is None:
            raise ValueError("No source has been read yet")
        return 5e9 + 5e6 * self.channel

    def __iter__(self) -> Iterator[AttemptEpoch]:
        """Yield amplitude epochs of accepted, unexcluded, mapped attempts.

        Raises:
            RuntimeError: If iterated a second time.
            ValueError: If sessions are duplicated, a source rate differs from
                120 Hz, or sources do not share one 5 GHz HE20 channel.
        """
        if self._consumed:
            raise RuntimeError("RecordedAttempts can be iterated only once")
        self._consumed = True
        seen = set()
        for source in self.sources:
            name = source.stem if source.suffix == ".zip" else source.name
            session = load_amplitude_session(
                source,
                self.root / "data/interim/frames" / name,
                annotations_dir=self.root / "data/annotations",
                progress=None,
            )
            session_id = session.manifest["session_id"]
            if session_id in seen:
                raise ValueError(f"Duplicate session: {session_id}")
            seen.add(session_id)
            if (
                session.analysis is None
                or session.analysis.nominal_rate_hz != SAMPLE_RATE_HZ
            ):
                raise ValueError(
                    f"Session {session_id} requires nominal 120 Hz sensing"
                )
            profile = (
                session.manifest.get("source_manifest", {})
                .get("environment", {})
                .get("radio_profile", {})
            )
            current_channel = profile.get("channel")
            if (
                profile.get("band") != "5ghz"
                or profile.get("bandwidth_mhz") != 20
                or not isinstance(current_channel, int)
                or current_channel <= 0
                or (self.channel is not None and self.channel != current_channel)
            ):
                raise ValueError("Sources must share one recorded 5 GHz HE20 channel")
            self.channel = current_channel
            self.identities.append(
                {
                    "session_id": session_id,
                    "source": str(source),
                    "source_fingerprint": session.manifest["source_fingerprint"],
                    "frames_fingerprint": session.manifest.get("frames_fingerprint"),
                    "protocol_hash": session.manifest.get("protocol_hash"),
                    "radio_profile": profile,
                }
            )
            reader = AmplitudePacketReader(session, columns=SEQUENCE_COLUMNS)
            for attempt in session.attempts.iter_rows(named=True):
                self.counts["attempts_seen"] += 1
                if attempt["status"] != "accepted" or attempt["inclusion"] == "exclude":
                    self.counts["attempts_excluded"] += 1
                    continue
                label = attempt["activity_label"]
                if label not in self.labels:
                    self.counts["attempts_unmapped_label"] += 1
                    continue
                key = attempt["attempt_key"]
                phases = session.analysis.phases.loc[
                    session.analysis.phases["attempt_key"] == key
                ].to_dict("records")
                frames = [reader.read(key, receiver) for receiver in RECEIVERS]
                frames = [frame for frame in frames if not frame.is_empty()]
                if not frames:
                    self.counts["attempts_without_packets"] += 1
                    continue
                frame = pl.concat(frames).filter(pl.col("is_sensing"))
                for index, epoch in enumerate(split_packet_epochs(frame)):
                    aligned, _ = align_epoch(epoch, rate_hz=SAMPLE_RATE_HZ)
                    yield AttemptEpoch(
                        session_id=session_id,
                        group=f"{session_id}/{key}",
                        label=label,
                        attempt=attempt,
                        phases=phases,
                        epoch=index,
                        amplitude=aligned["amplitude"][:, :, self.tones + 122],
                        time_ns=aligned["time_ns"],
                    )
