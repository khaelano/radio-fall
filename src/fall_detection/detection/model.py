"""Portable, hash-checked model bundles and an isolated CPU ensemble worker."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
from queue import Empty, Full
import shutil
import time

import numpy as np


def file_hash(path: Path) -> str:
    """Hash a model artifact without trusting external path names."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ModelBundle:
    """Verified weights, fixed preprocessing contract and recorded radio identities."""

    directory: Path
    metadata: dict
    mean: np.ndarray
    scale: np.ndarray

    @classmethod
    def load(cls, directory: Path) -> ModelBundle:
        """Validate the supported input contract and every used artifact hash."""
        directory = directory.resolve()
        metadata = json.loads((directory / "bundle.json").read_text())
        phase = metadata.get("representation") == "phase_change"
        channels = 16 if phase else 8
        if (
            metadata.get("schema_version") != (2 if phase else 1)
            or metadata.get("architecture", "small-cnn-v1") != "small-cnn-v1"
            or metadata.get("representation") not in {"amplitude", "phase_change"}
            or metadata.get("input_shape") != [1, channels, 100, 242]
            or metadata.get("window_seconds") != 4
            or metadata.get("bin_hz") != 25
            or len(metadata.get("receivers", [])) != 4
            or len(set(metadata.get("receivers", []))) != 4
            or len(metadata.get("checkpoints", [])) != 3
            or not 0 < metadata.get("threshold", 0) < 1
            or not 0 <= metadata.get("minimum_coverage", -1) <= 1
        ):
            raise ValueError("Unsupported four-receiver model contract")
        if phase and (
            metadata.get("normalization") != "none"
            or metadata.get("phase_preprocessing") != "calibrated-delta-sincos-v1"
            or metadata.get("lag_seconds") != 0.1
            or metadata.get("maximum_lag_seconds") != 0.15
            or metadata.get("smoothing_bins") != 1
        ):
            raise ValueError("Unsupported unscaled phase-change contract")
        required = ([metadata["normalization"]] if not phase else []) + metadata[
            "checkpoints"
        ]
        if len(set(required)) != len(required):
            raise ValueError("Duplicate model artifacts")
        for name in required:
            if Path(name).name != name or name in {".", ".."}:
                raise ValueError("Model filenames must be local basenames")
            if file_hash(directory / name) != metadata["sha256"].get(name):
                raise ValueError(f"Model artifact hash mismatch: {name}")
        if phase:
            # Identity parameters satisfy the legacy native constructor; phase
            # preprocessing rejects nonidentity parameters and never fits a scaler.
            mean = np.zeros((1, 4, 1, 242), dtype=np.float32)
            scale = np.ones_like(mean)
        else:
            with np.load(
                directory / metadata["normalization"], allow_pickle=False
            ) as scaler:
                mean = scaler["mean"].astype(np.float32)
                scale = scaler["scale"].astype(np.float32)
        if (
            mean.shape != (1, 4, 1, 242)
            or scale.shape != mean.shape
            or not np.isfinite(mean).all()
            or not np.isfinite(scale).all()
            or (scale < 0.05).any()
        ):
            raise ValueError("Invalid saved normalization")
        return cls(directory, metadata, mean, scale)

    def validate_radio(self, settings) -> None:
        """Reject different sensing profiles, transmitter or receiver/channel order."""
        expected = self.metadata["radio"]
        actual = settings.inventory
        if (
            settings.profile_fingerprint != expected["profile_fingerprint"]
            or actual.transmitter.mac.lower() != expected["transmitter_mac"].lower()
            or [(r.id, r.mac.lower()) for r in actual.receivers]
            != [
                (r, m.lower())
                for r, m in zip(
                    self.metadata["receivers"], expected["receiver_macs"], strict=True
                )
            ]
        ):
            raise ValueError(
                "Radio profile/ordered identities differ from the trained model"
            )


