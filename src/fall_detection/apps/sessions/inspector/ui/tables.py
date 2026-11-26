"""Table models for the session inspector."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui

from fall_detection.session.models import RecordedAttempt, RecordedTrial, SessionBundle

from ..data import (
    TableData,
)
from ..review import (
    ReviewDocument,
)


class TextTableModel(QtCore.QAbstractTableModel):
    """Read-only virtualized model backed by exact textual table values."""

    def __init__(
        self,
        table: TableData | None = None,
        parent: Any = None,
        *,
        page_size: int = 250,
    ) -> None:
        super().__init__(parent)
        self.table = table or TableData(name="")
        self.page_size = max(1, page_size)
        self.page = 0

    def set_table(self, table: TableData) -> None:
        self.beginResetModel()
        self.table = table
        self.page = 0
        self.endResetModel()

    @property
    def page_count(self) -> int:
        return max(1, (len(self.table.rows) + self.page_size - 1) // self.page_size)

    def set_page(self, page: int) -> None:
        page = max(0, min(page, self.page_count - 1))
        if page == self.page:
            return
        self.beginResetModel()
        self.page = page
        self.endResetModel()

    def source_row(self, visible_row: int) -> int:
        return self.page * self.page_size + visible_row

    def rowCount(self, parent: Any = QtCore.QModelIndex()) -> int:  # noqa: B008 — Qt virtual method signature
        if parent.isValid():
            return 0
        remaining = len(self.table.rows) - self.page * self.page_size
        return max(0, min(self.page_size, remaining))

    def columnCount(self, parent: Any = QtCore.QModelIndex()) -> int:  # noqa: B008 — Qt virtual method signature
        return 0 if parent.isValid() else len(self.table.headers)

    def data(self, index: Any, role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        value = self.table.rows[self.source_row(index.row())][index.column()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return value if len(value) <= 240 else value[:237] + "…"
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return value
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return value
        return None

    def headerData(self, section: int, orientation: Any, role: int) -> Any:
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            return self.table.headers[section]
        return str(self.source_row(section) + 1)


class AttemptTableModel(QtCore.QAbstractTableModel):
    """Flat trial/attempt rows with review-derived columns."""

    HEADERS = (
        "Trial",
        "Attempt",
        "Scenario",
        "Trial outcome",
        "Rep",
        "Acquisition",
        "Effective label",
        "Inclusion",
        "Quality",
    )

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.rows: list[tuple[RecordedTrial, RecordedAttempt | None]] = []
        self.review: ReviewDocument | None = None
        self._display_rows: list[tuple[str, ...]] = []
        self._attempt_rows: dict[str, int] = {}
        self._trial_rows: dict[int, list[int]] = {}

    def set_session(
        self, session: SessionBundle | None, review: ReviewDocument | None
    ) -> None:
        self.beginResetModel()
        self.review = review
        self.rows = []
        self._attempt_rows = {}
        self._trial_rows = {}
        if session is not None:
            for trial in session.trials:
                if trial.attempts:
                    self.rows.extend((trial, attempt) for attempt in trial.attempts)
                else:
                    self.rows.append((trial, None))
        for row, (trial, attempt) in enumerate(self.rows):
            self._trial_rows.setdefault(trial.ordinal, []).append(row)
            if attempt is not None:
                self._attempt_rows[attempt.key] = row
        self._display_rows = [
            self._display_values(trial, attempt) for trial, attempt in self.rows
        ]
        self.endResetModel()

    def refresh(self, attempt_key: str | None = None) -> None:
        if not self.rows:
            return
        if attempt_key is None:
            indices = range(len(self.rows))
        else:
            row = self._attempt_rows.get(attempt_key)
            if row is None:
                return
            trial_ordinal = self.rows[row][0].ordinal
            indices = self._trial_rows.get(trial_ordinal, ())
        changed = tuple(indices)
        for row in changed:
            trial, attempt = self.rows[row]
            self._display_rows[row] = self._display_values(trial, attempt)
        if changed:
            self.dataChanged.emit(
                self.index(min(changed), 0),
                self.index(max(changed), len(self.HEADERS) - 1),
            )

    def rowCount(self, parent: Any = QtCore.QModelIndex()) -> int:  # noqa: B008 — Qt virtual method signature
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: Any = QtCore.QModelIndex()) -> int:  # noqa: B008 — Qt virtual method signature
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Any, role: int) -> Any:
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return str(section + 1)

    def data(self, index: Any, role: int = QtCore.Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        _trial, attempt = self.rows[index.row()]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._display_rows[index.row()][index.column()]
        if role == QtCore.Qt.ItemDataRole.ToolTipRole and attempt is not None:
            return attempt.key
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return attempt
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and attempt is None:
            return QtGui.QBrush(QtGui.QColor("#777777"))
        return None

    def _display_values(
        self,
        trial: RecordedTrial,
        attempt: RecordedAttempt | None,
    ) -> tuple[str, ...]:
        review = (
            self.review.attempts.get(attempt.key)
            if self.review is not None and attempt is not None
            else None
        )
        reviewed_attempts = [
            self.review.attempts.get(item.key)
            for item in trial.attempts
            if self.review is not None
        ]
        if not trial.attempts:
            trial_outcome = "not recorded"
        elif any(
            item is not None and item.inclusion == "include"
            for item in reviewed_attempts
        ):
            trial_outcome = "included"
        elif reviewed_attempts and all(
            item is not None and item.inclusion == "exclude"
            for item in reviewed_attempts
        ):
            trial_outcome = "excluded"
        elif any(
            item is not None and item.quality in {"questionable", "bad"}
            for item in reviewed_attempts
        ):
            trial_outcome = "needs review"
        elif any(item.status == "accepted" for item in trial.attempts):
            trial_outcome = "accepted"
        elif any(
            item.status in {"pending_review", "recording"} for item in trial.attempts
        ):
            trial_outcome = "unresolved"
        else:
            trial_outcome = trial.attempts[-1].status
        return tuple(
            str(value)
            for value in (
                trial.ordinal,
                "—" if attempt is None else attempt.attempt_number,
                trial.title or trial.scenario_id,
                trial_outcome,
                trial.repetition if trial.repetition is not None else "—",
                "not recorded" if attempt is None else attempt.status,
                (
                    trial.activity_label
                    if attempt is None
                    else (
                        review.activity_label
                        if review and review.activity_label
                        else attempt.activity_label
                    )
                ),
                review.inclusion if review else "unreviewed",
                review.quality if review else "unreviewed",
            )
        )

    def attempt_at(self, row: int) -> RecordedAttempt | None:
        return self.rows[row][1] if 0 <= row < len(self.rows) else None

    def trial_at(self, row: int) -> RecordedTrial | None:
        return self.rows[row][0] if 0 <= row < len(self.rows) else None
