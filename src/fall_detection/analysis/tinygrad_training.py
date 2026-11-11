"""Binary full-sequence models, training, and synchronized tinygrad benchmarks.

The caller selects DEV=CL before importing this module. CPU is supported only
for deterministic synthetic validation; production notebook runs require CL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import gc
from importlib.metadata import version
import json
import os
from pathlib import Path
import random
import struct
from time import perf_counter

import numpy as np
import polars as pl
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from tinygrad import Device, Tensor, TinyJit, nn
from tinygrad.helpers import Context
from tinygrad.nn.optim import Adam
from tinygrad.nn.state import get_parameters, get_state_dict, load_state_dict, safe_load

from .sequence_training_data import (
    LABELS,
    Normalizer,
    SequenceDataset,
    prefetched_batches,
)


@dataclass(frozen=True)
class TrainingConfig:
    """Editable baseline settings shared by notebook model sections."""

    seed: int = 42
    epochs: int = 30
    batch_size: int = 32
    learning_rate: float = 0.001
    patience: int = 5
    hidden_size: int = 64
    clip_norm: float = 1.0
    recurrent_chunk_steps: int = 32
    micro_batch_size: int = 32
    inference_windows: int = 100

    def __post_init__(self) -> None:
        if (
            min(
                self.epochs,
                self.batch_size,
                self.patience,
                self.hidden_size,
                self.recurrent_chunk_steps,
                self.micro_batch_size,
                self.inference_windows,
            )
            < 1
        ):
            raise ValueError(
                "Epochs, batch size, patience, and hidden size must be positive"
            )
        if self.learning_rate <= 0 or self.clip_norm <= 0:
            raise ValueError("Learning rate and clipping norm must be positive")


class CNNModel:
    """Two same-length temporal convolutions and a binary linear head."""

    def __init__(self, features: int, hidden: int = 64):
        self.conv1 = nn.Conv1d(features, hidden, 5, padding=2)
        self.conv2 = nn.Conv1d(hidden, hidden, 3, padding=1)
        self.head = nn.Linear(hidden, 1)

    def __call__(self, x: Tensor) -> Tensor:
        hidden = self.conv1(x.transpose(1, 2)).relu()
        return self.head(self.conv2(hidden).relu().mean(axis=2)).reshape(-1)


class LSTMModel:
    """Single-layer LSTM with one batched input projection and full BPTT."""

    def __init__(self, features: int, hidden: int = 64):
        self.input_gates = nn.Linear(features, 4 * hidden)
        self.hidden_gates = nn.Linear(hidden, 4 * hidden)
        self.head = nn.Linear(hidden, 1)
        self.hidden_size = hidden

    def initial_state(self, batch: int, device: str) -> tuple[Tensor, ...]:
        """Create independent hidden and cell states for one batch."""
        return tuple(
            Tensor.zeros(batch, self.hidden_size, device=device) for _ in range(2)
        )

    def encode(self, x: Tensor, state: tuple[Tensor, ...]) -> tuple[Tensor, ...]:
        """Encode a bounded chunk without cutting its gradient graph."""
        projected = self.input_gates(x).contiguous()
        h, c = state
        for t in range(x.shape[1]):
            i, f, g, o = (projected[:, t] + self.hidden_gates(h)).chunk(4, dim=-1)
            c = (f.sigmoid() * c + i.sigmoid() * g.tanh()).contiguous()
            h = (o.sigmoid() * c.tanh()).contiguous()
        return h, c

    def __call__(self, x: Tensor) -> Tensor:
        """Infer over all steps with bounded forward graphs."""
        state = self.initial_state(x.shape[0], x.device)
        for start in range(0, x.shape[1], 16):
            state = self.encode(x[:, start : start + 16], state)
            Tensor.realize(*state)
            state = tuple(s.detach() for s in state)
        return self.head(state[0]).reshape(-1)


class GRUModel:
    """Single-layer reset-after GRU with full-sequence backpropagation."""

    def __init__(self, features: int, hidden: int = 64):
        self.input_gates = nn.Linear(features, 3 * hidden)
        self.hidden_gates = nn.Linear(hidden, 3 * hidden)
        self.head = nn.Linear(hidden, 1)
        self.hidden_size = hidden

    def initial_state(self, batch: int, device: str) -> tuple[Tensor, ...]:
        """Create one independent hidden state per window."""
        return (Tensor.zeros(batch, self.hidden_size, device=device),)

    def encode(self, x: Tensor, state: tuple[Tensor, ...]) -> tuple[Tensor, ...]:
        """Encode a bounded chunk without cutting its gradient graph."""
        projected = self.input_gates(x).contiguous()
        (h,) = state
        for t in range(x.shape[1]):
            ir, iz, inn = projected[:, t].chunk(3, dim=-1)
            hr, hz, hn = self.hidden_gates(h).chunk(3, dim=-1)
            reset, update = (ir + hr).sigmoid(), (iz + hz).sigmoid()
            candidate = (inn + reset * hn).tanh()
            h = ((1 - update) * candidate + update * h).contiguous()
        return (h,)

    def __call__(self, x: Tensor) -> Tensor:
        """Infer over all steps with bounded forward graphs."""
        state = self.initial_state(x.shape[0], x.device)
        for start in range(0, x.shape[1], 16):
            state = self.encode(x[:, start : start + 16], state)
            Tensor.realize(*state)
            state = tuple(s.detach() for s in state)
        return self.head(state[0]).reshape(-1)


Model = CNNModel | LSTMModel | GRUModel
MODEL_CLASSES = {"cnn": CNNModel, "lstm": LSTMModel, "gru": GRUModel}


def write_json(path: Path, value: dict | list) -> None:
    """Publish a complete JSON artifact atomically, rejecting nonfinite numbers."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def opencl_preflight() -> dict:
    """Require OpenCL device execution and a numerically correct backward pass."""
    if Device.DEFAULT.split(":")[0] != "CL":
        raise RuntimeError(
            "Set DEV=CL before importing tinygrad, then restart the kernel."
        )
    try:
        device = Device[Device.DEFAULT]
        x = Tensor([1.0, 2.0], device=Device.DEFAULT)
        loss = x.square().sum()
        loss.backward()
        np.testing.assert_allclose(loss.numpy(), 5)
        np.testing.assert_allclose(x.grad.numpy(), [2, 4])
        device.synchronize()
    except Exception as error:
        raise RuntimeError(
            "OpenCL preflight failed. On Fedora/AMD install mesa-libOpenCL.x86_64, "
            "set RUSTICL_ENABLE=radeonsi, and restart the kernel. Check GPU device "
            "access and the vendor ICD with clinfo. No backend fallback was used."
        ) from error
    return {
        "device": Device.DEFAULT,
        "device_name": device.device_name,
        "driver_version": device.driver_version,
        "tinygrad": version("tinygrad"),
        "numpy": version("numpy"),
        "polars": version("polars"),
        "scikit_learn": version("scikit-learn"),
        "rusticl_enable": os.environ.get("RUSTICL_ENABLE"),
    }


