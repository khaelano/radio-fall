"""Grouped FallDeFi evaluation and reproducible result publication."""

import joblib
import numpy as np
import pytest
from synthetic_traces import burst_trace

from fall_detection.analysis.falldefi.dataset import TraceDataset
from fall_detection.analysis.falldefi.experiment import run_experiment, save_experiment
from fall_detection.analysis.falldefi.model import FallDeFiConfig

CONFIG = FallDeFiConfig(cv_folds=2, svm_log2_c=(0, 4), svm_log2_gamma=(0, 2))


def dataset():
    """Build eight fall and eight non-fall attempts with their own rest."""
    rng = np.random.default_rng(11)
    targets = np.array([1, 0] * 8)
    traces = [
        burst_trace(rng, frequency=15, start=4, stop=6.5)
        if target
        else burst_trace(rng, frequency=8, start=2, stop=7, amplitude=1)
        for target in targets
    ]
    groups = np.array([f"session-1/attempt-{i}" for i in range(16)])
    return TraceDataset(
        traces=traces,
        targets=targets,
        groups=groups,
        metadata=[
            {"session_id": "session-1", "participant_id": "p1", "duration_seconds": 10}
            for _ in groups
        ],
        resting=[
            burst_trace(rng, frequency=1, start=0, stop=1, seconds=4, amplitude=0)
            for _ in groups
        ],
        resting_groups=groups.copy(),
        provenance={
            "parameters": {"sample_rate_hz": 120},
            "coordinates": {"receivers": ["rx-1"], "subcarriers": [2]},
        },
    )


def test_run_experiment_uses_training_rest_and_saved_model_replays(tmp_path):
    source = dataset()
    result = run_experiment(source, CONFIG, test_fraction=0.25)
    split = result.report["split"]
    assert not set(split["train_attempts"]) & set(split["test_attempts"])
    assert split["resting_segments"] == split["train_traces"]
    assert sum(map(sum, result.report["held_out"]["confusion_matrix"])) == len(
        result.predictions
    )
    alarms = result.report["held_out_false_alarms"]
    assert alarms["non_fall_trace_hours"] == pytest.approx(
        sum(row["target"] == 0 for row in result.predictions) * 10 / 3600
    )
    output = tmp_path / "result"
    save_experiment(result, output)
    saved = joblib.load(output / "model.joblib")["detector"]
    test = [
        i for i, group in enumerate(source.groups) if group in split["test_attempts"]
    ]
    np.testing.assert_array_equal(
        saved.predict([source.traces[i] for i in test]),
        [row["prediction"] for row in result.predictions],
    )
    assert (output / "report.json").is_file()
    with pytest.raises(FileExistsError):
        save_experiment(result, output)


def test_run_experiment_refuses_without_training_rest():
    source = dataset()
    no_rest = TraceDataset(
        source.traces,
        source.targets,
        source.groups,
        source.metadata,
        [],
        np.array([], dtype=str),
        source.provenance,
    )
    with pytest.raises(ValueError, match="training attempts"):
        run_experiment(no_rest, CONFIG)
