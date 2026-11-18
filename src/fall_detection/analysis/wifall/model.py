"""Training-only stable profiles and classifiers for a WiFall adaptation."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import NotFittedError
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from .features import STATISTIC_NAMES, singular_value_features, statistical_features
from .signal import aggregate_streams, validate_amplitudes, weighted_moving_average


@dataclass(frozen=True)
class WiFallConfig:
    """Paper window duration and explicit implementation hyperparameters.

    All numerical defaults other than the two-second duration are adaptation
    choices. The sample rate describes the supplied data, not resampling.
    """

    sample_rate_hz: float = 120
    window_seconds: float = 2
    smoothing_samples: int = 5
    lof_neighbors: int = 20
    lof_threshold: float = 1.5
    svm_nu: float = 0.1
    svm_gamma: str | float = "scale"
    forest_trees: int = 200
    random_seed: int = 42
    representation: Literal["statistics", "singular_values"] = "statistics"
    entropy_bins: int = 16

    def __post_init__(self) -> None:
        for name in ("sample_rate_hz", "window_seconds", "lof_threshold"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in (
            "smoothing_samples",
            "lof_neighbors",
            "forest_trees",
            "entropy_bins",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.lof_neighbors < 2 or self.entropy_bins < 2:
            raise ValueError("LOF requires at least two neighbors and entropy two bins")
        samples = self.sample_rate_hz * self.window_seconds
        if samples < 2 or not np.isclose(samples, round(samples)):
            raise ValueError(
                "Window must contain an integral number of at least two samples"
            )
        if not np.isfinite(self.svm_nu) or not 0 < self.svm_nu <= 1:
            raise ValueError("svm_nu must be in (0, 1]")
        if self.representation not in {"statistics", "singular_values"}:
            raise ValueError("Unknown feature representation")
        if isinstance(self.svm_gamma, str):
            if self.svm_gamma not in {"scale", "auto"}:
                raise ValueError("svm_gamma must be scale, auto or a positive number")
        elif not np.isfinite(self.svm_gamma) or self.svm_gamma <= 0:
            raise ValueError("svm_gamma must be scale, auto or a positive number")

    @property
    def window_samples(self) -> int:
        """Return the required number of time samples in each input window."""
        return round(self.sample_rate_hz * self.window_seconds)


class WiFallDetector:
    """Causal amplitude smoothing, LOF activity gating and fall classification.

    Args:
        config: Sampling, representation and model parameters.
        classifier: Random forest or fall-trained one-class SVM.
        frequency_weights: Optional per-tone frequency ratios f_j/f_0.
    """

    def __init__(
        self,
        config: WiFallConfig | None = None,
        *,
        classifier: Literal["random_forest", "one_class_svm"] = "random_forest",
        frequency_weights: np.ndarray | None = None,
    ) -> None:
        if classifier not in {"random_forest", "one_class_svm"}:
            raise ValueError("Unknown classifier")
        self.config = config if config is not None else WiFallConfig()
        self.classifier = classifier
        self.frequency_weights = (
            None
            if frequency_weights is None
            else np.asarray(frequency_weights, dtype=np.float64).copy()
        )

    def _windows(self, windows: np.ndarray) -> np.ndarray:
        values = validate_amplitudes(windows, ndim=4)
        if values.shape[1] != self.config.window_samples:
            raise ValueError("Window sample count differs from configuration")
        if hasattr(self, "input_shape_") and values.shape[1:] != self.input_shape_:
            raise ValueError("Window stream/tone schema differs from fitted data")
        aggregate_streams(values, self.frequency_weights)
        return values

    def _require_fitted(self) -> None:
        if not hasattr(self, "classifier_"):
            raise NotFittedError("Fit WiFallDetector before predicting or transforming")

    def _prepare(self, windows: np.ndarray) -> np.ndarray:
        return np.stack(
            [
                weighted_moving_average(window, self.config.smoothing_samples)
                for window in self._windows(windows)
            ]
        )

    def _scores(self, prepared: np.ndarray) -> np.ndarray:
        streams = aggregate_streams(prepared, self.frequency_weights)
        scores = np.empty_like(streams)
        for index, model in enumerate(self.activity_models_):
            scores[:, :, index] = -model.score_samples(
                streams[:, :, index].reshape(-1, 1)
            ).reshape(streams.shape[:2])
        return scores

    def _features(self, prepared: np.ndarray, scores: np.ndarray) -> np.ndarray:
        if self.config.representation == "singular_values":
            return np.stack([singular_value_features(window) for window in prepared])
        active = scores > self.config.lof_threshold
        return np.stack(
            [
                statistical_features(
                    window,
                    mask,
                    sample_rate_hz=self.config.sample_rate_hz,
                    entropy_bins=self.config.entropy_bins,
                )
                for window, mask in zip(prepared, active, strict=True)
            ]
        )

    def fit(
        self, windows: np.ndarray, labels: np.ndarray, stable: np.ndarray
    ) -> "WiFallDetector":
        """Fit a stable profile and classifier using training data only.

        Args:
            windows: Raw finite amplitudes [window, time, stream, tone].
            labels: Binary training targets, with 1 denoting a fall.
            stable: Independently selected training-only resting amplitudes,
                either one contiguous [time, stream, tone] segment or separate
                [chunk, time, stream, tone] chunks. Filtering never crosses chunks.

        Returns:
            This fitted detector. Fall is the inlier class for one-class SVM.
        """
        # Failed refits must not leave an old classifier paired with new LOF.
        for name in (
            "input_shape_",
            "classifier_",
            "scaler_",
            "feature_names_",
            "activity_models_",
        ):
            if hasattr(self, name):
                delattr(self, name)
        values = self._windows(windows)
        resting = np.asarray(stable, dtype=np.float64)
        if resting.ndim not in (3, 4):
            raise ValueError("Stable profile must be a segment or separate chunks")
        resting = validate_amplitudes(resting, ndim=resting.ndim)
        if resting.shape[-2:] != values.shape[2:]:
            raise ValueError("Stable profile stream/tone shape differs from windows")
        chunks = resting[None] if resting.ndim == 3 else resting
        if chunks.shape[0] * chunks.shape[1] <= self.config.lof_neighbors:
            raise ValueError(
                "Stable profile must contain more samples than LOF neighbors"
            )
        target = np.asarray(labels)
        if target.shape != (len(values),) or not np.isin(target, [0, 1]).all():
            raise ValueError("labels must provide a binary target for every window")
        if self.classifier == "random_forest" and set(target.tolist()) != {0, 1}:
            raise ValueError(
                "Random forest requires fall and non-fall training windows"
            )
        if not np.any(target == 1):
            raise ValueError("At least one fall training window is required")
        profile = aggregate_streams(
            np.concatenate(
                [
                    weighted_moving_average(chunk, self.config.smoothing_samples)
                    for chunk in chunks
                ]
            ),
            self.frequency_weights,
        )
        self.activity_models_ = [
            LocalOutlierFactor(n_neighbors=self.config.lof_neighbors, novelty=True).fit(
                profile[:, index, None]
            )
            for index in range(profile.shape[1])
        ]
        self.input_shape_ = values.shape[1:]
        prepared = self._prepare(values)
        features = self._features(prepared, self._scores(prepared))
        selected = (
            target == 1
            if self.classifier == "one_class_svm"
            else np.ones(len(target), dtype=bool)
        )
        self.scaler_ = StandardScaler().fit(features[selected])
        scaled = self.scaler_.transform(features[selected])
        if self.classifier == "one_class_svm":
            self.classifier_ = OneClassSVM(
                kernel="rbf", nu=self.config.svm_nu, gamma=self.config.svm_gamma
            ).fit(scaled)
        else:
            self.classifier_ = RandomForestClassifier(
                n_estimators=self.config.forest_trees,
                random_state=self.config.random_seed,
                n_jobs=1,
            ).fit(scaled, target[selected].astype(np.int64))
        self.feature_names_ = (
            tuple(f"singular_value_{index + 1}" for index in range(3))
            if self.config.representation == "singular_values"
            else tuple(
                f"stream_{index}/{name}"
                for index in range(values.shape[2])
                for name in STATISTIC_NAMES
            )
        )
        return self

    def activity_scores(self, windows: np.ndarray) -> np.ndarray:
        """Return LOF anomaly scores shaped [window, time, stream].

        Args:
            windows: Raw amplitude windows with the fitted schema.

        Returns:
            Positive anomaly scores; values above lof_threshold are active.
        """
        self._require_fitted()
        return self._scores(self._prepare(windows))

    def predict_activity(self, windows: np.ndarray) -> np.ndarray:
        """Flag windows containing a simultaneous strict majority of active streams.

        Args:
            windows: Raw amplitude windows with the fitted schema.

        Returns:
            One boolean activity flag per window.
        """
        active = self.activity_scores(windows) > self.config.lof_threshold
        return (active.sum(axis=-1) > active.shape[-1] / 2).any(axis=1)

    def transform(self, windows: np.ndarray) -> np.ndarray:
        """Return unscaled features without fitting on the supplied windows.

        Args:
            windows: Raw amplitude windows with the fitted schema.

        Returns:
            One feature row per input window.
        """
        self._require_fitted()
        prepared = self._prepare(windows)
        return self._features(prepared, self._scores(prepared))

    def predict(self, windows: np.ndarray) -> np.ndarray:
        """Return binary fall labels after strict-majority LOF activity gating.

        Args:
            windows: Raw amplitude windows with the fitted schema.

        Returns:
            Integer labels: 1 for an active fall candidate, otherwise 0.
        """
        self._require_fitted()
        prepared = self._prepare(windows)
        scores = self._scores(prepared)
        features = self._features(prepared, scores)
        prediction = self.classifier_.predict(self.scaler_.transform(features))
        fall = prediction == 1
        active = scores > self.config.lof_threshold
        gate = (active.sum(axis=-1) > active.shape[-1] / 2).any(axis=1)
        return (fall & gate).astype(np.int64)

    def predict_ungated(self, windows: np.ndarray) -> np.ndarray:
        """Return classifier-only labels for comparison with the activity gate.

        Args:
            windows: Raw amplitude windows with the fitted schema.

        Returns:
            Binary labels with fall as 1, including one-class SVM inliers.
        """
        features = self.transform(windows)
        prediction = self.classifier_.predict(self.scaler_.transform(features))
        return (prediction == 1).astype(np.int64)
