"""Cumulative radio counters recorded with each collection attempt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ReceiverStats:
    """Cumulative receiver counters carried by a batched packet."""

    accepted_records: int
    sensing_missing: int
    sensing_reordered: int
    sensing_restarts: int
    queue_drops: int
    unavailable_ip_drops: int
    batches_built: int
    batches_sent: int
    records_sent: int
    send_errors: int


@dataclass(frozen=True)
class TransmitterTelemetry:
    """One cumulative transmitter counter snapshot."""

    uptime_ms: int
    attempts: int
    immediate_errors: int
    asynchronous_successes: int
    asynchronous_failures: int


@dataclass(frozen=True)
class GatewayTelemetry:
    """One cumulative ESP-NOW serial-gateway counter snapshot."""

    uptime_ms: int
    received: int
    invalid: int
    queue_drops: int
    serial_frames: int
    serial_errors: int


@dataclass(frozen=True)
class BackhaulTelemetrySnapshot:
    """Read-only cumulative counters observed by one host reader.

    Firmware counters are cumulative and may wrap at uint32.  The snapshot
    intentionally keeps the nested firmware records intact so an artifact can
    be audited without reconstructing the state from a later summary.
    """

    captured_monotonic_ns: int
    records: int
    batches: int
    host_missing_sequences: int
    transport_missing: int
    transport_reordered: int
    batch_missing: int
    batch_reordered: int
    malformed: int
    foreign: int
    receiver_restarts: int
    serial_frames: int | None
    receiver_boot_id: int | None
    receiver_stats: ReceiverStats | None
    transmitter_stats: TransmitterTelemetry | None
    gateway_stats: GatewayTelemetry | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation for collection artifacts."""

        result = asdict(self)
        return result

    def delta(self, start: BackhaulTelemetrySnapshot) -> dict[str, Any]:
        """Compute a boot-aware unsigned-counter delta from ``start``.

        Host counters are ordinary process counters. Firmware counters use
        uint32 modular subtraction, while uptime and receiver boot IDs detect
        a restart. Missing snapshots are represented by callers as an
        incomplete telemetry section rather than as zeroes.
        """

        warnings: list[str] = []
        duration_ns = self.captured_monotonic_ns - start.captured_monotonic_ns
        if duration_ns <= 0:
            warnings.append("telemetry timestamps are not increasing")
        if (
            start.receiver_boot_id is not None
            and self.receiver_boot_id is not None
            and start.receiver_boot_id != self.receiver_boot_id
        ):
            warnings.append("receiver restarted during the attempt")
        for label, before, after in (
            (
                "transmitter",
                getattr(start.transmitter_stats, "uptime_ms", None),
                getattr(self.transmitter_stats, "uptime_ms", None),
            ),
            (
                "gateway",
                getattr(start.gateway_stats, "uptime_ms", None),
                getattr(self.gateway_stats, "uptime_ms", None),
            ),
        ):
            if before is not None and after is not None and after < before:
                warnings.append(f"{label} restarted during the attempt")

        values: dict[str, Any] = {}
        host_fields = (
            "records",
            "batches",
            "host_missing_sequences",
            "transport_missing",
            "transport_reordered",
            "batch_missing",
            "batch_reordered",
            "malformed",
            "foreign",
            "receiver_restarts",
            "serial_frames",
        )
        for name in host_fields:
            end_value = getattr(self, name)
            start_value = getattr(start, name)
            if end_value is None or start_value is None:
                values[name] = None
            elif end_value < start_value:
                if name == "host_missing_sequences":
                    # Late records can close a previously observed buffer gap;
                    # this is a state view, not a cumulative counter.
                    values[name] = 0
                else:
                    warnings.append(f"host counter {name} decreased")
                    values[name] = None
            else:
                values[name] = end_value - start_value

        if self.receiver_stats is None or start.receiver_stats is None:
            warnings.append("receiver statistics unavailable")
        else:
            for field in self.receiver_stats.__dataclass_fields__:
                values[f"receiver_{field}"] = _uint32_delta(
                    getattr(start.receiver_stats, field),
                    getattr(self.receiver_stats, field),
                )

        if self.transmitter_stats is None or start.transmitter_stats is None:
            warnings.append("transmitter statistics unavailable")
        else:
            for field in (
                "attempts",
                "immediate_errors",
                "asynchronous_successes",
                "asynchronous_failures",
            ):
                values[f"transmitter_{field}"] = _uint32_delta(
                    getattr(start.transmitter_stats, field),
                    getattr(self.transmitter_stats, field),
                )

        if self.gateway_stats is None or start.gateway_stats is None:
            warnings.append("gateway statistics unavailable")
        else:
            for field in (
                "received",
                "invalid",
                "queue_drops",
                "serial_frames",
                "serial_errors",
            ):
                values[f"gateway_{field}"] = _uint32_delta(
                    getattr(start.gateway_stats, field),
                    getattr(self.gateway_stats, field),
                )

        duration_seconds = duration_ns / 1_000_000_000 if duration_ns > 0 else None
        values["duration_seconds"] = duration_seconds
        values["effective_records_per_second"] = (
            values["records"] / duration_seconds
            if duration_seconds and values["records"] is not None
            else None
        )
        return {
            "complete": not warnings,
            "warnings": warnings,
            "values": values,
        }


def _uint32_delta(start: int, end: int) -> int:
    """Return the unsigned uint32 delta between cumulative counters."""

    return (end - start) & 0xFFFFFFFF


def telemetry_delta(
    start: BackhaulTelemetrySnapshot | None,
    end: BackhaulTelemetrySnapshot | None,
) -> dict[str, Any]:
    """Return a serializable attempt delta with explicit availability state."""

    if start is None or end is None:
        missing = []
        if start is None:
            missing.append("start")
        if end is None:
            missing.append("end")
        return {
            "complete": False,
            "warnings": [f"telemetry {side} snapshot unavailable" for side in missing],
            "values": None,
        }
    return end.delta(start)
