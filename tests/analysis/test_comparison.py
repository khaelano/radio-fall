"""Shared held-out attempts and attempt-level scoring across approaches."""

import json

import polars as pl
import pytest

from fall_detection.analysis.comparison import (
    attempt_scores,
    baseline_group,
    choose_threshold,
    debounce,
    latest_run,
    latest_split_run,
    latest_training_run,
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


def test_latest_training_run_skips_other_representations(tmp_path):
    for name, manifest in (
        ("20261101T000000Z", {}),
        ("20261102T000000Z", {"representation": "log1p_squared_difference"}),
        ("20261103T000000Z", {"representation": "filtered_amplitude"}),
    ):
        (tmp_path / name / "full").mkdir(parents=True)
        (tmp_path / name / "manifest.json").write_text(json.dumps(manifest))
    assert latest_training_run(tmp_path, "full").name == "20261102T000000Z"
    assert (
        latest_training_run(tmp_path, "full", representation="filtered_amplitude").name
        == "20261103T000000Z"
    )
    (tmp_path / "20261102T000000Z" / "manifest.json").write_text(
        json.dumps({"representation": "other"})
    )
    assert latest_training_run(tmp_path, "full").name == "20261101T000000Z"
    with pytest.raises(FileNotFoundError, match="absent"):
        latest_training_run(tmp_path, "full", representation="absent")
    (tmp_path / "20261104T000000Z" / "full").mkdir(parents=True)
    (tmp_path / "20261104T000000Z" / "manifest.json").write_text(
        json.dumps({"held_out_session": "akmal"})
    )
    assert latest_training_run(tmp_path, "full").name == "20261101T000000Z"
    assert (
        latest_training_run(tmp_path, "full", held_out_session="akmal").name
        == "20261104T000000Z"
    )
    (tmp_path / "20261105T000000Z" / "full").mkdir(parents=True)
    (tmp_path / "20261105T000000Z" / "manifest.json").write_text(
        json.dumps({"held_out_session": ["continuous_non_fall", "akmal"]})
    )
    assert (
        latest_training_run(
            tmp_path, "full", held_out_session=("akmal", "continuous_non_fall")
        ).name
        == "20261105T000000Z"
    )
    assert (
        latest_training_run(tmp_path, "full", held_out_session="akmal").name
        == "20261104T000000Z"
    )


def test_latest_training_run_separates_kept_splits(tmp_path):
    for name, manifest in (
        ("20261101T000000Z", {"held_out_session": "khaelano"}),
        ("20261102T000000Z", {"held_out_session": "khaelano", "keep_split": []}),
        ("20261103T000000Z", {"held_out_session": None, "keep_split": None}),
    ):
        (tmp_path / name / "full").mkdir(parents=True)
        (tmp_path / name / "manifest.json").write_text(json.dumps(manifest))
    assert (
        latest_training_run(tmp_path, "full", held_out_session="khaelano").name
        == "20261101T000000Z"
    )
    assert (
        latest_training_run(
            tmp_path, "full", held_out_session="khaelano", keep_split=()
        ).name
        == "20261102T000000Z"
    )
    assert latest_training_run(tmp_path, "full", keep_split=()).name == (
        "20261103T000000Z"
    )


def test_latest_split_run_selects_by_split_hash(tmp_path):
    for name, digest in (
        ("20261101T000000Z", "a" * 64),
        ("20261102T000000Z", "b" * 64),
        ("20261103T000000Z", "a" * 64),
    ):
        (tmp_path / name).mkdir()
        (tmp_path / name / "manifest.json").write_text(
            json.dumps({"split_sha256": digest})
        )
    assert latest_split_run(tmp_path, "a" * 64).name == "20261103T000000Z"
    assert latest_split_run(tmp_path, "b" * 64).name == "20261102T000000Z"
    with pytest.raises(FileNotFoundError, match="cccccccccccc"):
        latest_split_run(tmp_path, "c" * 64)


def _window(group, segment, start, probability, target=0):
    return {
        "group": group,
        "segment_id": segment,
        "start": start,
        "stop": start + 4,
        "target": target,
        "probability": probability,
    }


def test_debounce_needs_overlapping_alarms_in_one_segment():
    rows = [
        _window("a", "s0", 0, 0.9),
        _window("a", "s0", 2, 0.9),  # overlaps the previous window: run of 2
        _window("b", "s0", 0, 0.9),
        _window("b", "s0", 8, 0.9),  # after a gap: no run
        _window("c", "s0", 0, 0.9),
        _window("c", "s1", 2, 0.9),  # next segment: no run
    ]
    predicted = {
        (row["group"], row["start"]): row["prediction"]
        for row in debounce(rows, threshold=0.5, consecutive=2)
    }
    assert predicted == {
        ("a", 0): 0,
        ("a", 2): 1,
        ("b", 0): 0,
        ("b", 8): 0,
        ("c", 0): 0,
        ("c", 2): 0,
    }
    with pytest.raises(ValueError, match="at least one"):
        debounce(rows, threshold=0.5, consecutive=0)


def test_choose_threshold_takes_lowest_threshold_within_target():
    rows = [
        _window("s::fall", "s0", 0, 0.8, target=1),
        _window("s::fall", "s0", 2, 0.7, target=1),
        _window("s::quiet", "s0", 0, 0.3),
        _window("s::quiet", "s0", 2, 0.4),
        _window("s::busy", "s0", 0, 0.6),
        _window("s::busy", "s0", 2, 0.65),
    ]
    # Attempt scores at k = 2: fall 0.7, busy 0.6, quiet 0.3.
    scores = attempt_scores(rows, consecutive=2)
    assert dict(zip(scores["group"], scores["score"], strict=True)) == {
        "s/busy": 0.6,
        "s/fall": 0.7,
        "s/quiet": 0.3,
    }
    # One of two non-falls may alarm: any threshold in (0.3, 0.6] flags only
    # "busy"; the midpoint is returned.
    choice = choose_threshold(rows, target_false_positive_rate=0.5, consecutive=2)
    assert choice == pytest.approx(
        {"threshold": 0.45, "false_positive_rate": 0.5, "recall": 1.0}
    )
    # No non-fall may alarm: (0.6, 0.7] keeps the fall.
    strict = choose_threshold(rows, target_false_positive_rate=0.0, consecutive=2)
    assert strict == pytest.approx(
        {"threshold": 0.65, "false_positive_rate": 0.0, "recall": 1.0}
    )
    # The debounced test rule agrees with the attempt scores.
    predicted = debounce(rows, threshold=strict["threshold"], consecutive=2)
    assert {row["group"] for row in predicted if row["prediction"]} == {"s::fall"}
