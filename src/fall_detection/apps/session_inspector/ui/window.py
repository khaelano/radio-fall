"""Main window of the offline session inspector."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from threading import Event
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from fall_detection.session import (
    RecordedAttempt,
    RecordedTrial,
    SessionBundle,
    SessionReadError,
    SessionSource,
    scan_sessions,
)

from ..data import (
    AttemptData,
)
from ..exporter import ExportCancelled, export_curated_bundle, session_size
from ..formatting import REVIEW_FILE, _human_size, _json_text, _review_state
from ..review import (
    INCLUSION_VALUES,
    METADATA_FIELDS,
    QUALITY_VALUES,
    AttemptReview,
    LoadedReview,
    ReviewConflictError,
    ReviewDocument,
    ReviewError,
    ReviewStore,
)
from .signals_panel import SignalsPanel
from .tables import AttemptTableModel
from .values_panel import ValuesPanel
from .workers import AttemptLoadWorker, SignalPrepareWorker


class SessionInspectorWindow(QtWidgets.QMainWindow):
    """Main offline session browser and review editor."""

    def __init__(self, source_path: Path, annotations_dir: Path | None = None) -> None:
        super().__init__()
        self.source_path = source_path
        self.annotations_dir = annotations_dir
        self.sessions: tuple[SessionBundle, ...] = ()
        self.session: SessionBundle | None = None
        self.store: ReviewStore | None = None
        self.loaded_review: LoadedReview | None = None
        self.review: ReviewDocument | None = None
        self.review_writable = False
        self.baseline_state: dict[str, Any] | None = None
        self.current_attempt: RecordedAttempt | None = None
        self.current_trial: RecordedTrial | None = None
        self._loading_forms = False
        self._load_token = 0
        self._load_cancel: Event | None = None
        self._pending_receiver = ""
        self._current_data: AttemptData | None = None
        self._preparing_key: tuple[str, str, str] | None = None
        self._data_cache: OrderedDict[tuple[str, str, str], AttemptData] = OrderedDict()
        self._cache_limit = 4
        self._load_timer = QtCore.QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(140)
        self._load_timer.timeout.connect(self._dispatch_attempt_load)
        self.thread_pool = QtCore.QThreadPool(self)
        self.thread_pool.setMaxThreadCount(2)
        # Python's frame-to-record decoding is CPU-bound and can starve the
        # GUI event loop even from a QThread. A spawned process pool keeps
        # the interpreter work isolated without forking Qt state.
        self.process_pool = ProcessPoolExecutor(
            max_workers=2,
            mp_context=get_context("spawn"),
        )
        self._process_pool_closed = False

        self.setWindowTitle("Collection session inspector")
        self.resize(1480, 900)
        self._build_ui()
        self.refresh_sessions()

    # -- UI construction -----------------------------------------

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

    # -- session discovery and selection -------------------------

    @QtCore.Slot()
    def refresh_sessions(self) -> None:
        if self.is_dirty() and not self._confirm_leave():
            return
        try:
            self.sessions = scan_sessions(self.source_path)
        except SessionReadError as exc:
            QtWidgets.QMessageBox.critical(self, "Unable to read sessions", str(exc))
            self.sessions = ()
        self._populate_session_list()
        self.statusBar().showMessage(f"Found {len(self.sessions)} session(s)", 5000)

    @QtCore.Slot()
    def _populate_session_list(self, *_args: Any) -> None:
        selected_path = self.session.path if self.session is not None else None
        search = self.search.text().strip().lower()
        status_filter = self.status_filter.currentText()
        blocker = QtCore.QSignalBlocker(self.session_list)
        self.session_list.clear()
        selected_item = None
        for session in self.sessions:
            searchable = " ".join(
                str(session.manifest.get(key, ""))
                for key in ("session_id", "participant_id", "operator", "location")
            ).lower()
            if search and search not in searchable:
                continue
            normalized = "active" if session.active else session.status.lower()
            if status_filter != "All statuses":
                if status_filter == "other":
                    if normalized in {"complete", "ended", "active"}:
                        continue
                elif normalized != status_filter:
                    continue
            participant = str(session.manifest.get("participant_id") or "—")
            text = (
                f"{session.session_id}\n"
                f"{participant} · {session.status} · {len(session.attempts)} attempts"
            )
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, session.path.as_posix())
            if session.active:
                item.setForeground(QtGui.QColor("#b45309"))
            self.session_list.addItem(item)
            if selected_path == session.path:
                selected_item = item
        del blocker
        if selected_item is not None:
            self.session_list.setCurrentItem(selected_item)
        elif self.session is None and self.session_list.count():
            self.session_list.setCurrentRow(0)

    @QtCore.Slot()
    def _session_item_changed(self, current: Any, previous: Any) -> None:
        if current is None:
            return
        if self.is_dirty() and not self._confirm_leave():
            blocker = QtCore.QSignalBlocker(self.session_list)
            self.session_list.setCurrentItem(previous)
            del blocker
            return
        path_text = current.data(QtCore.Qt.ItemDataRole.UserRole)
        session = next(
            (item for item in self.sessions if item.path.as_posix() == path_text),
            None,
        )
        if session is not None:
            self._open_session(session)

    def _resolve_receivers(self, session: SessionBundle) -> SessionBundle:
        """Fill in the session's receivers, converting its journals if needed."""
        if session.receivers_resolved:
            return session

        def progress(message: str) -> None:
            self.statusBar().showMessage(message)
            self.statusBar().repaint()

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            resolved = session.with_receivers(progress)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.sessions = tuple(
            resolved if item.path == resolved.path else item for item in self.sessions
        )
        return resolved

    def _open_session(self, session: SessionBundle) -> None:
        self._cancel_load()
        session = self._resolve_receivers(session)
        self._data_cache.clear()
        self.session = session
        self.store = ReviewStore(
            session,
            None
            if self.annotations_dir is None
            else self.annotations_dir / session.session_id / REVIEW_FILE,
        )
        review_error = None
        try:
            self.loaded_review = self.store.load()
            self.review = self.loaded_review.document.clone()
        except ReviewError as exc:
            review_error = str(exc)
            self.loaded_review = LoadedReview(ReviewDocument.empty(session), None)
            self.review = self.loaded_review.document.clone()
        self.baseline_state = _review_state(self.review)
        self.current_attempt = None
        self.current_trial = None
        self.session_title.setText(
            f"{session.session_id} — "
            f"{session.manifest.get('participant_id') or 'unnamed participant'}"
        )
        read_only = session.active or review_error is not None
        self.review_writable = not read_only
        if read_only:
            self.read_only_badge.setText(
                "ACTIVE — READ ONLY" if session.active else "INVALID REVIEW — READ ONLY"
            )
            self.read_only_badge.show()
        else:
            self.read_only_badge.hide()
        self._load_general_form()
        self._set_editable(not read_only)
        self.attempt_model.set_session(session, self.review)
        self._clear_attempt()
        warnings = list(session.warnings)
        if review_error:
            warnings.append(review_error)
        self.statusBar().showMessage(
            " · ".join(warnings)
            if warnings
            else f"Loaded {len(session.attempts)} attempts"
        )
        if self.attempt_model.rowCount():
            self.attempt_table.selectRow(0)

    def _load_general_form(self) -> None:
        if self.session is None or self.review is None:
            return
        self._loading_forms = True
        for field_name, editor in self.metadata_widgets.items():
            value = self.review.metadata.get(
                field_name, str(self.session.manifest.get(field_name) or "")
            )
            if isinstance(editor, QtWidgets.QPlainTextEdit):
                editor.setPlainText(value)
            else:
                editor.setText(value)
        manifest = self.session.manifest
        self.general_summary.setText(
            f"Status: {self.session.status}\n"
            f"Started: {manifest.get('started_at_utc') or '—'}\n"
            f"Protocol: {manifest.get('protocol_id') or '—'}\n"
            f"Hash: {self.session.protocol_hash or '—'}\n"
            f"Planned trials: {len(self.session.trials)}\n"
            f"Recorded attempts: {len(self.session.attempts)}"
        )
        self.environment_text.setPlainText(
            _json_text(
                {
                    "environment": manifest.get("environment", {}),
                    "protocol_identity": {
                        "protocol_id": manifest.get("protocol_id"),
                        "protocol_hash": self.session.protocol_hash,
                        "title": (
                            self.session.protocol.title
                            if self.session.protocol
                            else None
                        ),
                    },
                    "protocol_snapshot": self.session.protocol_source,
                }
            )
        )
        self._loading_forms = False

    def _set_editable(self, editable: bool) -> None:
        for editor in self.metadata_widgets.values():
            editor.setEnabled(editable)
        for editor in (
            self.label_combo,
            self.inclusion_combo,
            self.quality_combo,
            self.attempt_notes,
        ):
            editor.setEnabled(editable and self.current_attempt is not None)
        self.save_button.setEnabled(editable)
        self.discard_button.setEnabled(editable)
        self.export_button.setEnabled(self.session is not None and self.review_writable)

    # -- editing --------------------------------------------------

    @QtCore.Slot()
    def _metadata_changed(self, *_args: Any) -> None:
        if self._loading_forms or self.session is None or self.review is None:
            return
        for field_name in METADATA_FIELDS:
            editor = self.metadata_widgets[field_name]
            value = (
                editor.toPlainText()
                if isinstance(editor, QtWidgets.QPlainTextEdit)
                else editor.text()
            )
            original = str(self.session.manifest.get(field_name) or "")
            if value == original:
                self.review.metadata.pop(field_name, None)
            else:
                self.review.metadata[field_name] = value
        self._update_dirty_status()

    @QtCore.Slot()
    def _attempt_row_changed(self, current: Any, _previous: Any) -> None:
        trial = self.attempt_model.trial_at(current.row())
        attempt = self.attempt_model.attempt_at(current.row())
        self.current_trial = trial
        self.current_attempt = attempt
        if attempt is None:
            self._clear_attempt("This planned protocol trial has no recorded attempts.")
            return
        self._load_attempt_form(trial, attempt)

    def _load_attempt_form(
        self, trial: RecordedTrial | None, attempt: RecordedAttempt
    ) -> None:
        if self.review is None or self.session is None:
            return
        self._cancel_load()
        self._loading_forms = True
        current = self.review.attempts.get(attempt.key, AttemptReview())
        self.attempt_summary.setText(
            f"Trial {attempt.trial_ordinal}, attempt {attempt.attempt_number}\n"
            f"{trial.title if trial else attempt.scenario_id}\n"
            f"Acquisition status: {attempt.status}\n"
            f"{trial.instruction if trial else ''}"
        )
        blocker = QtCore.QSignalBlocker(self.receiver_combo)
        self.receiver_combo.clear()
        self.receiver_combo.addItems(attempt.receiver_ids)
        del blocker
        label_blocker = QtCore.QSignalBlocker(self.label_combo)
        self.label_combo.clear()
        self.label_combo.addItems(self.session.labels)
        effective_label = current.activity_label or attempt.activity_label
        if effective_label and self.label_combo.findText(effective_label) < 0:
            self.label_combo.addItem(effective_label)
        self.label_combo.setCurrentText(effective_label)
        del label_blocker
        inclusion_blocker = QtCore.QSignalBlocker(self.inclusion_combo)
        quality_blocker = QtCore.QSignalBlocker(self.quality_combo)
        notes_blocker = QtCore.QSignalBlocker(self.attempt_notes)
        self.inclusion_combo.setCurrentText(current.inclusion)
        self.quality_combo.setCurrentText(current.quality)
        self.attempt_notes.setPlainText(current.notes)
        del inclusion_blocker, quality_blocker, notes_blocker
        self.attempt_metadata.setPlainText(
            _json_text(
                {
                    "protocol_trial": {
                        "scenario_id": trial.scenario_id
                        if trial
                        else attempt.scenario_id,
                        "title": trial.title if trial else "",
                        "instruction": trial.instruction if trial else "",
                        "block": trial.block_title if trial else "",
                        "attributes": trial.attributes if trial else {},
                    },
                    "attempt": attempt.metadata,
                    "receivers": list(attempt.receiver_ids),
                    "frame_tables": attempt.frames_path.as_posix(),
                }
            )
        )
        editable = self.review_writable
        for editor in (
            self.label_combo,
            self.inclusion_combo,
            self.quality_combo,
            self.attempt_notes,
        ):
            editor.setEnabled(editable)
        self._loading_forms = False
        self.signals_tab.video.set_attempt(attempt)
        if self.receiver_combo.count():
            self._schedule_attempt_load(self.receiver_combo.currentText())
        else:
            self.signals_tab.clear("No receiver frames found")
            self.values_tab.clear("No receiver frames found")

    def _clear_attempt(self, message: str = "Select a recorded attempt") -> None:
        self._cancel_load()
        self._pending_receiver = ""
        self._current_data = None
        self.current_attempt = None
        self._loading_forms = True
        self.attempt_summary.setText(message)
        self.receiver_combo.clear()
        self.label_combo.clear()
        self.inclusion_combo.setCurrentText("unreviewed")
        self.quality_combo.setCurrentText("unreviewed")
        self.attempt_notes.clear()
        self.attempt_metadata.clear()
        self._loading_forms = False
        for editor in (
            self.label_combo,
            self.inclusion_combo,
            self.quality_combo,
            self.attempt_notes,
        ):
            editor.setEnabled(False)
        self.signals_tab.clear(message)
        self.signals_tab.video.set_attempt(None)
        self.values_tab.clear(message)

    @QtCore.Slot()
    def _attempt_review_changed(self, *_args: Any) -> None:
        if (
            self._loading_forms
            or self.review is None
            or self.current_attempt is None
            or self.session is None
            or not self.session.editable
        ):
            return
        label = self.label_combo.currentText().strip()
        review = AttemptReview(
            activity_label=(
                None if label == self.current_attempt.activity_label else label
            ),
            inclusion=self.inclusion_combo.currentText(),
            quality=self.quality_combo.currentText(),
            notes=self.attempt_notes.toPlainText(),
        )
        is_empty = (
            review.activity_label is None
            and review.inclusion == "unreviewed"
            and review.quality == "unreviewed"
            and not review.notes
        )
        if is_empty:
            self.review.attempts.pop(self.current_attempt.key, None)
        else:
            self.review.attempts[self.current_attempt.key] = review
        self.attempt_model.refresh(self.current_attempt.key)
        self._update_dirty_status()

    def is_dirty(self) -> bool:
        return (
            self.review is not None
            and self.baseline_state is not None
            and _review_state(self.review) != self.baseline_state
        )

    def _update_dirty_status(self) -> None:
        marker = " *" if self.is_dirty() else ""
        if self.session is not None:
            self.setWindowTitle(
                f"Collection session inspector — {self.session.session_id}{marker}"
            )

    def _confirm_leave(self) -> bool:
        result = QtWidgets.QMessageBox.question(
            self,
            "Unsaved review",
            "Save review changes before leaving this session?",
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Save,
        )
        if result == QtWidgets.QMessageBox.StandardButton.Cancel:
            return False
        if result == QtWidgets.QMessageBox.StandardButton.Save:
            return self.save_review()
        return True

    @QtCore.Slot()
    def save_review(self) -> bool:
        if self.store is None or self.review is None or self.loaded_review is None:
            return False
        try:
            saved = self.store.save(self.review, self.loaded_review.token)
        except ReviewConflictError as exc:
            QtWidgets.QMessageBox.warning(self, "Review changed elsewhere", str(exc))
            return False
        except ReviewError as exc:
            QtWidgets.QMessageBox.warning(self, "Unable to save review", str(exc))
            return False
        self.loaded_review = saved
        self.review = saved.document.clone()
        self.baseline_state = _review_state(self.review)
        self.attempt_model.review = self.review
        self.attempt_model.refresh()
        self._update_dirty_status()
        self.statusBar().showMessage(
            f"Saved review revision {self.review.revision}", 5000
        )
        return True

    @QtCore.Slot()
    def discard_review(self) -> None:
        if self.store is None or self.session is None:
            return
        try:
            self.loaded_review = self.store.load()
        except ReviewError as exc:
            QtWidgets.QMessageBox.warning(self, "Unable to reload review", str(exc))
            return
        self.review = self.loaded_review.document.clone()
        self.baseline_state = _review_state(self.review)
        self.attempt_model.set_session(self.session, self.review)
        self._load_general_form()
        self._clear_attempt()
        self._update_dirty_status()

    # -- asynchronous values and signals -------------------------

    @QtCore.Slot(str)
    def _receiver_changed(self, receiver_id: str) -> None:
        if not self._loading_forms and receiver_id:
            self._schedule_attempt_load(receiver_id)

    def _cancel_load(self) -> None:
        # A completed worker signal may already be queued when cancellation
        # is requested. Advancing the token also makes that queued result
        # stale, preventing an old scenario from replacing the new one.
        self._load_token += 1
        self._load_timer.stop()
        if self._load_cancel is not None:
            self._load_cancel.set()
        self._load_cancel = None
        self._preparing_key = None

    def _cache_key(
        self,
        attempt: RecordedAttempt,
        receiver_id: str,
    ) -> tuple[str, str, str]:
        session_path = self.session.path.as_posix() if self.session else ""
        return session_path, attempt.key, receiver_id

    def _cache_put(
        self,
        key: tuple[str, str, str],
        data: AttemptData,
    ) -> None:
        self._data_cache[key] = data
        self._data_cache.move_to_end(key)
        while len(self._data_cache) > self._cache_limit:
            self._data_cache.popitem(last=False)

    def _schedule_attempt_load(self, receiver_id: str) -> None:
        if self.current_attempt is None or not receiver_id:
            return
        self._cancel_load()
        self._pending_receiver = receiver_id
        self._current_data = None
        if self.detail_tabs.currentWidget() is self.signals_tab:
            self.signals_tab.clear(f"Waiting to load {receiver_id}…")
        if self.detail_tabs.currentWidget() is self.values_tab:
            self.values_tab.clear(f"Waiting to load {receiver_id}…")
        self._load_timer.start()

    @QtCore.Slot()
    def _dispatch_attempt_load(self) -> None:
        if self.current_attempt is None or not self._pending_receiver:
            return
        receiver_id = self._pending_receiver
        key = self._cache_key(self.current_attempt, receiver_id)
        cached = self._data_cache.get(key)
        if cached is not None:
            self._data_cache.move_to_end(key)
            self._current_data = cached
            self._apply_visible_data()
            return
        token = self._load_token
        cancellation = Event()
        self._load_cancel = cancellation
        if self.detail_tabs.currentWidget() is self.signals_tab:
            self.signals_tab.clear(f"Loading {receiver_id}…")
        if self.detail_tabs.currentWidget() is self.values_tab:
            self.values_tab.clear(f"Loading {receiver_id}…")
        worker = AttemptLoadWorker(
            token,
            self.current_attempt,
            receiver_id,
            cancellation,
            self.process_pool,
            prepare_signals=(self.detail_tabs.currentWidget() is self.signals_tab),
        )
        worker.signals.completed.connect(self._attempt_data_loaded)
        worker.signals.failed.connect(self._attempt_data_failed)
        self.thread_pool.start(worker)

    def _ensure_signals(self) -> None:
        data = self._current_data
        if data is None or data.prepared_frame is not None:
            if data is not None:
                self.signals_tab.set_data(data)
            return
        key = (
            self.session.path.as_posix() if self.session else "",
            data.attempt_key,
            data.receiver_id,
        )
        if self._preparing_key == key:
            return
        if self._load_cancel is not None:
            self._load_cancel.set()
        cancellation = Event()
        self._load_cancel = cancellation
        self._preparing_key = key
        self.signals_tab.clear("Preparing downsampled signal plots…")
        worker = SignalPrepareWorker(
            self._load_token,
            self.current_attempt,
            data.receiver_id,
            cancellation,
            self.process_pool,
        )
        worker.signals.completed.connect(self._attempt_data_loaded)
        worker.signals.failed.connect(self._attempt_data_failed)
        self.thread_pool.start(worker, -1)

    def _apply_visible_data(self) -> None:
        data = self._current_data
        if data is None:
            return
        current_tab = self.detail_tabs.currentWidget()
        if current_tab is self.values_tab:
            current = self.values_tab.data
            if (
                current is None
                or current.attempt_key != data.attempt_key
                or current.receiver_id != data.receiver_id
            ):
                self.values_tab.set_data(data)
        elif current_tab is self.signals_tab:
            if data.prepared_frame is None:
                self._ensure_signals()
            elif self.signals_tab.data is not data:
                self.signals_tab.set_data(data)

    @QtCore.Slot(int)
    def _detail_tab_changed(self, _index: int) -> None:
        self._apply_visible_data()

    @QtCore.Slot(int, object)
    def _attempt_data_loaded(self, token: int, data: AttemptData) -> None:
        if token != self._load_token:
            return
        self._load_cancel = None
        self._preparing_key = None
        key = (
            self.session.path.as_posix() if self.session else "",
            data.attempt_key,
            data.receiver_id,
        )
        self._cache_put(key, data)
        self._current_data = data
        self._apply_visible_data()
        self.statusBar().showMessage(
            f"Loaded {data.record_count} CSI records for {data.receiver_id}", 5000
        )

    @QtCore.Slot(int, str)
    def _attempt_data_failed(self, token: int, message: str) -> None:
        if token != self._load_token:
            return
        self._load_cancel = None
        self._preparing_key = None
        self.signals_tab.clear("Unable to load signal")
        self.values_tab.clear(message)
        self.statusBar().showMessage(message)

    # -- curated export ------------------------------------------

    @QtCore.Slot()
    def export_session(self) -> None:
        if self.session is None or self.review is None:
            return
        if self.is_dirty() and not self.save_review():
            return
        parent_text = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose export parent directory", str(self.session.path.parent)
        )
        if not parent_text:
            return
        default_name = f"{SessionSource(self.session.path).name}-curated"
        name, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Curated bundle name",
            "New directory name:",
            text=default_name,
        )
        if not accepted or not name.strip():
            return
        if Path(name).name != name or name in {".", ".."}:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid name",
                "Enter one new directory name without separators.",
            )
            return
        destination = Path(parent_text) / name
        if destination.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Destination exists",
                f"The destination already exists:\n{destination}",
            )
            return
        total = session_size(self.session)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Export curated bundle",
            f"Copy {_human_size(total)} to:\n{destination}\n\n"
            "All attempts, including excluded attempts, will be retained and flagged.",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        progress_dialog = QtWidgets.QProgressDialog(
            "Preparing export…", "Cancel", 0, 1000, self
        )
        progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)

        def update(copied: int, expected: int, relative: str) -> None:
            value = 1000 if expected == 0 else min(1000, int(copied * 1000 / expected))
            progress_dialog.setValue(value)
            progress_dialog.setLabelText(
                f"Copying {relative}\n{_human_size(copied)} / {_human_size(expected)}"
            )
            QtWidgets.QApplication.processEvents()

        try:
            export_curated_bundle(
                self.session,
                self.review,
                destination,
                progress=update,
                cancelled=progress_dialog.wasCanceled,
            )
        except ExportCancelled:
            self.statusBar().showMessage("Export cancelled", 5000)
            return
        except Exception as exc:  # noqa: BLE001 — application error boundary
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))
            return
        finally:
            progress_dialog.close()
        QtWidgets.QMessageBox.information(
            self, "Export complete", f"Curated bundle created at:\n{destination}"
        )

    def closeEvent(self, event: Any) -> None:
        if self.is_dirty() and not self._confirm_leave():
            event.ignore()
            return
        self._cancel_load()
        self.signals_tab.shutdown()
        if not self._process_pool_closed:
            self.process_pool.shutdown(wait=False, cancel_futures=True)
            self._process_pool_closed = True
        event.accept()
