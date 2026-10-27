"""Live CSI viewer with synchronized signal and radio diagnostics."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ..acquisition.buffer import DEFAULT_NOMINAL_RATE_HZ
from ..acquisition.espnow_serial_reader import EspNowSerialCsiReader
from ..acquisition.serial_reader import SerialCsiReader
from ..acquisition.udp_reader import UdpCsiReader
from ..acquisition.usb_reader import UsbReceiverManager
from ..profile import RadioProfileError, load_inventory_and_profile
from ..provisioning import ProvisioningError, configure_connected_devices
from .dashboard import (
    CsiDashboardPanel,
    DASHBOARD_TRACE_COUNTS,
    DEFAULT_DASHBOARD_SUBCARRIERS,
    DEFAULT_INSPECT_SUBCARRIER,
    DEFAULT_VIEW_SECONDS,
    VALID_SUBCARRIERS,
)
from .state import LiveState


GUI_FPS_CHOICES = (16, 24)
GUI_FPS_DEFAULT = 24


def frame_interval_ms(fps: int) -> int:
    """Whole-millisecond timer interval for a constant render rate."""

    return max(1, int(1000 / fps + 0.5))


GUI_INTERVAL_MS = frame_interval_ms(GUI_FPS_DEFAULT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Display live Espressif CSI data.")
    parser.add_argument(
        "--transport",
        choices=("serial", "udp", "espnow"),
        default="serial",
        help=(
            "Input transport: receiver CSV serial, UDP, or framed serial from "
            "the ESP-NOW transmitter gateway."
        ),
    )
    parser.add_argument(
        "--port",
        help=(
            "Serial device: receiver for serial transport or transmitter "
            "gateway for ESP-NOW transport"
        ),
    )
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="UDP bind address when --transport udp is selected",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=5500,
        help="UDP listen port when --transport udp is selected",
    )
    parser.add_argument(
        "--receiver-mac",
        help="Optional receiver MAC filter for binary UDP or ESP-NOW input",
    )
    parser.add_argument("--receiver-config", type=Path)
    parser.add_argument("--radio-profile", type=Path)
    parser.add_argument(
        "--receiver-id",
        help="receiver inventory ID to preview when multiple USB receivers are configured",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--fps",
        type=int,
        choices=GUI_FPS_CHOICES,
        default=GUI_FPS_DEFAULT,
        help="constant UI refresh rate in frames per second",
    )
    parser.add_argument(
        "--nominal-rate-hz",
        type=int,
        default=DEFAULT_NOMINAL_RATE_HZ,
        help="configured sensing transmission rate used for history sizing",
    )
    parser.add_argument(
        "--dashboard-subcarriers",
        type=int,
        choices=DASHBOARD_TRACE_COUNTS,
        default=DEFAULT_DASHBOARD_SUBCARRIERS,
        help="Number of representative physical subcarriers on the dashboard",
    )
    parser.add_argument(
        "--inspect-subcarrier",
        type=int,
        choices=VALID_SUBCARRIERS,
        default=DEFAULT_INSPECT_SUBCARRIER,
        help="Physical subcarrier shown in the detail trace",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the live GUI."""

    args = _parser().parse_args(argv)
    if bool(args.receiver_config) != bool(args.radio_profile):
        _parser().error("--receiver-config and --radio-profile must be provided together")
    inventory = profile = None
    profile_fingerprint = None
    if args.receiver_config is not None:
        try:
            inventory, profile, profile_fingerprint = load_inventory_and_profile(
                args.receiver_config, args.radio_profile
            )
        except RadioProfileError as exc:
            _parser().error(str(exc))
    profile_mode = inventory is not None
    if not profile_mode:
        _parser().error(
            "--receiver-config and --radio-profile are required for csi-viewer"
        )
    if args.receiver_id is not None and not profile_mode:
        _parser().error("--receiver-id requires --receiver-config and --radio-profile")
    if args.receiver_id is not None:
        receiver_ids = {receiver.id for receiver in inventory.receivers}
        if args.receiver_id not in receiver_ids:
            _parser().error(
                "--receiver-id must match one of the configured receivers: "
                + ", ".join(sorted(receiver_ids))
            )
    if args.nominal_rate_hz < 1:
        _parser().error("--nominal-rate-hz must be at least 1")
    if not profile_mode and args.transport in ("serial", "espnow") and not args.port:
        _parser().error(
            f"--port is required when --transport {args.transport} is selected"
        )
    if not profile_mode and args.transport == "udp" and args.port:
        _parser().error("--port cannot be used with --transport udp")
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError as exc:
        print("Install processor dependencies with: uv sync", file=sys.stderr)
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    app = QtWidgets.QApplication(sys.argv)
    state = LiveState(profile.nominal_rate_hz if profile_mode else args.nominal_rate_hz)
    usb_bindings = ()
    if profile_mode:
        # Configure whatever is plugged in before binding, so a band or channel
        # change is just another viewer launch instead of a separate command.
        try:
            reconfigured = configure_connected_devices(inventory, profile)
        except ProvisioningError as exc:
            print(f"Unable to configure connected boards: {exc}", file=sys.stderr)
            return 2
        if reconfigured:
            print(f"configured {len(reconfigured)} board(s) for {profile.profile_id}")
        reader = UsbReceiverManager(
            inventory,
            profile,
            args.output_dir,
            on_status=state.set_status,
        )
        try:
            usb_bindings = reader.bind()
        except RuntimeError as exc:
            print(f"Unable to bind configured USB receivers: {exc}", file=sys.stderr)
            return 2
        state.configure_receivers(
            {
                receiver_id: usb_reader.buffer
                for receiver_id, usb_reader in reader.readers.items()
            },
            args.receiver_id,
        )
    elif args.transport == "udp":
        reader = UdpCsiReader(
            args.listen_host,
            args.listen_port,
            state.buffer,
            args.output_dir,
            receiver_mac=args.receiver_mac,
            on_status=state.set_status,
        )
    elif args.transport == "espnow":
        reader = EspNowSerialCsiReader(
            args.port,
            args.baud,
            state.buffer,
            args.output_dir,
            receiver_mac=args.receiver_mac,
            on_status=state.set_status,
        )
    else:
        reader = SerialCsiReader(
            args.port,
            args.baud,
            state.buffer,
            args.output_dir,
            on_status=state.set_status,
        )

    window = QtWidgets.QMainWindow()
    window.setWindowTitle(
        "Espressif CSI live viewer"
        if not profile_mode
        else f"CSI viewer — {profile.profile_id} ({profile.band} ch {profile.channel})"
    )
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    panel = CsiDashboardPanel(
        state,
        fps=args.fps,
        dashboard_subcarriers=args.dashboard_subcarriers,
        inspect_subcarrier=args.inspect_subcarrier,
        window_seconds=DEFAULT_VIEW_SECONDS,
        receivers=[binding.receiver_id for binding in usb_bindings] or None,
    )
    layout.addWidget(panel.widget)
    window.setCentralWidget(central)
    status_label = QtWidgets.QLabel("starting")
    status_label.setMaximumWidth(260)
    status_label.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Ignored,
        QtWidgets.QSizePolicy.Policy.Preferred,
    )
    metrics_label = QtWidgets.QLabel(
        "seq — | rec 0 | bad 0 | sense 0 | record 0 | batch 0 | drops 0/0/0 | age —"
    )
    status_bar = QtWidgets.QStatusBar()
    status_bar.addWidget(status_label, 1)
    status_bar.addPermanentWidget(metrics_label)
    window.setStatusBar(status_bar)
    window.resize(800, 680)

    def update_status() -> None:
        message, connected = state.get_status()
        selected_reader = reader
        if profile_mode:
            selected_reader = reader.readers[state.selected_receiver_id]
            connected = selected_reader.connected and not selected_reader.profile_mismatch
            message = f"{state.selected_receiver_id}: {message}"
        status = message if connected else f"offline: {message}"
        status_label.setText(status if len(status) <= 42 else f"{status[:41]}…")
        status_label.setToolTip(status)
        sequence = state.buffer.last_sequence
        if selected_reader.last_valid_time is None:
            age = "—"
        else:
            age = f"{max(0.0, time.monotonic() - selected_reader.last_valid_time):.1f}s"
        record_missing = getattr(selected_reader, "transport_missing", 0)
        batch_missing = getattr(selected_reader, "batch_missing", 0)
        receiver_stats = getattr(selected_reader, "receiver_stats", None)
        sensing_missing = (
            receiver_stats.sensing_missing
            if receiver_stats is not None
            else "—"
        )
        queue_drops = receiver_stats.queue_drops if receiver_stats is not None else "—"
        ip_drops = (
            receiver_stats.unavailable_ip_drops
            if receiver_stats is not None
            else "—"
        )
        send_errors = receiver_stats.send_errors if receiver_stats is not None else "—"
        receiver_label = (
            f"  |  receiver {state.selected_receiver_id}"
            if profile_mode
            else ""
        )
        metrics_label.setText(
            f"seq {sequence if sequence is not None else '—'}  |  "
            f"rec {state.buffer.received_records}  |  "
            f"bad {getattr(selected_reader, 'malformed_lines', 0)}  |  "
            f"sense {sensing_missing}  |  record {record_missing}  |  "
            f"batch {batch_missing}  |  drops {queue_drops}/{ip_drops}/{send_errors}"
            f"  |  age {age}"
            f"{receiver_label}"
            f"  |  {panel.measured_fps:.0f} data fps  |  ui {args.fps} fps"
            f"  |  {panel.phase_mode}"
            f"  |  phase gaps {panel.phase_gap_count}"
        )

    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    timer.timeout.connect(panel.refresh)
    timer.start(frame_interval_ms(args.fps))

    status_timer = QtCore.QTimer()
    status_timer.timeout.connect(update_status)
    status_timer.start(250)

    def close() -> None:
        reader.stop()

    app.aboutToQuit.connect(close)
    reader.start()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
