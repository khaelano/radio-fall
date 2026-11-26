"""Session setup and scenario detail dialogs, independent of acquisition."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.continuous import continuous_protocol
from fall_detection.collection.video import VideoConfig
from fall_detection.protocol.loader import load_protocol, select_blocks
from fall_detection.protocol.model import CollectionProtocol, ProtocolError, Trial

from ..plan import SessionPlan


def choose_protocol(
    QtWidgets: Any, initial_path: Path, parent: Any = None
) -> tuple[Path, CollectionProtocol] | None:
    """Choose a valid scenario protocol file, or return None when canceled."""

    while True:
        filename, _filter = QtWidgets.QFileDialog.getOpenFileName(
            parent,
            "Choose scenario file",
            str(initial_path),
            "Scenario protocols (*.json)",
        )
        if not filename:
            return None
        initial_path = Path(filename)
        try:
            return initial_path, load_protocol(initial_path)
        except ProtocolError as exc:
            QtWidgets.QMessageBox.warning(parent, "Invalid scenario file", str(exc))


def camera_devices(root: Path = Path("/dev")) -> tuple[str, ...]:
    """List V4L2 device nodes; not every node is a capture device."""
    return tuple(
        str(path)
        for path in sorted(root.glob("video*"), key=lambda p: (len(p.name), p.name))
    )


class NewSessionDialog:
    """One form for a new session: recording mode, protocol, people, camera.

    Args:
        QtWidgets: The PySide6 widgets module.
        protocol_path: Protocol selected first; other ``*.json`` protocols in
            its folder are offered beside it.
        output_dir: Directory that receives the new session.
        continuous: Select continuous activity recording first.
        segment_seconds: Initial continuous segment length.
        segments: Initial maximum number of continuous segments.
        video_device: Camera selected first, or None for CSI only.
        video_size: Requested camera width, height and frame rate.
        radio_text: Read-only description of the radio profile and gateway.
        cameras: Camera device nodes to offer; discovered when omitted.
        parent: Parent widget.
    """

    def __init__(
        self,
        QtWidgets: Any,
        *,
        protocol_path: Path,
        output_dir: Path,
        continuous: bool = False,
        segment_seconds: float = 300,
        segments: int = 288,
        video_device: str | None = None,
        video_size: tuple[int, int, int] = (1280, 720, 30),
        radio_text: str = "",
        cameras: Sequence[str] | None = None,
        parent: Any = None,
    ) -> None:
        self.QtWidgets = QtWidgets
        self.output_dir = output_dir
        self.video_size = video_size
        self.protocol: CollectionProtocol | None = None
        self._protocols: dict[str, CollectionProtocol] = {}
        self._blocks: list[tuple[str, Any, int]] = []
        self._plan: SessionPlan | None = None
        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setWindowTitle("New collection session")
        self.dialog.setMinimumWidth(520)
        outer = QtWidgets.QVBoxLayout(self.dialog)

        recording = QtWidgets.QGroupBox("Recording")
        form = QtWidgets.QFormLayout(recording)
        mode_row = QtWidgets.QHBoxLayout()
        self.scripted_radio = QtWidgets.QRadioButton("Guided trials from a protocol")
        self.continuous_radio = QtWidgets.QRadioButton("Continuous activity segments")
        self.continuous_radio.setToolTip(
            "Record non-fall activity automatically in fixed-length segments"
        )
        mode_row.addWidget(self.scripted_radio)
        mode_row.addWidget(self.continuous_radio)
        mode_row.addStretch()
        form.addRow("Mode", mode_row)
        protocol_row = QtWidgets.QHBoxLayout()
        self.protocol_combo = QtWidgets.QComboBox()
        self.protocol_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.browse_button = QtWidgets.QPushButton("Browse…")
        protocol_row.addWidget(self.protocol_combo, 1)
        protocol_row.addWidget(self.browse_button)
        form.addRow("Protocol", protocol_row)
        segment_row = QtWidgets.QHBoxLayout()
        self.segment_seconds = QtWidgets.QDoubleSpinBox()
        self.segment_seconds.setRange(1, 3600)
        self.segment_seconds.setDecimals(0)
        self.segment_seconds.setSuffix(" s each")
        self.segment_seconds.setValue(segment_seconds)
        self.segment_count = QtWidgets.QSpinBox()
        self.segment_count.setRange(1, 10000)
        self.segment_count.setPrefix("up to ")
        self.segment_count.setSuffix(" segments")
        self.segment_count.setValue(segments)
        segment_row.addWidget(self.segment_seconds)
        segment_row.addWidget(self.segment_count)
        segment_row.addStretch()
        self.segment_label = QtWidgets.QLabel("Segments")
        form.addRow(self.segment_label, segment_row)
        destination = QtWidgets.QLabel(str(output_dir))
        destination.setStyleSheet("color: palette(mid);")
        form.addRow("Saved to", destination)
        outer.addWidget(recording)

        people = QtWidgets.QGroupBox("Session details")
        people_form = QtWidgets.QFormLayout(people)
        self.participant = QtWidgets.QLineEdit()
        self.participant.setPlaceholderText("pseudonymous participant ID")
        self.operator = QtWidgets.QLineEdit()
        self.location = QtWidgets.QLineEdit()
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setMaximumHeight(70)
        people_form.addRow("Participant ID *", self.participant)
        people_form.addRow("Operator", self.operator)
        people_form.addRow("Location", self.location)
        people_form.addRow("Notes", self.notes)
        outer.addWidget(people)

        self.scenarios = QtWidgets.QGroupBox("Scenarios")
        self.scenario_layout = QtWidgets.QVBoxLayout(self.scenarios)
        self.block_area = QtWidgets.QWidget()
        self.block_layout = QtWidgets.QVBoxLayout(self.block_area)
        self.block_layout.setContentsMargins(0, 0, 0, 0)
        self.scenario_layout.addWidget(self.block_area)
        self.total_label = QtWidgets.QLabel("")
        self.total_label.setStyleSheet("font-weight: 600;")
        self.scenario_layout.addWidget(self.total_label)
        outer.addWidget(self.scenarios)

        hardware = QtWidgets.QGroupBox("Hardware")
        hardware_form = QtWidgets.QFormLayout(hardware)
        self.camera_combo = QtWidgets.QComboBox()
        self.camera_combo.addItem("None (CSI only)", None)
        listed = list(camera_devices() if cameras is None else cameras)
        if video_device and video_device not in listed:
            listed.insert(0, video_device)
        for device in listed:
            self.camera_combo.addItem(device, device)
        if video_device:
            self.camera_combo.setCurrentIndex(self.camera_combo.findData(video_device))
        width, height, fps = video_size
        self.camera_combo.setToolTip(
            f"DroidCam USB virtual webcam; recorded at {width}×{height}, {fps} fps"
        )
        hardware_form.addRow("Camera", self.camera_combo)
        if radio_text:
            radio = QtWidgets.QLabel(radio_text)
            radio.setWordWrap(True)
            radio.setStyleSheet("color: palette(mid);")
            hardware_form.addRow("Radio", radio)
        outer.addWidget(hardware)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.start_button = buttons.addButton(
            "Start recording", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.start_button.setDefault(True)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.dialog.reject)
        outer.addWidget(buttons)

        protocol_path = protocol_path.resolve()
        candidates = sorted({protocol_path, *protocol_path.parent.glob("*.json")})
        for path in candidates:
            try:
                protocol = load_protocol(path)
            except (OSError, ProtocolError):
                continue
            self._add_protocol(path, protocol)
        index = self.protocol_combo.findData(str(protocol_path))
        self.protocol_combo.setCurrentIndex(max(0, index))
        self.protocol_combo.currentIndexChanged.connect(self._protocol_changed)
        self.browse_button.clicked.connect(self._browse)
        self.scripted_radio.toggled.connect(self._mode_changed)
        self.segment_seconds.valueChanged.connect(self._update_total)
        self.segment_count.valueChanged.connect(self._update_total)
        (self.continuous_radio if continuous else self.scripted_radio).setChecked(True)
        self._protocol_changed()
        self._mode_changed()

    # -- protocol and mode ---------------------------------------------

    def _add_protocol(self, path: Path, protocol: CollectionProtocol) -> None:
        self._protocols[str(path)] = protocol
        trials = len(protocol.trials)
        self.protocol_combo.addItem(
            f"{protocol.title}  ·  {trials} trials  ·  {path.name}", str(path)
        )

    def _browse(self) -> None:
        current = self.protocol_combo.currentData()
        chosen = choose_protocol(
            self.QtWidgets,
            Path(current) if current else Path(),
            self.dialog,
        )
        if chosen is None:
            return
        path, protocol = chosen
        path = path.resolve()
        index = self.protocol_combo.findData(str(path))
        if index < 0:
            self._add_protocol(path, protocol)
            index = self.protocol_combo.count() - 1
        self.protocol_combo.setCurrentIndex(index)

    def _protocol_changed(self, *_args: Any) -> None:
        path = self.protocol_combo.currentData()
        self.protocol = None
        while self.block_layout.count():
            item = self.block_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._blocks = []
        if path:
            self.protocol = self._protocols.get(path)
        if self.protocol is not None:
            for block_id, block_title, block_scenarios in self.protocol.blocks:
                trials = sum(scenario.repetitions for scenario in block_scenarios)
                checkbox = self.QtWidgets.QCheckBox(f"{block_title}  ({trials} trials)")
                checkbox.setChecked(True)
                checkbox.toggled.connect(self._update_total)
                self.block_layout.addWidget(checkbox)
                self._blocks.append((block_id, checkbox, trials))
        self._update_total()

    def _mode_changed(self, *_args: Any) -> None:
        continuous = self.continuous
        self.protocol_combo.setEnabled(not continuous)
        self.browse_button.setEnabled(not continuous)
        for widget in (self.segment_label, self.segment_seconds, self.segment_count):
            widget.setVisible(continuous)
        self.block_area.setVisible(not continuous)
        self.scenarios.setTitle("Recording plan" if continuous else "Scenarios")
        self.camera_combo.setEnabled(not continuous)
        if continuous:
            self.camera_combo.setCurrentIndex(0)
            self.camera_combo.setToolTip("Continuous mode currently records CSI only")
        self._update_total()

    @property
    def continuous(self) -> bool:
        """Whether continuous activity recording is selected."""
        return self.continuous_radio.isChecked()

    def _selected_trials(self) -> int:
        return sum(trials for _id, box, trials in self._blocks if box.isChecked())

    def _update_total(self, *_args: Any) -> None:
        if self.continuous:
            seconds = self.segment_seconds.value()
            count = self.segment_count.value()
            self.total_label.setText(
                f"Non-fall activity · {seconds:g} seconds per segment\n"
                f"Up to {count} segments · stop at any time"
            )
        else:
            total = self._selected_trials()
            noun = "trial" if total == 1 else "trials"
            self.total_label.setText(f"this session collects {total} {noun}")

    # -- result --------------------------------------------------------

    def block_ids(self) -> tuple[str, ...]:
        """Return the selected scenario block identifiers in protocol order."""

        return tuple(
            block_id
            for block_id, checkbox, _trials in self._blocks
            if checkbox.isChecked()
        )

    def metadata(self) -> SessionMetadata:
        """Return the session details as entered."""
        return SessionMetadata(
            participant_id=self.participant.text().strip(),
            operator=self.operator.text().strip(),
            location=self.location.text().strip(),
            notes=self.notes.toPlainText().strip(),
        )

    def plan(self) -> SessionPlan:
        """Build the session plan from the current form.

        Raises:
            ValueError: The form is incomplete or names an invalid setting;
                the message is written for the operator.
        """
        metadata = self.metadata()
        if not metadata.participant_id:
            raise ValueError("Enter a pseudonymous participant ID.")
        if self.continuous:
            try:
                protocol = continuous_protocol(
                    self.segment_seconds.value(), self.segment_count.value()
                )
            except ProtocolError as exc:
                raise ValueError(str(exc)) from exc
            video = None
        else:
            if self.protocol is None:
                raise ValueError("Choose a valid scenario protocol.")
            if not self.block_ids():
                raise ValueError("Select at least one scenario block to collect.")
            try:
                protocol = select_blocks(self.protocol, self.block_ids())
            except ProtocolError as exc:
                raise ValueError(str(exc)) from exc
            device = self.camera_combo.currentData()
            width, height, fps = self.video_size
            video = VideoConfig(device, width, height, fps) if device else None
        path = None if self.continuous else self.protocol_combo.currentData()
        return SessionPlan(
            protocol=protocol,
            metadata=metadata,
            output_dir=self.output_dir,
            continuous=self.continuous,
            video=video,
            protocol_path=Path(path) if path else None,
        )

    def _accept(self) -> None:
        try:
            self._plan = self.plan()
        except ValueError as exc:
            self.QtWidgets.QMessageBox.warning(
                self.dialog, "Session cannot start yet", str(exc)
            )
            return
        self.dialog.accept()

    def get(self) -> SessionPlan | None:
        """Show the dialog; return the plan, or None when canceled."""
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return self._plan


class ScenarioDetailDialog:
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
        self.setup_label = None
        if attributes.get("equipment") is not None:
            setup = str(attributes["equipment"]).replace("_", " ")
            if attributes.get("chair_direction"):
                setup += f" · chair facing {attributes['chair_direction']}"
            self.setup_label = self._section(layout, "Equipment setup", setup)
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
