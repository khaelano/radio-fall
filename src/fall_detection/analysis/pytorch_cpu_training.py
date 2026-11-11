"""CPU or CUDA PyTorch training for v2 binary sequence windows."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import resource
except ImportError:  # Windows does not provide resource.getrusage.
    resource = None
from time import perf_counter

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import numpy as np
import polars as pl
import torch
from torch import nn

from .sequence_training_data import (
    Normalizer,
    SegmentStore,
    SequenceDataset,
    prefetched_batches,
)


class TorchCNN(nn.Module):
    """Two temporal convolutions and a pooled binary head, for sequence inputs."""

    def __init__(self, features: int, hidden: int) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(features, hidden, 5, padding=2)
        self.conv2 = nn.Conv1d(hidden, hidden, 3, padding=1)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = self.conv1(x.transpose(1, 2)).relu()
        return self.head(self.conv2(hidden).relu().mean(dim=2)).flatten()


class TorchLSTM(nn.Module):
    """Single-layer full-sequence LSTM with a binary head."""

    def __init__(self, features: int, hidden: int) -> None:
        super().__init__()
        self.rnn = nn.LSTM(features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        output, _ = self.rnn(x)
        return self.head(output[:, -1]).flatten()


class TorchGRU(nn.Module):
    """Single-layer full-sequence reset-after GRU with a binary head."""

    def __init__(self, features: int, hidden: int) -> None:
        super().__init__()
        self.rnn = nn.GRU(features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        output, _ = self.rnn(x)
        return self.head(output[:, -1]).flatten()


MODELS = {"cnn": TorchCNN, "lstm": TorchLSTM, "gru": TorchGRU}


@dataclass(frozen=True)
class CpuPilotConfig:
    """Training settings for PyTorch experiments."""

    seed: int = 42
    duration: int = 2
    epochs: int = 3
    batch_size: int = 32
    hidden_size: int = 64
    learning_rate: float = 0.001
    clip_norm: float = 1.0
    cpu_threads: int = 4
    patience: int = 3
    device: str = "auto"


def _rss_bytes() -> int | None:
    """Return peak resident memory on Linux, or None when unavailable."""
    if resource is None or platform.system() != "Linux":
        return None
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _cpu_name() -> str:
    """Read the host CPU model when the platform helper returns an empty name."""
    if Path("/proc/cpuinfo").is_file():
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor()


def _evaluate(
    model: nn.Module, dataset: SequenceDataset, batch_size: int, device: torch.device
) -> dict:
    model.eval()
    targets, probabilities = [], []
    started = perf_counter()
    with torch.inference_mode():
        for values, rows in prefetched_batches(dataset, batch_size):
            logits = model(torch.from_numpy(values).to(device))
            probabilities.extend(torch.sigmoid(logits).cpu().numpy().tolist())
            targets.extend(int(row["target"]) for row in rows)
    labels = np.asarray(targets, dtype=np.int8)
    predicted = np.asarray(probabilities) >= 0.5
    true_positive = int(np.count_nonzero(predicted & (labels == 1)))
    false_positive = int(np.count_nonzero(predicted & (labels == 0)))
    false_negative = int(np.count_nonzero(~predicted & (labels == 1)))
    denominator = 2 * true_positive + false_positive + false_negative
    return {
        "windows": len(labels),
        "fall_f1": 2 * true_positive / denominator if denominator else 0.0,
        "seconds": perf_counter() - started,
    }


def run_cpu_training(
    frame_path: Path,
    normalizer_path: Path,
    output: Path,
    config: CpuPilotConfig | None = None,
    *,
    expected_dataset: str | None = None,
    data_root: Path | None = None,
) -> dict:
    """Train three PyTorch models on a saved v2 split and normalizer.

    Args:
        frame_path: Saved attempt-level split with absolute segment paths.
        normalizer_path: Statistics fitted on this split's training windows.
        output: Directory for metrics and model checkpoints.
        config: Batch, model, optimization, and CPU thread settings.
        expected_dataset: Restrict a paired pilot to one named dataset.
        data_root: Rebase saved signal paths to this v2 dataset directory.

    Returns:
        Runtime and validation summaries for CNN, LSTM, and GRU.
    """
    if config is None:
        config = CpuPilotConfig()
    frame_path, normalizer_path, output = (
        frame_path.resolve(),
        normalizer_path.resolve(),
        output.resolve(),
    )
    frame = pl.read_parquet(frame_path).filter(pl.col("duration") == config.duration)
    if data_root is not None:
        root = data_root.resolve()

        def signal_path(row: dict) -> str:
            path = (root / row["dataset"] / row["signal"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Signal path escapes the dataset root")
            return str(path)

        frame = frame.with_columns(
            pl.struct("dataset", "signal")
            .map_elements(signal_path, return_dtype=pl.String)
            .alias("path")
        )
    if frame.is_empty() or not normalizer_path.is_file():
        raise ValueError("A matching split and normalizer are required")
    if set(frame["split"]) != {"train", "validation", "test"}:
        raise ValueError("Pilot selection must contain all three splits")
    if expected_dataset is not None and set(frame["dataset"]) != {expected_dataset}:
        raise ValueError(f"Expected only {expected_dataset} windows")
    normalizer = Normalizer.load(normalizer_path)
    if len(normalizer.mean) != 980:
        raise ValueError("Expected the same 980 signal features")
    if config.device not in ("auto", "cpu", "cuda"):
        raise ValueError("Device must be auto, cpu, or cuda")
    device_name = (
        ("cuda" if torch.cuda.is_available() else "cpu")
        if config.device == "auto"
        else config.device
    )
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but PyTorch cannot access an NVIDIA GPU")
    device = torch.device(device_name)
    print(
        f"Training device: {device}"
        + (f" ({torch.cuda.get_device_name(device)})" if device.type == "cuda" else ""),
        flush=True,
    )
    torch.set_num_threads(config.cpu_threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        if torch.get_num_interop_threads() != 1:
            raise
    torch.use_deterministic_algorithms(True)
    output.mkdir(parents=True, exist_ok=True)
    store = SegmentStore()
    datasets = {
        split: SequenceDataset(
            frame.filter(pl.col("split") == split), normalizer, store
        )
        for split in ("train", "validation", "test")
    }
    counts = {split: len(dataset) for split, dataset in datasets.items()}
    positives = int(datasets["train"].frame["target"].sum())
    if positives == 0 or positives == counts["train"]:
        raise ValueError("Both classes are required in training")
    positive_weight = (counts["train"] - positives) / positives
    result = {
        "schema": "pytorch_sequence_v1",
        "config": asdict(config),
        "selection_sha256": hashlib.sha256(frame_path.read_bytes()).hexdigest(),
        "normalizer_sha256": hashlib.sha256(normalizer_path.read_bytes()).hexdigest(),
        "code_sha256": {
            name: hashlib.sha256(
                (Path(__file__).parent / name).read_bytes()
            ).hexdigest()
            for name in ("pytorch_cpu_training.py", "sequence_training_data.py")
        },
        "counts": counts,
        "datasets": sorted(frame["dataset"].unique()),
        "runtime": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": str(device),
            "step_timing": (
                "cuda_event_seconds" if device.type == "cuda" else "wall_seconds"
            ),
            "cuda_version": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(device)
            if device.type == "cuda"
            else None,
            "cpu": _cpu_name(),
            "cpu_threads": torch.get_num_threads(),
            "interop_threads": torch.get_num_interop_threads(),
            "mkldnn_enabled": torch.backends.mkldnn.enabled,
            "affinity_cpus": len(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else None,
        },
        "models": {},
    }
    for kind, model_class in MODELS.items():
        random.seed(config.seed)
        np.random.seed(config.seed)
        torch.manual_seed(config.seed)
        model = model_class(1960, config.hidden_size).to(device)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
            torch.cuda.reset_peak_memory_stats(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
        criterion = nn.BCEWithLogitsLoss(
            pos_weight=torch.tensor(positive_weight, device=device)
        )
        history = []
        model_started = perf_counter()
        best_f1 = -1.0
        stale = 0
        checkpoint = output / f"{kind}-{config.duration}s.pt"
        for epoch in range(1, config.epochs + 1):
            model.train()
            started = perf_counter()
            load_wait, step_seconds, total_loss, seen = 0.0, [], 0.0, 0
            cuda_events = []
            waiting = perf_counter()
            for values, rows in prefetched_batches(
                datasets["train"], config.batch_size, config.seed + epoch
            ):
                load_wait += perf_counter() - waiting
                step_started = perf_counter()
                if device.type == "cuda":
                    start_event = torch.cuda.Event(enable_timing=True)
                    end_event = torch.cuda.Event(enable_timing=True)
                    start_event.record()
                inputs = torch.from_numpy(values).to(
                    device, non_blocking=device.type == "cuda"
                )
                labels = torch.tensor(
                    [row["target"] for row in rows], dtype=torch.float32, device=device
                )
                optimizer.zero_grad(set_to_none=True)
                loss = criterion(model(inputs), labels)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), config.clip_norm)
                optimizer.step()
                if device.type == "cuda":
                    total_loss = total_loss + loss.detach() * len(rows)
                    end_event.record()
                    cuda_events.append((start_event, end_event))
                else:
                    step_seconds.append(perf_counter() - step_started)
                    total_loss += float(loss.detach()) * len(rows)
                seen += len(rows)
                waiting = perf_counter()
            if device.type == "cuda":
                torch.cuda.synchronize(device)
                step_seconds = [
                    start.elapsed_time(end) / 1000 for start, end in cuda_events
                ]
                total_loss = float(total_loss)
            train_seconds = perf_counter() - started
            validation = _evaluate(
                model, datasets["validation"], config.batch_size, device
            )
            checkpoint_started = perf_counter()
            if validation["fall_f1"] > best_f1:
                best_f1, stale = validation["fall_f1"], 0
                torch.save(model.state_dict(), checkpoint)
            else:
                stale += 1
            checkpoint_seconds = perf_counter() - checkpoint_started
            epoch_result = {
                "epoch": epoch,
                "train_loss": total_loss / seen,
                "train_seconds": train_seconds,
                "load_wait_seconds": load_wait,
                "step_seconds": step_seconds,
                "validation_seconds": validation["seconds"],
                "validation_f1": validation["fall_f1"],
                "checkpoint_seconds": checkpoint_seconds,
                "epoch_seconds": train_seconds
                + validation["seconds"]
                + checkpoint_seconds,
            }
            history.append(epoch_result)
            print(
                f"{kind.upper()} {device.type.upper()} epoch {epoch}/{config.epochs}: "
                f"{epoch_result['epoch_seconds']:.3f}s",
                flush=True,
            )
            if stale >= config.patience:
                break
        training_seconds = perf_counter() - model_started
        model.load_state_dict(
            torch.load(checkpoint, map_location="cpu", weights_only=True)
        )
        test = _evaluate(model, datasets["test"], config.batch_size, device)
        result["models"][kind] = {
            "history": history,
            "training_seconds": training_seconds,
            "peak_rss_bytes": _rss_bytes(),
            "peak_cuda_allocated_bytes": (
                torch.cuda.max_memory_allocated(device)
                if device.type == "cuda"
                else None
            ),
            "test_windows": test["windows"],
            "test_f1": test["fall_f1"],
            "test_seconds": test["seconds"],
        }
    (output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
