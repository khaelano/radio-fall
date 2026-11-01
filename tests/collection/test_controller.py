from __future__ import annotations

from pathlib import Path
import json

import pytest

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionState,
)
from fall_detection.collection.protocol import protocol_from_mapping
from fall_detection.radio.acquisition.telemetry import (
    BackhaulTelemetrySnapshot,
    GatewayTelemetry,
    TransmitterTelemetry,
)
from fall_detection.radio.acquisition.wire import ReceiverStats


def protocol():
    return {
        "schema_version": 1,
        "protocol_id": "test",
        "title": "Test protocol",
        "defaults": {
            "countdown_seconds": 1,
            "action_seconds": 2,
            "recovery_seconds": 1,
        },
        "blocks": [
            {
                "id": "block",
                "title": "Block",
                "scenarios": [
                    {
                        "id": "one",
                        "activity_label": "walk",
                        "title": "Walk",
                        "instruction": "Walk forward",
                    }
                ],
            }
        ],
    }


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def ready_health() -> HealthSnapshot:
    return HealthSnapshot(
        radio_live=True,
        storage_ready=True,
        clock_sync_ready=True,
    )


def make_controller(tmp_path: Path, clock: FakeClock) -> SessionController:
    return SessionController(
        protocol_from_mapping(protocol()),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1_000_000_000),
        session_id_factory=lambda: "session",
        environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}},
    )


def start_ready(controller: SessionController) -> None:
    controller.start_session(SessionMetadata("participant-01"))
    controller.update_health(ready_health())


def test_controller_runs_timed_trial_and_writes_bundle(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    start_ready(controller)

    snapshot = controller.dispatch(OperatorCommand.START_TRIAL)
    assert snapshot.state is SessionState.COUNTDOWN
    assert snapshot.trial.ordinal == 1

    clock.advance(1)
    assert controller.tick().state is SessionState.ACTION
    clock.advance(2)
    assert controller.tick().state is SessionState.RECOVERY
    clock.advance(1)
    assert controller.tick().state is SessionState.REVIEW

    controller.dispatch(OperatorCommand.ACCEPT)
    assert controller.state is SessionState.COMPLETE
    attempt_dir = tmp_path / "session" / "trials" / "001_one" / "attempt_01"
    assert (attempt_dir / "attempt.json").exists()
    assert (attempt_dir / "receivers" / "rx-1" / "csi.csv").exists()
    session_manifest = json.loads((tmp_path / "session" / "session.json").read_text())
    attempt_manifest = json.loads((attempt_dir / "attempt.json").read_text())
    assert session_manifest["artifact_schema_version"] == 2
    assert attempt_manifest["artifact_schema_version"] == 2
    assert attempt_manifest["status"] == "accepted"


def test_controller_requires_all_inputs_before_start(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    controller.start_session(SessionMetadata("participant-01"))

    with pytest.raises(RuntimeError, match="health"):
        controller.dispatch(OperatorCommand.START_TRIAL)


def test_lost_input_marks_attempt_invalid_and_retry_gets_new_number(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)

    controller.update_health(
        HealthSnapshot(
            radio_live=False,
            radio_detail="radio disconnected",
        )
    )
    assert controller.state is SessionState.REVIEW
    attempt = tmp_path / "session" / "trials" / "001_one" / "attempt_01" / "attempt.json"
    assert '"status": "invalid"' in attempt.read_text()

    controller.dispatch(OperatorCommand.RETRY)
    controller.update_health(ready_health())
    controller.dispatch(OperatorCommand.START_TRIAL)
    assert controller.state is SessionState.COUNTDOWN
    assert (
        tmp_path / "session" / "trials" / "001_one" / "attempt_02" / "attempt.json"
    ).exists()


def test_invalid_attempt_cannot_be_accepted(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    controller.update_health(HealthSnapshot(radio_live=False))

    with pytest.raises(RuntimeError, match="cannot be accepted"):
        controller.dispatch(OperatorCommand.ACCEPT)


def test_subscribers_receive_the_same_immutable_snapshot(tmp_path: Path):
    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    first = []
    second = []
    controller.subscribe(first.append)
    controller.subscribe(second.append)
    controller.start_session(SessionMetadata("participant-01"))

    assert first[-1] == second[-1]
    assert first[-1].state is SessionState.READY


def test_attempt_persists_boot_aware_radio_telemetry_delta(tmp_path: Path):
    clock = FakeClock()

    def telemetry(timestamp: int, records: int, boot_id: int = 7):
        return BackhaulTelemetrySnapshot(
            captured_monotonic_ns=timestamp,
            records=records,
            batches=records,
            host_missing_sequences=0,
            transport_missing=0,
            transport_reordered=0,
            batch_missing=0,
            batch_reordered=0,
            malformed=0,
            foreign=0,
            receiver_restarts=0,
            serial_frames=records,
            receiver_boot_id=boot_id,
            receiver_stats=ReceiverStats(records, 0, 0, 0, 0, 0, records, records, records, 0),
            transmitter_stats=TransmitterTelemetry(1000, records, 0, records, 0),
            gateway_stats=GatewayTelemetry(1000, records, 0, 0, records, 0),
        )

    snapshots = iter((telemetry(0, 0), telemetry(5_000_000_000, 5)))
    controller = SessionController(
        protocol_from_mapping(protocol()),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1_000_000_000),
        session_id_factory=lambda: "session",
        telemetry_provider=lambda: next(snapshots),
        environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}},
    )
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(1)
    controller.tick()
    clock.advance(2)
    controller.tick()
    clock.advance(1)
    controller.tick()
    controller.dispatch(OperatorCommand.ACCEPT)

    payload = json.loads(
        (
            tmp_path / "session" / "trials" / "001_one" / "attempt_01" / "attempt.json"
        ).read_text()
    )
    assert payload["radio_telemetry_delta"]["complete"]
    assert payload["radio_telemetry_delta"]["values"]["records"] == 5


