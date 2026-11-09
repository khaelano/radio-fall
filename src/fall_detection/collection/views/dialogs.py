"""Session setup and scenario detail dialogs, independent of acquisition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..capture import SessionMetadata
from ..protocol import CollectionProtocol, ProtocolError, Trial, load_protocol


def choose_protocol(QtWidgets: Any, initial_path: Path) -> CollectionProtocol | None:
    """Choose a valid scenario protocol, or return None when canceled."""

    while True:
        filename, _filter = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Choose scenario file",
            str(initial_path),
            "Scenario protocols (*.json)",
        )
        if not filename:
            return None
        initial_path = Path(filename)
        try:
            return load_protocol(initial_path)
        except ProtocolError as exc:
            QtWidgets.QMessageBox.warning(None, "Invalid scenario file", str(exc))


class MetadataDialog:
    """Session metadata plus the scenario blocks this session will collect."""

    def __init__(self, QtWidgets: Any, protocol: CollectionProtocol, *, continuous: bool = False) -> None:
        self.continuous = continuous
        self.QtWidgets = QtWidgets
        self.protocol = protocol
        self.dialog = QtWidgets.QDialog()
        self.dialog.setWindowTitle("Start collection session")
        form = QtWidgets.QFormLayout(self.dialog)
        protocol_label = QtWidgets.QLabel(protocol.title)
        protocol_label.setWordWrap(True)
        form.addRow("Protocol", protocol_label)
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

        scenarios = QtWidgets.QGroupBox("Recording" if continuous else "Scenarios")
        scenario_layout = QtWidgets.QVBoxLayout(scenarios)
        self._blocks: list[tuple[str, Any, int]] = []
        for block_id, block_title, block_scenarios in protocol.blocks:
            trials = sum(scenario.repetitions for scenario in block_scenarios)
            checkbox = QtWidgets.QCheckBox(f"{block_title}  ({trials} trials)")
            if continuous:
                checkbox.hide()
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
        if self.continuous:
            seconds = self.protocol.defaults.action_seconds
            self.total_label.setText(
                f"Non-fall activity · {seconds:g} seconds per segment\n"
                f"Up to {total} segments · stop at any time"
            )
        else:
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
