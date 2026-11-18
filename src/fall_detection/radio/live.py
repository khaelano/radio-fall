"""Live gateway acquisition for desktop applications, without Qt imports.

Rust owns the radio session: startup, journal-before-ACK acceptance, capture
mapping, availability bins, duplicate removal, quality counters and restarts.
This module only moves accepted records to the host's sinks and display
buffers and turns native health into presentation-ready snapshots.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from .availability import AvailabilitySnapshot
from .buffer import RollingCsiBuffer
from .gateway_diagnostics import (
    DeliveryRates,
    GatewayDiagnostics,
    ReceiverDiagnostics,
)
from .native import backend_info, require_native
from .records import CsiRecord
from .settings import resolve_settings
from .state import LiveState
from .telemetry import BackhaulTelemetrySnapshot

__all__ = ["LiveRadio", "ReceiverBinding"]

# Stale status or delivery beyond this age marks a receiver offline.
LIVENESS_S = 2.5
# Plot work waits while more accepted records than this await Python delivery.
PREVIEW_MAX_PENDING_RECORDS = 512
HEALTH_INTERVAL_S = 0.1
POLL_IDLE_S = 0.005


@dataclass(frozen=True)
class ReceiverBinding:
    """A configured receiver slot; the USB port belongs to the shared gateway."""

    receiver_id: str
    mac: str
    target: str
    port: str
    profile_fingerprint: str


def _native_acquisition(config_json: str) -> Any:
    native = require_native()
    if not hasattr(native, "NativeAcquisition"):
        raise RuntimeError("Rebuild the native extension to enable NativeAcquisition")
    return native.NativeAcquisition(config_json)


class LiveRadio:
    """Validate configuration once, then deliver native records to the host.

    Construction does not open hardware. ``acquisition_factory`` receives the
    JSON configuration and is the seam for offline lifecycle tests. Call
    ``start`` only after the host's sinks are ready, and ``stop`` on every exit.

    Args:
        args: Parsed live arguments with ``config``, ``gateway_port`` and
            ``output_dir`` (the journal directory when ``journal_root`` is
            absent); ``receiver_id`` optionally selects the preview.
        require_four: Require exactly four configured receivers.
        on_status: Receives human-readable radio state changes.
        record_sink: Receives each accepted first-capture record and its host
            arrival time. Rust has already journaled the record, so neither the
            viewer nor the collector passes one.
        journal_root: Returns the directory for transport journals at start;
            defaults to ``args.output_dir``.
        on_interruption: Called once per failed run with the failure reason.
        acquisition_factory: Builds the native acquisition from JSON.
    """

    def __init__(
        self,
        args: argparse.Namespace,
        *,
        require_four: bool = False,
        on_status: Callable[[str, bool], None] | None = None,
        record_sink: Callable[[CsiRecord, int], None] | None = None,
        journal_root: Callable[[], Path | None] | None = None,
        on_interruption: Callable[[str], None] | None = None,
        acquisition_factory: Callable[[str], Any] = _native_acquisition,
    ) -> None:
        self.settings = resolve_settings(args)
        self.settings.transport.validate(
            self.settings.inventory, self.settings.profile, require_four=require_four
        )
        if not args.gateway_port:
            raise ValueError("a gateway USB port is required (--gateway-port)")
        receivers = self.settings.inventory.receivers
        selected = getattr(args, "receiver_id", None)
        receiver_ids = [device.id for device in receivers]
        if selected is not None and selected not in receiver_ids:
            raise ValueError(
                "--receiver-id must match one of: " + ", ".join(sorted(receiver_ids))
            )
        fingerprint = self.settings.profile_fingerprint
        self.bindings = tuple(
            ReceiverBinding(
                device.id, device.mac, device.target, args.gateway_port, fingerprint
            )
            for device in receivers
        )
        self.buffers = {
            device.id: RollingCsiBuffer(
                nominal_rate=self.settings.profile.nominal_rate_hz, seconds=10
            )
            for device in receivers
        }
        self.state = LiveState(self.settings.profile.nominal_rate_hz)
        self.state.configure_receivers(self.buffers, selected)
        self._args = args
        self._on_status = on_status
        self._record_sink = record_sink
        self._journal_root = journal_root
        self._on_interruption = on_interruption
        self._factory = acquisition_factory
        self._acquisition: Any = None
        self._rates = DeliveryRates()
        self._health: dict[str, Any] = {"session": {"state": "idle"}}
        self._health_lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._started = self._stopped = False
        self._announced: tuple[str | None, int] = (None, 0)
        self._sink_failure: str | None = None

    # ------------------------------------------------------------------ setup

    def environment(self) -> dict[str, Any]:
        """Snapshot resolved radio inputs for an immutable session manifest."""
        settings = self.settings
        return {
            "host_processing": backend_info(),
            "transport": "espnow_gateway",
            "gateway_transport": asdict(settings.transport),
            "gateway_transport_fingerprint": settings.transport.fingerprint(
                settings.inventory, settings.profile
            ),
            "gateway_port": self._args.gateway_port,
            "transmitter_link": settings.connection["transmitter_link"],
            "radio_config": str(self._args.config) if self._args.config else None,
            "nominal_rate_hz": settings.profile.nominal_rate_hz,
            "receiver_ids": {
                device.mac: device.id for device in settings.inventory.receivers
            },
            "radio_inventory": settings.inventory.as_dict(),
            "radio_profile": settings.profile.as_dict(),
            "radio_profile_fingerprint": settings.profile_fingerprint,
            "receiver_bindings": {
                binding.receiver_id: {
                    "mac": binding.mac,
                    "target": binding.target,
                    "port": binding.port,
                    "profile_fingerprint": binding.profile_fingerprint,
                }
                for binding in self.bindings
            },
        }

    def native_config(self, journal_root: Path) -> dict[str, Any]:
        """Return the JSON-serializable configuration for ``NativeAcquisition``."""
        settings = self.settings
        transport = settings.transport
        return {
            "serial_path": str(self._args.gateway_port),
            "radio_config": settings.native_radio_config(),
            "journal_root": str(journal_root),
            "metadata": {
                "host_processing": backend_info(),
                "transmitter_link": settings.connection["transmitter_link"],
                "transport_config": asdict(transport),
                "transport_fingerprint": transport.fingerprint(
                    settings.inventory, settings.profile
                ),
                "inventory": settings.inventory.as_dict(),
                "profile": settings.profile.as_dict(),
            },
            "bin_hz": transport.bin_hz,
            "delivery_grace_ms": transport.delivery_grace_ms,
            "restart_delay_ms": 3000,
            "maximum_restart_delay_ms": 30000,
            "relay_ready_timeout_ms": 8000,
        }

    # -------------------------------------------------------------- lifecycle

    def start(self) -> None:
        """Start native acquisition after the host's sinks are ready."""
        if self._stopped or self._started:
            raise RuntimeError("a live radio starts once; create a new instance")
        root = self._journal_root() if self._journal_root else None
        root = Path(root or self._args.output_dir)
        config = self.native_config(root)
        self._acquisition = self._factory(json.dumps(config, allow_nan=False))
        self._started = True
        self._report("Starting radio", False)
        self._acquisition.start()
        self._thread = Thread(target=self._deliver, name="csi-delivery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop acquisition and deliver every accepted record; repeat calls are harmless."""
        if self._stopped:
            return
        self._stopped = True
        error = None
        if self._acquisition is not None:
            try:
                self._acquisition.stop(10.0)
            except Exception as exc:  # noqa: BLE001 — continue draining before raising
                error = exc
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise TimeoutError("radio record delivery did not stop")
        if self._acquisition is not None:
            self._drain()
            self._refresh_health()
        if error is not None:
            raise error

    def _deliver(self) -> None:
        last_health = 0.0
        while not self._stop.is_set():
            delivered = self._drain(limit=4096)
            now = time.monotonic()
            if now - last_health >= HEALTH_INTERVAL_S:
                self._refresh_health()
                last_health = now
            if not delivered:
                self._stop.wait(POLL_IDLE_S)

    def _drain(self, limit: int | None = None) -> int:
        delivered = 0
        while limit is None or delivered < limit:
            items = self._acquisition.poll(4096)
            if not items:
                break
            for item in items:
                self._deliver_record(*item)
            delivered += len(items)
        return delivered

    def _deliver_record(
        self,
        native: Any,
        slot: int,
        run: int,
        transmitter_boot: int,
        receiver_boot: int,
        _batch: int,
        capture_ns: int,
        arrival_ns: int,
        available_ns: int,
        uncertainty_us: float,
    ) -> None:
        binding = self.bindings[slot]
        record = CsiRecord.from_native(
            native,
            {
                "run_id": run,
                "transmitter_boot_id": transmitter_boot,
                "receiver_boot_id": receiver_boot,
                "transport": "espnow_gateway",
                "capture_host_monotonic_ns": capture_ns,
                "capture_clock_uncertainty_us": uncertainty_us,
                "native_processed_ns": available_ns,
            },
        )
        if self._sink_failure is None:
            try:
                if self._record_sink is not None:
                    self._record_sink(record, arrival_ns)
            except Exception as exc:  # noqa: BLE001 — storage failure ends delivery
                self._sink_failure = f"record storage failed: {exc}"
                self._report(self._sink_failure, False)
                if self._on_interruption is not None:
                    self._on_interruption(self._sink_failure)
        self.buffers[binding.receiver_id].append(record)
        self._rates.observe(binding.receiver_id, 1, time.monotonic_ns())

    # ----------------------------------------------------------------- health

    def _refresh_health(self) -> None:
        health = json.loads(self._acquisition.health())
        with self._health_lock:
            self._health = health
        session = health.get("session", {})
        state, runs = session.get("state"), health.get("runs", 0)
        if (state, runs) == self._announced:
            return
        self._announced = (state, runs)
        if state == "running":
            self._report(
                "Radio recovered; sensing resumed with fresh timing"
                if runs > 1
                else "Radio live; sensing",
                True,
            )
        elif state == "starting_radio":
            self._report(
                "Radio reconnected; establishing fresh timing"
                if runs
                else "Starting radio",
                False,
            )
        elif state in {"restarting", "failed"}:
            reason = session.get("error") or "unknown radio failure"
            self._report(
                "Radio interrupted; reconnecting: " + reason
                if state == "restarting"
                else "Radio stopped: " + reason,
                False,
            )
            if self._on_interruption is not None:
                self._on_interruption(reason)

    def _report(self, message: str, connected: bool) -> None:
        self.state.set_status(message, connected)
        if self._on_status is not None:
            self._on_status(message, connected)

    def health(self) -> dict[str, Any]:
        """Return the latest native health document."""
        with self._health_lock:
            return self._health

    @property
    def failure(self) -> str | None:
        """Return the current run failure, a fatal stop, or a storage failure."""
        health = self.health()
        if self._sink_failure:
            return self._sink_failure
        if health.get("fatal") or health.get("session", {}).get("state") in {
            "restarting",
            "starting_radio",
            "failed",
        }:
            return health.get("failure")
        return None

    @property
    def _running(self) -> bool:
        return self.health().get("session", {}).get("state") == "running"

    @property
    def clock_sync_ready(self) -> bool:
        """Capture-time mapping is valid for the current run."""
        clock = self.health().get("session", {}).get("clock") or {}
        return bool(self._running and clock.get("ready") and not self.failure)

    @property
    def all_live(self) -> bool:
        """Every configured receiver reported status recently."""
        receivers = self.health().get("session", {}).get("receivers") or []
        return (
            self._running
            and len(receivers) == len(self.bindings)
            and all(
                r.get("status_age_ns") is not None
                and r["status_age_ns"] < LIVENESS_S * 1e9
                for r in receivers
            )
        )

    @property
    def any_recent_record(self) -> bool:
        """Every configured receiver delivered a record recently."""
        receivers = self.health().get("receivers") or []
        return len(receivers) >= len(self.bindings) and all(
            r.get("last_record_age_ns") is not None
            and r["last_record_age_ns"] < LIVENESS_S * 1e9
            for r in receivers[: len(self.bindings)]
        )

    @property
    def preflight_ready(self) -> bool:
        return self.all_live and self.any_recent_record and self.clock_sync_ready

    @property
    def preview_ready(self) -> bool:
        """Allow plot work only while record delivery keeps up.

        This affects display only; acquisition and recording are independent.
        """
        queue = self.health().get("queue") or {}
        return (
            not self.failure and queue.get("pending", 0) <= PREVIEW_MAX_PENDING_RECORDS
        )

    def availability(
        self, seconds: float, now_ns: int | None = None
    ) -> AvailabilitySnapshot | None:
        """Return recent availability bins of the current run, if one started."""
        del now_ns  # The native snapshot uses the shared monotonic clock.
        if self._acquisition is None:
            return None
        value = self._acquisition.availability(seconds)
        return None if value is None else AvailabilitySnapshot.from_json(value)

    def telemetry_snapshot(self) -> BackhaulTelemetrySnapshot:
        """Aggregate native quality counters for collection artifacts."""
        totals = self.health().get("totals") or {}
        return BackhaulTelemetrySnapshot(
            captured_monotonic_ns=time.monotonic_ns(),
            records=totals.get("records", 0),
            batches=totals.get("batches", 0),
            host_missing_sequences=totals.get("host_missing_sequences", 0),
            transport_missing=totals.get("transport_missing", 0),
            transport_reordered=totals.get("transport_reordered", 0),
            batch_missing=totals.get("batch_missing", 0),
            batch_reordered=totals.get("batch_reordered", 0),
            malformed=0,
            foreign=0,
            receiver_restarts=totals.get("receiver_restarts", 0),
            serial_frames=None,
            receiver_boot_id=None,
            receiver_stats=None,
            transmitter_stats=None,
            gateway_stats=None,
        )

    def diagnostics(self, *, now_ns: int | None = None) -> GatewayDiagnostics:
        """Snapshot reported gateway and receiver counters for display."""
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        health = self.health()
        session = health.get("session", {})
        statuses = session.get("receivers") or []
        quality = health.get("receivers") or []
        rates = self._rates.snapshot(now_ns)
        receivers = []
        for slot, binding in enumerate(self.bindings):
            report = statuses[slot] if slot < len(statuses) else {}
            status = report.get("status") or {}
            counters = quality[slot] if slot < len(quality) else {}
            status_age = report.get("status_age_ns")
            delivery_age = counters.get("last_record_age_ns")
            receivers.append(
                ReceiverDiagnostics(
                    receiver_id=binding.receiver_id,
                    status_age_s=None if status_age is None else status_age / 1e9,
                    delivery_age_s=None if delivery_age is None else delivery_age / 1e9,
                    online=bool(
                        status_age is not None
                        and status_age < LIVENESS_S * 1e9
                        and not self.failure
                    ),
                    reported_state=status.get("state"),
                    records=counters.get("records", 0),
                    records_s=rates.get(binding.receiver_id, 0.0),
                    last_sequence=counters.get("last_sequence"),
                    captured=status.get("captured"),
                    queued=status.get("queued"),
                    queue_peak=status.get("peak"),
                    expired=status.get("expired"),
                    dropped=status.get("dropped"),
                    send_errors=status.get("send_errors"),
                    diagnostic_loss=status.get("queue_event_loss"),
                    sequence_gaps=counters.get("missing_sequences", 0),
                    transport_gaps=counters.get("transport_missing", 0),
                    batch_gaps=counters.get("batch_missing", 0),
                    malformed_packets=0,
                )
            )
        clock = session.get("clock") or {}
        gateway = session.get("gateway") or {}
        gateway_age = session.get("gateway_age_ns")
        transport = self.settings.transport
        return GatewayDiagnostics(
            nominal_rate_hz=self.settings.profile.nominal_rate_hz,
            sensing_channel=self.settings.profile.channel,
            backhaul_channel=transport.channel,
            backhaul_phy=transport.phy,
            slot_ms=transport.slot_ms,
            queue_capacity=transport.queue_capacity,
            application_acknowledgements=transport.application_acknowledgements,
            transmitter_link=self.settings.connection["transmitter_link"],
            reference_present=bool(clock),
            reference_ready=self.clock_sync_ready,
            clock_uncertainty_us=clock.get("uncertainty_us"),
            gateway_age_s=None if gateway_age is None else gateway_age / 1e9,
            gateway_configured=gateway.get("configured"),
            received_envelopes=gateway.get("received"),
            forwarded_envelopes=gateway.get("forwarded"),
            rejected_or_dropped=gateway.get("rejected"),
            usb_errors=gateway.get("usb_errors"),
            gateway_queued=gateway.get("queued"),
            failure=self.failure,
            receivers=tuple(receivers),
        )
