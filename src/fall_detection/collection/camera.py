"""Camera capture, pose inference, and trial-frame adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
import time
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from ..vision.rules import DetectionOutput, FallRulesConfig, PoseObservation, RuleBasedFallDetector
from ..vision.scenarios import (
    ActivityObservation,
    ActivityRecognizer,
    ScenarioCompletionConfig,
)
from ..vision.yolo import largest_person_index, observation_from_yolo


@dataclass(frozen=True)
class CameraFrame:
    """One camera frame delivered to the preview and active trial sink."""

    timestamp_ns: int
    frame: Any
    detector_state: str
    proposal: Optional[dict[str, Any]]
    pose: Optional[dict[str, Any]]
    display_frame: Any | None = None
    activity: ActivityObservation | None = None


def _pose_payload(observation: PoseObservation) -> dict[str, Any]:
    return {
        "timestamp_s": observation.timestamp_s,
        "track_id": observation.track_id,
        "keypoints": [asdict(point) for point in observation.keypoints],
        "box": asdict(observation.box),
    }


def _detection_payload(output: DetectionOutput) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": output.state.value,
        "transition": output.transition.value,
    }
    if output.features is not None:
        payload["features"] = asdict(output.features)
    if output.proposal is not None:
        payload["proposal"] = asdict(output.proposal)
    return payload


def _display_frame(result: Any, fallback: Any) -> Any:
    """Render Ultralytics annotations without changing the raw frame.

    Plotting is a preview convenience.  If a model backend does not expose
    ``plot`` or plotting fails, collection still receives the raw frame and
    can continue recording.
    """

    plot = getattr(result, "plot", None)
    if not callable(plot):
        return fallback
    try:
        annotated = plot()
    except Exception:
        return fallback
    return fallback if annotated is None else annotated


class CameraCaptureWorker:
    """Capture and infer camera frames outside the Qt GUI thread."""

    def __init__(
        self,
        source: int | str,
        model_path: Path,
        rules_config: Path,
        *,
        camera_backend: Literal["auto", "v4l2"] = "auto",
        device: str = "cpu",
        image_size: int = 320,
        on_frame: Callable[[CameraFrame], None] | None = None,
        on_health: Callable[[bool, str], None] | None = None,
    ) -> None:
        self.source = source
        self.model_path = model_path
        self.rules_config = rules_config
        self.camera_backend = camera_backend
        self.device = device
        self.image_size = image_size
        self.on_frame = on_frame
        self.on_health = on_health
        self.stop_event = threading.Event()
        self._ready_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run, name="collection-camera", daemon=True
        )

    def start(self) -> None:
        """Start the camera worker."""

        self.thread.start()

    def stop(self) -> None:
        """Stop capture and wait briefly for the camera to release."""

        self.stop_event.set()
        self.thread.join(timeout=3)

    @property
    def ready(self) -> bool:
        """Return whether the model has completed one successful inference."""

        return self._ready_event.is_set()

    def _health(self, live: bool, detail: str) -> None:
        if self.on_health is not None:
            self.on_health(live, detail)

    def _run(self) -> None:
        try:
            import cv2
            from ultralytics import YOLO
        except ImportError as exc:
            self._health(False, f"camera dependencies unavailable: {exc}")
            return

        try:
            capture = self._open_capture(cv2)
        except ValueError as exc:
            self._health(False, str(exc))
            return
        if not capture.isOpened():
            self._health(False, f"unable to open camera source {self.source!r}")
            return
        try:
            model = YOLO(str(self.model_path))
            detector = RuleBasedFallDetector(
                FallRulesConfig.from_toml(self.rules_config)
            )
            activity_recognizer = ActivityRecognizer(
                ScenarioCompletionConfig.from_toml(self.rules_config)
            )
            camera_live_announced = False
            self._health(False, "camera model loaded; warming first inference")
            while not self.stop_event.is_set():
                ok, frame = capture.read()
                if not ok:
                    self._health(False, "camera frame read failed")
                    break
                timestamp_ns = time.monotonic_ns()
                timestamp_s = timestamp_ns / 1_000_000_000.0
                try:
                    results = model.predict(
                        source=frame,
                        stream=False,
                        imgsz=self.image_size,
                        device=self.device,
                        save=False,
                        verbose=False,
                    )
                    result = results[0]
                    display_frame = _display_frame(result, frame)
                    person_index = largest_person_index(result)
                    if person_index is None:
                        output = detector.update_missing(timestamp_s)
                        observation = None
                    else:
                        observation = observation_from_yolo(
                            result, timestamp_s, person_index
                        )
                        output = detector.update(observation)
                    activity = activity_recognizer.update(
                        observation,
                        output,
                        timestamp_s=timestamp_s,
                    )
                except Exception as exc:  # inference must not kill collection
                    self._health(False, f"camera inference failed: {exc}")
                    camera_live_announced = False
                    continue

                if not self._ready_event.is_set():
                    self._ready_event.set()
                if not camera_live_announced:
                    self._health(True, f"camera live: {self.source}")
                    camera_live_announced = True

                if self.on_frame is not None:
                    self.on_frame(
                        CameraFrame(
                            timestamp_ns=timestamp_ns,
                            frame=frame,
                            detector_state=output.state.value,
                            proposal=_detection_payload(output),
                            pose=(
                                _pose_payload(observation)
                                if observation is not None
                                else None
                            ),
                            display_frame=display_frame,
                            activity=activity,
                        )
                    )
        except Exception as exc:
            self._health(False, f"camera worker failed: {exc}")
        finally:
            capture.release()
            self._health(False, "camera stopped")

    def _open_capture(self, cv2: Any) -> Any:
        """Open the configured source with the requested OpenCV backend.

        ``auto`` preserves OpenCV's normal backend selection for indexes,
        files, and network URLs.  ``v4l2`` is useful for Linux UVC devices,
        including Android phones that expose a USB webcam interface.
        """

        if self.camera_backend == "auto":
            return cv2.VideoCapture(self.source)
        if self.camera_backend == "v4l2":
            backend = getattr(cv2, "CAP_V4L2", None)
            if backend is None:
                raise ValueError("OpenCV was built without the V4L2 backend")
            return cv2.VideoCapture(self.source, backend)
        raise ValueError(f"unsupported camera backend {self.camera_backend!r}")
