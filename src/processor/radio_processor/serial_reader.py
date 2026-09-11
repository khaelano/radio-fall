"""Reconnectable serial CSI reader running outside the GUI thread."""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from .buffer import RollingCsiBuffer
from .protocol import parse_csi_line
from .recorder import CsiRecorder


class SerialCsiReader:
    """Read CSI records, reconnecting after USB resets or unplug/replug."""

    def __init__(
        self,
        port: str,
        baud: int,
        buffer: RollingCsiBuffer,
        output_dir: Path,
        on_status: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        self.port = port
        self.baud = baud
        self.buffer = buffer
        self.output_dir = output_dir
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name="csi-serial-reader", daemon=True
        )
        self.malformed_lines = 0
        self.total_lines = 0
        self.last_valid_time: Optional[float] = None
        self.firmware_messages: deque[str] = deque(maxlen=20)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _status(self, message: str, connected: bool) -> None:
        if self.on_status is not None:
            self.on_status(message, connected)

    def _run(self) -> None:
        try:
            import serial
            from serial import SerialException
        except ImportError:
            self._status("pyserial is not installed", False)
            return

        backoff = 0.5
        while not self.stop_event.is_set():
            recorder: Optional[CsiRecorder] = None
            try:
                self._status(f"opening serial port: {self.port}", False)
                with serial.Serial(self.port, self.baud, timeout=0.25) as connection:
                    # Do not leave the USB-UART control lines asserted while
                    # the GUI owns the port.  CH340/CP210x boards commonly
                    # wire DTR/RTS to EN/BOOT, and a second open can otherwise
                    # keep the receiver in a reset loop.
                    connection.dtr = False
                    connection.rts = False
                    # Create a segment only after opening the port. A failed
                    # open must not leave behind a misleading header-only CSV.
                    recorder = CsiRecorder(self.output_dir)
                    self._status(f"port open; waiting for CSI: {self.port}", True)
                    backoff = 0.5
                    stream_live = False
                    pending = bytearray()
                    while not self.stop_event.is_set():
                        # ``Serial.readline()`` ultimately reads this 900-byte
                        # CSV stream a byte at a time. Pull available UART data
                        # in chunks and frame complete lines locally instead.
                        chunk = connection.read(max(1, connection.in_waiting))
                        if not chunk:
                            continue
                        pending.extend(chunk)
                        if len(pending) > 64 * 1024:
                            pending.clear()
                            self.malformed_lines += 1
                            continue

                        while (newline := pending.find(b"\n")) >= 0:
                            raw = bytes(pending[:newline])
                            del pending[: newline + 1]
                            self.total_lines += 1
                            line = raw.decode("utf-8", errors="replace").strip()
                            if not line.startswith("CSI_DATA,"):
                                if line:
                                    self.firmware_messages.append(line)
                                    self._status(f"firmware: {line}", True)
                                continue
                            try:
                                record = parse_csi_line(line)
                            except ValueError:
                                self.malformed_lines += 1
                                continue
                            recorder.write(line)
                            self.buffer.append(record)
                            self.last_valid_time = time.monotonic()
                            if not stream_live:
                                stream_live = True
                                self._status("stream live", True)
            except (SerialException, OSError) as exc:
                if self.stop_event.is_set():
                    break
                self._status(f"serial error: {exc}; retrying", False)
            finally:
                if recorder is not None:
                    recorder.close()

            if self.stop_event.is_set():
                break
            self._status("receiver disconnected; retrying", False)
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2.0, 5.0)
