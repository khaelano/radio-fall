"""Exercise grouped evaluation and reproducible WiFall result publication."""

import joblib
import numpy as np
import pytest

from fall_detection.analysis.wifall.dataset import WindowDataset
from fall_detection.analysis.wifall.experiment import (
    grouped_holdout,
    run_experiment,
    save_experiment,
)
from fall_detection.analysis.wifall.model import WiFallConfig


def dataset():
    """Build overlapping-window groups with distinct resting chunks."""
    rng = np.random.default_rng(12)
    targets = np.repeat([0, 1] * 4, 2)
    groups = np.repeat([f"attempt-{i}" for i in range(8)], 2)
    windows = 10 + rng.normal(0, 0.01, (16, 20, 4, 3))
    windows[targets == 1] += np.sin(np.linspace(0, np.pi, 20))[None, :, None, None] * 6
    stable = 10 + rng.normal(0, 0.01, (8, 20, 4, 3))
    return WindowDataset(
        windows=windows,
        targets=targets,
        groups=groups,
        metadata=[
            {
                "session_id": f"session-{index // 8}",
                "participant_id": f"participant-{index // 8}",
                "attempt_key": str(group),
                "start_ns": index * 100,
            }
            for index, group in enumerate(groups)
        ],
        stable_windows=stable,
        stable_groups=np.array([f"attempt-{i}" for i in range(8)]),
        provenance={
            "parameters": {"sample_rate_hz": 10, "window_seconds": 2},
            "coordinates": {
                "receivers": [f"rx-{i}" for i in range(4)],
                "subcarriers": [-2, 2, 3],
            },
            "center_frequency_hz": 5.22e9,
            "subcarrier_spacing_hz": 78125,
            "sources": [{"source_fingerprint": "synthetic-v1"}],
        },
    )


@pytest.mark.parametrize("split_by", ["attempt", "session", "participant"])
def test_grouped_holdout_keeps_overlapping_windows_and_requested_identities_together(
    split_by,
):
    source = dataset()
    train, test = grouped_holdout(
        source, split_by=split_by, test_fraction=0.25, seed=42
    )
    assert not set(source.groups[train]) & set(source.groups[test])
    for indices in (train, test):
        assert set(source.targets[indices]) == {0, 1}
    if split_by != "attempt":
        key = f"{split_by}_id"
        assert not {source.metadata[i][key] for i in train} & {
            source.metadata[i][key] for i in test
        }


@pytest.mark.parametrize("classifier", ["random_forest", "one_class_svm"])
@pytest.mark.parametrize("representation", ["statistics", "singular_values"])
def test_run_experiment_uses_training_rest_only_and_saved_predictions_replay(
    tmp_path, classifier, representation
):
    source = dataset()
    config = WiFallConfig(
        sample_rate_hz=10,
        smoothing_samples=1,
        lof_neighbors=5,
        forest_trees=10,
        representation=representation,
    )
    result = run_experiment(source, config, classifier=classifier, max_stable_windows=3)
    split = result.report["split"]
    assert set(split["stable_attempts"]) <= set(split["train_attempts"])
    assert not set(split["stable_attempts"]) & set(split["test_attempts"])
    assert split["stable_windows"] == 3
    assert sum(map(sum, result.report["held_out"]["confusion_matrix"])) == len(
        result.predictions
    )
    output = tmp_path / "result"
    save_experiment(result, output)
    saved = joblib.load(output / "model.joblib")
    test = [
        i for i, group in enumerate(source.groups) if group in split["test_attempts"]
    ]
    np.testing.assert_array_equal(
        saved["detector"].predict(source.windows[test]),
        [row["prediction"] for row in result.predictions],
    )
    assert (output / "report.json").is_file()
    assert (output / "predictions.json").is_file()
    with pytest.raises(FileExistsError):
        save_experiment(result, output)


def test_run_experiment_refuses_resting_data_from_test_attempts():
    source = dataset()
    _, test = grouped_holdout(source, split_by="attempt", test_fraction=0.25, seed=42)
    only_test_rest = np.isin(source.stable_groups, source.groups[test])
    # The dataset is frozen, so build an explicit test-only resting dataset.
    invalid = WindowDataset(
        source.windows,
        source.targets,
        source.groups,
        source.metadata,
        np.full((int(only_test_rest.sum()), 20, 4, 3), 10),
        source.stable_groups[only_test_rest],
        source.provenance,
    )
    with pytest.raises(ValueError, match="training attempts"):
        run_experiment(invalid, WiFallConfig(sample_rate_hz=10))


def test_run_experiment_rejects_different_rates_even_when_sample_counts_match():
    with pytest.raises(ValueError, match="sampling rate/window duration"):
        run_experiment(dataset(), WiFallConfig(sample_rate_hz=5, window_seconds=4))
