"""Stratified, bounded training pilots and explicit full-run time projections."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

from .sequence_training_data import (
    DURATIONS,
    Normalizer,
    SequenceDataset,
    SegmentStore,
    fit_normalizer,
)

if TYPE_CHECKING:
    from .tinygrad_training import TrainingConfig


def prepare_profile(root: Path, per_stratum: int = 4, seed: int = 42) -> dict:
    """Sample each existing split/duration/dataset/activity without moving groups.

    Fit pilot statistics using selected training windows only. Pilot artifacts
    live separately from full-data statistics and checkpoints.
    """
    if per_stratum < 1:
        raise ValueError("per_stratum must be positive")
    folder = root / "profile"
    folder.mkdir(parents=True, exist_ok=True)
    full = pl.read_parquet(root / "window_split.parquet")
    parts = full.partition_by(
        ["duration", "split", "dataset", "activity_label", "target"],
        maintain_order=True,
    )
    subset = pl.concat(
        [
            part.sample(n=min(len(part), per_stratum), seed=seed).sort("window_id")
            for part in parts
        ]
    ).sort("duration", "split", "path", "start")
    subset.write_parquet(folder / "window_split.parquet")
    preparation = {}
    for duration in DURATIONS:
        started = perf_counter()
        store = SegmentStore()
        fit_normalizer(subset.filter(pl.col("duration") == duration), store).save(
            folder / f"normalizer-{duration}s.npz"
        )
        preparation[str(duration)] = perf_counter() - started
        store.clear()
    metadata = {
        "seed": seed,
        "per_stratum": per_stratum,
        "selection": "Within existing duration/split/dataset/activity/target strata",
        "window_split_sha256": hashlib.sha256(
            (folder / "window_split.parquet").read_bytes()
        ).hexdigest(),
        "preparation_seconds": preparation,
        "subset_counts": subset.group_by("duration", "split")
        .len()
        .sort("duration", "split")
        .to_dicts(),
        "full_counts": full.group_by("duration", "split")
        .len()
        .sort("duration", "split")
        .to_dicts(),
    }
    (folder / "selection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def profile_run(
    root: Path, kind: str, duration: int, config: TrainingConfig, runtime: dict
) -> dict:
    """Exercise real loading, training, validation, checkpoints and final testing."""
    from .tinygrad_training import train_run, write_json

    folder = root / "profile"
    selection = json.loads((folder / "selection.json").read_text())
    frame = pl.read_parquet(folder / "window_split.parquet").filter(
        pl.col("duration") == duration
    )
    full = pl.read_parquet(root / "window_split.parquet").filter(
        pl.col("duration") == duration
    )
    normalizer = Normalizer.load(folder / f"normalizer-{duration}s.npz")
    store = SegmentStore()
    store.read(frame["path"][0])
    datasets = {
        split: SequenceDataset(
            frame.filter(pl.col("split") == split), normalizer, store
        )
        for split in ("train", "validation", "test")
    }
    if len(datasets["train"]) < config.batch_size:
        raise ValueError(
            "Pilot needs a full training batch; increase per_stratum or reduce batch_size"
        )
    # Three epochs separate initial schedule construction from repeat execution.
    # A pilot never early-stops before the steady epoch has been measured.
    config = replace(config, epochs=3, patience=3, inference_windows=8)
    code_sha256 = {
        name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in (
            "sequence_training_data.py",
            "tinygrad_training.py",
            "sequence_training_worker.py",
            "sequence_training_profile.py",
        )
    }
    result = train_run(
        kind,
        duration,
        datasets,
        folder / f"{duration}s" / kind,
        config,
        {"pilot": selection, "code_sha256": code_sha256},
        runtime,
        selection["preparation_seconds"][str(duration)],
    )
    result["code_sha256"] = code_sha256
    steady = result["history"][1:]
    counts = {s: full.filter(pl.col("split") == s).height for s in datasets}
    epoch_estimates = [
        h["train_seconds"] * counts["train"] / len(datasets["train"])
        + h["validation_seconds"] * counts["validation"] / len(datasets["validation"])
        + h["checkpoint_seconds"]
        for h in steady
    ]
    epoch_seconds = float(np.median(epoch_estimates))
    warmup_seconds = max(
        0.0,
        result["history"][0]["epoch_seconds"]
        - float(np.median([h["epoch_seconds"] for h in steady])),
    )
    # Final validation/test throughput is measured on the same pilot. This is
    # distinct from repeated per-epoch validation and the batch-one benchmark.
    final_seconds = result["final_evaluation_seconds"] * (
        (counts["validation"] + counts["test"])
        / (len(datasets["validation"]) + len(datasets["test"]))
    )
    result["projection"] = {
        "full_counts": counts,
        "steady_epoch_seconds": epoch_seconds,
        "observed_epoch_rate_range_seconds": [
            min(epoch_estimates),
            max(epoch_estimates),
        ],
        "initial_schedule_overhead_seconds": warmup_seconds,
        "final_evaluation_seconds": final_seconds,
        "training_30_epochs_seconds": warmup_seconds + 30 * epoch_seconds,
        "method": "Scale repeat-epoch training and validation separately by window count",
        "limits": [
            "Runtime estimates only; accuracy/F1 and stopping epoch cannot be extrapolated",
            "Two repeat epochs do not establish a statistical confidence interval",
            "Subset shard access, OS cache, thermal state and tail shapes can alter full-run rates",
            "Normalization, worker startup and final batch-one benchmarking are separate",
        ],
    }
    write_json(folder / f"{duration}s" / kind / "metrics.json", result)
    return result


def profile_table(results: list[dict]) -> pl.DataFrame:
    """Summarize measured pilot time and inferred full-data runtime in minutes."""
    return pl.DataFrame(
        [
            {
                "model": r["model"],
                "duration": r["duration_seconds"],
                "pilot_train_windows": r["counts"]["train"],
                "pilot_training_seconds": r["training_seconds"],
                "full_epoch_minutes": r["projection"]["steady_epoch_seconds"] / 60,
                "full_30_epochs_minutes": r["projection"]["training_30_epochs_seconds"]
                / 60,
                "projection_basis": "measured full loading"
                if "phase_budgets" in r["projection"]
                else "subset only: provisional",
                "worker_peak_GB": r.get("worker_memory_peak_bytes", 0) / 1e9,
            }
            for r in results
        ]
    ).sort("duration", "model")


def measure_loading(root: Path, duration: int, batch_size: int = 32) -> dict:
    """Time full-data input streaming once, without any training or model use.

    A scattered subset decodes almost one entire shard per window, whereas the
    complete dataset amortizes decoding over all selected rows in each shard.
    Measure this term rather than extrapolating it by subset window count.
    """
    folder = root / "profile"
    normalizer = Normalizer.load(folder / f"normalizer-{duration}s.npz")
    frame = pl.read_parquet(root / "window_split.parquet").filter(
        pl.col("duration") == duration
    )
    result = {"duration": duration, "batch_size": batch_size, "splits": {}}
    for split in ("train", "validation", "test"):
        store = SegmentStore()
        dataset = SequenceDataset(
            frame.filter(pl.col("split") == split), normalizer, store
        )
        started, seen = perf_counter(), 0
        for _, rows in dataset.batches(batch_size, 45 if split == "train" else None):
            seen += len(rows)
        seconds = perf_counter() - started
        result["splits"][split] = {"windows": seen, "seconds": seconds}
        store.clear()
        print(
            f"LOADING {duration}s {split}: {seen} windows / {seconds:.2f}s", flush=True
        )
    (folder / f"loading-{duration}s.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


def project_runtime(result: dict, loading: dict) -> dict:
    """Combine measured repeat-batch compute with measured full input streaming.

    The lower bound assumes effective producer/consumer overlap; the upper bound
    assumes serial I/O and compute. Neither bound is a confidence interval.
    """
    steady = result["history"][1:]
    batch_size = result["config"]["batch_size"]
    # Exclude a partial training batch when estimating full-batch throughput.
    full_batches = result["counts"]["train"] // batch_size
    if full_batches < 1:
        raise ValueError(
            "A full pilot training batch is required to estimate throughput"
        )
    train_rate = float(
        np.median(
            [seconds for h in steady for seconds in h["step_seconds"][:full_batches]]
        )
    )
    val_times = [
        seconds for h in steady for seconds in h.get("validation_forward_seconds", [])
    ]
    if not val_times:
        raise ValueError("Repeat this pilot with per-batch validation timings")
    validation_rate = float(np.median(val_times))
    budgets = {}
    for split in ("train", "validation", "test"):
        count = loading["splits"][split]["windows"]
        compute = math.ceil(count / batch_size) * (
            train_rate if split == "train" else validation_rate
        )
        io = loading["splits"][split]["seconds"]
        budgets[split] = {
            "windows": count,
            "compute_seconds": compute,
            "loading_seconds": io,
            "overlap_seconds": max(compute, io),
            "serial_seconds": compute + io,
        }
    low = sum(budgets[s]["overlap_seconds"] for s in ("train", "validation"))
    high = sum(budgets[s]["serial_seconds"] for s in ("train", "validation"))
    overhead = max(
        0.0,
        result["history"][0]["epoch_seconds"]
        - float(np.median([h["epoch_seconds"] for h in steady])),
    )
    projection = result["projection"]
    projection.pop("observed_epoch_rate_range_seconds", None)
    projection.update(
        steady_epoch_seconds=(low + high) / 2,
        epoch_overlap_to_serial_seconds=[low, high],
        phase_budgets=budgets,
        initial_schedule_overhead_seconds=overhead,
        training_30_epochs_seconds=overhead + 30 * (low + high) / 2,
        training_30_epochs_range_seconds=[overhead + 30 * low, overhead + 30 * high],
        final_evaluation_seconds=sum(
            budgets[s]["serial_seconds"] for s in ("validation", "test")
        ),
        method="Measured full input streaming plus repeat-pilot batch compute; overlap/serial bounds",
        limits=[
            "Runtime estimates only; accuracy/F1 and stopping epoch cannot be extrapolated",
            "Overlap/serial bounds are not confidence intervals; only two repeat epochs were sampled",
            "Single full input scan; OS/driver/compiler caches were not cleared",
            "Thermal state, competing workloads, shard locality and tail shapes can alter rates",
            "Normalization, worker startup and final batch-one benchmarking are separate",
        ],
    )
    return result


def refresh_projections(root: Path) -> list[dict]:
    """Update completed pilots after independent full-data loader measurements."""
    results = []
    for path in sorted((root / "profile").glob("*s/*/metrics.json")):
        result = json.loads(path.read_text())
        loading_path = root / "profile" / f"loading-{result['duration_seconds']}s.json"
        if loading_path.exists():
            result = project_runtime(result, json.loads(loading_path.read_text()))
            path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        results.append(result)
    profile_table(results).write_csv(root / "profile/comparison.csv")
    (root / "profile/results.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def compare_forward(root: Path, kind: str, duration: int) -> dict:
    """Compare uncaptured evaluation with bounded JIT on identical saved weights."""
    from tinygrad import Device, Tensor
    from tinygrad.helpers import Context
    from .tinygrad_training import ModelPredictor, load_checkpoint, write_json

    folder = root / "profile" / f"{duration}s" / kind
    model, normalizer, metadata = load_checkpoint(folder)
    frame = pl.read_parquet(root / "profile/window_split.parquet").filter(
        (pl.col("duration") == duration) & (pl.col("split") == "test")
    )
    dataset = SequenceDataset(frame, normalizer, SegmentStore())
    x, _ = next(dataset.batches(metadata["config"]["batch_size"]))
    predictor = ModelPredictor(model, metadata["config"]["recurrent_chunk_steps"])
    times, expected = {}, None
    with Context(TRAINING=0):
        for name, forward in (("uncaptured", model), ("cached", predictor)):
            samples = []
            for _ in range(4):
                Device[Device.DEFAULT].synchronize()
                started = perf_counter()
                logits = forward(Tensor(x.copy()).is_param_(False)).numpy()
                Device[Device.DEFAULT].synchronize()
                samples.append(perf_counter() - started)
                if expected is None:
                    expected = logits.copy()
                np.testing.assert_allclose(logits, expected, rtol=1e-4, atol=1e-5)
            times[name] = samples
    result = {
        "model": kind,
        "duration": duration,
        "batch_size": len(x),
        "seconds": times,
        "steady_speedup": float(
            np.median(times["uncaptured"][2:]) / np.median(times["cached"][2:])
        ),
        "scope": "Evaluation forward plus input transfer and host logits; decoding excluded",
    }
    write_json(folder / "forward_comparison.json", result)
    return result