def classification_metrics(targets: np.ndarray, probabilities: np.ndarray) -> dict:
    """Report binary fall metrics at 0.5, including both class supports."""
    if len(targets) == 0 or not np.isfinite(probabilities).all():
        raise ValueError("Predictions must be nonempty and finite")
    predicted = (probabilities >= 0.5).astype(np.int8)
    return {
        "accuracy": float(accuracy_score(targets, predicted)),
        "precision": float(precision_score(targets, predicted, zero_division=0)),
        "recall": float(recall_score(targets, predicted, zero_division=0)),
        "f1": float(f1_score(targets, predicted, zero_division=0)),
        "macro_f1": float(
            f1_score(
                targets, predicted, labels=[0, 1], average="macro", zero_division=0
            )
        ),
        "balanced_accuracy": float(balanced_accuracy_score(targets, predicted)),
        "confusion_matrix": confusion_matrix(
            targets, predicted, labels=[0, 1]
        ).tolist(),
        "per_class": classification_report(
            targets,
            predicted,
            labels=[0, 1],
            target_names=LABELS,
            zero_division=0,
            output_dict=True,
        ),
    }


def binary_loss(
    logits: Tensor,
    labels: Tensor,
    positive_weight: float,
    sample_weights: Tensor | None = None,
) -> Tensor:
    """Compute BCE after a contiguous boundary, retaining the gradient graph.

    Mesa 26.2.6 / Renoir miscomputes a large fused CNN + BCE reduction. Explicit
    buffering prevents fusion without eagerly discarding the backward graph.
    """
    losses = logits.contiguous().binary_crossentropy_logits(
        labels, pos_weight=positive_weight, reduction="none"
    )
    if sample_weights is not None:
        return (losses * sample_weights).sum() / sample_weights.sum()
    return losses.mean()


