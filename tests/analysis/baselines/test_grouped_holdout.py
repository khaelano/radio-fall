"""Grouped holdout splits shared by the classical baselines."""

import numpy as np
import pytest

from fall_detection.analysis.baselines._grouped_holdout import (
    assigned_holdout,
    grouped_holdout,
)


@pytest.mark.parametrize("split_by", ["attempt", "session", "participant"])
def test_grouped_holdout_keeps_attempts_and_requested_identities_together(split_by):
    targets = np.repeat([0, 1] * 4, 2)
    groups = np.repeat([f"attempt-{i}" for i in range(8)], 2)
    metadata = [
        {"session_id": f"session-{i // 8}", "participant_id": f"person-{i // 8}"}
        for i in range(len(targets))
    ]
    train, test = grouped_holdout(
        targets, groups, metadata, split_by=split_by, test_fraction=0.25, seed=42
    )
    assert not set(groups[train]) & set(groups[test])
    for indices in (train, test):
        assert set(targets[indices]) == {0, 1}
    if split_by != "attempt":
        key = f"{split_by}_id"
        assert not {metadata[i][key] for i in train} & {metadata[i][key] for i in test}


def test_assigned_holdout_trains_on_validation_and_leaves_unassigned_out():
    targets = np.array([0, 1, 0, 1, 0, 1, 1])
    groups = np.array(["a", "b", "c", "d", "e", "f", "g"])
    assignment = {"a": "train", "b": "validation", "c": "test", "d": "test"}
    assignment |= {"e": "train", "f": "train"}
    train, test, unassigned = assigned_holdout(targets, groups, assignment)
    assert groups[train].tolist() == ["a", "b", "e", "f"]
    assert groups[test].tolist() == ["c", "d"]
    assert unassigned == ["g"]


def test_assigned_holdout_rejects_unknown_names_and_one_class_sides():
    targets = np.array([0, 1, 0, 1])
    groups = np.array(["a", "b", "c", "d"])
    with pytest.raises(ValueError, match="Unknown split"):
        assigned_holdout(targets, groups, dict.fromkeys(groups, "holdout"))
    one_class = {"a": "train", "b": "train", "c": "test", "d": "train"}
    with pytest.raises(ValueError, match="test attempts need both classes"):
        assigned_holdout(targets, groups, one_class)
