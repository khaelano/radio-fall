"""Adapt preserved ESP32-C5 sessions to represented windows for WiFall.

Windows of two seconds slide with a one-second hop inside each recording
epoch. A window whose center lies in an action cue is classified; a window
lying wholly inside a countdown cue is a resting chunk for the activity
profile. Cues are collection instructions, not measured motion boundaries,
and countdown stillness has not been inspected.

Receivers are judged per window, as for FallDeFi: each C5 receiver loses a
0.1 s burst about every 0.57 s and the receivers lose theirs at different
times, so a receiver that fails coverage or the gap limit is dropped from that
window only, and a window needs ``minimum_receivers`` of them. Each window is
represented immediately (see ``representation.py``), which keeps memory small
enough for many tones and long continuous segments.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..._cache_keys import file_hash
from ...sequence.alignment import RECEIVERS
from .._recorded_attempts import (
    SAMPLE_RATE_HZ,
    SUBCARRIER_SPACING_HZ,
    RecordedAttempts,
    interior_subcarriers,
    loader_code_hashes,
    sample_count,
    usable_receivers,
)
from .representation import STATISTIC_NAMES, Representations, receiver_representation

WIFALL_SUBCARRIERS = interior_subcarriers(120)
"""Every other interior tone; the C5 reports 245 tones, not the Intel 5300's 30."""


@dataclass(frozen=True)
class WindowSet:
    """Represented windows and resting streams with split provenance.

    Attributes:
        windows: Representations of the classification windows.
        targets: Binary window labels, with fall equal to one.
        groups: Session/attempt keys, keeping overlapping windows together.
        metadata: Label, cue, timing, receivers and coverage per window.
        resting_streams: Activity streams of resting chunks
            ``[chunk, time, receiver]``, NaN for dropped receivers.
        resting_groups: Attempt key of each resting chunk.
        provenance: Source identities, parameters, code hashes and exclusions.
    """

    windows: Representations
    targets: np.ndarray
    groups: np.ndarray
    metadata: list[dict[str, Any]]
    resting_streams: np.ndarray
    resting_groups: np.ndarray
    provenance: dict[str, Any]