class CompiledStep:
    """Replay a full BPTT schedule, checking finite gradients before updates.

    Keep a separate captured schedule for a short final batch. This preserves
    every training example without padding, dropping, or truncating sequences.
    """

    def __init__(
        self, model: Model, optimizer: Adam, positive_weight: float, clip_norm: float
    ):
        self.model, self.optimizer = model, optimizer
        self.positive_weight, self.clip_norm = positive_weight, clip_norm
        self.schedules = {}

    def __call__(self, x: np.ndarray, targets: np.ndarray) -> float:
        """Run a realized update using the schedule matching this batch shape."""
        if x.shape not in self.schedules:

            @TinyJit
            def gradients(inputs: Tensor, labels: Tensor):
                with Context(TRAINING=1):
                    self.optimizer.zero_grad()
                    loss = binary_loss(self.model(inputs), labels, self.positive_weight)
                    loss.backward()
                    grads = tuple(p.grad for p in self.optimizer.params)
                    if any(g is None for g in grads):
                        raise RuntimeError("A model parameter has no gradient")
                    norm = sum(g.square().sum() for g in grads).sqrt()
                    Tensor.realize(loss, norm, *grads)
                    return loss.detach(), norm.detach(), grads

            @TinyJit
            def update(norm: Tensor, *grads: Tensor):
                with Context(TRAINING=1):
                    factor = (self.clip_norm / (norm + 1e-12)).minimum(1.0)
                    for parameter, gradient in zip(self.optimizer.params, grads):
                        parameter.grad = gradient * factor
                    self.optimizer.step()

            self.schedules[x.shape] = (gradients, update)
        gradients, update = self.schedules[x.shape]
        loss, norm, grads = gradients(
            Tensor(x, device=Device.DEFAULT).is_param_(False),
            Tensor(targets.astype(np.float32), device=Device.DEFAULT).is_param_(False),
        )
        scalar, norm_value = float(loss.item()), float(norm.item())
        if not np.isfinite([scalar, norm_value]).all() or scalar < 0:
            raise FloatingPointError("Invalid loss or gradient norm")
        update(norm, *grads)
        return scalar


