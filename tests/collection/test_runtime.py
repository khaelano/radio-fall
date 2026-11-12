"""Collection health stays responsive and cleanup survives failed startup."""

from contextlib import ExitStack
from types import SimpleNamespace

import pytest
from test_controller import FakeClock, make_controller

from fall_detection.apps.collector.runtime import (
    CollectionPresenter,
    running_collection,
)
from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import OperatorCommand, SessionState
from fall_detection.presentation.radio.transport_status import TransportStatusText


@pytest.mark.parametrize(
    "failure", [None, "session", "camera", "radio", "display", "stop"]
)
def test_collection_cleans_partial_startup_and_continues_after_cleanup_failure(failure):
    calls = []

    def step(name):
        calls.append(name)
        if name == failure:
            raise RuntimeError(failure)

    controller = SimpleNamespace(
        state=SessionState.READY,
        start_session=lambda metadata: step("session"),
        dispatch=lambda command: step("end"),
        flush_radio=lambda: step("flush"),
    )
    radio = SimpleNamespace(start=lambda: step("radio"), stop=lambda: step("stop"))
    video = SimpleNamespace(
        start=lambda: step("camera"), stop=lambda: step("camera_stop")
    )

    def run():
        with ExitStack() as resources:
            resources.callback(video.stop)
            with running_collection(
                controller, radio, SessionMetadata("p01"), video=video
            ):
                step("display")

    if failure:
        with pytest.raises(RuntimeError, match=failure):
            run()
    else:
        run()
    assert calls[-4:] == ["end", "stop", "flush", "camera_stop"]


def test_presenter_checks_health_each_tick_without_reprobing_storage(
    tmp_path, monkeypatch
):
    from fall_detection.apps.collector import runtime

    clock = FakeClock()
    controller = make_controller(tmp_path, clock)
    controller.start_session(SessionMetadata("p01"))
    reader = SimpleNamespace(
        clock_sync_ready=True, all_live=True, any_recent_record=True
    )
    radio = SimpleNamespace(
        manager=reader, state=SimpleNamespace(get_status=lambda: ("ready", True))
    )
    frames = []
    text = TransportStatusText("ready", "settings", "metrics", "detail")
    dashboard = SimpleNamespace(refresh=lambda **kw: text)
    operator = SimpleNamespace(apply=lambda snapshot, **kw: frames.append(snapshot))
    previews = []
    video = SimpleNamespace(
        ready=True, detail="video ready", latest_preview=lambda: "new image"
    )
    operator.camera_preview = SimpleNamespace(
        apply=lambda image, **kw: previews.append((image, kw))
    )
    performer = SimpleNamespace(apply=lambda snapshot: None)
    probes = []
    monkeypatch.setattr(
        runtime, "output_writable", lambda path: probes.append(path) or True
    )
    presenter = CollectionPresenter(
        controller,
        radio,
        dashboard,
        operator=operator,
        performer=performer,
        output_dir=tmp_path,
        video=video,
    )
    presenter.refresh(now=0)
    assert previews[-1] == ("new image", {"ready": True, "detail": "video ready"})
    controller.dispatch(OperatorCommand.START_TRIAL)
    # Planned upload gaps must not interrupt an active attempt.
    reader.all_live = reader.any_recent_record = False
    for frame in range(1, 24):
        snapshot = presenter.refresh(now=frame / 24)
        assert snapshot.health.ready
    assert len(probes) == 1
    # Reference health loss must still abort on the next tick, inside the cache period.
    reader.clock_sync_ready = False
    snapshot = presenter.refresh(now=0.99)
    assert snapshot.state is SessionState.REVIEW
    assert snapshot.attempt_status == "invalid"
    assert not snapshot.health.clock_sync_ready
    assert len(probes) == 1
    presenter.refresh(now=1)
    assert len(probes) == 2
    assert len(frames) == 26

    # Recovery may finish while GUI refreshes are paused. Reconcile health from
    # the controller rather than relying on the presenter's last displayed value.
    reader.clock_sync_ready = reader.all_live = reader.any_recent_record = True
    presenter.refresh(now=2)
    controller.interrupt_radio("another restart while the GUI was paused")
    assert not controller.health.radio_live
    presenter.refresh(now=2.1)
    assert controller.health.radio_live and controller.health.clock_sync_ready
    assert controller.tick().attempt_status == "invalid"
    video.ready, video.detail = False, "camera worker stopped"
    presenter.refresh(now=2.2)
    assert previews[-1] == (None, {"ready": False, "detail": "camera worker stopped"})


def test_output_writable_checks_actual_output_and_nearest_existing_parent(
    tmp_path, monkeypatch
):
    from fall_detection.apps.collector import runtime

    checked = []
    monkeypatch.setattr(
        runtime.os, "access", lambda path, mode: checked.append(path) or True
    )
    assert runtime.output_writable(tmp_path / "not-yet-created" / "sessions")
    assert checked == [tmp_path]
    destination = tmp_path / "output"
    destination.mkdir()
    assert runtime.output_writable(destination)
    assert checked[-1] == destination
