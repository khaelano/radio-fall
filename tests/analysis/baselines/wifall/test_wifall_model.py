"""WiFall activity gating, pooled features and classifiers."""

from dataclasses import replace

import numpy as np
import pytest
from sklearn.exceptions import NotFittedError

from fall_detection.analysis.baselines.wifall.model import WiFallConfig, WiFallDetector
from fall_detection.analysis.baselines.wifall.representation import (
    Representations,
    represent_windows,
)

REPRESENT = {"sample_rate_hz": 10, "smoothing_samples": 1, "entropy_bins": 16}
CONFIG = WiFallConfig(sample_rate_hz=10, lof_neighbors=5, forest_trees=10)


def samples():
    """Return represented windows, labels and resting streams for four receivers."""
    rng = np.random.default_rng(24)
    windows = 10 + rng.normal(0, 0.01, (12, 20, 4, 3))
    windows[6:] += np.sin(np.linspace(0, np.pi, 20))[None, :, None, None] * 8
    resting = 10 + rng.normal(0, 0.01, (5, 20, 4, 3))
    rest = represent_windows(resting, **REPRESENT).streams
    return represent_windows(windows, **REPRESENT), np.repeat([0, 1], 6), rest


def probes(active, present):
    """Return windows whose streams deviate on the given receivers."""
    count = len(active)
    streams = np.zeros((count, 20, 4), dtype=np.float32)
    statistics = np.zeros((count, 4, 6))
    for window, receivers in enumerate(active):
        for receiver, start, stop in receivers:
            streams[window, start:stop, receiver] = 0.5
    for window, receivers in enumerate(present):
        missing = [r for r in range(4) if r not in receivers]
        streams[window, :, missing] = np.nan
        statistics[window, missing] = np.nan
    return Representations(
        statistics, np.where(np.isnan(statistics[..., :3]), np.nan, 0), streams
    )


def test_activity_gate_needs_a_strict_majority_of_present_receivers():
    windows, labels, rest = samples()
    model = WiFallDetector(CONFIG).fit(windows, labels, rest)
    everyone = [range(4)] * 3
    gate = model.predict_activity(
        probes(
            [
                [(0, 0, 20), (1, 0, 20)],
                [(0, 0, 20), (1, 0, 20), (2, 0, 20)],
                # Two receivers at each time never form a strict majority of four.
                [(0, 0, 10), (1, 0, 10), (2, 10, 20), (3, 10, 20)],
            ],
            everyone,
        )
    )
    np.testing.assert_array_equal(gate, [False, True, False])
    # Of two present receivers, both must be active.
    two = model.predict_activity(
        probes([[(0, 0, 20), (1, 0, 20)], [(0, 0, 20)]], [[0, 1], [0, 1]])
    )
    np.testing.assert_array_equal(two, [True, False])


def test_pooled_features_ignore_dropped_receivers():
    windows, labels, rest = samples()
    model = WiFallDetector(CONFIG).fit(windows, labels, rest)
    dropped = Representations(
        windows.statistics.copy(),
        windows.singular_values.copy(),
        windows.streams.copy(),
    )
    dropped.statistics[:, 3] = np.nan
    dropped.singular_values[:, 3] = np.nan
    dropped.streams[:, :, 3] = np.nan
    features = model.transform(dropped)
    names = list(model.feature_names_)
    expected = np.nanmean(windows.statistics[:, :3, 0], axis=1)
    np.testing.assert_allclose(
        features[:, names.index("normalized_std_mean")], expected
    )
    assert np.isfinite(features).all()


def test_one_class_svm_fits_only_fall_features():
    windows, labels, rest = samples()
    model = WiFallDetector(replace(CONFIG, classifier="one_class_svm")).fit(
        windows, labels, rest
    )
    features = model.transform(windows)
    np.testing.assert_allclose(model.scaler_.mean_, features[labels == 1].mean(axis=0))
    gated, ungated, gate = model.predict_all(windows)
    np.testing.assert_array_equal(gated, ungated & gate)
    np.testing.assert_array_equal(model.predict_ungated(windows), ungated)


@pytest.mark.parametrize("features,count", [("statistics", 14), ("all", 20)])
def test_random_forest_is_deterministic_and_gates_inactive_windows(features, count):
    windows, labels, rest = samples()
    config = replace(CONFIG, features=features)
    first = WiFallDetector(config).fit(windows, labels, rest)
    second = WiFallDetector(config).fit(windows, labels, rest)
    np.testing.assert_array_equal(first.predict(windows), second.predict(windows))
    np.testing.assert_array_equal(first.predict(windows.take(np.arange(6))), 0)
    assert len(first.feature_names_) == first.transform(windows).shape[1] == count


def test_detector_rejects_bad_labels_schemas_and_unfitted_calls():
    windows, labels, rest = samples()
    model = WiFallDetector(CONFIG)
    with pytest.raises(NotFittedError):
        model.predict(windows)
    with pytest.raises(ValueError, match="binary"):
        model.fit(windows, labels + 1, rest)
    model.fit(windows, labels, rest)
    three = Representations(
        windows.statistics[:, :3],
        windows.singular_values[:, :3],
        windows.streams[..., :3],
    )
    with pytest.raises(ValueError, match="schema"):
        model.predict(three)


@pytest.mark.parametrize(
    "parameters",
    [
        {"sample_rate_hz": float("nan")},
        {"lof_neighbors": 1},
        {"svm_nu": 0},
        {"features": "combined"},
        {"class_weight": "inverse"},
    ],
)
def test_config_rejects_invalid_parameters(parameters):
    with pytest.raises(ValueError):
        WiFallConfig(**parameters)
