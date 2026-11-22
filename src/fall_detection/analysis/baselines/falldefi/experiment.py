"""Grouped evaluation and publication of the FallDeFi adaptation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from ..._cache_keys import file_hash
from ..._io import atomic_json, temporary_sibling
from .._grouped_holdout import assigned_holdout, binary_metrics, grouped_holdout
from .dataset import TraceDataset
from .events import FEATURE_NAMES
from .model import FallDeFiConfig, FallDeFiDetector


@dataclass
class ExperimentResult:
    """Fitted detector, evaluation provenance, and held-out trace predictions."""

    detector: FallDeFiDetector
    report: dict[str, Any]
    predictions: list[dict[str, Any]]


def run_experiment(
    dataset: TraceDataset,
    config: FallDeFiConfig,
    *,
    split_by: str = "attempt",
    test_fraction: float = 0.25,
    assignment: dict[str, str] | None = None,
) -> ExperimentResult:
    """Fit on training attempts and evaluate once on held-out traces.

    Args:
        dataset: Traces and resting segments derived from raw magnitudes.
        config: Signal, event and classifier settings.
        split_by: Identity level kept disjoint across the holdout.
        test_fraction: Held-out group fraction.
        assignment: Optional attempt identity to ``train``, ``validation`` or
            ``test`` from another experiment, replacing the seeded holdout;
            ``split_by`` and ``test_fraction`` are then unused. Validation
            attempts train, and unassigned attempts are left out.

    Returns:
        Detector, report, and predictions. No files are written by this function.

    Raises:
        ValueError: Incompatible data, no training resting segments, or too few
            training events.
    """
    if dataset.provenance.get("parameters", {}).get("sample_rate_hz") != (
        config.sample_rate_hz
    ):
        raise ValueError("Dataset sampling rate differs from config")
    unassigned: list[str] = []
    if assignment is None:
        train, test = grouped_holdout(
            dataset.targets,
            dataset.groups,
            dataset.metadata,
            split_by=split_by,
            test_fraction=test_fraction,
            seed=config.random_seed,
        )
    else:
        train, test, unassigned = assigned_holdout(
            dataset.targets, dataset.groups, assignment
        )
    train_groups = set(dataset.groups[train].tolist())
    resting = [
        index
        for index, group in enumerate(dataset.resting_groups)
        if group in train_groups
    ]
    if not resting:
        raise ValueError(
            "No usable countdown/resting segments from training attempts; "
            "inspect dataset coverage and cue intervals"
        )
    detector = FallDeFiDetector(config).fit(
        [dataset.traces[index] for index in train],
        dataset.targets[train],
        [dataset.resting[index] for index in resting],
    )
    rows, predictions = [], []
    for index in test:
        analysis = detector.analyze(dataset.traces[index])
        labels = detector.classify(analysis)
        times = analysis.spectrogram.frame_seconds
        half = config.window_samples / config.sample_rate_hz / 2
        prediction = int(labels.any())
        predictions.append(prediction)
        rows.append(
            {
                **dataset.metadata[int(index)],
                "group": str(dataset.groups[index]),
                "target": int(dataset.targets[index]),
                "prediction": prediction,
                "events": [
                    {
                        "start_seconds": float(times[start] - half),
                        "stop_seconds": float(times[stop - 1] + half),
                        "main": position == analysis.main_event,
                        "prediction": int(label),
                        "features": dict(
                            zip(FEATURE_NAMES, features.tolist(), strict=True)
                        ),
                    }
                    for position, ((start, stop), label, features) in enumerate(
                        zip(analysis.events, labels, analysis.features, strict=True)
                    )
                ],
            }
        )
    target = dataset.targets[test]
    predicted = np.asarray(predictions)
    detected = np.array([bool(row["events"]) for row in rows])
    non_fall = [row for row in rows if row["target"] == 0]
    hours = sum(row["duration_seconds"] for row in non_fall) / 3600
    alarms = sum(event["prediction"] for row in non_fall for event in row["events"])
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
        "schema": "falldefi_experiment",
        "version": 1,
        "implementation": "FallDeFi adapted to the ESP32-C5 receivers",
        "paper_doi": "10.1145/3161183",
        "parameters": asdict(config),
        "feature_names": list(FEATURE_NAMES),
        "noise_threshold": detector.noise_threshold_,
        "threshold_k": detector.threshold_k_,
        "threshold_k_source": "fixed"
        if config.threshold_k is not None
        else ("largest grid value reaching the training detection target"),
        "training_detection_rate": detector.training_detection_rate_,
        "resting_thresholds": {
            "count": len(detector.resting_thresholds_),
            "minimum": float(detector.resting_thresholds_.min()),
            "median": float(np.median(detector.resting_thresholds_)),
            "maximum": float(detector.resting_thresholds_.max()),
        },
        "receiver_floors": [floor is not None for floor in detector.floors_],
        "training_events": detector.training_events_,
        "svm": {
            "C": float(detector.search_.best_params_["C"]),
            "gamma": float(detector.search_.best_params_["gamma"]),
            "cross_validation_accuracy": float(detector.search_.best_score_),
        },
        "dataset": dataset.provenance,
        "split": {
            "by": "assignment" if assignment is not None else split_by,
            "test_fraction": None if assignment is not None else test_fraction,
            "seed": None if assignment is not None else config.random_seed,
            "unassigned_attempts": unassigned,
            "train_traces": len(train),
            "test_traces": len(test),
            "train_attempts": sorted(train_groups),
            "test_attempts": sorted(set(dataset.groups[test].tolist())),
            "resting_segments": len(resting),
            "assignments": assignments,
        },
        "held_out": binary_metrics(target, predicted),
        "held_out_event_detection": {
            "fall_traces_with_events": int(detected[target == 1].sum()),
            "fall_traces": int((target == 1).sum()),
            "non_fall_traces_with_events": int(detected[target == 0].sum()),
            "non_fall_traces": int((target == 0).sum()),
        },
        "held_out_false_alarms": {
            "fall_classified_events_in_non_fall_traces": int(alarms),
            "non_fall_trace_hours": hours,
            "per_hour": alarms / hours if hours else None,
        },
        "versions": {
            name: version(name)
            for name in ("numpy", "scipy", "scikit-learn", "PyWavelets", "joblib")
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
            "Recordings are 120 Hz; the paper used 1000 Hz and saw decline below 400.",
            "Scheduled 0.1 s receiver gaps are interpolated inside every window.",
            "Hardware adaptations were chosen on the 9 November 13:15 session.",
            "Countdown cues are assumed quiet; they are not verified resting labels.",
            "Action cues are not measured movement or impact boundaries.",
            "False alarms per hour of dense cue traces are not continuous monitoring.",
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
                "schema": "falldefi_model",
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
