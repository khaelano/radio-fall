"""Gateway status uses real delivery windows and explicit unknowns."""

import os
import time

import pytest
from fake_acquisition import FakeAcquisition

from fall_detection.apps.live.app import parser as _parser
from fall_detection.radio.gateway_diagnostics import DeliveryRates
from fall_detection.radio.live import LiveRadio


def test_delivery_window_decays_without_new_packets_and_keeps_receivers_separate():
    rates = DeliveryRates()
    rates.observe("rx-1", 80, 1_000_000_000)
    rates.observe("rx-2", 95, 1_500_000_000)
    rates.observe("rx-1", 10, 1_900_000_000)
    assert rates.snapshot(1_900_000_000) == {"rx-1": 90, "rx-2": 95}
    assert rates.snapshot(2_000_000_000) == {"rx-1": 10, "rx-2": 95}
    assert rates.snapshot(3_000_000_000) == {"rx-1": 0, "rx-2": 0}


def test_shared_gateway_panel_switches_selected_row_without_mixing_counters(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets

    from fall_detection.apps.common.transport_status import GatewayStatusPanel

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    radio = LiveRadio(
        _parser().parse_args(["--output-dir", str(tmp_path)]),
        acquisition_factory=FakeAcquisition,
    )
    try:
        now = time.monotonic_ns()
        order = list(radio.buffers)
        radio._rates.observe(order[0], 80, now)
        radio._rates.observe(order[1], 90, now)
        panel = GatewayStatusPanel()
        snapshot = radio.diagnostics(now_ns=now)
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
        radio.stop()
