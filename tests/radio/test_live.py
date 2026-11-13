"""Live radio delivery, status and diagnostics over a scripted native acquisition."""

import os
import time

import pytest
from fake_acquisition import FakeAcquisition, item, running_health

from fall_detection.apps.csi_viewer.app import _parser
from fall_detection.presentation.radio.transport_status import (
    format_transport_status,
    receiver_cells,
)
from fall_detection.radio.live import LiveRadio


def make_radio(tmp_path, *arguments, **options):
    args = _parser().parse_args(["--output-dir", str(tmp_path), *arguments])
    return LiveRadio(args, acquisition_factory=FakeAcquisition, **options)


def wait_until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        time.sleep(0.01)


def test_live_radio_configures_native_session_without_opening_hardware(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "serial.Serial", lambda *a, **k: pytest.fail("must not open USB")
    )
    journals = tmp_path / "session"
    radio = make_radio(tmp_path, "--receiver-id", "rx-3", journal_root=lambda: journals)
    assert radio.state.selected_receiver_id == "rx-3"
    assert radio.state.buffer is radio.buffers["rx-3"]
    environment = radio.environment()
    assert environment["radio_profile_fingerprint"] == "8b28a906a0fbcd1f"
    assert len(environment["receiver_bindings"]) == 4
    assert environment["transmitter_link"] == "espnow_uart"
    radio.start()
    acquisition = FakeAcquisition.instances[-1]
    config = acquisition.config
    assert len(config["radio_config"]) == 108 and config["radio_config"][:4] == list(
        b"CGCF"
    )
    assert config["journal_root"] == str(journals)
    assert config["serial_path"] == radio.settings.connection["gateway_port"]
    assert config["bin_hz"] == radio.settings.transport.bin_hz
    assert config["delivery_grace_ms"] == radio.settings.transport.delivery_grace_ms
    radio.stop()
    radio.stop()
    assert acquisition.started == acquisition.stopped == 1
    with pytest.raises(RuntimeError, match="starts once"):
        radio.start()


def test_invalid_receiver_is_rejected_before_creating_acquisition(tmp_path):
    args = _parser().parse_args(["--receiver-id", "unknown"])
    with pytest.raises(ValueError, match="--receiver-id"):
        LiveRadio(
            args,
            acquisition_factory=lambda config: pytest.fail("must not create"),
        )


def test_records_reach_sink_and_receiver_buffer_and_stop_drains_queue(tmp_path):
    delivered = []
    radio = make_radio(tmp_path, record_sink=lambda r, t: delivered.append((r, t)))
    radio.start()
    acquisition = FakeAcquisition.instances[-1]
    acquisition.push(item(1, 0), item(2, 1))
    wait_until(lambda: len(delivered) == 2)
    acquisition.push(item(3, 2))
    radio.stop()
    assert [r.sequence for r, _ in delivered] == [1, 2, 3]
    record, arrival = delivered[0]
    assert arrival == 6_000
    assert (record.run_id, record.transmitter_boot_id, record.receiver_boot_id) == (
        123,
        11,
        21,
    )
    assert record.capture_host_monotonic_ns == 5_000
    assert record.capture_clock_uncertainty_us == 12.5
    assert record.transport == "espnow_gateway"
    assert record.native_processed_ns == 6_010
    assert radio.buffers["rx-1"].received_records == 1
    assert radio.buffers["rx-2"].received_records == 1
    assert radio.buffers["rx-3"].received_records == 1


def test_storage_failure_is_reported_once_and_display_continues(tmp_path):
    messages, interruptions = [], []

    def sink(record, arrival):
        raise OSError("disk full")

    radio = make_radio(
        tmp_path,
        record_sink=sink,
        on_status=lambda *v: messages.append(v),
        on_interruption=interruptions.append,
    )
    radio.start()
    FakeAcquisition.instances[-1].push(item(1, 0), item(2, 0))
    radio.stop()
    assert interruptions == ["record storage failed: disk full"]
    assert ("record storage failed: disk full", False) in messages
    assert radio.failure == "record storage failed: disk full"
    assert radio.buffers["rx-1"].received_records == 2


def test_without_sink_records_are_written_to_receiver_csv(tmp_path):
    radio = make_radio(tmp_path)
    radio.start()
    FakeAcquisition.instances[-1].push(item(1, 1))
    radio.stop()
    (path,) = (tmp_path / "rx-2").glob("csi_*.csv")
    lines = path.read_text().splitlines()
    assert lines[1].startswith("CSI_DATA,1,")
    (timing,) = (tmp_path / "rx-2").glob("radio_timing_*.csv")
    assert timing.read_text().splitlines()[1].endswith(",6000")


