"""Dialogs that bring scenarios into, and protocols out of, the protocol editor.

* :class:`AddScenariosDialog` picks scenarios from any protocol file, such as
  the blocks not selected when the session started.
* :class:`NewScenarioDialog` defines a scenario by hand.
* :class:`SaveProtocolDialog` names a new protocol file for an edited queue.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from fall_detection.protocol.loader import load_protocol
from fall_detection.protocol.model import (
    CollectionProtocol,
    ProtocolError,
    Scenario,
    TimingDefaults,
)
from fall_detection.protocol.revision import custom_scenario

PROTOCOL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ADDED_BLOCK = ("added", "Added scenarios")


def _identity(scenario: Scenario) -> tuple[Any, ...]:
    return (
        scenario.id,
        scenario.activity_label,
        scenario.title,
        scenario.instruction,
        scenario.countdown_seconds,
        scenario.action_seconds,
        scenario.recovery_seconds,
        scenario.block_id,
        scenario.block_title,
        tuple(sorted((k, repr(v)) for k, v in scenario.attributes.items())),
    )


def protocol_files(folder: Path | None) -> list[Path]:
    """Return the protocol JSON files of a folder that load, sorted by name."""
    if folder is None or not folder.is_dir():
        return []
    files = []
    for path in sorted(folder.glob("*.json")):
        try:
            load_protocol(path)
        except (OSError, ProtocolError):
            continue
        files.append(path.resolve())
    return files


class AddScenariosDialog:
    """Choose scenarios of a protocol file to add as trials.

    Args:
        QtCore: The PySide6 core module.
        QtWidgets: The PySide6 widgets module.
        sources: Labelled protocol files offered first.
        protocol_dir: Folder whose protocol files are offered next.
        known: Scenarios already in the session or the edited queue.
        parent: Parent widget.
    """

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        *,
        sources: Sequence[tuple[str, Path]] = (),
        protocol_dir: Path | None = None,
        known: Sequence[Scenario] = (),
        parent: Any = None,
    ) -> None:
        self.QtCore, self.QtWidgets = QtCore, QtWidgets
        self.protocol: CollectionProtocol | None = None
        self._known = {_identity(scenario) for scenario in known}
        self._result: tuple[CollectionProtocol, list[tuple[Scenario, int]]] | None = (
            None
        )
        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setWindowTitle("Add trials from a protocol")
        self.dialog.resize(820, 560)
        layout = QtWidgets.QVBoxLayout(self.dialog)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Protocol"))
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        row.addWidget(self.source_combo, 1)
        browse = QtWidgets.QPushButton("Browse…")
        browse.setAutoDefault(False)
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filter by title, label or id")
        self.filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(("Scenario", "Label", "Trials", ""))
        self.tree.setUniformRowHeights(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        self.tree.itemChanged.connect(lambda *_: self._update_summary())
        layout.addWidget(self.tree, 1)

        count_row = QtWidgets.QHBoxLayout()
        count_row.addWidget(QtWidgets.QLabel("Trials per scenario"))
        self.count = QtWidgets.QSpinBox()
        self.count.setRange(0, 100)
        self.count.setSpecialValueText("as in the protocol")
        self.count.setValue(0)
        self.count.valueChanged.connect(lambda *_: self._update_summary())
        count_row.addWidget(self.count)
        count_row.addStretch()
        layout.addLayout(count_row)
        self.summary = QtWidgets.QLabel()
        self.summary.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.summary)

        box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.add_button = box.addButton(
            "Add trials", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        )
        box.accepted.connect(self._accept)
        box.rejected.connect(self.dialog.reject)
        layout.addWidget(box)

        seen: set[Path] = set()
        for label, path in sources:
            self._add_source(path, label, seen)
        for path in protocol_files(protocol_dir):
            self._add_source(path, None, seen)
        self.source_combo.currentIndexChanged.connect(self._load_current)
        self._load_current()

    # -- sources -------------------------------------------------------

    def _add_source(self, path: Path, label: str | None, seen: set[Path]) -> int:
        path = Path(path).resolve()
        if path in seen:
            return self.source_combo.findData(str(path))
        try:
            protocol = load_protocol(path)
        except (OSError, ProtocolError):
            return -1
        seen.add(path)
        text = f"{protocol.title}  ·  {len(protocol.trials)} trials  ·  {path.name}"
        self.source_combo.addItem(f"{label}: {text}" if label else text, str(path))
        return self.source_combo.count() - 1

    def _browse(self) -> None:
        current = self.source_combo.currentData()
        filename, _filter = self.QtWidgets.QFileDialog.getOpenFileName(
            self.dialog,
            "Choose a protocol",
            str(Path(current).parent) if current else "",
            "Scenario protocols (*.json)",
        )
        if not filename:
            return
        try:
            load_protocol(Path(filename))
        except ProtocolError as exc:
            self.QtWidgets.QMessageBox.warning(
                self.dialog, "Invalid scenario file", str(exc)
            )
            return
        seen = {
            Path(self.source_combo.itemData(i))
            for i in range(self.source_combo.count())
        }
        index = self._add_source(Path(filename), None, seen)
        self.source_combo.setCurrentIndex(index)

    def _load_current(self, *_args: Any) -> None:
        QtCore = self.QtCore
        flag = QtCore.Qt.ItemFlag
        blocked = self.tree.blockSignals(True)
        self.tree.clear()
        self.protocol = None
        path = self.source_combo.currentData()
        if path:
            try:
                self.protocol = load_protocol(Path(path))
            except (OSError, ProtocolError):
                self.protocol = None
        if self.protocol is not None:
            for _block_id, title, scenarios in self.protocol.blocks:
                block = self.QtWidgets.QTreeWidgetItem([title, "", "", ""])
                block.setFlags(
                    block.flags() | flag.ItemIsUserCheckable | flag.ItemIsAutoTristate
                )
                block.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                for scenario in scenarios:
                    note = (
                        "already in session"
                        if _identity(scenario) in self._known
                        else ""
                    )
                    item = self.QtWidgets.QTreeWidgetItem(
                        [
                            scenario.title,
                            scenario.activity_label,
                            str(scenario.repetitions),
                            note,
                        ]
                    )
                    item.setFlags(item.flags() | flag.ItemIsUserCheckable)
                    item.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                    item.setToolTip(0, f"{scenario.id}\n{scenario.instruction}")
                    item.setData(0, QtCore.Qt.ItemDataRole.UserRole, scenario.id)
                    block.addChild(item)
                self.tree.addTopLevelItem(block)
            self.tree.expandAll()
        self.tree.blockSignals(blocked)
        self._apply_filter(self.filter.text())
        self._update_summary()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for index in range(self.tree.topLevelItemCount()):
            block = self.tree.topLevelItem(index)
            shown = 0
            for child_index in range(block.childCount()):
                child = block.child(child_index)
                haystack = " ".join(
                    (
                        child.text(0),
                        child.text(1),
                        str(child.data(0, self.QtCore.Qt.ItemDataRole.UserRole)),
                    )
                ).lower()
                visible = not needle or needle in haystack
                child.setHidden(not visible)
                shown += visible
            block.setHidden(shown == 0)

    # -- result --------------------------------------------------------

    def chosen(self) -> list[tuple[Scenario, int]]:
        """Return the checked scenarios and how many trials each adds."""
        if self.protocol is None:
            return []
        by_id = {
            scenario.id: scenario
            for _id, _title, group in self.protocol.blocks
            for scenario in group
        }
        result = []
        for index in range(self.tree.topLevelItemCount()):
            block = self.tree.topLevelItem(index)
            for child_index in range(block.childCount()):
                child = block.child(child_index)
                if child.checkState(0) == self.QtCore.Qt.CheckState.Checked:
                    scenario = by_id[
                        child.data(0, self.QtCore.Qt.ItemDataRole.UserRole)
                    ]
                    result.append(
                        (scenario, self.count.value() or scenario.repetitions)
                    )
        return result

    def _update_summary(self) -> None:
        chosen = self.chosen()
        trials = sum(count for _scenario, count in chosen)
        self.summary.setText(
            f"{len(chosen)} scenario(s) selected · adds {trials} trial(s) after the "
            "selected trials, or at the end"
        )
        self.add_button.setEnabled(bool(chosen))

    def _accept(self) -> None:
        if self.protocol is not None and self.chosen():
            self._result = (self.protocol, self.chosen())
            self.dialog.accept()

    def get(self) -> tuple[CollectionProtocol, list[tuple[Scenario, int]]] | None:
        """Show the dialog; return the source protocol and chosen scenarios."""
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return self._result


class NewScenarioDialog:
    """Define a scenario that no protocol file contains.

    Args:
        QtWidgets: The PySide6 widgets module.
        known: Scenarios already in the session or the edited queue.
        defaults: The session protocol's timing defaults.
        parent: Parent widget.
    """

    def __init__(
        self,
        QtWidgets: Any,
        *,
        known: Sequence[Scenario],
        defaults: TimingDefaults,
        parent: Any = None,
    ) -> None:
        self.QtWidgets = QtWidgets
        self.known = list(known)
        self._result: tuple[Scenario, int] | None = None
        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setWindowTitle("New scenario")
        self.dialog.setMinimumWidth(480)
        form = QtWidgets.QFormLayout(self.dialog)
        self.title = QtWidgets.QLineEdit()
        self.title.setPlaceholderText("e.g. Kneel to fall (front)")
        self.label = QtWidgets.QComboBox()
        self.label.setEditable(True)
        self.label.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.label.addItems(sorted({s.activity_label for s in self.known}))
        self.label.setCurrentText("")
        self.instruction = QtWidgets.QLineEdit()
        self.block = QtWidgets.QComboBox()
        blocks: dict[str, str] = {}
        for scenario in self.known:
            blocks.setdefault(scenario.block_id, scenario.block_title)
        block_id, block_title = ADDED_BLOCK
        suffix = 2
        while block_id in blocks and blocks[block_id] != block_title:
            block_id = f"{ADDED_BLOCK[0]}_{suffix}"
            suffix += 1
        if block_id not in blocks:
            self.block.addItem(f"New block: {block_title}", (block_id, block_title))
        for existing_id, existing_title in blocks.items():
            self.block.addItem(existing_title, (existing_id, existing_title))
        self.timings = {}
        for name, value in (
            ("countdown_seconds", defaults.countdown_seconds),
            ("action_seconds", defaults.action_seconds),
            ("recovery_seconds", defaults.recovery_seconds),
        ):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(0, 3600)
            spin.setDecimals(1)
            spin.setSuffix(" s")
            spin.setValue(value)
            self.timings[name] = spin
        self.count = QtWidgets.QSpinBox()
        self.count.setRange(1, 100)
        self.count.setValue(1)
        form.addRow("Title *", self.title)
        form.addRow("Label *", self.label)
        form.addRow("Instruction *", self.instruction)
        form.addRow("Block", self.block)
        form.addRow("Countdown", self.timings["countdown_seconds"])
        form.addRow("Action", self.timings["action_seconds"])
        form.addRow("Recovery", self.timings["recovery_seconds"])
        form.addRow("Trials to add", self.count)
        box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        box.addButton("Add trials", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.dialog.reject)
        form.addRow(box)

    def build(self) -> tuple[Scenario, int]:
        """Return the scenario and trial count as entered.

        Raises:
            ProtocolError: A field is missing or invalid.
        """
        block_id, block_title = self.block.currentData()
        scenario = custom_scenario(
            self.known,
            title=self.title.text(),
            activity_label=self.label.currentText(),
            instruction=self.instruction.text(),
            countdown_seconds=self.timings["countdown_seconds"].value(),
            action_seconds=self.timings["action_seconds"].value(),
            recovery_seconds=self.timings["recovery_seconds"].value(),
            block_id=block_id,
            block_title=block_title,
        )
        return scenario, self.count.value()

    def _accept(self) -> None:
        try:
            self._result = self.build()
        except ProtocolError as exc:
            self.QtWidgets.QMessageBox.warning(
                self.dialog, "Scenario incomplete", str(exc)
            )
            return
        self.dialog.accept()

    def get(self) -> tuple[Scenario, int] | None:
        """Show the dialog; return the new scenario and its trial count."""
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return self._result


class SaveProtocolDialog:
    """Name and place a new protocol file for an edited queue.

    Args:
        QtWidgets: The PySide6 widgets module.
        protocol: The session's protocol, whose id the new file may not reuse.
        folder: Folder suggested for the file.
        trials: Number of trials the file will contain.
        parent: Parent widget.
    """

    def __init__(
        self,
        QtWidgets: Any,
        protocol: CollectionProtocol,
        *,
        folder: Path,
        trials: int,
        parent: Any = None,
    ) -> None:
        self.QtWidgets = QtWidgets
        self.protocol = protocol
        self._result: tuple[str, str, Path] | None = None
        self._path_edited = False
        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setWindowTitle("Save queue as a protocol file")
        self.dialog.setMinimumWidth(560)
        form = QtWidgets.QFormLayout(self.dialog)
        intro = QtWidgets.QLabel(
            f"Writes all {trials} trials, in the order shown, as a new protocol "
            "for later sessions. The session itself is not changed."
        )
        intro.setWordWrap(True)
        form.addRow(intro)
        self.title = QtWidgets.QLineEdit(f"{protocol.title} (edited)")
        self.protocol_id = QtWidgets.QLineEdit(f"{protocol.protocol_id}-edited")
        self.protocol_id.setToolTip(
            "A new id keeps sessions recorded with this file distinguishable"
        )
        path_row = QtWidgets.QHBoxLayout()
        self.path = QtWidgets.QLineEdit(str(folder / f"{self.protocol_id.text()}.json"))
        browse = QtWidgets.QPushButton("Browse…")
        browse.setAutoDefault(False)
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)
        form.addRow("Title", self.title)
        form.addRow("Protocol id", self.protocol_id)
        form.addRow("File", path_row)
        self.protocol_id.textEdited.connect(self._follow_id)
        self.path.textEdited.connect(lambda _text: setattr(self, "_path_edited", True))
        box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        box.addButton("Save file", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.dialog.reject)
        form.addRow(box)

    def _follow_id(self, text: str) -> None:
        if not self._path_edited and text.strip():
            self.path.setText(
                str(Path(self.path.text()).parent / f"{text.strip()}.json")
            )

    def _browse(self) -> None:
        filename, _filter = self.QtWidgets.QFileDialog.getSaveFileName(
            self.dialog,
            "Save protocol as",
            self.path.text(),
            "Scenario protocols (*.json)",
        )
        if filename:
            self.path.setText(filename)
            self._path_edited = True

    def values(self) -> tuple[str, str, Path]:
        """Return the title, protocol id and file path as entered.

        Raises:
            ProtocolError: A value is missing or invalid.
        """
        title = self.title.text().strip()
        protocol_id = self.protocol_id.text().strip()
        path = Path(self.path.text().strip()).expanduser()
        if not title:
            raise ProtocolError("enter a title")
        if not PROTOCOL_ID.fullmatch(protocol_id):
            raise ProtocolError(
                "the protocol id may contain letters, digits, '.', '_' and '-'"
            )
        if protocol_id == self.protocol.protocol_id:
            raise ProtocolError(
                "use a new protocol id, so sessions recorded with the new file "
                "stay distinguishable"
            )
        if path.suffix != ".json" or not path.name:
            raise ProtocolError("the file name must end in .json")
        if not path.parent.is_dir():
            raise ProtocolError(f"folder {path.parent} does not exist")
        return title, protocol_id, path

    def _accept(self) -> None:
        QtWidgets = self.QtWidgets
        try:
            values = self.values()
        except ProtocolError as exc:
            QtWidgets.QMessageBox.warning(self.dialog, "Cannot save yet", str(exc))
            return
        if values[2].exists():
            answer = QtWidgets.QMessageBox.question(
                self.dialog,
                "Replace file",
                f"{values[2]} exists. Replace it?",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self._result = values
        self.dialog.accept()

    def get(self) -> tuple[str, str, Path] | None:
        """Show the dialog; return the title, protocol id and path."""
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return self._result
