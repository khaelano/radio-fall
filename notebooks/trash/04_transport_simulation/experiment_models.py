"""Matched-budget clean/missingness-trained CNNs and frozen comparisons."""

from __future__ import annotations

from copy import deepcopy
import importlib.metadata
from pathlib import Path
import random
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from support import case_path, read_json, sha256, write_json
from modeling import SmallCNN, cluster_intervals, metrics
from prepare import verify
from replay import stable_seed


class Cases:
    """Memory-map cases and construct explicitly masked model inputs on demand."""

    def __init__(self, output: Path, config: dict) -> None:
        self.output, self.config, self.cache = output, config, {}

    def raw(self, condition: str, seed: int) -> tuple:
        """Return read-only phase, count and age arrays for one case."""
        key = condition, seed
        if key not in self.cache:
            directory = case_path(self.output, condition, seed)
            self.cache[key] = tuple(
                np.load(directory / f"{name}.npy", mmap_mode="r")
                for name in ("values", "counts", "age")
            )
        return self.cache[key]

    def input(self, condition: str, seed: int, index: int, scaler: dict) -> np.ndarray:
        """Scale phase with train-only moments and append masks/counts/ages."""
        values, counts, age = self.raw(condition, seed)
        x = values[index]
        finite = np.isfinite(x)
        normalized = np.where(finite, (x - scaler["mean"]) / scaler["scale"], 0)
        telemetry = np.concatenate(
            (
                np.clip(
                    counts[index] / (self.config["source_hz"] / self.config["bin_hz"]),
                    0,
                    1,
                ),
                age[index],
            )
        )
        telemetry = np.broadcast_to(telemetry[:, :, None], (4, x.shape[1], x.shape[2]))
        return np.concatenate((normalized, finite, telemetry)).astype(np.float32)


def fit_scaler(cases: Cases, indices: np.ndarray) -> dict:
    """Fit common per-channel/tone moments on original training attempts only."""
    values = cases.raw("original_100", cases.config["training_realizations"][0])[0]
    count = np.zeros((4, 1, 242), dtype=float)
    total, squared = np.zeros_like(count), np.zeros_like(count)
    for index in indices:
        x = values[index].astype(float)
        valid = np.isfinite(x)
        count += valid.sum(axis=1, keepdims=True)
        total += np.where(valid, x, 0).sum(axis=1, keepdims=True)
        squared += np.where(valid, x * x, 0).sum(axis=1, keepdims=True)
    mean = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    var = (
        np.divide(squared, count, out=np.ones_like(total), where=count > 0)
        - mean * mean
    )
    return dict(
        mean=mean.astype(np.float32),
        scale=np.maximum(np.sqrt(np.maximum(var, 0)), 0.05).astype(np.float32),
        count=count,
    )


class Attempts(Dataset):
    """One variant per original attempt/epoch, keeping update counts matched."""

    def __init__(
        self,
        cases: Cases,
        table: pd.DataFrame,
        indices: np.ndarray,
        scaler: dict,
        regime: str,
        seed: int,
    ) -> None:
        self.cases, self.table, self.indices, self.scaler = (
            cases,
            table,
            indices,
            scaler,
        )
        self.regime, self.seed, self.epoch = regime, seed, 0

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, position: int) -> tuple:
        index = int(self.indices[position])
        condition = "original_100"
        realization = self.cases.config["training_realizations"][0]
        if self.regime == "missingness_trained":
            rng = np.random.default_rng(stable_seed(self.seed, self.epoch, index))
            condition = self.cases.config["conditions"][
                int(rng.integers(len(self.cases.config["conditions"])))
            ]["name"]
            realization = int(rng.choice(self.cases.config["training_realizations"]))
        return torch.from_numpy(
            self.cases.input(condition, realization, index, self.scaler)
        ), torch.tensor(float(self.table.iloc[index].target), dtype=torch.float32)


def predict_case(
    model: nn.Module,
    cases: Cases,
    condition: str,
    realization: int,
    indices: np.ndarray,
    scaler: dict,
) -> np.ndarray:
    """Predict one frozen case in small batches without loading all cases."""
    model.eval()
    predictions = []
    size = cases.config["batch_size"]
    with torch.no_grad():
        for start in range(0, len(indices), size):
            batch = np.stack(
                [
                    cases.input(condition, realization, int(i), scaler)
                    for i in indices[start : start + size]
                ]
            )
            predictions.extend(torch.sigmoid(model(torch.from_numpy(batch))).numpy())
    return np.asarray(predictions)


