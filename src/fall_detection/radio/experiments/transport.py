"""Headless capture and analysis for the ESP-NOW/UDP interference experiment."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import threading
import time
from typing import Any, Generic, TypeVar

from ..acquisition.buffer import RollingCsiBuffer
from ..acquisition.telemetry import (
    ReceiverTelemetry,
    TransmitterTelemetry,
    parse_telemetry_line,
)
from ..acquisition.udp_reader import UdpCsiReader
from ..acquisition.wire import ReceiverStats


CONDITION_MODES = {
    "rf-baseline": "metrics-only",
    "ap-silent": "udp-dry-run",
    "udp-active": "udp-active",
}
BOOTSTRAP_SEED = 20260911
BOOTSTRAP_SAMPLES = 10_000
Z_95 = 1.959963984540054

TelemetryT = TypeVar("TelemetryT", ReceiverTelemetry, TransmitterTelemetry)


@dataclass(frozen=True)
class TimedSample(Generic[TelemetryT]):
    host_monotonic: float
    telemetry: TelemetryT


class TelemetrySerialMonitor(Generic[TelemetryT]):
    """Capture one board's console and retain parsed telemetry snapshots."""

    def __init__(self, port: str, baud: int, role: str, raw_path: Path) -> None:
        self.port = port
        self.baud = baud
        self.role = role
        self.raw_path = raw_path
        self.samples: list[TimedSample[TelemetryT]] = []
        self.malformed_telemetry = 0
        self.connection_errors: list[str] = []
        self.stop_event = threading.Event()
        self.ready_event = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run, name=f"{role}-telemetry", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self._thread.join(timeout=2)

    def latest(self) -> TimedSample[TelemetryT] | None:
        with self._lock:
            return self.samples[-1] if self.samples else None

    def _accepts(self, telemetry: object) -> bool:
        if self.role == "receiver":
            return isinstance(telemetry, ReceiverTelemetry)
        return isinstance(telemetry, TransmitterTelemetry)

    def _run(self) -> None:
        try:
            import serial
            from serial import SerialException
        except ImportError:
            self.connection_errors.append("pyserial is not installed")
            return

        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with (
                serial.Serial(self.port, self.baud, timeout=0.25) as connection,
                self.raw_path.open("w", encoding="utf-8") as raw_file,
            ):
                connection.dtr = False
                connection.rts = False
                pending = bytearray()
                while not self.stop_event.is_set():
                    chunk = connection.read(max(1, connection.in_waiting))
                    if not chunk:
                        continue
                    pending.extend(chunk)
                    while (newline := pending.find(b"\n")) >= 0:
                        raw = bytes(pending[:newline])
                        del pending[: newline + 1]
                        line = raw.decode("utf-8", errors="replace").strip()
                        host_time = time.monotonic()
                        raw_file.write(f"{host_time:.9f},{line}\n")
                        raw_file.flush()
                        try:
                            telemetry = parse_telemetry_line(line)
                        except ValueError:
                            if line.startswith(("CSI_RX_STATS,", "CSI_TX_STATS,")):
                                self.malformed_telemetry += 1
                            continue
                        if telemetry is None or not self._accepts(telemetry):
                            continue
                        with self._lock:
                            self.samples.append(TimedSample(host_time, telemetry))
                        self.ready_event.set()
        except (SerialException, OSError) as exc:
            self.connection_errors.append(str(exc))


@dataclass(frozen=True)
class UdpCounterSnapshot:
    records: int
    datagrams: int
    batches: int
    legacy_datagrams: int
    transport_missing: int
    transport_reordered: int
    batch_missing: int
    batch_reordered: int
    malformed: int
    foreign: int
    receiver_restarts: int


def udp_snapshot(reader: UdpCsiReader) -> UdpCounterSnapshot:
    """Take one cumulative host-side UDP counter snapshot."""

    return UdpCounterSnapshot(
        records=reader.buffer.received_records,
        datagrams=reader.total_datagrams,
        batches=reader.batch_datagrams,
        legacy_datagrams=reader.legacy_datagrams,
        transport_missing=reader.transport_missing,
        transport_reordered=reader.transport_reordered,
        batch_missing=reader.batch_missing,
        batch_reordered=reader.batch_reordered,
        malformed=reader.malformed_lines,
        foreign=reader.foreign_datagrams,
        receiver_restarts=reader.receiver_restarts,
    )


