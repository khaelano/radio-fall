"""Operator controls and protocol queue rendered from session snapshots."""

from __future__ import annotations

from typing import Any

from ...radio.visualization.dashboard import CsiDashboardPanel
from ..controller import OperatorCommand, SessionSnapshot, SessionState
from ..protocol import CollectionProtocol
from .camera import CameraPreview
from .dialogs import ScenarioDetailDialog
from .theme import STYLESHEET, state_badge_style


class OperatorWindow:
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
        video_enabled: bool = False,
        continuous: bool = False,
    ) -> None:
        self._continuous = continuous
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.panel = panel
        self._on_command = on_command
        self._trials = protocol.trials
        self._trial_by_ordinal = {trial.ordinal: trial for trial in protocol.trials}
        self._detail_windows: list[ScenarioDetailDialog] = []
        self._current_ordinal: int | None = None
        self._resolved_count = 0
        self._queue_key: tuple[Any, int | None] | None = None
        self._rendered_state: SessionState | None = None

        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle(f"Collection operator — {protocol.title}")
        self.window.setStyleSheet(STYLESHEET)
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
        self.camera_preview = None
        if video_enabled:
            self.camera_preview = CameraPreview(QtCore, QtWidgets)
            splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            splitter.addWidget(panel.widget)
            splitter.addWidget(self.camera_preview.widget)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 1)
            splitter.setSizes([480, 240])
            root.addWidget(splitter, 1)
        else:
            root.addWidget(panel.widget, 1)

        side.addWidget(self._build_session_card(profile_text))
        side.addWidget(self._build_scenario_card())
        queue_card = self._build_queue_card()
        side.addWidget(queue_card, 1)
        if self._continuous:
            queue_card.hide()
        side.addWidget(self._build_command_card())

        self.status_label = QtWidgets.QLabel("waiting for receivers")
        self.status_label.setMaximumWidth(420)
        self.status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.metrics_label = QtWidgets.QLabel("Delivered records/s: waiting")
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
        self.state_label.setStyleSheet(state_badge_style(SessionState.SETUP))
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
        frame, layout = self._card("Recording" if self._continuous else "Scenario")
        self.scenario_title = QtWidgets.QLabel("Protocol complete")
        self.scenario_title.setObjectName("scenarioTitle")
        self.scenario_title.setWordWrap(True)
        self.scenario_meta = QtWidgets.QLabel("—")
        self.scenario_meta.setStyleSheet("color: palette(mid); font-size: 11px;")
        self.setup_label = QtWidgets.QLabel("")
        self.setup_label.setWordWrap(True)
        self.setup_label.hide()
        meta_row = QtWidgets.QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.addWidget(self.scenario_meta, 1)
        self.detail_button = QtWidgets.QPushButton("Details")
        self.detail_button.setFlat(True)
        self.detail_button.setToolTip("Open the full detail card for this scenario")
        self.detail_button.setCursor(self.QtCore.Qt.CursorShape.PointingHandCursor)
        self.detail_button.clicked.connect(self.show_current_details)
        self.detail_button.setEnabled(False)
        if self._continuous:
            self.detail_button.hide()
        meta_row.addWidget(self.detail_button)
        self.instruction_label = QtWidgets.QLabel("Waiting to record" if self._continuous else "Waiting for the first trial")
        self.instruction_label.setObjectName("instruction")
        self.instruction_label.setWordWrap(True)
        self.message_label = QtWidgets.QLabel("")
        self.message_label.setObjectName("message")
        self.message_label.setWordWrap(True)
        self.phase_label = QtWidgets.QLabel("—")
        self.phase_label.setObjectName("phase")
        layout.addWidget(self.scenario_title)
        layout.addLayout(meta_row)
        layout.addWidget(self.setup_label)
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
            if self._continuous and command is not OperatorCommand.END_SESSION:
                button.hide()
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
            self.state_label.setStyleSheet(state_badge_style(snapshot.state))
        self.progress_label.setText(snapshot.progress_text)
        self.health_label.setText(health_text)

        trial = snapshot.trial
        if trial is None:
            self.scenario_title.setText("Protocol complete")
            self.scenario_meta.setText("—")
            self.instruction_label.setText("All segments are recorded." if self._continuous else "All selected trials are resolved.")
            self.phase_label.setText("—")
            self.setup_label.hide()
        else:
            self.scenario_title.setText(trial.scenario.title)
            self.scenario_meta.setText(
                (f"{trial.scenario.activity_label}  ·  segment {trial.ordinal}" if self._continuous
                 else f"{trial.scenario.activity_label}  ·  repetition {trial.repetition}")
                + f"  ·  attempt {snapshot.attempt_number or '—'}"
                + f"  ·  {trial.ordinal}/{snapshot.total_trials}"
            )
            self.instruction_label.setText(trial.scenario.instruction)
            attributes = trial.scenario.attributes
            equipment = attributes.get("equipment")
            self.setup_label.setVisible(equipment is not None)
            if equipment is not None:
                setup = "clear floor" if equipment == "none" else equipment.replace("_", " ")
                if attributes.get("chair_direction"):
                    setup += f" · chair facing {attributes['chair_direction']}"
                self.setup_label.setText(f"Setup: {setup}")
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
            and snapshot.health.ready,
            OperatorCommand.CONFIRM_ACTION: snapshot.state is SessionState.ACTION
            and not snapshot.action_confirmed,
            OperatorCommand.ABORT: snapshot.state in active_states,
            OperatorCommand.ACCEPT: snapshot.state is SessionState.REVIEW
            and snapshot.attempt_status != "invalid" and not snapshot.accept_pending,
            OperatorCommand.RETRY: snapshot.state is SessionState.REVIEW,
            OperatorCommand.SKIP: snapshot.state
            in (SessionState.READY, SessionState.REVIEW),
            OperatorCommand.END_SESSION: snapshot.state is not SessionState.COMPLETE,
        }
        for command, button in self.buttons.items():
            button.setEnabled(enabled[command] and (not self._continuous or command is OperatorCommand.END_SESSION))

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
        dialog = ScenarioDetailDialog(
            self.QtCore,
            self.QtWidgets,
            trial,
            status=self._detail_status(ordinal),
            total_trials=len(self._trials),
            parent=self.window,
        )
        self._detail_windows.append(dialog)
        dialog.show()
