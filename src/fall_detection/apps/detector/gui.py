"""Desktop controls for the native CSI detection backend; no Python inference."""

from __future__ import annotations

import json
import os
import signal
import sysconfig
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from fall_detection.apps.common.qt import qt_application

# Model IDs of the live-compatible exports. The Rust bundle loader is the
# authority on families; a model whose bundle is absent fails at start.
MODELS = (
    *(
        f"{family}-{duration}s"
        for family in ("cnn", "lstm", "gru")
        for duration in (2, 4, 6)
    ),
    "tonepool_tcn-4s",
)
DEFAULT_MODELS = ("tonepool_tcn-4s",)


def runtime_library() -> Path | None:
    """Locate native ORT binaries without importing its Python binding."""
    configured = os.environ.get("ORT_DYLIB_PATH")
    if configured:
        return Path(configured)
    for directory in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib")):
        if directory:
            candidates = sorted(
                (Path(directory) / "onnxruntime/capi").glob("libonnxruntime.so*")
            )
            if candidates:
                return candidates[-1]
    return None


def plugin_library() -> Path | None:
    """Locate the separately packaged native WebGPU provider."""
    configured = os.environ.get("ORT_WEBGPU_PLUGIN")
    if configured:
        return Path(configured)
    candidates = [
        Path(directory) / "onnxruntime_ep_webgpu/libonnxruntime_providers_webgpu.so"
        for directory in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib"))
        if directory
    ]
    return next((path for path in candidates if path.is_file()), None)


def build_config(args: Any, models: list[str] | None = None) -> dict:
    """Encode the native detector configuration; Rust owns packets and tensors.

    Args:
        args: Parsed detector arguments.
        models: Optional model selection overriding ``args.models``.

    Returns:
        JSON-serializable configuration for ``NativeDetector``.

    Raises:
        ValueError: Missing native libraries or an invalid selection or policy.
    """
    replay = getattr(args, "replay_capture", None)
    core = args.ort_library or runtime_library()
    if core is None or not core.is_file():
        raise ValueError("Set --ort-library to the native ONNX Runtime shared library")
    plugin = args.webgpu_plugin or plugin_library()
    if args.backend == "webgpu" and (plugin is None or not plugin.is_file()):
        raise ValueError(
            "Set --webgpu-plugin to the native WebGPU provider shared library"
        )
    selected = list(models or args.models)
    if (
        not selected
        or len(set(selected)) != len(selected)
        or any(model not in MODELS for model in selected)
    ):
        raise ValueError("Select a unique nonempty subset of the sequence models")
    if args.hop_ms <= 0 or args.grace_ms < 0 or not 0 <= args.minimum_coverage <= 1:
        raise ValueError("Invalid hop, grace, or coverage policy")
    output = args.output_dir or Path("data/experiments/detector") / datetime.now(
        UTC
    ).strftime("native-%Y%m%dT%H%M%S%fZ")
    config = {
        "model_root": str(args.model_root.resolve()),
        "core_library": str(core.resolve()),
        "webgpu_plugin": str(plugin.resolve()) if plugin else None,
        "backend": args.backend,
        "adapter_id": args.adapter_id,
        "models": selected,
        "output_dir": str(output.resolve()),
        "hop_ms": args.hop_ms,
        "delivery_grace_ms": args.grace_ms,
        "minimum_coverage": args.minimum_coverage,
        "packet_capacity": args.packet_capacity,
    }
    if replay:
        if args.replay_speed <= 0:
            raise ValueError("--replay-speed must be positive")
        config["replay"] = {
            "captures": [str(Path(path).resolve()) for path in replay],
            "speed": args.replay_speed,
            "repeat": args.replay_repeat,
        }
        return config
    from fall_detection.radio.settings import resolve_settings

    # Resolving first fills an omitted --gateway-port from the settings file.
    settings = resolve_settings(args)
    if not args.gateway_port:
        raise ValueError("a gateway USB port is required (--gateway-port)")
    config["serial_path"] = str(args.gateway_port)
    config["radio_config"] = settings.native_radio_config()
    return config