class RecurrentStep:
    """Full BPTT through recomputed chunks, with host-side gradient accumulation.

    Forward boundary states are saved as small host arrays. Reverse-mode VJPs
    propagate hidden/cell-state gradients across EVERY boundary, so chunks do
    not truncate BPTT. Only one chunk and one microbatch occupy the graph at a
    time. Clip once and perform one Adam update per effective batch.
    """

    def __init__(
        self,
        model: LSTMModel | GRUModel,
        optimizer: Adam,
        positive_weight: float,
        clip_norm: float,
        chunk_steps: int = 16,
        micro_batch_size: int = 1,
    ):
        self.model, self.optimizer = model, optimizer
        self.positive_weight, self.clip_norm = positive_weight, clip_norm
        self.chunk_steps, self.micro_batch_size = chunk_steps, micro_batch_size
        self.encoder = get_parameters([model.input_gates, model.hidden_gates])
        self.head = get_parameters(model.head)
        self.forward_cache, self.backward_cache, self.head_cache = {}, {}, {}

        @TinyJit
        def update(*gradients: Tensor):
            with Context(TRAINING=1):
                for parameter, gradient in zip(self.optimizer.params, gradients):
                    parameter.grad = gradient
                self.optimizer.step()

        self.update = update

    def gradients(
        self, x: np.ndarray, targets: np.ndarray
    ) -> tuple[float, list[np.ndarray]]:
        """Compute complete sequence gradients without an optimizer update."""
        sums = [np.zeros(p.shape, dtype=np.float64) for p in self.encoder + self.head]
        mean_loss = 0.0
        micro_size = self.micro_batch_size
        for offset in range(0, len(x), micro_size):
            part = x[offset : offset + micro_size]
            labels = targets[offset : offset + len(part)]
            weight = len(part) / len(x)
            present = len(part)
            sample_weights = np.zeros(micro_size, dtype=np.float32)
            sample_weights[:present] = 1
            if present < micro_size:
                part = np.pad(
                    part, ((0, micro_size - present), (0, 0), (0, 0))
                )
                labels = np.pad(labels, (0, micro_size - present))
            states = [
                tuple(
                    s.numpy()
                    for s in self.model.initial_state(len(part), Device.DEFAULT)
                )
            ]
            chunks = [
                part[:, t : t + self.chunk_steps].copy()
                for t in range(0, part.shape[1], self.chunk_steps)
            ]
            for chunk in chunks:
                key = chunk.shape
                if key not in self.forward_cache:

                    @TinyJit
                    def forward(inputs: Tensor, *state: Tensor):
                        result = self.model.encode(inputs, state)
                        Tensor.realize(*result)
                        return tuple(s.detach() for s in result)

                    self.forward_cache[key] = forward
                result = self.forward_cache[key](
                    Tensor(chunk), *(Tensor(s.copy()) for s in states[-1])
                )
                states.append(tuple(s.numpy().copy() for s in result))

            if len(part) not in self.head_cache:

                @TinyJit
                def head_gradient(hidden: Tensor, labels: Tensor, weights: Tensor):
                    loss = binary_loss(
                        self.model.head(hidden).reshape(-1),
                        labels,
                        self.positive_weight,
                        weights,
                    )
                    gradients = loss.gradient(hidden, *self.head)
                    Tensor.realize(loss, *gradients)
                    return loss.detach(), gradients

                self.head_cache[len(part)] = head_gradient
            loss, gradients = self.head_cache[len(part)](
                Tensor(states[-1][0].copy()),
                Tensor(labels.astype(np.float32)),
                Tensor(sample_weights),
            )
            scalar = float(loss.item())
            if not np.isfinite(scalar) or scalar < 0:
                raise FloatingPointError("Invalid recurrent loss")
            mean_loss += weight * scalar
            carry = [gradients[0].numpy().copy()]
            carry.extend(np.zeros_like(s) for s in states[-1][1:])
            for dest, gradient in zip(sums[len(self.encoder) :], gradients[1:]):
                dest += weight * gradient.numpy()

            for chunk, state in reversed(list(zip(chunks, states[:-1]))):
                key = chunk.shape
                count = len(state)
                if key not in self.backward_cache:

                    @TinyJit
                    def backward(inputs: Tensor, *boundaries: Tensor):
                        initial, seeds = boundaries[:count], boundaries[count:]
                        result = self.model.encode(inputs, initial)
                        objective = sum(
                            (s * seed).sum() for s, seed in zip(result, seeds)
                        )
                        grads = objective.gradient(*initial, *self.encoder)
                        Tensor.realize(*grads)
                        return grads

                    self.backward_cache[key] = backward
                gradients = self.backward_cache[key](
                    Tensor(chunk),
                    *(Tensor(s.copy()) for s in state),
                    *(Tensor(g.copy()) for g in carry),
                )
                carry = [g.numpy().copy() for g in gradients[:count]]
                for dest, gradient in zip(sums[: len(self.encoder)], gradients[count:]):
                    dest += weight * gradient.numpy()
        return mean_loss, [g.astype(np.float32) for g in sums]

    def __call__(self, x: np.ndarray, targets: np.ndarray) -> float:
        """Accumulate full gradients, check them, clip, and update once."""
        loss, gradients = self.gradients(x, targets)
        norm = float(
            np.sqrt(sum(np.square(g.astype(np.float64)).sum() for g in gradients))
        )
        if not np.isfinite(norm):
            raise FloatingPointError("Nonfinite recurrent gradient norm")
        factor = min(1.0, self.clip_norm / (norm + 1e-12))
        self.update(*(Tensor(g * factor) for g in gradients))
        return loss


def make_training_step(
    model: Model, optimizer: Adam, positive_weight: float, config: TrainingConfig
) -> CompiledStep | RecurrentStep:
    """Choose CNN capture or bounded full-sequence recurrent differentiation."""
    if isinstance(model, (LSTMModel, GRUModel)):
        return RecurrentStep(
            model,
            optimizer,
            positive_weight,
            config.clip_norm,
            config.recurrent_chunk_steps,
            config.micro_batch_size,
        )
    return CompiledStep(model, optimizer, positive_weight, config.clip_norm)


