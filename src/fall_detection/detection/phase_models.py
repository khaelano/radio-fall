"""Experimental simultaneous live inference for offline-trained phase models.

The bounded background worker uses rolling per-window normalization and
centered Hampel processing as an explicit approximation of offline processing.
Its three-class phase probabilities are not fall probabilities.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from pathlib import Path
from queue import Empty, Full, Queue

import numpy as np

from ..analysis.amplitude import hampel_subcarriers, normalize_subcarriers
from ..analysis.window_data import LABELS, pooled_input
from ..analysis.windows import resample_amplitude


def load_phase_models(directory: Path, threads: int = 2) -> dict:
    """Load the 12 locally trusted phase models and their preprocessing metadata."""
    import joblib
    import torch
    from torch import nn

    class Network(nn.Module):
        def __init__(self, kind, features, hidden):
            super().__init__()
            self.kind = kind
            if kind == "cnn":
                self.encoder = nn.Sequential(
                    nn.Conv1d(features, hidden, 5, padding=2),
                    nn.ReLU(),
                    nn.Conv1d(hidden, hidden, 3, padding=1),
                    nn.ReLU(),
                    nn.AdaptiveAvgPool1d(1),
                    nn.Flatten(),
                )
            else:
                self.encoder = {"lstm": nn.LSTM, "gru": nn.GRU}[kind](
                    features, hidden, batch_first=True
                )
            self.head = nn.Linear(hidden, len(LABELS))

        def forward(self, x):
            if self.kind == "cnn":
                encoded = self.encoder(x.transpose(1, 2))
            else:
                sequence, _ = self.encoder(x)
                encoded = sequence[:, -1, :]
            return self.head(encoded)

    torch.set_num_threads(threads)
    result = {}
    for duration in (2, 4, 6):
        for kind in ("cnn", "lstm", "gru", "random_forest"):
            path = directory / f"{duration}s" / kind
            with (path / "metrics.json").open() as stream:
                info = json.load(stream)
            if info["model"] != kind or info["duration_seconds"] != duration:
                raise ValueError(f"Mismatched phase model metadata: {path}")
            bins = int(info["config"]["temporal_bins"])
            if bins < 1 or bins > duration * 80:
                raise ValueError(f"Invalid temporal pooling size: {path}")
            if kind == "random_forest":
                # Only load trusted local joblib files; pickle can execute code.
                model = joblib.load(path / "model.joblib")
                if int(model.n_features_in_) != bins * 490 or not set(
                    model.classes_
                ).issubset({0, 1, 2}):
                    raise ValueError(f"Incompatible forest features or labels: {path}")
            else:
                checkpoint = torch.load(
                    path / "model.pt", map_location="cpu", weights_only=True
                )
                if (
                    checkpoint["kind"] != kind
                    or checkpoint["features"] != 490
                    or tuple(checkpoint["labels"]) != LABELS
                    or int(checkpoint["config"]["temporal_bins"]) != bins
                ):
                    raise ValueError(f"Incompatible phase checkpoint: {path}")
                model = Network(kind, checkpoint["features"], checkpoint["hidden_size"])
                model.load_state_dict(checkpoint["state_dict"], strict=True)
                model.eval()
            result[(duration, kind)] = (model, bins)
    return result


def score_phase_models(
    models: dict, duration: int, values: np.ndarray, valid: np.ndarray
) -> dict:
    """Run all models for one duration on the same processed receiver window."""
    import torch

    result = {}
    pooled = {}
    for (seconds, kind), (model, bins) in models.items():
        if seconds != duration:
            continue
        if bins not in pooled:
            pooled[bins] = pooled_input(values, valid, bins)
        x = pooled[bins]
        if kind == "random_forest":
            raw = model.predict_proba(x.reshape(1, -1))[0]
            probabilities = np.zeros(len(LABELS), dtype=float)
            probabilities[np.asarray(model.classes_, dtype=int)] = raw
        else:
            with torch.inference_mode():
                logits = model(torch.from_numpy(x).unsqueeze(0))
                probabilities = torch.softmax(logits, dim=1)[0].numpy().astype(float)
        if not np.isfinite(probabilities).all():
            raise ValueError("Non-finite phase probabilities")
        result[kind] = dict(zip(LABELS, probabilities.tolist(), strict=True))
    return result


def prepare_live_phase_window(
    times_ns: np.ndarray, amplitude: np.ndarray, end_ns: int, duration: int
) -> tuple[np.ndarray, np.ndarray]:
    """Apply shared offline operations using a completed rolling window.

    Whole-window scaling and centered filtering approximate the original
    whole-recording processing; they are not numerically equivalent to it.
    """
    start_ns = end_ns - duration * 1_000_000_000
    selected = (times_ns >= start_ns) & (times_ns <= end_ns)
    times_ns, amplitude = times_ns[selected], amplitude[selected]
    if not len(times_ns):
        return np.full((duration * 80, 245), np.nan), np.zeros(
            (duration * 80, 245), dtype=bool
        )
    order = np.argsort(times_ns, kind="stable")
    times_ns, amplitude = times_ns[order], amplitude[order]
    keep = np.r_[np.diff(times_ns) != 0, True]
    times = (times_ns[keep] - start_ns).astype(float) / 1e9
    amplitude = amplitude[keep]
    normalized, _, _ = normalize_subcarriers(amplitude)
    filtered, _ = hampel_subcarriers(normalized, times)
    # Offline windows are generated from float32 saved filtered amplitudes.
    filtered = filtered.astype(np.float32)
    grid = np.arange(duration * 80, dtype=float) / 80
    values, valid, _, _ = resample_amplitude(
        times, filtered, np.isfinite(filtered), grid, 0.025
    )
    return values.astype(np.float32), valid


class PhaseModelEngine:
    """Bounded background processing for separate receiver/phase model scores."""

    def __init__(
        self,
        model_dir: Path,
        radio: dict,
        receiver_names: list[str],
        *,
        threads: int = 2,
        grace_ms: int = 900,
        hop_ms: int = 2000,
        minimum_coverage: float = 0.7,
    ):
        self.model_dir = Path(model_dir)
        self.radio = radio
        self.receivers = {
            mac.lower(): name
            for mac, name in zip(radio["receiver_macs"], receiver_names, strict=True)
        }
        self.threads, self.grace_ns, self.hop_ns = (
            threads,
            grace_ms * 1_000_000,
            hop_ms * 1_000_000,
        )
        self.minimum_coverage = minimum_coverage
        self.queue = Queue(maxsize=4096)
        self.lock = threading.Lock()
        self.stop_event, self.ready = threading.Event(), threading.Event()
        self.generation, self.failure, self.dropped = 0, "", 0
        self.radio_ready = False
        self.results = {}
        self.absent_training_classes = {}
        self.worker = None

    def start(self) -> None:
        """Load all model files before accepting records."""
        self.models = load_phase_models(self.model_dir, self.threads)
        for duration, kind in self.models:
            metadata_path = self.model_dir / f"{duration}s" / kind / "metrics.json"
            if metadata_path.is_file():
                with metadata_path.open() as stream:
                    info = json.load(stream)
                self.absent_training_classes[(duration, kind)] = info.get(
                    "absent_training_classes", []
                )
        self.worker = threading.Thread(
            target=self._run, name="phase-model-worker", daemon=True
        )
        self.worker.start()

    def interrupt(self, reason: str) -> None:
        """Invalidate queued and in-flight scores after radio interruption."""
        with self.lock:
            self.generation += 1
            self.results.clear()

    def fail(self, reason: str) -> None:
        """Record a phase-only failure and suppress its scores."""
        with self.lock:
            self.failure = reason
            self.generation += 1
            self.results.clear()

    def on_record(self, record, arrival_ns: int) -> None:
        """Queue a native record reference without performing model work in acquisition."""
        if (
            record.mac.lower() != self.radio["transmitter_mac"].lower()
            or record.profile_fingerprint != self.radio["profile_fingerprint"]
            or record.receiver_mac.lower() not in self.receivers
            or record.rx_state != 0
        ):
            return
        timestamp = record.capture_host_monotonic_ns
        uncertainty = record.capture_clock_uncertainty_us
        if (
            timestamp is None
            or uncertainty is None
            or not math.isfinite(uncertainty)
            or uncertainty < 0
            or timestamp > arrival_ns + math.ceil(uncertainty * 1000)
            or record.run_id is None
            or record.transmitter_boot_id is None
            or record.receiver_boot_id is None
        ):
            return
        with self.lock:
            if not self.radio_ready or self.failure:
                return
            generation = self.generation
        try:
            self.queue.put_nowait((generation, record, int(timestamp), int(arrival_ns)))
        except Full:
            with self.lock:
                self.dropped += 1
                self.generation += 1
                self.results.clear()

    def _run(self) -> None:
        histories = {name: deque(maxlen=2048) for name in self.receivers.values()}
        boot_ids, run_key, active_generation, last_end = {}, None, -1, {}
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    generation = self.generation
                if generation != active_generation:
                    for history in histories.values():
                        history.clear()
                    boot_ids, run_key, last_end, active_generation = (
                        {},
                        None,
                        {},
                        generation,
                    )
                try:
                    item_generation, record, timestamp, arrival_ns = self.queue.get(
                        timeout=0.05
                    )
                except Empty:
                    record = None
                if record is not None and item_generation == active_generation:
                    receiver = self.receivers[record.receiver_mac.lower()]
                    identity = (record.run_id, record.transmitter_boot_id)
                    boot = record.receiver_boot_id
                    if run_key is not None and (
                        identity != run_key
                        or (receiver in boot_ids and boot_ids[receiver] != boot)
                    ):
                        self.interrupt("radio epoch changed")
                        continue
                    run_key, boot_ids[receiver] = identity, boot
                    block = record.channel_estimate_block
                    if block is not None:
                        indices = np.asarray(block.subcarrier_indices)
                        keep = (indices >= -122) & (indices <= 122)
                        sample = np.full(245, np.nan)
                        raw = np.asarray(block.raw_phases)[keep]
                        amp = np.asarray(block.amplitudes)[keep]
                        sample[indices[keep] + 122] = np.where(
                            np.isfinite(raw), amp, np.nan
                        )
                        histories[receiver].append((timestamp, arrival_ns, sample))
                now = time.monotonic_ns()
                end = ((now - self.grace_ns) // self.hop_ns) * self.hop_ns
                # Process only the latest due window, never backfill stale results.
                for receiver, history in histories.items():
                    if len(history) < 2:
                        continue
                    while history and history[0][0] < end - 8_000_000_000:
                        history.popleft()
                    if not history:
                        continue
                    for duration in (2, 4, 6):
                        key = (receiver, duration)
                        if last_end.get(key, 0) >= end:
                            continue
                        last_end[key] = end
                        coverage, scores = 0.0, {}
                        eligible = [
                            item for item in history if item[1] <= end + self.grace_ns
                        ]
                        if (
                            eligible
                            and min(item[0] for item in eligible)
                            <= end - duration * 1_000_000_000
                        ):
                            ts = np.asarray(
                                [item[0] for item in eligible], dtype=np.int64
                            )
                            amplitude = np.asarray([item[2] for item in eligible])
                            values, valid = prepare_live_phase_window(
                                ts, amplitude, end, duration
                            )
                            coverage = float(valid.mean())
                            if coverage >= self.minimum_coverage:
                                scores = score_phase_models(
                                    self.models, duration, values, valid
                                )
                        with self.lock:
                            if active_generation == self.generation:
                                for kind in ("cnn", "lstm", "gru", "random_forest"):
                                    self.results[(receiver, duration, kind)] = {
                                        "receiver": receiver,
                                        "duration_seconds": duration,
                                        "model": kind,
                                        "end_ns": end,
                                        "center_ns": end - duration * 500_000_000,
                                        "coverage": coverage,
                                        "absent_training_classes": self.absent_training_classes.get(
                                            (duration, kind), []
                                        ),
                                        "probabilities": scores.get(kind),
                                        "generation": active_generation,
                                    }
        except Exception as exc:  # noqa: BLE001 - report worker failures to the UI
            with self.lock:
                self.failure = f"{type(exc).__name__}: {exc}"
                self.results.clear()

    def status(self, radio_ready: bool = True) -> dict:
        """Return fresh scores; unavailable or stale results are suppressed."""
        now = time.monotonic_ns()
        with self.lock:
            if self.radio_ready and not radio_ready:
                self.generation += 1
                self.results.clear()
            self.radio_ready = radio_ready
            max_age = self.grace_ns + 2 * self.hop_ns
            results = [
                dict(item)
                for item in self.results.values()
                if radio_ready and not self.failure and now - item["end_ns"] <= max_age
            ]
            return {
                "models": results,
                "failure": self.failure,
                "dropped": self.dropped,
                "pending": self.queue.qsize(),
                "generation": self.generation,
            }

    def close(self) -> None:
        """Stop the worker with bounded wait."""
        self.interrupt("shutdown")
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=5)
