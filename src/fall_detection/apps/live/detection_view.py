"""Detection page of ``csi-live``: model scores, window previews and calibration.

The page shows what the native detector publishes; Rust owns acquisition,
preprocessing and inference. One backend runs at a time: :meth:`start` creates
and starts it, :meth:`tick` polls it once per display frame, and :meth:`stop`
releases it. The threshold calibrator outlives restarts, so thresholds fitted
for one selection carry over to the next.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import numpy as np

from . import calibration
from .detection import StreamBuffer, preview_images, status_text

TABLE_COLUMNS = (
    "Model",
    "State",
    "Score",
    "Threshold",
    "Data age",
    "Coverage",
    "Backend",
    "Replaced",
    "Error",
)
# Scores kept per model for the history plot: one minute at the default hop.
HISTORY_POINTS = 240
RECEIVER_TICKS = [[(122.5 + 245 * r, f"rx-{r + 1}") for r in range(4)]]


def robust_levels(values: np.ndarray) -> tuple[float, float] | None:
    """Return a 1st–99th percentile color range from a subsample of finite values."""
    sample = values.ravel()[::16]
    sample = sample[np.isfinite(sample)]
    if sample.size == 0:
        return None
    low, high = np.percentile(sample, [1, 99])
    return float(low), float(max(high, low + 1e-6))


class DetectionView:
    """Widgets and polling of one native detector run.

    Args:
        args: Parsed ``csi-live`` arguments (threshold, calibration file,
            hop, grace and backend name).
        backend_factory: Creates a native detector from a configuration.
    """

    def __init__(self, args: Any, *, backend_factory: Callable[[dict], Any]) -> None:
        import pyqtgraph as pg
        from PySide6 import QtCore, QtWidgets

        self._pg, self._QtCore, self._QtWidgets = pg, QtCore, QtWidgets
        self.args = args
        self._factory = backend_factory
        self.backend: Any = None
        self.models: list[str] = []
        self.maximum_age_ns = calibration.maximum_age_ns(args.hop_ms, args.grace_ms)
        self.calibrator = calibration.Calibrator(
            fallback=args.threshold,
            maximum_age_ns=self.maximum_age_ns,
            file=args.calibration,
        )
        self._latest: dict[str, dict] = {}
        self._histories: dict[str, deque] = {}
        self._curves: dict[str, Any] = {}
        self._cells: dict[tuple[int, int], str] = {}
        self._origin_ns: int | None = None
        self._preview_end_ns = 0
        self._preview_model: str | None = None
        self._stream_seq = 0
        self._levels_at = 0.0
        self._stream_buffer = StreamBuffer()

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._build_calibration_bar())

        self.table = QtWidgets.QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.plot = pg.PlotWidget(title="Fall score per model")
        self.plot.setYRange(0, 1)
        self.plot.setLabel("left", "score")
        self.plot.setLabel("bottom", "Window center since first result", units="s")
        self.plot.addLegend()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.plot)
        splitter.addWidget(self._build_preview_panel())
        splitter.setSizes([110, 200, 560])
        layout.addWidget(splitter, 1)

    # -- construction --------------------------------------------------

    def _build_calibration_bar(self) -> Any:
        QtWidgets = self._QtWidgets
        bar = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("Calibration:")
        label.setToolTip(
            "Perform the prompted ordinary movements (known non-falls); each "
            "model's threshold is then set so that at most "
            f"{calibration.TARGET_FALSE_POSITIVE_RATE:.0%} of them would alarm."
        )
        self.mark_button = QtWidgets.QPushButton("Start movement")
        self.mark_button.setToolTip(
            "Press when the prompted movement starts, and again when it ends"
        )
        self.mark_button.setEnabled(False)
        self.discard_button = QtWidgets.QPushButton("Discard movement")
        self.discard_button.setToolTip(
            "Drop the movement in progress, or the last recorded one"
        )
        self.discard_button.setEnabled(False)
        self.calibration_status = QtWidgets.QLabel()
        bar.addWidget(label)
        bar.addWidget(self.mark_button)
        bar.addWidget(self.discard_button)
        bar.addWidget(self.calibration_status, 1)
        self.mark_button.clicked.connect(self._mark_movement)
        self.discard_button.clicked.connect(self._discard_movement)
        return bar

    def _build_preview_panel(self) -> Any:
        QtCore, QtWidgets, pg = self._QtCore, self._QtWidgets, self._pg
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Preview model:"))
        self.preview_choice = QtWidgets.QComboBox()
        bar.addWidget(self.preview_choice)
        self.preview_info = QtWidgets.QLabel("Waiting for the first window…")
        bar.addWidget(self.preview_info, 1)
        layout.addLayout(bar)
        self.images = pg.GraphicsLayoutWidget()
        layout.addWidget(self.images)
        seconds = self._stream_buffer.rounds / 120
        self._stream_rect = QtCore.QRectF(-seconds, 0, seconds, 980)
        self.stream_image, self.stream_bar = self._image_plot(
            "Raw CSI stream (all received packets)",
            "viridis",
            "|H|",
            (0, 0, 2),
            "Time before latest packet",
        )
        self.raw_image, self.raw_bar = self._image_plot(
            "Latest window: raw CSI magnitude",
            "viridis",
            "|H|",
            (1, 0, 1),
            "Time in window",
        )
        self.input_image, self.input_bar = self._image_plot(
            "Latest window: model input, normalized",
            "CET-D1",
            "z",
            (1, 1, 1),
            "Time in window",
        )
        self.input_bar.setLevels((-3, 3))
        return panel

    def _image_plot(
        self,
        title: str,
        colormap: str,
        label: str,
        cell: tuple[int, int, int],
        x_label: str,
    ) -> tuple[Any, Any]:
        pg = self._pg
        row, column, span = cell
        view = self.images.addPlot(row=row, col=column, colspan=span, title=title)
        item = pg.ImageItem(axisOrder="row-major")
        item.setColorMap(pg.colormap.get(colormap))
        view.addItem(item)
        view.setLabel("bottom", x_label, units="s")
        view.getAxis("left").setTicks(RECEIVER_TICKS)
        view.invertY(True)
        for boundary in (245, 490, 735):
            view.addLine(y=boundary, pen=pg.mkPen("w", width=1))
        bar = pg.ColorBarItem(colorMap=pg.colormap.get(colormap), label=label)
        bar.setImageItem(item, insert_in=view)
        return item, bar

    # -- lifecycle -----------------------------------------------------

    @property
    def running(self) -> bool:
        """Whether a backend is currently started."""
        return self.backend is not None

    def start(self, config: dict) -> None:
        """Reset the page and start one backend for ``config``.

        Raises:
            RuntimeError, ValueError, OSError, KeyError: The calibration file
                does not fit, or the backend cannot be created or started.
                The page then holds no backend.
        """
        pg = self._pg
        self.stop()
        self.models = list(config["models"])
        self.calibrator.start(config)
        self._latest.clear()
        self._histories.clear()
        self._curves.clear()
        self._cells.clear()
        self.plot.clear()
        self._origin_ns = None
        self._preview_end_ns = 0
        self._preview_model = None
        self._stream_seq = 0
        self._levels_at = 0.0
        self._stream_buffer = StreamBuffer()
        self.preview_choice.clear()
        self.preview_choice.addItems(self.models)
        self.preview_info.setText("Waiting for the first window…")
        self.table.clearContents()
        self.table.setRowCount(len(self.models))
        for index, model in enumerate(self.models):
            self._histories[model] = deque(maxlen=HISTORY_POINTS)
            self._curves[model] = self.plot.plot(
                name=model, pen=pg.intColor(index, hues=max(1, len(self.models)))
            )
            self._set_cell(index, 0, model)
        backend = self._factory({**config, "preview": True})
        try:
            backend.start()
        except BaseException:
            backend.stop()
            raise
        self.backend = backend

    def stop(self) -> None:
        """Stop and release the backend; repeat calls are harmless."""
        backend, self.backend = self.backend, None
        self.mark_button.setEnabled(False)
        self.discard_button.setEnabled(False)
        if backend is not None:
            backend.stop()

    def tick(self) -> str:
        """Poll the backend once and return the status line for the window."""
        if self.backend is None:
            return ""
        # Poll every tick: each call is cheap when nothing is new, and a
        # coarser polling grid would show hop-spaced updates unevenly.
        self._update_stream()
        text = self._update_results()
        self._update_preview()
        return text

    # -- helpers -------------------------------------------------------

    def _set_cell(self, row: int, column: int, text: str) -> None:
        """Rewrite a table cell only when its text changes."""
        if self._cells.get((row, column)) == text:
            return
        self._cells[(row, column)] = text
        item = self.table.item(row, column)
        if item is None:
            self.table.setItem(row, column, self._QtWidgets.QTableWidgetItem(text))
        else:
            item.setText(text)

    def _mark_movement(self) -> None:
        if self.backend is not None:
            self.calibrator.mark(json.loads(self.backend.health()))

    def _discard_movement(self) -> None:
        if self.backend is not None:
            self.calibrator.discard(json.loads(self.backend.health()))

    def _update_stream(self) -> None:
        metadata, magnitudes = self.backend.stream(self._stream_seq)
        metadata = json.loads(metadata)
        self._stream_seq = metadata["seq"]
        if not self._stream_buffer.add(
            metadata["generation"],
            metadata["round"],
            metadata["receiver"],
            magnitudes,
        ):
            return
        image = self._stream_buffer.image()
        self.stream_image.setImage(image.T, autoLevels=False)
        # The rectangle scales from the current image size, so set it after.
        self.stream_image.setRect(self._stream_rect)
        if time.monotonic() - self._levels_at > 1.0:
            levels = robust_levels(image)
            if levels:
                self.stream_bar.setLevels(levels)
                self._levels_at = time.monotonic()

    def _update_preview(self) -> None:
        QtCore = self._QtCore
        model = self.preview_choice.currentText()
        if not model:
            return
        if model != self._preview_model:
            self._preview_end_ns = 0
            self._preview_model = model
        result = self.backend.preview(model, self._preview_end_ns)
        if result is None:
            return
        metadata, raw, model_input = result
        metadata = json.loads(metadata)
        frames = metadata["frames"]
        magnitudes, signals = preview_images(raw, model_input, frames)
        seconds = frames / 120
        self.raw_image.setImage(magnitudes.T, autoLevels=False)
        self.raw_image.setRect(QtCore.QRectF(0, 0, seconds, 980))
        levels = robust_levels(magnitudes)
        if levels:
            self.raw_bar.setLevels(levels)
        self.input_image.setImage(signals.T, autoLevels=False)
        self.input_image.setRect(QtCore.QRectF(0, 0, seconds, 980))
        coverage = " / ".join(f"{100 * c:.0f}%" for c in metadata["coverage"])
        self.preview_info.setText(
            f"{model} · {seconds:.0f} s window · coverage {coverage} · "
            "transparent = missing sample"
        )
        self._preview_end_ns = metadata["end_ns"]

    def _update_calibration(self, health: dict) -> None:
        self.calibrator.update(health)
        recorder = self.calibrator.recorder
        self.mark_button.setText(
            "Stop movement" if recorder.state == "recording" else "Start movement"
        )
        self.mark_button.setEnabled(self.calibrator.can_mark(health))
        self.discard_button.setEnabled(
            recorder.state != "idle" or bool(recorder.movements)
        )
        self.calibration_status.setText(self.calibrator.status(health["clock_ns"]))

    def _update_results(self) -> str:
        rows = json.loads(self.backend.poll(64))
        health = json.loads(self.backend.health())
        # Result times use the backend clock, which replay shifts.
        now = health.get("clock_ns") or time.monotonic_ns()
        self._update_calibration(health)
        for row in rows:
            model = row["model_id"]
            if model not in self._histories:
                continue
            self._latest[model] = row
            score = row.get("score")
            center = row.get("center_ns", row.get("end_ns"))
            if score is not None and center is not None:
                if self._origin_ns is None:
                    self._origin_ns = center
                points = self._histories[model]
                points.append(((center - self._origin_ns) / 1e9, score))
                self._curves[model].setData(
                    [p[0] for p in points], [p[1] for p in points]
                )
        finished = health.get("state") in ("finished", "stopped")
        for index, model in enumerate(self.models):
            row = self._latest.get(model, {})
            score = row.get("score")
            end = row.get("end_ns")
            stale = end is not None and now - end > self.maximum_age_ns
            threshold, calibrated = self.calibrator.threshold(model)
            if health.get("error"):
                score = None
                label = "unknown: backend error"
            elif finished:
                label = f"{health['state']} (no new data)"
            else:
                label = "unknown: stale" if stale else row.get("state", "waiting")
            if score is not None and not stale and not finished:
                label = "fall candidate" if score >= threshold else "non-candidate"
            coverage = row.get("coverage")
            values = [
                label,
                "—" if score is None or stale else f"{score:.4f}",
                f"{threshold:.4f} {'calibrated' if calibrated else 'uncalibrated'}",
                "—" if end is None else f"{max(0, now - end) / 1e9:.2f} s",
                "—"
                if not coverage
                else " / ".join(f"{100 * c:.0f}%" for c in coverage),
                row.get("provider", self.args.backend),
                str(health.get("queue_replacements", 0)),
                row.get("error") or health.get("error") or "",
            ]
            for column, value in enumerate(values, 1):
                self._set_cell(index, column, str(value))
        return status_text(health)
