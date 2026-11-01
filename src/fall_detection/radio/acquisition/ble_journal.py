"""Append-only BLE transport sidecars; no changes to existing raw recordings."""

from __future__ import annotations

import json
import struct
import time
from collections import deque
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from .ble_protocol import MAX_ENVELOPE, BleBatch

ENTRY = struct.Struct("!QI")


class BleJournal:
    """Accept complete envelopes before ACK, with bounded duplicate memory.

    Flush means application/file-buffer acceptance, not a power-loss durability
    guarantee. A filesystem error propagates and prevents acknowledgement.
    """

    def __init__(self, session_root: Path, run_id: int, metadata: dict) -> None:
        self.root = session_root / "transport" / "ble" / f"{run_id:016x}"
        self.root.mkdir(parents=True, exist_ok=False)
        (self.root / "manifest.json").write_text(
            json.dumps(dict(schema_version=1, run_id=str(run_id), **metadata), indent=2)
            + "\n"
        )
        self._data = (self.root / "envelopes.bin").open("xb")
        self._events = (self.root / "events.jsonl").open("x", encoding="utf-8")
        self._bins = (self.root / "availability.jsonl").open("x", encoding="utf-8")
        self._lock = RLock()
        self._keys = deque()
        self._seen = {}
        self.closed = False

    def accept(self, batch: BleBatch, arrival_ns: int) -> bool:
        """Persist an envelope; return false for a previously accepted duplicate."""
        data = batch.encode()
        key = (
            batch.run_id,
            batch.transmitter_boot_id,
            batch.receiver_boot_id,
            batch.batch_id,
        )
        with self._lock:
            if self.closed:
                raise RuntimeError("BLE journal is closed")
            if key in self._seen:
                if self._seen[key] != data:
                    raise ValueError("batch identity reused for different bytes")
                return False
            self._data.write(ENTRY.pack(arrival_ns, len(data)) + data)
            self._data.flush()
            self._keys.append(key)
            self._seen[key] = data
            if len(self._keys) > 4096:
                del self._seen[self._keys.popleft()]
            return True

    def event(self, kind: str, **values: Any) -> None:
        """Append timestamped diagnostics, clock exchanges, or receipt metadata."""
        with self._lock:
            if self.closed:
                return
            self._events.write(
                json.dumps(
                    dict(kind=kind, host_monotonic_ns=time.monotonic_ns(), **values),
                    separators=(",", ":"),
                )
                + "\n"
            )
            self._events.flush()

    def bin(self, value: dict) -> None:
        """Append an immutable derived availability bin."""
        with self._lock:
            self._bins.write(json.dumps(value, separators=(",", ":")) + "\n")
            self._bins.flush()

    def close(self) -> None:
        """Close this run's files without modifying another run."""
        with self._lock:
            if not self.closed:
                self.closed = True
                self._data.close()
                self._events.close()
                self._bins.close()


def iter_envelopes(path: Path) -> Iterator[tuple[int, BleBatch]]:
    """Read bounded entries, rejecting a truncated or corrupted journal."""
    with path.open("rb") as stream:
        while header := stream.read(ENTRY.size):
            if len(header) != ENTRY.size:
                raise ValueError("truncated BLE journal header")
            arrival, length = ENTRY.unpack(header)
            if length > MAX_ENVELOPE:
                raise ValueError("oversized BLE journal entry")
            data = stream.read(length)
            if len(data) != length:
                raise ValueError("truncated BLE journal envelope")
            yield arrival, BleBatch.decode(data)
