"""Two-window operator/performer collection application."""

from __future__ import annotations

import argparse
from collections import deque
import os
from pathlib import Path
import sys
import time
from typing import Any, Sequence

from .capture import SessionMetadata
from .controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionState,
)
from .protocol import ProtocolError, load_protocol
from ..radio.acquisition.buffer import DEFAULT_NOMINAL_RATE_HZ, RollingCsiBuffer
from ..radio.acquisition.espnow_serial_reader import EspNowSerialCsiReader
from ..radio.acquisition.serial_reader import SerialCsiReader
from ..radio.acquisition.udp_reader import UdpCsiReader
from ..radio.acquisition.usb_reader import UsbReceiverManager
from ..radio.profile import RadioProfileError, load_inventory_and_profile
from ..radio.provisioning import ProvisioningError, configure_connected_devices
from ..radio.visualization.widget import CsiDashboardWidget


DEFAULT_PROTOCOL = Path("configs/collection/fall_v1.json")
COLLECTOR_FPS_CHOICES = (16, 24)
COLLECTOR_FPS_DEFAULT = 24


def frame_interval_ms(fps: int) -> int:
    """Whole-millisecond timer interval for a constant render rate."""

    return max(1, int(1000 / fps + 0.5))


COLLECTOR_UI_INTERVAL_MS = frame_interval_ms(COLLECTOR_FPS_DEFAULT)
# The CSI dashboard is the collector's viewer, so it follows the same pacing.
COLLECTOR_RADIO_REFRESH_MS = COLLECTOR_UI_INTERVAL_MS
COLLECTOR_RADIO_PREVIEW_SECONDS = 3.0
COLLECTOR_RADIO_PREVIEW_POINTS = 90


