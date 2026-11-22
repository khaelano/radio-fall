"""Shared held-out attempts and attempt-level scoring across approaches."""

import polars as pl
import pytest

from fall_detection.analysis.comparison import (
    baseline_group,
    latest_run,
    split_assignment,
    split_labels,
    split_sessions,
    summarize,
)

SPLIT = pl.DataFrame(
    {
        "group": ["s1::001/01", "s1::001/01", "s1::002/01", "s2::001/01"],
        "split": ["train", "train", "test", "validation"],
        "activity_label": ["walk_to_fall", "walk_to_fall", "sit_to_stand", "non_fall"],
        "target": [1, 1, 0, 0],
    }
)


def test_split_helpers_translate_groups_labels_and_sessions():
    assert baseline_group("s1::001/01") == "s1/001/01"
    assert baseline_group("s1/001/01") == "s1/001/01"
    assert split_assignment(SPLIT) == {
        "s1/001/01": "train",
        "s1/002/01": "test",
        "s2/001/01": "validation",
    }
    assert split_labels(SPLIT) == (("walk_to_fall",), ("non_fall", "sit_to_stand"))
    assert split_sessions(SPLIT) == ["s1", "s2"]
    with pytest.raises(ValueError, match="no session"):
        baseline_group("001")
    with pytest.raises(ValueError, match="both targets"):
        split_labels(SPLIT.with_columns(pl.Series("target", [1, 0, 0, 0])))


def test_summarize_reduces_units_to_attempts_and_reports_unscored(tmp_path):
    rows = [
        {"group": "s/a", "target": 1, "prediction": 0},
        {"group": "s/a", "target": 1, "prediction": 1},
        {"group": "s::b", "target": 0, "prediction": 1},
        {"group": "s/c", "target": 0, "prediction": 0},
    ]
    result = summarize("model", "window", rows, {"s/a", "s/b", "s/c", "s/d"})
    assert result["units"] == 4
    assert result["attempts"] == 3
    assert result["attempt_metrics"]["confusion_matrix"] == [[1, 1], [0, 1]]
    assert result["unit_metrics"]["confusion_matrix"] == [[1, 1], [1, 1]]
    assert result["unscored_test_attempts"] == ["s/d"]
    with pytest.raises(ValueError, match="outside the test split"):
        summarize("model", "window", rows, {"s/a"})
    for name in ("20261101T000000Z", "20261102T000000Z", "20261103T000000Z"):
        (tmp_path / name).mkdir()
    (tmp_path / "20261101T000000Z" / "metrics.json").write_text("{}")
    (tmp_path / "20261102T000000Z" / "metrics.json").write_text("{}")
    assert latest_run(tmp_path, "metrics.json").name == "20261102T000000Z"
    with pytest.raises(FileNotFoundError):
        latest_run(tmp_path, "missing.json")
