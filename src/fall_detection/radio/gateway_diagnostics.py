"""Immutable gateway diagnostics and a bounded host-delivery rate window."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock


class DeliveryRates:
    """Count unique records accepted by the host in the preceding one second."""

    def __init__(self) -> None:
        self._times: dict[str, deque[int]] = {}
        self._lock = Lock()

    def observe(self, receiver_id: str, count: int, now_ns: int) -> None:
        """Add successful ingestion only; repeated batches do not enter this window."""
        with self._lock:
            window = self._times.setdefault(receiver_id, deque(maxlen=4096))
            window.extend([now_ns] * count)
            while window and window[0] <= now_ns - 1_000_000_000:
                window.popleft()

    def snapshot(self, now_ns: int) -> dict[str, float]:
        """Return trailing rates, including zero after arrivals cease."""
        with self._lock:
            for window in self._times.values():
                while window and window[0] <= now_ns - 1_000_000_000:
                    window.popleft()
            return {
                key: float(sum(t <= now_ns for t in window))
                for key, window in self._times.items()
            }


RECEIVER_STATES = {
    0: "capture",
    1: "switch to 2.4 GHz",
    2: "upload",
    3: "return to 5 GHz",
    4: "confirm return",
    5: "fault",
}


@dataclass(frozen=True)
class ReceiverDiagnostics:
    """One receiver's reported counters, separate from host delivery observations."""

    receiver_id: str
    status_age_s: float | None
    delivery_age_s: float | None
    online: bool
    reported_state: int | None
    records: int
    records_s: float
    last_sequence: int | None
    captured: int | None
    queued: int | None
    queue_peak: int | None
    expired: int | None
    dropped: int | None
    send_errors: int | None
    diagnostic_loss: bool | None
    sequence_gaps: int
    transport_gaps: int
    batch_gaps: int
    malformed_packets: int

    @property
    def state_name(self) -> str:
        """Name the last report, without claiming the receiver's current channel."""
        if self.reported_state is None:
            return "pending"
        return RECEIVER_STATES.get(
            self.reported_state, f"unknown ({self.reported_state})"
        )


@dataclass(frozen=True)
class GatewayDiagnostics:
    """Read-only view shared by the viewer and collection console."""

    nominal_rate_hz: int
    sensing_channel: int
    backhaul_channel: int
    backhaul_phy: str
    slot_ms: int
    queue_capacity: int
    application_acknowledgements: bool
    transmitter_link: str
    reference_present: bool
    reference_ready: bool
    clock_uncertainty_us: float | None
    gateway_age_s: float | None
    gateway_configured: bool | None
    received_envelopes: int | None
    forwarded_envelopes: int | None
    rejected_or_dropped: int | None
    usb_errors: int | None
    gateway_queued: int | None
    failure: str | None
    receivers: tuple[ReceiverDiagnostics, ...]

    @property
    def records_s(self) -> float:
        """Aggregate delivered records/s; configured sensing Hz is per receiver."""
        return sum(receiver.records_s for receiver in self.receivers)
