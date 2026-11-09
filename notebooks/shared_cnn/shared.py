"""Shared preprocessing and CNN helpers for the four-receiver experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, average_precision_score, balanced_accuracy_score,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
import torch
from torch import nn

def read_json(path: Path) -> dict:
    """Read a UTF-8 JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    """Write portable JSON and reject non-finite numeric values."""
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    """Hash a file without loading it fully into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bin_values(
    seconds: np.ndarray, values: np.ndarray, bins: int, hz: int
) -> np.ndarray:
    """Average each tone inside fixed time bins; leave empty bins missing.

    Does not interpolate across gaps or mix physical subcarriers. Sine/cosine
    components must be supplied for circular values.
    """
    indices = np.floor(seconds * hz).astype(int)
    selected = (indices >= 0) & (indices < bins)
    indices, values = indices[selected], values[selected]
    finite = np.isfinite(values)
    totals = np.zeros((bins, values.shape[1]), dtype=np.float64)
    counts = np.zeros_like(totals)
    np.add.at(totals, indices, np.where(finite, values, 0))
    np.add.at(counts, indices, finite)
    return np.divide(
        totals, counts, out=np.full_like(totals, np.nan), where=counts > 0
    ).astype(np.float32)


def smooth_valid(values: np.ndarray, width: int) -> np.ndarray:
    """Average adjacent supported bins without filling a missing center bin."""
    if width < 1 or width % 2 != 1:
        raise ValueError("Smoothing width must be positive and odd")
    pad = width // 2
    padded = np.pad(values, ((0, 0), (pad, pad), (0, 0)), constant_values=np.nan)
    stack = np.stack(
        [padded[:, offset : offset + values.shape[1]] for offset in range(width)]
    )
    finite = np.isfinite(stack)
    count = finite.sum(axis=0)
    total = np.where(finite, stack, 0).sum(axis=0)
    result = np.divide(total, count, out=np.full_like(total, np.nan), where=count > 0)
    result[~np.isfinite(values)] = np.nan
    return result.astype(np.float32)


class SmallCNN(nn.Module):
    """Learn local time/frequency patches, then pool to one attempt logit."""

    def __init__(self, channels: int) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv2d(channels, 8, kernel_size=5, stride=2, padding=2),
            nn.ReLU(),
            nn.Conv2d(8, 16, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(0.25),
            nn.Linear(32, 1),
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        """Return one unnormalized fall logit per attempt."""
        return self.network(values).squeeze(1)


def metrics(target: np.ndarray, probability: np.ndarray) -> dict:
    """Calculate binary trial-level metrics at the fixed 0.5 threshold."""
    predicted = probability >= 0.5
    tn, fp, fn, tp = confusion_matrix(target, predicted, labels=[0, 1]).ravel()
    return {
        "n": len(target),
        "accuracy": float(accuracy_score(target, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(target, predicted)),
        "fall_precision": float(precision_score(target, predicted, zero_division=0)),
        "fall_recall": float(recall_score(target, predicted, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if tn + fp else None,
        "fall_f1": float(f1_score(target, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(target, probability))
        if len(np.unique(target)) == 2
        else None,
        "average_precision": float(average_precision_score(target, probability))
        if np.any(target == 1)
        else None,
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


def predict(model: nn.Module, values: np.ndarray, batch_size: int) -> np.ndarray:
    """Predict in CPU batches with dropout disabled."""
    model.eval()
    with torch.no_grad():
        return np.concatenate(
            [
                torch.sigmoid(
                    model(torch.from_numpy(values[start : start + batch_size]))
                ).numpy()
                for start in range(0, len(values), batch_size)
            ]
        )


def summarize_features(values: np.ndarray) -> np.ndarray:
    """Create a simple baseline from channel means and variability."""
    # This reduction is confined to the baseline; the CNN retains every tone.
    return np.concatenate([values.mean(axis=(2, 3)), values.std(axis=(2, 3))], axis=1)


def cluster_intervals(
    table: pd.DataFrame,
    probabilities: np.ndarray,
    seed: int = 812,
    repetitions: int = 2000,
) -> dict:
    """Bootstrap held-out scenarios, keeping their repetitions together.

    These exploratory intervals condition on one split and one session; they
    do not quantify uncertainty across participants or model selection.
    """
    groups = table.scenario_id.unique()
    rng = np.random.default_rng(seed)
    scores = {
        "balanced_accuracy": [],
        "fall_recall": [],
        "specificity": [],
        "roc_auc": [],
    }
    indices = {group: np.flatnonzero(table.scenario_id.eq(group)) for group in groups}
    targets = table.target.to_numpy()
    for _ in range(repetitions):
        sample = np.concatenate(
            [indices[group] for group in rng.choice(groups, len(groups), replace=True)]
        )
        if len(np.unique(targets[sample])) < 2:
            continue
        result = metrics(targets[sample], probabilities[sample])
        for name in scores:
            scores[name].append(result[name])
    return {
        name: [float(value) for value in np.quantile(values, [0.025, 0.975])]
        for name, values in scores.items()
    }
