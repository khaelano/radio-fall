"""Shared acquisition setup for live desktop applications, without Qt imports."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from .acquisition.gateway_reader import GatewayReceiverManager
from .acquisition.protocol import CsiRecord
from .acquisition.recovery import RecoveryUnavailable, can_recover, recover_gateway
from .settings import add_config_argument, resolve_settings
from .visualization.state import LiveState


def add_live_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the common configuration and connection overrides to a live command."""
    add_config_argument(parser)
    parser.add_argument(
        "--transport", choices=("espnow_gateway",), default="espnow_gateway"
    )
    parser.add_argument("--gateway-port", help="override the configured C6 USB path")
    parser.add_argument("--port", help="override the C5 USB path for USB fallback")
    parser.add_argument("--transmitter-link", choices=("usb", "ble", "espnow_uart"))


class LiveRadio:
    """Validate and bind acquisition once, then share its buffers with the UI.

    Construction does not open hardware. The manager factory is the seam for
    offline lifecycle tests. Call ``start`` only after the host is ready to
    accept data, and ``stop`` on every exit, including failed startup.
    """

    def __init__(
        self,
        args: argparse.Namespace,
        *,
        require_four: bool = False,
        on_status: Callable[[str, bool], None] | None = None,
        record_sink: Callable[[CsiRecord, int], None] | None = None,
        journal_root: Callable[[], Path | None] | None = None,
        manager_factory: Callable[..., Any] = GatewayReceiverManager,
        on_interruption: Callable[[str], None] | None = None,
        repair_link: Callable[[Any], None] = recover_gateway,
        recording_io=None,
    ) -> None:
        self.settings = resolve_settings(args)
        self.settings.transport.validate(
            self.settings.inventory, self.settings.profile, require_four=require_four
        )
        selected = getattr(args, "receiver_id", None)
        receiver_ids = {device.id for device in self.settings.inventory.receivers}
        if selected is not None and selected not in receiver_ids:
            raise ValueError(
                "--receiver-id must match one of: " + ", ".join(sorted(receiver_ids))
            )
        self.state = LiveState(self.settings.profile.nominal_rate_hz)

        def report_status(message: str, connected: bool) -> None:
            self.state.set_status(message, connected)
            if on_status is not None:
                on_status(message, connected)

        self._report_status = report_status
        self._manager_factory = manager_factory
        self._manager_args = (
            self.settings.inventory,
            self.settings.profile,
            args.output_dir,
        )
        self._manager_options = dict(
            transmitter_port=args.port,
            gateway_port=args.gateway_port,
            transmitter_link=args.transmitter_link,
            config=self.settings.transport,
            require_four=require_four,
            on_status=report_status,
            record_sink=record_sink,
            journal_root=journal_root,
            reference_failure_sink=on_interruption,
            recording_io=recording_io,
        )
        self.manager = manager_factory(*self._manager_args, **self._manager_options)
        self.bindings = self.manager.bind()
        self.state.configure_receivers(
            {key: reader.buffer for key, reader in self.manager.readers.items()},
            selected,
        )
        self._stopped = False
        self._recovery_stop = Event()
        self._recovery_lock = Lock()
        self._recovery_thread: Thread | None = None
        self._retired_manager = None
        self._repair_link = repair_link
        self._recovery_delay_s = 3.0
        self._recovery_attempt = 0
        self._inputs = {
            "port": args.port,
            "gateway_port": args.gateway_port,
            "transmitter_link": args.transmitter_link,
            "radio_config": str(args.config) if args.config else None,
            "receiver_config": str(args.receiver_config)
            if args.receiver_config
            else None,
        }

    def environment(self) -> dict[str, Any]:
        """Snapshot resolved radio inputs for an immutable session manifest."""
        from dataclasses import asdict
        from .acquisition.native import backend_info

        settings = self.settings
        return {
            "host_processing": backend_info(),
            "transport": "espnow_gateway",
            "gateway_transport": asdict(settings.transport),
            "gateway_transport_fingerprint": settings.transport.fingerprint(
                settings.inventory, settings.profile
            ),
            **self._inputs,
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

    def start(self) -> None:
        """Start the acquisition worker after the host's sinks are ready."""
        if self._stopped:
            raise RuntimeError("a stopped radio cannot be restarted; create a new run")
        self.manager.start()
        if self.manager.transmitter_link in {"usb", "espnow_uart"}:
            self._recovery_thread = Thread(
                target=self._recover, name="csi-radio-recovery", daemon=True
            )
            self._recovery_thread.start()

    def _recover(self) -> None:
        announced = None
        while not self._recovery_stop.wait(0.1):
            previous = self.manager
            reason = previous.failure
            if not reason:
                if previous.preflight_ready:
                    self._recovery_attempt = 0
                    if previous.recovery_context and announced != previous.run_id:
                        if previous.journal:
                            try:
                                previous.journal.event(
                                    "run_recovered", **previous.recovery_context
                                )
                            except OSError as exc:
                                previous._fail(f"journal recovery event failed: {exc}")
                                return
                        self._report_status(
                            "Radio recovered; sensing resumed with fresh timing", True
                        )
                        announced = previous.run_id
                continue
            if not can_recover(reason):
                return
            with self._recovery_lock:
                if self._recovery_stop.is_set():
                    return
                try:
                    previous.stop()
                except Exception as exc:
                    self._report_status(f"Recovery stopped: {exc}", False)
                    return
                self._retired_manager = previous
            while not self._recovery_stop.is_set():
                self._recovery_attempt += 1
                self._report_status("Radio interrupted; reconnecting: " + reason, False)
                # Also lets the independent C5 control lease end before a new run.
                if self._recovery_stop.wait(
                    min(30.0, self._recovery_delay_s * self._recovery_attempt)
                ):
                    return
                try:
                    with self._recovery_lock:
                        if self._recovery_stop.is_set():
                            return
                        self._repair_link(previous)
                        replacement = self._manager_factory(
                            *self._manager_args,
                            **self._manager_options,
                            recovery_context=dict(
                                previous_run_id=str(previous.run_id), reason=reason
                            ),
                        )
                        replacement.bind()
                        self.manager = replacement
                        self._retired_manager = None
                        self.state.configure_receivers(
                            {
                                key: reader.buffer
                                for key, reader in replacement.readers.items()
                            },
                            self.state.selected_receiver_id,
                        )
                        self._report_status(
                            "Radio reconnected; establishing fresh timing", False
                        )
                        replacement.start()
                    break
                except RecoveryUnavailable as exc:
                    previous.failure = str(exc)
                    self._report_status(str(exc), False)
                    return
                except (OSError, TimeoutError) as exc:
                    self._report_status(f"Waiting for radio: {exc}", False)
                except Exception as exc:
                    self.manager._fail(f"Recovery stopped: {exc}")
                    return

    def stop(self) -> None:
        """Stop and drain acquisition; repeated successful shutdown is harmless."""
        if not self._stopped:
            self._recovery_stop.set()
            with self._recovery_lock:
                if self.manager is not self._retired_manager:
                    self.manager.stop()
            if self._recovery_thread:
                self._recovery_thread.join(timeout=2)
                if self._recovery_thread.is_alive():
                    raise TimeoutError("radio recovery did not stop")
            self._stopped = True