def export_bundle(
    experiment: Path, destination: Path, scheme: str | None = None
) -> ModelBundle:
    """Export the frozen selected ensemble without changing research artifacts."""
    experiment, destination = experiment.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(experiment):
        raise ValueError("Choose a new bundle directory outside the experiment")
    selection = json.loads((experiment / "selection.json").read_text())
    manifest = json.loads((experiment / "manifest.json").read_text())
    if file_hash(experiment / "manifest.json") != selection["manifest_sha256"]:
        raise ValueError("Experiment manifest changed after model selection")
    scheme = scheme or selection["winner"]["scheme"]
    representation = selection["selected_by_scheme"][scheme]
    phase = (
        representation == "phase_change" and selection.get("normalization") == "none"
    )
    if representation != "amplitude" and not phase:
        raise ValueError(
            "Live export requires amplitude or unscaled phase-change training"
        )
    config = selection["config"]
    if phase and (
        config.get("lag_seconds") != 0.1
        or config.get("smoothing_bins") != 1
        or config.get("normalization") != "none"
    ):
        raise ValueError("Unsupported phase preprocessing in training configuration")
    session = Path(manifest["raw_session"])
    if destination.is_relative_to(session) or session.is_relative_to(destination):
        raise ValueError("Model output overlaps the raw recording")
    if file_hash(session / "session.json") != manifest["source_sha256"]["session.json"]:
        raise ValueError("Recorded radio metadata changed after preparation")
    environment = json.loads((session / "session.json").read_text())["environment"]
    inventory = environment["radio_inventory"]
    tag = f"{scheme}__{representation}"
    normalization = "none" if phase else f"{tag}_normalization.npz"
    checkpoints = [f"{tag}_seed{seed}.pt" for seed in config["training_seeds"]]
    names = ([] if phase else [normalization]) + checkpoints
    for name in names:
        if (
            file_hash(experiment / "models" / name)
            != selection["checkpoint_sha256"][name]
        ):
            raise ValueError(f"Frozen checkpoint changed: {name}")
    metadata = dict(
        schema_version=2 if phase else 1,
        architecture="small-cnn-v1",
        representation=representation,
        scheme=scheme,
        receivers=config["receivers"],
        input_shape=[1, 16 if phase else 8, 100, 242],
        window_seconds=config["window_seconds"],
        bin_hz=config["bin_hz"],
        minimum_coverage=config["minimum_coverage"],
        threshold=selection["threshold"],
        normalization=normalization,
        checkpoints=checkpoints,
        sha256={name: file_hash(experiment / "models" / name) for name in names},
        selection_sha256=file_hash(experiment / "selection.json"),
        training_versions=selection["versions"],
        training_manifest_sha256=file_hash(experiment / "manifest.json"),
        radio=dict(
            profile_fingerprint=environment["radio_profile_fingerprint"],
            transmitter_mac=inventory["transmitter"]["mac"],
            receiver_macs=[
                next(r["mac"] for r in inventory["receivers"] if r["id"] == key)
                for key in config["receivers"]
            ],
        ),
        scope="Experimental score from one participant/session; chronology/setup confounding remains unresolved.",
    )
    if phase:
        metadata.update(
            phase_preprocessing="calibrated-delta-sincos-v1",
            lag_seconds=0.1,
            maximum_lag_seconds=0.15,
            smoothing_bins=1,
        )
    destination.mkdir(parents=True)
    for name in names:
        shutil.copy2(experiment / "models" / name, destination / name)
    (destination / "bundle.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return ModelBundle.load(destination)


def load_ensemble(bundle: ModelBundle, threads: int = 2):
    """Load the exact trained architecture on CPU; called only inside the scorer."""
    import torch
    from torch import nn

    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)

    class SmallCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.network = nn.Sequential(
                nn.Conv2d(bundle.metadata["input_shape"][1], 8, 5, stride=2, padding=2),
                nn.ReLU(),
                nn.Conv2d(8, 16, 3, stride=2, padding=1),
                nn.ReLU(),
                nn.Conv2d(16, 32, 3, stride=2, padding=1),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten(),
                nn.Dropout(0.25),
                nn.Linear(32, 1),
            )

        def forward(self, values):
            return self.network(values).squeeze(1)

    models = []
    for name in bundle.metadata["checkpoints"]:
        checkpoint = torch.load(
            bundle.directory / name, map_location="cpu", weights_only=True
        )
        if (
            checkpoint["channels"] != bundle.metadata["input_shape"][1]
            or checkpoint["representation"] != bundle.metadata["representation"]
            or (
                bundle.metadata["representation"] == "phase_change"
                and checkpoint.get("normalization") != "none"
            )
        ):
            raise ValueError("Checkpoint input contract mismatch")
        model = SmallCNN()
        model.load_state_dict(checkpoint["state_dict"], strict=True)
        models.append(model.eval())
    return models