class ModelPredictor:
    """Reuse shape-specific forward schedules, bounding recurrent graphs.

    Chunk schedules are independent of sequence duration. They replay live model
    weights after every optimizer update; no probability cache is retained.
    """

    def __init__(self, model: Model, chunk_steps: int = 32) -> None:
        self.model, self.chunk_steps = model, chunk_steps
        self.schedules = {}
        self.head = TinyJit(lambda h: model.head(h).reshape(-1).realize())

    def __call__(self, x: Tensor) -> Tensor:
        """Return realized logits for every complete input window."""
        with Context(TRAINING=0):
            if isinstance(self.model, CNNModel):
                if x.shape not in self.schedules:
                    self.schedules[x.shape] = TinyJit(lambda v: self.model(v).realize())
                return self.schedules[x.shape](x)
            # JIT signatures include DETACH views. Match the representation of
            # replayed chunk outputs even at a fresh window's zero boundary.
            state = tuple(s.realize().detach() for s in
                          self.model.initial_state(x.shape[0], x.device))
            for start in range(0, x.shape[1], self.chunk_steps):
                chunk = x[:, start : start + self.chunk_steps].contiguous().realize()
                if chunk.shape not in self.schedules:
                    @TinyJit
                    def encode(inputs: Tensor, *boundary: Tensor):
                        result = self.model.encode(inputs, boundary)
                        Tensor.realize(*result)
                        return tuple(s.detach() for s in result)
                    self.schedules[chunk.shape] = encode
                state = self.schedules[chunk.shape](chunk, *state)
            return self.head(state[0])


def evaluate_model(
    model: Model, dataset: SequenceDataset, batch_size: int,
    predictor: ModelPredictor | None = None,
) -> tuple[dict, pl.DataFrame]:
    """Return metrics and identity-preserving predictions in evaluation order."""
    rows, forward_seconds = [], []
    predictor = predictor or ModelPredictor(model)
    with Context(TRAINING=0):
        for x, metadata in prefetched_batches(dataset, batch_size):
            present = len(x)
            if present < batch_size:
                x = np.pad(x, ((0, batch_size - present), (0, 0), (0, 0)))
            started = perf_counter()
            probabilities = (
                predictor(Tensor(x, device=Device.DEFAULT).is_param_(False))
                .sigmoid()
                .numpy()
            )
            forward_seconds.append(perf_counter() - started)
            rows.extend(
                dict(row, probability=float(p), prediction=int(p >= 0.5))
                for row, p in zip(metadata, probabilities[:present])
            )
    predictions = pl.DataFrame(rows)
    metrics = classification_metrics(
        predictions["target"].to_numpy(), predictions["probability"].to_numpy()
    )
    metrics["forward_batch_seconds"] = forward_seconds
    continuous = predictions.filter(pl.col("dataset") == "continuous_non_fall")
    metrics["continuous_non_fall"] = {
        "windows": len(continuous),
        "false_positives": int(continuous["prediction"].sum()),
        "false_positive_proportion": float(continuous["prediction"].mean())
        if len(continuous)
        else None,
    }
    return metrics, predictions


def save_checkpoint(model: Model, path: Path) -> None:
    """Publish standalone float32 safetensors weights."""
    temporary = path.with_name(path.name + ".tmp")
    # tinygrad 0.14 safe_save creates CPU tensors for its header, requiring clang
    # even for CL-only training. Write the standard F32 container through NumPy;
    # tinygrad's safe_load remains the independent checkpoint reader.
    arrays = {
        key: np.ascontiguousarray(value.numpy(), dtype="<f4")
        for key, value in get_state_dict(model).items()
    }
    header, offset = {}, 0
    for key, value in arrays.items():
        header[key] = {
            "dtype": "F32",
            "shape": list(value.shape),
            "data_offsets": [offset, offset + value.nbytes],
        }
        offset += value.nbytes
    encoded = json.dumps(header, separators=(",", ":")).encode()
    encoded += b" " * (-len(encoded) % 8)
    with temporary.open("wb") as stream:
        stream.write(struct.pack("<Q", len(encoded)))
        stream.write(encoded)
        for value in arrays.values():
            stream.write(value.tobytes())
    os.replace(temporary, path)


def load_checkpoint(folder: Path) -> tuple[Model, Normalizer, dict]:
    """Reconstruct a binary model and its input contract from a saved run."""
    metadata = json.loads((folder / "config.json").read_text())
    model = MODEL_CLASSES[metadata["model"]](
        metadata["features"], metadata["config"]["hidden_size"]
    )
    load_state_dict(model, safe_load(folder / "model.safetensors"), verbose=False)
    return model, Normalizer.load(folder / "normalizer.npz"), metadata


