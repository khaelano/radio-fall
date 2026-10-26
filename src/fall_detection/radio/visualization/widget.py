"""Reusable live CSI plotting widget for Qt applications."""

from __future__ import annotations

from ..acquisition.buffer import RollingCsiBuffer


class CsiDashboardWidget:
    """Small dashboard that renders the same prepared frames as ``csi-viewer``."""

    def __init__(
        self,
        buffer: RollingCsiBuffer,
        *,
        window_seconds: float = 3.0,
        max_points: int = 90,
    ) -> None:
        try:
            import pyqtgraph as pg
        except ImportError as exc:
            raise ImportError("pyqtgraph is required for CSI plots") from exc
        self.buffer = buffer
        self.window_seconds = window_seconds
        self.max_points = max_points
        self.widget = pg.GraphicsLayoutWidget()
        self.amplitude_plot = self.widget.addPlot(row=0, col=0)
        self.amplitude_plot.setTitle("Mean CSI I/Q")
        self.amplitude_plot.setLabel("left", "sample")
        self.amplitude_plot.setLabel("bottom", "time", units="s")
        self.amplitude_plot.showGrid(x=True, y=True, alpha=0.2)
        self.rssi_plot = self.widget.addPlot(row=1, col=0)
        self.rssi_plot.setTitle("Radio RSSI / noise")
        self.rssi_plot.setLabel("left", "dBm")
        self.rssi_plot.setLabel("bottom", "time", units="s")
        self.rssi_plot.showGrid(x=True, y=True, alpha=0.2)
        self.mean_i_curve = self.amplitude_plot.plot(pen=pg.mkPen("#4e79a7", width=2))
        self.mean_q_curve = self.amplitude_plot.plot(pen=pg.mkPen("#59a14f", width=2))
        self.rssi_curve = self.rssi_plot.plot(pen=pg.mkPen("#e15759", width=2))
        self.noise_curve = self.rssi_plot.plot(pen=pg.mkPen("#f28e2b", width=2))

    def refresh(self) -> None:
        """Render the current rolling buffer snapshot."""

        snapshot = self.buffer.monitor_snapshot(
            seconds=self.window_seconds,
            max_points=self.max_points,
        )
        if not snapshot.timestamps:
            return
        timestamps = tuple(
            timestamp - snapshot.timestamps[-1]
            for timestamp in snapshot.timestamps
        )
        self.mean_i_curve.setData(timestamps, snapshot.mean_i)
        self.mean_q_curve.setData(timestamps, snapshot.mean_q)
        self.rssi_curve.setData(timestamps, snapshot.rssi)
        self.noise_curve.setData(timestamps, snapshot.noise_floor)
