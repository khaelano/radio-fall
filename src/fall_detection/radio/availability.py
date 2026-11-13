"""Availability snapshots published by the native acquisition for display.

Rust finalizes capture-time bins once their delivery deadline passes and
journals them to ``availability.jsonl``; late deliveries never revise a bin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

AVAILABILITY_HISTORY_SECONDS = 10


@dataclass(frozen=True)
class AvailabilitySnapshot:
    """Capture-time bins; None denotes pre-run or no longer retained history."""

    receivers: tuple[str, ...]
    first_bin_start_ns: int
    width_ns: int
    grace_ns: int
    packet_counts: tuple[tuple[int | None, ...], ...]

    @classmethod
    def from_json(cls, value: str) -> AvailabilitySnapshot:
        """Parse the native snapshot document.

        Args:
            value: JSON produced by ``NativeAcquisition.availability``.

        Returns:
            The immutable snapshot.
        """
        data = json.loads(value)
        return cls(
            tuple(data["receivers"]),
            int(data["first_bin_start_ns"]),
            int(data["width_ns"]),
            int(data["grace_ns"]),
            tuple(tuple(row) for row in data["packet_counts"]),
        )
