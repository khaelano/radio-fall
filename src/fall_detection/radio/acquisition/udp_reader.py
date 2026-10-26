"""Realtime UDP CSI reader for the processor-hosted access point."""

from __future__ import annotations

import socket
import threading
from pathlib import Path
from typing import Callable, Optional

from .buffer import RollingCsiBuffer
from .packet_reader import BinaryCsiPacketReader
from .protocol import CsiRecord


class UdpCsiReader(BinaryCsiPacketReader):
    """Receive compact CSI datagrams without blocking the GUI thread."""

    def __init__(
        self,
        host: str,
        port: int,
        buffer: RollingCsiBuffer,
        output_dir: Path,
        receiver_mac: Optional[str] = None,
        on_status: Optional[Callable[[str, bool], None]] = None,
        record_sink: Optional[Callable[[CsiRecord, int], None]] = None,
    ) -> None:
        super().__init__(
            buffer,
            output_dir,
            receiver_mac=receiver_mac,
            on_status=on_status,
            live_status="UDP stream live",
            record_sink=record_sink,
        )
        self.host = host
        self.port = port
        self.bound_port: Optional[int] = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name="csi-udp-reader", daemon=True
        )
        self._socket: Optional[socket.socket] = None

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        sock = self._socket
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self.thread.join(timeout=2)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket = sock
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(0.25)
            sock.bind((self.host, self.port))
            self.bound_port = sock.getsockname()[1]
            self._status(
                f"listening for CSI UDP on {self.host}:{self.bound_port}", True
            )
            while not self.stop_event.is_set():
                try:
                    data, _address = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError as exc:
                    if self.stop_event.is_set():
                        break
                    self._status(f"UDP socket error: {exc}; retrying", False)
                    break
                self._ingest_packet(data)
        except OSError as exc:
            if not self.stop_event.is_set():
                self._status(f"unable to bind CSI UDP socket: {exc}", False)
        finally:
            self._socket = None
            try:
                sock.close()
            except OSError:
                pass
            self._close_packet_stream()
