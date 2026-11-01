"""Read-only summaries of historical ESP-NOW backhaul captures."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from ..acquisition.telemetry import BackhaulTelemetrySnapshot


@dataclass(frozen=True)
class BackhaulProfile:
    """Firmware settings declared for one controlled measurement profile."""

    name: str
    nominal_rate_hz: int
    return_mcs: int
    return_power_dbm: int
    batch_records: int = 4
    batch_wait_ms: int = 35
    send_timeout_ms: int = 100


BACKHAUL_PROFILES = {
    "baseline-100-mcs3-11": BackhaulProfile("baseline-100-mcs3-11", 100, 3, 11),
    "link-100-mcs0-20": BackhaulProfile("link-100-mcs0-20", 100, 0, 20),
    "final-50-mcs0-20": BackhaulProfile("final-50-mcs0-20", 50, 0, 20),
}


def _loss(missing: int | None, delivered: int | None) -> float | None:
    if missing is None or delivered is None:
        return None
    denominator = missing + delivered
    return missing / denominator if denominator else 0.0


def _rate(failures: int | None, attempts: int | None) -> float | None:
    """Return a failure rate when the failure counter is a subset of attempts."""

    if failures is None or attempts is None:
        return None
    return failures / attempts if attempts else 0.0


def _stage_metrics(values: dict[str, Any]) -> dict[str, Any]:
    """Derive loss rates without manufacturing values for unavailable stages."""

    accepted = values.get("receiver_accepted_records")
    sensing_missing = values.get("receiver_sensing_missing")
    batches_built = values.get("receiver_batches_built")
    batches_sent = values.get("receiver_batches_sent")
    records_sent = values.get("receiver_records_sent")
    send_errors = values.get("receiver_send_errors")
    gateway_received = values.get("gateway_received")
    gateway_queue_drops = values.get("gateway_queue_drops")
    return {
        "transmitter_attempts": values.get("transmitter_attempts"),
        "transmitter_immediate_error_rate": _rate(
            values.get("transmitter_immediate_errors"),
            values.get("transmitter_attempts"),
        ),
        "transmitter_async_failure_rate": _rate(
            values.get("transmitter_asynchronous_failures"),
            values.get("transmitter_attempts"),
        ),
        "forward_sensing_loss": _loss(sensing_missing, accepted),
        "receiver_queue_loss": _loss(values.get("receiver_queue_drops"), accepted),
        "receiver_send_loss": _rate(send_errors, batches_built),
        "return_batch_loss": _loss(
            (batches_built - batches_sent)
            if batches_built is not None and batches_sent is not None
            else None,
            batches_sent,
        ),
        "gateway_queue_loss": _loss(gateway_queue_drops, gateway_received),
        "gateway_invalid": values.get("gateway_invalid"),
        "gateway_serial_errors": values.get("gateway_serial_errors"),
        "gateway_serial_frames": values.get("gateway_serial_frames"),
        "host_transport_loss": _loss(
            values.get("transport_missing"), values.get("records")
        ),
        "host_batch_loss": _loss(values.get("batch_missing"), values.get("batches")),
        "delivered_records_per_second": values.get("effective_records_per_second"),
        "records_sent": records_sent,
    }


def _snapshot_payload(snapshot: BackhaulTelemetrySnapshot | None) -> Any:
    return snapshot.to_dict() if snapshot is not None else None


def build_backhaul_summary(
    *,
    profile: BackhaulProfile,
    cycle: int,
    warmup_seconds: float,
    duration_seconds: float,
    geometry_notes: str,
    start: BackhaulTelemetrySnapshot,
    end: BackhaulTelemetrySnapshot,
) -> dict[str, Any]:
    """Build one auditable summary from two cumulative reader snapshots."""

    delta = end.delta(start)
    values = delta["values"] or {}
    issues = list(delta["warnings"])
    attempts = values.get("transmitter_attempts")
    expected_attempts = profile.nominal_rate_hz * duration_seconds
    if attempts is not None and expected_attempts > 0:
        observed_rate = attempts / duration_seconds
        if (
            abs(observed_rate - profile.nominal_rate_hz)
            > profile.nominal_rate_hz * 0.10
        ):
            issues.append(
                "transmitter attempt rate does not match the declared nominal profile"
            )
    else:
        observed_rate = None
        issues.append("transmitter attempt counter unavailable")
    values["observed_transmitter_rate_hz"] = observed_rate
    payload = {
        "schema_version": 1,
        "experiment": "espnow-backhaul",
        "profile": asdict(profile),
        "cycle": cycle,
        "warmup_seconds": warmup_seconds,
        "duration_seconds": duration_seconds,
        "geometry_notes": geometry_notes,
        "complete": not issues,
        "issues": issues,
        "start": _snapshot_payload(start),
        "end": _snapshot_payload(end),
        "delta": delta,
        "stages": _stage_metrics(values),
    }
    return payload


def _bootstrap_interval(
    values: Iterable[float], *, samples: int = 5000
) -> list[float] | None:
    observations = list(values)
    if not observations:
        return None
    rng = random.Random(20261014)
    means = []
    for _ in range(samples):
        means.append(statistics.fmean(rng.choice(observations) for _ in observations))
    means.sort()
    return [means[int(samples * 0.025)], means[int(samples * 0.975)]]


def summarize_backhaul(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize paired baseline/link/final runs without a loss threshold."""

    run_list = [run for run in runs if run.get("experiment") == "espnow-backhaul"]
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for run in run_list:
        by_profile.setdefault(run["profile"]["name"], []).append(run)
    complete_cycles = []
    for cycle in range(1, 6):
        cycle_runs = [
            run for run in run_list if run.get("cycle") == cycle and run.get("complete")
        ]
        if {run["profile"]["name"] for run in cycle_runs} == set(BACKHAUL_PROFILES):
            complete_cycles.append(cycle)

    profiles: dict[str, Any] = {}
    for name in BACKHAUL_PROFILES:
        profile_runs = by_profile.get(name, [])
        rates = [
            run["stages"]["delivered_records_per_second"]
            for run in profile_runs
            if run.get("complete")
            and run["stages"].get("delivered_records_per_second") is not None
        ]
        losses = [
            run["stages"]["host_transport_loss"]
            for run in profile_runs
            if run.get("complete")
            and run["stages"].get("host_transport_loss") is not None
        ]
        profiles[name] = {
            "runs": len(profile_runs),
            "complete_runs": sum(1 for run in profile_runs if run.get("complete")),
            "delivered_records_per_second": statistics.fmean(rates) if rates else None,
            "delivered_records_per_second_ci95": _bootstrap_interval(rates),
            "host_transport_loss": statistics.fmean(losses) if losses else None,
            "host_transport_loss_ci95": _bootstrap_interval(losses),
        }

    paired_differences: dict[str, list[float]] = {}
    for candidate in ("link-100-mcs0-20", "final-50-mcs0-20"):
        differences = []
        for cycle in complete_cycles:
            baseline = next(
                (
                    run
                    for run in run_list
                    if run["cycle"] == cycle
                    and run["profile"]["name"] == "baseline-100-mcs3-11"
                ),
                None,
            )
            comparison = next(
                (
                    run
                    for run in run_list
                    if run["cycle"] == cycle and run["profile"]["name"] == candidate
                ),
                None,
            )
            if baseline and comparison:
                base_loss = baseline["stages"].get("host_transport_loss")
                candidate_loss = comparison["stages"].get("host_transport_loss")
                if base_loss is not None and candidate_loss is not None:
                    differences.append(candidate_loss - base_loss)
        paired_differences[candidate] = differences

    return {
        "schema_version": 1,
        "experiment": "espnow-backhaul",
        "profiles": profiles,
        "complete_cycles": complete_cycles,
        "paired_host_transport_loss_difference_vs_baseline": paired_differences,
        "accepted": len(complete_cycles) == 5,
        "acceptance_note": (
            "No fixed loss threshold was applied; report observed final loss and "
            "stage-wise regressions or improvements."
        ),
    }


def summarize_backhaul_files(args: argparse.Namespace) -> int:
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.summaries]
    report = summarize_backhaul(runs)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8")
        print(args.output)
    return 0 if report["accepted"] else 1


def add_backhaul_commands(commands: Any) -> None:
    """Register backhaul subcommands on the main experiment parser."""

    summarize = commands.add_parser(
        "backhaul-summarize", help="summarize five paired ESP-NOW backhaul cycles"
    )
    summarize.add_argument("summaries", nargs="+", type=Path)
    summarize.add_argument("--output", type=Path)
    summarize.set_defaults(handler=summarize_backhaul_files)


def _parser() -> argparse.ArgumentParser:
    """Return a parser containing only the backhaul commands for unit tests."""

    parser = argparse.ArgumentParser(
        description="Summarize historical ESP-NOW backhaul experiments."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add_backhaul_commands(commands)
    return parser
