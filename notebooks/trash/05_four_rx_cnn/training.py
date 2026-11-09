"""Matched-budget fixed/shifted CNNs and frozen scenario-held-out evaluation."""

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

from support import (
    SmallCNN,
    cluster_intervals,
    code_hashes,
    metrics,
    predict,
    read_json,
    sha256,
    summarize_features,
    write_json,
)


def verify(config: dict, output: Path) -> tuple[dict, pd.DataFrame]:
    """Reject changed prepared inputs, config or scenario membership."""
    manifest = read_json(output / "manifest.json")
    if manifest["config"] != config:
        raise ValueError("Config differs from preparation")
    for name, digest in manifest["arrays_sha256"].items():
        if sha256(output / f"{name}.npy") != digest:
            raise ValueError(f"Array changed: {name}")
    for filename, key in [
        ("trials.csv", "trials_sha256"),
        ("split_before_quality.csv", "split_sha256"),
    ]:
        if sha256(output / filename) != manifest[key]:
            raise ValueError(f"Split changed: {filename}")
    table = pd.read_csv(output / "trials.csv")
    if table.groupby("scenario_id").split.nunique().ne(1).any():
        raise ValueError("Scenario leakage")
    return manifest, table


def fit_scaler(raw: np.ndarray, indices: np.ndarray, offsets: list[int]) -> dict:
    """Fit per-channel/tone moments only on the permitted training windows."""
    count = np.zeros((1, raw.shape[2], 1, raw.shape[4]), dtype=np.float64)
    total, squares = count.copy(), count.copy()
    for index in indices:
        values = raw[index, offsets].astype(np.float64)
        finite = np.isfinite(values)
        count += finite.sum(axis=(0, 2), keepdims=True)
        total += np.where(finite, values, 0).sum(axis=(0, 2), keepdims=True)
        squares += np.where(finite, values**2, 0).sum(axis=(0, 2), keepdims=True)
    mean = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    variance = (
        np.divide(squares, count, out=np.ones_like(total), where=count > 0) - mean**2
    )
    return dict(
        mean=mean.astype("float32"),
        scale=np.maximum(np.sqrt(np.maximum(variance, 0)), 0.05).astype("float32"),
        training_count=count,
    )


def transform(raw: np.ndarray, scaler: dict) -> np.ndarray:
    """Zero-impute scaled missing values and retain a finite mask per channel."""
    finite = np.isfinite(raw)
    return np.concatenate(
        [np.where(finite, (raw - scaler["mean"]) / scaler["scale"], 0), finite], axis=1
    ).astype("float32")


def epoch_offsets(
    n: int, n_offsets: int, center: int, scheme: str, seed: int, epoch: int
) -> np.ndarray:
    """Choose one window per attempt/epoch, keeping fixed and shifted update counts equal."""
    if scheme == "fixed":
        return np.full(n, center)
    if scheme != "shift_augmented":
        raise ValueError("Unknown window scheme")
    return np.random.default_rng(np.random.SeedSequence([seed, epoch, 1104])).integers(
        n_offsets, size=n
    )


class WindowDataset(Dataset):
    """Read one reproducibly chosen timing variant per training attempt."""

    def __init__(
        self, raw: np.ndarray, indices: np.ndarray, target: np.ndarray, scaler: dict
    ):
        self.raw, self.indices, self.target, self.scaler = raw, indices, target, scaler
        self.offsets = np.zeros(len(indices), dtype=int)

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        trial = self.indices[index]
        values = transform(self.raw[trial, self.offsets[index]][None], self.scaler)[0]
        return torch.from_numpy(values), torch.tensor(
            self.target[trial], dtype=torch.float32
        )


def validation_loss(
    probability: np.ndarray, target: np.ndarray, weight: float
) -> float:
    """Compute the same class-weighted BCE used to fit the network."""
    p = np.clip(probability.astype(np.float64), 1e-7, 1 - 1e-7)
    return float(-(weight * target * np.log(p) + (1 - target) * np.log1p(-p)).mean())


