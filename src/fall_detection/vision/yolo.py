"""Adapters from Ultralytics pose results to detector observations."""

from __future__ import annotations

from typing import Any

import numpy as np

from .rules import BoundingBox, Keypoint, PoseObservation


def _array(value: Any) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def largest_person_index(result: Any) -> int | None:
    """Select the largest detected person in an Ultralytics result."""

    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None
    xyxy = _array(boxes.xyxy)
    areas = np.maximum(0.0, xyxy[:, 2] - xyxy[:, 0]) * np.maximum(
        0.0, xyxy[:, 3] - xyxy[:, 1]
    )
    return int(np.argmax(areas))


def observation_from_yolo(
    result: Any,
    timestamp_s: float,
    person_index: int,
) -> PoseObservation:
    """Convert one selected YOLO person into normalized detector input."""

    normalized_points = _array(result.keypoints.xyn)[person_index]
    confidence_values = getattr(result.keypoints, "conf", None)
    if confidence_values is None:
        confidences = np.ones(len(normalized_points), dtype=float)
    else:
        confidences = _array(confidence_values)[person_index]
    keypoints = tuple(
        Keypoint(float(point[0]), float(point[1]), float(confidence))
        for point, confidence in zip(
            normalized_points, confidences, strict=True
        )
    )

    normalized_box = _array(result.boxes.xyxyn)[person_index]
    box = BoundingBox(*(float(value) for value in normalized_box))
    track_id = None
    identifiers = getattr(result.boxes, "id", None)
    if identifiers is not None:
        track_id = int(_array(identifiers)[person_index])
    return PoseObservation(timestamp_s, keypoints, box, track_id)
