"""WiFall detector: per-receiver activity profiles, pooled features, classifier.

Each receiver gets a Local Outlier Factor (LOF) profile of its resting stream
values from training countdowns (§4.3.1). A sample is active on a receiver
when its LOF score exceeds the threshold, and a window passes the activity
gate when, at some sample, a strict majority of the receivers present in that
window are active. The motion period of each receiver is its active time.

Per-receiver features are pooled over the receivers present in the window by
their mean and maximum, so the feature vector does not depend on which
receiver was dropped. The random forest weights classes by inverse frequency;
the one-class SVM is fitted on fall windows only, falls being its inliers as in
the paper.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import NotFittedError
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from .representation import SINGULAR_VALUE_NAMES, STATISTIC_NAMES, Representations

RECEIVER_FEATURES = (
    STATISTIC_NAMES[:2] + ("motion_period_seconds",) + STATISTIC_NAMES[2:]
)
"""The paper's seven statistics in its order, motion period third."""

FEATURE_SETS = {
    "statistics": RECEIVER_FEATURES,
    "singular_values": SINGULAR_VALUE_NAMES,
    "all": RECEIVER_FEATURES + SINGULAR_VALUE_NAMES,
}


@dataclass(frozen=True)
class WiFallConfig:
    """Activity profile and classifier settings.

    The paper omits these values; defaults are explicit adaptation choices.
    """

    sample_rate_hz: float = 120
    lof_neighbors: int = 20
    lof_threshold: float = 1.5
    features: str = "all"
    classifier: str = "random_forest"
    forest_trees: int = 200
    svm_nu: float = 0.1
    svm_gamma: str | float = "scale"
    class_weight: str | None = "balanced"
    random_seed: int = 42

    def __post_init__(self) -> None:
        for name in ("sample_rate_hz", "lof_threshold"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("lof_neighbors", "forest_trees"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 2:
                raise ValueError(f"{name} must be an integer of at least two")
        gamma_ok = (
            self.svm_gamma in {"scale", "auto"}
            if isinstance(self.svm_gamma, str)
            else np.isfinite(self.svm_gamma) and self.svm_gamma > 0
        )
        if (
            self.features not in FEATURE_SETS
            or self.classifier not in {"random_forest", "one_class_svm"}
            or not np.isfinite(self.svm_nu)
            or not 0 < self.svm_nu <= 1
            or not gamma_ok
            or self.class_weight not in {None, "balanced"}
        ):
            raise ValueError("Invalid feature set, classifier or SVM settings")


class WiFallDetector:
    """Activity gating and fall classification fitted on training data only.

    Args:
        config: Activity profile and classifier settings.
    """

    def __init__(self, config: WiFallConfig | None = None) -> None:
        self.config = config if config is not None else WiFallConfig()

    def _require_fitted(self) -> None:
        if not hasattr(self, "classifier_"):
            raise NotFittedError("Fit WiFallDetector before predicting")

    def _check(self, windows: Representations) -> None:
        if hasattr(self, "receivers_") and windows.streams.shape[2] != self.receivers_:
            raise ValueError("Window receiver schema differs from fitted data")

    def activity(self, windows: Representations) -> tuple[np.ndarray, np.ndarray]:
        """Return active samples and the receivers counted for each window.

        Args:
            windows: Representations with the fitted receiver schema.

        Returns:
            Active flags ``[window, time, receiver]`` and counted receivers
            ``[window, receiver]``: present in the window and profiled.
        """
        if not hasattr(self, "profiles_"):
            raise NotFittedError("Fit WiFallDetector before scoring activity")
        self._check(windows)
        counted = windows.present & np.array([p is not None for p in self.profiles_])
        active = np.zeros(windows.streams.shape, dtype=bool)
        for receiver, profile in enumerate(self.profiles_):
            rows = counted[:, receiver]
            if profile is None or not rows.any():
                continue
            values = windows.streams[rows, :, receiver].astype(np.float64)
            scores = -profile.score_samples(values.reshape(-1, 1))
            active[rows, :, receiver] = (
                scores.reshape(values.shape) > self.config.lof_threshold
            )
        return active, counted

    def predict_activity(self, windows: Representations) -> np.ndarray:
        """Flag windows where a strict majority of counted receivers is active.

        Args:
            windows: Representations with the fitted receiver schema.

        Returns:
            One boolean flag per window.
        """
        return self._gate(*self.activity(windows))

    @staticmethod
    def _gate(active: np.ndarray, counted: np.ndarray) -> np.ndarray:
        majority = active.sum(axis=2) > counted.sum(axis=1, keepdims=True) / 2
        return majority.any(axis=1) & counted.any(axis=1)

    def transform(self, windows: Representations) -> np.ndarray:
        """Return pooled features ``[window, feature]`` without fitting.

        Args:
            windows: Representations with the fitted receiver schema.

        Returns:
            Means then maxima over present receivers, ordered as
            ``feature_names_``.
        """
        return self._pooled(windows, *self.activity(windows))

    def _pooled(
        self, windows: Representations, active: np.ndarray, counted: np.ndarray
    ) -> np.ndarray:
        period = active.sum(axis=1) / self.config.sample_rate_hz
        period = np.where(counted, period, np.nan)
        stats = windows.statistics
        per_receiver = np.concatenate(
            [
                stats[..., :2],
                period[..., None],
                stats[..., 2:],
                windows.singular_values,
            ],
            axis=2,
        )
        names = RECEIVER_FEATURES + SINGULAR_VALUE_NAMES
        chosen = [names.index(name) for name in FEATURE_SETS[self.config.features]]
        values = per_receiver[..., chosen]
        with np.errstate(all="ignore"):
            pooled = np.concatenate(
                [np.nanmean(values, axis=1), np.nanmax(values, axis=1)], axis=1
            )
        # A window whose receivers all lack a profile has no motion period.
        return np.nan_to_num(pooled, nan=0.0)

    def fit(
        self, windows: Representations, labels: np.ndarray, resting: np.ndarray
    ) -> WiFallDetector:
        """Fit per-receiver profiles and the classifier on training data only.

        Args:
            windows: Training representations.
            labels: Binary window targets, with 1 denoting a fall.
            resting: Training-only resting streams ``[chunk, time, receiver]``,
                NaN for dropped receivers.

        Returns:
            This fitted detector.

        Raises:
            ValueError: If labels, schemas or resting data are unusable.
        """
        for name in (
            "receivers_",
            "profiles_",
            "scaler_",
            "classifier_",
            "feature_names_",
        ):
            if hasattr(self, name):
                delattr(self, name)
        target = np.asarray(labels)
        streams = np.asarray(resting, dtype=np.float64)
        if target.shape != (len(windows),) or not np.isin(target, [0, 1]).all():
            raise ValueError("labels must provide a binary target for every window")
        if not np.any(target == 1):
            raise ValueError("At least one fall training window is required")
        if self.config.classifier == "random_forest" and set(target.tolist()) != {
            0,
            1,
        }:
            raise ValueError("Random forest requires fall and non-fall windows")
        if streams.ndim != 3 or streams.shape[2] != windows.streams.shape[2]:
            raise ValueError("Resting streams must match the window receiver schema")
        profiles = []
        for receiver in range(streams.shape[2]):
            values = streams[:, :, receiver]
            values = values[np.isfinite(values)]
            profiles.append(
                LocalOutlierFactor(
                    n_neighbors=self.config.lof_neighbors, novelty=True
                ).fit(values.reshape(-1, 1))
                if len(values) > self.config.lof_neighbors
                else None
            )
        if all(profile is None for profile in profiles):
            raise ValueError("Resting streams have too few samples for any profile")
        self.receivers_ = streams.shape[2]
        self.profiles_ = profiles
        features = self.transform(windows)
        selected = (
            target == 1
            if self.config.classifier == "one_class_svm"
            else np.ones(len(target), dtype=bool)
        )
        self.scaler_ = StandardScaler().fit(features[selected])
        scaled = self.scaler_.transform(features[selected])
        if self.config.classifier == "one_class_svm":
            self.classifier_ = OneClassSVM(
                kernel="rbf", nu=self.config.svm_nu, gamma=self.config.svm_gamma
            ).fit(scaled)
        else:
            self.classifier_ = RandomForestClassifier(
                n_estimators=self.config.forest_trees,
                class_weight=self.config.class_weight,
                random_state=self.config.random_seed,
                n_jobs=1,
            ).fit(scaled, target)
        chosen = FEATURE_SETS[self.config.features]
        self.feature_names_ = tuple(
            f"{name}_{pool}" for pool in ("mean", "max") for name in chosen
        )
        return self

    def _classify(self, features: np.ndarray) -> np.ndarray:
        self._require_fitted()
        scaled = self.scaler_.transform(features)
        return (self.classifier_.predict(scaled) == 1).astype(np.int64)

    def predict_ungated(self, windows: Representations) -> np.ndarray:
        """Return classifier-only labels, with fall as 1.

        Args:
            windows: Representations with the fitted receiver schema.

        Returns:
            Binary labels; one-class SVM inliers are falls.
        """
        return self._classify(self.transform(windows))

    def predict_all(
        self, windows: Representations
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return gated labels, classifier-only labels and activity flags.

        Args:
            windows: Representations with the fitted receiver schema.

        Returns:
            Three arrays with one entry per window, scoring activity once.
        """
        self._require_fitted()
        active, counted = self.activity(windows)
        ungated = self._classify(self._pooled(windows, active, counted))
        gate = self._gate(active, counted)
        return (ungated.astype(bool) & gate).astype(np.int64), ungated, gate

    def predict(self, windows: Representations) -> np.ndarray:
        """Return 1 for windows classified as falls that pass the activity gate.

        Args:
            windows: Representations with the fitted receiver schema.

        Returns:
            One binary label per window.
        """
        return self.predict_all(windows)[0]
