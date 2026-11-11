from fall_detection.radio.experiments.transport import (
    UdpCounterSnapshot,
    _parser,
    bootstrap_mean_interval,
    build_run_summary,
    receiver_counter_delta,
    summarize_experiments,
)
from fall_detection.radio.acquisition.telemetry import (
    ReceiverTelemetry,
    TransmitterTelemetry,
)
from fall_detection.radio.acquisition.wire import ReceiverStats


ZERO_STATS = ReceiverStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
ZERO_UDP = UdpCounterSnapshot(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def receiver(mode: str, stats: ReceiverStats, *, boot_id: int = 7, uptime=1000):
    return ReceiverTelemetry(mode, uptime, boot_id, stats)


def transmitter(attempts: int, *, uptime=1000):
    return TransmitterTelemetry(uptime, attempts, 0, attempts, 0)


def run(condition: str, cycle: int, *, missing: int) -> dict:
    mode = {
        "rf-baseline": "metrics-only",
        "ap-silent": "udp-dry-run",
        "udp-active": "udp-active",
    }[condition]
    end_stats = ReceiverStats(
        accepted_records=60_000,
        sensing_missing=missing,
        sensing_reordered=0,
        sensing_restarts=0,
        queue_drops=0,
        unavailable_ip_drops=0,
        batches_built=15_000 if condition != "rf-baseline" else 0,
        batches_sent=15_000 if condition == "udp-active" else 0,
        records_sent=60_000 if condition == "udp-active" else 0,
        send_errors=0,
    )
    udp_end = (
        UdpCounterSnapshot(
            records=60_000,
            datagrams=15_000,
            batches=15_000,
            legacy_datagrams=0,
            transport_missing=0,
            transport_reordered=0,
            batch_missing=0,
            batch_reordered=0,
            malformed=0,
            foreign=0,
            receiver_restarts=0,
        )
        if condition == "udp-active"
        else None
    )
    return build_run_summary(
        condition=condition,
        cycle=cycle,
        warmup_seconds=30,
        duration_seconds=600,
        receiver_start=receiver(mode, ZERO_STATS),
        receiver_end=receiver(mode, end_stats, uptime=601_000),
        transmitter_start=transmitter(0),
        transmitter_end=transmitter(60_000, uptime=601_000),
        udp_start=ZERO_UDP if udp_end else None,
        udp_end=udp_end,
    )


def test_receiver_counter_delta_handles_uint32_wrap():
    maximum = 0xFFFFFFFF
    start = receiver(
        "udp-active",
        ReceiverStats(maximum - 1, maximum, 0, 0, 0, 0, 0, 0, 0, 0),
    )
    end = receiver(
        "udp-active",
        ReceiverStats(1, 1, 0, 0, 0, 0, 0, 0, 0, 0),
        uptime=2000,
    )

    delta = receiver_counter_delta(start, end)

    assert delta.accepted_records == 3
    assert delta.sensing_missing == 2


def test_receiver_counter_delta_rejects_uptime_reset():
    start = receiver("metrics-only", ZERO_STATS, uptime=10_000)
    end = receiver("metrics-only", ZERO_STATS, uptime=100)

    try:
        receiver_counter_delta(start, end)
    except ValueError as exc:
        assert "restarted" in str(exc)
    else:
        raise AssertionError("receiver uptime reset was accepted")


def test_run_summary_marks_mode_mismatch_and_malformed_udp_incomplete():
    end_udp = UdpCounterSnapshot(10, 3, 3, 0, 0, 0, 0, 0, 1, 0, 0)

    summary = build_run_summary(
        condition="udp-active",
        cycle=1,
        warmup_seconds=30,
        duration_seconds=600,
        receiver_start=receiver("udp-dry-run", ZERO_STATS),
        receiver_end=receiver("udp-dry-run", ZERO_STATS, uptime=601_000),
        transmitter_start=transmitter(0),
        transmitter_end=transmitter(60_000, uptime=601_000),
        udp_start=ZERO_UDP,
        udp_end=end_udp,
    )

    assert not summary["complete"]
    assert any("requires receiver mode" in issue for issue in summary["issues"])
    assert any("malformed" in issue for issue in summary["issues"])


def test_bootstrap_interval_is_deterministic():
    first = bootstrap_mean_interval([0.001, 0.002, 0.003], samples=1000)
    second = bootstrap_mean_interval([0.001, 0.002, 0.003], samples=1000)

    assert first == second
    assert first[0] <= 0.002 <= first[1]


def test_five_complete_cycles_pass_relative_and_transport_gates():
    runs = []
    for cycle in range(1, 6):
        runs.extend(
            [
                run("rf-baseline", cycle, missing=60),
                run("ap-silent", cycle, missing=120),
                run("udp-active", cycle, missing=300),
            ]
        )

    report = summarize_experiments(runs)

    assert report["complete_cycles"] == [1, 2, 3, 4, 5]
    assert report["batch_reduction"] == 0.75
    assert all(report["gates"].values())
    assert report["accepted"]


def test_experiment_parser_uses_documented_capture_defaults():
    args = _parser().parse_args(
        [
            "run",
            "--condition",
            "udp-active",
            "--transmitter-port",
            "/dev/ttyUSB0",
            "--receiver-port",
            "/dev/ttyUSB1",
        ]
    )

    assert args.warmup == 30
    assert args.duration == 600
    assert args.listen_port == 5500
    assert args.baud == 921600
