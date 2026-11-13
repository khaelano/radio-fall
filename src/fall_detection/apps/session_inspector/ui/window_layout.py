"""Widget construction for the session inspector window."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from ..review import (
    INCLUSION_VALUES,
    QUALITY_VALUES,
)
from .signals_panel import SignalsPanel
from .tables import AttemptTableModel
from .values_panel import ValuesPanel


class LayoutMixin:
    """Builds the inspector window's widget tree and wires its signals.

    Mixin of :class:`SessionInspectorWindow`; it relies on the attributes
    the window initializes in its constructor.
    """

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        sidebar = QtWidgets.QWidget()
        sidebar.setMinimumWidth(270)
        sidebar.setMaximumWidth(390)
        side = QtWidgets.QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        heading = QtWidgets.QLabel("COLLECTION SESSIONS")
        heading.setStyleSheet("font-size: 12px; font-weight: 700;")
        side.addWidget(heading)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search session, participant, operator…")
        side.addWidget(self.search)
        self.status_filter = QtWidgets.QComboBox()
        self.status_filter.addItems(
            ("All statuses", "complete", "ended", "active", "other")
        )
        side.addWidget(self.status_filter)
        self.session_list = QtWidgets.QListWidget()
        self.session_list.setAlternatingRowColors(True)
        side.addWidget(self.session_list, 1)
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        side.addWidget(self.refresh_button)
        splitter.addWidget(sidebar)

        content = QtWidgets.QWidget()
        body = QtWidgets.QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        header = QtWidgets.QHBoxLayout()
        self.session_title = QtWidgets.QLabel("Select a session")
        self.session_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        header.addWidget(self.session_title, 1)
        self.read_only_badge = QtWidgets.QLabel("")
        self.read_only_badge.setStyleSheet(
            "background: #b45309; color: white; border-radius: 5px; padding: 4px 9px;"
        )
        self.read_only_badge.hide()
        header.addWidget(self.read_only_badge)
        self.discard_button = QtWidgets.QPushButton("Discard")
        self.save_button = QtWidgets.QPushButton("Save review")
        self.export_button = QtWidgets.QPushButton("Export curated bundle…")
        header.addWidget(self.discard_button)
        header.addWidget(self.save_button)
        header.addWidget(self.export_button)
        body.addLayout(header)

        vertical = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        body.addWidget(vertical, 1)
        self.attempt_model = AttemptTableModel(self)
        self.attempt_table = QtWidgets.QTableView()
        self.attempt_table.setModel(self.attempt_model)
        self.attempt_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.attempt_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.attempt_table.setAlternatingRowColors(True)
        self.attempt_table.setSortingEnabled(False)
        self.attempt_table.verticalHeader().setVisible(False)
        self.attempt_table.verticalHeader().setDefaultSectionSize(24)
        header = self.attempt_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column, width in {
            0: 52,
            1: 62,
            3: 95,
            4: 44,
            5: 86,
            6: 120,
            7: 86,
            8: 90,
        }.items():
            self.attempt_table.setColumnWidth(column, width)
        self.attempt_table.setMinimumHeight(230)
        vertical.addWidget(self.attempt_table)

        self.detail_tabs = QtWidgets.QTabWidget()
        self.general_tab = self._build_general_tab()
        self.attempt_tab = self._build_attempt_tab()
        self.signals_tab = SignalsPanel()
        self.values_tab = ValuesPanel()
        self.detail_tabs.addTab(self.general_tab, "General")
        self.detail_tabs.addTab(self.attempt_tab, "Attempt review")
        self.detail_tabs.addTab(self.signals_tab, "Signals")
        self.detail_tabs.addTab(self.values_tab, "Values")
        self.detail_tabs.currentChanged.connect(self._detail_tab_changed)
        vertical.addWidget(self.detail_tabs)
        vertical.setSizes((330, 530))
        splitter.addWidget(content)
        splitter.setSizes((310, 1170))

        self.statusBar().showMessage("Ready")
        self.search.textChanged.connect(self._populate_session_list)
        self.status_filter.currentTextChanged.connect(self._populate_session_list)
        self.refresh_button.clicked.connect(self.refresh_sessions)
        self.session_list.currentItemChanged.connect(self._session_item_changed)
        self.attempt_table.selectionModel().currentRowChanged.connect(
            self._attempt_row_changed
        )
        self.save_button.clicked.connect(self.save_review)
        self.discard_button.clicked.connect(self.discard_review)
        self.export_button.clicked.connect(self.export_session)

    def _build_general_tab(self) -> Any:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        form_widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(form_widget)
        self.metadata_widgets: dict[str, Any] = {}
        for field_name, title in (
            ("participant_id", "Participant ID"),
            ("operator", "Operator"),
            ("location", "Location"),
        ):
            editor = QtWidgets.QLineEdit()
            editor.textEdited.connect(self._metadata_changed)
            self.metadata_widgets[field_name] = editor
            form.addRow(title, editor)
        notes = QtWidgets.QPlainTextEdit()
        notes.setMaximumHeight(130)
        notes.textChanged.connect(self._metadata_changed)
        self.metadata_widgets["notes"] = notes
        form.addRow("Notes", notes)
        self.general_summary = QtWidgets.QLabel("No session selected")
        self.general_summary.setWordWrap(True)
        self.general_summary.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow("Session", self.general_summary)
        layout.addWidget(form_widget, 1)
        self.environment_text = QtWidgets.QPlainTextEdit()
        self.environment_text.setReadOnly(True)
        self.environment_text.setPlaceholderText("Acquisition environment and protocol")
        layout.addWidget(self.environment_text, 1)
        return widget

    def _build_attempt_tab(self) -> Any:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        left = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(left)
        self.attempt_summary = QtWidgets.QLabel("Select a recorded attempt")
        self.attempt_summary.setWordWrap(True)
        self.attempt_summary.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form.addRow("Recorded attempt", self.attempt_summary)
        self.receiver_combo = QtWidgets.QComboBox()
        self.receiver_combo.currentTextChanged.connect(self._receiver_changed)
        form.addRow("Receiver", self.receiver_combo)
        self.label_combo = QtWidgets.QComboBox()
        self.label_combo.setEditable(True)
        self.label_combo.currentTextChanged.connect(self._attempt_review_changed)
        form.addRow("Activity label", self.label_combo)
        self.inclusion_combo = QtWidgets.QComboBox()
        self.inclusion_combo.addItems(INCLUSION_VALUES)
        self.inclusion_combo.currentTextChanged.connect(self._attempt_review_changed)
        form.addRow("Inclusion", self.inclusion_combo)
        self.quality_combo = QtWidgets.QComboBox()
        self.quality_combo.addItems(QUALITY_VALUES)
        self.quality_combo.currentTextChanged.connect(self._attempt_review_changed)
        form.addRow("Quality", self.quality_combo)
        self.attempt_notes = QtWidgets.QPlainTextEdit()
        self.attempt_notes.setMaximumHeight(120)
        self.attempt_notes.textChanged.connect(self._attempt_review_changed)
        form.addRow("Review notes", self.attempt_notes)
        layout.addWidget(left, 1)
        self.attempt_metadata = QtWidgets.QPlainTextEdit()
        self.attempt_metadata.setReadOnly(True)
        layout.addWidget(self.attempt_metadata, 1)
        return widget
