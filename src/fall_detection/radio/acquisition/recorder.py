"""Raw CSI stream recording."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TextIO

from .clock_sync import ClockSyncEstimate, ClockSyncSample
from .protocol import CSI_HEADER, CsiRecord, format_csi_record


TIMING_HEADER = (
    "sequence,receiver_mac,transport_sequence,tx_enqueue_timestamp_us,"
    "rx_radio_timestamp_us,rx_callback_timestamp_us,host_receive_monotonic_ns"
)
CLOCK_SYNC_HEADER = (
    "host_receive_monotonic_ns,receiver_mac,sync_id,sensing_sequence,receiver_boot_id,"
    "tx_t1_us,rx_t2_us,rx_t3_us,tx_t4_us,rx_radio_t2_us,tx_radio_t4_us,"
    "round_trip_us,receiver_minus_transmitter_us,drift_ppm,uncertainty_us"
)


class CsiRecorder:
    """Append only valid CSI lines to a timestamped CSV file."""

    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.path = output_dir / f"csi_{stamp}.csv"
        self.timing_path = output_dir / f"radio_timing_{stamp}.csv"
        self._file: TextIO = self.path.open("w", encoding="utf-8", buffering=1)
        self._file.write(CSI_HEADER + "\n")
        self._timing_file: TextIO | None = None
        self._lock = Lock()

    def write(self, line: str) -> None:
        """Write one already-validated CSI line."""

        with self._lock:
            self._file.write(line.rstrip("\r\n") + "\n")

    def write_record(
        self,
        record: CsiRecord,
        *,
        host_receive_monotonic_ns: int,
    ) -> None:
        """Write a CSI row and its lossless cross-clock timing metadata."""

        with self._lock:
            self._file.write(format_csi_record(record).rstrip("\r\n") + "\n")
            if self._timing_file is None:
                self._timing_file = self.timing_path.open(
                    "w", encoding="utf-8", buffering=1
                )
                self._timing_file.write(TIMING_HEADER + "\n")
            tx_timestamp = "" if record.tx_timestamp_us is None else record.tx_timestamp_us
            rx_callback = (
                ""
                if record.rx_callback_timestamp_us is None
                else record.rx_callback_timestamp_us
            )
            self._timing_file.write(
                f"{record.sequence},{record.receiver_mac},"
                f"{record.transport_sequence},{tx_timestamp},"
                f"{record.timestamp_us},{rx_callback},"
                f"{host_receive_monotonic_ns}\n"
            )

    def close(self) -> None:
        with self._lock:
            self._file.close()
            if self._timing_file is not None:
                self._timing_file.close()


class ClockSyncRecorder:
    """Append raw synchronization exchanges and derived diagnostics."""

    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.path = output_dir / f"clock_sync_{stamp}.csv"
        self._file: TextIO = self.path.open("w", encoding="utf-8", buffering=1)
        self._file.write(CLOCK_SYNC_HEADER + "\n")
        self._lock = Lock()

    def write(
        self,
        sample: ClockSyncSample,
        estimate: ClockSyncEstimate,
        *,
        host_receive_monotonic_ns: int,
    ) -> None:
        """Write one raw sample together with the current fit diagnostics."""

        with self._lock:
            self._file.write(
                f"{host_receive_monotonic_ns},{sample.receiver_mac},{sample.sync_id},"
                f"{sample.sensing_sequence},{sample.receiver_boot_id},"
                f"{sample.tx_t1_us},{sample.rx_t2_us},{sample.rx_t3_us},"
                f"{sample.tx_t4_us},{sample.rx_radio_t2_us},"
                f"{sample.tx_radio_t4_us},{sample.round_trip_us},"
                f"{sample.receiver_minus_transmitter_us:.6f},"
                f"{estimate.drift_ppm:.6f},{estimate.uncertainty_us:.6f}\n"
            )

    def close(self) -> None:
        """Close the synchronization CSV file."""

        with self._lock:
            self._file.close()
