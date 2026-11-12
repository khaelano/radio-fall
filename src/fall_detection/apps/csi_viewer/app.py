"""Live CSI viewer with synchronized signal and radio diagnostics."""

from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

from fall_detection.presentation.radio.dashboard import (
    DASHBOARD_TRACE_COUNTS,
    DEFAULT_DASHBOARD_SUBCARRIERS,
    DEFAULT_INSPECT_SUBCARRIER,
    DEFAULT_VIEW_SECONDS,
    VALID_SUBCARRIERS,
)
from fall_detection.presentation.radio.live import LiveDashboard
from fall_detection.presentation.radio.pacing import (
    FPS_CHOICES as GUI_FPS_CHOICES,
)
from fall_detection.presentation.radio.pacing import (
    FPS_DEFAULT as GUI_FPS_DEFAULT,
)
from fall_detection.presentation.radio.pacing import (
    frame_interval_ms,
)
from fall_detection.radio.live import LiveRadio, add_live_arguments

GUI_INTERVAL_MS = frame_interval_ms(GUI_FPS_DEFAULT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Display live Espressif CSI data.")
    add_live_arguments(parser)
    parser.add_argument(
        "--receiver-id",
        help="receiver inventory ID to preview when multiple ESP-NOW gateway receivers are configured",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--fps",
        type=int,
        choices=GUI_FPS_CHOICES,
        default=GUI_FPS_DEFAULT,
        help="constant UI refresh rate in frames per second",
    )

    parser.add_argument(
        "--dashboard-subcarriers",
        type=int,
        choices=DASHBOARD_TRACE_COUNTS,
        default=DEFAULT_DASHBOARD_SUBCARRIERS,
        help="Number of representative physical subcarriers on the dashboard",
    )
    parser.add_argument(
        "--inspect-subcarrier",
        type=int,
        choices=VALID_SUBCARRIERS,
        default=DEFAULT_INSPECT_SUBCARRIER,
        help="Physical subcarrier shown in the detail trace",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the live GUI."""

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        radio = LiveRadio(args)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError as exc:
        print(
            "Install viewer dependencies with: uv sync --extra radio", file=sys.stderr
        )
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    profile = radio.settings.profile
    window = QtWidgets.QMainWindow()
    window.setWindowTitle(
        f"CSI viewer — {profile.profile_id} ({profile.band} ch {profile.channel})"
    )
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    dashboard = LiveDashboard(
        radio,
        fps=args.fps,
        dashboard_subcarriers=args.dashboard_subcarriers,
        inspect_subcarrier=args.inspect_subcarrier,
        window_seconds=DEFAULT_VIEW_SECONDS,
    )
    panel = dashboard.panel
    layout.addWidget(panel.widget)
    window.setCentralWidget(central)
    status_label = QtWidgets.QLabel("starting")
    status_label.setMaximumWidth(260)
    status_label.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Ignored,
        QtWidgets.QSizePolicy.Policy.Preferred,
    )
    metrics_label = QtWidgets.QLabel("Delivered records/s: waiting")
    status_bar = QtWidgets.QStatusBar()
    status_bar.addWidget(status_label, 1)
    status_bar.addPermanentWidget(metrics_label)
    window.setStatusBar(status_bar)
    window.resize(1040, 820)

    def update_status() -> None:
        text = dashboard.refresh()
        status_label.setText(text.connection)
        status_label.setToolTip(text.detail)
        metrics_label.setText(text.compact)
        metrics_label.setToolTip(text.detail)

    timer = QtCore.QTimer(window)
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    timer.timeout.connect(update_status)
    app.aboutToQuit.connect(timer.stop)
    with ExitStack() as resources:
        resources.callback(window.close)
        resources.callback(timer.stop)
        resources.callback(radio.stop)
        radio.start()
        timer.start(frame_interval_ms(args.fps))
        window.show()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
