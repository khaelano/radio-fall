"""Explicit random-window phase-only retraining on the frozen four-RX cohort."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import importlib.metadata
import json
import multiprocessing
from pathlib import Path
import random
import shutil
import statistics
import sys
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

FOLDER = Path(__file__).resolve().parent
sys.path.insert(0, str(FOLDER.parent / "05_four_rx_cnn"))
from support import (  # noqa: E402
    ROOT,
    SmallCNN,
    code_hashes,
    metrics,
    predict,
    read_json,
    sha256,
    write_json,
)
from training import validation_loss  # noqa: E402
from fall_detection.detection.replay import load_attempt  # noqa: E402
from fall_detection.radio.acquisition.native import require_native  # noqa: E402


def reference_phase_windows(rows: list, starts: list[int]) -> np.ndarray:
    """Independently compute lagged phase/bin means with integer capture times."""
    result = [[] for _ in starts]
    for rx in range(4):
        unique = {(t, r.sequence): r for r, receiver, t in rows if receiver == rx}
        times, phases = [], []
        for (capture, _), record in sorted(unique.items()):
            encoded = record.wire
            phase = record.phase_bytes()
            if encoded[37:40] != bytes([4, 0, 0]) or phase is None:
                continue
            tones, _, raw, calibrated = phase
            order = np.argsort(tones)
            tones = np.asarray(tones)[order]
            keep = (np.abs(tones) > 1) & (np.abs(tones) <= 122)
            values = np.frombuffer(calibrated, dtype="=f8")[order][keep].copy()
            valid = np.isfinite(np.frombuffer(raw, dtype="=f8")[order][keep])
            values[~valid] = np.nan
            if encoded[50] != 0:
                values[:] = np.nan
            times.append(capture)
            phases.append(values)
        times = np.asarray(times, dtype=np.int64)
        phases = np.asarray(phases)
        previous = np.searchsorted(times, times - 100_000_000, side="right") - 1
        valid = (previous >= 0) & (
            (times - times[np.maximum(previous, 0)]) <= 150_000_000
        )
        delta = np.full_like(phases, np.nan)
        delta[valid] = np.angle(np.exp(1j * (phases[valid] - phases[previous[valid]])))
        for wi, start in enumerate(starts):
            inside = (times >= start) & (times < start + 4_000_000_000)
            bins = (times[inside] - start) * 25 // 1_000_000_000
            for component in [np.sin(delta[inside]), np.cos(delta[inside])]:
                finite = np.isfinite(component)
                total = np.zeros((100, 242))
                count = np.zeros_like(total)
                np.add.at(total, bins, np.where(finite, component, 0))
                np.add.at(count, bins, finite)
                result[wi].append(
                    np.divide(
                        total, count, out=np.full_like(total, np.nan), where=count > 0
                    )
                )
    return np.asarray(result, dtype=np.float32)


def prepare_one(job: tuple) -> tuple[list[dict], dict]:
    """Build all candidate phase windows with the same Rust path used live."""
    session, row, config = job
    session = Path(session)
    environment = read_json(session / "session.json")["environment"]
    inventory = environment["radio_inventory"]
    bundle = SimpleNamespace(
        metadata=dict(
            receivers=config["receivers"],
            radio=dict(
                profile_fingerprint=environment["radio_profile_fingerprint"],
                transmitter_mac=inventory["transmitter"]["mac"],
                receiver_macs=[
                    next(r["mac"] for r in inventory["receivers"] if r["id"] == key)
                    for key in config["receivers"]
                ],
            ),
        )
    )
    low, high = min(config["offsets_seconds"]), max(config["offsets_seconds"])
    rows, start = load_attempt(bundle, session, row["attempt_id"], low)
    if high != low:
        extra, _ = load_attempt(bundle, session, row["attempt_id"], high)
        rows.extend(extra)  # Rust deduplicates capture/sequence identities.
    cue = start - round(low * 1e9)
    starts = [cue + round(offset * 1e9) for offset in config["offsets_seconds"]]
    reference = reference_phase_windows(rows, starts)
    native = require_native().CnnPreprocessor(
        [0.0] * 968, [1.0] * 968, workers=1, representation="phase_change"
    )
    values, quality = [], []
    try:
        for wi, offset in enumerate(config["offsets_seconds"]):
            window = native.build(rows, starts[wi])
            metadata = json.loads(window.metadata_json())
            values.append(
                np.frombuffer(window.raw_bytes(), dtype="=f4").reshape(8, 100, 242)
            )
            if not np.array_equal(np.isfinite(values[-1]), np.isfinite(reference[wi])):
                raise ValueError("Native/reference phase masks differ")
            error = float(np.nanmax(np.abs(values[-1] - reference[wi])))
            if error > 1e-6:
                raise ValueError(f"Native/reference phase values differ: {error}")
            quality.extend(
                dict(
                    offset_seconds=offset,
                    phase_change_coverage=coverage,
                    reference_maximum_error=error,
                )
                for coverage in metadata["phase_change_coverage"]
            )
    finally:
        native.close()
    return quality, {"phase_change": np.stack(values)}


def random_offsets(attempt_id: str, config: dict, round_id: int = 0) -> list[float]:
    """Return distinct seeded shifts in nanoseconds, excluding the central window."""
    trial, attempt = map(int, attempt_id.split("/"))
    rng = np.random.default_rng(
        np.random.SeedSequence([config["augmentation_seed"], trial, attempt, round_id])
    )
    low = round(config["shift_min_seconds"] * 1e9)
    high = round(config["shift_max_seconds"] * 1e9)
    if not low < 0 < high or config["random_shifts_per_attempt"] < 20:
        raise ValueError("Require at least 20 random shifts spanning the cue")
    # Stratification spreads the random windows over the requested interval.
    edges = np.linspace(low, high, config["random_shifts_per_attempt"] + 1).astype(int)
    shifts = [
        int(rng.integers(a, b)) for a, b in zip(edges[:-1], edges[1:], strict=True)
    ]
    if 0 in shifts:
        shifts[shifts.index(0)] = 1
    rng.shuffle(shifts)
    return [shift / 1e9 for shift in shifts]


def encode(raw: np.ndarray) -> np.ndarray:
    """Keep bounded sine/cosine values unchanged, zero-impute and append masks."""
    finite = np.isfinite(raw)
    if np.any(np.abs(raw[finite]) > 1.000001):
        raise ValueError("Phase sine/cosine outside its physical bounds")
    return np.concatenate([np.where(finite, raw, 0), finite], axis=-3).astype("float32")


def prepare_attempt(job: tuple) -> tuple[list[dict], np.ndarray, list[dict]]:
    """Decode one attempt and retain 20 quality-qualified random training shifts."""
    session, row, config = job
    chosen, arrays, audit = [], [], []
    # Failed candidates are replaced using new seeded draws; never reduce the quota.
    for round_id in range(10):
        offsets = ([0.0] if round_id == 0 else []) + (
            random_offsets(row["attempt_id"], config, round_id)
            if row["split"] == "train"
            else []
        )
        local = dict(config, offsets_seconds=offsets, minimum_coverage=0.0)
        quality, data = prepare_one((session, row, local))
        if data is None:
            raise ValueError(f"Cannot prepare {row['attempt_id']}: {quality[-1]}")
        for oi, offset in enumerate(offsets):
            coverage = [
                q["phase_change_coverage"]
                for q in quality
                if q["offset_seconds"] == offset
            ]
            valid = len(coverage) == 4 and min(coverage) >= config["minimum_coverage"]
            audit.append(
                dict(
                    attempt_id=row["attempt_id"],
                    offset_seconds=offset,
                    minimum_coverage=min(coverage),
                    qualified=valid,
                    reference_maximum_error=max(
                        q.get("reference_maximum_error", 0)
                        for q in quality
                        if q["offset_seconds"] == offset
                    ),
                )
            )
            if not valid:
                if offset == 0:
                    raise ValueError("Parent cohort has an invalid central window")
                continue
            if offset in [item["offset_seconds"] for item in chosen]:
                continue
            chosen.append(dict(row, offset_seconds=offset, central=offset == 0))
            arrays.append(data["phase_change"][oi])
            needed = (
                config["random_shifts_per_attempt"] + 1
                if row["split"] == "train"
                else 1
            )
            if len(chosen) == needed:
                return chosen, np.stack(arrays).astype("float32"), audit
    raise ValueError(f"Insufficient qualified shifts for {row['attempt_id']}")


def prepare(config: dict, output: Path) -> None:
    """Preserve the parent split/cohort and materialize every augmented example."""
    contract = dict(
        window_seconds=4.0,
        bin_hz=25,
        lag_seconds=0.1,
        smoothing_bins=1,
        normalization="none",
        representations=["phase_change"],
    )
    if any(config.get(key) != value for key, value in contract.items()):
        raise ValueError(
            "Configuration differs from the supported native phase contract"
        )
    if output.exists():
        raise ValueError("Preparation requires a new output directory")
    parent = (FOLDER / config["parent_experiment"]).resolve()
    original = read_json(parent / "manifest.json")
    session = Path(original["raw_session"])
    if output.is_relative_to(session) or session.is_relative_to(output):
        raise ValueError("Output overlaps raw data")
    if sha256(parent / "trials.csv") != original["trials_sha256"]:
        raise ValueError("Parent cohort changed")
    table = pd.read_csv(parent / "trials.csv")
    if table.groupby("scenario_id").split.nunique().ne(1).any():
        raise ValueError("Parent scenario leakage")
    print("Verifying all raw source hashes", flush=True)
    for name, digest in original["source_sha256"].items():
        if sha256(session / name) != digest:
            raise ValueError(f"Raw source changed: {name}")
    output.mkdir(parents=True)
    table.to_csv(output / "trials.csv", index=False)
    total = sum(
        config["random_shifts_per_attempt"] + 1 if split == "train" else 1
        for split in table.split
    )
    raw = np.lib.format.open_memmap(
        output / "phase_change.npy",
        mode="w+",
        dtype="float32",
        shape=(total, 8, 100, 242),
    )
    rows, audits = [], []
    jobs = [(str(session), row, config) for row in table.to_dict("records")]
    with ProcessPoolExecutor(
        max_workers=config["workers"], mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        for i, (windows, values, audit) in enumerate(pool.map(prepare_attempt, jobs)):
            raw[len(rows) : len(rows) + len(windows)] = values
            rows.extend(windows)
            audits.extend(audit)
            if (i + 1) % 10 == 0:
                print(
                    f"Prepared {i + 1}/{len(table)} attempts; {len(rows)} windows",
                    flush=True,
                )
    raw.flush()
    del raw
    windows = pd.DataFrame(rows)
    windows.insert(0, "window_index", np.arange(len(rows)))
    windows.to_csv(output / "windows.csv", index=False)
    pd.DataFrame(audits).to_csv(output / "augmentation_audit.csv", index=False)
    if len(rows) != total:
        raise ValueError("Augmentation quota mismatch")
    write_json(
        output / "manifest.json",
        dict(
            config=config,
            raw_session=str(session),
            source_sha256=original["source_sha256"],
            parent_manifest_sha256=sha256(parent / "manifest.json"),
            cohort="Same 206 quality-retained attempts and scenario split as four_rx_v1; original 26 exclusions retained.",
            trials_sha256=sha256(output / "trials.csv"),
            windows_sha256=sha256(output / "windows.csv"),
            arrays_sha256={"phase_change": sha256(output / "phase_change.npy")},
            code_sha256=current_code_hashes(),
            windows=total,
            numpy_parity=dict(
                windows=len(audits),
                maximum_absolute_error=max(
                    q["reference_maximum_error"] for q in audits
                ),
                finite_masks_identical=True,
                tolerance=1e-6,
            ),
            representation="100 ms wrapped calibrated phase difference; sine/cosine before 25 Hz bin means; no smoothing or fitted normalization",
            layout="window, receiver/sin-cos component, time, physical HE20 tone",
        ),
    )
    print(windows.groupby("split").size().to_string(), flush=True)


def current_code_hashes() -> dict:
    """Record the experiment and shared implementation used at each frozen stage."""
    return {
        **code_hashes(),
        **{str(p.relative_to(ROOT)): sha256(p) for p in FOLDER.glob("*.py")},
    }


def verify(config: dict, output: Path) -> pd.DataFrame:
    """Reject modified inputs or leaking scenario/window membership."""
    manifest = read_json(output / "manifest.json")
    if config != manifest["config"]:
        raise ValueError("Configuration changed")
    for filename, digest in [
        ("windows.csv", manifest["windows_sha256"]),
        ("trials.csv", manifest["trials_sha256"]),
        ("phase_change.npy", manifest["arrays_sha256"]["phase_change"]),
    ]:
        if sha256(output / filename) != digest:
            raise ValueError(f"Prepared input changed: {filename}")
    table = pd.read_csv(output / "windows.csv")
    if table.groupby("scenario_id").split.nunique().ne(1).any():
        raise ValueError("Scenario leakage")
    training = table.loc[table.split.eq("train")]
    if (
        not training.groupby("attempt_id")
        .size()
        .eq(config["random_shifts_per_attempt"] + 1)
        .all()
    ):
        raise ValueError("Every training attempt must have 20 shifts plus center")
    if not table.loc[~table.split.eq("train"), "offset_seconds"].eq(0).all():
        raise ValueError("Held-out windows must remain unaugmented")
    return table


class PhaseDataset(Dataset):
    """Expose all materialized windows to the shuffled loader on every epoch."""

    def __init__(self, raw: np.ndarray, table: pd.DataFrame):
        self.raw = raw
        self.indices = table.window_index.to_numpy()
        self.targets = table.target.to_numpy(dtype="float32")

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return torch.from_numpy(encode(self.raw[self.indices[index]])), torch.tensor(
            self.targets[index]
        )


def train(config: dict, output: Path) -> None:
    """Fit three fresh CNNs; choose epochs using central validation BCE only."""
    table = verify(config, output)
    models = output / "models"
    if models.exists():
        raise ValueError("Refuse to overwrite trained checkpoints")
    models.mkdir()
    torch.set_num_threads(config["threads"])
    torch.use_deterministic_algorithms(True)
    training = table.loc[table.split.eq("train")]
    validation = table.loc[table.split.eq("validation")].copy()
    raw = np.load(output / "phase_change.npy", mmap_mode="r")
    val_values = encode(raw[validation.window_index.to_numpy()])
    y_val = validation.target.to_numpy()
    weight = float(training.target.eq(0).sum() / training.target.eq(1).sum())
    dataset = PhaseDataset(raw, training)
    histories, probabilities = [], []
    began = time.monotonic()
    tag = f"{config['scheme']}__phase_change"
    for seed in config["training_seeds"]:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        model = SmallCNN(16)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config["learning_rate"],
            weight_decay=config["weight_decay"],
        )
        criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(weight))
        loader = DataLoader(
            dataset,
            batch_size=config["batch_size"],
            shuffle=True,
            generator=torch.Generator().manual_seed(seed),
            num_workers=0,
        )
        best_loss, best_epoch, best_state, stale = float("inf"), 0, None, 0
        for epoch in range(1, config["max_epochs"] + 1):
            model.train()
            loss_sum = 0.0
            for values, targets in loader:
                optimizer.zero_grad()
                loss = criterion(model(values), targets)
                loss.backward()
                optimizer.step()
                loss_sum += float(loss.detach()) * len(targets)
            p = predict(model, val_values, config["batch_size"])
            val_loss = validation_loss(p, y_val, weight)
            if not np.isfinite(val_loss):
                raise ValueError("Nonfinite validation loss")
            histories.append(
                dict(
                    seed=seed,
                    epoch=epoch,
                    train_loss=loss_sum / len(dataset),
                    validation_loss=val_loss,
                    validation_balanced_accuracy=metrics(y_val, p)["balanced_accuracy"],
                    windows_per_epoch=len(dataset),
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
            pd.DataFrame(histories).to_csv(output / "training_history.csv", index=False)
            print(
                f"seed={seed} epoch={epoch} train={loss_sum / len(dataset):.4f} val={val_loss:.4f} elapsed={time.monotonic() - began:.0f}s",
                flush=True,
            )
            if stale >= config["patience"]:
                break
        model.load_state_dict(best_state)
        torch.save(
            dict(
                state_dict=best_state,
                channels=16,
                scheme=config["scheme"],
                representation="phase_change",
                normalization="none",
                seed=seed,
                best_epoch=best_epoch,
            ),
            models / f"{tag}_seed{seed}.pt",
        )
        probabilities.append(predict(model, val_values, config["batch_size"]))
    validation["probability"] = np.mean(probabilities, axis=0)
    validation.to_csv(output / "validation_predictions.csv", index=False)
    write_json(
        output / "selection.json",
        dict(
            config=config,
            selected_by_scheme={config["scheme"]: "phase_change"},
            winner=dict(scheme=config["scheme"], representation="phase_change"),
            threshold=0.5,
            normalization="none",
            rule="Architecture and representation fixed before training; each seed minimizes central validation weighted BCE. Threshold fixed at 0.5.",
            augmentation="20 materialized random shifts plus center per training attempt; all 21 visited every epoch; no held-out augmentation in training",
            manifest_sha256=sha256(output / "manifest.json"),
            code_sha256=current_code_hashes(),
            checkpoint_sha256={p.name: sha256(p) for p in sorted(models.iterdir())},
            training_seconds=time.monotonic() - began,
            validation_metrics=metrics(y_val, validation.probability.to_numpy()),
            versions={
                name: importlib.metadata.version(name)
                for name in ["numpy", "pandas", "torch", "scikit-learn", "matplotlib"]
            },
        ),
    )


def evaluate(config: dict, output: Path) -> None:
    """Evaluate the frozen ensemble on the previously inspected held-out attempts."""
    from fall_detection.detection.model import (
        ModelBundle,
        export_bundle,
        load_ensemble,
        score_tensor,
    )

    table = verify(config, output)
    selection = read_json(output / "selection.json")
    if sha256(output / "manifest.json") != selection["manifest_sha256"]:
        raise ValueError("Manifest changed after training")
    bundle_path = ROOT / "data/models/phase_random20_v1"
    bundle = (
        ModelBundle.load(bundle_path)
        if bundle_path.exists()
        else export_bundle(output, bundle_path)
    )
    if bundle.metadata["selection_sha256"] != sha256(output / "selection.json"):
        raise ValueError("Existing bundle belongs to a different training selection")
    models = load_ensemble(bundle, config["threads"])
    raw = np.load(output / "phase_change.npy", mmap_mode="r")
    validation = table.loc[table.split.eq("validation")]
    val_values = encode(raw[validation.window_index.to_numpy()])
    seed_diagnostics = []
    for seed, model, name in zip(
        config["training_seeds"], models, bundle.metadata["checkpoints"], strict=True
    ):
        probability = predict(model, val_values, config["batch_size"])
        checkpoint = torch.load(
            bundle.directory / name, map_location="cpu", weights_only=True
        )
        seed_diagnostics.append(
            dict(
                seed=seed,
                best_epoch=checkpoint["best_epoch"],
                validation_balanced_accuracy=metrics(
                    validation.target.to_numpy(), probability
                )["balanced_accuracy"],
                minimum_validation_probability=float(probability.min()),
                maximum_validation_probability=float(probability.max()),
            )
        )
    write_json(output / "seed_diagnostics.json", seed_diagnostics)
    test = table.loc[table.split.eq("test")].copy()
    scores = [
        score_tensor(models, encode(raw[i])[None].tobytes())[0]
        for i in test.window_index
    ]
    test["probability"] = scores
    test["prediction"] = test.probability.ge(0.5).astype(int)
    test.to_csv(output / "test_predictions.csv", index=False)
    stationary = np.zeros((8, 100, 242), dtype=np.float32)
    stationary[1::2] = 1.0  # sin(0), cos(0) with all tones valid.
    stationary_score, stationary_seeds = score_tensor(
        models, encode(stationary)[None].tobytes()
    )
    summary = dict(
        validation=selection["validation_metrics"],
        test=metrics(test.target.to_numpy(), np.asarray(scores)),
        synthetic_stationary_phase=dict(
            probability=stationary_score,
            seed_probabilities=stationary_seeds,
            scope="Exactly zero phase change with full masks; synthetic diagnostic, not recorded standing accuracy.",
        ),
        code_sha256=current_code_hashes(),
        scope="Exploratory reuse of previously inspected scenario-held-out test split from one participant/session; no new live accuracy established.",
    )
    write_json(output / "evaluation.json", summary)
    print(
        {
            key: summary[key]
            for key in ["validation", "test", "synthetic_stationary_phase", "scope"]
        },
        flush=True,
    )


def verify_live(config: dict, output: Path) -> None:
    """Rebuild real random/central windows and compare exported scores and kernels."""
    from fall_detection.detection.model import ModelBundle, load_ensemble, score_tensor

    table = verify(config, output)
    manifest = read_json(output / "manifest.json")
    bundle = ModelBundle.load(ROOT / "data/models/phase_random20_v1")
    models = load_ensemble(bundle, config["threads"])
    raw = np.load(output / "phase_change.npy", mmap_mode="r")
    picked = []
    for split in ["train", "validation", "test"]:
        attempt = table.loc[table.split.eq(split), "attempt_id"].iloc[0]
        picked.extend(table.index[table.attempt_id.eq(attempt)].tolist())
    processors = {
        (kernel, workers): require_native().CnnPreprocessor(
            [0.0] * 968,
            [1.0] * 968,
            workers=workers,
            kernel=kernel,
            representation="phase_change",
        )
        for kernel, workers in [("scalar", 1), ("auto", 1), ("auto", 2)]
    }
    checks = []
    try:
        for attempt, group in table.loc[picked].groupby("attempt_id", sort=False):
            low, high = group.offset_seconds.min(), group.offset_seconds.max()
            rows, start = load_attempt(
                bundle, Path(manifest["raw_session"]), attempt, low
            )
            if low != high:
                extra, _ = load_attempt(
                    bundle, Path(manifest["raw_session"]), attempt, high
                )
                rows.extend(extra)
            cue = start - round(low * 1e9)
            for row in group.itertuples():
                window_start = cue + round(row.offset_seconds * 1e9)
                frame = processors[("auto", 2)].build(rows, window_start)
                expected = encode(raw[row.window_index])
                actual = np.frombuffer(frame.tensor_bytes(), dtype="=f4").reshape(
                    16, 100, 242
                )
                np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0)
                probability, _ = score_tensor(models, frame.tensor_bytes())
                expected_probability, _ = score_tensor(models, expected.tobytes())
                if abs(probability - expected_probability) > 1e-6:
                    raise ValueError(
                        "Exported live score differs from saved input score"
                    )
                for processor in processors.values():
                    other = processor.build(rows, window_start)
                    if other.tensor_bytes() != frame.tensor_bytes():
                        raise ValueError(
                            "Native scalar/SIMD/worker phase tensors differ"
                        )
                checks.append(
                    dict(
                        attempt_id=attempt,
                        offset_seconds=row.offset_seconds,
                        maximum_tensor_error=float(np.max(np.abs(actual - expected))),
                        maximum_score_error=abs(probability - expected_probability),
                    )
                )
        benchmark = {}
        for key, processor in processors.items():
            times, native_times = [], []
            for _ in range(15):
                began = time.perf_counter()
                frame = processor.build(rows, window_start)
                times.append((time.perf_counter() - began) * 1000)
                native_times.append(
                    json.loads(frame.metadata_json())["preprocessing_ms"]
                )
            benchmark[f"{key[0]}_{key[1]}_workers"] = dict(
                replay_call_median_ms=statistics.median(times),
                native_window_median_ms=statistics.median(native_times),
            )
        write_json(
            output / "live_verification.json",
            dict(
                windows=checks,
                benchmark=benchmark,
                scope="Read-only real-window score parity and native timing; no live fall accuracy measurement. Native timing excludes packet feature preparation; replay timing includes it, both exclude disk and CNN inference.",
            ),
        )
    finally:
        for processor in processors.values():
            processor.close()


def report(config: dict, output: Path) -> None:
    """Publish compact measured results without copying data arrays or weights."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    results = FOLDER / "results/phase_random20_v1"
    results.mkdir(parents=True, exist_ok=True)
    for name in [
        "manifest.json",
        "selection.json",
        "evaluation.json",
        "trials.csv",
        "windows.csv",
        "augmentation_audit.csv",
        "training_history.csv",
        "validation_predictions.csv",
        "test_predictions.csv",
        "seed_diagnostics.json",
    ]:
        shutil.copy2(output / name, results / name)
    if (output / "live_verification.json").exists():
        shutil.copy2(
            output / "live_verification.json", results / "live_verification.json"
        )
    history = pd.read_csv(output / "training_history.csv")
    windows = pd.read_csv(output / "windows.csv")
    audit = pd.read_csv(output / "augmentation_audit.csv")
    trials = pd.read_csv(output / "trials.csv")
    evaluation = read_json(output / "evaluation.json")
    selection = read_json(output / "selection.json")
    manifest = read_json(output / "manifest.json")
    fig, axes = plt.subplots(
        1, 3, figsize=(12, 3.5), constrained_layout=True, sharey=True
    )
    for axis, (seed, values) in zip(axes, history.groupby("seed"), strict=True):
        axis.plot(values.epoch, values.train_loss, label="training")
        axis.plot(values.epoch, values.validation_loss, label="validation")
        axis.set(title=f"Seed {seed}", xlabel="Epoch", ylabel="Weighted BCE")
        axis.legend()
    fig.savefig(results / "learning-curves.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.7), constrained_layout=True)
    shifts = windows.loc[windows.split.eq("train") & ~windows.central, "offset_seconds"]
    axes[0].hist(shifts, bins=20, range=(-0.5, 0.5), edgecolor="white")
    axes[0].set(xlabel="Training window shift (seconds)", ylabel="Materialized windows")
    test = evaluation["test"]
    matrix = np.array([[test["tn"], test["fp"]], [test["fn"], test["tp"]]])
    axes[1].imshow(matrix, cmap="Blues", vmin=0)
    for (i, j), value in np.ndenumerate(matrix):
        axes[1].text(j, i, str(value), ha="center", va="center")
    axes[1].set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["Non-fall", "Fall"],
        yticklabels=["Non-fall", "Fall"],
        xlabel="Prediction",
        ylabel="Recorded label",
        title="Previously inspected test scenarios",
    )
    fig.savefig(results / "shifts-and-confusion.png", dpi=160)
    plt.close(fig)
    raw = np.load(output / "phase_change.npy", mmap_mode="r")
    central = windows.loc[windows.split.eq("train") & windows.central].copy()
    motion = np.stack(
        [
            np.nanmean(1 - raw[index, 1::2], axis=(1, 2))
            for index in central.window_index
        ]
    )
    fig, axes = plt.subplots(1, 4, figsize=(12, 3), constrained_layout=True)
    for rx, axis in enumerate(axes):
        for label, target in [("Non-fall", 0), ("Fall", 1)]:
            axis.hist(
                motion[central.target.eq(target), rx], bins=15, alpha=0.55, label=label
            )
        axis.set(
            title=f"rx-{rx + 1}",
            xlabel="Mean 1 − cos(phase change)",
            ylabel="Training attempts",
        )
        axis.legend()
    fig.savefig(results / "training-phase-motion.png", dpi=160)
    plt.close(fig)
    for rx in range(4):
        central[f"rx_{rx + 1}_phase_motion"] = motion[:, rx]
    central.to_csv(results / "training_phase_summary.csv", index=False)
    groups = trials.groupby("split").size().to_dict()
    training = windows.loc[windows.split.eq("train")]
    minimum_scenario_shifts = int(
        training.loc[~training.central].groupby("scenario_id").size().min()
    )
    stationary = evaluation["synthetic_stationary_phase"]["probability"]
    rejected = int((~audit.qualified).sum())
    coverage_summary = (
        "All random candidates passed the 70% per-receiver coverage requirement; no replacements were needed."
        if rejected == 0
        else f"{rejected} random candidates failed the coverage requirement and were replaced with seeded draws to keep every quota."
    )
    live_summary = ""
    if (output / "live_verification.json").exists():
        live = read_json(output / "live_verification.json")
        measured = live["benchmark"]["auto_2_workers"]["native_window_median_ms"]
        live_summary = (
            f"Read-only raw replay verified {len(live['windows'])} real windows, including all 20 random shifts from one training attempt, "
            f"with identical saved/native tensors and ensemble scores across scalar/SIMD and worker configurations. "
            f"The cached AVX2/two-worker phase window measured {measured:.2f} ms median, excluding packet feature preparation, disk and inference. "
            "This is a pipeline check, not a measurement of live fall accuracy."
        )
    diagnostics = read_json(output / "seed_diagnostics.json")
    seed_summary = "\n".join(
        f"- Seed {row['seed']}: best epoch {row['best_epoch']}, validation balanced accuracy "
        f"{row['validation_balanced_accuracy']:.3f}, probability range "
        f"{row['minimum_validation_probability']:.4f}–{row['maximum_validation_probability']:.4f}."
        for row in diagnostics
    )
    (results / "REPORT.md").write_text(
        f"""# Phase-change CNN with 20 explicit random shifts

This run uses calibrated phase change only, with no fitted normalization and
no amplitude features. Each of {groups["train"]} training attempts contributes
20 reproducibly random shifts in [−0.5, +0.5] seconds and its central window:
{len(training)} materialized training examples, all visited on every epoch.
Every training scenario contributes at least {minimum_scenario_shifts} shifted
examples. All repetitions, receiver views and shifts stay in their original
scenario split. Validation has {groups["validation"]} central windows; the
previously inspected test split has {groups["test"]} central windows.

The raw session is `20261104T081805521126Z`. This run preserves the parent
206-attempt cohort and its 26 quality exclusions. Augmentation supplies timing
variation; overlapping windows do not create independent recordings.
{coverage_summary}

Four-second windows use 25 Hz bins and 242 physical tones for each of four
receivers. Signed calibrated phase differences use the packet at or before
100 ms earlier, with an inclusive maximum lag of 150 ms. Sine and cosine are
averaged in each bin, retaining eight feature planes and eight masks. Values
remain in [−1, 1]; only missing values become zero. There is no smoothing,
standardization, batch normalization or per-window recentering.

Timing comparisons use integer nanoseconds in both offline and live Rust
preprocessing. The older Python analysis can reject an exact 150 ms lag after
floating-point subtraction (observed in `007/01`). This run uses the exact
inclusive cutoff and leaves the old experiment unchanged. Independent NumPy
window calculations checked {manifest["numpy_parity"]["windows"]} candidate
windows: maximum feature error {manifest["numpy_parity"]["maximum_absolute_error"]:.3g},
with identical finite masks. The comparison reuses decoded packet phases and
independently calculates wrapped differences, lag admission and bin means.

Three fresh SmallCNN fits (seeds 17, 29, 43) retain the previous architecture,
with 16 input channels. Training uses class-weighted BCE and AdamW, up to 40
epochs with patience 8. Each seed's checkpoint minimizes central validation
BCE. The ensemble averages three sigmoid probabilities at fixed threshold 0.5;
neither architecture nor threshold was selected using test scores. Training
took {selection["training_seconds"] / 60:.2f} minutes on this machine.

| Partition | Attempts | Balanced accuracy | Fall recall | Specificity | ROC AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
"""
        + "".join(
            f"| {split} | {m['n']} | {m['balanced_accuracy']:.3f} | {m['fall_recall']:.3f} | {m['specificity']:.3f} | {m['roc_auc']:.3f} |\n"
            for split, m in [
                ("Validation", evaluation["validation"]),
                ("Test (reused)", test),
            ]
        )
        + f"""
Test decisions: TP {test["tp"]}, FN {test["fn"]}, FP {test["fp"]}, TN {test["tn"]}.
The fully valid synthetic zero-phase-change input scores {stationary:.6f};
this diagnostic is not measured standing accuracy.

Seed diagnostics:

{seed_summary}

The near-constant seed did not learn useful separation. All three predeclared
seeds remain in the equal-weight ensemble; no test-based pruning or retraining
was performed.

![Training and validation loss](learning-curves.png)

![Training shifts and held-out confusion matrix](shifts-and-confusion.png)

![Phase motion in central training windows only](training-phase-motion.png)

{live_summary}

The portable bundle is `data/models/phase_random20_v1/`. It contains three
checkpoints and a hash-checked preprocessing manifest, without a scaler file.
These remain exploratory results on one participant/session and an already
inspected test split. New labeled continuous recordings are required to assess
live false alarms and missed falls; augmentation does not establish that the
previous live failure is fixed.
"""
    )


def main() -> None:
    """Run one reproducible stage; keep original artifacts immutable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=["prepare", "train", "evaluate", "verify_live", "report"]
    )
    args = parser.parse_args()
    config = read_json(FOLDER / "config.json")
    output = FOLDER / "artifacts/phase_random20_v1"
    globals()[args.stage](config, output)


if __name__ == "__main__":
    main()
