"""Attempt selection and attempt form handling for the session inspector window."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore

from fall_detection.session import (
    RecordedAttempt,
    RecordedTrial,
)

from ..formatting import _json_text
from ..review import (
    AttemptReview,
)


class AttemptMixin:
    """Shows the selected attempt in the attempt tab and starts its value load.

    Mixin of :class:`SessionInspectorWindow`; it relies on the attributes
    the window initializes in its constructor.
    """

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
