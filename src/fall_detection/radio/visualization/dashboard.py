"""Shared live CSI dashboard panel for the viewer and the collector."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import time
from typing import Any

import numpy as np

from ..acquisition.availability import AvailabilitySnapshot
from ..acquisition.buffer import PreviewNotReady
from .gaps import CsiGapPanel
from .rendering import (
    DASHBOARD_TRACE_COUNTS,
    DEFAULT_DASHBOARD_SUBCARRIERS,
    DEFAULT_INSPECT_SUBCARRIER,
    VALID_SUBCARRIERS,
    PreparedCsiFrame,
    CsiFrameCache,
    RenderGate,
    phase_column,
    representative_subcarriers,
)
from .state import HISTORY_SECONDS, LiveState


DEFAULT_VIEW_SECONDS = 3.0
PHASE_MODE_CALIBRATED = "Calibrated phase"
PHASE_MODE_CHANGE = "Phase change"
PHASE_MODE_RAW = "Raw phase (diagnostic)"

__all__ = [
    "CsiDashboardPanel",
    "DASHBOARD_TRACE_COUNTS",
    "DEFAULT_DASHBOARD_SUBCARRIERS",
    "DEFAULT_INSPECT_SUBCARRIER",
    "DEFAULT_VIEW_SECONDS",
    "HISTORY_SECONDS",
    "PHASE_MODE_CALIBRATED",
    "PHASE_MODE_CHANGE",
    "PHASE_MODE_RAW",
    "VALID_SUBCARRIERS",
    "qt_modules",
]


def qt_modules() -> tuple[Any, Any, Any]:
    """Import Qt and pyqtgraph lazily so the apps stay importable without them."""

    try:
        from PySide6 import QtCore, QtWidgets
        import pyqtgraph as pg
    except ImportError as exc:
        raise ImportError(
            "PySide6 and pyqtgraph are required for the CSI dashboard"
        ) from exc
    pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")
    return QtCore, QtWidgets, pg


class CsiDashboardPanel:
    """Controls and dashboard views, shared by every CSI application.

    The panel owns the plotting widgets and the render gate.  Hosts drive it by
    calling :meth:`refresh` from a timer; it reads the buffers held by the
    supplied :class:`LiveState` and never touches acquisition threads.
    """

    def __init__(
        self,
        state: LiveState,
        *,
        fps: int,
        dashboard_subcarriers: int = DEFAULT_DASHBOARD_SUBCARRIERS,
        inspect_subcarrier: int = DEFAULT_INSPECT_SUBCARRIER,
        window_seconds: float = DEFAULT_VIEW_SECONDS,
        receivers: Sequence[str] | None = None,
        on_receiver_changed: Callable[[str], None] | None = None,
        can_render: Callable[[], bool] | None = None,
        gap_snapshot: Callable[[float, int], AvailabilitySnapshot | None] | None = None,
    ) -> None:
        QtCore, QtWidgets, pg = qt_modules()
        self._QtCore = QtCore
        self._QtWidgets = QtWidgets
        self._pg = pg
        self._np = np
        self.state = state
        self.fps = fps
        self.on_receiver_changed = on_receiver_changed
        self.can_render = can_render or (lambda: True)
        self.measured_fps = 0.0
        self.phase_gap_count = 0
        self._frame_cache = CsiFrameCache()

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.controls = QtWidgets.QHBoxLayout()

        self.trace_count_combo = QtWidgets.QComboBox()
        for count in DASHBOARD_TRACE_COUNTS:
            self.trace_count_combo.addItem(str(count), count)
        self.trace_count_combo.setCurrentIndex(
            DASHBOARD_TRACE_COUNTS.index(dashboard_subcarriers)
        )

        self.inspect_combo = QtWidgets.QComboBox()
        for subcarrier in VALID_SUBCARRIERS:
            self.inspect_combo.addItem(f"{subcarrier:+d}", subcarrier)
        self.inspect_combo.setCurrentIndex(VALID_SUBCARRIERS.index(inspect_subcarrier))

        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.window_spin.setRange(1.0, HISTORY_SECONDS)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setSuffix(" s")
        self.window_spin.setValue(window_seconds)

        self.phase_mode_combo = QtWidgets.QComboBox()
        self.phase_mode_combo.addItems(
            [PHASE_MODE_CALIBRATED, PHASE_MODE_CHANGE, PHASE_MODE_RAW]
        )

        self.receiver_combo = None
        if receivers:
            self.receiver_combo = QtWidgets.QComboBox()
            self.set_receivers(receivers, state.selected_receiver_id)
            self.receiver_combo.currentIndexChanged.connect(self._receiver_changed)
            self.controls.addWidget(QtWidgets.QLabel("receiver"))
            self.controls.addWidget(self.receiver_combo)
        self.controls.addWidget(QtWidgets.QLabel("dashboard traces"))
        self.controls.addWidget(self.trace_count_combo)
        self.controls.addWidget(QtWidgets.QLabel("inspect k"))
        self.controls.addWidget(self.inspect_combo)
        self.controls.addWidget(QtWidgets.QLabel("window"))
        self.controls.addWidget(self.window_spin)
        self.controls.addWidget(QtWidgets.QLabel("phase"))
        self.controls.addWidget(self.phase_mode_combo)
        self.preview_status = QtWidgets.QLabel("")
        self.controls.addWidget(self.preview_status)
        self.controls.addStretch()
        layout.addLayout(self.controls)

        self.plot_canvas = pg.GraphicsLayoutWidget()
        self.amplitude_plot = self._make_plot("Amplitude", "value", 0, 0)
        self.phase_plot = self._make_plot("Phase", "radians", 0, 1)
        self.iq_plot = self._make_plot("Mean I / Q", "sample", 1, 0)
        self.radio_plot = self._make_plot("Radio", "dBm", 1, 1)
        self.iq_plot.setYRange(-128.0, 128.0, padding=0)
        self.radio_plot.setYRange(-120.0, 0.0, padding=0)
        self.amplitude_plot.setYRange(0.0, 200.0, padding=0)
        self.phase_plot.setYRange(-3.2, 3.2, padding=0)

        self.amplitude_curves: list[Any] = []
        self.phase_curves: list[Any] = []
        self._curve_keys: list[int | None] = []
        for index in range(max(DASHBOARD_TRACE_COUNTS)):
            pen = pg.mkPen(
                pg.intColor(index, hues=max(DASHBOARD_TRACE_COUNTS)),
                width=1,
            )
            self.amplitude_curves.append(self.amplitude_plot.plot(pen=pen))
            self.phase_curves.append(self.phase_plot.plot(pen=pen))
            self._curve_keys.append(None)

        self.iq_plot.addLegend()
        self.iq_curves = (
            self.iq_plot.plot(pen=pg.mkPen("#f28e2b", width=2), name="mean I"),
            self.iq_plot.plot(
                pen=pg.mkPen("#59a14f", width=2, style=QtCore.Qt.PenStyle.DashLine),
                name="mean Q",
            ),
        )
        self.radio_plot.addLegend()
        self.radio_curves = (
            self.radio_plot.plot(pen=pg.mkPen("#e15759", width=2), name="RSSI"),
            self.radio_plot.plot(pen=pg.mkPen("#4e79a7", width=2), name="noise"),
        )
        self.plots = (
            self.amplitude_plot,
            self.phase_plot,
            self.iq_plot,
            self.radio_plot,
        )

        self.tabs = QtWidgets.QTabWidget()
        dashboard_tab = QtWidgets.QWidget()
        dashboard_layout = QtWidgets.QVBoxLayout(dashboard_tab)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.addWidget(self.plot_canvas)
        self.tabs.addTab(dashboard_tab, "Dashboard")

        self.phase_detail_canvas = pg.GraphicsLayoutWidget()
        self.phase_detail_plot = self.phase_detail_canvas.addPlot(row=0, col=0)
        self.phase_detail_plot.setTitle("Phase heatmap")
        self.phase_detail_plot.setLabel("left", "subcarrier k")
        self.phase_detail_plot.setLabel("bottom", "time", units="s")
        self.phase_detail_plot.setXRange(-DEFAULT_VIEW_SECONDS, 0.0, padding=0)
        self.phase_detail_plot.setYRange(-32.0, 31.0, padding=0)
        self.phase_detail_plot.setLimits(xMin=-HISTORY_SECONDS, xMax=0.0)
        self.phase_detail_plot.getViewBox().setMouseEnabled(x=False, y=False)
        self.phase_detail_plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.phase_detail_plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.phase_detail_plot.showGrid(x=True, y=False, alpha=0.15)
        self.phase_image = pg.ImageItem(axisOrder="row-major")
        self.phase_image.setColorMap(pg.colormap.get("CET-C7"))
        self.phase_detail_plot.addItem(self.phase_image)
        self.phase_color_bar = pg.ColorBarItem(
            values=(-np.pi, np.pi),
            colorMap=pg.colormap.get("CET-C7"),
            label="phase",
        )
        self.phase_color_bar.setImageItem(self.phase_image)
        self.phase_detail_canvas.addItem(self.phase_color_bar, row=0, col=1)

        self.phase_trace_plot = self.phase_detail_canvas.addPlot(
            row=1, col=0, colspan=2
        )
        self.phase_trace_plot.setTitle("Selected phase")
        self.phase_trace_plot.setLabel("left", "radians")
        self.phase_trace_plot.setLabel("bottom", "time", units="s")
        self.phase_trace_plot.setXRange(-DEFAULT_VIEW_SECONDS, 0.0, padding=0)
        self.phase_trace_plot.setYRange(-3.2, 3.2, padding=0)
        self.phase_trace_plot.setLimits(xMin=-HISTORY_SECONDS, xMax=0.0)
        self.phase_trace_plot.getViewBox().setMouseEnabled(x=False, y=True)
        self.phase_trace_plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.phase_trace_plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        self.phase_trace_plot.showGrid(x=True, y=True, alpha=0.2)
        self.phase_trace_curve = self.phase_trace_plot.plot(
            pen=pg.mkPen("#4e79a7", width=1),
        )

        phase_detail_tab = QtWidgets.QWidget()
        phase_detail_layout = QtWidgets.QVBoxLayout(phase_detail_tab)
        phase_detail_layout.setContentsMargins(0, 0, 0, 0)
        phase_detail_layout.addWidget(self.phase_detail_canvas)
        self.tabs.addTab(phase_detail_tab, "Phase by subcarrier")
        self.gaps = CsiGapPanel(
            QtCore, QtWidgets, pg,
            receivers=receivers or (), snapshot=gap_snapshot,
        )
        self.tabs.addTab(self.gaps.widget, "CSI gaps")
        self._gap_config_version = -1
        layout.addWidget(self.tabs, 1)

        self._render_gate = RenderGate(view_count=2)
        self._config_version = 0
        self._frame_count = 0
        self._frame_started = time.perf_counter()

        self.tabs.currentChanged.connect(self._tab_changed)
        self.window_spin.valueChanged.connect(self._set_time_range)
        self.trace_count_combo.currentIndexChanged.connect(
            lambda _index: self.mark_dirty()
        )
        self.inspect_combo.currentIndexChanged.connect(lambda _index: self.mark_dirty())
        self.phase_mode_combo.currentIndexChanged.connect(
            lambda _index: self.mark_dirty()
        )
        self._set_time_range(window_seconds)

    # -- public API ----------------------------------------------------

    @property
    def window_seconds(self) -> float:
        """Current history window in seconds."""

        return float(self.window_spin.value())

    @property
    def phase_mode(self) -> str:
        """Currently selected phase display mode."""

        return self.phase_mode_combo.currentText()

    def mark_dirty(self) -> None:
        """Force the active view to render on the next refresh."""

        self._config_version += 1

    def set_receivers(
        self,
        receiver_ids: Sequence[str],
        selected: str | None = None,
    ) -> None:
        """Populate the receiver selector without emitting a selection change."""

        if self.receiver_combo is None:
            return
        blocked = self.receiver_combo.blockSignals(True)
        try:
            self.receiver_combo.clear()
            for receiver_id in receiver_ids:
                self.receiver_combo.addItem(receiver_id, receiver_id)
            index = self.receiver_combo.findData(selected) if selected else -1
            self.receiver_combo.setCurrentIndex(max(0, index))
        finally:
            self.receiver_combo.blockSignals(blocked)

    def refresh(self) -> bool:
        """Render the active view when its data or controls changed."""

        if not self.can_render():
            self.preview_status.setText("Preview paused")
            return False

        active_tab = self.tabs.currentIndex()
        if active_tab == 2:
            self.preview_status.setText("")
            rendered = self.gaps.refresh(
                self.window_seconds,
                force=self._gap_config_version != self._config_version,
            )
            if rendered:
                self._gap_config_version = self._config_version
                self._record_frame()
            return rendered
        buffer = self.state.buffer
        revision = buffer.received_records
        if not self._render_gate.needs_render(
            active_tab, revision, self._config_version
        ):
            return False

        if not buffer.prepare_phase_views(seconds=self.window_seconds):
            self.preview_status.setText("Preparing preview…")
            return False
        self.preview_status.setText("")
        try:
            frame = self._frame_cache.prepare(
                buffer,
                phase_mode=self.phase_mode,
                phase_mode_change=PHASE_MODE_CHANGE,
                phase_mode_raw=PHASE_MODE_RAW,
                window_seconds=self.window_seconds,
                prepared_only=True,
            )
        except PreviewNotReady:
            self.preview_status.setText("Preparing preview…")
            return False
        if active_tab == 0:
            self._update_dashboard(frame)
        else:
            self._update_detail(frame)
        self._render_gate.mark_rendered(active_tab, revision, self._config_version)
        self._record_frame()
        return True

    # -- construction helpers -----------------------------------------

    def _make_plot(self, title: str, ylabel: str, row: int, column: int) -> Any:
        pg = self._pg
        chart = self.plot_canvas.addPlot(row=row, col=column)
        chart.setTitle(title)
        chart.setLabel("left", ylabel)
        chart.setLabel("bottom", "time", units="s")
        chart.showGrid(x=True, y=True, alpha=0.25)
        chart.setXRange(-DEFAULT_VIEW_SECONDS, 0.0, padding=0)
        chart.setLimits(xMin=-HISTORY_SECONDS, xMax=0.0)
        chart.getViewBox().setMouseEnabled(x=False, y=True)
        chart.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        chart.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
        chart.setClipToView(True)
        chart.setDownsampling(auto=True, mode="peak")
        return chart

    # -- signal handlers ----------------------------------------------

    def _tab_changed(self, _index: int) -> None:
        self.mark_dirty()

    def _receiver_changed(self, _index: int) -> None:
        receiver_id = self.receiver_combo.currentData()
        if receiver_id is None:
            return
        try:
            self.state.select_receiver(str(receiver_id))
        except ValueError:
            return
        if self.on_receiver_changed is not None:
            self.on_receiver_changed(str(receiver_id))
        for curve in (
            *self.amplitude_curves,
            *self.phase_curves,
            *self.iq_curves,
            *self.radio_curves,
        ):
            curve.clear()
        self.phase_trace_curve.clear()
        self.phase_image.setVisible(False)
        self.mark_dirty()

    def _set_time_range(self, seconds: float) -> None:
        for plot in self.plots:
            plot.setXRange(-seconds, 0.0, padding=0)
        self.phase_detail_plot.setXRange(-seconds, 0.0, padding=0)
        self.phase_trace_plot.setXRange(-seconds, 0.0, padding=0)
        self.mark_dirty()

    # -- rendering -----------------------------------------------------

    def _record_frame(self) -> None:
        self._frame_count += 1
        now = time.perf_counter()
        elapsed = now - self._frame_started
        if elapsed >= 1.0:
            self.measured_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._frame_started = now

    def _update_dashboard(self, frame: PreparedCsiFrame) -> None:
        pg = self._pg
        np_module = self._np
        selected = representative_subcarriers(
            int(self.trace_count_combo.currentData()),
            frame.subcarriers,
        )
        self.phase_gap_count = (
            int(np_module.count_nonzero(~np_module.isfinite(frame.selected_phases)))
            if frame.selected_phases.size
            else 0
        )
        for index, (amplitude_curve, phase_curve) in enumerate(
            zip(self.amplitude_curves, self.phase_curves)
        ):
            if index >= len(selected) or not frame.timestamps.size:
                amplitude_curve.setVisible(False)
                phase_curve.setVisible(False)
                continue
            subcarrier = selected[index]
            column = frame.subcarriers.index(subcarrier)
            if self._curve_keys[index] != subcarrier:
                pen = pg.mkPen(
                    pg.intColor(
                        VALID_SUBCARRIERS.index(subcarrier),
                        hues=len(VALID_SUBCARRIERS),
                    ),
                    width=1,
                )
                amplitude_curve.setPen(pen)
                phase_curve.setPen(pen)
                self._curve_keys[index] = subcarrier
            amplitude_curve.setVisible(True)
            phase_curve.setVisible(True)
            amplitude_curve.setData(
                frame.timestamps,
                frame.amplitudes[:, column],
                skipFiniteCheck=False,
            )
            phase_curve.setData(
                frame.timestamps,
                frame.selected_phases[:, column],
                skipFiniteCheck=False,
            )

        self.iq_curves[0].setData(frame.timestamps, frame.mean_i, skipFiniteCheck=False)
        self.iq_curves[1].setData(frame.timestamps, frame.mean_q, skipFiniteCheck=False)
        self.radio_curves[0].setData(
            frame.timestamps, frame.rssi, skipFiniteCheck=False
        )
        self.radio_curves[1].setData(
            frame.timestamps, frame.noise_floor, skipFiniteCheck=False
        )

    def _update_detail(self, frame: PreparedCsiFrame) -> None:
        QtCore = self._QtCore
        np_module = self._np
        self.phase_gap_count = (
            int(np_module.count_nonzero(~np_module.isfinite(frame.selected_phases)))
            if frame.selected_phases.size
            else 0
        )
        if not frame.timestamps.size or not frame.subcarriers:
            self.phase_image.setVisible(False)
            self.phase_trace_curve.setData([], [])
            self.phase_detail_plot.setTitle("Phase heatmap — waiting for HT-LTF data")
            return

        self.phase_image.setVisible(True)
        self.phase_image.setImage(
            frame.selected_phases.T,
            autoLevels=False,
            levels=(-np.pi, np.pi),
        )
        image_width = max(float(frame.timestamps[-1] - frame.timestamps[0]), 1e-6)
        image_height = max(float(len(frame.subcarriers) - 1), 1.0)
        self.phase_image.setRect(
            QtCore.QRectF(
                float(frame.timestamps[0]),
                float(frame.subcarriers[0]),
                image_width,
                image_height,
            )
        )
        inspected = int(self.inspect_combo.currentData())
        self.phase_trace_curve.setData(
            frame.timestamps,
            phase_column(frame, inspected),
            skipFiniteCheck=False,
        )
        self.phase_detail_plot.setTitle(
            f"Phase heatmap ({self.phase_mode_combo.currentText()})"
        )
        self.phase_trace_plot.setTitle(f"Selected phase k={inspected:+d}")