def test_health_drives_status_interruptions_and_readiness(tmp_path):
    messages, interruptions = [], []
    radio = make_radio(
        tmp_path,
        on_status=lambda *v: messages.append(v),
        on_interruption=interruptions.append,
    )
    radio.start()
    acquisition = FakeAcquisition.instances[-1]
    try:
        assert not radio.clock_sync_ready and not radio.preflight_ready
        acquisition.health_value = running_health()
        wait_until(lambda: radio.preflight_ready)
        assert radio.failure is None and radio.preview_ready
        assert messages[-1] == ("Radio live; sensing", True)
        acquisition.health_value = {
            **running_health(),
            "session": {"state": "restarting", "error": "gateway status timed out"},
            "failure": "gateway status timed out",
        }
        wait_until(lambda: interruptions == ["gateway status timed out"])
        assert radio.failure == "gateway status timed out"
        assert not radio.clock_sync_ready and not radio.all_live
        assert messages[-1] == (
            "Radio interrupted; reconnecting: gateway status timed out",
            False,
        )
        acquisition.health_value = {**running_health(), "runs": 2}
        wait_until(lambda: messages[-1][1])
        assert messages[-1][0] == "Radio recovered; sensing resumed with fresh timing"
        acquisition.health_value = running_health(status_age_ns=3_000_000_000)
        wait_until(lambda: not radio.all_live)
        acquisition.health_value = {
            **running_health(),
            "queue": {"pending": 10_000},
        }
        wait_until(lambda: not radio.preview_ready)
    finally:
        radio.stop()


def test_stop_failure_still_drains_records_and_propagates(tmp_path):
    delivered = []
    radio = make_radio(tmp_path, record_sink=lambda r, t: delivered.append(r))
    radio.start()
    acquisition = FakeAcquisition.instances[-1]
    acquisition.stop_error = RuntimeError("radio acquisition did not stop")
    acquisition.push(item(1, 0))
    with pytest.raises(RuntimeError, match="did not stop"):
        radio.stop()
    assert [r.sequence for r in delivered] == [1]
    radio.stop()


def test_diagnostics_report_native_counters_and_explicit_unknowns(tmp_path):
    radio = make_radio(tmp_path)
    radio.start()
    acquisition = FakeAcquisition.instances[-1]
    try:
        pending = radio.diagnostics()
        assert receiver_cells(pending.receivers[0], 96)[5:] == ("pending",) * 4
        assert all(not r.online for r in pending.receivers)
        health = running_health()
        health["session"]["receivers"][0] = {
            "slot": 0,
            "status_age_ns": 100_000_000,
            "status": {
                "state": 2,
                "captured": 900,
                "dropped": 7,
                "expired": 12,
                "queued": 40,
                "peak": 80,
                "send_errors": 17,
                "queue_event_loss": True,
            },
        }
        health["receivers"][0] = {
            "records": 5,
            "missing_sequences": 3,
            "transport_missing": 2,
            "batch_missing": 1,
            "last_sequence": 99,
            "last_record_age_ns": 0,
        }
        health["session"]["gateway"] = {
            "configured": True,
            "received": 400,
            "forwarded": 399,
            "rejected": 2,
            "usb_errors": 1,
            "queued": 3,
        }
        acquisition.health_value = health
        wait_until(lambda: radio.clock_sync_ready)
        snapshot = radio.diagnostics()
        receiver = snapshot.receivers[0]
        assert (receiver.send_errors, receiver.queued, receiver.queue_peak) == (
            17,
            40,
            80,
        )
        assert (receiver.expired, receiver.dropped, receiver.captured) == (12, 7, 900)
        assert receiver.reported_state == 2 and receiver.online
        assert receiver.diagnostic_loss and receiver.records == 5
        assert (
            receiver.sequence_gaps,
            receiver.transport_gaps,
            receiver.batch_gaps,
        ) == (
            3,
            2,
            1,
        )
        assert snapshot.clock_uncertainty_us == 40.0 and snapshot.reference_ready
        assert snapshot.usb_errors == 1 and snapshot.received_envelopes == 400
        text = format_transport_status(
            snapshot,
            selected_receiver_id=receiver.receiver_id,
            plot_refresh_fps=23,
            ui_fps=24,
        )
        assert text.connection.startswith("Reference C6 relay:")
        assert "peak 80" in text.detail and "USB errors 1" in text.detail
        stale = running_health(status_age_ns=4_000_000_000)
        acquisition.health_value = stale
        wait_until(lambda: not radio.diagnostics().receivers[0].online)
    finally:
        radio.stop()


def test_telemetry_snapshot_uses_native_totals(tmp_path):
    radio = make_radio(tmp_path)
    radio.start()
    acquisition = FakeAcquisition.instances[-1]
    acquisition.health_value = {
        **running_health(),
        "totals": {
            "records": 10,
            "batches": 4,
            "host_missing_sequences": 2,
            "transport_missing": 1,
            "transport_reordered": 1,
            "batch_missing": 0,
            "batch_reordered": 0,
            "receiver_restarts": 1,
        },
    }
    try:
        wait_until(lambda: radio.telemetry_snapshot().records == 10)
        snapshot = radio.telemetry_snapshot()
        assert (snapshot.batches, snapshot.host_missing_sequences) == (4, 2)
        assert snapshot.receiver_restarts == 1 and snapshot.malformed == 0
    finally:
        radio.stop()


def test_live_dashboard_limits_diagnostics_and_updates_selection_immediately(
    tmp_path, monkeypatch
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.presentation.radio.live import LiveDashboard

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    radio = make_radio(tmp_path)
    calls = []
    original = radio.diagnostics
    monkeypatch.setattr(radio, "diagnostics", lambda: calls.append(True) or original())
    dashboard = LiveDashboard(radio, fps=24)
    try:
        for frame in range(24):
            dashboard.refresh(now=frame / 24)
        assert len(calls) == 4
        radio.state.select_receiver("rx-2")
        text = dashboard.refresh(now=0.97)
        assert len(calls) == 5
        assert "rx-2" in text.compact
    finally:
        dashboard.panel.widget.close()
        application.processEvents()