def benchmark_inference(
    model: Model, dataset: SequenceDataset, limit: int = 100
) -> dict:
    """Time batch-one forward and transfer-inclusive latency after five warmups.

    Input decoding and normalization occur outside the timed region. Timings
    include host dispatch and OpenCL synchronization; they are not kernel-only.
    """
    frame = dataset.frame.sort("window_id")
    positions = np.linspace(0, len(frame) - 1, min(limit, len(frame)), dtype=int)
    samples = SequenceDataset(
        frame[positions.tolist()], dataset.normalizer, dataset.store
    )
    device = Device[Device.DEFAULT]
    resident_times, transfer_times, ids = [], [], []
    first_call = None
    # Explicit replay prevents lazy evaluation from reusing an already-realized
    # result when warm-up calls receive the same resident input buffer.
    forward = ModelPredictor(model)
    with Context(TRAINING=0):
        for x, rows in samples.batches(1):
            resident = Tensor(x, device=Device.DEFAULT).is_param_(False).realize()
            device.synchronize()
            if first_call is None:
                started = perf_counter()
                forward(resident)
                device.synchronize()
                first_call = (perf_counter() - started) * 1000
                for _ in range(5):
                    forward(resident)
                device.synchronize()
            device.synchronize()
            started = perf_counter()
            forward(resident)
            device.synchronize()
            resident_times.append((perf_counter() - started) * 1000)
            device.synchronize()
            started = perf_counter()
            forward(Tensor(x, device=Device.DEFAULT).is_param_(False)).sigmoid().numpy()
            device.synchronize()
            transfer_times.append((perf_counter() - started) * 1000)
            ids.append(rows[0]["window_id"])

    def summary(values: list[float]) -> dict:
        return {
            "mean_ms": float(np.mean(values)),
            "median_ms": float(np.median(values)),
            "p95_ms": float(np.percentile(values, 95)),
        }

    return {
        "batch_size": 1,
        "windows": len(ids),
        "window_ids": ids,
        "warmup_calls": 5,
        "first_batch_one_call_ms": first_call,
        "device_resident_forward": summary(resident_times),
        "input_transfer_to_host_probability": summary(transfer_times),
    }


def smoke_models(
    features: int, steps: int = 576, batch_size: int = 1, hidden: int = 64
) -> list[dict]:
    """Check every full-length architecture, gradient update, and finite output."""
    if Device.DEFAULT.split(":")[0] == "CL":
        from .sequence_training_worker import MEMORY_LIMIT, verify_memory_limit

        verify_memory_limit(MEMORY_LIMIT)
    reports = []
    for name, model_class in MODEL_CLASSES.items():
        Tensor.manual_seed(42)
        model = model_class(features, hidden)
        parameters = get_parameters(model)
        optimizer = Adam(parameters, lr=0.001)
        x = (
            np.random.default_rng(42)
            .normal(size=(batch_size, steps, features))
            .astype(np.float32)
        )
        targets = np.arange(batch_size) % 2
        before = parameters[-1].numpy().copy()
        started = perf_counter()
        predictor = ModelPredictor(model)
        reference_logits = predictor(Tensor(x, device=Device.DEFAULT)).numpy()
        expected_loss = float(
            (np.logaddexp(0, reference_logits) - targets * reference_logits).mean()
        )
        step = make_training_step(
            model, optimizer, 1.0, TrainingConfig(
                hidden_size=hidden, batch_size=batch_size,
                micro_batch_size=min(batch_size, 32),
            )
        )
        loss = step(x, targets)
        np.testing.assert_allclose(loss, expected_loss, rtol=1e-4, atol=1e-5)
        output = predictor(Tensor(x, device=Device.DEFAULT).is_param_(False)).numpy()
        if output.shape != (batch_size,) or not np.isfinite(output).all():
            raise RuntimeError(f"{name}: invalid output")
        if np.array_equal(before, parameters[-1].numpy()):
            raise RuntimeError(f"{name}: optimizer did not update the head")
        reports.append(
            {
                "model": name,
                "steps": steps,
                "batch_size": batch_size,
                "loss": loss,
                "numpy_loss": expected_loss,
                "seconds": perf_counter() - started,
            }
        )
        print(f"Smoke {name}: {reports[-1]}", flush=True)
        del model, optimizer, parameters, step, predictor
        gc.collect()
    return reports


