"""Synthetic live-worker/GIL and offscreen GUI checks; never opens radio hardware."""

import argparse
from dataclasses import fields
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fall_detection import _radio_native as core
from fall_detection.detection.engine import DetectorEngine
from fall_detection.detection.model import ModelBundle
from fall_detection.radio.acquisition.native import NativeRecord
from fall_detection.radio.acquisition.protocol import CsiRecord
from fall_detection.radio.acquisition.wire import encode_csi_datagram


def synthetic_runtime(bundle: ModelBundle) -> dict:
    """Exercise actual native preprocessing and scorer with an injected 350 ms GIL hold."""
    records = []
    for rx, mac in enumerate(bundle.metadata["radio"]["receiver_macs"]):
        values = tuple(complex(12 + (i + rx) % 17, 7 + i % 13) for i in range(245))
        record = CsiRecord(
            1,
            bundle.metadata["radio"]["transmitter_mac"],
            -40,
            -95,
            1,
            values,
            raw_csi=values,
            sig_mode=4,
            profile_fingerprint=bundle.metadata["radio"]["profile_fingerprint"],
        )
        records.append(
            core.decode_cnn_record(
                encode_csi_datagram(record, receiver_mac=mac, transport_sequence=1)
            )
        )
    engine = DetectorEngine(bundle)
    events = []
    gap_check = {}
    try:
        engine.start()
        began = time.monotonic()
        next_packet = began
        injected = False
        while time.monotonic() - began < 8:
            now = time.monotonic()
            if now >= next_packet:
                captured = time.monotonic_ns()
                for record in records:
                    adapter = NativeRecord(
                        record,
                        dict(
                            capture_host_monotonic_ns=captured,
                            capture_clock_uncertainty_us=1.0,
                            run_id=1,
                            transmitter_boot_id=2,
                            receiver_boot_id=3,
                        ),
                    )
                    engine.on_record(adapter, captured)
                next_packet = now + 0.01
            events.extend(engine.tick())
            if not injected and now - began > 6:
                before = json.loads(engine.native.stats_json())["windows"]
                previous = sys.getswitchinterval()
                try:
                    sys.setswitchinterval(1.0)
                    until = time.perf_counter() + 0.35
                    while time.perf_counter() < until:
                        pass
                finally:
                    sys.setswitchinterval(previous)
                after = json.loads(engine.native.stats_json())["windows"]
                gap_check = dict(
                    before=before,
                    after=after,
                    native_windows_during_gil_hold=after - before,
                )
                injected = True
            time.sleep(0.001)
        events.extend(engine.tick())
        state = engine.status()
        predictions = [e for e in events if e["kind"] == "prediction"]
        assert not engine.failure, engine.failure
        assert state["native"]["overflow"] == 0, state
        assert predictions, "Synthetic scorer produced no valid predictions"
        assert gap_check["native_windows_during_gil_hold"] > 0, gap_check
        return dict(
            scope="Synthetic repeated CSI, not a hardware rate/accuracy result",
            duration_s=time.monotonic() - began,
            native=state["native"],
            predictions=len(predictions),
            gil_hold=gap_check,
            median_native_window_ms=statistics.median(
                p["preprocessing_ms"] for p in predictions
            ),
            median_inference_ms=statistics.median(
                p["inference_ms"] for p in predictions
            ),
            skipped_inference=state["skipped_inference"],
        )
    finally:
        engine.close()


def gui_smoke(bundle: ModelBundle, output: Path) -> dict:
    """Run real widgets with explicitly synthetic snapshots and save an offscreen image."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtWidgets
    from fall_detection.detection.app import _gui
    from fall_detection.radio.acquisition.gateway_diagnostics import (
        GatewayDiagnostics,
        ReceiverDiagnostics,
    )

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    receivers = []
    for key in bundle.metadata["receivers"]:
        row = {f.name: 0 for f in fields(ReceiverDiagnostics)}
        row.update(
            receiver_id=key,
            online=True,
            records_s=99.0,
            status_age_s=0.1,
            delivery_age_s=0.2,
        )
        receivers.append(ReceiverDiagnostics(**row))
    gateway = {f.name: None for f in fields(GatewayDiagnostics)}
    gateway.update(
        nominal_rate_hz=120,
        sensing_channel=44,
        backhaul_channel=11,
        backhaul_phy="ht20_mcs3_lgi",
        slot_ms=125,
        queue_capacity=96,
        application_acknowledgements=False,
        transmitter_link="espnow_uart",
        reference_present=True,
        reference_ready=True,
        gateway_configured=True,
        gateway_age_s=0.1,
        receivers=tuple(receivers),
    )
    radio = SimpleNamespace(
        manager=SimpleNamespace(diagnostics=lambda: GatewayDiagnostics(**gateway))
    )

    class Engine:
        def __init__(self):
            self.bundle = bundle

        def status(self):
            return dict(
                prediction=dict(probability=0.62, candidate=True),
                quality=dict(valid=True, phase_change_coverage=[0.84] * 4),
                failure="",
                native=dict(kernel="avx2", pending=0, overflow=0),
                skipped_inference=0,
            )

    def snapshot():
        for widget in application.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMainWindow):
                widget.setWindowTitle("SYNTHETIC GUI CHECK — no radio hardware")
                widget.grab().save(str(output))

    QtCore.QTimer.singleShot(500, snapshot)
    result = _gui(SimpleNamespace(duration=0.8), radio, Engine(), lambda: [])
    assert result == 0 and output.is_file()
    return dict(
        exit_code=result,
        image=str(output),
        scope="Offscreen synthetic GUI lifecycle only",
    )


def main() -> None:
    """Save bounded-worker and GUI evidence outside participant recordings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("data/models/four_rx_v1"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/experiments/detector/runtime-check"),
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    bundle = ModelBundle.load(args.model)
    result = dict(
        runtime=synthetic_runtime(bundle),
        gui=gui_smoke(bundle, args.output_dir / "gui-smoke.png"),
    )
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