def train(config: dict, output: Path) -> None:
    """Freeze six checkpoints using training/validation attempts only."""
    verify(config, output, full=True)
    if (output / "selection.json").exists():
        raise ValueError("Models already frozen; choose a new output for another run")
    torch.set_num_threads(config["threads"])
    torch.use_deterministic_algorithms(True)
    cases = Cases(output, config)
    table = pd.read_csv(output / "trials.csv")
    train_indices = np.flatnonzero(table.split.eq("train"))
    val_indices = np.flatnonzero(table.split.eq("validation"))
    targets = table.target.to_numpy(dtype=np.float32)
    scaler = fit_scaler(cases, train_indices)
    models = output / "models"
    models.mkdir(exist_ok=True)
    np.savez(models / "normalization.npz", **scaler)
    histories, selections = [], []
    started = time.monotonic()
    for regime in ("clean_trained", "missingness_trained"):
        val_names = (
            ["original_100"]
            if regime == "clean_trained"
            else [c["name"] for c in config["conditions"]]
        )
        for seed in config["training_seeds"]:
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)
            model = SmallCNN(12)
            optimizer = torch.optim.AdamW(
                model.parameters(),
                lr=config["learning_rate"],
                weight_decay=config["weight_decay"],
            )
            weight = float(
                (targets[train_indices] == 0).sum()
                / (targets[train_indices] == 1).sum()
            )
            loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(weight))
            dataset = Attempts(cases, table, train_indices, scaler, regime, seed)
            loader = DataLoader(
                dataset,
                batch_size=config["batch_size"],
                shuffle=True,
                generator=torch.Generator().manual_seed(seed),
            )
            # The validation realization is never used for training variants.
            val_values = np.concatenate(
                [
                    np.stack(
                        [
                            cases.input(
                                name, config["validation_realization"], int(i), scaler
                            )
                            for i in val_indices
                        ]
                    )
                    for name in val_names
                ]
            )
            val_targets = np.tile(targets[val_indices], len(val_names))
            best, best_state, best_epoch, stale = float("inf"), None, 0, 0
            for epoch in range(1, config["max_epochs"] + 1):
                dataset.epoch = epoch
                model.train()
                total = 0.0
                for batch, labels in loader:
                    optimizer.zero_grad()
                    loss = loss_fn(model(batch), labels)
                    loss.backward()
                    optimizer.step()
                    total += float(loss.detach()) * len(labels)
                model.eval()
                val_loss = 0.0
                with torch.no_grad():
                    for start in range(0, len(val_targets), config["batch_size"]):
                        stop = start + config["batch_size"]
                        logits = model(torch.from_numpy(val_values[start:stop]))
                        loss = loss_fn(
                            logits, torch.from_numpy(val_targets[start:stop])
                        )
                        val_loss += float(loss) * len(logits)
                val_loss /= len(val_targets)
                if not np.isfinite(val_loss):
                    raise ValueError("Nonfinite validation loss")
                histories.append(
                    dict(
                        regime=regime,
                        seed=seed,
                        epoch=epoch,
                        train_loss=total / len(train_indices),
                        validation_loss=val_loss,
                    )
                )
                if val_loss < best - 1e-5:
                    best, best_state, best_epoch, stale = (
                        val_loss,
                        deepcopy(model.state_dict()),
                        epoch,
                        0,
                    )
                else:
                    stale += 1
                if stale >= config["patience"]:
                    break
            torch.save(
                dict(
                    state_dict=best_state,
                    channels=12,
                    regime=regime,
                    seed=seed,
                    best_epoch=best_epoch,
                ),
                models / f"{regime}_{seed}.pt",
            )
            selections.append(
                dict(
                    regime=regime,
                    seed=seed,
                    best_epoch=best_epoch,
                    validation_loss=best,
                    validation_conditions=val_names,
                )
            )
            pd.DataFrame(histories).to_csv(output / "training_history.csv", index=False)
            print(
                f"{regime}, seed {seed}: epoch {best_epoch}, validation BCE {best:.4f}",
                flush=True,
            )
            del val_values
    write_json(
        output / "selection.json",
        dict(
            models=selections,
            threshold=0.5,
            config=config,
            manifest_sha256=sha256(output / "manifest.json"),
            checkpoint_sha256={p.name: sha256(p) for p in sorted(models.iterdir())},
            training_seconds=time.monotonic() - started,
            validation_rule="Weighted BCE; original validation condition for clean training, equal-condition mean for missingness training. No test selection.",
            matched_budget="One variant per original training attempt per epoch, same maximum epochs and optimizer settings.",
            versions={
                name: importlib.metadata.version(name)
                for name in ("numpy", "pandas", "torch", "scikit-learn", "matplotlib")
            },
        ),
    )


def baseline_features(values: np.ndarray, counts: np.ndarray, age: np.ndarray) -> tuple:
    """Return signal summaries and a separate missingness-only diagnostic."""
    finite = np.isfinite(values)
    valid = finite.sum(axis=(1, 2))
    means = np.divide(
        np.where(finite, values, 0).sum(axis=(1, 2)),
        valid,
        out=np.zeros(4),
        where=valid > 0,
    )
    squares = np.divide(
        np.where(finite, values * values, 0).sum(axis=(1, 2)),
        valid,
        out=np.zeros(4),
        where=valid > 0,
    )
    quality = np.concatenate(
        [
            finite.mean(axis=(1, 2)),
            counts.mean(axis=1),
            counts.std(axis=1),
            (counts == 0).mean(axis=1),
            age.mean(axis=1),
            age.std(axis=1),
        ]
    )
    return np.concatenate(
        (means, np.sqrt(np.maximum(0, squares - means * means)), quality)
    ), quality


