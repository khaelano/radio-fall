"""Headless rendering benchmark for the CSI viewer's two view shapes."""

from __future__ import annotations

import argparse
import json
import time

import numpy as np


def _paint(widget: object, target: object, QtGui: object) -> None:
    target.fill(0)
    painter = QtGui.QPainter(target)
    widget.render(painter)
    painter.end()


def _control_refresh_benchmark(*, frames: int, points: int) -> dict[str, float | int]:
    """Measure display refresh work for unchanged data, excluding paint and RF."""
    from ..acquisition.protocol import CsiRecord
    from .dashboard import CsiDashboardPanel
    from .state import LiveState

    state = LiveState(120)
    csi = tuple(complex(4 + k % 9, 2 + k % 7) for k in range(256))
    for sequence in range(points):
        state.buffer.append(
            CsiRecord(
                sequence,
                "02:00:00:00:00:01",
                -40,
                -95,
                sequence * 8333,
                csi,
                sig_mode=4,
                bandwidth=0,
                csi_length=512,
            )
        )
    snapshot_calls = 0
    original = state.buffer.snapshot

    def snapshot(*args, **kwargs):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original(*args, **kwargs)

    state.buffer.snapshot = snapshot
    panel = CsiDashboardPanel(state, fps=24)
    timings = []
    try:
        # Cold phase preparation is deliberately spread across bounded GUI ticks.
        for _ in range(points + 1):
            if panel.refresh():
                break
        else:
            raise RuntimeError("preview warmup did not complete")
        for _ in range(frames):
            panel.mark_dirty()
            started = time.perf_counter()
            panel.refresh()
            timings.append((time.perf_counter() - started) * 1000)
    finally:
        panel.widget.close()
    return {
        "median_ms": float(np.median(timings)),
        "p95_ms": float(np.percentile(timings, 95)),
        "frames": frames,
        "snapshot_calls_including_warmup": snapshot_calls,
    }


def _dashboard_benchmark(
    pg: object,
    QtGui: object,
    QtWidgets: object,
    *,
    frames: int,
    points: int,
    channels: int,
) -> tuple[float, float, int]:
    widget = pg.GraphicsLayoutWidget()
    widget.resize(800, 680)
    plots = [widget.addPlot(row=index // 2, col=index % 2) for index in range(4)]
    for plot in plots:
        plot.setXRange(-3.0, 0.0, padding=0)
        plot.setYRange(-3.0, 3.0, padding=0)
        plot.enableAutoRange(False)
        plot.setClipToView(True)
        plot.setDownsampling(auto=True, mode="peak")
    curves = [
        plot.plot(pen=pg.mkPen(pg.intColor(index, hues=max(channels, 16))))
        for plot in plots[:2]
        for index in range(channels)
    ]
    curves.extend(plot.plot() for plot in plots[2:] for _ in range(2))
    x = np.linspace(-3.0, 0.0, points)
    values = np.random.default_rng(7).normal(size=(len(curves), points))
    values = values.cumsum(axis=1) / 20.0
    target = QtGui.QImage(widget.size(), QtGui.QImage.Format.Format_ARGB32)
    widget.show()
    QtWidgets.QApplication.processEvents()
    timings: list[float] = []
    for frame in range(frames):
        started = time.perf_counter()
        for curve, values_row in zip(curves, values):
            curve.setData(
                x,
                values_row + frame * 0.0001,
                skipFiniteCheck=True,
            )
        _paint(widget, target, QtGui)
        QtWidgets.QApplication.processEvents()
        timings.append(time.perf_counter() - started)
    widget.close()
    elapsed = sum(timings)
    return frames / elapsed, float(np.percentile(timings, 95) * 1000), len(curves)


def _detail_benchmark(
    pg: object,
    QtGui: object,
    QtWidgets: object,
    *,
    frames: int,
    points: int,
) -> tuple[float, float, int]:
    widget = pg.GraphicsLayoutWidget()
    widget.resize(800, 680)
    heat_plot = widget.addPlot(row=0, col=0)
    heat_plot.setXRange(-3.0, 0.0, padding=0)
    heat_plot.setYRange(-32.0, 31.0, padding=0)
    heat_plot.enableAutoRange(False)
    image = pg.ImageItem(axisOrder="row-major")
    image.setColorMap(pg.colormap.get("CET-C7"))
    heat_plot.addItem(image)
    color_bar = pg.ColorBarItem(
        values=(-np.pi, np.pi),
        colorMap=pg.colormap.get("CET-C7"),
        label="phase",
    )
    color_bar.setImageItem(image)
    widget.addItem(color_bar, row=0, col=1)
    trace_plot = widget.addPlot(row=1, col=0, colspan=2)
    trace_plot.setXRange(-3.0, 0.0, padding=0)
    trace_plot.setYRange(-3.2, 3.2, padding=0)
    trace_plot.enableAutoRange(False)
    trace = trace_plot.plot(pen=pg.mkPen("#4e79a7", width=1))
    x = np.linspace(-3.0, 0.0, points)
    values = (
        np.random.default_rng(11)
        .uniform(-np.pi, np.pi, size=(64, points))
        .astype(np.float32)
    )
    target = QtGui.QImage(widget.size(), QtGui.QImage.Format.Format_ARGB32)
    widget.show()
    QtWidgets.QApplication.processEvents()
    timings: list[float] = []
    for frame in range(frames):
        started = time.perf_counter()
        image.setImage(
            values + frame * 0.0001,
            autoLevels=False,
            levels=(-np.pi, np.pi),
        )
        trace.setData(x, values[33], skipFiniteCheck=True)
        _paint(widget, target, QtGui)
        QtWidgets.QApplication.processEvents()
        timings.append(time.perf_counter() - started)
    widget.close()
    elapsed = sum(timings)
    return frames / elapsed, float(np.percentile(timings, 95) * 1000), 3


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark and print throughput and p95 frame time."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--view", choices=("dashboard", "detail", "both", "controls"), default="both"
    )
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--points", type=int, default=300)
    args = parser.parse_args(argv)
    if args.frames < 1 or args.points < 1:
        parser.error("frames and points must be positive")

    from PySide6 import QtGui, QtWidgets
    import pyqtgraph as pg

    pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    del app
    if args.view == "controls":
        print(
            json.dumps(
                _control_refresh_benchmark(frames=args.frames, points=args.points)
            )
        )
        return 0
    views = ("dashboard", "detail") if args.view == "both" else (args.view,)
    for view in views:
        if view == "dashboard":
            fps, p95, items = _dashboard_benchmark(
                pg,
                QtGui,
                QtWidgets,
                frames=args.frames,
                points=args.points,
                channels=12,
            )
        else:
            fps, p95, items = _detail_benchmark(
                pg,
                QtGui,
                QtWidgets,
                frames=args.frames,
                points=args.points,
            )
        print(f"{view}: {fps:.1f} FPS, p95 {p95:.2f} ms, {items} graphics items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
