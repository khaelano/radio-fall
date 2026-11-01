"""Hardware BLE benchmarks and replayable reports, separate from model training."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import time
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..acquisition.ble_reader import BleReceiverManager
from ..ble_config import SERVICE_UUID, STATUS_UUID, BleTransportConfig
from ..profile import RadioInventory, load_inventory_and_profile


def summarize(run_dir: Path) -> dict[str, Any]:
    """Summarize measured event logs without inventing capture-loss causes."""
    manifest = json.loads((run_dir / "manifest.json").read_text())
    records, statuses, rounds = defaultdict(list), defaultdict(list), []
    first = last = grid_start = start = end = None
    failure = None
    startup_receivers: list[str] = []
    protocol_errors: Counter[str] = Counter()
    for line in (run_dir / "events.jsonl").open(encoding="utf-8"):
        event = json.loads(line)
        stamp = event["host_monotonic_ns"]
        first = stamp if first is None else min(first, stamp)
        last = stamp if last is None else max(last, stamp)
        kind = event["kind"]
        if kind == "measurement_started":
            start = event["at_ns"]
        elif kind == "measurement_finished":
            end = event["at_ns"]
        elif kind == "sensing_started":
            grid_start = event["start_ns"]
        elif kind == "record":
            records[event["receiver_mac"]].append(
                (
                    event["capture_host_ns"],
                    event.get("available_ns", event["arrival_ns"]),
                )
            )
        elif kind == "receiver_status":
            snapshot = dict(event["status"])
            for field in (
                "notification_drops",
                "reassembly_evictions",
                "reassembly_expired",
                "reassembly_stale_fragments",
            ):
                if field in event:
                    snapshot[field] = event[field]
            statuses[event["receiver"]].append((stamp, snapshot))
        elif kind == "startup_receivers":
            startup_receivers = event["receivers"]
        elif kind == "batch_rejected":
            protocol_errors[event["detail"]] += 1
        elif kind == "round_availability":
            rounds.append(event)
        elif kind == "run_finished":
            failure = event.get("failure") or failure
        elif kind == "benchmark_failed":
            failure = event["error"]
    start = (
        start if start is not None else grid_start if grid_start is not None else first
    )
    end = end if end is not None else last
    seconds = (
        max(0, (end - start) / 1e9) if start is not None and end is not None else 0
    )
    width = 1_000_000_000 // manifest["transport_config"]["bin_hz"]
    grace = manifest["transport_config"]["delivery_grace_ms"] * 1_000_000
    report = dict(
        schema_version=1,
        measured_hardware=bool(
            manifest.get("hardware_backend") and any(records.values())
        ),
        run_id=manifest["run_id"],
        scheduler=manifest["transport_config"]["scheduler"],
        transport_experiment=manifest["transport_config"].get("experiment"),
        nominal_rate_hz=manifest["radio_profile"]["nominal_rate_hz"],
        measurement_seconds=seconds,
        failure=failure,
        receivers={},
        joint_availability={},
        startup_receivers=startup_receivers,
        development_allow_missing_receivers=manifest.get(
            "development_allow_missing_receivers", False
        ),
        protocol_errors=dict(protocol_errors),
    )
    measured_rounds = [r for r in rounds if start <= r["host_capture_ns"] < end]
    report["joint_availability"] = dict(
        Counter(str(sum(r["availability"].values())) for r in measured_rounds)
    )
    for device in manifest["inventory"]["receivers"]:
        receiver, mac = device["id"], device["mac"]
        values = [(c, a) for c, a in records[mac] if c is not None and start <= c < end]
        delays = [(a - c) / 1e6 for c, a in values]
        timely = (
            sum(
                a <= grid_start + ((c - grid_start) // width + 1) * width + grace
                for c, a in values
            )
            if grid_start is not None
            else 0
        )
        longest, missing_start = 0, None
        for r in measured_rounds:
            stamp = r["host_capture_ns"]
            if not r["availability"].get(receiver, False):
                missing_start = stamp if missing_start is None else missing_start
                longest = max(longest, stamp - missing_start + r["period_us"] * 1000)
            else:
                missing_start = None
        snapshots = [(t, s) for t, s in statuses[receiver] if start <= t <= end]
        diagnostics = {}
        if snapshots:
            diagnostics["negotiated_last"] = {
                k: snapshots[-1][1].get(k)
                for k in (
                    "mtu",
                    "tx_phy",
                    "rx_phy",
                    "tx_octets",
                    "rx_octets",
                    "interval_units",
                    "latency",
                    "supervision_units",
                )
            }
            requested_interval = (
                manifest["transport_config"].get("experiment") or {}
            ).get("connection_interval_units", 10)
            observed_intervals = sorted(
                {
                    s["interval_units"]
                    for _, s in snapshots
                    if s.get("interval_units") is not None
                }
            )
            diagnostics["requested_interval_units"] = requested_interval
            diagnostics["observed_interval_units"] = observed_intervals
            diagnostics["interval_request_verified"] = observed_intervals == [
                requested_interval
            ]
            same_boot = len({s.get("boot_id") for _, s in snapshots}) == 1
            if any("flow_inflight_fragments" in s for _, s in snapshots):
                diagnostics["flow"] = {
                    "peak_inflight_fragments": max(
                        s.get("flow_inflight_fragments", 0) for _, s in snapshots
                    ),
                    "peak_inflight_bytes": max(
                        s.get("flow_inflight_bytes", 0) for _, s in snapshots
                    ),
                    "firmware_peak_fragments": max(
                        s.get("flow_peak_fragments", 0) for _, s in snapshots
                    ),
                    "firmware_peak_bytes": max(
                        s.get("flow_peak_bytes", 0) for _, s in snapshots
                    ),
                }
                for field in (
                    "flow_receipts",
                    "flow_invalid_receipts",
                    "flow_admission_drops",
                    "flow_transfer_expired",
                    "flow_credit_wait_ticks",
                    "flow_stall_disconnects",
                    "flow_submitted_fragments",
                    "flow_submitted_bytes",
                    "flow_submission_failures",
                ):
                    before, after = (
                        snapshots[0][1].get(field),
                        snapshots[-1][1].get(field),
                    )
                    diagnostics["flow"][field + "_delta"] = (
                        (after - before) & 0xFFFFFFFF
                        if same_boot and before is not None and after is not None
                        else None
                    )
            diagnostics["queue_peak"] = max(s.get("queued", 0) for _, s in snapshots)
            diagnostics["oldest_queue_age_ms"] = (
                max(s.get("oldest_age_us", 0) for _, s in snapshots) / 1000
            )
            diagnostics["minimum_reported_free_heap"] = min(
                (
                    s["minimum_free_heap"]
                    for _, s in snapshots
                    if "minimum_free_heap" in s
                ),
                default=None,
            )
            status_span = (snapshots[-1][0] - snapshots[0][0]) / 1e9
            diagnostics["status_span_seconds"] = status_span
            diagnostics["receiver_restarted"] = not same_boot
            for name in (
                "captured",
                "acknowledged",
                "evicted",
                "expired",
                "rejected",
                "epoch_dropped",
                "retries",
                "send_errors",
                "notification_drops",
                "reassembly_evictions",
                "reassembly_expired",
                "reassembly_stale_fragments",
            ):
                before, after = snapshots[0][1].get(name), snapshots[-1][1].get(name)
                diagnostics[f"{name}_delta"] = (
                    (after - before) & 0xFFFFFFFF
                    if same_boot and before is not None and after is not None
                    else None
                )
            captures = diagnostics.get("captured_delta")
            diagnostics["capture_rate_over_status_span"] = (
                captures / status_span if captures is not None and status_span else None
            )
        report["receivers"][receiver] = dict(
            discovered_at_startup=receiver in startup_receivers,
            delivered_records=len(values),
            timely_records=timely,
            delivered_rate_hz=len(values) / seconds if seconds else None,
            timely_rate_hz=timely / seconds if seconds else None,
            delay_ms={str(p): float(np.percentile(delays, p)) for p in (50, 95, 99)}
            if delays
            else {},
            longest_timely_missing_run_ms=longest / 1e6,
            diagnostics=diagnostics,
        )
    report["limitations"] = [
        "Rates describe this hardware run, not detector accuracy or a guaranteed service rate.",
        "Capture counter deltas use the explicitly reported status span, not exact measurement boundaries.",
        "Grant ownership is not proof of Wi-Fi blindness; loss causes may remain unknown.",
    ]
    return report


def prepare_matrix(
    output: Path,
    inventory_path: Path,
    profile_path: Path,
    config: BleTransportConfig,
    port: str,
) -> list[dict[str, Any]]:
    """Write a reproducible hardware run manifest; never change board settings."""
    _, base, _ = load_inventory_and_profile(inventory_path, profile_path)
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    for rate in (50, 60, 70, 80, 100):
        radio = replace(
            base,
            nominal_rate_hz=rate,
            profile_id=f"{base.band}-ch{base.channel}-{rate}hz",
        )
        radio_path = (output / f"radio-{rate}.json").resolve()
        radio_path.write_text(json.dumps(radio.as_dict(), indent=2) + "\n")
        provision = [
            "uv",
            "run",
            "--extra",
            "radio",
            "csi-radio-provision",
            "--receiver-config",
            str(inventory_path.resolve()),
            "--radio-profile",
            str(radio_path),
        ]
        for scheduler, seeds in (
            ("round_robin", (config.seed,)),
            ("random", (101, 202, 303)),
        ):
            for seed in seeds:
                policy = replace(config, scheduler=scheduler, seed=seed)
                policy_path = (output / f"{scheduler}-{seed}.json").resolve()
                if not policy_path.exists():
                    policy_path.write_text(json.dumps(asdict(policy), indent=2) + "\n")
                args = [
                    "uv",
                    "run",
                    "--extra",
                    "radio",
                    "csi-ble-benchmark",
                    "run",
                    "--receiver-config",
                    str(inventory_path.resolve()),
                    "--radio-profile",
                    str(radio_path),
                    "--ble-config",
                    str(policy_path),
                    "--port",
                    port,
                    "--output-dir",
                    str((output / "recordings").resolve()),
                ]
                commands.append(
                    dict(
                        rate_hz=rate,
                        scheduler=scheduler,
                        seed=seed,
                        preparation="Provision all boards over USB, then disconnect receiver USB data connections.",
                        provision_command=shlex.join(provision),
                        run_command=shlex.join(args),
                    )
                )
    (output / "matrix.json").write_text(
        json.dumps(
            dict(
                schema_version=1,
                conditions=commands,
                soak_instruction="Run the selected round-robin condition again with --duration 1800.",
            ),
            indent=2,
        )
        + "\n"
    )
    return commands


def main(argv: Sequence[str] | None = None) -> int:
    """Run one measured condition, prepare a matrix, or summarize saved data."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report")
    report.add_argument("run_dir", type=Path)
    report.add_argument(
        "--signal-quality",
        action="store_true",
        help="verify raw envelopes, authoritative metadata and subcarrier statistics",
    )
    for command in ("run", "matrix"):
        p = sub.add_parser(command)
        p.add_argument("--receiver-config", type=Path, required=True)
        p.add_argument("--radio-profile", type=Path, required=True)
        p.add_argument("--ble-config", type=Path)
        p.add_argument("--port", required=True)
        p.add_argument("--output-dir", type=Path, required=True)
        if command == "run":
            p.add_argument("--warmup", type=float, default=30)
            p.add_argument("--duration", type=float, default=300)
            p.add_argument(
                "--development",
                action="store_true",
                help="allow missing startup receivers while preserving the full provisioned slot order",
            )
            p.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    if args.command == "report":
        result = summarize(args.run_dir)
        if args.signal_quality:
            from .ble_quality import analyze_ble_quality

            result["signal_quality"] = analyze_ble_quality(args.run_dir)
        print(json.dumps(result, indent=2))
        return 0
    try:
        config = BleTransportConfig.load(args.ble_config)
        inventory, profile, _ = load_inventory_and_profile(
            args.receiver_config, args.radio_profile
        )
        if args.command == "matrix":
            prepare_matrix(
                args.output_dir,
                args.receiver_config,
                args.radio_profile,
                config,
                args.port,
            )
            print(
                f"Prepared {args.output_dir / 'matrix.json'}; no hardware was changed"
            )
            return 0
        if args.warmup < 0 or args.duration <= 0:
            parser.error("warmup must be nonnegative and duration positive")
        manager = BleReceiverManager(
            inventory,
            profile,
            args.output_dir,
            transmitter_port=args.port,
            config=config,
            require_four=not args.development,
            allow_missing_receivers=args.development,
            on_status=lambda text, _: print(text, flush=True),
        )
        manager.bind()
        manager.start()
        try:
            deadline = time.monotonic() + 60
            while not manager.preflight_ready:
                if manager.failure or time.monotonic() > deadline:
                    raise RuntimeError(
                        manager.failure or "hardware preflight timed out"
                    )
                time.sleep(0.1)
            for name, duration in (
                ("warmup", args.warmup),
                ("measurement", args.duration),
            ):
                manager.journal.event(
                    f"{name}_started", at_ns=time.monotonic_ns(), notes=args.notes
                )
                deadline = time.monotonic() + duration
                while time.monotonic() < deadline:
                    if manager.failure:
                        raise RuntimeError(manager.failure)
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
                manager.journal.event(f"{name}_finished", at_ns=time.monotonic_ns())
        except BaseException as exc:
            if manager.journal and not manager.journal.closed:
                manager.journal.event(
                    "benchmark_failed", error=str(exc) or type(exc).__name__
                )
            raise
        finally:
            manager.stop()
        result = summarize(manager.journal.root)
        (manager.journal.root / "benchmark.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


def discover(argv: Sequence[str] | None = None) -> int:
    """Report real BLE identities; optionally extend an existing inventory."""
    parser = argparse.ArgumentParser(description="Discover CSI BLE receiver identities")
    parser.add_argument("--receiver-config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, help="write an extended inventory to a new file"
    )
    args = parser.parse_args(argv)

    async def scan():
        from bleak import BleakClient, BleakScanner

        values = []
        for device in await BleakScanner.discover(
            timeout=5, service_uuids=[SERVICE_UUID]
        ):
            async with BleakClient(device) as client:
                status = json.loads(bytes(await client.read_gatt_char(STATUS_UUID)))
            if status.get("role") == "receiver" and status.get("protocol_version") == 1:
                values.append(status)
        return values

    try:
        inventory = RadioInventory.load(args.receiver_config)
        values = asyncio.run(scan())
        if len({v["mac"] for v in values}) != len(values):
            raise ValueError("duplicate BLE receiver identities discovered")
        print(json.dumps(values, indent=2))
        if args.output:
            updated = inventory.as_dict()
            known = {r["mac"] for r in updated["receivers"]}
            used = {r["id"] for r in updated["receivers"]}
            for value in sorted(values, key=lambda v: v["mac"]):
                if value["mac"] in known:
                    continue
                index = 1
                while f"rx-{index}" in used:
                    index += 1
                receiver_id = f"rx-{index}"
                used.add(receiver_id)
                updated["receivers"].append(
                    dict(
                        id=receiver_id,
                        role="receiver",
                        target=value["target"],
                        mac=value["mac"],
                        placement="not yet recorded",
                    )
                )
            if len(updated["receivers"]) > 4:
                raise ValueError(
                    "discovery exceeds the four-receiver protocol capacity"
                )
            RadioInventory.from_mapping(updated)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(updated, indent=2) + "\n")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
