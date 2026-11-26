"""Run both complete Qt applications with offline acquisition and real windows."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from fake_acquisition import FakeAcquisition
from PySide6 import QtCore, QtWidgets

from fall_detection.collection.capture import SessionMetadata
from fall_detection.protocol.loader import load_protocol, select_blocks
from fall_detection.radio.live import LiveRadio


@pytest.fixture
def application():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
    for widget in app.topLevelWidgets():
        widget.close()
    app.processEvents()
    app.setQuitOnLastWindowClosed(True)


def offline_radio(managers, *, fail_start=False):
    class OfflineAcquisition(FakeAcquisition):
        def __init__(self, config_json):
            super().__init__(config_json)
            managers.append(self)

        def start(self):
            if fail_start:
                raise RuntimeError("partial startup failed")
            super().start()

    return lambda args, **kwargs: LiveRadio(
        args, acquisition_factory=OfflineAcquisition, **kwargs
    )


def visible(application, title):
    return [
        widget
        for widget in application.topLevelWidgets()
        if widget.isVisible() and widget.windowTitle().startswith(title)
    ]


def run_steps(application, steps, *, interval_ms=150, timeout_ms=8000):
    """Run each step on a timer until it returns True; quit after the last."""
    pending = list(steps)
    timed_out = []
    timer = QtCore.QTimer()

    def advance():
        if pending and pending[0]():
            pending.pop(0)
        if not pending:
            timer.stop()

    timer.timeout.connect(advance)
    timer.start(interval_ms)
    watchdog = QtCore.QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: timed_out.append(True) or application.quit())
    watchdog.start(timeout_ms)
    return timer, watchdog, pending, timed_out


# -- csi-live ----------------------------------------------------------------


@pytest.mark.parametrize("fail_start", [False, True])
def test_live_view_closes_inputs_and_windows(
    fail_start, tmp_path, monkeypatch, application
):
    from fall_detection.apps.live import app as command

    managers = []
    monkeypatch.setattr(
        command, "LiveRadio", offline_radio(managers, fail_start=fail_start)
    )
    seen = []

    def close_console():
        windows = visible(application, "CSI live")
        if not windows:
            return False
        window = windows[0]
        tabs = [
            tabs.tabText(index)
            for tabs in window.findChildren(QtWidgets.QTabWidget)
            for index in range(tabs.count())
        ]
        banners = [
            label.text()
            for label in window.findChildren(QtWidgets.QLabel)
            if label.isVisible() and "Could not start" in label.text()
        ]
        seen.append((tabs, banners))
        window.close()
        return True

    timer, watchdog, pending, timed_out = run_steps(application, [close_console])
    try:
        assert command.main(["--output-dir", str(tmp_path)]) == 0
    finally:
        timer.stop()
        watchdog.stop()
    assert not pending and not timed_out
    tabs, banners = seen[0]
    if fail_start:
        # The error stays in the window; the user can fix it and retry.
        assert banners and "partial startup failed" in banners[0]
    else:
        assert "CSI gaps" in tabs and not banners
    assert managers[0].stopped == 1
    assert not any(widget.isVisible() for widget in application.topLevelWidgets())


class FakeDetector:
    instances: ClassVar[list] = []

    def __init__(self, config):
        self.config = config
        self.started = self.stopped = 0
        FakeDetector.instances.append(self)

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def poll(self, maximum):
        return json.dumps(
            [{"model_id": "cnn-4s", "score": 0.9, "end_ns": 5, "center_ns": 4}]
        )

    def health(self):
        return json.dumps(
            {"state": "running", "clock_ns": 5, "generation": 1, "source": "gateway"}
        )

    def stream(self, after_seq, limit=4096):
        metadata = {"seq": after_seq, "generation": [], "round": [], "receiver": []}
        return json.dumps(metadata), b""

    def preview(self, model, after_end_ns=0):
        return None


def test_live_window_hands_the_gateway_between_view_and_detection(
    tmp_path, application
):
    from fall_detection.apps.live.app import parser
    from fall_detection.apps.live.window import LiveWindow

    model_root = tmp_path / "models"
    (model_root / "cnn").mkdir(parents=True)
    (model_root / "cnn" / "manifest.json").write_text(
        json.dumps(
            {
                "exports": [
                    {
                        "model": "cnn",
                        "duration_seconds": 4,
                        "sha256": "a",
                        "normalizer_sha256": "b",
                    }
                ]
            }
        )
    )
    (model_root / "cnn" / "cnn-4s.onnx").touch()
    args = parser().parse_args(
        ["--output-dir", str(tmp_path / "out"), "--model-root", str(model_root)]
    )
    managers = []
    configs = []

    def build_config(args, models):
        output = tmp_path / "out" / f"native-{len(configs)}"
        configs.append(models)
        return {
            "models": models,
            "model_root": str(model_root),
            "output_dir": str(output),
            "hop_ms": 250,
            "delivery_grace_ms": 900,
            "minimum_coverage": 0.7,
        }

    FakeDetector.instances.clear()
    live = LiveWindow(
        args,
        radio_factory=offline_radio(managers),
        backend_factory=FakeDetector,
        build_config=build_config,
        inference_problem=None,
        source_text="gateway",
    )
    try:
        assert live.model_actions["cnn-4s"].isEnabled()
        # A model without an exported bundle cannot be chosen.
        assert not live.model_actions["gru-6s"].isEnabled()
        live.apply()
        assert live.running == () and managers[0].started == 1
        assert live.mode_badge.text() == "LIVE VIEW"
        assert not live.apply_button.isEnabled()

        live.set_selection(["cnn-4s"])
        assert live.apply_button.text() == "Start detection"
        live.apply()
        # The live view released the gateway before the detector opened it.
        assert managers[0].stopped == 1
        assert live.running == ("cnn-4s",) and configs == [["cnn-4s"]]
        assert FakeDetector.instances[0].started == 1
        assert live.pages.currentWidget() is live.detection.widget
        assert live.mode_badge.text().startswith("DETECTING")
        live.tick()
        assert live.detection.table.item(0, 1).text() == "fall candidate"

        live.set_selection([])
        assert live.apply_button.text() == "Switch to live view"
        live.apply()
        assert FakeDetector.instances[0].stopped == 1
        assert live.running == () and managers[1].started == 1
        assert live.pages.currentWidget() is live.view_page
    finally:
        live.shutdown()
    assert managers[1].stopped == 1


def test_live_selection_text_names_the_next_action():
    from fall_detection.apps.live.window import apply_text, selection_text

    assert selection_text(()) == "None — view live data"
    assert selection_text(("cnn-4s", "gru-4s")) == "cnn-4s +1"
    assert apply_text((), ("cnn-4s",)) == "Start detection"
    assert apply_text(("cnn-4s",), ()) == "Switch to live view"
    assert apply_text(("cnn-4s",), ("gru-4s",)) == "Restart with selection"
    assert apply_text(None, ()) == "Start live view"


def test_live_outputs_stay_outside_dvc_tracked_raw_data():
    from fall_detection.apps.live.app import parser
    from fall_detection.apps.live.detection import DETECTOR_OUTPUT_ROOT
    from fall_detection.apps.live.window import view_output_dir

    output = view_output_dir(parser().parse_args([]))
    assert output == Path("data/experiments/viewer")
    for path in (output, DETECTOR_OUTPUT_ROOT):
        assert not path.is_relative_to("data/raw")


# -- csi-sessions -------------------------------------------------------------


def _first_block_plan(tmp_path, command):
    from fall_detection.apps.sessions.collector.plan import SessionPlan

    protocol = load_protocol(command.DEFAULT_PROTOCOL)
    return SessionPlan(
        protocol=select_blocks(protocol, (protocol.blocks[0][0],)),
        metadata=SessionMetadata("test-participant"),
        output_dir=tmp_path,
    )


@pytest.mark.parametrize("fail_start", [False, True])
def test_new_session_records_archives_and_returns_to_the_browser(
    fail_start, tmp_path, monkeypatch, application
):
    from fall_detection.apps.sessions import app as command
    from fall_detection.apps.sessions import window as window_module
    from fall_detection.apps.sessions.collector import run as run_module

    managers = []
    errors = []
    monkeypatch.setattr(
        command, "LiveRadio", offline_radio(managers, fail_start=fail_start)
    )
    plan = _first_block_plan(tmp_path, run_module)
    monkeypatch.setattr(
        window_module,
        "NewSessionDialog",
        lambda *args, **kwargs: SimpleNamespace(get=lambda: plan),
    )
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "critical", lambda *args: errors.append(args[2])
    )
    browser = []

    def close_operator():
        if fail_start:
            return bool(errors)
        consoles = visible(application, "Collection operator")
        if not consoles:
            return False
        assert any(
            tabs.tabText(index) == "CSI gaps"
            for tabs in consoles[0].findChildren(QtWidgets.QTabWidget)
            for index in range(tabs.count())
        )
        assert not visible(application, "CSI sessions")
        consoles[0].close()
        return True

    def close_browser():
        windows = visible(application, "CSI sessions")
        if not windows:
            return False
        browser.append(windows[0])
        windows[0].close()
        return True

    timer, watchdog, pending, timed_out = run_steps(
        application, [close_operator, close_browser]
    )
    try:
        assert command.main(["--sessions-dir", str(tmp_path), "--new"]) == 0
    finally:
        timer.stop()
        watchdog.stop()
    assert not pending and not timed_out
    assert managers[0].stopped == 1
    assert not any(widget.isVisible() for widget in application.topLevelWidgets())
    manifests = list(tmp_path.glob("*/session.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text())
    assert manifest["status"] == "ended"
    assert manifest["protocol_id"] == "fall-collection-simple-v2"
    assert len(manifest["environment"]["receiver_bindings"]) == 4
    if fail_start:
        assert "partial startup failed" in errors[0]
        assert browser[0].last_outcome is None
    else:
        outcome = browser[0].last_outcome
        assert outcome.error is None
        assert outcome.archive == manifests[0].parent.with_suffix(".zip")
        assert outcome.archive.is_file()
        # The browser came back with the new archive selected.
        assert browser[0].session.path == outcome.archive.resolve()


def test_canceling_new_session_initializes_no_inputs(
    tmp_path, monkeypatch, application
):
    from fall_detection.apps.sessions import app as command
    from fall_detection.apps.sessions import window as window_module
    from fall_detection.collection import video

    monkeypatch.setattr(
        window_module,
        "NewSessionDialog",
        lambda *args, **kwargs: SimpleNamespace(get=lambda: None),
    )
    monkeypatch.setattr(
        command, "LiveRadio", lambda *args, **kwargs: pytest.fail("radio initialized")
    )
    monkeypatch.setattr(
        video, "VideoRecorder", lambda *args: pytest.fail("camera initialized")
    )

    def close_browser():
        windows = visible(application, "CSI sessions")
        if windows:
            windows[0].close()
        return bool(windows)

    timer, watchdog, pending, timed_out = run_steps(application, [close_browser])
    try:
        assert (
            command.main(
                [
                    "--sessions-dir",
                    str(tmp_path),
                    "--new",
                    "--video-device",
                    "/dev/video-test",
                ]
            )
            == 0
        )
    finally:
        timer.stop()
        watchdog.stop()
    assert not pending and not timed_out
    assert not list(tmp_path.iterdir())


def test_resume_continues_an_ended_session_folder(tmp_path, monkeypatch, application):
    from fall_detection.apps.sessions.collector import run as run_module
    from fall_detection.apps.sessions.window import SessionsWindow, resume_blocker
    from fall_detection.collection.controller import OperatorCommand, SessionController

    plan = _first_block_plan(tmp_path, run_module)
    controller = SessionController(
        plan.protocol,
        tmp_path,
        environment={"receiver_ids": {"00:11:22:33:44:55": "rx-1"}},
    )
    controller.start_session(plan.metadata)
    controller.dispatch(OperatorCommand.END_SESSION)
    root = controller.session_root
    options = SimpleNamespace(
        video_device=None, video_width=1280, video_height=720, video_fps=30
    )
    window = SessionsWindow(
        tmp_path,
        None,
        options=options,
        sessions_dir=tmp_path,
        radio_factory=lambda *a, **k: pytest.fail("radio opened"),
    )
    started = []
    monkeypatch.setattr(window, "start_collection", started.append)
    try:
        assert window.select_session(root)
        assert resume_blocker(window.session) is None
        assert window.resume_action.isEnabled()
        window.resume_session(root)
    finally:
        window.close()
    (resumed,) = started
    assert resumed.resume.root == root.resolve()
    assert resumed.output_dir == root.resolve().parent
    assert resumed.metadata.participant_id == "test-participant"


def test_scenario_file_selection_recovers_from_invalid_json(
    tmp_path, monkeypatch, application
):
    from fall_detection.apps.sessions.collector.run import DEFAULT_PROTOCOL
    from fall_detection.apps.sessions.collector.views.dialogs import choose_protocol

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken")
    simple = DEFAULT_PROTOCOL.with_name("fall_simple.json")
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

    path, protocol = choose_protocol(QtWidgets, DEFAULT_PROTOCOL)

    assert path == simple
    assert protocol.protocol_id == "fall-collection-simple-v2"
    assert len(protocol.trials) == 232
    assert len(warnings) == 1 and "invalid JSON" in warnings[0]


def test_operator_revision_is_saved_in_the_archive(tmp_path, monkeypatch, application):
    from fall_detection.apps.sessions import app as command
    from fall_detection.apps.sessions import window as window_module
    from fall_detection.apps.sessions.collector import run as run_module
    from fall_detection.apps.sessions.collector.views import protocol_editor
    from fall_detection.protocol.revision import draft_queue, revise_protocol
    from fall_detection.session.models import load_session

    managers = []
    monkeypatch.setattr(command, "LiveRadio", offline_radio(managers))
    plan = _first_block_plan(tmp_path, run_module)
    monkeypatch.setattr(
        window_module,
        "NewSessionDialog",
        lambda *args, **kwargs: SimpleNamespace(get=lambda: plan),
    )

    class Editor:
        def __init__(self, QtCore, QtWidgets, protocol, *, locked, revision, **kwargs):
            assert kwargs["sources"][0][1].name == "protocol.json"
            queue = draft_queue(protocol)
            self.edit = protocol_editor.ProtocolEdit(
                revise_protocol(
                    protocol, queue[-1:] + queue[:-1], locked=locked, revision=revision
                ),
                "performer asked to start with the last scenario",
                ["reordered the remaining trials"],
            )

        def get(self):
            return self.edit

    monkeypatch.setattr(protocol_editor, "ProtocolEditorDialog", Editor)
    revised = []
    browser = []

    def revise_then_close():
        consoles = visible(application, "Collection operator")
        if not consoles:
            return False
        (run,) = [
            widget.collection
            for widget in application.topLevelWidgets()
            if isinstance(widget, window_module.SessionsWindow)
            and widget.collection is not None
        ]
        revised.append(run.edit_protocol())
        revised.append(run.controller.protocol.trials[0].scenario.id)
        consoles[0].close()
        return True

    def close_browser():
        windows = visible(application, "CSI sessions")
        if windows:
            browser.append(windows[0])
            windows[0].close()
        return bool(windows)

    timer, watchdog, pending, timed_out = run_steps(
        application, [revise_then_close, close_browser]
    )
    try:
        assert command.main(["--sessions-dir", str(tmp_path), "--new"]) == 0
    finally:
        timer.stop()
        watchdog.stop()
    assert not pending and not timed_out
    last = plan.protocol.trials[-1].scenario.id
    assert revised == [True, last]
    archive = browser[0].last_outcome.archive
    session = load_session(archive)
    assert not session.warnings
    (entry,) = session.protocol_revisions
    assert entry["note"] == "performer asked to start with the last scenario"
    assert session.trials[0].scenario_id == last
    assert session.protocol_hash == plan.protocol.source_hash
