"""Session discovery, selection, and loading for the session inspector window."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from fall_detection.session import (
    SessionBundle,
    SessionReadError,
    scan_sessions,
)

from ..formatting import REVIEW_FILE, _json_text, _review_state
from ..review import (
    LoadedReview,
    ReviewDocument,
    ReviewError,
    ReviewStore,
)


class SessionsMixin:
    """Lists sessions and opens one, resetting review state and general forms.

    Mixin of :class:`SessionInspectorWindow`; it relies on the attributes
    the window initializes in its constructor.
    """

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
