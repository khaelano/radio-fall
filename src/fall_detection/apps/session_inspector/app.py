"""Standalone PySide6 application for offline session review and curation."""

from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from collections.abc import Sequence
from concurrent.futures import (
    Executor,
    ProcessPoolExecutor,
)
from concurrent.futures import (
    TimeoutError as FutureTimeoutError,
)
from copy import deepcopy
from multiprocessing import get_context
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np

from fall_detection.radio.preprocessing.rendering import (
    representative_subcarriers,
)
from fall_detection.session_inspector.data import (
    AttemptData,
    TableData,
    csi_record_for_table_row,
    csi_value_rows,
    downsample_indices,
    load_attempt_data_for_ui,
    timed_phase_image,
)
from fall_detection.session_inspector.exporter import (
    ExportCancelled,
    export_curated_bundle,
    session_size,
)
from fall_detection.session_inspector.models import (
    RecordedAttempt,
    RecordedTrial,
    SessionBundle,
    SessionReadError,
    scan_sessions,
)
from fall_detection.session_inspector.review import (
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

DEFAULT_SESSIONS_DIR = Path("data/raw/sessions")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and curate recorded fall-detection sessions."
    )
    parser.add_argument(
        "session",
        nargs="?",
        type=Path,
        help="optional individual session directory to open",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=DEFAULT_SESSIONS_DIR,
        help="directory containing collection session bundles",
    )
    return parser


def _review_state(document: ReviewDocument) -> dict[str, Any]:
    return {
        "metadata": deepcopy(document.metadata),
        "attempts": {
            key: value.to_mapping() for key, value in sorted(document.attempts.items())
        },
    }


def _human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{value} B"


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


try:  # Keep the module importable when the optional GUI extra is absent.
    import pyqtgraph as pg
    from PySide6 import QtCore, QtGui, QtWidgets
except (
    ImportError
):  # pragma: no cover - exercised by installations without radio extras
    QtCore = QtGui = QtWidgets = pg = None


