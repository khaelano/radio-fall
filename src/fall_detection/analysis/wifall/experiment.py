"""Grouped evaluation and publication of the WiFall adaptation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from .._cache_keys import file_hash
from .._grouped_holdout import binary_metrics, grouped_holdout
from .._io import atomic_json, temporary_sibling
from .dataset import WindowSet
from .model import WiFallConfig, WiFallDetector


@dataclass
class ExperimentResult:
    """Fitted detector, evaluation provenance, and held-out window predictions."""

    detector: WiFallDetector
    report: dict[str, Any]
    predictions: list[dict[str, Any]]


def run_experiment(
    dataset: WindowSet,
    config: WiFallConfig,
    *,
    split_by: str = "attempt",
    test_fraction: float = 0.25,
    max_stable_windows: int = 128,
) -> ExperimentResult:
    """Fit on training attempts and evaluate once on held-out windows.

    Args:
        dataset: Represented windows and resting streams.
        config: Activity profile and classifier settings.
        split_by: Identity level kept disjoint across the holdout.
        test_fraction: Held-out group fraction.
        max_stable_windows: Seeded cap on training-only resting chunks.

    Returns:
        Detector, report, and predictions. No files are written by this function.

    Raises:
        ValueError: Incompatible data or no training resting chunks.
    """
    if not isinstance(max_stable_windows, int) or max_stable_windows < 1:
        raise ValueError("max_stable_windows must be a positive integer")
    if dataset.provenance.get("parameters", {}).get("sample_rate_hz") != (
        config.sample_rate_hz
    ):
        raise ValueError("Dataset sampling rate differs from config")
    train, test = grouped_holdout(
        dataset.targets,
        dataset.groups,
        dataset.metadata,
        split_by=split_by,
        test_fraction=test_fraction,
        seed=config.random_seed,
    )
    train_groups = set(dataset.groups[train].tolist())
    stable = np.flatnonzero(np.isin(dataset.resting_groups, list(train_groups)))
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
    detector = WiFallDetector(config).fit(
        dataset.windows.take(train),
        dataset.targets[train],
        dataset.resting_streams[stable],
    )
    prediction, ungated, activity = detector.predict_all(dataset.windows.take(test))
    target = dataset.targets[test]
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
    attempts = sorted(set(dataset.groups[test].tolist()))
    attempt_target = np.array(
        [int(target[dataset.groups[test] == group][0]) for group in attempts]
    )
    attempt_prediction = np.array(
        [int(prediction[dataset.groups[test] == group].any()) for group in attempts]
    )
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
        "version": 2,
        "implementation": "WiFall adapted to the ESP32-C5 receivers",
        "paper_doi": "10.1109/TMC.2016.2557792",
        "parameters": asdict(config),
        "feature_names": list(detector.feature_names_),
        "profiled_receivers": [profile is not None for profile in detector.profiles_],
        "dataset": dataset.provenance,
        "split": {
            "by": split_by,
            "test_fraction": test_fraction,
            "seed": config.random_seed,
            "train_windows": len(train),
            "test_windows": len(test),
            "train_attempts": sorted(train_groups),
            "test_attempts": attempts,
            "stable_attempts": sorted(set(dataset.resting_groups[stable].tolist())),
            "stable_windows": len(stable),
            "max_stable_windows": max_stable_windows,
            "assignments": assignments,
        },
        "held_out": binary_metrics(target, prediction),
        "held_out_classifier_only": binary_metrics(target, ungated),
        "held_out_attempts": binary_metrics(attempt_target, attempt_prediction),
        "held_out_activity_fraction": {
            "fall": float(activity[target == 1].mean()),
            "non_fall": float(activity[target == 0].mean()),
        },
        "versions": {
            name: version(name) for name in ("numpy", "scikit-learn", "joblib")
        },
        "code_sha256": {
            path.name: file_hash(path)
            for path in sorted(Path(__file__).parent.glob("*.py"))
        }
        | {
            "_grouped_holdout.py": file_hash(
                Path(__file__).parents[1] / "_grouped_holdout.py"
            )
        },
        "limitations": [
            "Scheduled 0.1 s receiver gaps are interpolated inside every window.",
            "Hardware adaptations were chosen on the 9 November 13:15 session.",
            "Countdown cues are assumed quiet; they are not verified resting labels.",
            "Action cues are not measured movement or impact boundaries.",
            "Overlapping windows of one attempt are correlated.",
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
                "version": 2,
                "detector": result.detector,
                "coordinates": result.report["dataset"]["coordinates"],
                "parameters": result.report["parameters"],
                "representation": {
                    name: result.report["dataset"]["parameters"][name]
                    for name in ("sample_rate_hz", "smoothing_samples", "entropy_bins")
                },
            },
            temporary,
        )
    atomic_json(result.predictions, destination / "predictions.json")
    atomic_json(
        {**result.report, "model_sha256": file_hash(model_path)},
        destination / "report.json",
    )
