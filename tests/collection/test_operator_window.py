"""Headless construction tests for the collection console window."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6 import QtCore, QtWidgets

from fall_detection.collection.views.dialogs import MetadataDialog
from fall_detection.collection.views.operator import OperatorWindow
from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionSnapshot,
)
from fall_detection.collection.protocol import (
    load_protocol,
    protocol_from_mapping,
    select_blocks,
)
from fall_detection.radio.visualization.dashboard import CsiDashboardPanel
from fall_detection.radio.visualization.state import LiveState


PROTOCOL_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "collection" / "fall_v1.json"
)
RECEIVER_ENV = {"receiver_ids": {"00:11:22:33:44:55": "rx-1"}}


@pytest.fixture(scope="module")
def qt_app():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application


def _session(tmp_path, block_ids):
    protocol = select_blocks(load_protocol(PROTOCOL_PATH), block_ids)
    controller = SessionController(protocol, tmp_path, environment=RECEIVER_ENV)
    controller.start_session(SessionMetadata(participant_id="p01"))
    snapshot = controller.update_health(HealthSnapshot(radio_live=True))
    return protocol, controller, snapshot


def _window(qt_app, protocol, commands=None, *, video_enabled=False):
    state = LiveState(50)
    panel = CsiDashboardPanel(state, fps=24)
    window = OperatorWindow(
        QtCore,
        QtWidgets,
        protocol=protocol,
        profile_text="profile test",
        panel=panel,
        on_command=(
            commands.append if commands is not None else (lambda command: None)
        ),
        video_enabled=video_enabled,
    )
    return window


def test_operator_window_camera_preview_preserves_aspect_and_clears_on_loss(
    qt_app, tmp_path,
):
    from fall_detection.collection.video import VideoPreviewFrame

    protocol, _controller, _snapshot = _session(tmp_path, ["walk-to-fall"])
    window = _window(qt_app, protocol, video_enabled=True)
    window.window.show()
    qt_app.processEvents()
    preview = window.camera_preview
    assert preview.image.text() == "Waiting for camera frames"
    image = VideoPreviewFrame(64, 48, bytes([255, 0, 0]) * (64 * 48), 100)
    preview.apply(image, ready=True, detail="video ready")
    pixmap = preview.image.pixmap()
    assert not pixmap.isNull()
    assert pixmap.width() / pixmap.height() == pytest.approx(4 / 3, abs=0.02)
    assert pixmap.toImage().pixelColor(0, 0).red() == 255
    preview.apply(None, ready=True, detail="video ready")
    assert preview.image.pixmap().cacheKey() == pixmap.cacheKey()
    window.window.resize(1300, 900)
    qt_app.processEvents()
    pixmap = preview.image.pixmap()
    assert pixmap.width() <= preview.image.width()
    assert pixmap.height() <= preview.image.height()
    preview.apply(None, ready=False, detail="camera worker stopped")
    assert preview.image.pixmap().isNull()
    assert preview.image.text() == "Camera unavailable"
    assert "camera worker stopped" in preview.status.text()
    window.window.close()


def test_operator_window_omits_preview_without_video(qt_app, tmp_path):
    protocol, _controller, _snapshot = _session(tmp_path, ["walk-to-fall"])
    window = _window(qt_app, protocol)
    assert window.camera_preview is None
    window.window.close()


def _apply(window, snapshot: SessionSnapshot) -> None:
    window.apply(
        snapshot,
        health_text="radio ok",
        metrics_text="rec 0",
        metrics_tooltip="tooltip",
        radio_detail="ready",
    )


def test_operator_window_shows_state_scenario_and_queue(qt_app, tmp_path):
    protocol, _controller, snapshot = _session(tmp_path, ["walk-to-fall"])
    window = _window(qt_app, protocol)

    _apply(window, snapshot)

    assert window.state_label.text() == "READY"
    assert window.progress_label.text() == "1/128"
    assert window.scenario_title.text() == "Walk to fall (front → front)"
    assert "walk_to_fall" in window.scenario_meta.text()
    assert window.trial_list.count() == 128
    assert window.trial_list.item(0).text().startswith("▶")
    assert window.buttons[OperatorCommand.START_TRIAL].isEnabled()
    assert not window.buttons[OperatorCommand.ACCEPT].isEnabled()


def test_operator_window_shows_equipment_grouped_queue_and_setup(qt_app, tmp_path):
    protocol = select_blocks(
        load_protocol(PROTOCOL_PATH.with_name("fall_simple.json")),
        ["walk-to-sit", "sit-to-walk"],
    )
    controller = SessionController(protocol, tmp_path, environment=RECEIVER_ENV)
    controller.start_session(SessionMetadata(participant_id="p01"))
    snapshot = controller.update_health(HealthSnapshot(radio_live=True))
    window = _window(qt_app, protocol)

    _apply(window, snapshot)
    window.show_current_details()

    assert window.trial_list.count() == 64
    assert window.setup_label.text() == "Setup: chair · chair facing front"
    assert not window.setup_label.isHidden()
    assert "chair facing front" in window._detail_windows[0].setup_label.text()
    for row, trial in enumerate(protocol.trials):
        assert trial.scenario.title in window.trial_list.item(row).text()
    window.window.close()
    controller.dispatch(OperatorCommand.END_SESSION)


def test_operator_window_queue_filter_narrows_to_one_block(qt_app, tmp_path):
    protocol, _controller, snapshot = _session(
        tmp_path, ["walk-to-fall", "sit-to-stand"]
    )
    window = _window(qt_app, protocol)
    _apply(window, snapshot)
    assert window.trial_list.count() == 144

    window.queue_filter.setCurrentIndex(2)
    _apply(window, snapshot)

    assert window.trial_list.count() == 16


def test_operator_window_marks_resolved_and_current_trials(qt_app, tmp_path):
    protocol, controller, snapshot = _session(tmp_path, ["walk-to-fall"])
    window = _window(qt_app, protocol)
    _apply(window, snapshot)

    resolved = controller.dispatch(OperatorCommand.SKIP)
    _apply(window, resolved)

    assert window.trial_list.item(0).text().startswith("✓")
    assert window.trial_list.item(1).text().startswith("▶")


def test_operator_window_dispatches_command_buttons(qt_app, tmp_path):
    protocol, _controller, snapshot = _session(tmp_path, ["walk-to-fall"])
    commands: list[OperatorCommand] = []
    window = _window(qt_app, protocol, commands)
    _apply(window, snapshot)

    window.buttons[OperatorCommand.START_TRIAL].click()

    assert commands == [OperatorCommand.START_TRIAL]


def test_operator_window_renders_the_complete_state(qt_app, tmp_path):
    protocol = protocol_from_mapping(
        {
            "schema_version": 1,
            "protocol_id": "single-trial",
            "title": "Single trial",
            "defaults": {
                "countdown_seconds": 1,
                "action_seconds": 2,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "only",
                    "title": "Only block",
                    "scenarios": [
                        {
                            "id": "only-scenario",
                            "activity_label": "walk",
                            "title": "Walk",
                            "instruction": "Walk forward",
                            "repetitions": 1,
                        }
                    ],
                }
            ],
        }
    )
    controller = SessionController(protocol, tmp_path, environment=RECEIVER_ENV)
    controller.start_session(SessionMetadata(participant_id="p01"))
    snapshot = controller.update_health(HealthSnapshot(radio_live=True))
    window = _window(qt_app, protocol)
    _apply(window, snapshot)

    complete = controller.dispatch(OperatorCommand.SKIP)
    _apply(window, complete)

    assert window.state_label.text() == "COMPLETE"
    assert window.scenario_title.text() == "Protocol complete"
    assert window.phase_label.text() == "—"
    assert window.trial_list.item(0).text().startswith("✓")


def test_metadata_dialog_defaults_to_every_block(qt_app):
    protocol = load_protocol(PROTOCOL_PATH)

    dialog = MetadataDialog(QtWidgets, protocol)

    assert dialog.block_ids() == tuple(block[0] for block in protocol.blocks)
    assert "576 trials" in dialog.total_label.text()

    for _block_id, checkbox, _trials in dialog._blocks:
        checkbox.setChecked(False)

    assert dialog.block_ids() == ()
    assert "0 trials" in dialog.total_label.text()


def test_dashboard_panel_lists_bound_receivers_and_switches_stream(qt_app):
    from fall_detection.radio.acquisition.buffer import RollingCsiBuffer

    state = LiveState(100)
    first, second = RollingCsiBuffer(), RollingCsiBuffer()
    state.configure_receivers({"rx-1": first, "rx-2": second})

    panel = CsiDashboardPanel(state, fps=24, receivers=["rx-1", "rx-2"])

    assert panel.receiver_combo.count() == 2
    assert panel.receiver_combo.currentData() == "rx-1"

    panel.receiver_combo.setCurrentIndex(1)

    assert state.selected_receiver_id == "rx-2"
    assert state.buffer is second


def test_scenario_detail_card_shows_every_field(qt_app, tmp_path):
    protocol, _controller, snapshot = _session(tmp_path, ["walk-to-fall"])
    window = _window(qt_app, protocol)
    _apply(window, snapshot)

    window.show_current_details()

    assert len(window._detail_windows) == 1
    detail = window._detail_windows[0]
    assert "current trial" in detail.status_label.text()
    assert detail.title_label.text() == "Walk to fall (front → front)"
    assert "walk_to_fall" in detail.meta_label.text()
    assert detail.instruction_label.text().startswith("Walk toward front")
    assert "countdown 5 s" in detail.timing_label.text()
    assert "action 8 s" in detail.timing_label.text()
    assert "recovery 5 s" in detail.timing_label.text()
    assert "start front" in detail.direction_label.text()
    assert "end front" in detail.direction_label.text()
    assert detail.safety_label is not None
    assert "crash mat" in detail.safety_label.text()
    assert detail.id_label.text() == "walk-to-fall__start_front__end_front"


def test_scenario_detail_reports_upcoming_and_resolved_trials(qt_app, tmp_path):
    protocol, controller, snapshot = _session(tmp_path, ["walk-to-fall"])
    window = _window(qt_app, protocol)
    _apply(window, snapshot)

    window._show_detail(3)
    assert "upcoming" in window._detail_windows[0].status_label.text()

    resolved = controller.dispatch(OperatorCommand.SKIP)
    _apply(window, resolved)
    window._show_detail(1)

    assert len(window._detail_windows) == 1
    assert "already resolved" in window._detail_windows[0].status_label.text()


def test_queue_double_click_opens_that_scenario_without_dispatching(qt_app, tmp_path):
    protocol, _controller, snapshot = _session(tmp_path, ["walk-to-fall"])
    commands: list[OperatorCommand] = []
    window = _window(qt_app, protocol, commands)
    _apply(window, snapshot)

    window.trial_list.itemDoubleClicked.emit(window.trial_list.item(4))

    assert len(window._detail_windows) == 1
    assert "Scenario 005" in window._detail_windows[0].window.windowTitle()
    assert commands == []


def test_scenario_detail_marks_every_trial_resolved_after_completion(qt_app, tmp_path):
    protocol = protocol_from_mapping(
        {
            "schema_version": 1,
            "protocol_id": "single-trial",
            "title": "Single trial",
            "defaults": {
                "countdown_seconds": 1,
                "action_seconds": 2,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "only",
                    "title": "Only block",
                    "scenarios": [
                        {
                            "id": "only-scenario",
                            "activity_label": "walk",
                            "title": "Walk",
                            "instruction": "Walk forward",
                            "repetitions": 1,
                        }
                    ],
                }
            ],
        }
    )
    controller = SessionController(protocol, tmp_path, environment=RECEIVER_ENV)
    controller.start_session(SessionMetadata(participant_id="p01"))
    snapshot = controller.update_health(HealthSnapshot(radio_live=True))
    window = _window(qt_app, protocol)
    _apply(window, snapshot)

    complete = controller.dispatch(OperatorCommand.SKIP)
    _apply(window, complete)
    window._show_detail(1)

    assert "already resolved" in window._detail_windows[0].status_label.text()
    assert not window.detail_button.isEnabled()