def _u32_delta(start: int, end: int) -> int:
    return (end - start) & 0xFFFFFFFF


def receiver_counter_delta(
    start: ReceiverTelemetry, end: ReceiverTelemetry
) -> ReceiverStats:
    """Return wrap-safe receiver counter deltas for one uninterrupted boot."""

    if start.boot_id != end.boot_id:
        raise ValueError("receiver boot id changed during measurement")
    if start.mode != end.mode:
        raise ValueError("receiver mode changed during measurement")
    if end.uptime_ms < start.uptime_ms:
        raise ValueError("receiver restarted during measurement")
    return ReceiverStats(
        *(
            _u32_delta(getattr(start.stats, field.name), getattr(end.stats, field.name))
            for field in fields(ReceiverStats)
        )
    )


def transmitter_counter_delta(
    start: TransmitterTelemetry, end: TransmitterTelemetry
) -> TransmitterTelemetry:
    """Return wrap-safe transmitter deltas for one measurement window."""

    if end.uptime_ms < start.uptime_ms:
        raise ValueError("transmitter restarted during measurement")
    if end.attempts < start.attempts:
        # A uint32 attempt counter takes well over a year to wrap at 100 Hz;
        # a decrease in a ten-minute trial is a restart.
        raise ValueError("transmitter attempt counter reset during measurement")
    return TransmitterTelemetry(
        uptime_ms=end.uptime_ms - start.uptime_ms,
        attempts=_u32_delta(start.attempts, end.attempts),
        immediate_errors=_u32_delta(start.immediate_errors, end.immediate_errors),
        asynchronous_successes=_u32_delta(
            start.asynchronous_successes, end.asynchronous_successes
        ),
        asynchronous_failures=_u32_delta(
            start.asynchronous_failures, end.asynchronous_failures
        ),
    )


def _plain_delta(start: UdpCounterSnapshot, end: UdpCounterSnapshot) -> dict[str, int]:
    return {
        field.name: getattr(end, field.name) - getattr(start, field.name)
        for field in fields(UdpCounterSnapshot)
    }


def _loss(missing: int, received: int) -> float | None:
    total = missing + received
    return missing / total if total else None