if QtCore is not None:
    from fall_detection.apps.session_inspector.video_panel import VideoPanel

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
            self.table = table or TableData(name="", path=None)
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

        def data(
            self, index: Any, role: int = QtCore.Qt.ItemDataRole.DisplayRole
        ) -> Any:
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

        def data(
            self, index: Any, role: int = QtCore.Qt.ItemDataRole.DisplayRole
        ) -> Any:
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
                item.status in {"pending_review", "recording"}
                for item in trial.attempts
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

    class WorkerSignals(QtCore.QObject):
        completed = QtCore.Signal(int, object)
        failed = QtCore.Signal(int, str)

    class AttemptLoadWorker(QtCore.QRunnable):
        """Load one receiver outside the GUI thread."""

        def __init__(
            self,
            token: int,
            attempt: RecordedAttempt,
            receiver_id: str,
            cancelled: Event,
            executor: Executor,
            *,
            prepare_signals: bool,
        ) -> None:
            super().__init__()
            self.token = token
            self.attempt = attempt
            self.receiver_id = receiver_id
            self.cancelled = cancelled
            self.executor = executor
            self.prepare_signals = prepare_signals
            self.signals = WorkerSignals()

        @QtCore.Slot()
        def run(self) -> None:
            try:
                if self.cancelled.is_set():
                    return
                future = self.executor.submit(
                    load_attempt_data_for_ui,
                    self.attempt,
                    self.receiver_id,
                    prepare_signals=self.prepare_signals,
                )
                while True:
                    if self.cancelled.is_set():
                        future.cancel()
                        return
                    try:
                        data = future.result(timeout=0.05)
                        break
                    except FutureTimeoutError:
                        continue
            except Exception as exc:  # noqa: BLE001 — keep worker exceptions inside the UI boundary
                self.signals.failed.emit(self.token, str(exc))
                return
            self.signals.completed.emit(self.token, data)

    class SignalPrepareWorker(QtCore.QRunnable):
        """Prepare downsampled plot matrices outside the GUI thread."""

        def __init__(
            self,
            token: int,
            attempt: RecordedAttempt,
            receiver_id: str,
            cancelled: Event,
            executor: Executor,
        ) -> None:
            super().__init__()
            self.token = token
            self.attempt = attempt
            self.receiver_id = receiver_id
            self.cancelled = cancelled
            self.executor = executor
            self.signals = WorkerSignals()

        @QtCore.Slot()
        def run(self) -> None:
            try:
                if self.cancelled.is_set():
                    return
                future = self.executor.submit(
                    load_attempt_data_for_ui,
                    self.attempt,
                    self.receiver_id,
                    prepare_signals=True,
                )
                while True:
                    if self.cancelled.is_set():
                        future.cancel()
                        return
                    try:
                        data = future.result(timeout=0.05)
                        break
                    except FutureTimeoutError:
                        continue
            except Exception as exc:  # noqa: BLE001 — application error boundary
                self.signals.failed.emit(self.token, str(exc))
                return
            self.signals.completed.emit(self.token, data)

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
                ("clock_sync", "Clock sync"),
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
            return self.models[
                ("csi", "radio_timing", "clock_sync", "detail")[
                    self.tabs.currentIndex()
                ]
            ]

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
                model.set_table(TableData(name="", path=None))
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
            self.models["clock_sync"].set_table(data.clock_sync)
            self.models["detail"].set_table(TableData(name="", path=None))
            summary = (
                f"{data.receiver_id}: {data.record_count} valid CSI records · "
                f"{data.radio_timing.row_count} timing rows · "
                f"{data.clock_sync.row_count} clock-sync rows"
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
                self.models["detail"].set_table(TableData(name="", path=None))
                return
            record = self._record_by_row.get(
                self.models["csi"].source_row(current.row())
            )
            if record is None and self.data is not None:
                record = csi_record_for_table_row(
                    self.data,
                    self.models["csi"].source_row(current.row()),
                )
            if record is None:
                self.models["detail"].set_table(TableData(name="", path=None))
                return
            rows = csi_value_rows(record)
            table = TableData(
                name="Selected CSI values",
                path=None,
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
            if self.tabs.currentIndex() == 3:
                self._update_paging()

    class SignalsPanel(QtWidgets.QWidget):
        """Interactive offline plots derived from the selected CSI file."""

        def __init__(self, parent: Any = None) -> None:
            super().__init__(parent)
            self.data: AttemptData | None = None
            self.frame = None
            self._closed = False
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            controls = QtWidgets.QHBoxLayout()
            controls.addWidget(QtWidgets.QLabel("Traces"))
            self.trace_count = QtWidgets.QComboBox()
            for count in (8, 12, 16):
                self.trace_count.addItem(str(count), count)
            self.trace_count.setCurrentText("12")
            controls.addWidget(self.trace_count)
            controls.addWidget(QtWidgets.QLabel("Inspect subcarrier"))
            self.subcarrier = QtWidgets.QComboBox()
            controls.addWidget(self.subcarrier)
            controls.addStretch()
            self.summary = QtWidgets.QLabel("No signal loaded")
            controls.addWidget(self.summary)
            layout.addLayout(controls)

            self.canvas = pg.GraphicsLayoutWidget()
            self.video = VideoPanel(self)
            self.video_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
            self.video_splitter.addWidget(self.canvas)
            self.video_splitter.addWidget(self.video)
            self.video_splitter.setSizes((850, 350))
            layout.addWidget(self.video_splitter, 1)
            self.amplitude_plot = self._plot("Amplitude", "value", 0, 0)
            self.phase_plot = self._plot("Selected calibrated phase", "radians", 0, 1)
            self.iq_plot = self._plot("Mean I / Q", "sample", 1, 0)
            self.radio_plot = self._plot("RSSI / noise floor", "dBm", 1, 1)
            self.interval_plot = self._plot("Frame interval", "ms", 2, 0)
            self.heatmap_plot = self.canvas.addPlot(row=2, col=1)
            self.heatmap_plot.setTitle("Calibrated phase heatmap")
            self.heatmap_plot.setLabel("bottom", "time", units="s")
            self.heatmap_plot.setLabel("left", "subcarrier k")
            self.heatmap = pg.ImageItem(axisOrder="row-major")
            self.heatmap.setColorMap(pg.colormap.get("CET-C7"))
            self.heatmap_plot.addItem(self.heatmap)
            self.amplitude_curves = [
                self._curve(
                    self.amplitude_plot,
                    pg.mkPen(pg.intColor(index, hues=16), width=1),
                )
                for index in range(16)
            ]
            self.phase_curve = self._curve(
                self.phase_plot, pg.mkPen("#4e79a7", width=1.5)
            )
            self.iq_curves = (
                self._curve(self.iq_plot, pg.mkPen("#f28e2b", width=1.5)),
                self._curve(self.iq_plot, pg.mkPen("#59a14f", width=1.5)),
            )
            self.radio_curves = (
                self._curve(self.radio_plot, pg.mkPen("#e15759", width=1.5)),
                self._curve(self.radio_plot, pg.mkPen("#4e79a7", width=1.5)),
            )
            self.interval_curve = self._curve(
                self.interval_plot, pg.mkPen("#7c3aed", width=1)
            )
            self._plots = (
                self.amplitude_plot,
                self.phase_plot,
                self.iq_plot,
                self.radio_plot,
                self.interval_plot,
                self.heatmap_plot,
            )
            self.video_cursors = []
            for plot in self._plots:
                line = pg.InfiniteLine(
                    0, angle=90, movable=True, pen=pg.mkPen("#f59e0b", width=2)
                )
                plot.addItem(line, ignoreBounds=True)
                line.hide()
                line.sigPositionChangeFinished.connect(
                    lambda item: self.video.seek(float(item.value()))
                )
                self.video_cursors.append(line)
            self.video.position_changed.connect(self._set_video_cursor)
            self.canvas.scene().sigMouseClicked.connect(self._plot_clicked)
            self.trace_count.currentIndexChanged.connect(self._render)
            self.subcarrier.currentIndexChanged.connect(self._render_phase)

        def _set_video_cursor(self, seconds: float) -> None:
            aligned = self.data is not None and self.data.signal_times is not None
            for line in self.video_cursors:
                line.setVisible(aligned and self.video.timeline is not None)
                line.setValue(seconds)

        def _plot_clicked(self, event: Any) -> None:
            if (
                event.button() != QtCore.Qt.MouseButton.LeftButton
                or self.data is None
                or self.data.signal_times is None
            ):
                return
            for plot in self._plots:
                if plot.getViewBox().sceneBoundingRect().contains(event.scenePos()):
                    self.video.pause()
                    self.video.seek(
                        float(plot.getViewBox().mapSceneToView(event.scenePos()).x())
                    )
                    break

        def closeEvent(self, event: Any) -> None:
            self.shutdown()
            super().closeEvent(event)

        def shutdown(self) -> None:
            """Release graphics objects while Qt is alive, before interpreter exit."""
            if self._closed:
                return
            self._closed = True
            self.video.shutdown()
            self.canvas.close()

        def _plot(self, title: str, label: str, row: int, column: int) -> Any:
            plot = self.canvas.addPlot(row=row, col=column)
            plot.setTitle(title)
            plot.setLabel("bottom", "time", units="s")
            plot.setLabel("left", label)
            plot.showGrid(x=True, y=True, alpha=0.18)
            return plot

        @staticmethod
        def _curve(plot: Any, pen: Any) -> Any:
            curve = plot.plot(pen=pen)
            curve.setClipToView(True)
            curve.setDownsampling(auto=True, method="peak")
            return curve

        def clear(self, message: str = "No signal loaded") -> None:
            self.data = None
            self.frame = None
            self.summary.setText(message)
            self.subcarrier.clear()
            for curve in (
                *self.amplitude_curves,
                self.phase_curve,
                *self.iq_curves,
                *self.radio_curves,
                self.interval_curve,
            ):
                curve.setData([], [])
            self.heatmap.clear()
            for line in self.video_cursors:
                line.hide()

        def set_data(self, data: AttemptData) -> None:
            self.data = data
            if not data.record_count:
                self.clear("No valid CSI records")
                return
            if data.prepared_frame is None:
                self.clear("Preparing signal plots…")
                return
            self.frame = data.prepared_frame
            blocker = QtCore.QSignalBlocker(self.subcarrier)
            self.subcarrier.clear()
            for value in self.frame.subcarriers:
                self.subcarrier.addItem(f"{value:+d}", value)
            if self.subcarrier.count():
                preferred = self.subcarrier.findData(2)
                if preferred < 0:
                    preferred = next(
                        (
                            index
                            for index, value in enumerate(self.frame.subcarriers)
                            if value != 0
                            and np.isfinite(
                                self.frame.calibrated_phases[:, index]
                            ).any()
                        ),
                        0,
                    )
                self.subcarrier.setCurrentIndex(preferred)
            del blocker
            duration = (
                float(self.frame.timestamps[-1] - self.frame.timestamps[0])
                if self.frame.timestamps.size > 1
                else 0.0
            )
            self.summary.setText(
                f"{data.record_count} records · {duration:.2f} s · {data.receiver_id}\n{data.time_source}"
            )
            self._render()
            self._set_video_cursor(self.video.position)

        def _series(self, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            if self.frame is None:
                return np.empty(0), np.empty(0)
            indices = np.asarray(downsample_indices(len(values)), dtype=np.int64)
            return self.frame.timestamps[indices], values[indices]

        @QtCore.Slot()
        def _render(self, *_args: Any) -> None:
            if self.frame is None:
                return
            frame = self.frame
            count = int(self.trace_count.currentData() or 12)
            selected = representative_subcarriers(count, frame.subcarriers)
            for curve_index, subcarrier in enumerate(selected):
                column = frame.subcarriers.index(subcarrier)
                x, y = self._series(frame.amplitudes[:, column])
                self.amplitude_curves[curve_index].setData(x, y)
            for curve in self.amplitude_curves[len(selected) :]:
                curve.setData([], [])

            for curve, values in zip(
                self.iq_curves, (frame.mean_i, frame.mean_q), strict=True
            ):
                x, y = self._series(values)
                curve.setData(x, y)
            for curve, values in zip(
                self.radio_curves,
                (frame.rssi, frame.noise_floor),
                strict=True,
            ):
                x, y = self._series(values)
                curve.setData(x, y)
            if frame.timestamps.size > 1:
                intervals = np.diff(frame.timestamps) * 1000.0
                indices = np.asarray(downsample_indices(len(intervals)), dtype=np.int64)
                self.interval_curve.setData(
                    frame.timestamps[1:][indices],
                    intervals[indices],
                )
            else:
                self.interval_curve.setData([], [])

            phase = frame.calibrated_phases
            if phase.size:
                image = (
                    timed_phase_image(frame.timestamps, phase)
                    if self.data.signal_times is not None
                    else phase.T
                )
                self.heatmap.setImage(image, autoLevels=False, levels=(-np.pi, np.pi))
                x0 = float(frame.timestamps[0])
                width = max(1e-6, float(frame.timestamps[-1] - x0))
                y0 = float(frame.subcarriers[0]) if frame.subcarriers else 0.0
                height = (
                    float(frame.subcarriers[-1] - frame.subcarriers[0] + 1)
                    if frame.subcarriers
                    else float(phase.shape[1])
                )
                self.heatmap.setRect(QtCore.QRectF(x0, y0, width, height))
            else:
                self.heatmap.clear()
            self._render_phase()

        @QtCore.Slot()
        def _render_phase(self, *_args: Any) -> None:
            if self.frame is None or self.subcarrier.currentData() is None:
                self.phase_curve.setData([], [])
                return
            subcarrier = int(self.subcarrier.currentData())
            try:
                column = self.frame.subcarriers.index(subcarrier)
            except ValueError:
                self.phase_curve.setData([], [])
                return
            x, y = self._series(self.frame.calibrated_phases[:, column])
            self.phase_curve.setData(x, y)

    class SessionInspectorWindow(QtWidgets.QMainWindow):
        """Main offline session browser and review editor."""

        def __init__(self, source_path: Path) -> None:
            super().__init__()
            self.source_path = source_path
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
            self._data_cache: OrderedDict[tuple[str, str, str], AttemptData] = (
                OrderedDict()
            )
            self._cache_limit = 4
            self._load_timer = QtCore.QTimer(self)
            self._load_timer.setSingleShot(True)
            self._load_timer.setInterval(140)
            self._load_timer.timeout.connect(self._dispatch_attempt_load)
            self.thread_pool = QtCore.QThreadPool(self)
            self.thread_pool.setMaxThreadCount(2)
            # Python's CSV/JSON CSI decoding is CPU-bound and can starve the
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
            self.environment_text.setPlaceholderText(
                "Acquisition environment and protocol"
            )
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
            self.inclusion_combo.currentTextChanged.connect(
                self._attempt_review_changed
            )
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
                QtWidgets.QMessageBox.critical(
                    self, "Unable to read sessions", str(exc)
                )
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

        def _open_session(self, session: SessionBundle) -> None:
            self._cancel_load()
            self._data_cache.clear()
            self.session = session
            self.store = ReviewStore(session)
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
                    "ACTIVE — READ ONLY"
                    if session.active
                    else "INVALID REVIEW — READ ONLY"
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
            self.export_button.setEnabled(
                self.session is not None and self.review_writable
            )

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
                self._clear_attempt(
                    "This planned protocol trial has no recorded attempts."
                )
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
                        "files": {
                            files.receiver_id: [
                                path.relative_to(self.session.path).as_posix()
                                for path in files.available
                            ]
                            for files in attempt.receiver_files
                        },
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
                self.signals_tab.clear("No receiver files found")
                self.values_tab.clear("No receiver files found")

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
                QtWidgets.QMessageBox.warning(
                    self, "Review changed elsewhere", str(exc)
                )
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
            default_name = f"{self.session.path.name}-curated"
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
                value = (
                    1000 if expected == 0 else min(1000, int(copied * 1000 / expected))
                )
                progress_dialog.setValue(value)
                progress_dialog.setLabelText(
                    f"Copying {relative}\n"
                    f"{_human_size(copied)} / {_human_size(expected)}"
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


def main(argv: Sequence[str] | None = None) -> int:
    """Run the offline collection session inspector."""

    args = _parser().parse_args(argv)
    if QtWidgets is None or pg is None:
        print(
            "PySide6 and pyqtgraph are required; install with: uv sync --extra radio",
            file=sys.stderr,
        )
        return 2
    source = args.session if args.session is not None else args.sessions_dir
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")
    window = SessionInspectorWindow(source)
    window.show()
    return application.exec()
