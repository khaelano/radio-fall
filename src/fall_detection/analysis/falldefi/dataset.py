"""Adapt preserved ESP32-C5 sessions to per-activity traces for FallDeFi.

FallDeFi records one 10 s trace per activity and localizes the event inside it
(§7). Here a trace is one action cue widened by a margin on both sides. A
non-fall cue longer than the interval, such as a continuous activity segment,
is split into consecutive non-overlapping intervals instead. Countdown cues
supply the training-only resting segments used to calibrate the noise
threshold; each is cut to the recorded epoch, since an attempt's first
packet arrives just after its countdown starts.

The defaults follow the C5 acquisition schedule. Each receiver loses a 0.1 s
burst about every 0.57 s (about 18 % of samples), and the receivers lose
theirs at different times. Coverage and gaps are therefore judged per
receiver: a receiver that fails in one trace is dropped from that trace only,
as all-NaN values, and the trace needs ``minimum_receivers`` of them.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .._cache_keys import file_hash
from .._recorded_attempts import (
    SAMPLE_RATE_HZ,
    SUBCARRIER_SPACING_HZ,
    AttemptEpoch,
    RecordedAttempts,
    interior_subcarriers,
    loader_code_hashes,
    sample_count,
    usable_receivers,
)
from ..preprocessing.sequence_preprocessing import RECEIVERS

_STEP_NS = 1e9 / SAMPLE_RATE_HZ
FALLDEFI_SUBCARRIERS = interior_subcarriers(120)
"""Every other interior tone: the C5 reports 245 tones, and PCA over more
tones averages more noise out of each component."""


@dataclass(frozen=True)
class TraceDataset:
    """Finite activity traces and resting segments with split provenance.

    Attributes:
        traces: Float32 amplitudes ``[time, receiver, subcarrier]``; lengths vary
            and a receiver dropped from a trace is all NaN.
        targets: Binary trace labels, with fall equal to one.
        groups: Session/attempt keys, keeping an attempt's traces together.
        metadata: Label, cue, timing, coverage and interpolation per trace.
        resting: Countdown segments ``[time, receiver, subcarrier]``, with
            dropped receivers all NaN.
        resting_groups: Attempt key of each resting segment.
        provenance: Source identities, parameters, code hashes and exclusions.
    """

    traces: list[np.ndarray]
    targets: np.ndarray
    groups: np.ndarray
    metadata: list[dict[str, Any]]
    resting: list[np.ndarray]
    resting_groups: np.ndarray
    provenance: dict[str, Any]


def _segments(
    epoch: AttemptEpoch,
    *,
    is_fall: bool,
    margin_ns: int,
    interval_ns: int,
) -> list[tuple[str, int, int, dict[str, Any]]]:
    """List the trace and resting intervals defined by an attempt's cues."""
    segments = []
    for phase in epoch.phases:
        start, end = int(phase["start_ns"]), int(phase["end_ns"])
        if phase["phase"] == "preparation":
            segments.append(("resting", start, end, phase))
        elif phase["phase"] == "action" and end - start <= interval_ns:
            segments.append(("cue", start - margin_ns, end + margin_ns, phase))
        elif phase["phase"] == "action" and is_fall:
            segments.append(("long_fall_cue", start, end, phase))
        elif phase["phase"] == "action":
            segments.extend(
                (
                    "interval",
                    start + k * interval_ns,
                    start + (k + 1) * interval_ns,
                    phase,
                )
                for k in range((end - start) // interval_ns)
            )
    return segments


def _slice(
    epoch: AttemptEpoch, start_ns: int, end_ns: int, *, clip: bool
) -> np.ndarray | None:
    """Return grid samples in ``[start_ns, end_ns)``.

    Without ``clip`` the interval must lie inside the epoch. With ``clip`` it
    is cut to the epoch, because the first packet of an attempt arrives a few
    milliseconds after its countdown cue starts.
    """
    times = epoch.time_ns
    first_ns, end_of_epoch_ns = times[0], times[-1] + _STEP_NS
    if clip:
        start_ns, end_ns = max(start_ns, first_ns), min(end_ns, end_of_epoch_ns)
    if start_ns < first_ns or end_ns > end_of_epoch_ns or end_ns <= start_ns:
        return None
    first, stop = np.searchsorted(times, [start_ns, end_ns], side="left")
    return epoch.amplitude[first:stop]


def load_traces(
    sources: list[Path],
    *,
    root: Path,
    fall_labels: tuple[str, ...],
    non_fall_labels: tuple[str, ...],
    margin_seconds: float = 1.0,
    interval_seconds: float = 10.0,
    minimum_seconds: float = 1.0,
    receivers: tuple[str, ...] = RECEIVERS,
    minimum_receivers: int = 2,
    subcarriers: tuple[int, ...] = FALLDEFI_SUBCARRIERS,
    max_gap_seconds: float = 0.25,
    minimum_coverage: float = 0.7,
) -> TraceDataset:
    """Read accepted attempts as activity traces and countdown resting segments.

    Cues are collection instructions, not measured motion boundaries.
    Countdown stillness is an assumption that must be inspected before trusting
    the noise threshold.

    Args:
        sources: Explicit closed session directories or version-3 archives.
        root: Repository root, containing ``data/annotations`` and derived
            ``data/interim/frames`` caches.
        fall_labels: Exact activity labels mapped to fall.
        non_fall_labels: Exact activity labels mapped to non-fall.
        margin_seconds: Time added before and after each action cue.
        interval_seconds: Longest cue kept as one trace; longer non-fall cues
            are split into intervals of this length and longer fall cues are
            excluded, since the fall cannot be localized.
        minimum_seconds: Shortest trace or resting segment kept.
        receivers: Receivers to consider, each standing in for one of the
            paper's links.
        minimum_receivers: Receivers that must pass in a trace or resting
            segment for it to be kept.
        subcarriers: Fixed physical indices; null tones cannot be selected.
        max_gap_seconds: Maximum finite-bracket separation for interpolation;
            the default covers at least 95 % of the scheduled gaps.
        minimum_coverage: Required observed fraction per receiver before
            filling; the schedule alone leaves about 0.82.

    Returns:
        Finite traces, resting segments and provenance. Raw sources are never
        modified; only shared derived frame caches may be created or reused.

    Raises:
        ValueError: If inputs are invalid, sessions are duplicated, source rates
            differ from 120 Hz, or no trace survives.
    """
    margin = sample_count(margin_seconds, "margin_seconds") if margin_seconds else 0
    interval = sample_count(interval_seconds, "interval_seconds")
    minimum = sample_count(minimum_seconds, "minimum_seconds")
    fall, non_fall = set(fall_labels), set(non_fall_labels)
    if (
        fall & non_fall
        or margin_seconds < 0
        or not receivers
        or len(set(receivers)) != len(receivers)
        or isinstance(minimum_receivers, bool)
        or not isinstance(minimum_receivers, int)
        or not 1 <= minimum_receivers <= len(receivers)
        or not set(receivers) <= set(RECEIVERS)
        or not np.isfinite(minimum_coverage)
        or not 0 < minimum_coverage <= 1
        or not np.isfinite(max_gap_seconds)
        or max_gap_seconds < 0
    ):
        raise ValueError(
            "Invalid disjoint label mapping, margin, receivers or gap settings"
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
    traces, targets, groups, metadata = [], [], [], []
    resting, resting_groups = [], []
    outcomes: dict[tuple[str, str, int], str] = {}
    for epoch in attempts:
        attempt = epoch.attempt
        for kind, start_ns, end_ns, phase in _segments(
            epoch,
            is_fall=epoch.label in fall,
            margin_ns=round(margin * _STEP_NS),
            interval_ns=round(interval * _STEP_NS),
        ):
            key = (epoch.group, kind, start_ns)
            prefix = "resting" if kind == "resting" else "trace"
            if outcomes.get(key, "pending") != "pending":
                continue
            if kind == "long_fall_cue":
                outcomes[key] = "fall_cues_longer_than_interval"
                continue
            if (
                start_ns < attempt["started_monotonic_ns"]
                or end_ns > attempt["ended_monotonic_ns"]
            ):
                outcomes[key] = f"{prefix}_outside_attempt"
                continue
            values = _slice(epoch, start_ns, end_ns, clip=kind == "resting")
            if values is None:
                outcomes[key] = "pending"
                continue
            values = values[:, selected]
            if len(values) < minimum:
                outcomes[key] = f"{prefix}_too_short"
                continue
            filled, coverage = usable_receivers(
                values,
                minimum_coverage=minimum_coverage,
                max_gap_seconds=max_gap_seconds,
                counts=counts,
                prefix=prefix,
            )
            used = np.isfinite(filled).all(axis=(0, 2))
            if used.sum() < minimum_receivers:
                outcomes[key] = f"{prefix}_too_few_receivers"
                continue
            outcomes[key] = "accepted"
            if kind == "resting":
                resting.append(filled.astype(np.float32))
                resting_groups.append(epoch.group)
                continue
            traces.append(filled.astype(np.float32))
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
                    "kind": kind,
                    "start_ns": start_ns,
                    "end_ns": end_ns,
                    "cue_start_ns": int(phase["start_ns"]),
                    "cue_end_ns": int(phase["end_ns"]),
                    "duration_seconds": len(filled) / SAMPLE_RATE_HZ,
                    "receiver_coverage": coverage.tolist(),
                    "receivers_used": [
                        name for name, kept in zip(receivers, used, strict=True) if kept
                    ],
                    "interpolated_values": int(
                        np.count_nonzero(~np.isfinite(values[:, used]))
                    ),
                    "annotation_source": "collection_cue",
                }
            )
    for (_, kind, _), outcome in outcomes.items():
        if outcome == "pending":
            prefix = "resting" if kind == "resting" else "trace"
            counts[f"{prefix}_outside_epochs"] += 1
        elif outcome != "accepted":
            counts[outcome] += 1
    if not traces:
        raise ValueError(f"No traces survived: {dict(counts)}")
    tones = [int(tone) for tone in subcarriers]
    provenance = {
        "schema": "falldefi_amplitude_traces",
        "version": 1,
        "sources": attempts.identities,
        "coordinates": {"receivers": list(receivers), "subcarriers": tones},
        "center_frequency_hz": attempts.center_frequency_hz,
        "subcarrier_spacing_hz": SUBCARRIER_SPACING_HZ,
        "parameters": {
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "margin_seconds": margin_seconds,
            "interval_seconds": interval_seconds,
            "minimum_seconds": minimum_seconds,
            "subcarriers": tones,
            "receivers": list(receivers),
            "minimum_receivers": minimum_receivers,
            "fall_labels": sorted(fall),
            "non_fall_labels": sorted(non_fall),
            "minimum_coverage": minimum_coverage,
            "max_gap_seconds": max_gap_seconds,
            "interpolation": "internal linear; finite bracket separation bounded",
            "receiver_policy": "receivers failing coverage or gaps dropped per trace",
            "trace_policy": "action cue plus margin; longer non-fall cues tiled",
            "resting_policy": "countdown cue cut to the epoch; stillness unverified",
        },
        "code_sha256": loader_code_hashes() | {"dataset.py": file_hash(Path(__file__))},
        "counts": dict(counts)
        | {"traces": len(traces), "resting_segments": len(resting)},
    }
    return TraceDataset(
        traces,
        np.asarray(targets, dtype=np.int64),
        np.asarray(groups, dtype=str),
        metadata,
        resting,
        np.asarray(resting_groups, dtype=str),
        provenance,
    )
