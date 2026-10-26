from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fall_detection.collection.camera as camera_module
from fall_detection.collection.camera import CameraCaptureWorker


def test_camera_becomes_ready_only_after_first_successful_inference(
    monkeypatch,
):
    events: list[str] = []
    frames = []

    class Capture:
        def isOpened(self):
            return True

        def read(self):
            return True, object()

        def release(self):
            events.append("released")

    worker = CameraCaptureWorker(
        0,
        Path("model"),
        Path("configs/vision/rule_based_fall.toml"),
        on_health=lambda live, detail: events.append(f"health:{live}:{detail}"),
    )

    class Yolo:
        def __init__(self, _model):
            assert not worker.ready
            events.append("model-loaded")

        def predict(self, **_kwargs):
            assert not worker.ready
            events.append("inference-succeeded")
            return [object()]

    def on_frame(frame):
        assert worker.ready
        frames.append(frame)
        worker.stop_event.set()

    worker.on_frame = on_frame
    monkeypatch.setitem(
        __import__("sys").modules,
        "cv2",
        SimpleNamespace(VideoCapture=lambda _source: Capture()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "ultralytics",
        SimpleNamespace(YOLO=Yolo),
    )
    monkeypatch.setattr(camera_module, "largest_person_index", lambda _result: None)

    worker._run()

    assert worker.ready
    assert len(frames) == 1
    assert events.index("model-loaded") < events.index("inference-succeeded")
    assert events.index("inference-succeeded") < next(
        index
        for index, event in enumerate(events)
        if event.startswith("health:True:camera live")
    )


def test_camera_can_force_v4l2_backend(monkeypatch):
    calls = []

    class Capture:
        def isOpened(self):
            return False

    class Cv2:
        CAP_V4L2 = 200

        @staticmethod
        def VideoCapture(source, backend):
            calls.append((source, backend))
            return Capture()

    worker = CameraCaptureWorker(
        "/dev/video2",
        Path("model"),
        Path("configs/vision/rule_based_fall.toml"),
        camera_backend="v4l2",
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "cv2",
        Cv2,
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "ultralytics",
        SimpleNamespace(YOLO=object),
    )

    worker._run()

    assert calls == [("/dev/video2", 200)]


def test_camera_keeps_raw_and_annotated_frames_separate(monkeypatch):
    raw = object()
    annotated = object()
    frames = []

    class Capture:
        def isOpened(self):
            return True

        def read(self):
            return True, raw

        def release(self):
            pass

    class Result:
        def plot(self):
            return annotated

    class Yolo:
        def __init__(self, _model):
            pass

        def predict(self, **_kwargs):
            return [Result()]

    worker = CameraCaptureWorker(
        0,
        Path("model"),
        Path("configs/vision/rule_based_fall.toml"),
        on_frame=lambda frame: (frames.append(frame), worker.stop_event.set()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "cv2",
        SimpleNamespace(VideoCapture=lambda _source: Capture()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "ultralytics",
        SimpleNamespace(YOLO=Yolo),
    )
    monkeypatch.setattr(camera_module, "largest_person_index", lambda _result: None)

    worker._run()

    assert len(frames) == 1
    assert frames[0].frame is raw
    assert frames[0].display_frame is annotated
