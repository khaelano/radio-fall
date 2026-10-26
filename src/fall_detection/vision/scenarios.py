"""Rule-based activity and scenario completion recognition.

The module deliberately separates two concerns:

* :class:`ActivityRecognizer` turns one tracked pose and the existing fall
  detector output into a small, serializable activity observation.
* :class:`ScenarioCompletionRecognizer` validates the expected temporal
  transition for the current collection trial.

The recognizers are intentionally conservative.  They report evidence and
coverage, not calibrated prediction confidence or ground-truth labels.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum
from math import atan2, degrees, hypot, isfinite
from pathlib import Path
from statistics import median
import tomllib
from typing import Any

from .rules import (
    CocoKeypoint,
    DetectionOutput,
    DetectorState,
    Keypoint,
    PoseObservation,
)


class PostureState(str, Enum):
    """Coarse posture state derived from one pose."""

    UNKNOWN = "unknown"
    STANDING = "standing"
    SEATED = "seated"
    FALLEN = "fallen"


class MotionState(str, Enum):
    """Coarse motion state derived from a short pose history."""

    UNKNOWN = "unknown"
    STATIONARY = "stationary"
    WALKING = "walking"


class ScenarioRecognitionStatus(str, Enum):
    """Lifecycle state of the expected scenario transition."""

    WAITING_FOR_SOURCE = "waiting_for_source"
    WAITING_FOR_TARGET = "waiting_for_target"
    COMPLETED = "completed"
    NOT_DETECTED = "not_detected"
    UNCERTAIN = "uncertain"
    UNSUPPORTED = "unsupported"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ScenarioCompletionConfig:
    """Thresholds for posture, gait, and scenario validation heuristics."""

    enabled: bool = True
    min_keypoint_confidence: float = 0.35
    motion_window_seconds: float = 0.8
    min_hip_translation_torso_lengths: float = 0.25
    min_ankle_motion_torso_lengths: float = 0.20
    min_box_scale_change: float = 0.08
    standing_max_torso_angle_degrees: float = 35.0
    standing_min_knee_angle_degrees: float = 150.0
    seated_max_torso_angle_degrees: float = 55.0
    seated_min_knee_angle_degrees: float = 60.0
    seated_max_knee_angle_degrees: float = 135.0
    posture_hold_seconds: float = 0.6
    walking_hold_seconds: float = 0.8
    max_missing_seconds: float = 0.5
    minimum_reliable_frame_fraction: float = 0.60

    @classmethod
    def from_toml(cls, path: Path) -> "ScenarioCompletionConfig":
        """Load ``[scenario_completion]`` from a vision TOML file.

        The table is optional; omitted values use the conservative defaults
        declared by this dataclass.
        """

        with path.open("rb") as config_file:
            document = tomllib.load(config_file)
        values = document.get("scenario_completion", {})
        if not isinstance(values, dict):
            raise ValueError("config.scenario_completion must be a table")
        return cls(**values)


@dataclass(frozen=True)
class ActivityObservation:
    """One timestamped, coarse activity observation."""

    timestamp_s: float
    posture: PostureState
    motion: MotionState
    reliable: bool

    def __post_init__(self) -> None:
        if not isfinite(self.timestamp_s):
            raise ValueError("timestamp_s must be finite")

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-compatible payload for capture artifacts."""

        return {
            "timestamp_s": self.timestamp_s,
            "posture": self.posture.value,
            "motion": self.motion.value,
            "reliable": self.reliable,
        }


