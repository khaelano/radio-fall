"""Explicit gateway switching probes and fixed-criteria hardware qualification."""

from __future__ import annotations

import argparse
import json
import time
from bisect import bisect_right
from collections import Counter
from pathlib import Path

import numpy as np

from ..acquisition.clock_sync import ClockSyncEstimate
from ..acquisition.gateway_reader import GatewayReceiverManager
from ..settings import add_config_argument, resolve_settings


def evaluate(
    root: Path,
    *,
    warmup_s: float = 30,
    measurement_s: float = 300,
    qualification: bool = True,
    target_records_s: int = 50,
) -> dict:
    """Evaluate recorded acceptance times; never relax criteria to obtain a pass."""
    if target_records_s not in (50, 80):
        raise ValueError("supported delivery targets are 50 and 80 records/s")
    manifest = json.loads((root / "manifest.json").read_text())
    events = [
        json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()
    ]
    rounds = [
        e
        for e in events
        if e["kind"] == "round" and e.get("host_capture_ns") is not None
    ]
    if not rounds:
        raise ValueError("no authoritative transmitter rounds")
    begin = min(e["host_capture_ns"] for e in rounds) + int(warmup_s * 1e9)
    end = begin + int(measurement_s * 1e9)
    complete = max(e["host_capture_ns"] for e in rounds) >= end
    receivers = manifest["inventory"]["receivers"]
    result = {
        "schema_version": 1,
        "mode": "qualification" if qualification else "switching_probe",
        "measurement_s": measurement_s,
        "target_records_s": target_records_s,
        "complete": complete,
        "receivers": {},
    }
    selected = [
        e
        for e in events
        if e["kind"] == "record" and begin <= e["capture_host_ns"] < end
    ]
    statuses = [
        e
        for e in events
        if e["kind"] == "receiver_status" and begin <= e["host_monotonic_ns"] < end
    ]
    for receiver in receivers:
        identity = receiver["id"]
        rows = [e for e in selected if e["receiver_id"] == identity]
        # Use the conservative upper delay estimate, not an unqualified point estimate.
        delays = np.array(
            [
                (e["available_ns"] - e["capture_host_ns"]) / 1e6
                + e["clock_uncertainty_us"] / 1000
                if e.get("clock_uncertainty_us") is not None
                else np.nan
                for e in rows
            ]
        )
        timely = [e for e, delay in zip(rows, delays) if 0 <= delay < 1000]
        counts = np.zeros(max(1, int(np.ceil(measurement_s))), dtype=int)
        for e in timely:
            counts[
                min(
                    len(counts) - 1,
                    int((e["capture_host_ns"] - begin) // 1_000_000_000),
                )
            ] += 1
        times = sorted([begin, end] + [e["capture_host_ns"] for e in timely])
        queues = [e["queued"] for e in statuses if e["receiver_id"] == identity]
        peaks = [e.get("peak", 0) for e in statuses if e["receiver_id"] == identity]
        width = min(30, len(queues) // 2)
        # Fixed operational stability test: no >one-record median increase
        # between the first/last 30 observed statuses, and no full pool.
        growth = (
            float(np.median(queues[-width:]) - np.median(queues[:width]))
            if width
            else None
        )
        stable = (
            growth is not None
            and growth <= 1
            and max(peaks, default=64) < manifest["transport_config"]["queue_capacity"]
        )
        rate = len(timely) / measurement_s
        fraction = float(np.mean((delays >= 0) & (delays < 1000))) if len(delays) else 0
        result["receivers"][identity] = {
            "delivered": len(rows),
            "timely_records_s": rate,
            "subsecond_fraction": fraction,
            "clock_alignment_complete": bool(len(delays))
            and bool(np.isfinite(delays).all()),
            "delay_p50_ms": float(np.quantile(delays[np.isfinite(delays)], 0.5))
            if np.isfinite(delays).any()
            else None,
            "delay_p99_ms": float(np.quantile(delays[np.isfinite(delays)], 0.99))
            if np.isfinite(delays).any()
            else None,
            "one_second_rates": counts.tolist(),
            "longest_timely_capture_gap_ms": max(np.diff(times)) / 1e6,
            "queue_peak": max(peaks, default=None),
            "queue_median_growth": growth,
            "queues_stable": stable,
            "passes": bool(
                rate >= target_records_s
                and fraction >= 0.99
                and stable
                and np.isfinite(delays).all()
            ),
        }
    intervals = [
        e
        for e in events
        if e["kind"] == "channel_interval"
        and e["start_lower_ns"] < end
        and e["end_upper_ns"] >= begin
    ]
    intervals.sort(key=lambda e: e["start_lower_ns"])
    overlaps = []
    for i, a in enumerate(intervals):
        for b in intervals[i + 1 :]:
            if b["start_lower_ns"] >= a["end_upper_ns"]:
                break
            if a["receiver_id"] != b["receiver_id"]:
                overlaps.append([a["grant_id"], b["grant_id"]])
    # Grant and status journals retain raw wire bytes for independent inspection.
    grants = []
    clock_events = sorted(
        (e for e in events if e["kind"] == "clock_exchange" and e.get("estimate")),
        key=lambda e: e["host_monotonic_ns"],
    )
    clock_times = [e["host_monotonic_ns"] for e in clock_events]
    deadline_bounds = {}
    for e in events:
        if e["kind"] == "radio_event":
            p = bytes.fromhex(e["payload_hex"])
            if p[:4] == b"CGGR":
                start = int.from_bytes(p[24:32], "big")
                grant = int.from_bytes(p[16:20], "big")
                grants.append((grant, start, e["host_monotonic_ns"]))
                index = bisect_right(clock_times, e["host_monotonic_ns"]) - 1
                if index >= 0:
                    estimate = ClockSyncEstimate(**clock_events[index]["estimate"])
                    if estimate.receiver_boot_id == int.from_bytes(p[12:16], "big"):
                        deadline = start + int.from_bytes(p[32:36], "big") * 1000
                        mapped = estimate.receiver_to_transmitter(deadline) * 1000
                        uncertainty = estimate.uncertainty_us * 1000
                        deadline_bounds[grant] = (
                            mapped - uncertainty,
                            mapped + uncertainty,
                        )
    required = {g for g, _, arrival in grants if begin <= arrival < end}
    proven = {e["grant_id"] for e in intervals}
    # A skipped/unobserved grant is not falsely certified as zero blindness.
    log_drops = max((e.get("log_drops", 0) for e in rounds), default=0)
    evidence = bool(required) and required <= proven and log_drops == 0
    starts = sorted(start for _, start, arrival in grants if begin <= arrival < end)
    spacing = np.diff(starts) / 1000
    result["upload_start_spacing_ms"] = {
        "samples": len(spacing),
        "mean": float(np.mean(spacing)) if len(spacing) else None,
        "p50": float(np.median(spacing)) if len(spacing) else None,
        "p99": float(np.quantile(spacing, 0.99)) if len(spacing) else None,
    }
    return_evidence = Counter()
    for interval in intervals:
        bounds = deadline_bounds.get(interval["grant_id"])
        if bounds is None:
            return_evidence["unmapped"] += 1
        elif interval["end_upper_ns"] <= bounds[0]:
            return_evidence["before_deadline"] += 1
        elif interval["end_lower_ns"] > bounds[1]:
            return_evidence["after_deadline"] += 1
        else:
            return_evidence["uncertain"] += 1
    result["slot_return_evidence"] = {
        key: return_evidence[key]
        for key in ("before_deadline", "after_deadline", "uncertain", "unmapped")
    }
    for receiver in receivers:
        queue_events = [
            e
            for e in events
            if e["kind"] == "queue_event" and e["receiver_id"] == receiver["id"]
        ]
        reasons = Counter(
            e.get("detail", 0) for e in queue_events if e["event_code"] == 9
        )
        result["receivers"][receiver["id"]]["early_return_events_full_run"] = {
            "complete_or_send_cutoff": reasons[1],
            "idle_grace": reasons[2],
            "unknown": sum(
                count for reason, count in reasons.items() if reason not in (1, 2)
            ),
        }
        result["receivers"][receiver["id"]]["retune_completed_events_full_run"] = sum(
            e["event_code"] == 10 for e in queue_events
        )
        metrics = [
            e
            for e in events
            if e["kind"] == "mac_completion_summary"
            and e["receiver_id"] == receiver["id"]
        ]
        samples = sum(e["samples"] for e in metrics)
        result["receivers"][receiver["id"]]["mac_completions_full_run"] = {
            "summaries": len(metrics),
            "samples": samples,
            "failures": sum(e["failures"] for e in metrics),
            "maximum_us": max((e["maximum_us"] for e in metrics), default=None),
            "maximum_failure_us": max(
                (e["maximum_failure_us"] for e in metrics), default=None
            ),
            "mean_us": sum(e["total_us"] for e in metrics) / samples
            if samples
            else None,
            "completions_after_cutoff": sum(
                e["completions_after_cutoff"] for e in metrics
            ),
            "busy_at_return": sum(e["sender_busy_at_return"] for e in metrics),
        }
    for receiver in receivers:
        # Departure is before retuning; recovery is the first observed sensing
        # packet. These conservative intervals are not channel-API durations.
        absence = np.array(
            [
                (e["end_upper_ns"] - e["start_lower_ns"]) / 1e6
                for e in intervals
                if e["receiver_id"] == receiver["id"]
            ]
        )
        result["receivers"][receiver["id"]]["observed_recovery_upper_ms"] = {
            "intervals": len(absence),
            "mean": float(np.mean(absence)) if len(absence) else None,
            "p50": float(np.median(absence)) if len(absence) else None,
            "p99": float(np.quantile(absence, 0.99)) if len(absence) else None,
            "maximum": float(np.max(absence)) if len(absence) else None,
        }
    result.update(
        channel_intervals=len(intervals),
        overlapping_or_uncertain_intervals=overlaps,
        complete_channel_evidence=evidence,
        unproven_grants=sorted(required - proven),
        transmitter_log_drops=log_drops,
    )
    # These causal 500 ms bins describe availability independently of the
    # one-second delivery criterion; late acceptance cannot revise their masks.
    bin_path = root / "availability.jsonl"
    masks: Counter[str] = Counter()
    if bin_path.exists():
        for line in bin_path.read_text().splitlines():
            value = json.loads(line)
            if begin <= value["start_ns"] < end:
                masks[
                    "".join(
                        "1" if value["receivers"][r["id"]]["available"] else "0"
                        for r in receivers
                    )
                ] += 1
    result["availability"] = {
        "receiver_order": [r["id"] for r in receivers],
        "bin_hz": manifest["transport_config"].get("bin_hz", 50),
        "grace_ms": manifest["transport_config"].get("delivery_grace_ms", 500),
        "finalized_bins": sum(masks.values()),
        "counts_by_mask": dict(sorted(masks.items())),
    }
    result["qualified"] = bool(
        qualification
        and len(receivers) == 4
        and warmup_s >= 30
        and measurement_s >= 300
        and complete
        and evidence
        and not overlaps
        and all(r["passes"] for r in result["receivers"].values())
    )
    if not qualification:
        result["note"] = (
            "A probe does not establish sustained four-receiver qualification."
        )
    return result


def main(argv: list[str] | None = None) -> int:
    """Collect a versioned hardware experiment or analyze an existing journal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analyze", type=Path, help="existing transport/gateway/<run> directory"
    )
    parser.add_argument("--mode", choices=("qualify", "probe"), default="qualify")
    parser.add_argument("--port", help="verified C5 transmitter USB path")
    parser.add_argument("--transmitter-link", choices=("usb", "espnow_uart"))
    parser.add_argument("--gateway-port", help="verified C6 gateway USB path")
    add_config_argument(parser)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/experiments/gateway")
    )
    parser.add_argument("--target-records-s", type=int, choices=(50, 80), default=80)
    parser.add_argument("--warmup", type=float, default=30)
    parser.add_argument("--seconds", type=float, default=300)
    args = parser.parse_args(argv)
    if args.warmup < 0 or args.seconds <= 0:
        parser.error("invalid measurement duration")
    qualification = args.mode == "qualify"
    if qualification and (args.warmup < 30 or args.seconds < 300):
        parser.error(
            "qualification requires at least 30 s warm-up and 300 s measurement"
        )
    root = args.analyze
    if root is None:
        try:
            settings = resolve_settings(args)
            settings.transport.validate(
                settings.inventory, settings.profile, require_four=qualification
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        if not args.gateway_port or (args.transmitter_link == "usb" and not args.port):
            parser.error("gateway port is required; USB reference also requires --port")
        inventory, profile, config = (
            settings.inventory,
            settings.profile,
            settings.transport,
        )
        manager = GatewayReceiverManager(
            inventory,
            profile,
            args.output_dir,
            transmitter_port=args.port,
            transmitter_link=args.transmitter_link,
            gateway_port=args.gateway_port,
            config=config,
            require_four=qualification,
            on_status=lambda message, live: print(message, flush=True),
        )
        manager.bind()
        manager.start()
        deadline = time.monotonic() + 15
        try:
            while (
                not manager.preflight_ready
                and not manager.failure
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            if manager.failure or not manager.preflight_ready:
                raise RuntimeError(
                    manager.failure or "gateway receiver preflight timed out"
                )
            until = time.monotonic() + args.warmup + args.seconds + 1
            while time.monotonic() < until:
                if manager.failure:
                    raise RuntimeError(manager.failure)
                time.sleep(0.1)
        finally:
            manager.stop()
        root = manager.journal.root
    report = evaluate(
        root,
        warmup_s=args.warmup,
        measurement_s=args.seconds,
        qualification=qualification,
        target_records_s=args.target_records_s,
    )
    output = root / "qualification.json"
    # Derived output only; raw journals are never rewritten.
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(journal=str(root), report=str(output), **report), indent=2))
    return 0 if not qualification or report["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
