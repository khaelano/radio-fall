"""Live CSI viewer with synchronized signal and radio diagnostics."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from threading import Lock

from ..acquisition.buffer import DEFAULT_NOMINAL_RATE_HZ, RollingCsiBuffer
from ..acquisition.espnow_serial_reader import EspNowSerialCsiReader
from ..acquisition.serial_reader import SerialCsiReader
from ..acquisition.udp_reader import UdpCsiReader
from ..acquisition.usb_reader import UsbReceiverManager
from ..profile import RadioProfileError, load_inventory_and_profile
from ..provisioning import ProvisioningError, configure_connected_devices
from .rendering import (
    DASHBOARD_TRACE_COUNTS,
    DEFAULT_DASHBOARD_SUBCARRIERS,
    DEFAULT_INSPECT_SUBCARRIER,
    PreparedCsiFrame,
    RenderGate,
    VALID_SUBCARRIERS,
    phase_column,
    prepare_frame,
    representative_subcarriers,
)


GUI_FPS_CHOICES = (16, 24)
GUI_FPS_DEFAULT = 24


def frame_interval_ms(fps: int) -> int:
    """Whole-millisecond timer interval for a constant render rate."""

    return max(1, int(1000 / fps + 0.5))


GUI_INTERVAL_MS = frame_interval_ms(GUI_FPS_DEFAULT)
HISTORY_SECONDS = 10.0
DEFAULT_VIEW_SECONDS = 3.0
PHASE_MODE_CALIBRATED = "Calibrated phase"
PHASE_MODE_CHANGE = "Phase change"
PHASE_MODE_RAW = "Raw phase (diagnostic)"


class LiveState:
    """Small synchronized state object shared by the reader and GUI threads."""

    def __init__(self, nominal_rate_hz: int = DEFAULT_NOMINAL_RATE_HZ) -> None:
        self.buffer = RollingCsiBuffer(
            nominal_rate=nominal_rate_hz,
            seconds=int(HISTORY_SECONDS),
            max_records=10_000,
        )
        self._lock = Lock()
        self.status = "starting"
        self.connected = False
        self.receiver_buffers: dict[str, RollingCsiBuffer] = {}
        self.selected_receiver_id: str | None = None

    def set_status(self, message: str, connected: bool) -> None:
        with self._lock:
            self.status = message
            self.connected = connected

    def get_status(self) -> tuple[str, bool]:
        with self._lock:
            return self.status, self.connected

    def configure_receivers(
        self,
        buffers: dict[str, RollingCsiBuffer],
        selected_receiver_id: str | None = None,
    ) -> None:
        """Register receiver buffers and select the preview stream.

        A USB hub can expose several configured receivers at once.  The
        acquisition manager keeps an independent rolling buffer per receiver;
        the viewer renders one selected stream so phase and amplitude traces
        never mix sequence or timestamp domains from different boards.
        """

        if not buffers:
            raise ValueError("at least one receiver buffer is required")
        receiver_ids = tuple(sorted(buffers))
        if selected_receiver_id is None:
            selected_receiver_id = receiver_ids[0]
        if selected_receiver_id not in buffers:
            raise ValueError(f"unknown receiver: {selected_receiver_id}")
        with self._lock:
            self.receiver_buffers = dict(buffers)
            self.selected_receiver_id = selected_receiver_id
            self.buffer = self.receiver_buffers[selected_receiver_id]

    def select_receiver(self, receiver_id: str) -> None:
        """Switch the stream rendered by the viewer."""

        with self._lock:
            try:
                self.buffer = self.receiver_buffers[receiver_id]
            except KeyError as exc:
                raise ValueError(f"unknown receiver: {receiver_id}") from exc
            self.selected_receiver_id = receiver_id


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Display live Espressif CSI data.")
    parser.add_argument(
        "--transport",
        choices=("serial", "udp", "espnow"),
        default="serial",
        help=(
            "Input transport: receiver CSV serial, UDP, or framed serial from "
            "the ESP-NOW transmitter gateway."
        ),
    )
    parser.add_argument(
        "--port",
        help=(
            "Serial device: receiver for serial transport or transmitter "
            "gateway for ESP-NOW transport"
        ),
    )
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument(
        "--listen-host",
        default="0.0.0.0",
        help="UDP bind address when --transport udp is selected",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=5500,
        help="UDP listen port when --transport udp is selected",
    )
    parser.add_argument(
        "--receiver-mac",
        help="Optional receiver MAC filter for binary UDP or ESP-NOW input",
    )
    parser.add_argument("--receiver-config", type=Path)
    parser.add_argument("--radio-profile", type=Path)
    parser.add_argument(
        "--receiver-id",
        help="receiver inventory ID to preview when multiple USB receivers are configured",
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
        "--nominal-rate-hz",
        type=int,
        default=DEFAULT_NOMINAL_RATE_HZ,
        help="configured sensing transmission rate used for history sizing",
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

    args = _parser().parse_args(argv)
    if bool(args.receiver_config) != bool(args.radio_profile):
        _parser().error("--receiver-config and --radio-profile must be provided together")
    inventory = profile = None
    profile_fingerprint = None
    if args.receiver_config is not None:
        try:
            inventory, profile, profile_fingerprint = load_inventory_and_profile(
                args.receiver_config, args.radio_profile
            )
        except RadioProfileError as exc:
            _parser().error(str(exc))
    profile_mode = inventory is not None
    if not profile_mode:
        _parser().error(
            "--receiver-config and --radio-profile are required for csi-viewer"
        )
    if args.receiver_id is not None and not profile_mode:
        _parser().error("--receiver-id requires --receiver-config and --radio-profile")
    if args.receiver_id is not None:
        receiver_ids = {receiver.id for receiver in inventory.receivers}
        if args.receiver_id not in receiver_ids:
            _parser().error(
                "--receiver-id must match one of the configured receivers: "
                + ", ".join(sorted(receiver_ids))
            )
    if args.nominal_rate_hz < 1:
        _parser().error("--nominal-rate-hz must be at least 1")
    if not profile_mode and args.transport in ("serial", "espnow") and not args.port:
        _parser().error(
            f"--port is required when --transport {args.transport} is selected"
        )
    if not profile_mode and args.transport == "udp" and args.port:
        _parser().error("--port cannot be used with --transport udp")
    try:
        import numpy as np
        from PySide6 import QtCore, QtWidgets
        import pyqtgraph as pg
    except ImportError as exc:
        print("Install processor dependencies with: uv sync", file=sys.stderr)
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")

    app = QtWidgets.QApplication(sys.argv)
    state = LiveState(profile.nominal_rate_hz if profile_mode else args.nominal_rate_hz)
    usb_bindings = ()
    if profile_mode:
        # Configure whatever is plugged in before binding, so a band or channel
        # change is just another viewer launch instead of a separate command.
        try:
            reconfigured = configure_connected_devices(inventory, profile)
        except ProvisioningError as exc:
            print(f"Unable to configure connected boards: {exc}", file=sys.stderr)
            return 2
        if reconfigured:
            print(f"configured {len(reconfigured)} board(s) for {profile.profile_id}")
        reader = UsbReceiverManager(
            inventory,
            profile,
            args.output_dir,
            on_status=state.set_status,
        )
        try:
            usb_bindings = reader.bind()
        except RuntimeError as exc:
            print(f"Unable to bind configured USB receivers: {exc}", file=sys.stderr)
            return 2
        state.configure_receivers(
            {
                receiver_id: usb_reader.buffer
                for receiver_id, usb_reader in reader.readers.items()
            },
            args.receiver_id,
        )
    elif args.transport == "udp":
        reader = UdpCsiReader(
            args.listen_host,
            args.listen_port,
            state.buffer,
            args.output_dir,
            receiver_mac=args.receiver_mac,
            on_status=state.set_status,
        )
    elif args.transport == "espnow":
        reader = EspNowSerialCsiReader(
            args.port,
            args.baud,
            state.buffer,
            args.output_dir,
            receiver_mac=args.receiver_mac,
            on_status=state.set_status,
        )
    else:
        reader = SerialCsiReader(
            args.port,
            args.baud,
            state.buffer,
            args.output_dir,
            on_status=state.set_status,
        )

    window = QtWidgets.QMainWindow()
    window.setWindowTitle(
        "Espressif CSI live viewer"
        if not profile_mode
        else f"CSI viewer — {profile.profile_id} ({profile.band} ch {profile.channel})"
    )
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    controls = QtWidgets.QHBoxLayout()
    status_label = QtWidgets.QLabel("starting")
    status_label.setMaximumWidth(260)
    status_label.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Ignored,
        QtWidgets.QSizePolicy.Policy.Preferred,
    )
    metrics_label = QtWidgets.QLabel(
        "seq — | rec 0 | bad 0 | sense 0 | record 0 | batch 0 | drops 0/0/0 | age —"
    )

    trace_count_combo = QtWidgets.QComboBox()
    for count in DASHBOARD_TRACE_COUNTS:
        trace_count_combo.addItem(str(count), count)
    trace_count_combo.setCurrentIndex(
        DASHBOARD_TRACE_COUNTS.index(args.dashboard_subcarriers)
    )

    inspect_combo = QtWidgets.QComboBox()
    for subcarrier in VALID_SUBCARRIERS:
        inspect_combo.addItem(f"{subcarrier:+d}", subcarrier)
    inspect_combo.setCurrentIndex(VALID_SUBCARRIERS.index(args.inspect_subcarrier))

    window_spin = QtWidgets.QDoubleSpinBox()
    window_spin.setRange(1.0, HISTORY_SECONDS)
    window_spin.setSingleStep(0.5)
    window_spin.setSuffix(" s")
    window_spin.setValue(DEFAULT_VIEW_SECONDS)
    phase_mode_combo = QtWidgets.QComboBox()
    phase_mode_combo.addItems(
        [PHASE_MODE_CALIBRATED, PHASE_MODE_CHANGE, PHASE_MODE_RAW]
    )
    receiver_combo = None
    if profile_mode:
        receiver_combo = QtWidgets.QComboBox()
        for binding in usb_bindings:
            receiver_combo.addItem(binding.receiver_id, binding.receiver_id)
        receiver_combo.setCurrentIndex(
            max(0, receiver_combo.findData(state.selected_receiver_id))
        )
        controls.addWidget(QtWidgets.QLabel("receiver"))
        controls.addWidget(receiver_combo)
    controls.addWidget(QtWidgets.QLabel("dashboard traces"))
    controls.addWidget(trace_count_combo)
    controls.addWidget(QtWidgets.QLabel("inspect k"))
    controls.addWidget(inspect_combo)
    controls.addWidget(QtWidgets.QLabel("window"))
    controls.addWidget(window_spin)
    controls.addWidget(QtWidgets.QLabel("phase"))
    controls.addWidget(phase_mode_combo)
    controls.addStretch()
    layout.addLayout(controls)

    plot_canvas = pg.GraphicsLayoutWidget()

    def make_plot(title: str, ylabel: str, row: int, column: int) -> object:
        chart = plot_canvas.addPlot(row=row, col=column)
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

    amplitude_plot = make_plot("Amplitude", "value", 0, 0)
    phase_plot = make_plot("Phase", "radians", 0, 1)
    iq_plot = make_plot("Mean I / Q", "sample", 1, 0)
    radio_plot = make_plot("Radio", "dBm", 1, 1)
    iq_plot.setYRange(-128.0, 128.0, padding=0)
    radio_plot.setYRange(-120.0, 0.0, padding=0)
    amplitude_plot.setYRange(0.0, 200.0, padding=0)
    phase_plot.setYRange(-3.2, 3.2, padding=0)

    amplitude_curves: list[object] = []
    phase_curves: list[object] = []
    curve_keys: list[int | None] = []
    for index in range(max(DASHBOARD_TRACE_COUNTS)):
        pen = pg.mkPen(
            pg.intColor(index, hues=max(DASHBOARD_TRACE_COUNTS)),
            width=1,
        )
        amplitude_curves.append(amplitude_plot.plot(pen=pen))
        phase_curves.append(phase_plot.plot(pen=pen))
        curve_keys.append(None)

    iq_plot.addLegend()
    iq_curves = (
        iq_plot.plot(pen=pg.mkPen("#f28e2b", width=2), name="mean I"),
        iq_plot.plot(
            pen=pg.mkPen(
                "#59a14f", width=2, style=QtCore.Qt.PenStyle.DashLine
            ),
            name="mean Q",
        ),
    )
    radio_plot.addLegend()
    radio_curves = (
        radio_plot.plot(pen=pg.mkPen("#e15759", width=2), name="RSSI"),
        radio_plot.plot(pen=pg.mkPen("#4e79a7", width=2), name="noise"),
    )
    plots = (amplitude_plot, phase_plot, iq_plot, radio_plot)

    tabs = QtWidgets.QTabWidget()
    dashboard_tab = QtWidgets.QWidget()
    dashboard_layout = QtWidgets.QVBoxLayout(dashboard_tab)
    dashboard_layout.setContentsMargins(0, 0, 0, 0)
    dashboard_layout.addWidget(plot_canvas)
    tabs.addTab(dashboard_tab, "Dashboard")

    phase_detail_canvas = pg.GraphicsLayoutWidget()
    phase_detail_plot = phase_detail_canvas.addPlot(row=0, col=0)
    phase_detail_plot.setTitle("Phase heatmap")
    phase_detail_plot.setLabel("left", "subcarrier k")
    phase_detail_plot.setLabel("bottom", "time", units="s")
    phase_detail_plot.setXRange(-DEFAULT_VIEW_SECONDS, 0.0, padding=0)
    phase_detail_plot.setYRange(-32.0, 31.0, padding=0)
    phase_detail_plot.setLimits(xMin=-HISTORY_SECONDS, xMax=0.0)
    phase_detail_plot.getViewBox().setMouseEnabled(x=False, y=False)
    phase_detail_plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
    phase_detail_plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
    phase_detail_plot.showGrid(x=True, y=False, alpha=0.15)
    phase_image = pg.ImageItem(axisOrder="row-major")
    phase_image.setColorMap(pg.colormap.get("CET-C7"))
    phase_detail_plot.addItem(phase_image)
    phase_color_bar = pg.ColorBarItem(
        values=(-np.pi, np.pi),
        colorMap=pg.colormap.get("CET-C7"),
        label="phase",
    )
    phase_color_bar.setImageItem(phase_image)
    phase_detail_canvas.addItem(phase_color_bar, row=0, col=1)

    phase_trace_plot = phase_detail_canvas.addPlot(row=1, col=0, colspan=2)
    phase_trace_plot.setTitle("Selected phase")
    phase_trace_plot.setLabel("left", "radians")
    phase_trace_plot.setLabel("bottom", "time", units="s")
    phase_trace_plot.setXRange(-DEFAULT_VIEW_SECONDS, 0.0, padding=0)
    phase_trace_plot.setYRange(-3.2, 3.2, padding=0)
    phase_trace_plot.setLimits(xMin=-HISTORY_SECONDS, xMax=0.0)
    phase_trace_plot.getViewBox().setMouseEnabled(x=False, y=True)
    phase_trace_plot.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
    phase_trace_plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
    phase_trace_plot.showGrid(x=True, y=True, alpha=0.2)
    phase_trace_curve = phase_trace_plot.plot(
        pen=pg.mkPen("#4e79a7", width=1),
    )

    phase_detail_tab = QtWidgets.QWidget()
    phase_detail_layout = QtWidgets.QVBoxLayout(phase_detail_tab)
    phase_detail_layout.setContentsMargins(0, 0, 0, 0)
    phase_detail_layout.addWidget(phase_detail_canvas)
    tabs.addTab(phase_detail_tab, "Phase by subcarrier")
    layout.addWidget(tabs)
    window.setCentralWidget(central)
    status_bar = QtWidgets.QStatusBar()
    status_bar.addWidget(status_label, 1)
    status_bar.addPermanentWidget(metrics_label)
    window.setStatusBar(status_bar)
    window.resize(800, 680)

    frame_count = 0
    frame_started = time.perf_counter()
    measured_fps = 0.0
    phase_gap_count = 0
    config_version = 0
    render_gate = RenderGate(view_count=2)

    def mark_dirty() -> None:
        nonlocal config_version
        config_version += 1

    def tab_changed(_index: int) -> None:
        mark_dirty()

    tabs.currentChanged.connect(tab_changed)

    if receiver_combo is not None:

        def receiver_changed(_index: int) -> None:
            receiver_id = receiver_combo.currentData()
            if receiver_id is not None:
                state.select_receiver(str(receiver_id))
                mark_dirty()

        receiver_combo.currentIndexChanged.connect(receiver_changed)

    def update_dashboard(frame: PreparedCsiFrame) -> None:
        nonlocal phase_gap_count
        selected = representative_subcarriers(
            int(trace_count_combo.currentData()),
            frame.subcarriers,
        )
        phase_gap_count = (
            int(np.count_nonzero(~np.isfinite(frame.selected_phases)))
            if frame.selected_phases.size
            else 0
        )
        for index, (amplitude_curve, phase_curve) in enumerate(
            zip(amplitude_curves, phase_curves)
        ):
            if index >= len(selected) or not frame.timestamps.size:
                amplitude_curve.setVisible(False)
                phase_curve.setVisible(False)
                continue
            subcarrier = selected[index]
            column = frame.subcarriers.index(subcarrier)
            if curve_keys[index] != subcarrier:
                pen = pg.mkPen(
                    pg.intColor(
                        VALID_SUBCARRIERS.index(subcarrier),
                        hues=len(VALID_SUBCARRIERS),
                    ),
                    width=1,
                )
                amplitude_curve.setPen(pen)
                phase_curve.setPen(pen)
                curve_keys[index] = subcarrier
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

        iq_curves[0].setData(
            frame.timestamps, frame.mean_i, skipFiniteCheck=False
        )
        iq_curves[1].setData(
            frame.timestamps, frame.mean_q, skipFiniteCheck=False
        )
        radio_curves[0].setData(
            frame.timestamps, frame.rssi, skipFiniteCheck=False
        )
        radio_curves[1].setData(
            frame.timestamps, frame.noise_floor, skipFiniteCheck=False
        )

    def update_detail(frame: PreparedCsiFrame) -> None:
        nonlocal phase_gap_count
        phase_gap_count = (
            int(np.count_nonzero(~np.isfinite(frame.selected_phases)))
            if frame.selected_phases.size
            else 0
        )
        if not frame.timestamps.size or not frame.subcarriers:
            phase_image.setVisible(False)
            phase_trace_curve.setData([], [])
            phase_detail_plot.setTitle("Phase heatmap — waiting for HT-LTF data")
            return

        phase_image.setVisible(True)
        phase_image.setImage(
            frame.selected_phases.T,
            autoLevels=False,
            levels=(-np.pi, np.pi),
        )
        image_width = max(float(frame.timestamps[-1] - frame.timestamps[0]), 1e-6)
        image_height = max(float(len(frame.subcarriers) - 1), 1.0)
        phase_image.setRect(
            QtCore.QRectF(
                float(frame.timestamps[0]),
                float(frame.subcarriers[0]),
                image_width,
                image_height,
            )
        )
        inspected = int(inspect_combo.currentData())
        phase_trace_curve.setData(
            frame.timestamps,
            phase_column(frame, inspected),
            skipFiniteCheck=False,
        )
        phase_detail_plot.setTitle(
            f"Phase heatmap ({phase_mode_combo.currentText()})"
        )
        phase_trace_plot.setTitle(f"Selected phase k={inspected:+d}")

    def redraw() -> None:
        nonlocal frame_count, frame_started, measured_fps

        active_tab = tabs.currentIndex()
        latest_sequence = state.buffer.last_sequence
        if not render_gate.needs_render(
            active_tab,
            latest_sequence,
            config_version,
        ):
            return

        snapshot = state.buffer.snapshot(0, None, seconds=window_spin.value())
        frame = prepare_frame(
            snapshot,
            phase_mode=phase_mode_combo.currentText(),
            phase_mode_change=PHASE_MODE_CHANGE,
            phase_mode_raw=PHASE_MODE_RAW,
            window_seconds=window_spin.value(),
        )
        if active_tab == 0:
            update_dashboard(frame)
        else:
            update_detail(frame)
        render_gate.mark_rendered(active_tab, frame.sequence, config_version)

        frame_count += 1
        now = time.perf_counter()
        elapsed = now - frame_started
        if elapsed >= 1.0:
            measured_fps = frame_count / elapsed
            frame_count = 0
            frame_started = now

    def update_status() -> None:
        message, connected = state.get_status()
        selected_reader = reader
        if profile_mode:
            selected_reader = reader.readers[state.selected_receiver_id]
            connected = selected_reader.connected and not selected_reader.profile_mismatch
            message = f"{state.selected_receiver_id}: {message}"
        status = message if connected else f"offline: {message}"
        status_label.setText(status if len(status) <= 42 else f"{status[:41]}…")
        status_label.setToolTip(status)
        sequence = state.buffer.last_sequence
        if selected_reader.last_valid_time is None:
            age = "—"
        else:
            age = f"{max(0.0, time.monotonic() - selected_reader.last_valid_time):.1f}s"
        record_missing = getattr(selected_reader, "transport_missing", 0)
        batch_missing = getattr(selected_reader, "batch_missing", 0)
        receiver_stats = getattr(selected_reader, "receiver_stats", None)
        sensing_missing = (
            receiver_stats.sensing_missing
            if receiver_stats is not None
            else "—"
        )
        queue_drops = receiver_stats.queue_drops if receiver_stats is not None else "—"
        ip_drops = (
            receiver_stats.unavailable_ip_drops
            if receiver_stats is not None
            else "—"
        )
        send_errors = receiver_stats.send_errors if receiver_stats is not None else "—"
        receiver_label = (
            f"  |  receiver {state.selected_receiver_id}"
            if profile_mode
            else ""
        )
        metrics_label.setText(
            f"seq {sequence if sequence is not None else '—'}  |  "
            f"rec {state.buffer.received_records}  |  "
            f"bad {getattr(selected_reader, 'malformed_lines', 0)}  |  "
            f"sense {sensing_missing}  |  record {record_missing}  |  "
            f"batch {batch_missing}  |  drops {queue_drops}/{ip_drops}/{send_errors}"
            f"  |  age {age}"
            f"{receiver_label}"
            f"  |  {measured_fps:.0f} data fps  |  ui {args.fps} fps"
            f"  |  {phase_mode_combo.currentText()}"
            f"  |  phase gaps {phase_gap_count}"
        )

    timer = QtCore.QTimer()
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    timer.timeout.connect(redraw)
    timer.start(frame_interval_ms(args.fps))

    status_timer = QtCore.QTimer()
    status_timer.timeout.connect(update_status)
    status_timer.start(250)

    def set_time_range(seconds: float) -> None:
        for plot in plots:
            plot.setXRange(-seconds, 0.0, padding=0)
        phase_detail_plot.setXRange(-seconds, 0.0, padding=0)
        phase_trace_plot.setXRange(-seconds, 0.0, padding=0)
        mark_dirty()

    window_spin.valueChanged.connect(set_time_range)
    trace_count_combo.currentIndexChanged.connect(lambda _index: mark_dirty())
    inspect_combo.currentIndexChanged.connect(lambda _index: mark_dirty())
    phase_mode_combo.currentIndexChanged.connect(lambda _index: mark_dirty())

    def close() -> None:
        reader.stop()

    app.aboutToQuit.connect(close)
    reader.start()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