def build_run_summary(
    *,
    condition: str,
    cycle: int,
    warmup_seconds: float,
    duration_seconds: float,
    receiver_start: ReceiverTelemetry,
    receiver_end: ReceiverTelemetry,
    transmitter_start: TransmitterTelemetry,
    transmitter_end: TransmitterTelemetry,
    udp_start: UdpCounterSnapshot | None,
    udp_end: UdpCounterSnapshot | None,
    telemetry_issues: list[str] | None = None,
) -> dict[str, Any]:
    """Build the machine-readable summary for one measurement run."""

    issues = list(telemetry_issues or [])
    expected_mode = CONDITION_MODES[condition]
    if receiver_start.mode != expected_mode or receiver_end.mode != expected_mode:
        issues.append(f"condition {condition} requires receiver mode {expected_mode}")
    try:
        receiver = receiver_counter_delta(receiver_start, receiver_end)
    except ValueError as exc:
        issues.append(str(exc))
        receiver = ReceiverStats(*(0 for _ in fields(ReceiverStats)))
    try:
        transmitter = transmitter_counter_delta(transmitter_start, transmitter_end)
    except ValueError as exc:
        issues.append(str(exc))
        transmitter = TransmitterTelemetry(0, 0, 0, 0, 0)

    udp = (
        _plain_delta(udp_start, udp_end)
        if udp_start is not None and udp_end is not None
        else None
    )
    if condition == "udp-active" and udp is None:
        issues.append("UDP-active run has no host UDP counters")
    if udp is not None:
        if udp["receiver_restarts"]:
            issues.append("host observed a receiver boot change")
        if udp["malformed"]:
            issues.append("host received malformed UDP packets")
        if udp["foreign"]:
            issues.append("host received packets from another receiver")

    if receiver.accepted_records == 0:
        issues.append("receiver accepted no CSI records")
    if receiver.sensing_restarts:
        issues.append("receiver detected a transmitter sequence restart")
    if transmitter.attempts == 0:
        issues.append("transmitter made no send attempts")
    completed_transmitter_sends = (
        transmitter.immediate_errors
        + transmitter.asynchronous_successes
        + transmitter.asynchronous_failures
    )
    if abs(transmitter.attempts - completed_transmitter_sends) > 2:
        issues.append("transmitter send counters are inconsistent")

    if condition == "rf-baseline":
        if any(
            (
                receiver.queue_drops,
                receiver.unavailable_ip_drops,
                receiver.batches_built,
                receiver.batches_sent,
                receiver.records_sent,
                receiver.send_errors,
            )
        ):
            issues.append("metrics-only receiver reported output-stage counters")
    elif condition == "ap-silent":
        if receiver.batches_built == 0:
            issues.append("UDP dry-run built no batches")
        if any(
            (
                receiver.batches_sent,
                receiver.records_sent,
                receiver.send_errors,
            )
        ):
            issues.append("UDP dry-run reported send-stage counters")
    else:
        if receiver.batches_sent == 0 or receiver.records_sent == 0:
            issues.append("UDP-active receiver sent no records")
        if receiver.batches_sent > receiver.batches_built:
            issues.append("receiver sent more batches than it built")
        if receiver.batches_sent > receiver.records_sent:
            issues.append("receiver batch and record counters are inconsistent")
        if receiver.send_errors:
            issues.append("receiver reported UDP serialization or send errors")
        if udp is not None:
            classified_datagrams = (
                udp["batches"]
                + udp["legacy_datagrams"]
                + udp["malformed"]
                + udp["foreign"]
            )
            if udp["datagrams"] != classified_datagrams:
                issues.append("host UDP datagram counters are inconsistent")
            if udp["batches"] == 0 or udp["records"] == 0:
                issues.append("host received no UDP CSI batches")

    sensing_loss = _loss(receiver.sensing_missing, receiver.accepted_records)
    transport_loss = (
        _loss(udp["transport_missing"], udp["records"]) if udp is not None else None
    )
    batch_loss = (
        _loss(udp["batch_missing"], udp["batches"]) if udp is not None else None
    )
    batch_reduction = (
        1 - receiver.batches_sent / receiver.records_sent
        if receiver.records_sent
        else None
    )
    return {
        "schema_version": 1,
        "condition": condition,
        "cycle": cycle,
        "warmup_seconds": warmup_seconds,
        "duration_seconds": duration_seconds,
        "complete": not issues,
        "issues": issues,
        "receiver_start": {
            "mode": receiver_start.mode,
            "uptime_ms": receiver_start.uptime_ms,
            "boot_id": receiver_start.boot_id,
            "stats": asdict(receiver_start.stats),
        },
        "receiver_end": {
            "mode": receiver_end.mode,
            "uptime_ms": receiver_end.uptime_ms,
            "boot_id": receiver_end.boot_id,
            "stats": asdict(receiver_end.stats),
        },
        "receiver_delta": asdict(receiver),
        "transmitter_delta": asdict(transmitter),
        "udp_delta": udp,
        "metrics": {
            "sensing_loss": sensing_loss,
            "transport_loss": transport_loss,
            "batch_loss": batch_loss,
            "batch_reduction": batch_reduction,
        },
    }


