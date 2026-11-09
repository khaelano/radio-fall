"""Bounded FIFO ownership of timestamped USB reads, consumed in small groups."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Condition
import time
from typing import Callable


@dataclass(frozen=True)
class UsbReadChunk:
    """Immutable bytes with their host USB read-completion timestamp."""

    data: bytes
    arrival_ns: int


class UsbReadBuffer:
    """Absorb short consumer stalls without silently dropping or aging data.

    Groups contain only work already available. Receiving one chunk wakes the
    consumer immediately; there is no timer to wait for a group to fill.
    """

    def __init__(
        self,
        *,
        capacity_bytes: int = 256 * 1024,
        capacity_chunks: int = 256,
        maximum_age_ns: int = 200_000_000,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if min(capacity_bytes, capacity_chunks, maximum_age_ns) <= 0:
            raise ValueError("USB buffer limits must be positive")
        self.capacity_bytes = capacity_bytes
        self.capacity_chunks = capacity_chunks
        self.maximum_age_ns = maximum_age_ns
        self._clock_ns = clock_ns
        self._condition = Condition()
        self._pending: deque[UsbReadChunk] = deque()
        self._bytes = self._peak_bytes = self._peak_chunks = 0
        self._maximum_wait_ns = self._groups = self._consumed_chunks = 0
        self._closed = False

    def put(self, data: bytes, arrival_ns: int) -> None:
        """Transfer immutable bytes into the FIFO or fail before discarding any."""
        with self._condition:
            if self._closed:
                raise RuntimeError("gateway USB receive buffer closed")
            if not data:
                return
            if (
                len(self._pending) >= self.capacity_chunks
                or self._bytes + len(data) > self.capacity_bytes
            ):
                raise BufferError("gateway USB receive buffer overflow")
            self._pending.append(UsbReadChunk(bytes(data), arrival_ns))
            self._bytes += len(data)
            self._peak_bytes = max(self._peak_bytes, self._bytes)
            self._peak_chunks = max(self._peak_chunks, len(self._pending))
            self._condition.notify()

    def get_batch(
        self, *, max_chunks: int = 4, timeout_s: float = 0.1
    ) -> tuple[UsbReadChunk, ...]:
        """Take at most max_chunks, waiting only when no input is available."""
        if max_chunks < 1 or timeout_s < 0:
            raise ValueError("invalid USB batch limits")
        with self._condition:
            self._condition.wait_for(
                lambda: bool(self._pending) or self._closed, timeout=timeout_s
            )
            if not self._pending:
                return ()
            wait_ns = max(0, self._clock_ns() - self._pending[0].arrival_ns)
            if wait_ns > self.maximum_age_ns:
                raise TimeoutError("gateway USB receive buffer age exceeded")
            self._maximum_wait_ns = max(self._maximum_wait_ns, wait_ns)
            group = tuple(
                self._pending.popleft()
                for _ in range(min(max_chunks, len(self._pending)))
            )
            self._bytes -= sum(len(chunk.data) for chunk in group)
            self._groups += 1
            self._consumed_chunks += len(group)
            return group

    def stats(self) -> dict[str, int]:
        """Return bounded-queue diagnostics without exposing owned data."""
        with self._condition:
            return dict(
                queued_bytes=self._bytes,
                queued_chunks=len(self._pending),
                peak_bytes=self._peak_bytes,
                peak_chunks=self._peak_chunks,
                maximum_wait_ns=self._maximum_wait_ns,
                oldest_age_ns=(
                    max(0, self._clock_ns() - self._pending[0].arrival_ns)
                    if self._pending
                    else 0
                ),
                groups=self._groups,
                consumed_chunks=self._consumed_chunks,
                capacity_bytes=self.capacity_bytes,
                capacity_chunks=self.capacity_chunks,
                maximum_age_ns=self.maximum_age_ns,
            )

    def close(self) -> None:
        """Wake consumers; already owned chunks remain available for draining."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
