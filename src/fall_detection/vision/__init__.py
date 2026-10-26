"""Camera-based pose extraction and proposed activity labels."""

from .rules import (
    BoundingBox,
    CocoKeypoint,
    DetectionOutput,
    DetectorState,
    DetectorTransition,
    FallEventProposal,
    FallRulesConfig,
    Keypoint,
    PoseObservation,
    RuleBasedFallDetector,
)
from .scenarios import (
    ActivityObservation,
    ActivityRecognizer,
    MotionState,
    PostureState,
    ScenarioCompletionConfig,
    ScenarioCompletionRecognizer,
    ScenarioRecognition,
    ScenarioRecognitionStatus,
)

__all__ = [
    "BoundingBox",
    "CocoKeypoint",
    "DetectionOutput",
    "DetectorState",
    "DetectorTransition",
    "FallEventProposal",
    "FallRulesConfig",
    "Keypoint",
    "PoseObservation",
    "RuleBasedFallDetector",
    "ActivityObservation",
    "ActivityRecognizer",
    "MotionState",
    "PostureState",
    "ScenarioCompletionConfig",
    "ScenarioCompletionRecognizer",
    "ScenarioRecognition",
    "ScenarioRecognitionStatus",
]
