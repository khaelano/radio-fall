"""Adapt preserved ESP32-C5 sessions to amplitude windows for WiFall.

The paper used nine Intel 5300 antenna-pair streams at 100 Hz. This adapter
keeps the recorded 120 Hz grid and treats four C5 receivers as four streams.
It never reads the existing log-squared-difference exports.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .._cache_keys import file_hash
from ..preprocessing import amplitude_pipeline, sequence_preprocessing
from ..preprocessing.amplitude_pipeline import (
    AmplitudePacketReader,
    load_amplitude_session,
)
from ..preprocessing.sequence_preprocessing import (
    RECEIVERS,
    SEQUENCE_COLUMNS,
    align_epoch,
    split_packet_epochs,
)

SAMPLE_RATE_HZ = 120
_USABLE_TONES = np.r_[np.arange(-122, -1), np.arange(2, 123)]
_INTERIOR_TONES = np.r_[np.arange(-120, -1), np.arange(2, 121)]
DEFAULT_SUBCARRIERS = tuple(
    int(value)
    for value in _INTERIOR_TONES[
        np.linspace(0, len(_INTERIOR_TONES) - 1, 30, dtype=int)
    ]
)
"""Thirty fixed interior HE20 tones, excluding nulls and edge indices.

The interior schema avoids edge tones that are zero in inspected C5 captures;
it is fixed across sources and is not fitted to held-out labels or accuracy.
"""


@dataclass(frozen=True)
class WindowDataset:
    """Finite windows with independent resting chunks and split provenance.

    Attributes:
        windows: Float32 amplitude ``[window,time,receiver,subcarrier]``.
        targets: Binary window labels, with fall equal to one.
        groups: Session/attempt keys, keeping overlapping windows together.
        metadata: Label, cue, timing, coverage and interpolation per window.
        stable_windows: Separate countdown chunks in the same tensor order.
        stable_groups: Attempt keys for selecting training-only resting chunks.
        provenance: Source identities, parameters, code hashes and exclusions.
    """

    windows: np.ndarray
    targets: np.ndarray
    groups: np.ndarray
    metadata: list[dict[str, Any]]
    stable_windows: np.ndarray
    stable_groups: np.ndarray
    provenance: dict[str, Any]


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


def _sample_count(seconds: float, name: str) -> int:
    value = seconds * SAMPLE_RATE_HZ
    if not np.isfinite(value) or value <= 0 or not np.isclose(value, round(value)):
        raise ValueError(f"{name} must be a positive whole number of 120 Hz samples")
    return round(value)


def _validated_window(
    values: np.ndarray,
    minimum_coverage: float,
    max_gap_seconds: float,
    counts: Counter,
    prefix: str,
) -> tuple[np.ndarray, list[float], int] | None:
    coverage = np.isfinite(values).mean(axis=(0, 2))
    if np.any(coverage < minimum_coverage):
        counts[f"{prefix}_low_coverage"] += 1
        return None
    filled = fill_short_gaps(values, max_gap_seconds=max_gap_seconds)
    if not np.isfinite(filled).all():
        counts[f"{prefix}_unfilled_gaps"] += 1
        return None
    return (
        filled.astype(np.float32),
        coverage.tolist(),
        int(np.count_nonzero(~np.isfinite(values))),
    )


def load_dataset(
    sources: list[Path],
    *,
    root: Path,
    fall_labels: tuple[str, ...],
    non_fall_labels: tuple[str, ...],
    window_seconds: float = 2.0,
    hop_seconds: float = 1.0,
    subcarriers: tuple[int, ...] = DEFAULT_SUBCARRIERS,
    max_gap_seconds: float = 0.025,
    minimum_coverage: float = 0.9,
) -> WindowDataset:
    """Read accepted recorded attempts using the shared native session loader.

    Classification windows require their center inside an action cue for both
    classes. Resting chunks must lie completely inside a countdown cue. Cues
    are collection instructions, not measured motion boundaries; countdown
    stillness must be checked before treating these chunks as a stable profile.

    Args:
        sources: Explicit closed session directories or version-3 archives.
        root: Repository root, containing ``data/annotations`` and derived
            ``data/interim/frames`` caches.
        fall_labels: Exact activity labels mapped to fall.
        non_fall_labels: Exact activity labels mapped to non-fall.
        window_seconds: Window duration, retaining the nominal 120 Hz grid.
        hop_seconds: Sliding-window hop within each separate attempt/epoch.
        subcarriers: Fixed physical indices; null tones cannot be selected.
        max_gap_seconds: Maximum finite-bracket separation for interpolation.
        minimum_coverage: Required observed fraction per receiver before filling.

    Returns:
        Finite amplitude windows with split groups, stable chunks and provenance.
        Raw sources are never modified; only shared derived frame caches may be
        created or reused.

    Raises:
        ValueError: If inputs are invalid, sessions are duplicated, source rates
            differ from 120 Hz, or no classification windows survive.
    """
    samples = _sample_count(window_seconds, "window_seconds")
    hop = _sample_count(hop_seconds, "hop_seconds")
    fall, non_fall = set(fall_labels), set(non_fall_labels)
    tones = np.asarray(subcarriers)
    if (
        not sources
        or not (fall | non_fall)
        or fall & non_fall
        or not all(isinstance(label, str) and label for label in fall | non_fall)
        or tones.ndim != 1
        or not len(tones)
        or not np.issubdtype(tones.dtype, np.integer)
        or len(np.unique(tones)) != len(tones)
        or not np.isin(tones, _USABLE_TONES).all()
        or not np.isfinite(minimum_coverage)
        or not 0 < minimum_coverage <= 1
        or not np.isfinite(max_gap_seconds)
        or max_gap_seconds < 0
    ):
        raise ValueError(
            "Invalid sources, disjoint label mapping, tones or gap settings"
        )
    root = Path(root).resolve()
    windows, targets, groups, metadata = [], [], [], []
    stable, stable_groups, identities = [], [], []
    counts: Counter = Counter()
    seen = set()
    channel = None
    for source in sources:
        source = Path(source).resolve()
        name = source.stem if source.suffix == ".zip" else source.name
        session = load_amplitude_session(
            source,
            root / "data/interim/frames" / name,
            annotations_dir=root / "data/annotations",
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
            raise ValueError(f"Session {session_id} requires nominal 120 Hz sensing")
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
            or (channel is not None and channel != current_channel)
        ):
            raise ValueError("Sources must share one recorded 5 GHz HE20 channel")
        channel = current_channel
        identities.append(
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
            counts["attempts_seen"] += 1
            if attempt["status"] != "accepted" or attempt["inclusion"] == "exclude":
                counts["attempts_excluded"] += 1
                continue
            label = attempt["activity_label"]
            if label not in fall | non_fall:
                counts["attempts_unmapped_label"] += 1
                continue
            key = attempt["attempt_key"]
            group = f"{session_id}/{key}"
            phases = session.analysis.phases.loc[
                session.analysis.phases["attempt_key"] == key
            ].to_dict("records")
            frames = [reader.read(key, receiver) for receiver in RECEIVERS]
            frames = [frame for frame in frames if not frame.is_empty()]
            if not frames:
                counts["attempts_without_packets"] += 1
                continue
            frame = pl.concat(frames).filter(pl.col("is_sensing"))
            for epoch_index, epoch in enumerate(split_packet_epochs(frame)):
                aligned, _ = align_epoch(epoch, rate_hz=SAMPLE_RATE_HZ)
                values = aligned["amplitude"][:, :, tones + 122]
                times = aligned["time_ns"]
                for start in range(0, len(values) - samples + 1, hop):
                    stop = start + samples
                    center_ns = int(times[start] + round(window_seconds * 0.5 * 1e9))
                    action = any(
                        phase["phase"] == "action"
                        and phase["start_ns"] <= center_ns < phase["end_ns"]
                        for phase in phases
                    )
                    # The right edge is exclusive, just like the cue intervals.
                    end_ns = int(times[stop - 1] + round(1e9 / SAMPLE_RATE_HZ))
                    if (
                        int(times[start]) < attempt["started_monotonic_ns"]
                        or end_ns > attempt["ended_monotonic_ns"]
                    ):
                        counts["windows_outside_attempt"] += 1
                        continue
                    resting = any(
                        phase["phase"] == "preparation"
                        and phase["start_ns"] <= int(times[start])
                        and end_ns <= phase["end_ns"]
                        for phase in phases
                    )
                    if not (action or resting):
                        counts["windows_outside_selected_cues"] += 1
                        continue
                    prefix = "action" if action else "stable"
                    checked = _validated_window(
                        values[start:stop],
                        minimum_coverage,
                        max_gap_seconds,
                        counts,
                        prefix,
                    )
                    if checked is None:
                        continue
                    window, coverage, interpolated = checked
                    if resting:
                        stable.append(window)
                        stable_groups.append(group)
                    if action:
                        windows.append(window)
                        targets.append(int(label in fall))
                        groups.append(group)
                        metadata.append(
                            {
                                "session_id": session_id,
                                "participant_id": attempt["participant_id"],
                                "attempt_key": key,
                                "activity_label": label,
                                "scenario_id": attempt["scenario_id"],
                                "review_revision": attempt["review_revision"],
                                "epoch": epoch_index,
                                "start_ns": int(times[start]),
                                "center_ns": center_ns,
                                "end_ns": end_ns,
                                "receiver_coverage": coverage,
                                "interpolated_values": interpolated,
                                "annotation_source": "collection_cue",
                            }
                        )
    if not windows:
        raise ValueError(f"No classification windows survived: {dict(counts)}")
    shape = (0, samples, len(RECEIVERS), len(tones))
    provenance = {
        "schema": "wifall_amplitude_windows",
        "version": 1,
        "sources": identities,
        "coordinates": {
            "receivers": list(RECEIVERS),
            "subcarriers": [int(tone) for tone in tones],
        },
        "center_frequency_hz": 5e9 + 5e6 * channel,
        "subcarrier_spacing_hz": 78125,
        "parameters": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "window_seconds": window_seconds,
            "hop_seconds": hop_seconds,
            "subcarriers": [int(tone) for tone in tones],
            "receivers": list(RECEIVERS),
            "fall_labels": sorted(fall),
            "non_fall_labels": sorted(non_fall),
            "minimum_coverage": minimum_coverage,
            "max_gap_seconds": max_gap_seconds,
            "interpolation": "internal linear; finite bracket separation bounded",
            "label_policy": "window center inside action cue for both classes",
            "stable_policy": "whole window inside countdown cue; stillness unverified",
        },
        "code_sha256": {
            Path(str(module.__file__)).name: file_hash(Path(str(module.__file__)))
            for module in (amplitude_pipeline, sequence_preprocessing)
        }
        | {"dataset.py": file_hash(Path(__file__))},
        "counts": dict(counts)
        | {"windows": len(windows), "stable_windows": len(stable)},
    }
    return WindowDataset(
        np.stack(windows),
        np.asarray(targets, dtype=np.int64),
        np.asarray(groups, dtype=str),
        metadata,
        np.stack(stable) if stable else np.empty(shape, dtype=np.float32),
        np.asarray(stable_groups, dtype=str),
        provenance,
    )
