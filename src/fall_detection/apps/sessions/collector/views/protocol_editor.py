"""Editor for the remaining trial queue of a session that is recording.

The operator reorders, removes and duplicates upcoming trials, adds trials of
scenarios from any protocol file or defined by hand, and changes their label,
title, instruction and phase timing. Trials that are recorded or in progress
are shown greyed out and cannot be selected. The dialog builds a revised
protocol, which the controller saves in the session, and can also write the
edited queue to a new protocol file for later sessions.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fall_detection.protocol.loader import load_protocol
from fall_detection.protocol.model import CollectionProtocol, ProtocolError, Scenario
from fall_detection.protocol.revision import (
    DraftTrial,
    adopt_scenario,
    describe_changes,
    draft_queue,
    protocol_scenarios,
    revise_protocol,
    standalone_protocol,
    validate_change,
)

from .protocol_sources import AddScenariosDialog, NewScenarioDialog, SaveProtocolDialog

COLUMNS = ("#", "Scenario", "Label", "Block", "Countdown / action / recovery", "")
FIELDS = (
    ("activity_label", "Label"),
    ("title", "Title"),
    ("instruction", "Instruction"),
    ("countdown_seconds", "Countdown (s)"),
    ("action_seconds", "Action (s)"),
    ("recovery_seconds", "Recovery (s)"),
)
MIXED = "(several values)"


@dataclass(frozen=True)
class ProtocolEdit:
    """A saved edit: the revised protocol and what to record with it."""

    protocol: CollectionProtocol
    note: str
    changes: list[str]


def _text(value: Any) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


class ProtocolEditorDialog:
    """Modal editor of the trials that have not been recorded yet.

    Args:
        QtCore: The PySide6 core module.
        QtWidgets: The PySide6 widgets module.
        protocol: The protocol the session follows now.
        locked: Number of leading trials that cannot change.
        revision: Number the saved revision will get.
        protocol_dir: Folder whose protocol files are offered as sources of
            scenarios and suggested for saved protocols.
        sources: Labelled protocol files offered first as sources of scenarios,
            e.g. the session's starting protocol.
        session_id: Session recorded in a saved protocol's ``derived_from``.
        parent: Parent widget.
    """

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        protocol: CollectionProtocol,
        *,
        locked: int,
        revision: int,
        protocol_dir: Path | None = None,
        sources: Sequence[tuple[str, Path]] = (),
        session_id: str | None = None,
        parent: Any = None,
    ) -> None:
        self.QtCore, self.QtWidgets = QtCore, QtWidgets
        self.protocol = protocol
        self.locked = locked
        self.revision = revision
        self.protocol_dir = protocol_dir
        self.sources = list(sources)
        self.session_id = session_id
        self.saved_files: list[Path] = []
        self.queue: list[DraftTrial] = draft_queue(protocol)
        self._editing: list[int] = []
        self._dirty: set[str] = set()
        self._result: ProtocolEdit | None = None

        self.dialog = QtWidgets.QDialog(parent)
        self.dialog.setWindowTitle("Edit remaining protocol")
        self.dialog.resize(1040, 680)
        outer = QtWidgets.QVBoxLayout(self.dialog)
        if locked:
            intro = (
                f"Trials 1–{locked} are recorded or in progress and stay as they "
                f"are. Your changes apply from trial {locked + 1}."
            )
        else:
            intro = "No trial has been recorded yet, so every trial can change."
        header = QtWidgets.QLabel(
            intro + " Recorded attempts keep their labels; correct those later "
            "in the session review."
        )
        header.setWordWrap(True)
        outer.addWidget(header)

        middle = QtWidgets.QHBoxLayout()
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4, 5):
            header_view.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        middle.addWidget(self.table, 1)

        side = QtWidgets.QVBoxLayout()
        self.buttons: dict[str, Any] = {}
        for key, text, tip, shortcut in (
            (
                "next",
                "Do next",
                "Move the selection right after the fixed trials",
                None,
            ),
            ("up", "Move up", "Move the selection one place earlier", "Ctrl+Up"),
            ("down", "Move down", "Move the selection one place later", "Ctrl+Down"),
            ("end", "Move to end", "Move the selection to the end of the queue", None),
            ("duplicate", "Duplicate", "Add a copy of each selected trial", "Ctrl+D"),
            ("remove", "Remove", "Remove the selected trials", "Delete"),
            (
                "add_from_protocol",
                "Add from protocol…",
                (
                    "Add trials of scenarios from a protocol file, such as blocks "
                    "not selected when the session started"
                ),
                None,
            ),
            (
                "new_scenario",
                "New scenario…",
                "Define a scenario by hand and add its trials",
                None,
            ),
        ):
            if key == "add_from_protocol":
                rule = QtWidgets.QFrame()
                rule.setFrameShape(QtWidgets.QFrame.Shape.HLine)
                side.addWidget(rule)
            button = QtWidgets.QPushButton(text)
            button.setToolTip(tip + (f" ({shortcut})" if shortcut else ""))
            if shortcut:
                button.setShortcut(shortcut)
            button.setAutoDefault(False)
            button.clicked.connect(getattr(self, f"_{key}"))
            side.addWidget(button)
            self.buttons[key] = button
        side.addStretch()
        middle.addLayout(side)
        outer.addLayout(middle, 1)

        fields = QtWidgets.QGroupBox(
            "Selected trials — edits apply to every selected trial"
        )
        form = QtWidgets.QGridLayout(fields)
        self.editors: dict[str, Any] = {}
        labels = sorted(
            {s.activity_label for _id, _t, group in protocol.blocks for s in group}
        )
        for index, (name, title) in enumerate(FIELDS):
            if name == "activity_label":
                editor = QtWidgets.QComboBox()
                editor.setEditable(True)
                editor.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
                editor.addItems(labels)
                editor.lineEdit().textEdited.connect(
                    lambda _text, n=name: self._dirty.add(n)
                )
                editor.activated.connect(lambda _i, n=name: self._mark_and_commit(n))
                editor.lineEdit().editingFinished.connect(self._commit_fields)
            else:
                editor = QtWidgets.QLineEdit()
                editor.textEdited.connect(lambda _text, n=name: self._dirty.add(n))
                editor.editingFinished.connect(self._commit_fields)
            self.editors[name] = editor
            row, column = (index, 0) if index < 3 else (index - 3, 2)
            form.addWidget(QtWidgets.QLabel(title), row, column)
            form.addWidget(editor, row, column + 1)
        form.setColumnStretch(1, 3)
        form.setColumnStretch(3, 1)
        outer.addWidget(fields)

        self.summary = QtWidgets.QLabel("No changes yet.")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: palette(mid);")
        outer.addWidget(self.summary)
        self.error = QtWidgets.QLabel()
        self.error.setStyleSheet("color: #b91c1c;")
        self.error.hide()
        outer.addWidget(self.error)
        note_row = QtWidgets.QHBoxLayout()
        note_row.addWidget(QtWidgets.QLabel("Reason"))
        self.note = QtWidgets.QLineEdit()
        self.note.setPlaceholderText("why the protocol changed; saved with the session")
        note_row.addWidget(self.note, 1)
        outer.addLayout(note_row)

        box = QtWidgets.QDialogButtonBox()
        self.reset_button = box.addButton(
            "Discard edits", QtWidgets.QDialogButtonBox.ButtonRole.ResetRole
        )
        self.export_button = box.addButton(
            "Save as protocol file…", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
        )
        self.export_button.setToolTip(
            "Write the queue as shown to a new protocol file for later sessions"
        )
        box.addButton(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.save_button = box.addButton(
            "Save revision", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        )
        # Enter in a field applies the field; it must not save the revision.
        for button in box.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        self.reset_button.clicked.connect(self._reset)
        self.export_button.clicked.connect(self._save_as_file)
        box.accepted.connect(self._save)
        box.rejected.connect(self.dialog.reject)
        outer.addWidget(box)

        self.table.itemSelectionChanged.connect(self._selection_changed)
        self._refresh(select=[locked] if locked < len(self.queue) else [])

    # -- table ---------------------------------------------------------

    def _refresh(self, *, select: list[int]) -> None:
        QtCore, QtWidgets = self.QtCore, self.QtWidgets
        blocked = self.table.blockSignals(True)
        self.table.setRowCount(len(self.queue))
        for row, draft in enumerate(self.queue):
            fixed = row < self.locked
            if fixed:
                status = "fixed"
            elif draft.origin is None:
                status = "new"
            elif draft.changes:
                status = "edited"
            else:
                status = ""
            values = (
                str(row + 1),
                draft.value("title"),
                draft.value("activity_label"),
                draft.scenario.block_title,
                " / ".join(
                    _text(float(draft.value(n)))
                    for n in ("countdown_seconds", "action_seconds", "recovery_seconds")
                )
                + " s",
                status,
            )
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if fixed:
                    item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                    item.setForeground(self.dialog.palette().mid())
                    item.setToolTip("Recorded or in progress; cannot change")
                else:
                    item.setToolTip(draft.value("instruction"))
                self.table.setItem(row, column, item)
        self.table.clearSelection()
        rows = [row for row in select if self.locked <= row < len(self.queue)]
        model = self.table.selectionModel()
        flags = QtCore.QItemSelectionModel.SelectionFlag
        if rows:
            self.table.setCurrentCell(rows[0], 0, flags.NoUpdate)
            self.table.scrollToItem(self.table.item(rows[0], 0))
        for row in rows:
            model.select(self.table.model().index(row, 0), flags.Select | flags.Rows)
        self.table.blockSignals(blocked)
        self._update_label_choices()
        self._fill_fields()
        self._update_summary()

    def _update_label_choices(self) -> None:
        editor = self.editors["activity_label"]
        labels = sorted(
            {s.activity_label for s in protocol_scenarios(self.protocol)}
            | {str(draft.value("activity_label")) for draft in self.queue}
        )
        current = [editor.itemText(i) for i in range(editor.count())]
        if current != labels:
            blocked = editor.blockSignals(True)
            text = editor.currentText()
            editor.clear()
            editor.addItems(labels)
            editor.setCurrentText(text)
            editor.blockSignals(blocked)

    def selected_rows(self) -> list[int]:
        """Return the selected editable rows in queue order."""
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        return sorted(row for row in rows if row >= self.locked)

    def _selection_changed(self) -> None:
        self._commit_fields()
        self._fill_fields()

    def _fill_fields(self) -> None:
        self._editing = self.selected_rows()
        self._dirty.clear()
        for name, editor in self.editors.items():
            editor.setEnabled(bool(self._editing))
            values = {self.queue[row].value(name) for row in self._editing}
            text = _text(next(iter(values))) if len(values) == 1 else ""
            placeholder = MIXED if len(values) > 1 else ""
            line = editor.lineEdit() if hasattr(editor, "lineEdit") else editor
            blocked = editor.blockSignals(True)
            line.setText(text)
            line.setPlaceholderText(placeholder)
            editor.blockSignals(blocked)
        for key, button in self.buttons.items():
            button.setEnabled(
                bool(self._editing) or key in {"add_from_protocol", "new_scenario"}
            )

    def _mark_and_commit(self, name: str) -> None:
        self._dirty.add(name)
        self._commit_fields()

    def _commit_fields(self) -> bool:
        """Apply edited fields to the rows they were filled from."""
        if not self._dirty or not self._editing:
            self._dirty.clear()
            return True
        values = {}
        for name in self._dirty:
            editor = self.editors[name]
            line = editor.lineEdit() if hasattr(editor, "lineEdit") else editor
            try:
                values[name] = validate_change(name, line.text())
            except ProtocolError as exc:
                self._show_error(str(exc))
                return False
        self._dirty.clear()
        self._show_error(None)
        for row in self._editing:
            draft = self.queue[row]
            changes = dict(draft.changes)
            for name, value in values.items():
                if value == getattr(draft.scenario, name):
                    changes.pop(name, None)
                else:
                    changes[name] = value
            self.queue[row] = replace(draft, changes=changes)
        # Keep whatever is selected now; a selection change commits first.
        self._refresh(select=self.selected_rows())
        return True

    # -- operations ----------------------------------------------------

    def _rows_for_operation(self) -> list[int]:
        if not self._commit_fields():
            return []
        return self.selected_rows()

    def _up(self) -> None:
        rows = self._rows_for_operation()
        if not rows or rows[0] <= self.locked:
            return
        for row in rows:
            self.queue[row - 1], self.queue[row] = self.queue[row], self.queue[row - 1]
        self._refresh(select=[row - 1 for row in rows])

    def _down(self) -> None:
        rows = self._rows_for_operation()
        if not rows or rows[-1] >= len(self.queue) - 1:
            return
        for row in reversed(rows):
            self.queue[row + 1], self.queue[row] = self.queue[row], self.queue[row + 1]
        self._refresh(select=[row + 1 for row in rows])

    def _split(self, rows: list[int]) -> tuple[list[DraftTrial], list[DraftTrial]]:
        chosen = set(rows)
        moving = [self.queue[row] for row in rows]
        rest = [draft for index, draft in enumerate(self.queue) if index not in chosen]
        return moving, rest

    def _next(self) -> None:
        rows = self._rows_for_operation()
        if not rows:
            return
        moving, rest = self._split(rows)
        self.queue = rest[: self.locked] + moving + rest[self.locked :]
        self._refresh(select=list(range(self.locked, self.locked + len(moving))))

    def _end(self) -> None:
        rows = self._rows_for_operation()
        if not rows:
            return
        moving, rest = self._split(rows)
        self.queue = rest + moving
        start = len(rest)
        self._refresh(select=list(range(start, start + len(moving))))

    def _duplicate(self) -> None:
        rows = self._rows_for_operation()
        if not rows:
            return
        copies = [replace(self.queue[row], origin=None) for row in rows]
        position = rows[-1] + 1
        self.queue[position:position] = copies
        self._refresh(select=list(range(position, position + len(copies))))

    def _remove(self) -> None:
        rows = self._rows_for_operation()
        if not rows:
            return
        chosen = set(rows)
        self.queue = [d for index, d in enumerate(self.queue) if index not in chosen]
        following = min(rows[0], len(self.queue) - 1)
        self._refresh(select=[following] if following >= self.locked else [])

    def known_scenarios(self) -> list[Scenario]:
        """Scenarios of the session protocol and of the edited queue."""
        known = {s.id: s for s in protocol_scenarios(self.protocol)}
        for draft in self.queue:
            known.setdefault(draft.scenario.id, draft.scenario)
        return list(known.values())

    def insert(self, drafts: list[DraftTrial]) -> None:
        """Insert trials after the selection, or at the end without one."""
        rows = self._rows_for_operation()
        position = rows[-1] + 1 if rows else len(self.queue)
        self.queue[position:position] = drafts
        self._refresh(select=list(range(position, position + len(drafts))))

    def add_scenarios(
        self, source: CollectionProtocol, chosen: list[tuple[Scenario, int]]
    ) -> None:
        """Add trials of scenarios taken from another protocol."""
        known = self.known_scenarios()
        drafts = []
        for scenario, count in chosen:
            adopted = adopt_scenario(
                scenario, known, source_protocol_id=source.protocol_id
            )
            if adopted not in known:
                known.append(adopted)
            drafts += [DraftTrial(adopted) for _ in range(count)]
        self.insert(drafts)

    def _add_from_protocol(self) -> None:
        if not self._commit_fields():
            return
        picker = AddScenariosDialog(
            self.QtCore,
            self.QtWidgets,
            sources=[
                *self.sources,
                *(("Saved now", path) for path in self.saved_files),
            ],
            protocol_dir=self.protocol_dir,
            known=self.known_scenarios(),
            parent=self.dialog,
        )
        result = picker.get()
        if result is not None:
            self.add_scenarios(*result)

    def _new_scenario(self) -> None:
        if not self._commit_fields():
            return
        dialog = NewScenarioDialog(
            self.QtWidgets,
            known=self.known_scenarios(),
            defaults=self.protocol.defaults,
            parent=self.dialog,
        )
        result = dialog.get()
        if result is not None:
            scenario, count = result
            self.insert([DraftTrial(scenario) for _ in range(count)])

    def export(self, *, protocol_id: str, title: str, path: Path) -> CollectionProtocol:
        """Write the queue as shown to a new protocol file.

        Args:
            protocol_id: Id of the new protocol; must differ from the session's.
            title: Title of the new protocol.
            path: JSON file to write; replaced if it exists.

        Returns:
            The protocol as read back from the file.

        Raises:
            ProtocolError: The queue or the names are invalid.
            OSError: The file cannot be written.
        """
        if not self._commit_fields():
            raise ProtocolError(self.error.text())
        revised = revise_protocol(
            self.protocol, self.queue, locked=self.locked, revision=self.revision
        )
        derived_from = {
            "protocol_id": self.protocol.protocol_id,
            "protocol_hash": self.protocol.source_hash,
            "saved_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        if self.session_id:
            derived_from["session_id"] = self.session_id
        protocol = standalone_protocol(
            revised, protocol_id=protocol_id, title=title, derived_from=derived_from
        )
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(protocol.source, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        saved = load_protocol(path)
        if path.resolve() not in self.saved_files:
            self.saved_files.append(path.resolve())
        return saved

    def _save_as_file(self) -> None:
        if not self._commit_fields():
            return
        folder = self.protocol_dir or Path.cwd()
        dialog = SaveProtocolDialog(
            self.QtWidgets,
            self.protocol,
            folder=folder,
            trials=len(self.queue),
            parent=self.dialog,
        )
        values = dialog.get()
        if values is None:
            return
        title, protocol_id, path = values
        try:
            saved = self.export(protocol_id=protocol_id, title=title, path=path)
        except (ProtocolError, OSError) as exc:
            self._show_error(f"Protocol file not saved: {exc}")
            return
        self._show_error(None)
        self.summary.setText(
            f"Saved {len(saved.trials)} trials as {saved.protocol_id} to {path}. "
            + self.summary.text()
        )

    def _reset(self) -> None:
        self._dirty.clear()
        self.queue = draft_queue(self.protocol)
        self._show_error(None)
        self._refresh(select=[self.locked] if self.locked < len(self.queue) else [])

    # -- result --------------------------------------------------------

    @property
    def changed(self) -> bool:
        """Whether the queue differs from the protocol."""
        origins = [draft.origin for draft in self.queue]
        return origins != [t.ordinal for t in self.protocol.trials] or any(
            draft.changes for draft in self.queue
        )

    def _update_summary(self) -> None:
        lines = describe_changes(self.protocol, self.queue, locked=self.locked)
        remaining = len(self.queue) - self.locked
        if not lines:
            self.summary.setText(f"No changes yet · {remaining} trial(s) remaining")
        else:
            self.summary.setText(
                f"{remaining} trial(s) remaining after the change · "
                + " · ".join(lines)
            )
        self.save_button.setEnabled(self.changed)

    def _show_error(self, message: str | None) -> None:
        self.error.setText(message or "")
        self.error.setVisible(bool(message))

    def build(self) -> ProtocolEdit | None:
        """Return the edit as it stands, or None when nothing changed.

        Raises:
            ProtocolError: A field value or the edited queue is invalid.
        """
        if not self._commit_fields():
            raise ProtocolError(self.error.text())
        if not self.changed:
            return None
        protocol = revise_protocol(
            self.protocol, self.queue, locked=self.locked, revision=self.revision
        )
        if protocol.source_hash == self.protocol.source_hash:
            return None
        return ProtocolEdit(
            protocol=protocol,
            note=self.note.text().strip(),
            changes=describe_changes(self.protocol, self.queue, locked=self.locked),
        )

    def _save(self) -> None:
        try:
            self._result = self.build()
        except ProtocolError as exc:
            self._show_error(str(exc))
            return
        if self._result is None:
            self.dialog.reject()
            return
        self.dialog.accept()

    def get(self) -> ProtocolEdit | None:
        """Show the editor; return the saved edit, or None when canceled."""
        if self.dialog.exec() != self.QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return self._result
