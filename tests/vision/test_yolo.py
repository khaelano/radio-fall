from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from fall_detection.vision.yolo import (
    largest_person_index,
    observation_from_yolo,
)


class Boxes:
    def __init__(self):
        self.xyxy = np.array([[0, 0, 10, 10], [0, 0, 30, 20]])
        self.xyxyn = np.array(
            [[0.0, 0.0, 0.1, 0.1], [0.1, 0.2, 0.8, 0.9]]
        )
        self.id = np.array([3, 9])

    def __len__(self):
        return 2


def result_fixture():
    points = np.zeros((2, 17, 2), dtype=float)
    points[1, :, 0] = 0.4
    points[1, :, 1] = 0.6
    confidence = np.full((2, 17), 0.8)
    return SimpleNamespace(
        boxes=Boxes(),
        keypoints=SimpleNamespace(xyn=points, conf=confidence),
    )


def test_largest_person_index_selects_largest_box():
    assert largest_person_index(result_fixture()) == 1


def test_observation_from_yolo_normalizes_selected_person():
    converted = observation_from_yolo(result_fixture(), 12.5, 1)

    assert converted.timestamp_s == 12.5
    assert converted.track_id == 9
    assert converted.box.x_min == 0.1
    assert converted.box.y_max == 0.9
    assert len(converted.keypoints) == 17
    assert converted.keypoints[0].x == 0.4
    assert converted.keypoints[0].confidence == 0.8