def evaluate(config: dict, output: Path) -> None:
    """Evaluate all prespecified conditions with an unseen replay realization."""
    verify(config, output, full=True)
    selection = read_json(output / "selection.json")
    if selection["manifest_sha256"] != sha256(output / "manifest.json"):
        raise ValueError("Preparation changed after training")
    for name, digest in selection["checkpoint_sha256"].items():
        if sha256(output / "models" / name) != digest:
            raise ValueError("Checkpoint/normalizer changed after training")
    torch.set_num_threads(config["threads"])
    cases, table = Cases(output, config), pd.read_csv(output / "trials.csv")
    train_idx = np.flatnonzero(table.split.eq("train"))
    test_idx = np.flatnonzero(table.split.eq("test"))
    test = table.iloc[test_idx].reset_index(drop=True)
    y = table.target.to_numpy()
    scaler = dict(np.load(output / "models" / "normalization.npz"))
    predictions, summaries, intervals, seed_metrics = [], [], [], []
    for regime in ("clean_trained", "missingness_trained"):
        fit_conditions = (
            ["original_100"]
            if regime == "clean_trained"
            else [c["name"] for c in config["conditions"]]
        )
        fit_x, fit_quality, fit_y = [], [], []
        # Baselines get the same number of original attempts; augmentation is
        # deterministic and label-independent, one variant per attempt.
        for position, i in enumerate(train_idx):
            name = fit_conditions[position % len(fit_conditions)]
            raw = cases.raw(
                name,
                config["training_realizations"][
                    position % len(config["training_realizations"])
                ],
            )
            x, quality = baseline_features(*(a[i] for a in raw))
            fit_x.append(x)
            fit_quality.append(quality)
            fit_y.append(y[i])
        baselines = []
        for name, features in (
            ("signal_logistic", fit_x),
            ("missingness_only", fit_quality),
        ):
            estimator = make_pipeline(
                StandardScaler(),
                LogisticRegression(
                    class_weight="balanced", max_iter=2000, random_state=17
                ),
            )
            estimator.fit(features, fit_y)
            baselines.append((name, estimator))
        models = []
        for seed in config["training_seeds"]:
            checkpoint = torch.load(
                output / "models" / f"{regime}_{seed}.pt",
                weights_only=True,
                map_location="cpu",
            )
            model = SmallCNN(checkpoint["channels"])
            model.load_state_dict(checkpoint["state_dict"])
            models.append((seed, model))
        for condition in config["conditions"]:
            name, realization = condition["name"], config["test_realization"]
            probabilities = []
            for seed, model in models:
                p = predict_case(model, cases, name, realization, test_idx, scaler)
                probabilities.append(p)
                seed_metrics.append(
                    dict(
                        regime=regime,
                        condition=name,
                        seed=seed,
                        **metrics(y[test_idx], p),
                    )
                )
            result = {"cnn": np.mean(probabilities, axis=0)}
            raw = cases.raw(name, realization)
            features = [baseline_features(*(a[i] for a in raw)) for i in test_idx]
            for number, (baseline_name, estimator) in enumerate(baselines):
                result[baseline_name] = estimator.predict_proba(
                    np.stack([f[number] for f in features])
                )[:, 1]
            result["majority"] = np.full(len(test), float(np.mean(y[train_idx]) >= 0.5))
            for model_name, p in result.items():
                summaries.append(
                    dict(
                        regime=regime,
                        condition=name,
                        model=model_name,
                        **metrics(y[test_idx], p),
                    )
                )
                frame = test[["attempt_id", "scenario_id", "label", "target"]].copy()
                frame["regime"], frame["condition"], frame["model"] = (
                    regime,
                    name,
                    model_name,
                )
                frame["probability"], frame["prediction"] = p, (p >= 0.5).astype(int)
                predictions.extend(frame.to_dict("records"))
            interval = cluster_intervals(
                test,
                result["cnn"],
                seed=812,
                repetitions=config["bootstrap_repetitions"],
            )
            intervals.append(dict(regime=regime, condition=name, intervals=interval))
            print(
                f"{regime}/{name}: CNN BA={summaries[-4]['balanced_accuracy']:.3f}",
                flush=True,
            )
    pd.DataFrame(predictions).to_csv(output / "test_predictions.csv", index=False)
    pd.DataFrame(summaries).to_csv(output / "test_metrics.csv", index=False)
    pd.DataFrame(seed_metrics).to_csv(output / "test_seed_metrics.csv", index=False)
    write_json(output / "test_intervals.json", intervals)
    write_json(
        output / "evaluation.json",
        dict(
            selection_sha256=sha256(output / "selection.json"),
            metrics_sha256=sha256(output / "test_metrics.csv"),
            predictions_sha256=sha256(output / "test_predictions.csv"),
            scope="Exploratory reused within-session scenario split, not new-session generalization or hardware validation.",
        ),
    )