def test_ble_delayed_records_route_by_capture_time_across_attempts(tmp_path: Path):
    from dataclasses import replace
    from fall_detection.radio.acquisition.protocol import CsiRecord

    clock = FakeClock()
    controller = SessionController(
        protocol_from_mapping(protocol()), tmp_path, clock=clock,
        monotonic_ns=lambda: int(clock.value*1_000_000_000),
        session_id_factory=lambda: "ble-session",
        environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"},
                     "transport": "ble", "ble_transport": {"drain_ms": 300}},
    )
    start_ready(controller)
    controller.dispatch(OperatorCommand.START_TRIAL)
    clock.advance(1)
    controller.dispatch(OperatorCommand.ABORT)
    controller.dispatch(OperatorCommand.RETRY)
    clock.advance(0.01)
    controller.dispatch(OperatorCommand.START_TRIAL)
    record = CsiRecord(1, "00:11:22:33:44:66", -40, -95, 100,
        (1+2j,), receiver_mac="00:11:22:33:44:55", csi_length=2,
        run_id=123, transmitter_boot_id=11, receiver_boot_id=21,
        capture_host_monotonic_ns=900_000_000)
    controller.write_radio(record, 1_050_000_000)
    controller.write_radio(replace(record, sequence=2, capture_host_monotonic_ns=1_020_000_000),
                           1_060_000_000)
    # Alignment failures and arrivals beyond the previous attempt's drain
    # deadline cannot become fresh observations in the new attempt.
    controller.write_radio(replace(record, sequence=3, capture_host_monotonic_ns=None), 1_070_000_000)
    clock.advance(0.4)
    controller.tick()
    controller.write_radio(replace(record, sequence=4), 1_410_000_000)
    controller.dispatch(OperatorCommand.ABORT)
    controller.flush_radio()
    root = controller.session_root/"trials"/"001_one"
    first = (root/"attempt_01"/"receivers"/"rx-1"/"csi.csv").read_text().splitlines()
    second = (root/"attempt_02"/"receivers"/"rx-1"/"csi.csv").read_text().splitlines()
    assert len(first) == 2 and first[1].startswith("CSI_DATA,1,")
    assert len(second) == 2 and second[1].startswith("CSI_DATA,2,")
    controller.dispatch(OperatorCommand.END_SESSION)
