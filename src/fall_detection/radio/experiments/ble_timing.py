"""Reproducible, explicitly developmental BLE timing comparisons."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import numpy as np

from ..ble_config import BleTimingExperiment, BleTransportConfig, BleDeliveryExperiment
from .ble import summarize


def timing_conditions() -> dict[str, BleTransportConfig]:
    """Return matched conditions; continuous uploads never become a default."""
    base = BleTransportConfig(experiment=BleTimingExperiment())
    e = base.experiment
    continuous = replace(base, experiment=replace(e, upload_policy="continuous"))
    return {
        "scheduled": base,
        "continuous": continuous,
        "continuous_one_outstanding": replace(continuous, outstanding_batches=1),
        "scheduled_one_outstanding": replace(base, outstanding_batches=1),
        "scheduled_paced_2ms": replace(
            base, experiment=replace(e, submission_pacing_us=2000)
        ),
        "scheduled_one_record": replace(base, experiment=replace(e, batch_records=1)),
        "scheduled_two_rounds": replace(base, experiment=replace(e, slot_rounds=2)),
        "scheduled_age_80ms": replace(base, maximum_age_ms=80),
        "scheduled_interval_7p5ms": replace(
            base, experiment=replace(e, connection_interval_units=6)
        ),
        "scheduled_delivery_7p5ms": replace(
            base,
            experiment=replace(
                e, connection_interval_units=6, delivery=BleDeliveryExperiment()
            ),
        ),
        "scheduled_delivery_credit4_7p5ms": replace(
            base,
            experiment=replace(
                e,
                connection_interval_units=6,
                delivery=BleDeliveryExperiment(credit_fragments=4),
            ),
        ),
        "scheduled_delivery_credit12_7p5ms": replace(
            base,
            experiment=replace(
                e,
                connection_interval_units=6,
                delivery=BleDeliveryExperiment(credit_fragments=12),
            ),
        ),
        "scheduled_age_80ms_interval_7p5ms": replace(
            base,
            maximum_age_ms=80,
            experiment=replace(e, connection_interval_units=6),
        ),
        "scheduled_interval_25ms": replace(
            base, experiment=replace(e, connection_interval_units=20)
        ),
    }


def timing_summary(root: Path) -> dict[str, Any]:
    """Summarize sampled receiver times and host stages during measurement.

    Receiver snapshots contain only four recent batches, so their distributions
    describe observed batches, not every captured record. Host stage times use
    the host clock; no receiver-to-host clock subtraction is performed.
    """
    events = [json.loads(line) for line in (root / "events.jsonl").open()]
    start = next(e["at_ns"] for e in events if e["kind"] == "measurement_started")
    end = next(e["at_ns"] for e in events if e["kind"] == "measurement_finished")
    samples = {}
    hosts = []
    for event in events:
        if not start <= event["host_monotonic_ns"] < end:
            continue
        if event["kind"] == "receiver_timing":
            for sample in event["batches"]:
                samples[
                    event["receiver"], event["receiver_boot_id"], sample["batch_id"]
                ] = sample
        elif event["kind"] == "batch_host_timing":
            hosts.append(event)

    def distribution(values):
        values = list(values)
        return (
            dict(
                count=len(values),
                **{
                    f"p{p}_ms": float(np.percentile(values, p)) / 1000
                    for p in (50, 95, 99)
                },
            )
            if values
            else dict(count=0)
        )

    result = {"sampled_receiver_batches": len(samples), "host_batches": len(hosts)}
    for name, first, last in (
        ("capture_to_build", "capture_us", "built_us"),
        ("capture_to_first_submit", "capture_us", "first_submit_us"),
        ("submission_span", "first_submit_us", "last_submit_us"),
        ("last_submit_to_ack", "last_submit_us", "ack_us"),
    ):
        result[name] = distribution(
            s[last] - s[first]
            for s in samples.values()
            if s[first] and s[last] and s[last] >= s[first]
        )
    for name, first, last in (
        ("host_fragment_span", "first_fragment_ns", "last_fragment_ns"),
        ("host_consumer_queue", "last_fragment_ns", "processing_started_ns"),
        ("host_acceptance", "processing_started_ns", "accepted_ns"),
        ("host_ack_submission", "accepted_ns", "ack_submitted_ns"),
    ):
        result[name] = distribution((s[last] - s[first]) / 1000 for s in hosts)
    result["sampled_expired_batches"] = sum(
        bool(s["flags"] & 8) for s in samples.values()
    )
    result["sampled_late_ack_batches"] = sum(
        bool(s["flags"] & 16) for s in samples.values()
    )
    result["limitations"] = [
        "Receiver timing snapshots expose four recent entries; absence is not loss evidence.",
        "Submission and ACK-write return times are not RF transmission times.",
        "Stage diagnostics select measurement-time events, unlike capture-time record rates.",
    ]
    return result


def deadline_sweep(
    root: Path, grace_ms: tuple[int, ...] = (100, 200, 350, 400)
) -> dict:
    """Compute alternative deadline counts without revising recorded input bins."""
    events = [json.loads(line) for line in (root / "events.jsonl").open()]
    manifest = json.loads((root / "manifest.json").read_text())
    width = 1_000_000_000 // manifest["transport_config"]["bin_hz"]
    grid = next(e["start_ns"] for e in events if e["kind"] == "sensing_started")
    start = next(e["at_ns"] for e in events if e["kind"] == "measurement_started")
    end = next(e["at_ns"] for e in events if e["kind"] == "measurement_finished")
    seconds = (end - start) / 1e9
    records = [
        e
        for e in events
        if e["kind"] == "record"
        and e.get("capture_host_ns") is not None
        and start <= e["capture_host_ns"] < end
    ]
    result = {}
    for grace in grace_ms:
        if type(grace) is not int or grace < 0:
            raise ValueError("deadline grace must be a nonnegative integer")
        counts, bins = {}, {}
        for e in records:
            identity = e["receiver_mac"]
            index = (e["capture_host_ns"] - grid) // width
            if (
                e.get("available_ns", e["arrival_ns"])
                <= grid + (index + 1) * width + grace * 1_000_000
            ):
                counts[identity] = counts.get(identity, 0) + 1
                bins.setdefault(identity, set()).add(index)
        result[str(grace)] = {
            d["mac"]: dict(
                timely_records=counts.get(d["mac"], 0),
                timely_record_rate_hz=counts.get(d["mac"], 0) / seconds,
                available_bin_rate_hz=len(bins.get(d["mac"], set())) / seconds,
            )
            for d in manifest["inventory"]["receivers"]
        }
    return dict(
        counterfactual=True,
        grace_ms=result,
        limitations="Assumes unchanged delivery trace; does not rerun transport or revise finalized bins.",
    )


def main(argv: list[str] | None = None) -> int:
    """Run selected conditions sequentially and retain each raw session."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receiver-config", type=Path, required=True)
    parser.add_argument("--radio-profile", type=Path, required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=tuple(timing_conditions()),
        default=list(timing_conditions()),
    )
    parser.add_argument("--warmup", type=float, default=30)
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--notes", default="Placement not recorded")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    plan = dict(
        warmup_seconds=args.warmup,
        measurement_seconds=args.duration,
        conditions={
            name: asdict(timing_conditions()[name]) for name in args.conditions
        },
        notes="Development only; fixed complete inventory; no automatic collection-default selection.",
        physical_notes=args.notes,
    )
    (args.output_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    results = []
    startup_receivers = None
    for name in args.conditions:
        path = args.output_dir / name
        path.mkdir()
        config = path / "config.json"
        config.write_text(json.dumps(plan["conditions"][name], indent=2) + "\n")
        command = [
            sys.executable,
            "-m",
            "fall_detection.radio.experiments.ble",
            "run",
            "--receiver-config",
            str(args.receiver_config),
            "--radio-profile",
            str(args.radio_profile),
            "--ble-config",
            str(config),
            "--port",
            args.port,
            "--output-dir",
            str(path / "recording"),
            "--warmup",
            str(args.warmup),
            "--duration",
            str(args.duration),
            "--development",
            "--notes",
            f"Timing comparison {name}; {args.notes}; CSI uncompressed",
        ]
        print(f"START {name}", flush=True)
        (path / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (path / "console.log").open("x") as output:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
        if completed.returncode:
            print(f"FAILED {name}; see {path / 'console.log'}", flush=True)
            return completed.returncode
        root = next((path / "recording").glob("*/transport/ble/*"))
        report = summarize(root)
        report["timing"] = timing_summary(root)
        (path / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        results.append(dict(condition=name, journal=str(root), **report))
        (args.output_dir / "results.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
        for receiver, r in report["receivers"].items():
            if r["discovered_at_startup"]:
                print(
                    f"DONE {name} {receiver}: delivered={r['delivered_rate_hz']:.2f} Hz timely={r['timely_rate_hz']:.2f} Hz latency={r['delay_ms']}",
                    flush=True,
                )
        if (
            startup_receivers is not None
            and report["startup_receivers"] != startup_receivers
        ):
            print(
                "FAILED: active receiver cohort changed between conditions", flush=True
            )
            return 1
        startup_receivers = report["startup_receivers"]
        if (args.output_dir / "stop_after_condition").exists():
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