def score_tensor(models, encoded: bytes) -> tuple[float, list[float]]:
    """Score a native-endian float32 tensor without rebuilding preprocessing."""
    import torch

    channels = models[0].network[0].in_channels
    if channels not in {8, 16} or len(encoded) != channels * 100 * 242 * 4:
        raise ValueError("Invalid native CNN tensor size")
    values = np.frombuffer(encoded, dtype="=f4")
    if values.size != channels * 100 * 242 or not np.isfinite(values).all():
        raise ValueError("Invalid native CNN tensor")
    tensor = torch.from_numpy(values.reshape(1, channels, 100, 242).copy())
    with torch.inference_mode():
        probabilities = [float(torch.sigmoid(model(tensor))[0]) for model in models]
    # Preserve the pilot's float32 ensemble reduction.
    return float(np.asarray(probabilities, dtype=np.float32).mean()), probabilities


def _score_worker(directory: str, threads: int, requests, responses) -> None:
    try:
        models = load_ensemble(ModelBundle.load(Path(directory)), threads)
        responses.put(dict(kind="ready"))
        while (job := requests.get()) is not None:
            encoded, metadata = job
            start = time.perf_counter()
            probability, seeds = score_tensor(models, encoded)
            responses.put(
                dict(
                    kind="prediction",
                    **metadata,
                    probability=probability,
                    seed_probabilities=seeds,
                    inference_ms=(time.perf_counter() - start) * 1000,
                )
            )
    except Exception as exc:
        responses.put(dict(kind="error", reason=f"{type(exc).__name__}: {exc}"))


class EnsembleWorker:
    """Bounded, nonblocking process handoff; acquisition never imports PyTorch."""

    def __init__(self, bundle: ModelBundle, threads: int = 2):
        context = mp.get_context("spawn")
        self.requests = context.Queue(maxsize=1)
        self.responses = context.Queue(maxsize=4)
        self.process = context.Process(
            target=_score_worker,
            args=(str(bundle.directory), threads, self.requests, self.responses),
            daemon=True,
            name="fall-cnn-scorer",
        )
        self.dropped = 0
        self.closed = False

    def start(self, timeout: float = 45) -> None:
        """Validate/load weights before starting radio acquisition."""
        self.process.start()
        try:
            ready = self.responses.get(timeout=timeout)
        except Empty as exc:
            self.close()
            raise RuntimeError("CNN process did not initialize before timeout") from exc
        if ready["kind"] != "ready":
            self.close()
            raise RuntimeError(ready["reason"])

    def submit(self, encoded: bytes, metadata: dict) -> bool:
        """Try to enqueue one frame; skip work rather than blocking acquisition/UI."""
        try:
            self.requests.put_nowait((encoded, metadata))
            return True
        except Full:
            self.dropped += 1
            return False

    def poll(self) -> dict | None:
        """Return the newest completed result, or a visible scorer failure."""
        latest = None
        while True:
            try:
                latest = self.responses.get_nowait()
            except Empty:
                break
        if (
            latest is None
            and not self.closed
            and self.process.pid
            and not self.process.is_alive()
        ):
            return dict(
                kind="error", reason=f"CNN process exited ({self.process.exitcode})"
            )
        return latest

    def close(self) -> None:
        """Bound shutdown even if a worker has stopped consuming requests."""
        if self.closed:
            return
        self.closed = True
        if self.process.pid:
            try:
                self.requests.put_nowait(None)
            except Full:
                pass
            self.process.join(timeout=3)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
        for queue in (self.requests, self.responses):
            queue.cancel_join_thread()
            queue.close()
