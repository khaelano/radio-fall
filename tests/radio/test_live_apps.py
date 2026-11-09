"""Run both complete Qt applications with offline acquisition and real windows."""

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtWidgets

from fall_detection.collection.capture import SessionMetadata
from fall_detection.radio.acquisition.gateway_reader import GatewayReceiverManager
from fall_detection.radio.live import LiveRadio


@pytest.mark.parametrize("application_name", ["viewer", "collector"])
@pytest.mark.parametrize("fail_start", [False, True])
def test_complete_application_closes_inputs_and_windows(
    application_name, fail_start, tmp_path, monkeypatch
):
    if application_name == "viewer":
        from fall_detection.radio.visualization import app as command

        title = "CSI viewer"
    else:
        from fall_detection.collection import app as command

        title = "Collection operator"
        monkeypatch.setattr(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            lambda *args: (
                str(command.DEFAULT_PROTOCOL.with_name("fall_simple.json")),
                "",
            ),
        )
        monkeypatch.setattr(
            command,
            "MetadataDialog",
            lambda widgets, protocol: SimpleNamespace(
                get=lambda: SessionMetadata("test-participant"),
                block_ids=lambda: (protocol.blocks[0][0],),
            ),
        )
    managers = []

    class OfflineManager(GatewayReceiverManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.stop_calls = 0
            managers.append(self)

        def start(self):
            if fail_start:
                raise RuntimeError("partial startup failed")

        def stop(self):
            self.stop_calls += 1

    monkeypatch.setattr(
        command,
        "LiveRadio",
        lambda args, **kwargs: LiveRadio(
            args,
            manager_factory=OfflineManager,
            **kwargs,
        ),
    )
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    closed = []
    timed_out = []
    close_timer = QtCore.QTimer()
    close_timer.setSingleShot(True)

    def close_console():
        for widget in application.topLevelWidgets():
            if widget.isVisible() and widget.windowTitle().startswith(title):
                assert any(
                    tabs.tabText(index) == "CSI gaps"
                    for tabs in widget.findChildren(QtWidgets.QTabWidget)
                    for index in range(tabs.count())
                )
                closed.append(True)
                widget.close()
                break

    close_timer.timeout.connect(close_console)
    close_timer.start(200)
    watchdog = QtCore.QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: timed_out.append(True) or application.quit())
    watchdog.start(2000)
    try:
        if fail_start:
            with pytest.raises(RuntimeError, match="partial startup"):
                command.main(["--output-dir", str(tmp_path)])
        else:
            assert command.main(["--output-dir", str(tmp_path)]) == 0
            assert closed and not timed_out
        assert managers[0].stop_calls == 1
        assert not any(widget.isVisible() for widget in application.topLevelWidgets())
        if application_name == "collector":
            manifests = list(tmp_path.glob("*/session.json"))
            assert len(manifests) == 1
            manifest = json.loads(manifests[0].read_text())
            assert manifest["status"] == "ended"
            assert manifest["protocol_id"] == "fall-collection-simple-v2"
            assert len(manifest["environment"]["receiver_bindings"]) == 4
    finally:
        close_timer.stop()
        watchdog.stop()
        for widget in application.topLevelWidgets():
            widget.close()
        application.processEvents()


def test_canceling_collection_setup_releases_unstarted_camera(tmp_path, monkeypatch):
    from fall_detection.collection import app as command
    from fall_detection.collection import video

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    closed = []
    monkeypatch.setattr(
        video,
        "VideoRecorder",
        lambda config: SimpleNamespace(
            config=config,
            stop=lambda: closed.append(True),
            start=lambda: pytest.fail("camera must not start before setup is accepted"),
        ),
    )
    monkeypatch.setattr(
        command, "MetadataDialog", lambda *args: SimpleNamespace(get=lambda: None)
    )
    monkeypatch.setattr(
        command,
        "choose_protocol",
        lambda *args: pytest.fail("explicit protocol must skip picker"),
    )
    assert (
        command.main(
            [
                "--output-dir",
                str(tmp_path),
                "--video-device",
                "/dev/video-test",
                "--protocol",
                str(command.DEFAULT_PROTOCOL),
            ]
        )
        == 0
    )
    assert closed == [True]
    assert not list(tmp_path.iterdir())
    application.processEvents()


def test_canceling_scenario_file_selection_does_not_initialize_inputs(
    tmp_path, monkeypatch
):
    from fall_detection.collection import app as command
    from fall_detection.collection import video

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getOpenFileName", lambda *args: ("", "")
    )
    monkeypatch.setattr(
        command, "LiveRadio", lambda *args, **kwargs: pytest.fail("radio initialized")
    )
    monkeypatch.setattr(
        video, "VideoRecorder", lambda *args: pytest.fail("camera initialized")
    )

    assert (
        command.main(
            ["--output-dir", str(tmp_path), "--video-device", "/dev/video-test"]
        )
        == 0
    )
    assert not list(tmp_path.iterdir())
    application.processEvents()


def test_scenario_file_selection_recovers_from_invalid_json(tmp_path, monkeypatch):
    from fall_detection.collection import app as command
    from fall_detection.collection.views.dialogs import choose_protocol

    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken")
    simple = command.DEFAULT_PROTOCOL.with_name("fall_simple.json")
    selections = iter([invalid, simple])
    warnings = []
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *args: (str(next(selections)), ""),
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "warning", lambda *args: warnings.append(args[2])
    )

    protocol = choose_protocol(QtWidgets, command.DEFAULT_PROTOCOL)

    assert protocol.protocol_id == "fall-collection-simple-v2"
    assert len(protocol.trials) == 232
    assert len(warnings) == 1 and "invalid JSON" in warnings[0]
    application.processEvents()