@dataclass(frozen=True)
class ScenarioRecognition:
    """Current evidence for one expected scenario transition."""

    expected_activity_label: str
    status: ScenarioRecognitionStatus
    observed_steps: tuple[str, ...] = ()
    message: str = ""
    source_confirmed_at_s: float | None = None
    target_started_at_s: float | None = None
    completed_at_s: float | None = None
    reliable_frame_fraction: float = 0.0
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-compatible payload for session artifacts."""

        payload = asdict(self)
        payload["status"] = self.status.value
        payload["observed_steps"] = list(self.observed_steps)
        return payload


@dataclass(frozen=True)
class _PoseFrame:
    timestamp_s: float
    hip_x: float
    hip_y: float
    torso_length: float
    box_width: float
    box_height: float
    ankle_relative: tuple[tuple[str, float, float], ...]
    posture: PostureState
    reliable: bool


def _angle(first: Keypoint, vertex: Keypoint, second: Keypoint) -> float | None:
    """Return the angle at ``vertex`` in degrees when points are reliable."""

    ux = first.x - vertex.x
    uy = first.y - vertex.y
    vx = second.x - vertex.x
    vy = second.y - vertex.y
    first_length = hypot(ux, uy)
    second_length = hypot(vx, vy)
    if first_length < 1e-6 or second_length < 1e-6:
        return None
    cosine = (ux * vx + uy * vy) / (first_length * second_length)
    cosine = max(-1.0, min(1.0, cosine))
    # Avoid importing a second geometry package for this small calculation.
    from math import acos

    return degrees(acos(cosine))


def _point(observation: PoseObservation, index: CocoKeypoint) -> Keypoint:
    return observation.keypoints[index]


def _midpoint(first: Keypoint, second: Keypoint) -> tuple[float, float] | None:
    if first.confidence <= 0 or second.confidence <= 0:
        return None
    return ((first.x + second.x) / 2.0, (first.y + second.y) / 2.0)


class ActivityRecognizer:
    """Convert pose frames into stable posture and walking observations."""

    def __init__(self, config: ScenarioCompletionConfig | None = None) -> None:
        self.config = config or ScenarioCompletionConfig()
        self._history: deque[_PoseFrame] = deque()
        self._last_timestamp: float | None = None
        self._missing_started_at: float | None = None

    def reset(self) -> None:
        """Clear temporal motion state before a new camera sequence."""

        self._history.clear()
        self._last_timestamp = None
        self._missing_started_at = None

    def update(
        self,
        pose: PoseObservation | None,
        fall_output: DetectionOutput,
        *,
        timestamp_s: float | None = None,
    ) -> ActivityObservation:
        """Return one activity observation for a pose or missing frame."""

        timestamp = timestamp_s
        if timestamp is None and pose is not None:
            timestamp = pose.timestamp_s
        if timestamp is None:
            if fall_output.features is not None:
                timestamp = fall_output.features.timestamp_s
            elif self._last_timestamp is not None:
                timestamp = self._last_timestamp
            else:
                raise ValueError("timestamp_s is required for a missing first frame")
        if not isfinite(timestamp):
            raise ValueError("timestamp_s must be finite")
        if self._last_timestamp is not None and timestamp < self._last_timestamp:
            raise ValueError("timestamps must be monotonically increasing")
        self._last_timestamp = timestamp

        if pose is None:
            if self._missing_started_at is None:
                self._missing_started_at = timestamp
            if timestamp - self._missing_started_at >= self.config.max_missing_seconds:
                self._history.clear()
            return ActivityObservation(
                timestamp, PostureState.UNKNOWN, MotionState.UNKNOWN, False
            )

        self._missing_started_at = None
        posture, frame = self._classify_pose(pose, fall_output)
        if frame is None:
            return ActivityObservation(
                timestamp, posture, MotionState.UNKNOWN, False
            )
        self._history.append(frame)
        cutoff = timestamp - self.config.motion_window_seconds
        while self._history and self._history[0].timestamp_s < cutoff:
            self._history.popleft()
        motion = self._classify_motion(frame)
        return ActivityObservation(timestamp, posture, motion, frame.reliable)

    def _classify_pose(
        self,
        observation: PoseObservation,
        fall_output: DetectionOutput,
    ) -> tuple[PostureState, _PoseFrame | None]:
        minimum = self.config.min_keypoint_confidence
        shoulders = _midpoint(
            _point(observation, CocoKeypoint.LEFT_SHOULDER),
            _point(observation, CocoKeypoint.RIGHT_SHOULDER),
        )
        hips = _midpoint(
            _point(observation, CocoKeypoint.LEFT_HIP),
            _point(observation, CocoKeypoint.RIGHT_HIP),
        )
        if shoulders is None or hips is None:
            return PostureState.UNKNOWN, None
        shoulder_points = (
            _point(observation, CocoKeypoint.LEFT_SHOULDER),
            _point(observation, CocoKeypoint.RIGHT_SHOULDER),
        )
        hip_points = (
            _point(observation, CocoKeypoint.LEFT_HIP),
            _point(observation, CocoKeypoint.RIGHT_HIP),
        )
        if any(point.confidence < minimum for point in (*shoulder_points, *hip_points)):
            return PostureState.UNKNOWN, None

        torso_length = hypot(shoulders[0] - hips[0], shoulders[1] - hips[1])
        if torso_length < 1e-3:
            return PostureState.UNKNOWN, None
        torso_angle = degrees(
            atan2(abs(shoulders[0] - hips[0]), abs(shoulders[1] - hips[1]))
        )
        box_width = max(0.0, observation.box.x_max - observation.box.x_min)
        box_height = max(0.0, observation.box.y_max - observation.box.y_min)
        ankles: list[tuple[str, float, float]] = []
        for side, index in (
            ("left", CocoKeypoint.LEFT_ANKLE),
            ("right", CocoKeypoint.RIGHT_ANKLE),
        ):
            ankle = _point(observation, index)
            if ankle.confidence >= minimum:
                ankles.append(
                    (
                        side,
                        (ankle.x - hips[0]) / torso_length,
                        (ankle.y - hips[1]) / torso_length,
                    )
                )

        knee_angles: list[float] = []
        for hip_index, knee_index, ankle_index in (
            (CocoKeypoint.LEFT_HIP, CocoKeypoint.LEFT_KNEE, CocoKeypoint.LEFT_ANKLE),
            (CocoKeypoint.RIGHT_HIP, CocoKeypoint.RIGHT_KNEE, CocoKeypoint.RIGHT_ANKLE),
        ):
            first = _point(observation, hip_index)
            vertex = _point(observation, knee_index)
            second = _point(observation, ankle_index)
            if min(first.confidence, vertex.confidence, second.confidence) >= minimum:
                angle = _angle(first, vertex, second)
                if angle is not None:
                    knee_angles.append(angle)

        if fall_output.state is DetectorState.FALLEN:
            posture = PostureState.FALLEN
        elif knee_angles and torso_angle <= self.config.standing_max_torso_angle_degrees and (
            median(knee_angles) >= self.config.standing_min_knee_angle_degrees
        ):
            posture = PostureState.STANDING
        elif knee_angles and torso_angle <= self.config.seated_max_torso_angle_degrees and (
            self.config.seated_min_knee_angle_degrees
            <= median(knee_angles)
            <= self.config.seated_max_knee_angle_degrees
        ):
            posture = PostureState.SEATED
        else:
            posture = PostureState.UNKNOWN

        reliable = bool(knee_angles) or (
            posture is PostureState.FALLEN and fall_output.features is not None
        )
        frame = _PoseFrame(
            timestamp_s=observation.timestamp_s,
            hip_x=hips[0],
            hip_y=hips[1],
            torso_length=torso_length,
            box_width=box_width,
            box_height=box_height,
            ankle_relative=tuple(ankles),
            posture=posture,
            reliable=reliable,
        )
        return posture, frame

    def _classify_motion(self, current: _PoseFrame) -> MotionState:
        if current.posture in (PostureState.SEATED, PostureState.FALLEN):
            return MotionState.STATIONARY
        candidates = [
            previous
            for previous in self._history
            if 0.05 <= current.timestamp_s - previous.timestamp_s
            <= self.config.motion_window_seconds
        ]
        if not candidates:
            return MotionState.STATIONARY if current.reliable else MotionState.UNKNOWN
        previous = candidates[0]
        scale = max(current.torso_length, previous.torso_length, 1e-3)
        hip_translation = hypot(
            current.hip_x - previous.hip_x,
            current.hip_y - previous.hip_y,
        ) / scale
        box_scale_change = max(
            abs(current.box_height - previous.box_height)
            / max(previous.box_height, 1e-3),
            abs(current.box_width - previous.box_width)
            / max(previous.box_width, 1e-3),
        )
        ankle_motion = 0.0
        previous_ankles = {
            side: (x, y) for side, x, y in previous.ankle_relative
        }
        for side, current_x, current_y in current.ankle_relative:
            previous_position = previous_ankles.get(side)
            if previous_position is None:
                continue
            ankle_motion = max(
                ankle_motion,
                hypot(
                    current_x - previous_position[0],
                    current_y - previous_position[1],
                ),
            )
        walking = (
            ankle_motion >= self.config.min_ankle_motion_torso_lengths
            and (
                hip_translation >= self.config.min_hip_translation_torso_lengths
                or box_scale_change >= self.config.min_box_scale_change
            )
        )
        return MotionState.WALKING if walking else MotionState.STATIONARY


_SCENARIO_STEPS: dict[str, tuple[str, str]] = {
    "walk_to_fall": ("walking", "fallen"),
    "sit_to_fall": ("seated", "fallen"),
    "stand_to_fall": ("standing", "fallen"),
    "walk_to_sit": ("walking", "seated"),
    "sit_to_walk": ("seated", "walking"),
    "sit_to_stand": ("seated", "standing"),
}


class ScenarioCompletionRecognizer:
    """Validate one expected source-to-target activity transition."""

    def __init__(
        self,
        expected_activity_label: str,
        config: ScenarioCompletionConfig | None = None,
    ) -> None:
        self.config = config or ScenarioCompletionConfig()
        self.expected_activity_label = expected_activity_label
        self._steps = _SCENARIO_STEPS.get(expected_activity_label)
        self._source_started_at: float | None = None
        self._source_confirmed_at: float | None = None
        self._target_started_at: float | None = None
        self._source_seen = False
        self._observed_steps: list[str] = []
        self._total_frames = 0
        self._reliable_frames = 0
        self._last_result = self._initial_result()

    @property
    def supported(self) -> bool:
        """Return whether this activity label has a known transition."""

        return self._steps is not None

    @property
    def completed(self) -> bool:
        """Return whether the expected transition has completed."""

        return self._last_result.status is ScenarioRecognitionStatus.COMPLETED

    @property
    def result(self) -> ScenarioRecognition:
        """Return the latest result without exposing implementation state."""

        return self._last_result

    def reset(self) -> None:
        """Reset evidence for a fresh attempt of the same scenario."""

        self._source_started_at = None
        self._source_confirmed_at = None
        self._target_started_at = None
        self._source_seen = False
        self._observed_steps.clear()
        self._total_frames = 0
        self._reliable_frames = 0
        self._last_result = self._initial_result()

    def update(
        self,
        activity: ActivityObservation,
        *,
        action_active: bool,
    ) -> ScenarioRecognition:
        """Consume one activity frame and return the current recognition."""

        if self._last_result.status in (
            ScenarioRecognitionStatus.COMPLETED,
            ScenarioRecognitionStatus.NOT_DETECTED,
            ScenarioRecognitionStatus.UNCERTAIN,
        ):
            return self._last_result
        self._total_frames += 1
        if activity.reliable:
            self._reliable_frames += 1
        if not self.config.enabled:
            self._last_result = self._make_result(
                ScenarioRecognitionStatus.DISABLED,
                "scenario recognition is disabled",
            )
            return self._last_result
        if self._steps is None:
            self._last_result = self._make_result(
                ScenarioRecognitionStatus.UNSUPPORTED,
                f"no completion rule for {self.expected_activity_label!r}",
            )
            return self._last_result

        source, target = self._steps
        if not self._source_seen:
            source_match = self._matches(source, activity)
            source_allowed = action_active or source != "walking"
            if source_match and source_allowed:
                if self._source_started_at is None:
                    self._source_started_at = activity.timestamp_s
                hold = self._hold_seconds(source)
                if activity.timestamp_s - self._source_started_at + 1e-9 >= hold:
                    self._source_seen = True
                    self._observed_steps.append(source)
                    self._source_confirmed_at = activity.timestamp_s
                    self._source_started_at = None
            else:
                self._source_started_at = None
            status = (
                ScenarioRecognitionStatus.WAITING_FOR_TARGET
                if self._source_seen
                else ScenarioRecognitionStatus.WAITING_FOR_SOURCE
            )
            self._last_result = self._make_result(
                status,
                f"waiting for {target}" if self._source_seen else f"waiting for {source}",
            )
            if not self._source_seen:
                return self._last_result

        if not action_active:
            self._last_result = self._make_result(
                ScenarioRecognitionStatus.WAITING_FOR_TARGET,
                f"{source} detected; waiting for {target}",
            )
            return self._last_result

        target_match = self._matches(target, activity)
        if target_match:
            if self._target_started_at is None:
                self._target_started_at = activity.timestamp_s
            hold = self._hold_seconds(target)
            # The fall detector already requires a persistent low posture, so
            # its FALLEN transition is the completion confirmation itself.
            if target == "fallen" or activity.timestamp_s - self._target_started_at + 1e-9 >= hold:
                self._observed_steps.append(target)
                self._last_result = self._make_result(
                    ScenarioRecognitionStatus.COMPLETED,
                    f"completed: {source} → {target}",
                    completed_at_s=activity.timestamp_s,
                )
                return self._last_result
        else:
            self._target_started_at = None
        self._last_result = self._make_result(
            ScenarioRecognitionStatus.WAITING_FOR_TARGET,
            f"{source} detected; waiting for {target}",
        )
        return self._last_result

    def finalize_timeout(self) -> ScenarioRecognition:
        """Mark an incomplete action as not detected or uncertain."""

        if self._last_result.status in (
            ScenarioRecognitionStatus.COMPLETED,
            ScenarioRecognitionStatus.DISABLED,
            ScenarioRecognitionStatus.UNSUPPORTED,
        ):
            return self._last_result
        fraction = self._reliable_frame_fraction()
        status = (
            ScenarioRecognitionStatus.NOT_DETECTED
            if fraction >= self.config.minimum_reliable_frame_fraction
            else ScenarioRecognitionStatus.UNCERTAIN
        )
        reason = (
            "required transition was not observed"
            if status is ScenarioRecognitionStatus.NOT_DETECTED
            else "insufficient reliable pose evidence"
        )
        self._last_result = self._make_result(status, reason)
        return self._last_result

    def _initial_result(self) -> ScenarioRecognition:
        if not self.config.enabled:
            status = ScenarioRecognitionStatus.DISABLED
            message = "scenario recognition is disabled"
        elif self._steps is None:
            status = ScenarioRecognitionStatus.UNSUPPORTED
            message = f"no completion rule for {self.expected_activity_label!r}"
        else:
            status = ScenarioRecognitionStatus.WAITING_FOR_SOURCE
            message = f"waiting for {self._steps[0]}"
        return self._make_result(status, message)

    def _matches(self, step: str, activity: ActivityObservation) -> bool:
        if not activity.reliable:
            return False
        if step == "walking":
            return activity.motion is MotionState.WALKING
        if step == "fallen":
            return activity.posture is PostureState.FALLEN
        if step == "seated":
            return activity.posture is PostureState.SEATED
        if step == "standing":
            return activity.posture is PostureState.STANDING
        return False

    def _hold_seconds(self, step: str) -> float:
        return (
            self.config.walking_hold_seconds
            if step == "walking"
            else self.config.posture_hold_seconds
        )

    def _reliable_frame_fraction(self) -> float:
        if self._total_frames == 0:
            return 0.0
        return self._reliable_frames / self._total_frames

    def _make_result(
        self,
        status: ScenarioRecognitionStatus,
        message: str,
        *,
        completed_at_s: float | None = None,
    ) -> ScenarioRecognition:
        reason = message
        return ScenarioRecognition(
            expected_activity_label=self.expected_activity_label,
            status=status,
            observed_steps=tuple(self._observed_steps),
            message=message,
            source_confirmed_at_s=self._source_confirmed_at,
            target_started_at_s=self._target_started_at,
            completed_at_s=completed_at_s,
            reliable_frame_fraction=self._reliable_frame_fraction(),
            reason=reason,
        )
