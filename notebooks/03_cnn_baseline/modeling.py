"""Small CNN, validation-only selection, and frozen held-out evaluation."""

from __future__ import annotations

from copy import deepcopy
import importlib.metadata
from pathlib import Path
import random
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from data_pipeline import normalize_inputs, read_json, sha256, write_json


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


def verify_data(output: Path) -> dict:
    """Reject modified arrays/split files before loading a trained experiment."""
    manifest = read_json(output / "manifest.json")
    for name, key in [
        ("dataset.npz", "dataset_sha256"),
        ("trials.csv", "trials_sha256"),
    ]:
        if sha256(output / name) != manifest[key]:
            raise ValueError(f"Dataset integrity mismatch: {name}")
    return manifest


def train(config: dict, output: Path) -> None:
    """Train all predefined candidates using only train/validation data."""
    manifest = verify_data(output)
    if manifest["config"] != config:
        raise ValueError("Config changed; prepare the dataset again")
    torch.set_num_threads(config["threads"])
    torch.use_deterministic_algorithms(True)
    table = pd.read_csv(output / "trials.csv")
    train_idx = np.flatnonzero(table.split.eq("train"))
    val_idx = np.flatnonzero(table.split.eq("validation"))
    y = table.target.to_numpy(dtype=np.float32)
    histories, candidates = [], []
    validation = table.iloc[val_idx].copy()
    models = output / "models"
    models.mkdir(exist_ok=True)
    started = time.monotonic()
    with np.load(output / "dataset.npz") as dataset:
        for name in config["representations"]:
            values, scaler = normalize_inputs(dataset[name], train_idx)
            np.savez(models / f"{name}_normalization.npz", **scaler)
            probability_seeds = []
            for seed in config["training_seeds"]:
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)
                model = SmallCNN(values.shape[1])
                optimizer = torch.optim.AdamW(
                    model.parameters(),
                    lr=config["learning_rate"],
                    weight_decay=config["weight_decay"],
                )
                positive_weight = float(
                    (y[train_idx] == 0).sum() / (y[train_idx] == 1).sum()
                )
                loss_function = nn.BCEWithLogitsLoss(
                    pos_weight=torch.tensor(positive_weight)
                )
                generator = torch.Generator().manual_seed(seed)
                loader = DataLoader(
                    TensorDataset(
                        torch.from_numpy(values[train_idx]),
                        torch.from_numpy(y[train_idx]),
                    ),
                    batch_size=config["batch_size"],
                    shuffle=True,
                    generator=generator,
                )
                best_loss, best_epoch, best_state, stale = float("inf"), 0, None, 0
                for epoch in range(1, config["max_epochs"] + 1):
                    model.train()
                    losses = []
                    for batch, targets in loader:
                        optimizer.zero_grad()
                        loss = loss_function(model(batch), targets)
                        loss.backward()
                        optimizer.step()
                        losses.append((float(loss.detach()), len(batch)))
                    model.eval()
                    with torch.no_grad():
                        val_logits = model(torch.from_numpy(values[val_idx]))
                        val_loss = float(
                            loss_function(val_logits, torch.from_numpy(y[val_idx]))
                        )
                        val_probability = torch.sigmoid(val_logits).numpy()
                    history = {
                        "representation": name,
                        "seed": seed,
                        "epoch": epoch,
                        "train_loss": sum(loss * size for loss, size in losses)
                        / len(train_idx),
                        "validation_loss": val_loss,
                        "validation_balanced_accuracy": metrics(
                            y[val_idx], val_probability
                        )["balanced_accuracy"],
                    }
                    histories.append(history)
                    if not np.isfinite(val_loss):
                        raise ValueError("Non-finite training loss")
                    if val_loss < best_loss - 1e-5:
                        best_loss, best_epoch, best_state, stale = (
                            val_loss,
                            epoch,
                            deepcopy(model.state_dict()),
                            0,
                        )
                    else:
                        stale += 1
                    if stale >= config["patience"]:
                        break
                model.load_state_dict(best_state)
                torch.save(
                    {
                        "state_dict": best_state,
                        "channels": values.shape[1],
                        "seed": seed,
                        "best_epoch": best_epoch,
                        "representation": name,
                    },
                    models / f"{name}_seed{seed}.pt",
                )
                probabilities = predict(model, values[val_idx], config["batch_size"])
                probability_seeds.append(probabilities)
                print(
                    f"{name}, seed {seed}: best epoch {best_epoch}, validation BA {metrics(y[val_idx], probabilities)['balanced_accuracy']:.3f}",
                    flush=True,
                )
                pd.DataFrame(histories).to_csv(
                    output / "training_history.csv", index=False
                )
            ensemble = np.mean(probability_seeds, axis=0)
            validation[f"cnn_{name}"] = ensemble
            candidates.append({"representation": name, **metrics(y[val_idx], ensemble)})
    ranked = sorted(
        candidates,
        key=lambda row: (
            -row["balanced_accuracy"],
            -row["roc_auc"],
            config["representations"].index(row["representation"]),
        ),
    )
    selected = ranked[0]["representation"]
    pd.DataFrame(candidates).to_csv(output / "validation_candidates.csv", index=False)
    validation.to_csv(output / "validation_predictions.csv", index=False)
    write_json(
        output / "selection.json",
        {
            "selected_representation": selected,
            "threshold": 0.5,
            "rule": "Highest ensemble validation balanced accuracy, then validation ROC AUC, then prespecified config order. Epochs minimize weighted validation BCE.",
            "seeds": config["training_seeds"],
            "config": config,
            "manifest_sha256": sha256(output / "manifest.json"),
            "modeling_sha256": sha256(Path(__file__)),
            "checkpoint_sha256": {
                path.name: sha256(path)
                for path in sorted(models.glob("*"))
                if path.is_file()
            },
            "training_seconds": time.monotonic() - started,
            "versions": {
                name: importlib.metadata.version(name)
                for name in ["numpy", "pandas", "scikit-learn", "torch", "matplotlib"]
            },
        },
    )
    print(
        f"Frozen selected representation: {selected}; test partition not scored during selection",
        flush=True,
    )


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


