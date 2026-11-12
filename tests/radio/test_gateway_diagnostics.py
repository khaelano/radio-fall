"""Gateway status uses native counters, real delivery windows and explicit unknowns."""

import os
import struct
import time
import zlib
from dataclasses import replace

import pytest
from test_gateway import batch, manager

from fall_detection.presentation.radio.transport_status import (
    format_transport_status,
    receiver_cells,
)
from fall_detection.radio.acquisition.gateway_diagnostics import DeliveryRates
from fall_detection.radio.espnow_config import EspnowTransportConfig


def test_delivery_window_decays_without_new_packets_and_keeps_receivers_separate():
    rates = DeliveryRates()
    rates.observe("rx-1", 80, 1_000_000_000)
    rates.observe("rx-2", 95, 1_500_000_000)
    rates.observe("rx-1", 10, 1_900_000_000)
    assert rates.snapshot(1_900_000_000) == {"rx-1": 90, "rx-2": 95}
    assert rates.snapshot(2_000_000_000) == {"rx-1": 10, "rx-2": 95}
    assert rates.snapshot(3_000_000_000) == {"rx-1": 0, "rx-2": 0}


def test_gateway_delivery_rate_excludes_duplicate_batches_and_failed_recorders(
    tmp_path, monkeypatch
):
    from fall_detection.radio.acquisition import gateway_reader

    now = time.monotonic_ns()
    monkeypatch.setattr(gateway_reader.time, "monotonic_ns", lambda: now)
    m = manager(tmp_path / "ok", lambda *args: None)
    try:
        assert m.accept(batch().encode(), now)
        assert m.accept(batch().encode(), now)
        assert m.accept(batch(receiver=1).encode(), now)
        snapshot = m.diagnostics(now_ns=now)
        assert [r.records_s for r in snapshot.receivers] == [1, 1, 0, 0]
        assert snapshot.records_s == 2
        assert m.diagnostics(now_ns=now + 2_000_000_000).records_s == 0
    finally:
        m.journal.close()

    def failed(*args):
        raise OSError("disk full")

    failed_manager = manager(tmp_path / "failed", failed)
    try:
        with pytest.raises(OSError):
            failed_manager.accept(batch().encode(), now)
        assert failed_manager.diagnostics(now_ns=now).records_s == 0
    finally:
        failed_manager.journal.close()


def configured_manager(tmp_path):
    m = manager(tmp_path, lambda *args: None)
    m.config = EspnowTransportConfig(
        schema_version=7,
        phy="ht20_mcs3_lgi",
        queue_capacity=96,
        slot_ms=125,
        maximum_age_ms=750,
        drain_ms=1000,
        application_acknowledgements=False,
        maximum_retries=0,
    )
    m.profile = replace(m.profile, schema_version=2, nominal_rate_hz=120)
    return m


def test_status_decodes_actual_send_counter_and_flags_stale_reports(tmp_path):
    m = configured_manager(tmp_path)
    try:
        data = bytearray(96)
        data[:4] = b"CGST"
        data[4:8] = bytes((1, 0, 2, 1))
        struct.pack_into("!Q", data, 8, m.run_id)
        struct.pack_into("!II", data, 16, 11, 21)
        struct.pack_into("!IIIHHI", data, 72, 900, 7, 12, 40, 80, 17)
        struct.pack_into("!I", data, 92, zlib.crc32(data[:92]))
        m._event("radio_event", payload_hex=data.hex())
        now = time.monotonic_ns()
        m.gateway_status = {
            "configured": True,
            "received": 400,
            "forwarded": 399,
            "rejected": 2,
            "usb_errors": 1,
            "queued": 3,
        }
        m._gateway_status_ns = now
        snapshot = m.diagnostics(now_ns=now)
        receiver = snapshot.receivers[0]
        assert (
            receiver.send_errors == 17
            and receiver.queued == 40
            and receiver.queue_peak == 80
        )
        assert (
            receiver.expired == 12
            and receiver.dropped == 7
            and receiver.captured == 900
        )
        assert (
            receiver.reported_state == 2
            and receiver.online
            and receiver.diagnostic_loss
        )
        text = format_transport_status(
            snapshot,
            selected_receiver_id=receiver.receiver_id,
            plot_refresh_fps=23,
            ui_fps=24,
        )
        relay_text = format_transport_status(
            replace(snapshot, transmitter_link="espnow_uart"),
            selected_receiver_id=receiver.receiver_id,
            plot_refresh_fps=23,
            ui_fps=24,
        )
        assert relay_text.connection.startswith("Reference C6 relay:")
        assert (
            "120 Hz/receiver" in text.configuration and "125 ms" in text.configuration
        )
        assert "ACK-less" in text.configuration and "MCS3" in text.configuration
        assert "peak 80" in text.detail and "USB errors 1" in text.detail
        assert "diagnostic event loss yes" in text.detail
        assert "sequence gaps" in text.detail and "do not identify" in text.detail
        stale = m.diagnostics(now_ns=now + 4_000_000_000)
        assert not stale.receivers[0].online
        assert (
            "gateway stale"
            in format_transport_status(
                stale, selected_receiver_id=None, plot_refresh_fps=0, ui_fps=24
            ).connection
        )
        # Last counters remain visible, explicitly attached to an old report.
        assert (
            stale.receivers[0].queued == 40 and stale.receivers[0].status_age_s >= 3.9
        )
    finally:
        m.journal.close()


def test_pending_stats_are_not_fabricated_and_failure_overrides_online_status(tmp_path):
    m = configured_manager(tmp_path)
    try:
        snapshot = m.diagnostics()
        assert receiver_cells(snapshot.receivers[0], 96)[5:] == ("pending",) * 4
        assert all(not r.online for r in snapshot.receivers)
        m.failure = "gateway USB disconnected"
        text = format_transport_status(
            m.diagnostics(), selected_receiver_id=None, plot_refresh_fps=24, ui_fps=24
        )
        assert text.connection == "Error: gateway USB disconnected"
        assert "plot 24 FPS" in text.compact and "records/s" in text.compact
        assert "data fps" not in text.compact
    finally:
        m.journal.close()


def test_shared_gateway_panel_switches_selected_row_without_mixing_counters(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.presentation.radio.transport_status import GatewayStatusPanel

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    m = configured_manager(tmp_path)
    try:
        now = time.monotonic_ns()
        order = list(m.readers)
        m._delivery_rates.observe(order[0], 80, now)
        m._delivery_rates.observe(order[1], 90, now)
        panel = GatewayStatusPanel()
        snapshot = m.diagnostics(now_ns=now)
        first = panel.apply(
            snapshot, selected_receiver_id=order[0], plot_refresh_fps=23, ui_fps=24
        )
        assert panel.table.rowCount() == 4
        assert [panel.table.item(i, 0).text() for i in range(4)] == order
        assert (
            panel.table.item(0, 3).text() == "80"
            and panel.table.item(1, 3).text() == "90"
        )
        assert panel.table.item(0, 0).font().bold()
        second = panel.apply(
            snapshot, selected_receiver_id=order[1], plot_refresh_fps=23, ui_fps=24
        )
        assert (
            not panel.table.item(0, 0).font().bold()
            and panel.table.item(1, 0).font().bold()
        )
        assert "170 records/s" in first.compact and "170 records/s" in second.compact
        assert f"{order[1]}: 90/s" in second.compact
        panel.widget.close()
        application.processEvents()
    finally:
        m.journal.close()