def _new_backend(config: dict):
    from fall_detection.radio.native import require_native

    native = require_native()
    if not hasattr(native, "NativeDetector"):
        raise RuntimeError("Rebuild the native extension to enable NativeDetector")
    return native.NativeDetector(json.dumps(config, allow_nan=False))


def run(args: Any) -> int:
    """Run the native frontend with bounded polling and unconditional shutdown."""
    config = build_config(args)
    if not args.headless:
        return _gui(args, config)
    backend = _new_backend(config)
    stopped = False

    def interrupt(*_):
        nonlocal stopped
        stopped = True

    previous = signal.signal(signal.SIGINT, interrupt)
    began = time.monotonic()
    try:
        backend.start()
        while not stopped and (
            args.duration is None or time.monotonic() - began < args.duration
        ):
            for row in json.loads(backend.poll(64)):
                print(json.dumps(row, allow_nan=False), flush=True)
            health = json.loads(backend.health())
            if health.get("error"):
                raise RuntimeError(health["error"])
            if health.get("state") == "finished":
                for row in json.loads(backend.poll(64)):
                    print(json.dumps(row, allow_nan=False), flush=True)
                break
            time.sleep(0.025)
        return 0
    finally:
        backend.stop()
        signal.signal(signal.SIGINT, previous)


def preview_images(
    raw: bytes, model_input: bytes, frames: int
) -> tuple[np.ndarray, np.ndarray]:
    """Decode one preview window into display images.

    Args:
        raw: Little-endian float32 magnitudes, ``[frames, 980]``.
        model_input: Little-endian float32 model input, ``[frames, 1964]``.
        frames: Window length in samples.

    Returns:
        Raw magnitudes and normalized model signals, both ``[frames, 980]`` in
        receiver-major tone order, with NaN wherever the sample was missing.

    Raises:
        ValueError: Buffer sizes do not match the window length.
    """
    magnitudes = np.frombuffer(raw, dtype="<f4")
    tensor = np.frombuffer(model_input, dtype="<f4")
    if magnitudes.size != frames * 980 or tensor.size != frames * 1964:
        raise ValueError("preview buffers do not match the window length")
    tensor = tensor.reshape(frames, 1964)
    signals = np.where(tensor[:, 980:1960] > 0.5, tensor[:, :980], np.nan)
    return magnitudes.reshape(frames, 980).copy(), signals


class StreamBuffer:
    """Rolling raw magnitudes ``[rounds, 980]`` indexed by sequence round.

    Rows are placed by round, so late or out-of-order receiver batches land in
    the correct column. A new generation (segment) clears the buffer.
    """

    def __init__(self, rounds: int = 1200) -> None:
        self.rounds = rounds
        self.data = np.full((rounds, 980), np.nan, dtype=np.float32)
        self.latest: int | None = None
        self.generation: int | None = None

    def add(
        self,
        generations: list[int],
        rounds: list[int],
        receivers: list[int],
        magnitudes: bytes,
    ) -> bool:
        """Insert rows from ``NativeDetector.stream``; return whether any changed.

        Args:
            generations: Segment generation of each row.
            rounds: Sequence round of each row.
            receivers: Receiver slot (0–3) of each row.
            magnitudes: Little-endian float32 ``[rows, 245]``.

        Returns:
            True when at least one row was stored.

        Raises:
            ValueError: Metadata and magnitude buffer lengths differ.
        """
        values = np.frombuffer(magnitudes, dtype="<f4")
        count = len(rounds)
        if values.size != count * 245 or not (
            len(generations) == len(receivers) == count
        ):
            raise ValueError("stream metadata does not match magnitudes")
        if count == 0:
            return False
        values = values.reshape(count, 245)
        generation = np.asarray(generations, dtype=np.int64)
        changes = np.flatnonzero(np.diff(generation)) + 1
        stored = False
        for part in np.split(np.arange(count), changes):
            if generation[part[0]] != self.generation:
                self.data.fill(np.nan)
                self.latest = None
                self.generation = int(generation[part[0]])
            stored |= self._place(
                np.asarray(rounds, dtype=np.int64)[part],
                np.asarray(receivers, dtype=np.int64)[part],
                values[part],
            )
        return stored

    def _place(self, rounds: np.ndarray, receivers: np.ndarray, values) -> bool:
        newest = int(rounds.max())
        if self.latest is None:
            self.latest = newest
        elif newest > self.latest:
            if newest - self.latest >= self.rounds:
                self.data.fill(np.nan)
            else:
                cleared = np.arange(self.latest + 1, newest + 1) % self.rounds
                self.data[cleared] = np.nan
            self.latest = newest
        keep = rounds > self.latest - self.rounds
        rows = (rounds[keep] % self.rounds)[:, None]
        columns = receivers[keep][:, None] * 245 + np.arange(245)
        self.data[rows, columns] = values[keep]
        return bool(keep.any())

    def image(self) -> np.ndarray:
        """Return rows ordered oldest to newest, ending at the latest round."""
        if self.latest is None:
            return self.data
        start = (self.latest + 1) % self.rounds
        return np.concatenate((self.data[start:], self.data[:start]))


