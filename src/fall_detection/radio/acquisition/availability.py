"""Causal availability bins, independent of CSI feature selection or training."""

from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock
from typing import Callable


class AvailabilityGrid:
    """Finalize receiver bins once; late delivery cannot revise old inputs."""

    def __init__(
        self,
        receivers: tuple[str, ...],
        start_ns: int,
        *,
        bin_hz: int = 50,
        grace_ms: int = 100,
        emit: Callable[[dict], None] | None = None,
    ) -> None:
        self.receivers = receivers
        self.start_ns = start_ns
        self.width_ns = 1_000_000_000 // bin_hz
        self.grace_ns = grace_ms * 1_000_000
        self.emit = emit or (lambda value: None)
        self.next_bin = 0
        self._counts = defaultdict(int)
        self._arrivals = {r: deque() for r in receivers}
        self._latest = {r: None for r in receivers}
        self._lock = RLock()
        self.timely = defaultdict(int)
        self.late = defaultdict(int)

    def observe(self, receiver: str, captured_ns: int, arrived_ns: int) -> bool:
        """Track packet availability without substituting or interpolating CSI."""
        if receiver not in self._arrivals:
            raise ValueError("unknown receiver")
        with self._lock:
            index = (captured_ns - self.start_ns) // self.width_ns
            if index < 0:
                return False
            end = self.start_ns + (index + 1) * self.width_ns
            timely = arrived_ns <= end + self.grace_ns and index >= self.next_bin
            if timely:
                self._counts[receiver, index] += 1
                self.timely[receiver] += 1
            else:
                self.late[receiver] += 1
            history = self._arrivals[receiver]
            if len(history) >= 2048:
                raise BufferError("availability history exceeded bounded capacity")
            history.append((captured_ns, arrived_ns))
            return timely

    def advance(self, now_ns: int) -> list[dict]:
        """Emit finalized bins through now, preserving capture and arrival clocks."""
        rows = []
        with self._lock:
            while (
                self.start_ns + (self.next_bin + 1) * self.width_ns + self.grace_ns
                <= now_ns
            ):
                index = self.next_bin
                end = self.start_ns + (index + 1) * self.width_ns
                deadline = end + self.grace_ns
                row = dict(
                    schema_version=1,
                    bin=index,
                    start_ns=end - self.width_ns,
                    end_ns=end,
                    deadline_ns=deadline,
                    receivers={},
                )
                for receiver in self.receivers:
                    remaining = deque()
                    latest = self._latest[receiver]
                    for captured, arrived in self._arrivals[receiver]:
                        if captured < end and arrived <= deadline:
                            latest = (
                                captured if latest is None else max(latest, captured)
                            )
                        else:
                            remaining.append((captured, arrived))
                    self._arrivals[receiver] = remaining
                    self._latest[receiver] = latest
                    count = self._counts.pop((receiver, index), 0)
                    row["receivers"][receiver] = dict(
                        available=count > 0,
                        packet_count=count,
                        age_ms=None
                        if latest is None
                        else max(0, (end - latest) / 1_000_000),
                    )
                self.next_bin += 1
                self.emit(row)
                rows.append(row)
        return rows


class RoundReceipts:
    """Join transmitter logs to receiver deliveries, including all-stream silence."""

    def __init__(
        self,
        receivers: tuple[str, ...],
        grid: AvailabilityGrid,
        emit: Callable[..., None],
    ) -> None:
        self.receivers = receivers
        self.grid = grid
        self.emit = emit
        self.pending = {}
        self.early = {}
        self.finalized = set()
        self._recent = deque()
        self._lock = RLock()

    def round(self, value: dict) -> None:
        """Register a logged sensing round, never inventing untransmitted rounds."""
        if value.get("skipped_rounds") or value.get("host_capture_ns") is None:
            return
        key = value["transmitter_boot_id"], value["sequence"]
        captured = value["host_capture_ns"]
        index = (captured - self.grid.start_ns) // self.grid.width_ns
        deadline = (
            self.grid.start_ns + (index + 1) * self.grid.width_ns + self.grid.grace_ns
        )
        with self._lock:
            if len(self.pending) >= 2048:
                raise BufferError("round receipt tracker overflow")
            if key not in self.finalized:
                self.pending[key] = dict(
                    value, deadline_ns=deadline, receipts=self.early.pop(key, {})
                )

    def receive(self, boot: int, sequence: int, receiver: str, arrival_ns: int) -> None:
        """Track earliest delivery for a receiver without revising finalized rounds."""
        key = boot, sequence
        with self._lock:
            if key in self.finalized:
                return
            if key in self.pending:
                receipts = self.pending[key]["receipts"]
            else:
                if len(self.early) >= 2048:
                    self.early.pop(next(iter(self.early)))
                receipts = self.early.setdefault(key, {})
            receipts[receiver] = min(arrival_ns, receipts.get(receiver, arrival_ns))

    def advance(self, now_ns: int) -> None:
        """Finalize round masks by deadline; unavailable cause remains unknown."""
        with self._lock:
            for key, value in list(self.pending.items()):
                if value["deadline_ns"] > now_ns:
                    continue
                receipts = value.pop("receipts")
                self.emit(
                    "round_availability",
                    **value,
                    availability={
                        receiver: receiver in receipts
                        and receipts[receiver] <= value["deadline_ns"]
                        for receiver in self.receivers
                    },
                )
                del self.pending[key]
                self.finalized.add(key)
                self._recent.append(key)
                if len(self._recent) > 4096:
                    self.finalized.discard(self._recent.popleft())
