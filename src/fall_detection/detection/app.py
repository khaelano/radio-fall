"""Separate live fall-score program with native preprocessing and isolated inference."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
import time

from ..radio.live import LiveRadio, add_live_arguments
from .engine import DetectorEngine
from .model import ModelBundle, export_bundle


def parser() -> argparse.ArgumentParser:
    """Expose model export, deterministic replay and GUI/headless live modes."""
    result = argparse.ArgumentParser(description=__doc__)
    add_live_arguments(result)
    result.add_argument(
        "--model", type=Path, default=Path("data/models/phase_random20_v1")
    )
    phase_default = Path("data/experiments/phase_models_v1/20261104T081805521126Z")
    result.add_argument(
        "--phase-models", type=Path, default=phase_default if phase_default.is_dir() else None,
        help="Trusted directory containing 2s/4s/6s phase model files",
    )
    result.add_argument("--no-phase-models", action="store_true",
                        help="Disable experimental phase-model scores")
    result.add_argument("--phase-hop-ms", type=int, default=2000)
    result.add_argument("--export-model", type=Path, metavar="NEW_DIRECTORY")
    result.add_argument(
        "--experiment",
        type=Path,
        default=Path("notebooks/trash/06_phase_shifted/artifacts/phase_random20_v1"),
    )
    result.add_argument("--scheme", choices=["fixed", "shift_augmented", "random20"])
    result.add_argument("--replay-session", type=Path)
    result.add_argument("--attempt", help="closed trial/attempt, such as 192/01")
    result.add_argument("--offset", type=float, default=0.0)
    result.add_argument("--headless", action="store_true")
    result.add_argument(
        "--duration", type=float, help="stop live acquisition after this many seconds"
    )
    result.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    result.add_argument("--inference-threads", type=int, choices=range(1, 5), default=2)
    result.add_argument("--kernel", choices=["auto", "scalar", "avx2"], default="auto")
    result.add_argument("--hop-ms", type=int, default=250)
    result.add_argument("--grace-ms", type=int, default=900)
    result.add_argument("--output-dir", type=Path)
    return result


def _gui(args, radio, engine, tick) -> int:
    from PySide6 import QtCore, QtWidgets
    import pyqtgraph as pg
    from ..radio.visualization.transport_status import GatewayStatusPanel

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Live fall score · Four receivers")
    central = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(central)
    title = QtWidgets.QLabel("Waiting for four receivers and a complete window")
    title.setStyleSheet("font-size: 25px; font-weight: 600; padding: 12px;")
    layout.addWidget(title)
    score = QtWidgets.QProgressBar()
    score.setRange(0, 1000)
    score.setFormat("Waiting for data")
    layout.addWidget(score)
    note = QtWidgets.QLabel(
        "Experimental model · Scores may reflect recording setup · Live detection accuracy is unverified"
    )
    note.setWordWrap(True)
    layout.addWidget(note)
    coverage = QtWidgets.QLabel("Coverage: waiting")
    layout.addWidget(coverage)
    phase_engine = getattr(engine, "phase_engine", None)
    phase_rows = {}
    if phase_engine is not None:
        phase_title = QtWidgets.QLabel(
            "Experimental phase scores at window center by receiver · rolling-window approximation · not fall scores"
        )
        phase_title.setWordWrap(True)
        layout.addWidget(phase_title)
        phase_table = QtWidgets.QTableWidget(0, 7)
        phase_table.setHorizontalHeaderLabels(
            ["Receiver", "Window", "Model", "Preparation", "Action", "Resting", "Coverage"]
        )
        phase_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        phase_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for receiver in phase_engine.receivers.values():
            for duration in (2, 4, 6):
                for model in ("cnn", "lstm", "gru", "random_forest"):
                    row = phase_table.rowCount()
                    phase_table.insertRow(row)
                    phase_rows[(receiver, duration, model)] = row
                    for col, value in enumerate((receiver, f"{duration} s", model, "—", "—", "—", "—")):
                        phase_table.setItem(row, col, QtWidgets.QTableWidgetItem(value))
        phase_table.setMinimumHeight(220)
        layout.addWidget(phase_table)
    transport = GatewayStatusPanel()
    layout.addWidget(transport.widget)
    plot = pg.PlotWidget(title="Fall score over completed windows")
    plot.setYRange(0, 1)
    plot.setLabel("left", "Ensemble fall score")
    plot.setLabel("bottom", "Seconds since start")
    plot.addItem(
        pg.InfiniteLine(
            pos=engine.bundle.metadata["threshold"],
            angle=0,
            pen=pg.mkPen("#eab308", style=QtCore.Qt.PenStyle.DashLine),
        )
    )
    curve = plot.plot(pen=pg.mkPen("#3b82f6", width=2))
    layout.addWidget(plot)
    diagnostics = QtWidgets.QLabel()
    layout.addWidget(diagnostics)
    window.setCentralWidget(central)
    window.resize(1000, 700)
    timer = QtCore.QTimer(window)
    times, scores = [], []
    began = time.monotonic()

    def refresh():
        try:
            events = tick()
            state = engine.status()
            prediction, quality = state["prediction"], state["quality"]
            transport.apply(
                radio.manager.diagnostics(),
                selected_receiver_id=None,
                plot_refresh_fps=10.0,
                ui_fps=10,
            )
            if phase_engine is not None:
                phase_state = phase_engine.status(
                    radio_ready=radio.manager.preflight_ready and not radio.manager.failure
                )
                for row in phase_rows.values():
                    for column in range(3, 7):
                        phase_table.item(row, column).setText("—")
                for item in phase_state["models"]:
                    row = phase_rows[(item["receiver"], item["duration_seconds"], item["model"])]
                    probabilities = item["probabilities"]
                    missing = item.get("absent_training_classes", [])
                    phase_table.item(row, 2).setText(item["model"] + (" *" if missing else ""))
                    phase_table.item(row, 2).setToolTip(
                        "Absent training classes: " + ", ".join(missing) if missing else ""
                    )
                    for column, label in enumerate(("preparation", "action", "resting"), 3):
                        phase_table.item(row, column).setText(
                            f"{probabilities[label]:.3f}" if probabilities is not None else "insufficient data"
                        )
                    phase_table.item(row, 6).setText(f"{item['coverage']:.1%}")
                if phase_state["failure"]:
                    phase_title.setText(f"Experimental phase scores unavailable: {phase_state['failure']}")
                else:
                    phase_title.setText(
                        "Experimental phase scores at window center · rolling-window approximation"
                        f" · not fall scores · * missing training classes · queued {phase_state.get('pending', 0)}"
                        f" · dropped {phase_state.get('dropped', 0)}"
                    )
            if prediction:
                probability = prediction["probability"]
                title.setText(
                    "Fall candidate"
                    if prediction["candidate"]
                    else "No fall candidate in current window"
                )
                title.setStyleSheet(
                    f"font-size: 25px; font-weight: 600; padding: 12px; color: {'#dc2626' if prediction['candidate'] else '#2563eb'};"
                )
                score.setValue(round(probability * 1000))
                score.setFormat(f"Fall score {probability:.3f}")
            else:
                title.setText(
                    state["failure"]
                    or (
                        "Insufficient data"
                        if quality and not quality["valid"]
                        else "Waiting for fresh aligned data and score"
                    )
                )
                title.setStyleSheet(
                    "font-size: 25px; font-weight: 600; padding: 12px; color: #a16207;"
                )
                score.setValue(0)
                score.setFormat("Unknown")
            if quality:
                coverage.setText(
                    "Phase-change support: "
                    + " · ".join(
                        f"{rx}: {value:.1%}"
                        for rx, value in zip(
                            engine.bundle.metadata["receivers"],
                            quality["phase_change_coverage"],
                            strict=True,
                        )
                    )
                )
            for event in events:
                if event["kind"] == "prediction":
                    times.append((event["emitted_ns"] / 1e9) - began)
                    scores.append(event["probability"])
            while len(times) > 240:
                times.pop(0)
                scores.pop(0)
            curve.setData(times, scores)
            native = state["native"]
            diagnostics.setText(
                f"Rust {native['kernel']} · queued {native['pending']} · overflow {native['overflow']} · skipped scorer windows {state['skipped_inference']}"
            )
            if args.duration and time.monotonic() - began >= args.duration:
                app.quit()
        except Exception as exc:
            title.setText(f"Stopped: {exc}")
            app.exit(1)

    timer.timeout.connect(refresh)
    app.aboutToQuit.connect(timer.stop)
    timer.start(100)
    window.show()
    try:
        return app.exec()
    finally:
        timer.stop()
        window.close()


def main(argv: list[str] | None = None) -> int:
    """Run model export/replay or a separate live detector application."""
    cli = parser()
    args = cli.parse_args(argv)
    if args.duration is not None and args.duration <= 0:
        cli.error("--duration must be positive")
    if args.replay_session and not args.attempt:
        cli.error("--replay-session requires --attempt")
    if args.phase_hop_ms <= 0:
        cli.error("--phase-hop-ms must be positive")
    try:
        if args.export_model:
            bundle = export_bundle(args.experiment, args.export_model, args.scheme)
            print(f"Exported verified model to {bundle.directory}")
            return 0
        bundle = ModelBundle.load(args.model)
        if args.replay_session:
            from .replay import replay

            print(
                json.dumps(
                    replay(
                        bundle,
                        args.replay_session,
                        args.attempt,
                        args.offset,
                        kernel=args.kernel,
                        workers=args.workers,
                        threads=args.inference_threads,
                    ),
                    allow_nan=False,
                )
            )
            return 0
        if not args.headless:
            # Resolve GUI dependencies before opening acquisition hardware.
            import PySide6  # noqa: F401
            import pyqtgraph  # noqa: F401
        args.output_dir = (
            args.output_dir
            or Path("data/experiments/detector")
            / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ).resolve()
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise ValueError("Choose a new empty --output-dir for live journals")
        with ExitStack() as resources:
            engine = DetectorEngine(
                bundle,
                workers=args.workers,
                threads=args.inference_threads,
                hop_ms=args.hop_ms,
                grace_ms=args.grace_ms,
                kernel=args.kernel,
            )
            resources.callback(engine.close)
            phase_engine = None
            if args.phase_models and not args.no_phase_models:
                from .phase_models import PhaseModelEngine
                phase_engine = PhaseModelEngine(
                    args.phase_models, bundle.metadata["radio"], bundle.metadata["receivers"],
                    threads=args.inference_threads, grace_ms=args.grace_ms, hop_ms=args.phase_hop_ms,
                )
                resources.callback(phase_engine.close)
            engine.phase_engine = phase_engine

            def on_record(record, arrival_ns):
                engine.on_record(record, arrival_ns)
                if phase_engine is not None:
                    try:
                        phase_engine.on_record(record, arrival_ns)
                    except Exception as exc:
                        phase_engine.fail(f"Input failed: {type(exc).__name__}: {exc}")

            def on_interruption(reason):
                engine.interrupt(reason)
                if phase_engine is not None:
                    phase_engine.interrupt(reason)

            radio = LiveRadio(
                args,
                require_four=True,
                record_sink=on_record,
                on_interruption=on_interruption,
            )
            resources.callback(radio.stop)
            bundle.validate_radio(radio.settings)
            if args.grace_ms != radio.settings.transport.delivery_grace_ms:
                raise ValueError(
                    "--grace-ms must match the configured transport delivery grace"
                )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "detector.json").write_text(
                json.dumps(
                    dict(
                        model=bundle.metadata,
                        phase_models=(str(args.phase_models) if phase_engine is not None else None),
                        phase_preprocessing="rolling-window approximation" if phase_engine is not None else None,
                        runtime=dict(
                            hop_ms=args.hop_ms,
                            grace_ms=args.grace_ms,
                            workers=args.workers,
                            inference_threads=args.inference_threads,
                            kernel=args.kernel,
                            phase_hop_ms=args.phase_hop_ms,
                        ),
                        radio=radio.environment(),
                    ),
                    indent=2,
                )
                + "\n"
            )
            log = resources.enter_context(
                (args.output_dir / "predictions.jsonl").open("w", buffering=1)
            )
            engine.start()
            if phase_engine is not None:
                phase_engine.start()
            radio.start()

            logged_phase = {}

            def tick():
                events = engine.tick(
                    radio_ready=radio.manager.preflight_ready
                    and not radio.manager.failure
                )
                if phase_engine is not None:
                    state = phase_engine.status(
                        radio_ready=radio.manager.preflight_ready and not radio.manager.failure
                    )
                    for item in state["models"]:
                        key = (item["receiver"], item["duration_seconds"], item["model"])
                        identity = (item["generation"], item["end_ns"])
                        if logged_phase.get(key) != identity:
                            logged_phase[key] = identity
                            events.append(dict(kind="phase_prediction", **item))
                for event in events:
                    log.write(json.dumps(event, allow_nan=False) + "\n")
                return events

            if not args.headless:
                return _gui(args, radio, engine, tick)
            stopped = False

            def stop(signum, frame):
                nonlocal stopped
                stopped = True

            old = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
            began = time.monotonic()
            last_status = float("-inf")
            try:
                while not stopped and (
                    args.duration is None or time.monotonic() - began < args.duration
                ):
                    for event in tick():
                        print(json.dumps(event, allow_nan=False), flush=True)
                    if time.monotonic() - last_status >= 1:
                        print(
                            json.dumps(
                                dict(
                                    kind="status",
                                    radio_ready=radio.manager.preflight_ready,
                                    **engine.status(),
                                    phase=(phase_engine.status(radio.manager.preflight_ready and
                                           not radio.manager.failure) if phase_engine else None),
                                ),
                                allow_nan=False,
                            ),
                            flush=True,
                        )
                        last_status = time.monotonic()
                    time.sleep(0.05)
            finally:
                for signum, handler in old.items():
                    signal.signal(signum, handler)
            return 1 if engine.failure else 0
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        print(f"fall-detect: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
