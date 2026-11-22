"""Grouped holdout splits shared by the classical baselines."""

import numpy as np
import pytest

from fall_detection.analysis.baselines._grouped_holdout import grouped_holdout


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
