"""Headless construction tests for the collection console window."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6 import QtCore, QtWidgets

from fall_detection.apps.common.dashboard import CsiDashboardPanel
from fall_detection.apps.sessions.collector.views.dialogs import NewSessionDialog
from fall_detection.apps.sessions.collector.views.operator import OperatorWindow
from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionSnapshot,
)
from fall_detection.protocol.loader import (
    load_protocol,
    protocol_from_mapping,
    select_blocks,
)
from fall_detection.radio.state import LiveState

PROTOCOL_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "collection" / "fall_simple.json"
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
    qt_app,
    tmp_path,
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
    assert window.progress_label.text() == "1/32"
    assert window.scenario_title.text() == "wf · Walk to fall (front → front)"
    assert "walk_to_fall" in window.scenario_meta.text()
    assert window.trial_list.count() == 32
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
    assert window.trial_list.count() == 64

    window.queue_filter.setCurrentIndex(2)
    _apply(window, snapshot)

    assert window.trial_list.count() == 32


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


def test_new_session_dialog_defaults_to_every_block(qt_app, tmp_path):
    protocol = load_protocol(PROTOCOL_PATH)

    dialog = NewSessionDialog(
        QtWidgets, protocol_path=PROTOCOL_PATH, output_dir=tmp_path, cameras=()
    )

    assert dialog.block_ids() == tuple(block[0] for block in protocol.blocks)
    assert "232 trials" in dialog.total_label.text()

    for _block_id, checkbox, _trials in dialog._blocks:
        checkbox.setChecked(False)

    assert dialog.block_ids() == ()
    assert "0 trials" in dialog.total_label.text()


def test_new_session_dialog_builds_a_plan_or_explains_what_is_missing(qt_app, tmp_path):
    dialog = NewSessionDialog(
        QtWidgets,
        protocol_path=PROTOCOL_PATH,
        output_dir=tmp_path,
        video_device="/dev/video2",
        cameras=("/dev/video0",),
    )
    with pytest.raises(ValueError, match="participant"):
        dialog.plan()
    dialog.participant.setText(" p07 ")
    first_block = dialog._blocks[0][0]
    for block_id, checkbox, _trials in dialog._blocks:
        checkbox.setChecked(block_id == first_block)

    plan = dialog.plan()

    assert plan.metadata.participant_id == "p07"
    assert plan.output_dir == tmp_path
    assert {trial.scenario.block_id for trial in plan.protocol.trials} == {first_block}
    assert plan.video is not None and plan.video.device == "/dev/video2"
    assert not plan.continuous


def test_new_session_dialog_continuous_mode_records_csi_only(qt_app, tmp_path):
    dialog = NewSessionDialog(
        QtWidgets,
        protocol_path=PROTOCOL_PATH,
        output_dir=tmp_path,
        continuous=True,
        segment_seconds=60,
        segments=3,
        video_device="/dev/video2",
        cameras=(),
    )
    dialog.participant.setText("p01")

    plan = dialog.plan()

    assert plan.continuous and plan.video is None
    assert plan.protocol.protocol_id == "continuous-activity-v1"
    assert len(plan.protocol.trials) == 3
    assert "Up to 3 segments" in dialog.total_label.text()
    assert not dialog.camera_combo.isEnabled()
