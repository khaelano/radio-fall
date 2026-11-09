"""Shared desktop acquisition setup and diagnostics pacing."""

import os

import pytest

from fall_detection.radio.acquisition.gateway_reader import GatewayReceiverManager
from fall_detection.radio.live import LiveRadio
from fall_detection.radio.visualization.app import _parser


class OfflineManager(GatewayReceiverManager):
    def start(self):
        self.started = True

    def stop(self):
        self.stop_calls = getattr(self, "stop_calls", 0) + 1


def test_live_radio_binds_shared_buffers_without_opening_hardware(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "serial.Serial", lambda *a, **k: pytest.fail("must not open USB")
    )
    args = _parser().parse_args(
        ["--output-dir", str(tmp_path), "--receiver-id", "rx-3"]
    )
    messages = []
    radio = LiveRadio(
        args, manager_factory=OfflineManager, on_status=lambda *v: messages.append(v)
    )
    assert radio.state.selected_receiver_id == "rx-3"
    assert radio.state.buffer is radio.manager.readers["rx-3"].buffer
    radio.manager.on_status("ready", True)
    assert radio.state.get_status() == ("ready", True)
    assert messages == [("ready", True)]
    environment = radio.environment()
    assert environment["radio_profile_fingerprint"] == "8b28a906a0fbcd1f"
    assert len(environment["receiver_bindings"]) == 4
    assert environment["transmitter_link"] == "espnow_uart"
    radio.start()
    radio.stop()
    radio.stop()
    assert radio.manager.stop_calls == 1
    with pytest.raises(RuntimeError, match="cannot be restarted"):
        radio.start()


def test_invalid_receiver_is_rejected_before_creating_acquisition():
    args = _parser().parse_args(["--receiver-id", "unknown"])
    with pytest.raises(ValueError, match="--receiver-id"):
        LiveRadio(
            args,
            manager_factory=lambda *a, **k: pytest.fail("must not create acquisition"),
        )


def test_shutdown_failure_can_be_retried():
    radio = LiveRadio(_parser().parse_args([]), manager_factory=OfflineManager)
    calls = []

    def stop():
        calls.append(True)
        if len(calls) == 1:
            raise TimeoutError("worker still draining")

    radio.manager.stop = stop
    with pytest.raises(TimeoutError):
        radio.stop()
    radio.stop()
    radio.stop()
    assert len(calls) == 2


def test_live_dashboard_limits_diagnostics_and_updates_selection_immediately(
    monkeypatch,
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6 import QtWidgets
    from fall_detection.radio.visualization.live import LiveDashboard

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    radio = LiveRadio(_parser().parse_args([]), manager_factory=OfflineManager)
    calls = []
    original = radio.manager.diagnostics
    monkeypatch.setattr(
        radio.manager, "diagnostics", lambda: calls.append(True) or original()
    )
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
