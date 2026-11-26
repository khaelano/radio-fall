"""Signal plots for the session inspector."""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from fall_detection.apps.common.rendering import representative_subcarriers

from ..data import (
    AttemptData,
    downsample_indices,
    timed_phase_image,
)
from .video_panel import VideoPanel


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
        self.phase_curve = self._curve(self.phase_plot, pg.mkPen("#4e79a7", width=1.5))
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
                        and np.isfinite(self.frame.calibrated_phases[:, index]).any()
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
