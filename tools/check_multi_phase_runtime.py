"""Exercise both live scorers with synthetic records; no radio hardware is opened."""

import argparse
import json
from pathlib import Path
import time

import numpy as np

from fall_detection import _radio_native as core
from fall_detection.detection.engine import DetectorEngine
from fall_detection.detection.model import ModelBundle
from fall_detection.detection.phase_models import PhaseModelEngine
from fall_detection.radio.acquisition.native import NativeRecord
from fall_detection.radio.acquisition.protocol import CsiRecord
from fall_detection.radio.acquisition.wire import encode_csi_datagram


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", type=Path, default=Path("data/models/phase_random20_v1")
    )
    parser.add_argument(
        "--phase-models",
        type=Path,
        default=Path("data/experiments/phase_models_v1/20261104T081805521126Z"),
    )
    parser.add_argument("--duration", type=float, default=16)
    parser.add_argument("--rate-hz", type=float, default=100)
    args = parser.parse_args()
    if args.duration < 10:
        parser.error("duration must be at least 10 seconds for 6-second windows")
    if args.rate_hz <= 0:
        parser.error("rate must be positive")
    bundle = ModelBundle.load(args.model)
    legacy = DetectorEngine(bundle, threads=2)
    phase = PhaseModelEngine(
        args.phase_models,
        bundle.metadata["radio"],
        bundle.metadata["receivers"],
        threads=2,
        grace_ms=900,
        hop_ms=2000,
    )
    records = []
    for rx, mac in enumerate(bundle.metadata["radio"]["receiver_macs"]):
        values = tuple(complex(12 + (i + rx) % 17, 7 + i % 13) for i in range(245))
        source = CsiRecord(
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
                encode_csi_datagram(source, receiver_mac=mac, transport_sequence=1)
            )
        )
    callbacks = []
    events = []
    peak_queue = 0
    missed_rounds = 0
    try:
        legacy.start()
        phase.start()
        phase.status(True)
        started = time.monotonic_ns()
        next_time = started
        period_ns = int(1e9 / args.rate_hz)
        while time.monotonic_ns() - started < int(args.duration * 1e9):
            now = time.monotonic_ns()
            if now >= next_time:
                # Do not invent capture rounds to make up for a missed deadline.
                skipped = (now - next_time) // period_ns
                missed_rounds += skipped
                next_time += (skipped + 1) * period_ns
                for record in records:
                    adapter = NativeRecord(
                        record,
                        dict(
                            capture_host_monotonic_ns=now,
                            capture_clock_uncertainty_us=1.0,
                            run_id=1,
                            transmitter_boot_id=2,
                            receiver_boot_id=3,
                        ),
                    )
                    before = time.perf_counter_ns()
                    legacy.on_record(adapter, now)
                    phase.on_record(adapter, now)
                    callbacks.append(time.perf_counter_ns() - before)
            events.extend(legacy.tick())
            peak_queue = max(peak_queue, phase.queue.qsize())
            time.sleep(0.001)
        legacy_state = legacy.status()
        state = phase.status(True)
        valid = [item for item in state["models"] if item["probabilities"] is not None]
        output = {
            "scope": "synthetic; not a hardware throughput or accuracy qualification",
            "elapsed_seconds": (time.monotonic_ns() - started) / 1e9,
            "records_submitted": len(callbacks),
            "missed_producer_rounds": missed_rounds,
            "requested_rate_hz_per_receiver": args.rate_hz,
            "observed_rate_hz_per_receiver": len(callbacks)
            / 4
            / ((time.monotonic_ns() - started) / 1e9),
            "phase_scores_available": len(valid),
            "phase_failure": state["failure"],
            "phase_dropped": state["dropped"],
            "phase_pending": phase.queue.qsize(),
            "phase_peak_pending": peak_queue,
            "legacy_failure": legacy.failure,
            "legacy_native": legacy_state["native"],
            "legacy_predictions": sum(
                event["kind"] == "prediction" for event in events
            ),
            "callback_p99_ms": float(np.percentile(callbacks, 99) / 1e6),
        }
        print(json.dumps(output, indent=2))
        assert not state["failure"] and not legacy.failure
        assert state["dropped"] == 0 and legacy_state["native"]["overflow"] == 0
        assert output["legacy_predictions"] > 0 and len(valid) == 48
    finally:
        phase.close()
        legacy.close()


if __name__ == "__main__":
    main()
