"""Receiver-to-transmitter clock synchronization samples and estimation."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import sqrt
import struct


MAGIC = b"CSYS"
VERSION = 1
SAMPLE = struct.Struct("!4sBBHIIIIQQQQII6sH")
SAMPLE_SIZE = SAMPLE.size


class ClockSyncError(ValueError):
    """Raised when a clock-synchronization sample is malformed."""


@dataclass(frozen=True)
class ClockSyncSample:
    """One completed four-timestamp exchange.

    ``t1`` and ``t4`` use the transmitter's ``esp_timer`` clock. ``t2`` and
    ``t3`` use the receiver's ``esp_timer`` clock. The radio timestamps are
    retained separately because they are 32-bit Wi-Fi receive timestamps.
    """

    sync_id: int
    sensing_sequence: int
    receiver_boot_id: int
    tx_t1_us: int
    rx_t2_us: int
    rx_t3_us: int
    tx_t4_us: int
    rx_radio_t2_us: int
    tx_radio_t4_us: int
    receiver_mac: str

    @property
    def round_trip_us(self) -> int:
        """Return network round-trip time with receiver turnaround removed."""

        return (self.tx_t4_us - self.tx_t1_us) - (
            self.rx_t3_us - self.rx_t2_us
        )

    @property
    def receiver_minus_transmitter_us(self) -> float:
        """Return the symmetric-delay NTP offset estimate."""

        return (
            (self.rx_t2_us - self.tx_t1_us)
            + (self.rx_t3_us - self.tx_t4_us)
        ) / 2.0

    @property
    def transmitter_midpoint_us(self) -> float:
        """Return the exchange midpoint in the transmitter clock domain."""

        return (self.tx_t1_us + self.tx_t4_us) / 2.0


@dataclass(frozen=True)
class ClockSyncEstimate:
    """Affine receiver-to-transmitter clock relationship."""

    receiver_boot_id: int
    reference_transmitter_us: float
    receiver_minus_transmitter_us: float
    drift_ppm: float
    uncertainty_us: float
    sample_count: int
    minimum_round_trip_us: int

    def receiver_to_transmitter(self, receiver_time_us: int | float) -> float:
        """Map a receiver ``esp_timer`` timestamp into transmitter time."""

        slope = self.drift_ppm / 1_000_000.0
        return (
            float(receiver_time_us)
            - self.receiver_minus_transmitter_us
            + slope * self.reference_transmitter_us
        ) / (1.0 + slope)


def decode_clock_sync_sample(data: bytes) -> ClockSyncSample:
    """Validate and decode one gateway clock-synchronization payload."""

    if len(data) != SAMPLE_SIZE:
        raise ClockSyncError("clock-sync sample has an unexpected length")
    (
        magic,
        version,
        flags,
        header_length,
        sync_id,
        sensing_sequence,
        receiver_boot_id,
        reserved,
        tx_t1_us,
        rx_t2_us,
        rx_t3_us,
        tx_t4_us,
        rx_radio_t2_us,
        tx_radio_t4_us,
        receiver_mac,
        trailer_reserved,
    ) = SAMPLE.unpack(data)
    if magic != MAGIC or version != VERSION or header_length != SAMPLE_SIZE:
        raise ClockSyncError("unsupported clock-sync sample")
    if flags != 0 or reserved != 0 or trailer_reserved != 0:
        raise ClockSyncError("unknown clock-sync flags or reserved value")
    receiver_mac_text = ":".join(f"{octet:02x}" for octet in receiver_mac)
    sample = ClockSyncSample(
        sync_id=sync_id,
        sensing_sequence=sensing_sequence,
        receiver_boot_id=receiver_boot_id,
        tx_t1_us=tx_t1_us,
        rx_t2_us=rx_t2_us,
        rx_t3_us=rx_t3_us,
        tx_t4_us=tx_t4_us,
        rx_radio_t2_us=rx_radio_t2_us,
        tx_radio_t4_us=tx_radio_t4_us,
        receiver_mac=receiver_mac_text,
    )
    if tx_t4_us < tx_t1_us or rx_t3_us < rx_t2_us:
        raise ClockSyncError("clock-sync timestamps are not monotonic")
    if sample.round_trip_us < 0:
        raise ClockSyncError("clock-sync receiver turnaround exceeds round trip")
    return sample


class ClockSyncEstimator:
    """Maintain a bounded, low-delay affine clock estimate."""

    def __init__(self, max_samples: int = 32) -> None:
        if max_samples < 2:
            raise ValueError("max_samples must be at least two")
        self._samples: deque[ClockSyncSample] = deque(maxlen=max_samples)
        self.estimate: ClockSyncEstimate | None = None

    @property
    def samples(self) -> tuple[ClockSyncSample, ...]:
        """Return the retained samples in arrival order."""

        return tuple(self._samples)

    def add(self, sample: ClockSyncSample) -> ClockSyncEstimate:
        """Add a sample, resetting automatically after a receiver reboot."""

        if self._samples and (
            sample.receiver_boot_id != self._samples[-1].receiver_boot_id
            or sample.tx_t4_us < self._samples[-1].tx_t4_us
        ):
            self._samples.clear()
        self._samples.append(sample)
        self.estimate = self._fit()
        return self.estimate

    def _fit(self) -> ClockSyncEstimate:
        samples = list(self._samples)
        minimum_rtt = min(sample.round_trip_us for sample in samples)
        # Queueing can only increase a two-way exchange. Keep samples near the
        # observed delay floor so an asymmetric backlog does not become clock
        # offset or drift.
        allowance = max(250, minimum_rtt // 4)
        selected = [
            sample
            for sample in samples
            if sample.round_trip_us <= minimum_rtt + allowance
        ]
        reference = selected[-1].transmitter_midpoint_us
        offsets = [sample.receiver_minus_transmitter_us for sample in selected]
        slope = 0.0
        if len(selected) >= 3:
            xs = [sample.transmitter_midpoint_us - reference for sample in selected]
            mean_x = sum(xs) / len(xs)
            mean_offset = sum(offsets) / len(offsets)
            denominator = sum((value - mean_x) ** 2 for value in xs)
            if denominator > 0:
                slope = sum(
                    (x - mean_x) * (offset - mean_offset)
                    for x, offset in zip(xs, offsets, strict=True)
                ) / denominator
        intercept = (
            sum(offsets) / len(offsets)
            - slope
            * sum(
                sample.transmitter_midpoint_us - reference
                for sample in selected
            )
            / len(selected)
        )
        residuals = [
            offset
            - (
                intercept
                + slope * (sample.transmitter_midpoint_us - reference)
            )
            for sample, offset in zip(selected, offsets, strict=True)
        ]
        residual_rms = sqrt(
            sum(value * value for value in residuals) / len(residuals)
        )
        return ClockSyncEstimate(
            receiver_boot_id=selected[-1].receiver_boot_id,
            reference_transmitter_us=reference,
            receiver_minus_transmitter_us=intercept,
            drift_ppm=slope * 1_000_000.0,
            uncertainty_us=minimum_rtt / 2.0 + residual_rms,
            sample_count=len(selected),
            minimum_round_trip_us=minimum_rtt,
        )
