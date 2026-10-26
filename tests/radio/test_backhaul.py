from __future__ import annotations

from fall_detection.radio.acquisition.telemetry import (
    BackhaulTelemetrySnapshot,
    GatewayTelemetry,
    ReceiverTelemetry,
    TransmitterTelemetry,
    telemetry_delta,
)
from fall_detection.radio.acquisition.wire import ReceiverStats
from fall_detection.radio.experiments.backhaul import (
    BACKHAUL_PROFILES,
    _parser,
    build_backhaul_summary,
    summarize_backhaul,
)


def snapshot(
    timestamp: int,
    *,
    boot_id: int = 7,
    records: int = 0,
    attempts: int = 0,
    accepted: int = 0,
    sensing_missing: int = 0,
) -> BackhaulTelemetrySnapshot:
    return BackhaulTelemetrySnapshot(
        captured_monotonic_ns=timestamp,
        records=records,
        batches=records // 2,
        host_missing_sequences=0,
        transport_missing=0,
        transport_reordered=0,
        batch_missing=0,
        batch_reordered=0,
        malformed=0,
        foreign=0,
        receiver_restarts=0,
        serial_frames=records // 2,
        receiver_boot_id=boot_id,
        receiver_stats=ReceiverStats(
            accepted,
            sensing_missing,
            0,
            0,
            0,
            0,
            records // 2,
            records // 2,
            records,
            0,
        ),
        transmitter_stats=TransmitterTelemetry(1000, attempts, 0, attempts, 0),
        gateway_stats=GatewayTelemetry(1000, records // 2, 0, 0, records // 2, 0),
    )


def test_backhaul_delta_handles_uint32_wrap_and_rates():
    start = snapshot(1_000_000_000, records=0, attempts=0xFFFFFFFF)
    end = snapshot(2_000_000_000, records=2, attempts=1)

    delta = end.delta(start)

    assert delta["complete"]
    assert delta["values"]["records"] == 2
    assert delta["values"]["transmitter_attempts"] == 2
    assert delta["values"]["effective_records_per_second"] == 2.0


def test_backhaul_delta_marks_restart_and_unavailable_stages():
    start = snapshot(1_000_000_000)
    end = snapshot(2_000_000_000, boot_id=8)
    end = BackhaulTelemetrySnapshot(**{**end.__dict__, "gateway_stats": None})

    delta = end.delta(start)

    assert not delta["complete"]
    assert any("restarted" in warning for warning in delta["warnings"])
    assert any("gateway statistics unavailable" in warning for warning in delta["warnings"])
    assert telemetry_delta(start, None)["values"] is None


def test_backhaul_summary_declares_profile_and_stage_metrics():
    profile = BACKHAUL_PROFILES["final-50-mcs0-20"]
    summary = build_backhaul_summary(
        profile=profile,
        cycle=1,
        warmup_seconds=30,
        duration_seconds=10,
        geometry_notes="fixed tripod",
        start=snapshot(0),
        end=snapshot(10_000_000_000, records=500, attempts=500, accepted=500),
    )

    assert summary["profile"]["nominal_rate_hz"] == 50
    assert summary["stages"]["delivered_records_per_second"] == 50
    assert summary["geometry_notes"] == "fixed tripod"


def test_backhaul_parser_and_five_cycle_summary():
    args = _parser().parse_args(
        [
            "backhaul-run",
            "--profile",
            "final-50-mcs0-20",
            "--gateway-port",
            "/dev/ttyACM0",
        ]
    )
    assert args.duration == 600
    assert args.warmup == 30

    runs = []
    for cycle in range(1, 6):
        for name, profile in BACKHAUL_PROFILES.items():
            runs.append(
                build_backhaul_summary(
                    profile=profile,
                    cycle=cycle,
                    warmup_seconds=30,
                    duration_seconds=10,
                    geometry_notes="",
                    start=snapshot(0),
                    end=snapshot(10_000_000_000, records=500, attempts=profile.nominal_rate_hz * 10, accepted=500),
                )
            )

    report = summarize_backhaul(runs)

    assert report["complete_cycles"] == [1, 2, 3, 4, 5]
    assert report["accepted"]