def _represent(
    values: np.ndarray, *, smoothing_samples: int, entropy_bins: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Represent each usable receiver of one window, NaN for the others."""
    time, receivers = values.shape[:2]
    statistics = np.full((receivers, len(STATISTIC_NAMES)), np.nan)
    singular = np.full((receivers, 3), np.nan)
    streams = np.full((time, receivers), np.nan)
    for receiver in range(receivers):
        if np.isnan(values[:, receiver]).all():
            continue
        statistics[receiver], singular[receiver], streams[:, receiver] = (
            receiver_representation(
                values[:, receiver],
                sample_rate_hz=SAMPLE_RATE_HZ,
                smoothing_samples=smoothing_samples,
                entropy_bins=entropy_bins,
            )
        )
    return statistics, singular, streams


def load_windows(
    sources: list[Path],
    *,
    root: Path,
    fall_labels: tuple[str, ...],
    non_fall_labels: tuple[str, ...],
    window_seconds: float = 2.0,
    hop_seconds: float = 1.0,
    receivers: tuple[str, ...] = RECEIVERS,
    minimum_receivers: int = 2,
    subcarriers: tuple[int, ...] = WIFALL_SUBCARRIERS,
    max_gap_seconds: float = 0.25,
    minimum_coverage: float = 0.7,
    smoothing_samples: int = 5,
    entropy_bins: int = 16,
) -> WindowSet:
    """Read accepted recorded attempts as represented windows.

    Args:
        sources: Explicit closed session directories or version-3 archives.
        root: Repository root, containing ``data/annotations`` and derived
            ``data/interim/frames`` caches.
        fall_labels: Exact activity labels mapped to fall.
        non_fall_labels: Exact activity labels mapped to non-fall.
        window_seconds: Window duration on the 120 Hz grid.
        hop_seconds: Sliding-window hop within each epoch.
        receivers: Receivers to consider.
        minimum_receivers: Receivers that must pass in a window.
        subcarriers: Fixed physical indices; null tones cannot be selected.
        max_gap_seconds: Maximum finite-bracket separation for interpolation;
            the default covers at least 95 % of the scheduled gaps.
        minimum_coverage: Observed fraction a receiver needs before filling;
            the schedule alone leaves about 0.82.
        smoothing_samples: Neighborhood m of equation 9.
        entropy_bins: Histogram bins for the signal entropy.

    Returns:
        Represented windows, resting streams and provenance. Raw sources are
        never modified; only shared derived frame caches may be created.

    Raises:
        ValueError: If inputs are invalid, sessions are duplicated, source rates
            differ from 120 Hz, or no classification window survives.
    """
    samples = sample_count(window_seconds, "window_seconds")
    hop = sample_count(hop_seconds, "hop_seconds")
    fall, non_fall = set(fall_labels), set(non_fall_labels)
    if (
        fall & non_fall
        or not receivers
        or len(set(receivers)) != len(receivers)
        or not set(receivers) <= set(RECEIVERS)
        or isinstance(minimum_receivers, bool)
        or not isinstance(minimum_receivers, int)
        or not 1 <= minimum_receivers <= len(receivers)
        or not np.isfinite(minimum_coverage)
        or not 0 < minimum_coverage <= 1
        or not np.isfinite(max_gap_seconds)
        or max_gap_seconds < 0
    ):
        raise ValueError(
            "Invalid disjoint label mapping, receivers, coverage or gap settings"
        )
    selected = [RECEIVERS.index(receiver) for receiver in receivers]
    counts: Counter = Counter()
    attempts = RecordedAttempts(
        sources,
        root=root,
        labels=fall | non_fall,
        subcarriers=subcarriers,
        counts=counts,
    )
    statistics, singular, streams = [], [], []
    targets, groups, metadata = [], [], []
    resting, resting_groups = [], []
    for epoch in attempts:
        attempt, phases = epoch.attempt, epoch.phases
        values, times = epoch.amplitude[:, selected], epoch.time_ns
        for start in range(0, len(values) - samples + 1, hop):
            stop = start + samples
            center_ns = int(times[start] + round(window_seconds * 0.5 * 1e9))
            # The right edge is exclusive, just like the cue intervals.
            end_ns = int(times[stop - 1] + round(1e9 / SAMPLE_RATE_HZ))
            action = any(
                phase["phase"] == "action"
                and phase["start_ns"] <= center_ns < phase["end_ns"]
                for phase in phases
            )
            if (
                int(times[start]) < attempt["started_monotonic_ns"]
                or end_ns > attempt["ended_monotonic_ns"]
            ):
                counts["windows_outside_attempt"] += 1
                continue
            rest = any(
                phase["phase"] == "preparation"
                and phase["start_ns"] <= int(times[start])
                and end_ns <= phase["end_ns"]
                for phase in phases
            )
            if not (action or rest):
                counts["windows_outside_selected_cues"] += 1
                continue
            prefix = "action" if action else "resting"
            filled, coverage = usable_receivers(
                values[start:stop],
                minimum_coverage=minimum_coverage,
                max_gap_seconds=max_gap_seconds,
                counts=counts,
                prefix=prefix,
            )
            used = np.isfinite(filled).all(axis=(0, 2))
            if used.sum() < minimum_receivers:
                counts[f"{prefix}_too_few_receivers"] += 1
                continue
            stats, values_svd, stream = _represent(
                filled,
                smoothing_samples=smoothing_samples,
                entropy_bins=entropy_bins,
            )
            if rest:
                resting.append(stream.astype(np.float32))
                resting_groups.append(epoch.group)
            if not action:
                continue
            statistics.append(stats)
            singular.append(values_svd)
            streams.append(stream.astype(np.float32))
            targets.append(int(epoch.label in fall))
            groups.append(epoch.group)
            metadata.append(
                {
                    "session_id": epoch.session_id,
                    "participant_id": attempt["participant_id"],
                    "attempt_key": attempt["attempt_key"],
                    "activity_label": epoch.label,
                    "scenario_id": attempt["scenario_id"],
                    "review_revision": attempt["review_revision"],
                    "epoch": epoch.epoch,
                    "start_ns": int(times[start]),
                    "center_ns": center_ns,
                    "end_ns": end_ns,
                    "receiver_coverage": coverage.tolist(),
                    "receivers_used": [
                        name for name, kept in zip(receivers, used, strict=True) if kept
                    ],
                    "annotation_source": "collection_cue",
                }
            )
    if not targets:
        raise ValueError(f"No classification windows survived: {dict(counts)}")
    tones = [int(tone) for tone in subcarriers]
    provenance = {
        "schema": "wifall_window_representations",
        "version": 2,
        "sources": attempts.identities,
        "coordinates": {"receivers": list(receivers), "subcarriers": tones},
        "center_frequency_hz": attempts.center_frequency_hz,
        "subcarrier_spacing_hz": SUBCARRIER_SPACING_HZ,
        "parameters": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "window_seconds": window_seconds,
            "hop_seconds": hop_seconds,
            "subcarriers": tones,
            "receivers": list(receivers),
            "minimum_receivers": minimum_receivers,
            "fall_labels": sorted(fall),
            "non_fall_labels": sorted(non_fall),
            "minimum_coverage": minimum_coverage,
            "max_gap_seconds": max_gap_seconds,
            "smoothing_samples": smoothing_samples,
            "entropy_bins": entropy_bins,
            "interpolation": "internal linear; finite bracket separation bounded",
            "receiver_policy": "receivers failing coverage or gaps dropped per window",
            "label_policy": "window center inside action cue for both classes",
            "resting_policy": "whole window inside countdown cue; stillness unverified",
        },
        "code_sha256": loader_code_hashes()
        | {
            name: file_hash(Path(__file__).with_name(name))
            for name in ("dataset.py", "representation.py")
        },
        "counts": dict(counts)
        | {"windows": len(targets), "resting_windows": len(resting)},
    }
    shape = (0, samples, len(receivers))
    return WindowSet(
        Representations(
            np.asarray(statistics),
            np.asarray(singular),
            np.asarray(streams, dtype=np.float32),
        ),
        np.asarray(targets, dtype=np.int64),
        np.asarray(groups, dtype=str),
        metadata,
        np.asarray(resting, dtype=np.float32) if resting else np.empty(shape),
        np.asarray(resting_groups, dtype=str),
        provenance,
    )