def bootstrap_mean_interval(
    values: list[float],
    *,
    seed: int = BOOTSTRAP_SEED,
    samples: int = BOOTSTRAP_SAMPLES,
) -> tuple[float, float]:
    """Return a deterministic percentile bootstrap interval for a mean."""

    if not values:
        raise ValueError("at least one value is required")
    generator = random.Random(seed)
    means = sorted(
        sum(generator.choice(values) for _ in values) / len(values)
        for _ in range(samples)
    )

    def percentile(probability: float) -> float:
        position = probability * (len(means) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        fraction = position - lower
        return means[lower] * (1 - fraction) + means[upper] * fraction

    return percentile(0.025), percentile(0.975)


def wilson_upper(missing: int, total: int) -> float | None:
    """Return the upper bound of a two-sided 95% Wilson interval."""

    if total <= 0:
        return None
    proportion = missing / total
    denominator = 1 + Z_95**2 / total
    centre = proportion + Z_95**2 / (2 * total)
    spread = Z_95 * math.sqrt(
        proportion * (1 - proportion) / total + Z_95**2 / (4 * total**2)
    )
    return (centre + spread) / denominator


def summarize_experiments(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine paired cycles and evaluate the documented acceptance gates."""

    cycles: dict[int, dict[str, dict[str, Any]]] = {}
    for run in runs:
        cycles.setdefault(int(run["cycle"]), {})[str(run["condition"])] = run
    complete_cycles = [
        cycle
        for cycle in sorted(cycles)
        if set(cycles[cycle]) == set(CONDITION_MODES)
        and all(cycles[cycle][condition]["complete"] for condition in CONDITION_MODES)
    ]
    paired_effects = [
        cycles[cycle]["udp-active"]["metrics"]["sensing_loss"]
        - cycles[cycle]["ap-silent"]["metrics"]["sensing_loss"]
        for cycle in complete_cycles
    ]
    relative_interval = (
        bootstrap_mean_interval(paired_effects) if paired_effects else None
    )

    active_runs = [cycles[cycle]["udp-active"] for cycle in complete_cycles]
    transport_missing = sum(
        run["udp_delta"]["transport_missing"] for run in active_runs
    )
    transport_received = sum(run["udp_delta"]["records"] for run in active_runs)
    transport_total = transport_missing + transport_received
    transport_upper = wilson_upper(transport_missing, transport_total)
    records_sent = sum(run["receiver_delta"]["records_sent"] for run in active_runs)
    batches_sent = sum(run["receiver_delta"]["batches_sent"] for run in active_runs)
    batch_reduction = 1 - batches_sent / records_sent if records_sent else None

    gates = {
        "five_complete_cycles": len(complete_cycles) >= 5,
        "relative_sensing_effect_at_most_1pp": (
            relative_interval is not None and relative_interval[1] <= 0.01
        ),
        "transport_loss_upper_bound_below_1pct": (
            transport_upper is not None and transport_upper < 0.01
        ),
        "datagram_reduction_at_least_70pct": (
            batch_reduction is not None and batch_reduction >= 0.70
        ),
    }
    return {
        "schema_version": 1,
        "complete_cycles": complete_cycles,
        "paired_sensing_effects": paired_effects,
        "relative_sensing_effect_95pct": relative_interval,
        "transport_missing": transport_missing,
        "transport_received": transport_received,
        "transport_loss_upper_95pct": transport_upper,
        "batch_reduction": batch_reduction,
        "gates": gates,
        "accepted": all(gates.values()),
    }


def _wait(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


def _capture(args: argparse.Namespace) -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / f"{timestamp}_cycle-{args.cycle}_{args.condition}"
    run_dir.mkdir(parents=True, exist_ok=False)
    receiver_monitor: TelemetrySerialMonitor[ReceiverTelemetry] = (
        TelemetrySerialMonitor(
            args.receiver_port, args.baud, "receiver", run_dir / "receiver.log"
        )
    )
    transmitter_monitor: TelemetrySerialMonitor[TransmitterTelemetry] = (
        TelemetrySerialMonitor(
            args.transmitter_port, args.baud, "transmitter", run_dir / "transmitter.log"
        )
    )
    udp_reader: UdpCsiReader | None = None
    if args.condition == "udp-active":
        udp_reader = UdpCsiReader(
            args.listen_host,
            args.listen_port,
            RollingCsiBuffer(nominal_rate=100, seconds=10),
            run_dir,
            receiver_mac=args.receiver_mac,
        )
        udp_reader.start()
    receiver_monitor.start()
    transmitter_monitor.start()

    summary_path = run_dir / "summary.json"
    try:
        if not receiver_monitor.ready_event.wait(args.startup_timeout):
            raise RuntimeError("timed out waiting for receiver telemetry")
        if not transmitter_monitor.ready_event.wait(args.startup_timeout):
            raise RuntimeError("timed out waiting for transmitter telemetry")
        receiver_ready = receiver_monitor.latest()
        if (
            receiver_ready is None
            or receiver_ready.telemetry.mode != CONDITION_MODES[args.condition]
        ):
            actual = receiver_ready.telemetry.mode if receiver_ready else "unknown"
            raise RuntimeError(
                f"receiver mode {actual} does not match condition {args.condition}"
            )

        _wait(args.warmup)
        receiver_start_sample = receiver_monitor.latest()
        transmitter_start_sample = transmitter_monitor.latest()
        if receiver_start_sample is None or transmitter_start_sample is None:
            raise RuntimeError("telemetry disappeared during warm-up")
        udp_start = udp_snapshot(udp_reader) if udp_reader is not None else None
        _wait(args.duration)
        receiver_end_sample = receiver_monitor.latest()
        transmitter_end_sample = transmitter_monitor.latest()
        udp_end = udp_snapshot(udp_reader) if udp_reader is not None else None
        if receiver_end_sample is None or transmitter_end_sample is None:
            raise RuntimeError("telemetry disappeared during measurement")

        issues: list[str] = []
        now = time.monotonic()
        if now - receiver_end_sample.host_monotonic > 2.5:
            issues.append("receiver telemetry is stale")
        if now - transmitter_end_sample.host_monotonic > 2.5:
            issues.append("transmitter telemetry is stale")
        if receiver_monitor.malformed_telemetry:
            issues.append("receiver emitted malformed telemetry")
        if transmitter_monitor.malformed_telemetry:
            issues.append("transmitter emitted malformed telemetry")
        issues.extend(
            f"receiver serial error: {message}"
            for message in receiver_monitor.connection_errors
        )
        issues.extend(
            f"transmitter serial error: {message}"
            for message in transmitter_monitor.connection_errors
        )
        summary = build_run_summary(
            condition=args.condition,
            cycle=args.cycle,
            warmup_seconds=args.warmup,
            duration_seconds=args.duration,
            receiver_start=receiver_start_sample.telemetry,
            receiver_end=receiver_end_sample.telemetry,
            transmitter_start=transmitter_start_sample.telemetry,
            transmitter_end=transmitter_end_sample.telemetry,
            udp_start=udp_start,
            udp_end=udp_end,
            telemetry_issues=issues,
        )
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(summary_path)
        return 0 if summary["complete"] else 1
    except (KeyboardInterrupt, RuntimeError) as exc:
        summary_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "condition": args.condition,
                    "cycle": args.cycle,
                    "complete": False,
                    "issues": [str(exc)],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"incomplete capture: {exc}")
        print(summary_path)
        return 1
    finally:
        receiver_monitor.stop()
        transmitter_monitor.stop()
        if udp_reader is not None:
            udp_reader.stop()


def _summarize(args: argparse.Namespace) -> int:
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in args.summaries]
    report = summarize_experiments(runs)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8")
        print(args.output)
    return 0 if report["accepted"] else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and assess controlled ESP-NOW/UDP experiments."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="capture one hardware condition")
    run.add_argument("--condition", choices=tuple(CONDITION_MODES), required=True)
    run.add_argument("--cycle", type=int, default=1)
    run.add_argument("--warmup", type=float, default=30.0)
    run.add_argument("--duration", type=float, default=600.0)
    run.add_argument("--startup-timeout", type=float, default=30.0)
    run.add_argument("--transmitter-port", required=True)
    run.add_argument("--receiver-port", required=True)
    run.add_argument("--baud", type=int, default=921600)
    run.add_argument("--listen-host", default="0.0.0.0")
    run.add_argument("--listen-port", type=int, default=5500)
    run.add_argument("--receiver-mac")
    run.add_argument("--output-dir", type=Path, default=Path("data/experiments"))
    run.set_defaults(handler=_capture)

    summarize = commands.add_parser(
        "summarize", help="evaluate five paired condition cycles"
    )
    summarize.add_argument("summaries", nargs="+", type=Path)
    summarize.add_argument("--output", type=Path)
    summarize.set_defaults(handler=_summarize)
    from .backhaul import add_backhaul_commands

    add_backhaul_commands(commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the experiment capture or summary command."""

    args = _parser().parse_args(argv)
    if getattr(args, "cycle", 1) < 1:
        _parser().error("--cycle must be at least 1")
    for name in ("warmup", "duration", "startup_timeout"):
        if hasattr(args, name) and getattr(args, name) < 0:
            _parser().error(f"--{name.replace('_', '-')} cannot be negative")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
