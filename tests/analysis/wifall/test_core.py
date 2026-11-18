"""Deterministic checks of WiFall equations, training boundaries and gating."""

from dataclasses import replace

import numpy as np
import pytest
from sklearn.exceptions import NotFittedError

from fall_detection.analysis.wifall import WiFallConfig, WiFallDetector
from fall_detection.analysis.wifall.features import (
    singular_value_features,
    statistical_features,
)
from fall_detection.analysis.wifall.signal import (
    aggregate_streams,
    weighted_moving_average,
)


def samples():
    """Return a small reproducible four-stream amplitude experiment."""
    rng = np.random.default_rng(24)
    stable = 10 + rng.normal(0, 0.01, (100, 4, 3))
    windows = 10 + rng.normal(0, 0.01, (12, 20, 4, 3))
    windows[6:] += np.sin(np.linspace(0, np.pi, 20))[None, :, None, None] * 8
    return windows, np.repeat([0, 1], 6), stable


def config(**kwargs):
    """Return economical model parameters for the synthetic experiment."""
    return WiFallConfig(
        sample_rate_hz=10,
        lof_neighbors=5,
        forest_trees=10,
        smoothing_samples=1,
        **kwargs,
    )


def test_weighted_moving_average_equation_and_segment_start():
    actual = weighted_moving_average(np.array([2, 5, 8, 11]), 3)
    np.testing.assert_allclose(actual, [2, 4, 6, 9])


def test_aggregate_streams_uses_subcarrier_count_not_weight_sum():
    values = np.array([[[2, 4], [6, 8]]])
    np.testing.assert_allclose(aggregate_streams(values, np.array([1, 2])), [[5, 11]])


def test_singular_value_features_retains_three_uncentered_values():
    window = np.diag([5.0, 3.0, 1.0]).reshape(3, 1, 3)
    np.testing.assert_allclose(singular_value_features(window), [5, 3, 1])


def test_statistical_features_has_duration_units_and_finite_constant_tones():
    features = statistical_features(
        np.full((20, 2, 3), 10.0),
        np.ones((20, 2), dtype=bool),
        sample_rate_hz=10,
        entropy_bins=16,
    ).reshape(2, 7)
    np.testing.assert_allclose(features[:, 2], 2)
    np.testing.assert_allclose(features[:, [0, 1, 3, 4, 5, 6]], 0)


def test_predict_activity_requires_simultaneous_strict_majority():
    windows, labels, stable = samples()
    model = WiFallDetector(config()).fit(windows, labels, stable)
    probes = np.full((3, 20, 4, 3), 10.0)
    probes[0, :, :2] += 8
    probes[1, :, :3] += 8
    # Two streams at each time never form a simultaneous strict majority.
    probes[2, :10, :2] += 8
    probes[2, 10:, 2:] += 8
    np.testing.assert_array_equal(model.predict_activity(probes), [False, True, False])


def test_one_class_svm_fits_only_fall_features_and_prediction_preserves_scaler():
    windows, labels, stable = samples()
    model = WiFallDetector(config(), classifier="one_class_svm").fit(
        windows, labels, stable
    )
    features = model.transform(windows)
    np.testing.assert_allclose(model.scaler_.mean_, features[labels == 1].mean(axis=0))
    mean = model.scaler_.mean_.copy()
    model.predict(windows * 100)
    np.testing.assert_array_equal(model.scaler_.mean_, mean)
    scaled = model.scaler_.transform(features)
    expected = (model.classifier_.predict(scaled) == 1) & model.predict_activity(
        windows
    )
    np.testing.assert_array_equal(model.predict(windows), expected.astype(int))
    np.testing.assert_array_equal(
        model.predict_ungated(windows),
        (model.classifier_.predict(scaled) == 1).astype(int),
    )


def test_fit_filters_stable_chunks_without_crossing_boundaries():
    windows, labels, _ = samples()
    stable = np.stack([np.full((20, 4, 3), level) for level in (10.0, 20.0)])
    model = WiFallDetector(replace(config(), smoothing_samples=3)).fit(
        windows, labels, stable
    )
    for activity_model in model.activity_models_:
        np.testing.assert_array_equal(
            activity_model._fit_X[:, 0], np.repeat([10.0, 20.0], 20)
        )


@pytest.mark.parametrize("representation", ["statistics", "singular_values"])
def test_random_forest_is_deterministic_and_gates_inactive_windows(representation):
    windows, labels, stable = samples()
    first = WiFallDetector(config(representation=representation)).fit(
        windows, labels, stable
    )
    second = WiFallDetector(config(representation=representation)).fit(
        windows, labels, stable
    )
    np.testing.assert_array_equal(first.predict(windows), second.predict(windows))
    np.testing.assert_array_equal(first.predict(windows[:6]), 0)
    assert len(first.feature_names_) == first.transform(windows).shape[1]


def test_model_rejects_missing_amplitudes_wrong_schema_and_unfitted_calls():
    windows, labels, stable = samples()
    model = WiFallDetector(config())
    with pytest.raises(NotFittedError):
        model.predict(windows)
    missing = windows.copy()
    missing[0, 0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        model.fit(missing, labels, stable)
    model.fit(windows, labels, stable)
    with pytest.raises(ValueError, match="schema"):
        model.predict(windows[:, :, :3])
    with pytest.raises(ValueError, match="binary"):
        model.fit(windows, labels + 1, stable)


@pytest.mark.parametrize(
    "parameters",
    [
        {"sample_rate_hz": float("nan")},
        {"smoothing_samples": 0},
        {"svm_nu": 0},
        {"window_seconds": 0.001},
        {"representation": "combined"},
    ],
)
def test_config_rejects_invalid_parameters(parameters):
    with pytest.raises(ValueError):
        WiFallConfig(**parameters)