def _status_text(health: dict) -> str:
    """Summarize backend health for the status line."""
    if health.get("error"):
        return f"Error: {health['error']}"
    parts = [f"{health.get('source', 'gateway')}: {health.get('state', 'starting')}"]
    records = health.get("records")
    if records:
        parts.append("records " + " / ".join(str(count) for count in records))
    if health.get("segments"):
        parts.append(f"segment {health['segments']}")
    if health.get("radio_error"):
        parts.append(f"last radio error: {health['radio_error']}")
    return " · ".join(parts)


def _gui(args: Any, initial_config: dict) -> int:
    app = qt_application("detector")
    import pyqtgraph as pg
    from PySide6 import QtCore, QtWidgets

    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Native live fall detection")
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    controls = QtWidgets.QHBoxLayout()
    choices = {}
    for model in MODELS:
        choice = QtWidgets.QCheckBox(model)
        choice.setChecked(model in initial_config["models"])
        choices[model] = choice
        controls.addWidget(choice)
    restart = QtWidgets.QPushButton("Apply selection / restart")
    controls.addWidget(restart)
    layout.addLayout(controls)
    status = QtWidgets.QLabel("Starting native backend…")
    layout.addWidget(status)
    columns = [
        "Model",
        "State",
        "Score",
        "Data age",
        "Coverage",
        "Backend",
        "Replaced",
        "Error",
    ]
    table = QtWidgets.QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.horizontalHeader().setSectionResizeMode(
        QtWidgets.QHeaderView.ResizeMode.Stretch
    )
    plot = pg.PlotWidget(title="Independent model score histories")
    plot.setYRange(0, 1)
    plot.setLabel("bottom", "Window center since first result", units="s")
    plot.addLegend()

    preview_panel = QtWidgets.QWidget()
    preview_layout = QtWidgets.QVBoxLayout(preview_panel)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_bar = QtWidgets.QHBoxLayout()
    preview_bar.addWidget(QtWidgets.QLabel("Preview model:"))
    preview_choice = QtWidgets.QComboBox()
    preview_bar.addWidget(preview_choice)
    preview_info = QtWidgets.QLabel("Waiting for the first window…")
    preview_bar.addWidget(preview_info, 1)
    preview_layout.addLayout(preview_bar)
    images = pg.GraphicsLayoutWidget()
    preview_layout.addWidget(images)
    receiver_ticks = [[(122.5 + 245 * r, f"rx-{r + 1}") for r in range(4)]]

    def image_plot(title, colormap, label, row, column, span, x_label):
        view = images.addPlot(row=row, col=column, colspan=span, title=title)
        item = pg.ImageItem(axisOrder="row-major")
        item.setColorMap(pg.colormap.get(colormap))
        view.addItem(item)
        view.setLabel("bottom", x_label, units="s")
        view.getAxis("left").setTicks(receiver_ticks)
        view.invertY(True)
        for boundary in (245, 490, 735):
            view.addLine(y=boundary, pen=pg.mkPen("w", width=1))
        bar = pg.ColorBarItem(colorMap=pg.colormap.get(colormap), label=label)
        bar.setImageItem(item, insert_in=view)
        return item, bar

    stream_buffer = StreamBuffer()
    stream_seconds = stream_buffer.rounds / 120
    stream_image, stream_bar = image_plot(
        "Raw CSI stream (all received packets)",
        "viridis",
        "|H|",
        0,
        0,
        2,
        "Time before latest packet",
    )
    stream_rect = QtCore.QRectF(-stream_seconds, 0, stream_seconds, 980)
    raw_image, raw_bar = image_plot(
        "Latest window: raw CSI magnitude", "viridis", "|H|", 1, 0, 1, "Time in window"
    )
    input_image, input_bar = image_plot(
        "Latest window: model input, normalized log1p(Δ²)",
        "CET-D1",
        "z",
        1,
        1,
        1,
        "Time in window",
    )
    input_bar.setLevels((-3, 3))

    splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
    splitter.addWidget(table)
    splitter.addWidget(plot)
    splitter.addWidget(preview_panel)
    splitter.setSizes([110, 200, 560])
    layout.addWidget(splitter, 1)
    window.setCentralWidget(central)
    window.resize(1400, 950)
    backend = None
    latest = {}
    histories = {}
    curves = {}
    cells = {}
    selected = []
    state = {
        "origin_ns": None,
        "preview_end_ns": 0,
        "preview_model": None,
        "stream_seq": 0,
        "levels_at": 0.0,
    }
    began = time.monotonic()
    restarts = 0

    def robust_levels(values: np.ndarray) -> tuple[float, float] | None:
        """Percentile color range estimated from a subsample of finite values."""
        sample = values.ravel()[::16]
        sample = sample[np.isfinite(sample)]
        if sample.size == 0:
            return None
        low, high = np.percentile(sample, [1, 99])
        return float(low), float(max(high, low + 1e-6))

    def set_cell(row: int, column: int, text: str) -> None:
        """Rewrite a table cell only when its text changes."""
        if cells.get((row, column)) == text:
            return
        cells[(row, column)] = text
        item = table.item(row, column)
        if item is None:
            table.setItem(row, column, QtWidgets.QTableWidgetItem(text))
        else:
            item.setText(text)

    def start(config: dict) -> None:
        nonlocal backend, selected, stream_buffer
        selected = config["models"]
        latest.clear()
        histories.clear()
        curves.clear()
        cells.clear()
        plot.clear()
        state.update(origin_ns=None, preview_end_ns=0, preview_model=None)
        state.update(stream_seq=0, levels_at=0.0)
        stream_buffer = StreamBuffer()
        preview_choice.clear()
        preview_choice.addItems(selected)
        table.clearContents()
        table.setRowCount(len(selected))
        for index, model in enumerate(selected):
            histories[model] = deque(maxlen=240)
            curves[model] = plot.plot(
                name=model, pen=pg.intColor(index, hues=max(1, len(selected)))
            )
            set_cell(index, 0, model)
        backend = _new_backend({**config, "preview": True})
        backend.start()

    def apply() -> None:
        nonlocal restarts, backend
        models = [model for model, choice in choices.items() if choice.isChecked()]
        if not models:
            status.setText("Select at least one model")
            return
        if backend is not None:
            backend.stop()
            backend = None
        restarts += 1
        config = build_config(args, models)
        if args.output_dir:
            config["output_dir"] = str(
                Path(config["output_dir"]) / f"restart-{restarts}"
            )
        try:
            start(config)
        except (RuntimeError, ValueError, OSError, KeyError) as error:
            status.setText(str(error))

    def update_stream() -> None:
        metadata, magnitudes = backend.stream(state["stream_seq"])
        metadata = json.loads(metadata)
        state["stream_seq"] = metadata["seq"]
        if not stream_buffer.add(
            metadata["generation"],
            metadata["round"],
            metadata["receiver"],
            magnitudes,
        ):
            return
        image = stream_buffer.image()
        stream_image.setImage(image.T, autoLevels=False)
        # The rectangle scales from the current image size, so set it after.
        stream_image.setRect(stream_rect)
        if time.monotonic() - state["levels_at"] > 1.0:
            levels = robust_levels(image)
            if levels:
                stream_bar.setLevels(levels)
                state["levels_at"] = time.monotonic()

    def update_preview() -> None:
        model = preview_choice.currentText()
        if not model:
            return
        if model != state["preview_model"]:
            state.update(preview_end_ns=0, preview_model=model)
        result = backend.preview(model, state["preview_end_ns"])
        if result is None:
            return
        metadata, raw, model_input = result
        metadata = json.loads(metadata)
        frames = metadata["frames"]
        magnitudes, signals = preview_images(raw, model_input, frames)
        seconds = frames / 120
        raw_image.setImage(magnitudes.T, autoLevels=False)
        raw_image.setRect(QtCore.QRectF(0, 0, seconds, 980))
        levels = robust_levels(magnitudes)
        if levels:
            raw_bar.setLevels(levels)
        input_image.setImage(signals.T, autoLevels=False)
        input_image.setRect(QtCore.QRectF(0, 0, seconds, 980))
        coverage = " / ".join(f"{100 * c:.0f}%" for c in metadata["coverage"])
        preview_info.setText(
            f"{model} · {seconds:.0f} s window · coverage {coverage} · "
            "transparent = missing sample"
        )
        state["preview_end_ns"] = metadata["end_ns"]

    def update_results() -> None:
        rows = json.loads(backend.poll(64))
        health = json.loads(backend.health())
        # Result times use the backend clock, which replay shifts.
        now = health.get("clock_ns") or time.monotonic_ns()
        for row in rows:
            model = row["model_id"]
            if model not in histories:
                continue
            latest[model] = row
            score = row.get("score")
            center = row.get("center_ns", row.get("end_ns"))
            if score is not None and center is not None:
                if state["origin_ns"] is None:
                    state["origin_ns"] = center
                histories[model].append(((center - state["origin_ns"]) / 1e9, score))
                points = histories[model]
                curves[model].setData([p[0] for p in points], [p[1] for p in points])
        status.setText(_status_text(health))
        finished = health.get("state") in ("finished", "stopped")
        for index, model in enumerate(selected):
            row = latest.get(model, {})
            score = row.get("score")
            end = row.get("end_ns")
            stale = (
                end is not None
                and now - end > (args.grace_ms + 250 + 2 * args.hop_ms) * 1_000_000
            )
            if health.get("error"):
                score = None
                label = "unknown: backend error"
            elif finished:
                label = f"{health['state']} (no new data)"
            else:
                label = "unknown: stale" if stale else row.get("state", "waiting")
            if score is not None and not stale and not finished:
                label = "fall candidate" if score >= args.threshold else "non-candidate"
            coverage = row.get("coverage")
            values = [
                label,
                "—" if score is None or stale else f"{score:.3f}",
                "—" if end is None else f"{max(0, now - end) / 1e9:.2f} s",
                "—"
                if not coverage
                else " / ".join(f"{100 * c:.0f}%" for c in coverage),
                row.get("provider", args.backend),
                str(health.get("queue_replacements", 0)),
                row.get("error") or health.get("error") or "",
            ]
            for column, value in enumerate(values, 1):
                set_cell(index, column, str(value))

    def tick() -> None:
        if backend is None:
            return
        try:
            # Poll every tick: each call is cheap when nothing is new, and a
            # coarser polling grid would show hop-spaced updates unevenly.
            update_stream()
            update_results()
            update_preview()
            if args.duration is not None and time.monotonic() - began >= args.duration:
                window.close()
        except (RuntimeError, ValueError, OSError, KeyError) as error:
            status.setText(str(error))

    restart.clicked.connect(apply)
    timer = QtCore.QTimer()
    timer.timeout.connect(tick)
    timer.start(33)
    try:
        start(initial_config)
        window.show()
        return app.exec()
    finally:
        timer.stop()
        if backend is not None:
            backend.stop()
        window.close()