def train_run(
    kind: str,
    duration: int,
    datasets: dict[str, SequenceDataset],
    output: Path,
    config: TrainingConfig,
    provenance: dict,
    runtime: dict,
    preparation_seconds: float,
) -> dict:
    """Train, select on validation F1, restore, benchmark, and evaluate once."""
    if Device.DEFAULT.split(":")[0] == "CL":
        from .sequence_training_worker import MEMORY_LIMIT, verify_memory_limit

        verify_memory_limit(MEMORY_LIMIT)
    output.mkdir(parents=True, exist_ok=True)
    random.seed(config.seed)
    np.random.seed(config.seed)
    Tensor.manual_seed(config.seed)
    normalizer = datasets["train"].normalizer
    features = len(normalizer.mean) * 2
    model = MODEL_CLASSES[kind](features, config.hidden_size)
    optimizer = Adam(get_parameters(model), lr=config.learning_rate)
    counts = datasets["train"].frame["target"].value_counts()
    by_class = dict(zip(counts["target"], counts["count"]))
    positive_weight = by_class[0] / by_class[1]
    step = make_training_step(model, optimizer, positive_weight, config)
    predictor = ModelPredictor(model, config.recurrent_chunk_steps)
    metadata = {
        "schema": "tinygrad_binary_sequence_v1",
        "model": kind,
        "duration_seconds": duration,
        "features": features,
        "steps": duration * 96,
        "labels": LABELS,
        "config": asdict(config),
        "positive_weight": positive_weight,
        "threshold": 0.5,
        "input": "log1p squared_difference; train-only feature standardization; validity channels",
        "runtime": runtime,
        "provenance": provenance,
    }
    write_json(output / "config.json", metadata)
    normalizer.save(output / "normalizer.npz")
    coordinates = datasets["train"].store.coordinates
    if coordinates is not None:
        np.savez(
            output / "coordinates.npz",
            receivers=coordinates[0],
            subcarriers=coordinates[1],
        )
    history, best, stale, best_epoch = [], -1.0, 0, None
    checkpoint = output / "model.safetensors"
    started = perf_counter()
    write_json(output / "status.json", {"status": "training"})
    try:
        for epoch in range(1, config.epochs + 1):
            epoch_start = perf_counter()
            total_loss, seen = 0.0, 0
            step_seconds, load_wait_seconds = [], 0.0
            waiting = perf_counter()
            for batch, rows in prefetched_batches(
                datasets["train"], config.batch_size, config.seed + epoch
            ):
                load_wait_seconds += perf_counter() - waiting
                step_started = perf_counter()
                loss = step(batch, np.asarray([r["target"] for r in rows]))
                Device[Device.DEFAULT].synchronize()
                step_seconds.append(perf_counter() - step_started)
                total_loss += loss * len(rows)
                seen += len(rows)
                waiting = perf_counter()
            train_seconds = perf_counter() - epoch_start
            validation_started = perf_counter()
            validation, _ = evaluate_model(
                model, datasets["validation"], config.batch_size, predictor
            )
            validation_seconds = perf_counter() - validation_started
            history.append(
                {
                    "epoch": epoch,
                    "train_loss": total_loss / seen,
                    "validation_f1": validation["f1"],
                    "validation_accuracy": validation["accuracy"],
                    "validation_precision": validation["precision"],
                    "validation_recall": validation["recall"],
                    "epoch_seconds": perf_counter() - epoch_start,
                    "train_seconds": train_seconds,
                    "load_wait_seconds": load_wait_seconds,
                    "step_seconds": step_seconds,
                    "validation_seconds": validation_seconds,
                    "validation_forward_seconds": validation["forward_batch_seconds"],
                }
            )
            checkpoint_started = perf_counter()
            if validation["f1"] > best:
                best, stale, best_epoch = validation["f1"], 0, epoch
                save_checkpoint(model, checkpoint)
            else:
                stale += 1
            history[-1]["checkpoint_seconds"] = perf_counter() - checkpoint_started
            history[-1]["epoch_seconds"] = perf_counter() - epoch_start
            # Nested per-step measurements are retained in metrics.json.
            pl.DataFrame(history).drop(
                "step_seconds", "validation_forward_seconds"
            ).write_csv(output / "history.csv")
            print(
                f"{kind.upper()} {duration}s epoch {epoch}/{config.epochs}: "
                f"loss={total_loss / seen:.4f} val F1={validation['f1']:.4f} "
                f"({history[-1]['epoch_seconds']:.1f}s)",
                flush=True,
            )
            if stale >= config.patience:
                break
        Device[Device.DEFAULT].synchronize()
        training_seconds = perf_counter() - started
        del model, optimizer, step, predictor
        gc.collect()
        model, _, _ = load_checkpoint(output)
        predictor = ModelPredictor(model, config.recurrent_chunk_steps)
        evaluation_started = perf_counter()
        timing = benchmark_inference(model, datasets["test"], config.inference_windows)
        inference_benchmark_seconds = perf_counter() - evaluation_started
        evaluation_started = perf_counter()
        validation, val_predictions = evaluate_model(
            model, datasets["validation"], config.batch_size, predictor
        )
        test, test_predictions = evaluate_model(
            model, datasets["test"], config.batch_size, predictor
        )
        val_predictions.write_parquet(output / "validation_predictions.parquet")
        test_predictions.write_parquet(output / "test_predictions.parquet")
        result = {
            "model": kind,
            "duration_seconds": duration,
            "best_epoch": best_epoch,
            "epochs_run": len(history),
            "config": asdict(config),
            "history": history,
            "counts": {key: len(value) for key, value in datasets.items()},
            "preparation_seconds": preparation_seconds,
            "training_seconds": training_seconds,
            "final_evaluation_seconds": perf_counter() - evaluation_started,
            "inference_benchmark_seconds": inference_benchmark_seconds,
            "inference": timing,
            "validation": validation,
            "test": test,
        }
        write_json(output / "metrics.json", result)
        write_json(output / "status.json", {"status": "complete"})
        return result
    except BaseException as error:
        write_json(
            output / "status.json",
            {
                "status": "failed",
                "error": repr(error),
                "elapsed_seconds": perf_counter() - started,
            },
        )
        raise
    finally:
        gc.collect()


