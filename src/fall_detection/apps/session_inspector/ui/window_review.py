"""Review editing, dirty tracking, and saving for the session inspector window."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from ..formatting import _review_state
from ..review import (
    METADATA_FIELDS,
    AttemptReview,
    ReviewConflictError,
    ReviewError,
)


class ReviewMixin:
    """Applies form edits to the review document and saves or discards it.

    Mixin of :class:`SessionInspectorWindow`; it relies on the attributes
    the window initializes in its constructor.
    """

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
