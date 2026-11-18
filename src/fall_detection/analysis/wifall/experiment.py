"""Grouped evaluation and publication of the WiFall adaptation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit

from .._cache_keys import file_hash
from .._io import atomic_json, temporary_sibling
from .dataset import WindowDataset
from .model import WiFallConfig, WiFallDetector


@dataclass
class ExperimentResult:
    """Fitted detector, evaluation provenance, and held-out window predictions."""

    detector: WiFallDetector
    report: dict[str, Any]
    predictions: list[dict[str, Any]]


def grouped_holdout(
    dataset: WindowDataset,
    *,
    split_by: str,
    test_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Find a deterministic group holdout containing both classes on each side.

    Args:
        dataset: Amplitude windows with attempt/session/participant identities.
        split_by: ``attempt``, ``session``, or ``participant``.
        test_fraction: Fraction of groups reserved for testing.
        seed: Seed for at most 100 candidate group assignments. Selection only
            checks class coverage; it never examines model performance.

    Returns:
        Training and test window indices with disjoint requested groups.

    Raises:
        ValueError: Missing identities or no valid two-class partition.
    """
    if split_by not in {"attempt", "session", "participant"}:
        raise ValueError("split_by must be attempt, session, or participant")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must lie strictly between zero and one")
    if len(dataset.metadata) != len(dataset.targets):
        raise ValueError("Every window needs provenance metadata")
    if split_by == "attempt":
        groups = np.asarray(dataset.groups)
    else:
        field = f"{split_by}_id"
        values = [row.get(field) for row in dataset.metadata]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"Every window needs a nonempty {field}")
        groups = np.asarray(values)
    if len(np.unique(groups)) < 2:
        raise ValueError(f"At least two {split_by} groups are required")
    splitter = GroupShuffleSplit(
        n_splits=100, test_size=test_fraction, random_state=seed
    )
    for train, test in splitter.split(dataset.windows, dataset.targets, groups):
        if all(
            set(dataset.targets[index].tolist()) == {0, 1} for index in (train, test)
        ):
            if set(dataset.groups[train]) & set(dataset.groups[test]):
                raise ValueError("Attempt identities cross the requested split")
            return train, test
    raise ValueError(
        f"No {split_by} holdout with both classes in train and test; "
        "provide more groups or explicitly choose a different split"
    )


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    tn, fp, fn, tp = confusion_matrix(target, prediction, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        target, prediction, average="binary", zero_division=0
    )
    return {
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "confusion_order": ["non_fall", "fall"],
        "accuracy": float(np.mean(target == prediction)),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": float(fp / (fp + tn)),
        "specificity": float(tn / (tn + fp)),
    }