def train(config: dict, output: Path) -> None:
    """Select representations and window scheme exclusively on central validation windows."""
    _, table = verify(config, output)
    torch.set_num_threads(config["threads"])
    torch.use_deterministic_algorithms(True)
    train_idx = np.flatnonzero(table.split.eq("train"))
    val_idx = np.flatnonzero(table.split.eq("validation"))
    y = table.target.to_numpy(dtype="float32")
    center = config["offsets_seconds"].index(0)
    models = output / "models"
    models.mkdir(exist_ok=True)
    histories, candidates = [], []
    validation = table.iloc[val_idx].copy()
    weight = float((y[train_idx] == 0).sum() / (y[train_idx] == 1).sum())
    started = time.monotonic()
    for scheme in config["schemes"]:
        allowed = (
            [center]
            if scheme == "fixed"
            else list(range(len(config["offsets_seconds"])))
        )
        for representation in config["representations"]:
            tag = f"{scheme}__{representation}"
            raw = np.load(output / f"{representation}.npy", mmap_mode="r")
            scaler = fit_scaler(raw, train_idx, allowed)
            np.savez(models / f"{tag}_normalization.npz", **scaler)
            val_values = transform(raw[val_idx, center], scaler)
            seed_probabilities = []
            for seed in config["training_seeds"]:
                random.seed(seed)
                np.random.seed(seed)
                torch.manual_seed(seed)
                model = SmallCNN(val_values.shape[1])
                optimizer = torch.optim.AdamW(
                    model.parameters(),
                    lr=config["learning_rate"],
                    weight_decay=config["weight_decay"],
                )
                loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(weight))
                dataset = WindowDataset(raw, train_idx, y, scaler)
                loader = DataLoader(
                    dataset,
                    batch_size=config["batch_size"],
                    shuffle=True,
                    generator=torch.Generator().manual_seed(seed),
                    num_workers=0,
                )
                best_loss, best_epoch, best_state, stale = float("inf"), 0, None, 0
                for epoch in range(1, config["max_epochs"] + 1):
                    dataset.offsets = epoch_offsets(
                        len(train_idx),
                        len(allowed)
                        if scheme != "fixed"
                        else len(config["offsets_seconds"]),
                        center,
                        scheme,
                        seed,
                        epoch,
                    )
                    model.train()
                    total_loss = 0.0
                    for values, targets in loader:
                        optimizer.zero_grad()
                        loss = loss_fn(model(values), targets)
                        loss.backward()
                        optimizer.step()
                        total_loss += float(loss.detach()) * len(targets)
                    probabilities = predict(model, val_values, config["batch_size"])
                    val_loss = validation_loss(probabilities, y[val_idx], weight)
                    if not np.isfinite(val_loss):
                        raise ValueError("Nonfinite training loss")
                    histories.append(
                        dict(
                            scheme=scheme,
                            representation=representation,
                            seed=seed,
                            epoch=epoch,
                            train_loss=total_loss / len(train_idx),
                            validation_loss=val_loss,
                            validation_balanced_accuracy=metrics(
                                y[val_idx], probabilities
                            )["balanced_accuracy"],
                            updates_per_epoch=len(loader),
                        )
                    )
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
                    dict(
                        state_dict=best_state,
                        channels=val_values.shape[1],
                        scheme=scheme,
                        representation=representation,
                        seed=seed,
                        best_epoch=best_epoch,
                    ),
                    models / f"{tag}_seed{seed}.pt",
                )
                seed_probabilities.append(
                    predict(model, val_values, config["batch_size"])
                )
                pd.DataFrame(histories).to_csv(
                    output / "training_history.csv", index=False
                )
                print(
                    f"{tag} seed={seed} best_epoch={best_epoch} val_BA={metrics(y[val_idx], seed_probabilities[-1])['balanced_accuracy']:.3f} elapsed={time.monotonic() - started:.0f}s",
                    flush=True,
                )
            ensemble = np.mean(seed_probabilities, axis=0)
            validation[tag] = ensemble
            candidates.append(
                dict(
                    scheme=scheme,
                    representation=representation,
                    **metrics(y[val_idx], ensemble),
                )
            )
            del raw, val_values

    def rank(row: dict) -> tuple:
        return (
            -row["balanced_accuracy"],
            -row["roc_auc"],
            config["schemes"].index(row["scheme"]),
            config["representations"].index(row["representation"]),
        )

    chosen = {
        scheme: sorted([r for r in candidates if r["scheme"] == scheme], key=rank)[0][
            "representation"
        ]
        for scheme in config["schemes"]
    }
    winner = sorted(candidates, key=rank)[0]
    pd.DataFrame(candidates).to_csv(output / "validation_candidates.csv", index=False)
    validation.to_csv(output / "validation_predictions.csv", index=False)
    write_json(
        output / "selection.json",
        dict(
            selected_by_scheme=chosen,
            winner={k: winner[k] for k in ["scheme", "representation"]},
            threshold=0.5,
            rule="Center-window validation ensemble balanced accuracy, then ROC AUC, then config order. Epochs minimize weighted validation BCE. No test selection.",
            augmentation="One uniformly random configured offset per training attempt per epoch; identical maximum updates to fixed scheme. Validation always offset zero.",
            config=config,
            manifest_sha256=sha256(output / "manifest.json"),
            code_sha256=code_hashes(),
            checkpoint_sha256={
                p.name: sha256(p) for p in sorted(models.iterdir()) if p.is_file()
            },
            training_seconds=time.monotonic() - started,
            versions={
                name: importlib.metadata.version(name)
                for name in ["numpy", "pandas", "torch", "scikit-learn", "matplotlib"]
            },
        ),
    )
    print(
        f"Frozen selection {chosen}; winner {winner['scheme']} / {winner['representation']}",
        flush=True,
    )