def _format_radio_metrics(reader: Any, nominal_rate_hz: int) -> str:
    """Format host and firmware stages without turning missing data into zero."""

    snapshot_fn = getattr(reader, "telemetry_snapshot", None)
    if snapshot_fn is None:
        return f"CSI records: {reader.buffer.received_records} | telemetry: unavailable"
    snapshot = snapshot_fn()
    receiver = snapshot.receiver_stats
    transmitter = snapshot.transmitter_stats
    gateway = snapshot.gateway_stats
    receiver_text = (
        "unavailable"
        if receiver is None
        else (
            f"sense-missing {receiver.sensing_missing} | "
            f"queue {receiver.queue_drops} | "
            f"send {receiver.send_errors}"
        )
    )
    transmitter_text = (
        "unavailable"
        if transmitter is None
        else (
            f"tx attempts {transmitter.attempts} | "
            f"async-fail {transmitter.asynchronous_failures}"
        )
    )
    gateway_text = (
        "unavailable"
        if gateway is None
        else (
            f"gateway queue {gateway.queue_drops} | "
            f"serial {gateway.serial_errors}"
        )
    )
    return (
        f"CSI records: {snapshot.records} / {nominal_rate_hz} Hz | "
        f"host sequence gaps {snapshot.host_missing_sequences} | "
        f"transport gaps {snapshot.transport_missing} | "
        f"batch gaps {snapshot.batch_missing}\n"
        f"{transmitter_text} | receiver {receiver_text} | {gateway_text}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guide and record operator-confirmed USB radio collection trials."
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument(
        "--transport", choices=("serial", "udp", "espnow"), default="espnow"
    )
    parser.add_argument("--port", help="Serial device for serial or espnow transport")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=5500)
    parser.add_argument("--receiver-mac")
    parser.add_argument("--receiver-config", type=Path)
    parser.add_argument("--radio-profile", type=Path)
    parser.add_argument(
        "--manual-confirmation",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="require operator confirmation during ACTION before recovery",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/sessions"))
    parser.add_argument(
        "--fps",
        type=int,
        choices=COLLECTOR_FPS_CHOICES,
        default=COLLECTOR_FPS_DEFAULT,
        help="constant UI refresh rate in frames per second",
    )
    parser.add_argument(
        "--nominal-rate-hz",
        type=int,
        default=DEFAULT_NOMINAL_RATE_HZ,
        help="configured sensing transmission rate recorded with the session",
    )
    return parser


class _MetadataDialog:
    """Construct the metadata dialog lazily so importing this module is cheap."""

    def __init__(self, QtWidgets: Any) -> None:
        self.QtWidgets = QtWidgets
        self.dialog = QtWidgets.QDialog()
        self.dialog.setWindowTitle("Start collection session")
        form = QtWidgets.QFormLayout(self.dialog)
        self.participant = QtWidgets.QLineEdit()
        self.participant.setPlaceholderText("pseudonymous participant ID")
        self.operator = QtWidgets.QLineEdit()
        self.location = QtWidgets.QLineEdit()
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setMaximumHeight(80)
        form.addRow("Participant ID *", self.participant)
        form.addRow("Operator", self.operator)
        form.addRow("Location", self.location)
        form.addRow("Notes", self.notes)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.dialog.reject)
        form.addRow(buttons)

    def _accept(self) -> None:
        if not self.participant.text().strip():
            self.QtWidgets.QMessageBox.warning(
                self.dialog, "Participant ID required", "Enter a pseudonymous participant ID."
            )
            return
        self.dialog.accept()

    def get(self) -> SessionMetadata | None:
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return SessionMetadata(
            participant_id=self.participant.text().strip(),
            operator=self.operator.text().strip(),
            location=self.location.text().strip(),
            notes=self.notes.toPlainText().strip(),
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the operator and performer collection windows."""

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
    profile_mode = inventory is not None and profile is not None
    if not profile_mode:
        _parser().error(
            "--receiver-config and --radio-profile are required for collection"
        )
    if not profile_mode and args.transport in ("serial", "espnow") and not args.port:
        _parser().error(f"--port is required when --transport {args.transport} is selected")
    if not profile_mode and args.transport == "udp" and args.port:
        _parser().error("--port cannot be used with --transport udp")
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError as exc:
        print("Install collection dependencies with: uv sync --extra radio", file=sys.stderr)
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    try:
        protocol = load_protocol(args.protocol)
    except ProtocolError as exc:
        print(f"Invalid collection protocol: {exc}", file=sys.stderr)
        return 2
    app = QtWidgets.QApplication(list(sys.argv))
    metadata = _MetadataDialog(QtWidgets).get()
    if metadata is None:
        return 0

    if args.nominal_rate_hz < 1:
        _parser().error("--nominal-rate-hz must be at least 1")
    reader_holder: dict[str, Any] = {}

    def telemetry_provider() -> Any:
        reader = reader_holder.get("reader")
        snapshot = getattr(reader, "telemetry_snapshot", None)
        return snapshot() if snapshot is not None else None

    nominal_rate_hz = profile.nominal_rate_hz if profile_mode else args.nominal_rate_hz
    buffer = RollingCsiBuffer(
        nominal_rate=nominal_rate_hz, seconds=10, max_records=10_000
    )
    controller = SessionController(
        protocol,
        args.output_dir,
        environment={
            "transport": args.transport,
            "port": args.port,
            "listen_host": args.listen_host,
            "listen_port": args.listen_port,
            "receiver_mac": args.receiver_mac,
            "nominal_rate_hz": nominal_rate_hz,
            "receiver_ids": (
                {device.mac: device.id for device in inventory.receivers}
                if profile_mode
                else {}
            ),
            "receiver_config": str(args.receiver_config) if profile_mode else None,
            "radio_inventory": inventory.as_dict() if profile_mode else None,
            "radio_profile": profile.as_dict() if profile_mode else (
                "espnow-50hz-mcs0-20dbm"
                if args.transport == "espnow" and args.nominal_rate_hz == 50
                else "custom"
            ),
            "radio_profile_fingerprint": profile_fingerprint if profile_mode else None,
        },
        telemetry_provider=telemetry_provider,
        manual_confirmation_required=args.manual_confirmation or profile_mode,
    )

    reader_status = deque(maxlen=20)

    def radio_status(message: str, connected: bool) -> None:
        reader_status.appendleft((message, connected))
        if profile_mode:
            controller.record_event(
                "receiver_status",
                message=message,
                connected=connected,
            )

    if profile_mode:
        # The collector configures the radios itself: plug the boards in, start
        # the session, and the profile is applied before any receiver binds.
        try:
            reconfigured = configure_connected_devices(
                inventory, profile, log=lambda message: reader_status.appendleft((message, True))
            )
        except ProvisioningError as exc:
            print(f"Unable to configure connected boards: {exc}", file=sys.stderr)
            return 2
        if reconfigured:
            reader_status.appendleft(
                (f"configured {len(reconfigured)} board(s) for {profile.profile_id}", True)
            )
        reader = UsbReceiverManager(
            inventory,
            profile,
            args.output_dir,
            on_status=radio_status,
            record_sink=controller.write_radio,
            clock_sync_sink=controller.write_clock_sync,
        )
    elif args.transport == "espnow":
        reader = EspNowSerialCsiReader(
            args.port,
            args.baud,
            buffer,
            args.output_dir,
            receiver_mac=args.receiver_mac,
            on_status=radio_status,
            record_sink=controller.write_radio,
            clock_sync_sink=controller.write_clock_sync,
        )
    elif args.transport == "serial":
        reader = SerialCsiReader(
            args.port,
            args.baud,
            buffer,
            args.output_dir,
            on_status=radio_status,
            record_sink=controller.write_radio,
        )
    else:
        reader = UdpCsiReader(
            args.listen_host,
            args.listen_port,
            buffer,
            args.output_dir,
            receiver_mac=args.receiver_mac,
            on_status=radio_status,
            record_sink=controller.write_radio,
        )
    reader_holder["reader"] = reader
    if profile_mode:
        try:
            reader.bind()
        except RuntimeError as exc:
            print(f"Unable to bind configured USB receivers: {exc}", file=sys.stderr)
            return 2
        controller.update_environment(
            {
                "receiver_bindings": {
                    receiver_id: {
                        "mac": binding.mac,
                        "target": binding.target,
                        "port": binding.port,
                        "profile_fingerprint": binding.profile_fingerprint,
                    }
                    for receiver_id, binding in reader.bindings.items()
                }
            }
        )
        buffer = reader.buffer

    operator = QtWidgets.QMainWindow()
    operator.setWindowTitle(f"Collection operator — {protocol.title}")
    central = QtWidgets.QWidget()
    operator.setCentralWidget(central)
    layout = QtWidgets.QVBoxLayout(central)
    header = QtWidgets.QHBoxLayout()
    state_label = QtWidgets.QLabel("SETUP")
    state_label.setStyleSheet("font-size: 20px; font-weight: bold;")
    progress_label = QtWidgets.QLabel("0/0")
    health_label = QtWidgets.QLabel("waiting for devices")
    header.addWidget(state_label)
    header.addWidget(progress_label)
    if profile_mode:
        profile_label = QtWidgets.QLabel(
            f"profile: {profile.profile_id} | {profile.band} ch {profile.channel} | "
            f"fp {profile_fingerprint}"
        )
        profile_label.setToolTip("Read-only profile; rerun provisioning to change channel")
        header.addWidget(profile_label, 1)
    header.addWidget(health_label, 1)
    layout.addLayout(header)

    message_label = QtWidgets.QLabel("enter session metadata")
    message_label.setWordWrap(True)
    message_label.setMinimumHeight(42)
    layout.addWidget(message_label)

    content = QtWidgets.QHBoxLayout()
    left = QtWidgets.QVBoxLayout()
    trial_list = QtWidgets.QListWidget()
    for trial in protocol.trials:
        trial_list.addItem(
            f"{trial.ordinal:02d}. {trial.scenario.title} [{trial.scenario.activity_label}]"
        )
    left.addWidget(QtWidgets.QLabel("Protocol queue"))
    left.addWidget(trial_list, 1)
    controls = QtWidgets.QGridLayout()
    buttons: dict[OperatorCommand, Any] = {}
    button_specs = (
        (OperatorCommand.START_TRIAL, "Start trial"),
        (OperatorCommand.CONFIRM_ACTION, "Confirm action"),
        (OperatorCommand.ABORT, "Abort"),
        (OperatorCommand.ACCEPT, "Accept"),
        (OperatorCommand.RETRY, "Retry"),
        (OperatorCommand.SKIP, "Skip"),
        (OperatorCommand.END_SESSION, "End session"),
    )
    for index, (command, text) in enumerate(button_specs):
        button = QtWidgets.QPushButton(text)
        buttons[command] = button
        controls.addWidget(button, index // 2, index % 2)
    left.addLayout(controls)
    content.addLayout(left, 1)

    right = QtWidgets.QVBoxLayout()
    csi_dashboard = None
    try:
        csi_dashboard = CsiDashboardWidget(
            buffer,
            window_seconds=COLLECTOR_RADIO_PREVIEW_SECONDS,
            max_points=COLLECTOR_RADIO_PREVIEW_POINTS,
        )
        right.addWidget(csi_dashboard.widget, 1)
    except ImportError:
        right.addWidget(QtWidgets.QLabel("Install pyqtgraph for live CSI plots."), 1)
    metrics_label = QtWidgets.QLabel("CSI records: 0")
    metrics_label.setWordWrap(True)
    right.addWidget(metrics_label)
    content.addLayout(right, 2)
    layout.addLayout(content, 1)

    performer = QtWidgets.QMainWindow()
    performer.setWindowTitle("Performer guidance")
    performer_central = QtWidgets.QWidget()
    performer.setCentralWidget(performer_central)
    performer_layout = QtWidgets.QVBoxLayout(performer_central)
    performer_layout.setContentsMargins(48, 48, 48, 48)
    performer_state = QtWidgets.QLabel("WAITING")
    performer_state.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    performer_state.setStyleSheet("font-size: 34px; font-weight: bold;")
    performer_title = QtWidgets.QLabel(protocol.title)
    performer_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    performer_title.setStyleSheet("font-size: 24px;")
    performer_instruction = QtWidgets.QLabel("Wait for the operator")
    performer_instruction.setWordWrap(True)
    performer_instruction.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    performer_instruction.setStyleSheet("font-size: 32px;")
    performer_timer = QtWidgets.QLabel("")
    performer_timer.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    performer_timer.setStyleSheet("font-size: 96px; font-weight: bold;")
    performer_layout.addStretch()
    performer_layout.addWidget(performer_state)
    performer_layout.addWidget(performer_title)
    performer_layout.addWidget(performer_instruction)
    performer_layout.addWidget(performer_timer)
    performer_layout.addStretch()

    screens = app.screens()
    if len(screens) > 1:
        performer.setGeometry(screens[1].geometry())
        performer.showFullScreen()
    else:
        performer.show()
        health_label.setText("warning: no second display; performer view is windowed")

    def dispatch(command: OperatorCommand) -> None:
        try:
            controller.dispatch(command)
        except (RuntimeError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(operator, "Collection command unavailable", str(exc))

    for command, button in buttons.items():
        button.clicked.connect(lambda _checked=False, c=command: dispatch(c))

    def update_view() -> None:
        now = time.monotonic()
        radio_last = getattr(reader, "last_valid_time", None)
        radio_live = radio_last is not None and now - radio_last < 2.5
        if reader_status:
            radio_detail = reader_status[0][0]
        else:
            radio_detail = (
                "waiting for USB receiver stream"
                if profile_mode
                else "waiting for radio"
            )
        clock_ready = (
            reader.clock_sync_ready
            if profile_mode
            else (
                args.transport != "espnow"
                or getattr(getattr(reader, "clock_sync", None), "estimate", None)
                is not None
            )
        )
        controller.update_health(
            HealthSnapshot(
                radio_live=radio_live,
                storage_ready=os.access(args.output_dir.parent, os.W_OK)
                if args.output_dir.parent.exists()
                else True,
                clock_sync_ready=clock_ready,
                radio_detail=radio_detail,
                storage_detail="output directory is not writable"
                if not os.access(args.output_dir.parent, os.W_OK)
                and args.output_dir.parent.exists()
                else "ready",
            )
        )
        snapshot = controller.tick()
        state_label.setText(snapshot.state.value.upper())
        progress_label.setText(snapshot.progress_text)
        message_label.setText(snapshot.message)
        health_label.setText(
            f"radio={'ok' if snapshot.health.radio_live else 'offline'} | "
            f"sync={'ok' if snapshot.health.clock_sync_ready else 'warming'}"
        )
        if snapshot.trial is not None:
            trial_list.setCurrentRow(snapshot.trial_index)
        active_states = (SessionState.COUNTDOWN, SessionState.ACTION, SessionState.RECOVERY)
        enabled = {
            OperatorCommand.START_TRIAL: snapshot.state is SessionState.READY
            and snapshot.health.radio_live
            and snapshot.health.storage_ready
            and snapshot.health.clock_sync_ready,
            OperatorCommand.CONFIRM_ACTION: snapshot.state is SessionState.ACTION
            and not snapshot.action_confirmed,
            OperatorCommand.ABORT: snapshot.state in active_states,
            OperatorCommand.ACCEPT: snapshot.state is SessionState.REVIEW
            and snapshot.attempt_status != "invalid",
            OperatorCommand.RETRY: snapshot.state is SessionState.REVIEW,
            OperatorCommand.SKIP: snapshot.state in (SessionState.READY, SessionState.REVIEW),
            OperatorCommand.END_SESSION: snapshot.state is not SessionState.COMPLETE,
        }
        for command, button in buttons.items():
            button.setEnabled(enabled[command])

        if snapshot.trial is None:
            performer_state.setText("COMPLETE")
            performer_instruction.setText(snapshot.message)
            performer_timer.setText("")
        elif snapshot.state is SessionState.COUNTDOWN:
            performer_state.setText("GET READY")
            performer_instruction.setText(snapshot.trial.scenario.instruction)
            performer_timer.setText(str(max(1, int(snapshot.phase_remaining_seconds + 0.999))))
        elif snapshot.state is SessionState.ACTION:
            performer_state.setText("PERFORM")
            performer_instruction.setText(snapshot.trial.scenario.title)
            performer_timer.setText(str(max(1, int(snapshot.phase_remaining_seconds + 0.999))))
        elif snapshot.state is SessionState.RECOVERY:
            performer_state.setText("RECOVER")
            performer_instruction.setText("Remain still until the operator continues.")
            performer_timer.setText(str(max(1, int(snapshot.phase_remaining_seconds + 0.999))))
        elif snapshot.state is SessionState.REVIEW:
            performer_state.setText("WAIT")
            performer_instruction.setText("The operator is reviewing this attempt.")
            performer_timer.setText("")
        else:
            performer_state.setText("WAITING")
            performer_instruction.setText("Wait for the operator.")
            performer_timer.setText("")

        metrics_label.setText(_format_radio_metrics(reader, nominal_rate_hz))

    controller.start_session(metadata)
    reader.start()
    ui_interval_ms = frame_interval_ms(args.fps)
    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    timer.setInterval(ui_interval_ms)
    timer.timeout.connect(update_view)
    timer.start()
    dashboard_timer = None
    if csi_dashboard is not None:
        dashboard_timer = QtCore.QTimer()
        dashboard_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        dashboard_timer.setInterval(ui_interval_ms)
        dashboard_timer.timeout.connect(csi_dashboard.refresh)
        dashboard_timer.start()

    def close() -> None:
        if controller.state is not SessionState.COMPLETE:
            try:
                controller.dispatch(OperatorCommand.END_SESSION)
            except RuntimeError:
                pass
        reader.stop()

    app.aboutToQuit.connect(close)
    operator.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
