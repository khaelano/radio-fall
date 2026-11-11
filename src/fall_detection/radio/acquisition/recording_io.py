"""Python file-shaped interface to Rust's bounded recording worker."""

from __future__ import annotations
from pathlib import Path
import json
from typing import Any
from .native import require_native


class _Stream:
    def __init__(self, native: Any) -> None:
        self._native = native

    @property
    def closed(self) -> bool:
        return self._native.closed

    @property
    def saved(self) -> bool:
        return self._native.saved

    def fileno(self) -> int:
        return self._native.fileno()

    def write(self, data: str | bytes) -> int:
        self._native.write(data.encode("utf-8") if isinstance(data, str) else data)
        return len(data)

    def flush(self) -> None:
        self._native.flush()

    def close(self) -> None:
        self._native.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class RecordingIO:
    """Bounded memory admission and five-second disk batches in native threads.

    Data/flush errors, limits, close barriers and file-buffer acceptance retain
    their existing meanings; native waits release Python's GIL.
    """

    def __init__(
        self,
        *,
        interval_s: float = 5,
        capacity_bytes: int = 32 * 1024 * 1024,
        compressed: bool = False,
    ) -> None:
        self.interval_s, self.capacity_bytes = interval_s, capacity_bytes
        self.compressed = compressed
        self._native = require_native().RecordingWriter(interval_s, capacity_bytes)

    @property
    def pending_bytes(self) -> int:
        return self._native.pending_bytes

    @property
    def failure(self) -> str | None:
        return self._native.failure

    def stats(self) -> dict[str, Any]:
        """Return native queue ownership, write counts and failure diagnostics."""
        return json.loads(self._native.stats_json())

    def check(self) -> None:
        """Raise a sticky storage failure without forcing disk I/O."""
        self._native.check()

    def open(self, path: Path, mode: str, **kwargs: Any) -> _Stream:
        """Open a byte-preserving stream; text is encoded as UTF-8."""
        if self.compressed:
            if mode.rstrip("b") == "a" and path.exists():
                raise ValueError(
                    "Cannot append compressed frames to a legacy plain file"
                )
            path = Path(str(path) + ".zst")
        return _Stream(self._native.open(str(path), mode))

    def flush(self, timeout: float = 10) -> None:
        """Wait for admitted data to reach file buffers, releasing the GIL."""
        self._native.flush(timeout)

    def close(self, timeout: float = 10) -> None:
        """Drain and close all streams, propagating timeout and storage errors."""
        self._native.close(timeout)