def run_experiment(
    dataset: WindowDataset,
    config: WiFallConfig,
    *,
    classifier: str = "random_forest",
    split_by: str = "attempt",
    test_fraction: float = 0.25,
    max_stable_windows: int = 128,
) -> ExperimentResult:
    """Fit on training attempts and evaluate once on held-out windows.

    Args:
        dataset: Windows derived from raw magnitudes, including resting chunks.
        config: Signal, feature and model parameters.
        classifier: ``random_forest`` or ``one_class_svm``.
        split_by: Identity level kept disjoint across the holdout.
        test_fraction: Held-out group fraction.
        max_stable_windows: Seeded cap on training-only resting chunks for LOF.

    Returns:
        Detector, report, and predictions. No files are written by this function.

    Raises:
        ValueError: Insufficient training resting chunks or incompatible data.
    """
    if not isinstance(max_stable_windows, int) or max_stable_windows < 1:
        raise ValueError("max_stable_windows must be a positive integer")
    parameters = dataset.provenance.get("parameters", {})
    if (
        parameters.get("sample_rate_hz") != config.sample_rate_hz
        or parameters.get("window_seconds") != config.window_seconds
    ):
        raise ValueError("Dataset sampling rate/window duration differs from config")
    train, test = grouped_holdout(
        dataset,
        split_by=split_by,
        test_fraction=test_fraction,
        seed=config.random_seed,
    )
    train_groups = set(dataset.groups[train].tolist())
    stable = np.flatnonzero(np.isin(dataset.stable_groups, list(train_groups)))
    if not len(stable):
        raise ValueError(
            "No usable countdown/resting windows from training attempts; "
            "inspect dataset coverage and cue intervals"
        )
    if len(stable) > max_stable_windows:
        stable = np.sort(
            np.random.default_rng(config.random_seed).choice(
                stable, max_stable_windows, replace=False
            )
        )
    coordinates = dataset.provenance["coordinates"]
    tones = np.asarray(coordinates["subcarriers"], dtype=float)
    weights = (
        1
        + tones
        * dataset.provenance["subcarrier_spacing_hz"]
        / dataset.provenance["center_frequency_hz"]
    )
    detector = WiFallDetector(
        config, classifier=classifier, frequency_weights=weights
    ).fit(
        dataset.windows[train], dataset.targets[train], dataset.stable_windows[stable]
    )
    windows = dataset.windows[test]
    prediction = detector.predict(windows)
    ungated = detector.predict_ungated(windows)
    activity = detector.predict_activity(windows)
    rows = [
        {
            **dataset.metadata[int(index)],
            "group": str(dataset.groups[index]),
            "target": int(dataset.targets[index]),
            "prediction": int(prediction[position]),
            "classifier_prediction": int(ungated[position]),
            "activity_detected": bool(activity[position]),
        }
        for position, index in enumerate(test)
    ]
    assignments = [
        {
            **dataset.metadata[int(index)],
            "group": str(dataset.groups[index]),
            "split": name,
        }
        for name, indices in (("train", train), ("test", test))
        for index in indices
    ]
    report = {
        "schema": "wifall_experiment",
        "version": 1,
        "implementation": "WiFall with explicit ESP32-C5 adaptations",
        "paper_doi": "10.1109/TMC.2016.2557792",
        "parameters": asdict(config),
        "classifier": classifier,
        "feature_names": list(detector.feature_names_),
        "frequency_weights": weights.tolist(),
        "dataset": dataset.provenance,
        "split": {
            "by": split_by,
            "test_fraction": test_fraction,
            "seed": config.random_seed,
            "train_windows": len(train),
            "test_windows": len(test),
            "train_attempts": sorted(train_groups),
            "test_attempts": sorted(set(dataset.groups[test].tolist())),
            "stable_attempts": sorted(set(dataset.stable_groups[stable].tolist())),
            "stable_windows": len(stable),
            "max_stable_windows": max_stable_windows,
            "assignments": assignments,
        },
        "held_out": _metrics(dataset.targets[test], prediction),
        "held_out_classifier_only": _metrics(dataset.targets[test], ungated),
        "held_out_activity_fraction": float(np.mean(activity)),
        "versions": {
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "code_sha256": {
            path.name: file_hash(path)
            for path in sorted(Path(__file__).parent.glob("*.py"))
        },
        "limitations": [
            "Paper feature formulas and hyperparameters are partly unspecified.",
            "Countdown cues are assumed quiet; they are not verified resting labels.",
            "Action cues are not measured movement or impact boundaries.",
            "Window metrics do not establish event accuracy or false alarms per hour.",
            "Attempt holdout does not establish participant/session generalization.",
        ],
    }
    return ExperimentResult(detector, report, rows)


def save_experiment(result: ExperimentResult, destination: Path) -> None:
    """Publish a new result directory, leaving the completed report until last.

    Args:
        result: Completed experiment returned by :func:`run_experiment`.
        destination: New directory outside raw data; an existing path is refused.
    """
    destination.mkdir(parents=True, exist_ok=False)
    model_path = destination / "model.joblib"
    with temporary_sibling(model_path) as temporary:
        joblib.dump(
            {
                "schema": "wifall_model",
                "version": 1,
                "detector": result.detector,
                "coordinates": result.report["dataset"]["coordinates"],
                "parameters": result.report["parameters"],
            },
            temporary,
        )
    atomic_json(result.predictions, destination / "predictions.json")
    atomic_json(
        {**result.report, "model_sha256": file_hash(model_path)},
        destination / "report.json",
    )
