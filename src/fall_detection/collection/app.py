"""Collection console with a live CSI dashboard and scenario controls."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from ..radio.acquisition.gateway_reader import GatewayReceiverManager
from ..radio.acquisition.buffer import DEFAULT_NOMINAL_RATE_HZ, RollingCsiBuffer
from ..radio.espnow_config import EspnowTransportConfig
from ..radio.profile import RadioProfileError, load_inventory_and_profile
from ..radio.visualization.dashboard import DEFAULT_VIEW_SECONDS, CsiDashboardPanel
from ..radio.visualization.state import LiveState
from .capture import SessionMetadata
from .controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionSnapshot,
    SessionState,
)
from .protocol import (
    CollectionProtocol,
    ProtocolError,
    Trial,
    load_protocol,
    select_blocks,
)

DEFAULT_PROTOCOL = Path("configs/collection/fall_v1.json")
COLLECTOR_FPS_CHOICES = (16, 24)
COLLECTOR_FPS_DEFAULT = 24
COLLECTOR_VIEW_SECONDS = DEFAULT_VIEW_SECONDS


def frame_interval_ms(fps: int) -> int:
    """Whole-millisecond timer interval for a constant render rate."""

    return max(1, int(1000 / fps + 0.5))


COLLECTOR_UI_INTERVAL_MS = frame_interval_ms(COLLECTOR_FPS_DEFAULT)

_STATE_COLORS = {
    SessionState.SETUP: "#6b7280",
    SessionState.READY: "#2563eb",
    SessionState.COUNTDOWN: "#d97706",
    SessionState.ACTION: "#dc2626",
    SessionState.RECOVERY: "#7c3aed",
    SessionState.REVIEW: "#0d9488",
    SessionState.COMPLETE: "#16a34a",
}

_STYLESHEET = """
QFrame#card {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 8px;
}
QLabel#cardTitle {
    color: palette(mid);
    font-size: 11px;
    font-weight: 700;
}
QLabel#scenarioTitle {
    font-size: 16px;
    font-weight: 700;
}
QLabel#instruction {
    font-size: 13px;
}
QLabel#message {
    color: palette(mid);
    font-size: 12px;
    font-style: italic;
}
QLabel#phase {
    font-size: 28px;
    font-weight: 700;
}
QPushButton:disabled {
    color: #9ca3af;
}
"""


def _state_badge_style(state: SessionState) -> str:
    """Return the badge stylesheet for one collection state."""

    color = _STATE_COLORS.get(state, "#6b7280")
    return (
        f"background: {color}; color: white; border-radius: 6px;"
        "padding: 4px 12px; font-size: 15px; font-weight: 700;"
    )


def _format_radio_metrics(
    reader: Any, nominal_rate_hz: int, snapshot: Any | None = None
) -> str:
    """Format host and firmware stages without turning missing data into zero."""

    if snapshot is None:
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
        else (f"gateway queue {gateway.queue_drops} | serial {gateway.serial_errors}")
    )
    return (
        f"CSI records: {snapshot.records} / {nominal_rate_hz} Hz | "
        f"host sequence gaps {snapshot.host_missing_sequences} | "
        f"transport gaps {snapshot.transport_missing} | "
        f"batch gaps {snapshot.batch_missing}\n"
        f"{transmitter_text} | receiver {receiver_text} | {gateway_text}"
    )


def _status_metrics(
    reader: Any, nominal_rate_hz: int, measured_fps: float
) -> tuple[str, str]:
    """Return the compact status strip and its detailed telemetry tooltip."""

    snapshot_fn = getattr(reader, "telemetry_snapshot", None)
    snapshot = snapshot_fn() if snapshot_fn is not None else None
    if snapshot is None:
        text = f"CSI records: {reader.buffer.received_records} | telemetry: unavailable"
        return text, text
    receiver = snapshot.receiver_stats
    missing = "—" if receiver is None else receiver.sensing_missing
    queue = "—" if receiver is None else receiver.queue_drops
    send = "—" if receiver is None else receiver.send_errors
    sequence = reader.buffer.last_sequence
    compact = (
        f"seq {sequence if sequence is not None else '—'}  |  "
        f"rec {reader.buffer.received_records}  |  "
        f"sense {missing}  |  queue {queue}  |  send {send}  |  "
        f"{measured_fps:.0f} data fps"
    )
    return compact, _format_radio_metrics(reader, nominal_rate_hz, snapshot)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guide and record operator-confirmed ESP-NOW gateway radio collection trials."
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--transport", choices=("espnow_gateway",), default="espnow_gateway")
    parser.add_argument(
        "--gateway-config",
        type=Path,
        help="ESP-NOW gateway transport policy JSON (round robin by default)",
    )
    parser.add_argument("--gateway-port", help="Native USB C6 gateway port")
    parser.add_argument("--port", help="Native USB transmitter control port")
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
    """Session metadata plus the scenario blocks this session will collect."""

    def __init__(self, QtWidgets: Any, protocol: CollectionProtocol) -> None:
        self.QtWidgets = QtWidgets
        self.protocol = protocol
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

        scenarios = QtWidgets.QGroupBox("Scenarios")
        scenario_layout = QtWidgets.QVBoxLayout(scenarios)
        self._blocks: list[tuple[str, Any, int]] = []
        for block_id, block_title, block_scenarios in protocol.blocks:
            trials = sum(scenario.repetitions for scenario in block_scenarios)
            checkbox = QtWidgets.QCheckBox(f"{block_title}  ({trials} trials)")
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._update_total)
            scenario_layout.addWidget(checkbox)
            self._blocks.append((block_id, checkbox, trials))
        self.total_label = QtWidgets.QLabel("")
        scenario_layout.addWidget(self.total_label)
        form.addRow(scenarios)
        self._update_total()

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.dialog.reject)
        form.addRow(buttons)

    def _selected_trials(self) -> int:
        return sum(trials for _id, box, trials in self._blocks if box.isChecked())

    def _update_total(self, *_args: Any) -> None:
        total = self._selected_trials()
        noun = "trial" if total == 1 else "trials"
        self.total_label.setText(f"this session collects {total} {noun}")

    def _accept(self) -> None:
        if not self.participant.text().strip():
            self.QtWidgets.QMessageBox.warning(
                self.dialog,
                "Participant ID required",
                "Enter a pseudonymous participant ID.",
            )
            return
        if not self.block_ids():
            self.QtWidgets.QMessageBox.warning(
                self.dialog,
                "Scenario required",
                "Select at least one scenario block to collect.",
            )
            return
        self.dialog.accept()

    def block_ids(self) -> tuple[str, ...]:
        """Return the selected scenario block identifiers in protocol order."""

        return tuple(
            block_id
            for block_id, checkbox, _trials in self._blocks
            if checkbox.isChecked()
        )

    def get(self) -> SessionMetadata | None:
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return SessionMetadata(
            participant_id=self.participant.text().strip(),
            operator=self.operator.text().strip(),
            location=self.location.text().strip(),
            notes=self.notes.toPlainText().strip(),
        )


class _ScenarioDetailDialog:
    """Read-only detail card for one protocol scenario.

    The window is a non-modal tool window so the operator can inspect an
    upcoming condition without losing access to the collection controls —
    a modal dialog would block "Confirm action" during a live trial.
    """

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        trial: Trial,
        *,
        status: str,
        total_trials: int,
        parent: Any = None,
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.trial = trial
        scenario = trial.scenario
        self.window = QtWidgets.QDialog(parent)
        self.window.setWindowFlag(QtCore.Qt.WindowType.Tool, True)
        self.window.setModal(False)
        self.window.setWindowTitle(f"Scenario {trial.ordinal:03d} — {scenario.title}")
        self.window.resize(460, 560)

        layout = QtWidgets.QVBoxLayout(self.window)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self.status_label = QtWidgets.QLabel(
            f"trial {trial.ordinal}/{total_trials}  ·  {status}"
        )
        self.status_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        self.title_label = QtWidgets.QLabel(scenario.title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.meta_label = QtWidgets.QLabel(
            f"{scenario.activity_label}  ·  {scenario.block_title}"
            f"  ·  repetition {trial.repetition}/{scenario.repetitions}"
        )
        self.meta_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addWidget(self.status_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.meta_label)
        rule = QtWidgets.QFrame()
        rule.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        rule.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(rule)

        self.instruction_label = self._section(
            layout, "Instruction", scenario.instruction
        )
        self.timing_label = self._section(
            layout,
            "Timing",
            f"countdown {scenario.countdown_seconds:g} s  ·  "
            f"action {scenario.action_seconds:g} s  ·  "
            f"recovery {scenario.recovery_seconds:g} s",
        )
        attributes = scenario.attributes
        self.direction_label = self._section(
            layout,
            "Directions",
            f"start {attributes.get('start_direction') or '—'}  ·  "
            f"end {attributes.get('end_direction') or '—'}  ·  "
            f"frame {attributes.get('direction_frame') or '—'}",
        )
        self.safety_label = None
        safety_note = attributes.get("safety_note")
        if safety_note:
            self.safety_label = self._section(layout, "Safety", str(safety_note))
            self.safety_label.setStyleSheet("color: #b45309; font-size: 11px;")
        self.id_label = self._section(layout, "Scenario ID", scenario.id)
        self.id_label.setStyleSheet("color: palette(mid); font-size: 11px;")
        layout.addStretch()

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.window.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _section(self, layout: Any, title: str, value: str) -> Any:
        QtWidgets = self.QtWidgets
        heading = QtWidgets.QLabel(title.upper())
        heading.setStyleSheet("color: palette(mid); font-size: 10px; font-weight: 700;")
        body = QtWidgets.QLabel(value)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            self.QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(heading)
        layout.addWidget(body)
        return body

    def show(self) -> None:
        """Show the window without blocking the operator console."""

        self.window.show()
        self.window.raise_()
        self.window.activateWindow()


class _OperatorWindow:
    """Operator window: scenario and collection controls beside the CSI dashboard.

    The dashboard is the same :class:`CsiDashboardPanel` the ``csi-viewer`` uses,
    so the operator previews exactly what the analyst sees.  Everything the
    collection state machine produces lives in the sidebar.
    """

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        *,
        protocol: CollectionProtocol,
        profile_text: str | None,
        panel: CsiDashboardPanel,
        on_command: Any,
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.panel = panel
        self._on_command = on_command
        self._trials = protocol.trials
        self._trial_by_ordinal = {trial.ordinal: trial for trial in protocol.trials}
        self._detail_windows: list[_ScenarioDetailDialog] = []
        self._current_ordinal: int | None = None
        self._resolved_count = 0
        self._queue_key: tuple[Any, int | None] | None = None
        self._rendered_state: SessionState | None = None

        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle(f"Collection operator — {protocol.title}")
        self.window.setStyleSheet(_STYLESHEET)
        central = QtWidgets.QWidget()
        self.window.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        sidebar = QtWidgets.QWidget()
        sidebar.setFixedWidth(360)
        side = QtWidgets.QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        root.addWidget(sidebar)
        root.addWidget(panel.widget, 1)

        side.addWidget(self._build_session_card(profile_text))
        side.addWidget(self._build_scenario_card())
        side.addWidget(self._build_queue_card(), 1)
        side.addWidget(self._build_command_card())

        self.status_label = QtWidgets.QLabel("waiting for receivers")
        self.status_label.setMaximumWidth(420)
        self.status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.metrics_label = QtWidgets.QLabel("rec 0")
        status_bar = QtWidgets.QStatusBar()
        status_bar.addWidget(self.status_label, 1)
        status_bar.addPermanentWidget(self.metrics_label)
        self.window.setStatusBar(status_bar)
        self.window.resize(1180, 760)

    # -- construction --------------------------------------------------

    def _card(self, title: str) -> tuple[Any, Any]:
        QtWidgets = self.QtWidgets
        frame = QtWidgets.QFrame()
        frame.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        heading = QtWidgets.QLabel(title.upper())
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
        return frame, layout

    def _build_session_card(self, profile_text: str | None) -> Any:
        QtWidgets = self.QtWidgets
        frame, layout = self._card("Session")
        header = QtWidgets.QHBoxLayout()
        self.state_label = QtWidgets.QLabel("SETUP")
        self.state_label.setStyleSheet(_state_badge_style(SessionState.SETUP))
        self.progress_label = QtWidgets.QLabel("0/0")
        self.progress_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        header.addWidget(self.state_label)
        header.addStretch()
        header.addWidget(self.progress_label)
        layout.addLayout(header)
        self.health_label = QtWidgets.QLabel("radio offline | sync warming | storage —")
        self.health_label.setWordWrap(True)
        layout.addWidget(self.health_label)
        if profile_text:
            profile_label = QtWidgets.QLabel(profile_text)
            profile_label.setWordWrap(True)
            profile_label.setStyleSheet("color: palette(mid); font-size: 11px;")
            layout.addWidget(profile_label)
        return frame

    def _build_scenario_card(self) -> Any:
        QtWidgets = self.QtWidgets
        frame, layout = self._card("Scenario")
        self.scenario_title = QtWidgets.QLabel("Protocol complete")
        self.scenario_title.setObjectName("scenarioTitle")
        self.scenario_title.setWordWrap(True)
        self.scenario_meta = QtWidgets.QLabel("—")
        self.scenario_meta.setStyleSheet("color: palette(mid); font-size: 11px;")
        meta_row = QtWidgets.QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.addWidget(self.scenario_meta, 1)
        self.detail_button = QtWidgets.QPushButton("Details")
        self.detail_button.setFlat(True)
        self.detail_button.setToolTip("Open the full detail card for this scenario")
        self.detail_button.setCursor(self.QtCore.Qt.CursorShape.PointingHandCursor)
        self.detail_button.clicked.connect(self.show_current_details)
        self.detail_button.setEnabled(False)
        meta_row.addWidget(self.detail_button)
        self.instruction_label = QtWidgets.QLabel("Waiting for the first trial")
        self.instruction_label.setObjectName("instruction")
        self.instruction_label.setWordWrap(True)
        self.message_label = QtWidgets.QLabel("")
        self.message_label.setObjectName("message")
        self.message_label.setWordWrap(True)
        self.phase_label = QtWidgets.QLabel("—")
        self.phase_label.setObjectName("phase")
        layout.addWidget(self.scenario_title)
        layout.addLayout(meta_row)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self.message_label)
        layout.addWidget(self.phase_label)
        return frame

    def _build_queue_card(self) -> Any:
        QtWidgets = self.QtWidgets
        frame, layout = self._card("Protocol queue")
        self.queue_filter = QtWidgets.QComboBox()
        self.queue_filter.addItem("All scenarios", None)
        blocks: dict[str, str] = {}
        for trial in self._trials:
            blocks.setdefault(trial.scenario.block_id, trial.scenario.block_title)
        for block_id, block_title in blocks.items():
            self.queue_filter.addItem(block_title, block_id)
        self.queue_filter.currentIndexChanged.connect(self._refresh_queue)
        layout.addWidget(self.queue_filter)
        hint = QtWidgets.QLabel("double-click a trial to inspect it")
        hint.setStyleSheet("color: palette(mid); font-size: 10px;")
        layout.addWidget(hint)
        self.trial_list = QtWidgets.QListWidget()
        self.trial_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        self.trial_list.setUniformItemSizes(True)
        self.trial_list.setTextElideMode(self.QtCore.Qt.TextElideMode.ElideRight)
        self.trial_list.setHorizontalScrollBarPolicy(
            self.QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.trial_list.itemDoubleClicked.connect(self._open_item_detail)
        layout.addWidget(self.trial_list, 1)
        return frame

    def _build_command_card(self) -> Any:
        QtWidgets = self.QtWidgets
        frame, layout = self._card("Collection control")
        self.buttons: dict[OperatorCommand, Any] = {}
        specs = (
            (OperatorCommand.START_TRIAL, "Start trial"),
            (OperatorCommand.CONFIRM_ACTION, "Confirm action"),
            (OperatorCommand.ABORT, "Abort"),
            (OperatorCommand.ACCEPT, "Accept"),
            (OperatorCommand.RETRY, "Retry"),
            (OperatorCommand.SKIP, "Skip"),
            (OperatorCommand.END_SESSION, "End session"),
        )
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(6)
        for index, (command, text) in enumerate(specs):
            button = QtWidgets.QPushButton(text)
            button.setMinimumHeight(30)
            button.clicked.connect(
                lambda _checked=False, c=command: self._on_command(c)
            )
            self.buttons[command] = button
            grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(grid)
        return frame

    # -- view updates --------------------------------------------------

    def apply(
        self,
        snapshot: SessionSnapshot,
        *,
        health_text: str,
        metrics_text: str,
        metrics_tooltip: str,
        radio_detail: str,
    ) -> None:
        """Render one controller snapshot into the operator widgets."""

        self.state_label.setText(snapshot.state.value.upper())
        if self._rendered_state is not snapshot.state:
            self._rendered_state = snapshot.state
            self.state_label.setStyleSheet(_state_badge_style(snapshot.state))
        self.progress_label.setText(snapshot.progress_text)
        self.health_label.setText(health_text)

        trial = snapshot.trial
        if trial is None:
            self.scenario_title.setText("Protocol complete")
            self.scenario_meta.setText("—")
            self.instruction_label.setText("All selected trials are resolved.")
            self.phase_label.setText("—")
        else:
            self.scenario_title.setText(trial.scenario.title)
            self.scenario_meta.setText(
                f"{trial.scenario.activity_label}  ·  repetition {trial.repetition}"
                f"  ·  attempt {snapshot.attempt_number or '—'}"
                f"  ·  {trial.ordinal}/{snapshot.total_trials}"
            )
            self.instruction_label.setText(trial.scenario.instruction)
            remaining = snapshot.phase_remaining_seconds
            if snapshot.state in (
                SessionState.COUNTDOWN,
                SessionState.ACTION,
                SessionState.RECOVERY,
            ):
                self.phase_label.setText(f"{max(0.0, remaining):.1f}s")
            else:
                self.phase_label.setText("—")
        message = snapshot.message
        if trial is not None and message == trial.scenario.instruction:
            message = ""
        self.message_label.setText(message)
        self._current_ordinal = trial.ordinal if trial is not None else None
        self._resolved_count = snapshot.trial_index
        self.detail_button.setEnabled(self._current_ordinal is not None)

        self._sync_queue(snapshot)

        active_states = (
            SessionState.COUNTDOWN,
            SessionState.ACTION,
            SessionState.RECOVERY,
        )
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
            OperatorCommand.SKIP: snapshot.state
            in (SessionState.READY, SessionState.REVIEW),
            OperatorCommand.END_SESSION: snapshot.state is not SessionState.COMPLETE,
        }
        for command, button in self.buttons.items():
            button.setEnabled(enabled[command])

        self.status_label.setText(radio_detail)
        self.metrics_label.setText(metrics_text)
        self.metrics_label.setToolTip(metrics_tooltip)
        self.status_label.setToolTip(radio_detail)

    def _sync_queue(self, snapshot: SessionSnapshot) -> None:
        ordinal = snapshot.trial.ordinal if snapshot.trial is not None else None
        key = (self.queue_filter.currentData(), ordinal, snapshot.trial_index)
        if key != self._queue_key:
            self._queue_key = key
            self._populate_queue(ordinal, snapshot.trial_index)

    def _refresh_queue(self, _index: int) -> None:
        self._queue_key = None

    def _populate_queue(self, current_ordinal: int | None, resolved: int) -> None:
        QtWidgets = self.QtWidgets
        block_id = self.queue_filter.currentData()
        self.trial_list.clear()
        current_row = -1
        for trial in self._trials:
            if block_id is not None and trial.scenario.block_id != block_id:
                continue
            if current_ordinal is not None and trial.ordinal == current_ordinal:
                marker = "▶"
                current_row = self.trial_list.count()
            elif trial.ordinal <= resolved:
                marker = "✓"
            else:
                marker = "·"
            item = QtWidgets.QListWidgetItem(
                f"{marker} {trial.ordinal:03d}  {trial.scenario.title}"
                f"  [{trial.scenario.activity_label} · rep {trial.repetition}]"
            )
            item.setToolTip(trial.scenario.instruction)
            item.setData(self.QtCore.Qt.ItemDataRole.UserRole, trial.ordinal)
            self.trial_list.addItem(item)
        if current_row >= 0:
            self.trial_list.setCurrentRow(current_row)
            item = self.trial_list.item(current_row)
            if item is not None:
                self.trial_list.scrollToItem(
                    item,
                    QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
                )

    # -- scenario detail -----------------------------------------------

    def show_current_details(self) -> None:
        """Open the detail card for the trial currently in progress."""

        if self._current_ordinal is None:
            return
        self._show_detail(self._current_ordinal)

    def _open_item_detail(self, item: Any) -> None:
        ordinal = item.data(self.QtCore.Qt.ItemDataRole.UserRole)
        if ordinal is None:
            return
        self._show_detail(int(ordinal))

    def _detail_status(self, ordinal: int) -> str:
        if self._current_ordinal is not None and ordinal == self._current_ordinal:
            return "current trial"
        if ordinal <= self._resolved_count:
            return "already resolved"
        return "upcoming"

    def _show_detail(self, ordinal: int) -> None:
        trial = self._trial_by_ordinal.get(ordinal)
        if trial is None:
            return
        # Keep a single inspector: the operator reads one scenario at a time,
        # and replacing the window avoids stacking stale cards during a session.
        for existing in self._detail_windows:
            existing.window.close()
            existing.window.deleteLater()
        self._detail_windows.clear()
        dialog = _ScenarioDetailDialog(
            self.QtCore,
            self.QtWidgets,
            trial,
            status=self._detail_status(ordinal),
            total_trials=len(self._trials),
            parent=self.window,
        )
        self._detail_windows.append(dialog)
        dialog.show()


class _PerformerWindow:
    """Full-screen performer guidance shown on the second display."""

    def __init__(
        self, QtCore: Any, QtWidgets: Any, protocol: CollectionProtocol
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle("Performer guidance")
        central = QtWidgets.QWidget()
        self.window.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(48, 48, 48, 48)
        self.state_label = QtWidgets.QLabel("WAITING")
        self.state_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("font-size: 34px; font-weight: bold;")
        self.title_label = QtWidgets.QLabel(protocol.title)
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 24px;")
        self.instruction_label = QtWidgets.QLabel("Wait for the operator")
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setStyleSheet("font-size: 32px;")
        self.timer_label = QtWidgets.QLabel("")
        self.timer_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("font-size: 96px; font-weight: bold;")
        layout.addStretch()
        layout.addWidget(self.state_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self.timer_label)
        layout.addStretch()

    def place(self, screens: Sequence[Any]) -> bool:
        """Place the guidance window and report whether a second display exists."""

        if len(screens) > 1:
            self.window.setGeometry(screens[1].geometry())
            self.window.showFullScreen()
            return True
        self.window.show()
        return False

    def apply(self, snapshot: SessionSnapshot) -> None:
        """Render one controller snapshot into the performer guidance."""

        trial = snapshot.trial
        if trial is None:
            self.state_label.setText("COMPLETE")
            self.instruction_label.setText(snapshot.message)
            self.timer_label.setText("")
        elif snapshot.state is SessionState.COUNTDOWN:
            self.state_label.setText("GET READY")
            self.instruction_label.setText(trial.scenario.instruction)
            self.timer_label.setText(
                str(max(1, int(snapshot.phase_remaining_seconds + 0.999)))
            )
        elif snapshot.state is SessionState.ACTION:
            self.state_label.setText("PERFORM")
            self.instruction_label.setText(trial.scenario.title)
            self.timer_label.setText(
                str(max(1, int(snapshot.phase_remaining_seconds + 0.999)))
            )
        elif snapshot.state is SessionState.RECOVERY:
            self.state_label.setText("RECOVER")
            self.instruction_label.setText("Remain still until the operator continues.")
            self.timer_label.setText(
                str(max(1, int(snapshot.phase_remaining_seconds + 0.999)))
            )
        elif snapshot.state is SessionState.REVIEW:
            self.state_label.setText("WAIT")
            self.instruction_label.setText("The operator is reviewing this attempt.")
            self.timer_label.setText("")
        else:
            self.state_label.setText("WAITING")
            self.instruction_label.setText("Wait for the operator.")
            self.timer_label.setText("")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the collection console."""

    args = _parser().parse_args(argv)
    if bool(args.receiver_config) != bool(args.radio_profile):
        _parser().error(
            "--receiver-config and --radio-profile must be provided together"
        )
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
    gateway_config = None
    if args.transport == "espnow_gateway":
        if not args.port or not args.gateway_port:
            _parser().error("--transport espnow_gateway requires --port and --gateway-port")
        if len(inventory.receivers) != 4:
            _parser().error(
                "ESP-NOW gateway collection requires four real registered receivers; use the viewer/benchmark for development"
            )
        try:
            gateway_config = EspnowTransportConfig.load(args.gateway_config)
        except (OSError, ValueError) as exc:
            _parser().error(str(exc))
    if args.nominal_rate_hz < 1:
        _parser().error("--nominal-rate-hz must be at least 1")
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError as exc:
        print(
            "Install collection dependencies with: uv sync --extra radio",
            file=sys.stderr,
        )
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    try:
        protocol = load_protocol(args.protocol)
    except ProtocolError as exc:
        print(f"Invalid collection protocol: {exc}", file=sys.stderr)
        return 2

    app = QtWidgets.QApplication(list(sys.argv))
    dialog = _MetadataDialog(QtWidgets, protocol)
    metadata = dialog.get()
    if metadata is None:
        return 0
    try:
        protocol = select_blocks(protocol, dialog.block_ids())
    except ProtocolError as exc:
        print(f"Invalid scenario selection: {exc}", file=sys.stderr)
        return 2

    reader_holder: dict[str, Any] = {}

    def telemetry_provider() -> Any:
        reader = reader_holder.get("reader")
        snapshot = getattr(reader, "telemetry_snapshot", None)
        return snapshot() if snapshot is not None else None

    nominal_rate_hz = profile.nominal_rate_hz
    buffer = RollingCsiBuffer(
        nominal_rate=nominal_rate_hz, seconds=10, max_records=10_000
    )
    controller = SessionController(
        protocol,
        args.output_dir,
        environment={
            "transport": args.transport,
            "gateway_transport": asdict(gateway_config) if gateway_config else None,
            "gateway_transport_fingerprint": gateway_config.fingerprint(inventory, profile) if gateway_config else None,
            "port": args.port,
            "gateway_port": args.gateway_port,
            "nominal_rate_hz": nominal_rate_hz,
            "receiver_ids": {device.mac: device.id for device in inventory.receivers},
            "receiver_config": str(args.receiver_config) if profile_mode else None,
            "radio_inventory": inventory.as_dict() if profile_mode else None,
            "radio_profile": profile.as_dict(),
            "radio_profile_fingerprint": profile_fingerprint if profile_mode else None,
        },
        telemetry_provider=telemetry_provider,
        manual_confirmation_required=args.manual_confirmation or profile_mode,
    )

    reader_status: deque[tuple[str, bool]] = deque(maxlen=20)

    def radio_status(message: str, connected: bool) -> None:
        reader_status.appendleft((message, connected))
        if profile_mode:
            controller.record_event(
                "receiver_status",
                message=message,
                connected=connected,
            )

    reader = GatewayReceiverManager(
        inventory,
        profile,
        args.output_dir,
        transmitter_port=args.port,
        gateway_port=args.gateway_port,
        config=gateway_config,
        require_four=True,
        on_status=radio_status,
        record_sink=controller.write_radio,
        journal_root=lambda: controller.session_root,
    )
    reader_holder["reader"] = reader
    receiver_bindings: tuple[Any, ...] = ()
    if profile_mode:
        try:
            receiver_bindings = reader.bind()
        except (RuntimeError, ValueError) as exc:
            print(f"Unable to bind configured ESP-NOW gateway receivers: {exc}", file=sys.stderr)
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

    # The dashboard mirrors the viewer: one live state, one panel, both apps.
    state = LiveState(nominal_rate_hz)
    if profile_mode:
        state.configure_receivers(
            {
                receiver_id: receiver_state.buffer
                for receiver_id, receiver_state in reader.readers.items()
            }
        )
    else:
        state.attach_buffer(buffer)
    panel = CsiDashboardPanel(
        state,
        fps=args.fps,
        window_seconds=COLLECTOR_VIEW_SECONDS,
        receivers=[binding.receiver_id for binding in receiver_bindings] or None,
    )

    def dispatch(command: OperatorCommand) -> None:
        try:
            controller.dispatch(command)
        except (RuntimeError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(
                operator.window, "Collection command unavailable", str(exc)
            )

    profile_text = (
        f"profile {profile.profile_id} · {profile.band} ch {profile.channel}"
        f" · fp {profile_fingerprint}"
        if profile_mode
        else None
    )
    operator = _OperatorWindow(
        QtCore,
        QtWidgets,
        protocol=protocol,
        profile_text=profile_text,
        panel=panel,
        on_command=dispatch,
    )
    performer = _PerformerWindow(QtCore, QtWidgets, protocol)
    if not performer.place(app.screens()):
        reader_status.appendleft(
            ("warning: no second display; performer view is windowed", False)
        )

    def update_view() -> None:
        now = time.monotonic()
        radio_last = getattr(reader, "last_valid_time", None)
        radio_live = radio_last is not None and now - radio_last < 2.5
        if args.transport == "espnow_gateway":
            active = controller.state in (
                SessionState.COUNTDOWN,
                SessionState.ACTION,
                SessionState.RECOVERY,
            )
            radio_live = (
                reader.clock_sync_ready
                if active
                else reader.all_live
                and reader.any_recent_record
                and reader.clock_sync_ready
            )
        radio_detail = (
            reader_status[0][0]
            if reader_status
            else (
                "waiting for ESP-NOW gateway receiver streams"
                if profile_mode
                else "waiting for radio"
            )
        )
        clock_ready = reader.clock_sync_ready
        storage_ready = (
            os.access(args.output_dir.parent, os.W_OK)
            if args.output_dir.parent.exists()
            else True
        )
        controller.update_health(
            HealthSnapshot(
                radio_live=radio_live,
                storage_ready=storage_ready,
                clock_sync_ready=clock_ready,
                radio_detail=radio_detail,
                storage_detail="output directory is not writable"
                if not storage_ready
                else "ready",
            )
        )
        snapshot = controller.tick()
        panel.refresh()
        health_text = (
            f"radio {'ok' if snapshot.health.radio_live else 'offline'}"
            f"  |  sync {'ok' if snapshot.health.clock_sync_ready else 'warming'}"
            f"  |  storage {'ok' if snapshot.health.storage_ready else 'blocked'}"
        )
        metrics_text, metrics_tooltip = _status_metrics(
            reader, nominal_rate_hz, panel.measured_fps
        )
        if args.transport == "espnow_gateway":
            metrics_tooltip += "\n" + reader.diagnostic_text()
            radio_detail = reader.failure or reader.diagnostic_text()
        operator.apply(
            snapshot,
            health_text=health_text,
            metrics_text=metrics_text,
            metrics_tooltip=metrics_tooltip,
            radio_detail=radio_detail,
        )
        performer.apply(snapshot)

    controller.start_session(metadata)
    reader.start()
    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    timer.setInterval(frame_interval_ms(args.fps))
    timer.timeout.connect(update_view)
    timer.start()

    def close() -> None:
        if controller.state is not SessionState.COMPLETE:
            try:
                controller.dispatch(OperatorCommand.END_SESSION)
            except RuntimeError:
                pass
        reader.stop()
        controller.flush_radio()

    app.aboutToQuit.connect(close)
    operator.window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
