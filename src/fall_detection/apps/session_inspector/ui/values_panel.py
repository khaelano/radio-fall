"""Exact value tables for the session inspector."""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtWidgets

from ..data import (
    AttemptData,
    TableData,
    csi_record_for_table_row,
    csi_value_rows,
)
from .tables import TextTableModel

RECORD_UNAVAILABLE_MESSAGE = (
    "Frame tables changed since this attempt was loaded; reload the attempt."
)


class ValuesPanel(QtWidgets.QWidget):
    """Exact attempt tables plus per-subcarrier detail for one CSI row."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QtWidgets.QLabel("Select a recorded attempt.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        paging = QtWidgets.QHBoxLayout()
        paging.addStretch()
        self.previous_page = QtWidgets.QPushButton("Previous page")
        self.page_label = QtWidgets.QLabel("Page 1 / 1")
        self.next_page = QtWidgets.QPushButton("Next page")
        paging.addWidget(self.previous_page)
        paging.addWidget(self.page_label)
        paging.addWidget(self.next_page)
        layout.addLayout(paging)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.models: dict[str, TextTableModel] = {}
        self.views: dict[str, Any] = {}
        for key, title in (
            ("csi", "CSI rows"),
            ("radio_timing", "Radio timing"),
            ("detail", "Selected CSI values"),
        ):
            view = QtWidgets.QTableView()
            view.setAlternatingRowColors(True)
            view.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
            )
            view.setSortingEnabled(False)
            view.horizontalHeader().setStretchLastSection(False)
            model = TextTableModel(parent=view)
            view.setModel(model)
            self.models[key] = model
            self.views[key] = view
            self.tabs.addTab(view, title)
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        self.next_page.clicked.connect(lambda: self._change_page(1))
        self.tabs.currentChanged.connect(self._update_paging)
        self.views["csi"].selectionModel().currentRowChanged.connect(
            self._csi_row_changed
        )
        self.data: AttemptData | None = None
        self._record_by_row: dict[int, Any] = {}
        self._update_paging()

    def _current_model(self) -> TextTableModel:
        return self.models[("csi", "radio_timing", "detail")[self.tabs.currentIndex()]]

    @QtCore.Slot()
    def _update_paging(self, *_args: Any) -> None:
        model = self._current_model()
        self.page_label.setText(f"Page {model.page + 1} / {model.page_count}")
        self.previous_page.setEnabled(model.page > 0)
        self.next_page.setEnabled(model.page + 1 < model.page_count)

    def _change_page(self, offset: int) -> None:
        model = self._current_model()
        model.set_page(model.page + offset)
        self._update_paging()

    def clear(self, message: str = "Select a recorded attempt.") -> None:
        self.data = None
        self._record_by_row = {}
        self.summary.setText(message)
        for model in self.models.values():
            model.set_table(TableData(name=""))
        self._update_paging()

    def set_data(self, data: AttemptData) -> None:
        self.data = data
        self._record_by_row = (
            dict(zip(data.record_row_indices, data.records, strict=True))
            if data.records
            else {}
        )
        self.models["csi"].set_table(data.csi)
        self.models["radio_timing"].set_table(data.radio_timing)
        self.models["detail"].set_table(TableData(name=""))
        summary = (
            f"{data.receiver_id}: {data.record_count} valid CSI records · "
            f"{data.radio_timing.row_count} timing rows"
        )
        if data.warnings:
            summary += f" · {len(data.warnings)} warning(s)"
            self.summary.setToolTip("\n".join(data.warnings))
        else:
            self.summary.setToolTip("")
        self.summary.setText(summary)
        self._update_paging()

    def _csi_row_changed(self, current: Any, _previous: Any) -> None:
        if not current.isValid():
            self.models["detail"].set_table(TableData(name=""))
            return
        record = self._record_by_row.get(self.models["csi"].source_row(current.row()))
        if record is None and self.data is not None:
            record = csi_record_for_table_row(
                self.data,
                self.models["csi"].source_row(current.row()),
            )
        if record is None:
            self.models["detail"].set_table(
                TableData(
                    name="Selected CSI values",
                    headers=("message",),
                    rows=((RECORD_UNAVAILABLE_MESSAGE,),),
                )
            )
            self.views["detail"].resizeColumnsToContents()
            if self.tabs.currentIndex() == 2:
                self._update_paging()
            return
        rows = csi_value_rows(record)
        table = TableData(
            name="Selected CSI values",
            headers=(
                "subcarrier",
                "real (I)",
                "imaginary (Q)",
                "amplitude",
                "raw phase",
                "calibrated phase",
            ),
            rows=tuple(
                (
                    row.subcarrier,
                    f"{row.real:.9g}",
                    f"{row.imaginary:.9g}",
                    f"{row.amplitude:.9g}",
                    f"{row.raw_phase:.9g}",
                    ""
                    if row.calibrated_phase is None
                    else f"{row.calibrated_phase:.9g}",
                )
                for row in rows
            ),
        )
        self.models["detail"].set_table(table)
        self.views["detail"].resizeColumnsToContents()
        if self.tabs.currentIndex() == 2:
            self._update_paging()
