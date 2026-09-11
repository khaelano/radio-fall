"""Raw CSI stream recording."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TextIO

from .protocol import CSI_HEADER


class CsiRecorder:
    """Append only valid CSI lines to a timestamped CSV file."""

    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.path = output_dir / f"csi_{stamp}.csv"
        self._file: TextIO = self.path.open("w", encoding="utf-8", buffering=1)
        self._file.write(CSI_HEADER + "\n")
        self._lock = Lock()

    def write(self, line: str) -> None:
        """Write one already-validated CSI line."""

        with self._lock:
            self._file.write(line.rstrip("\r\n") + "\n")

    def close(self) -> None:
        with self._lock:
            self._file.close()
