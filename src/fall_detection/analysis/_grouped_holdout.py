"""Grouped holdout splits and binary fall metrics for the classical baselines."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit


def grouped_holdout(
    targets: np.ndarray,
    groups: np.ndarray,
    metadata: list[dict[str, Any]],
    *,
    split_by: str,
    test_fraction: float,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Find a deterministic group holdout containing both classes on each side.

    Args:
        targets: Binary label per example, with fall equal to one.
        groups: Attempt identity per example; examples from one attempt never
            cross the split.
        metadata: Per-example provenance holding ``session_id`` and
            ``participant_id`` for the stronger split levels.
        split_by: ``attempt``, ``session``, or ``participant``.
        test_fraction: Fraction of groups reserved for testing.
        seed: Seed for at most 100 candidate group assignments. Selection only
            checks class coverage; it never examines model performance.

    Returns:
        Training and test example indices with disjoint requested groups.

    Raises:
        ValueError: Missing identities or no valid two-class partition.
    """
    if split_by not in {"attempt", "session", "participant"}:
        raise ValueError("split_by must be attempt, session, or participant")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must lie strictly between zero and one")
    targets = np.asarray(targets)
    attempts = np.asarray(groups)
    if len(metadata) != len(targets) or len(attempts) != len(targets):
        raise ValueError("Every example needs a target, group and metadata")
    if split_by == "attempt":
        split_groups = attempts
    else:
        field = f"{split_by}_id"
        values = [row.get(field) for row in metadata]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"Every example needs a nonempty {field}")
        split_groups = np.asarray(values)
    if len(np.unique(split_groups)) < 2:
        raise ValueError(f"At least two {split_by} groups are required")
    splitter = GroupShuffleSplit(
        n_splits=100, test_size=test_fraction, random_state=seed
    )
    for train, test in splitter.split(np.zeros(len(targets)), targets, split_groups):
        if all(set(targets[index].tolist()) == {0, 1} for index in (train, test)):
            if set(attempts[train]) & set(attempts[test]):
                raise ValueError("Attempt identities cross the requested split")
            return train, test
    raise ValueError(
        f"No {split_by} holdout with both classes in train and test; "
        "provide more groups or explicitly choose a different split"
    )


def binary_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    """Return the confusion matrix and fall-class metrics.

    Args:
        target: Binary reference labels containing both classes.
        prediction: Binary predicted labels in the same order.

    Returns:
        Confusion matrix in ``[non_fall, fall]`` order, accuracy, balanced
        accuracy, fall precision, recall and F1, false-positive rate and
        specificity.
    """
    tn, fp, fn, tp = confusion_matrix(target, prediction, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        target, prediction, average="binary", zero_division=0
    )
    return {
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "confusion_order": ["non_fall", "fall"],
        "accuracy": float(np.mean(np.asarray(target) == np.asarray(prediction))),
        "balanced_accuracy": float((tp / (tp + fn) + tn / (tn + fp)) / 2),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_positive_rate": float(fp / (fp + tn)),
        "specificity": float(tn / (tn + fp)),
    }