def quality_features(
    table: pd.DataFrame, quality: pd.DataFrame, config: dict, offset: float
) -> np.ndarray:
    """Make a missingness/transport-only control without CSI values or labels."""
    columns = [f"{r}_coverage" for r in config["representations"]] + [
        "packets",
        "max_gap_ms",
        "driver_bad_packets",
    ]
    subset = quality.loc[
        quality.offset_seconds.eq(offset) & quality.receiver.isin(config["receivers"])
    ]
    pivot = subset.pivot(index="attempt_id", columns="receiver", values=columns)
    return pivot.reindex(table.attempt_id).to_numpy(dtype=float)


def logistic(
    train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray, seed: int
) -> np.ndarray:
    """Fit a standardized class-balanced logistic control on training data only."""
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=1.0, class_weight="balanced", random_state=seed, max_iter=2000
        ),
    )
    model.fit(train_x, train_y)
    return model.predict_proba(test_x)[:, 1]


def evaluate(config: dict, output: Path) -> None:
    """Evaluate each frozen scheme at each offset, with one result per attempt."""
    _, table = verify(config, output)
    selection = read_json(output / "selection.json")
    if (
        selection["config"] != config
        or selection["manifest_sha256"] != sha256(output / "manifest.json")
        or selection["code_sha256"] != code_hashes()
    ):
        raise ValueError("Code or inputs changed after selection; retrain")
    for filename, digest in selection["checkpoint_sha256"].items():
        if sha256(output / "models" / filename) != digest:
            raise ValueError(f"Checkpoint changed: {filename}")
    torch.set_num_threads(config["threads"])
    center = config["offsets_seconds"].index(0)
    train_idx, test_idx = [np.flatnonzero(table.split.eq(s)) for s in ["train", "test"]]
    test = table.iloc[test_idx].reset_index(drop=True)
    y = table.target.to_numpy()
    quality = pd.read_csv(output / "quality.csv")
    control = quality_features(table, quality, config, 0.0)
    majority = float(table.iloc[train_idx].target.mean() >= 0.5)
    results, predictions, seeds, activity = [], [], [], []
    intervals = {}
    for scheme, representation in selection["selected_by_scheme"].items():
        tag = f"{scheme}__{representation}"
        raw = np.load(output / f"{representation}.npy", mmap_mode="r")
        with np.load(output / "models" / f"{tag}_normalization.npz") as saved:
            scaler = {k: saved[k] for k in saved.files}
        summary_train = summarize_features(transform(raw[train_idx, center], scaler))
        for oi, offset in enumerate(config["offsets_seconds"]):
            values = transform(raw[test_idx, oi], scaler)
            probabilities = []
            frame = test.copy()
            frame["scheme"], frame["representation"], frame["offset_seconds"] = (
                scheme,
                representation,
                offset,
            )
            for seed in config["training_seeds"]:
                ckpt = torch.load(
                    output / "models" / f"{tag}_seed{seed}.pt",
                    map_location="cpu",
                    weights_only=True,
                )
                model = SmallCNN(ckpt["channels"])
                model.load_state_dict(ckpt["state_dict"])
                probability = predict(model, values, config["batch_size"])
                probabilities.append(probability)
                frame[f"seed_{seed}_probability"] = probability
                seeds.append(
                    dict(
                        scheme=scheme,
                        representation=representation,
                        offset_seconds=offset,
                        seed=seed,
                        **metrics(test.target.to_numpy(), probability),
                    )
                )
            frame["cnn_probability"] = np.mean(probabilities, axis=0)
            frame["summary_logistic_probability"] = logistic(
                summary_train,
                y[train_idx],
                summarize_features(values),
                config["split_seed"],
            )
            q_test = quality_features(table, quality, config, offset)[test_idx]
            frame["quality_only_probability"] = logistic(
                control[train_idx], y[train_idx], q_test, config["split_seed"]
            )
            frame["collection_order_probability"] = logistic(
                table[["trial_ordinal"]].to_numpy()[train_idx],
                y[train_idx],
                table[["trial_ordinal"]].to_numpy()[test_idx],
                config["split_seed"],
            )
            frame["majority_probability"] = majority
            frame["cnn_prediction"] = (frame.cnn_probability >= 0.5).astype(int)
            for name in [
                "cnn",
                "summary_logistic",
                "quality_only",
                "collection_order",
                "majority",
            ]:
                results.append(
                    dict(
                        scheme=scheme,
                        representation=representation,
                        offset_seconds=offset,
                        model=name,
                        **metrics(
                            test.target.to_numpy(),
                            frame[f"{name}_probability"].to_numpy(),
                        ),
                    )
                )
            for label, group in frame.groupby("label"):
                activity.append(
                    dict(
                        scheme=scheme,
                        offset_seconds=offset,
                        activity=label,
                        **metrics(
                            group.target.to_numpy(), group.cnn_probability.to_numpy()
                        ),
                    )
                )
            predictions.append(frame)
            if offset == 0:
                intervals[scheme] = cluster_intervals(
                    test, frame.cnn_probability.to_numpy()
                )
        del raw
    score_table = pd.DataFrame(results)
    prediction_table = pd.concat(predictions, ignore_index=True)
    score_table.to_csv(output / "test_metrics.csv", index=False)
    prediction_table.to_csv(output / "test_predictions.csv", index=False)
    pd.DataFrame(seeds).to_csv(output / "test_seed_metrics.csv", index=False)
    pd.DataFrame(activity).to_csv(output / "test_activity_metrics.csv", index=False)
    stability = prediction_table.groupby(["scheme", "attempt_id"]).agg(
        prediction_changes=("cnn_prediction", "nunique"),
        min_probability=("cnn_probability", "min"),
        max_probability=("cnn_probability", "max"),
    )
    stability.to_csv(output / "timing_stability.csv")
    write_json(
        output / "evaluation.json",
        dict(
            winner=selection["winner"],
            selected_by_scheme=selection["selected_by_scheme"],
            center_scenario_bootstrap_95_percent_intervals=intervals,
            test_attempts=len(test),
            test_scenarios=int(test.scenario_id.nunique()),
            selection_sha256=sha256(output / "selection.json"),
            bootstrap_seed=812,
            bootstrap_repetitions=2000,
            scope="Within one participant/session. Five offsets are correlated sensitivity measurements, not five independent test sets. Models selected before any test scoring.",
        ),
    )
    print(
        score_table.loc[score_table.model.eq("cnn")].to_string(index=False), flush=True
    )
