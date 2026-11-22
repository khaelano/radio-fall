"""Grouped WiFall evaluation and reproducible result publication."""

import joblib
import numpy as np
import pytest

from fall_detection.analysis.wifall.dataset import WindowSet
from fall_detection.analysis.wifall.experiment import run_experiment, save_experiment
from fall_detection.analysis.wifall.model import WiFallConfig
from fall_detection.analysis.wifall.representation import represent_windows

REPRESENT = {"sample_rate_hz": 10, "smoothing_samples": 1, "entropy_bins": 16}


def dataset(resting_groups=None):
    """Build two overlapping windows per attempt with each attempt's own rest."""
    rng = np.random.default_rng(12)
    targets = np.repeat([0, 1] * 4, 2)
    groups = np.repeat([f"attempt-{i}" for i in range(8)], 2)
    raw = 10 + rng.normal(0, 0.01, (16, 20, 4, 3))
    raw[targets == 1] += np.sin(np.linspace(0, np.pi, 20))[None, :, None, None] * 6
    rest = represent_windows(10 + rng.normal(0, 0.01, (8, 20, 4, 3)), **REPRESENT)
    return WindowSet(
        windows=represent_windows(raw, **REPRESENT),
        targets=targets,
        groups=groups,
        metadata=[
            {"session_id": f"session-{i // 8}", "participant_id": "p1", "start_ns": i}
            for i in range(16)
        ],
        resting_streams=rest.streams,
        resting_groups=(
            np.array([f"attempt-{i}" for i in range(8)])
            if resting_groups is None
            else resting_groups
        ),
        provenance={
            "parameters": {"sample_rate_hz": 10, **REPRESENT},
            "coordinates": {"receivers": ["rx-1"], "subcarriers": [2]},
        },
    )


@pytest.mark.parametrize("classifier", ["random_forest", "one_class_svm"])
def test_run_experiment_uses_training_rest_and_saved_model_replays(
    tmp_path, classifier
):
    source = dataset()
    config = WiFallConfig(
        sample_rate_hz=10, lof_neighbors=5, forest_trees=10, classifier=classifier
    )
    result = run_experiment(source, config, max_stable_windows=3)
    split = result.report["split"]
    assert set(split["stable_attempts"]) <= set(split["train_attempts"])
    assert split["stable_windows"] == 3
    attempts = result.report["held_out_attempts"]["confusion_matrix"]
    assert sum(map(sum, attempts)) == len(split["test_attempts"])
    output = tmp_path / "result"
    save_experiment(result, output)
    saved = joblib.load(output / "model.joblib")
    test = np.isin(source.groups, split["test_attempts"])
    np.testing.assert_array_equal(
        saved["detector"].predict(source.windows.take(test)),
        [row["prediction"] for row in result.predictions],
    )
    assert saved["representation"]["smoothing_samples"] == 1
    with pytest.raises(FileExistsError):
        save_experiment(result, output)


def test_run_experiment_refuses_resting_data_from_test_attempts():
    config = WiFallConfig(sample_rate_hz=10, lof_neighbors=5, forest_trees=10)
    only_elsewhere = dataset(resting_groups=np.array(["other"] * 8))
    with pytest.raises(ValueError, match="training attempts"):
        run_experiment(only_elsewhere, config)
    with pytest.raises(ValueError, match="sampling rate"):
        run_experiment(dataset(), WiFallConfig(sample_rate_hz=5))