def evaluate(config: dict, output: Path) -> None:
    """Score the frozen CNN and basic baselines on untouched test scenarios."""
    verify_data(output)
    selection = read_json(output / "selection.json")
    if (
        sha256(output / "manifest.json") != selection["manifest_sha256"]
        or selection["config"] != config
    ):
        raise ValueError("Dataset/config changed after selection")
    if sha256(Path(__file__)) != selection["modeling_sha256"]:
        raise ValueError("Modeling code changed after selection; retrain")
    for name, digest in selection["checkpoint_sha256"].items():
        if sha256(output / "models" / name) != digest:
            raise ValueError(f"Checkpoint changed: {name}")
    torch.set_num_threads(config["threads"])
    table = pd.read_csv(output / "trials.csv")
    train_idx = np.flatnonzero(table.split.eq("train"))
    test_idx = np.flatnonzero(table.split.eq("test"))
    test = table.iloc[test_idx].copy().reset_index(drop=True)
    name = selection["selected_representation"]
    with np.load(output / "dataset.npz") as dataset:
        raw = dataset[name]
        with np.load(output / "models" / f"{name}_normalization.npz") as scaler:
            values = np.concatenate(
                [
                    np.where(
                        np.isfinite(raw), (raw - scaler["mean"]) / scaler["scale"], 0
                    ),
                    np.isfinite(raw),
                ],
                axis=1,
            ).astype(np.float32)
        probabilities = []
        seed_results = []
        for seed in selection["seeds"]:
            checkpoint = torch.load(
                output / "models" / f"{name}_seed{seed}.pt",
                map_location="cpu",
                weights_only=True,
            )
            model = SmallCNN(checkpoint["channels"])
            model.load_state_dict(checkpoint["state_dict"])
            probability = predict(model, values[test_idx], config["batch_size"])
            probabilities.append(probability)
            test[f"seed_{seed}_probability"] = probability
            seed_results.append(
                {"seed": seed, **metrics(test.target.to_numpy(), probability)}
            )
        test["cnn_probability"] = np.mean(probabilities, axis=0)
        baseline = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=1.0,
                class_weight="balanced",
                random_state=config["split_seed"],
                max_iter=2000,
            ),
        )
        features = summarize_features(values)
        baseline.fit(features[train_idx], table.target.to_numpy()[train_idx])
        test["summary_logistic_probability"] = baseline.predict_proba(
            features[test_idx]
        )[:, 1]
        # Quality control baseline sees all four original representation masks,
        # but no amplitude/phase values. Global mean and temporal variation only.
        masks = np.concatenate(
            [
                np.isfinite(dataset[rep]).astype(np.float32)
                for rep in config["representations"]
                if rep != "phase_change_smoothed"
            ],
            axis=1,
        )
        quality_features = summarize_features(masks)
        quality_model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=1.0,
                class_weight="balanced",
                random_state=config["split_seed"],
                max_iter=2000,
            ),
        )
        quality_model.fit(
            quality_features[train_idx], table.target.to_numpy()[train_idx]
        )
        test["quality_only_probability"] = quality_model.predict_proba(
            quality_features[test_idx]
        )[:, 1]
    majority = int(table.iloc[train_idx].target.mean() >= 0.5)
    test["majority_probability"] = float(majority)
    test["cnn_prediction"] = (test.cnn_probability >= selection["threshold"]).astype(
        int
    )
    test.to_csv(output / "test_predictions.csv", index=False)
    results = {
        column.removesuffix("_probability"): metrics(
            test.target.to_numpy(), test[column].to_numpy()
        )
        for column in [
            "cnn_probability",
            "summary_logistic_probability",
            "quality_only_probability",
            "majority_probability",
        ]
    }
    pd.DataFrame(seed_results).to_csv(output / "test_seed_metrics.csv", index=False)
    pd.DataFrame(
        [
            {
                "activity": label,
                **metrics(group.target.to_numpy(), group.cnn_probability.to_numpy()),
            }
            for label, group in test.groupby("label")
        ]
    ).to_csv(output / "test_activity_metrics.csv", index=False)
    write_json(
        output / "test_metrics.json",
        {
            "selected_representation": name,
            "threshold": selection["threshold"],
            "test_attempts": len(test),
            "test_scenarios": test.scenario_id.nunique(),
            "metrics": results,
            "cnn_scenario_bootstrap_95_percent_intervals": cluster_intervals(
                test, test.cnn_probability.to_numpy()
            ),
            "bootstrap_seed": 812,
            "bootstrap_repetitions": 2000,
            "selection_sha256": sha256(output / "selection.json"),
            "scope": "Pilot within one session/participant; fixed cue-aligned attempt classification, not continuous detection.",
        },
    )
    print(pd.DataFrame(results).T.to_string(), flush=True)