def comparison_table(results: list[dict]) -> pl.DataFrame:
    """Build the requested comparison with explicit timing units."""
    if not results:
        raise ValueError("Run at least one model section first")
    return pl.DataFrame(
        [
            {
                "model": r["model"],
                "window_seconds": r["duration_seconds"],
                **{
                    f"test_{metric}": r["test"][metric]
                    for metric in (
                        "accuracy",
                        "precision",
                        "recall",
                        "f1",
                        "macro_f1",
                        "balanced_accuracy",
                    )
                },
                "validation_f1": r["validation"]["f1"],
                "training_seconds": r["training_seconds"],
                "inference_median_ms": r["inference"]["device_resident_forward"][
                    "median_ms"
                ],
                "inference_p95_ms": r["inference"]["device_resident_forward"]["p95_ms"],
                "transfer_inclusive_median_ms": r["inference"][
                    "input_transfer_to_host_probability"
                ]["median_ms"],
                "continuous_false_positive_proportion": r["test"][
                    "continuous_non_fall"
                ]["false_positive_proportion"],
                "best_epoch": r["best_epoch"],
            }
            for r in results
        ]
    ).sort("window_seconds", "model")


def plot_results(results: list[dict], output: Path) -> None:
    """Save and display learning curves and correctly labeled confusion matrices."""
    import matplotlib.pyplot as plt

    for result in results:
        fig, axes = plt.subplots(1, 3, figsize=(13, 3.5))
        history = result["history"]
        epochs = [r["epoch"] for r in history]
        axes[0].plot(epochs, [r["train_loss"] for r in history])
        axes[0].set(xlabel="Epoch", ylabel="Training BCE loss")
        axes[1].plot(epochs, [r["validation_f1"] for r in history])
        axes[1].set(xlabel="Epoch", ylabel="Validation fall F1", ylim=(0, 1))
        matrix = np.asarray(result["test"]["confusion_matrix"])
        axes[2].imshow(matrix, cmap="Blues")
        axes[2].set(
            xticks=[0, 1],
            xticklabels=LABELS,
            yticks=[0, 1],
            yticklabels=LABELS,
            xlabel="Predicted",
            ylabel="Actual",
        )
        for (i, j), value in np.ndenumerate(matrix):
            axes[2].text(j, i, str(value), ha="center", va="center")
        fig.suptitle(f"{result['model'].upper()} — {result['duration_seconds']} s")
        fig.tight_layout()
        fig.savefig(
            output / f"{result['model']}-{result['duration_seconds']}s.png", dpi=140
        )
        plt.show()
        plt.close(fig)
