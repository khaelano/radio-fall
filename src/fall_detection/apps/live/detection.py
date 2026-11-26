"""Native detector configuration, headless runner and display buffers.

Rust owns acquisition, preprocessing and ONNX inference; this module only
encodes its configuration, checks that the native libraries and model bundles
exist, and decodes the buffers it returns for display. It imports no Qt and no
Python inference library.
"""

from __future__ import annotations

import json
import os
import signal
import sysconfig
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

# Model IDs of the live-compatible exports. The Rust bundle loader is the
# authority on families; a model whose bundle is absent fails at start.
MODELS = (
    *(
        f"{family}-{duration}s"
        for family in ("cnn", "lstm", "gru")
        for duration in (2, 4, 6)
    ),
    "tonepool_tcn-4s",
    "tiny_tcn1-4s",
    # Rust principal-component spectrum front end, then an ONNX GRU head.
    "pcspec_gru-4s",
)
DEFAULT_MODELS = ("tonepool_tcn-4s",)
DETECTOR_OUTPUT_ROOT = Path("data/experiments/detector")
DETECT_EXTRA_HINT = "install the detect extra: uv sync --extra radio --extra detect"


def runtime_library() -> Path | None:
    """Locate native ORT binaries without importing its Python binding."""
    configured = os.environ.get("ORT_DYLIB_PATH")
    if configured:
        return Path(configured)
    for directory in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib")):
        if directory:
            candidates = sorted(
                (Path(directory) / "onnxruntime/capi").glob("libonnxruntime.so*")
            )
            if candidates:
                return candidates[-1]
    return None


def plugin_library() -> Path | None:
    """Locate the separately packaged native WebGPU provider."""
    configured = os.environ.get("ORT_WEBGPU_PLUGIN")
    if configured:
        return Path(configured)
    candidates = [
        Path(directory) / "onnxruntime_ep_webgpu/libonnxruntime_providers_webgpu.so"
        for directory in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib"))
        if directory
    ]
    return next((path for path in candidates if path.is_file()), None)


def native_libraries(args: Any) -> tuple[Path, Path | None]:
    """Return the ONNX Runtime core and WebGPU plugin the detector will load.

    Args:
        args: Parsed arguments with ``ort_library``, ``webgpu_plugin`` and
            ``backend``.

    Returns:
        The core library and, when found, the WebGPU plugin.

    Raises:
        ValueError: A library the selected backend needs is missing.
    """
    core = args.ort_library or runtime_library()
    if core is None or not core.is_file():
        raise ValueError(
            "the native ONNX Runtime library was not found; "
            f"{DETECT_EXTRA_HINT}, or pass --ort-library"
        )
    plugin = args.webgpu_plugin or plugin_library()
    if args.backend == "webgpu" and (plugin is None or not plugin.is_file()):
        raise ValueError(
            "the native WebGPU provider was not found; "
            f"{DETECT_EXTRA_HINT}, pass --webgpu-plugin, or use --backend cpu"
        )
    return core, plugin


def inference_problem(args: Any) -> str | None:
    """Explain why inference cannot start, or return None when it can."""
    try:
        native_libraries(args)
    except ValueError as exc:
        return str(exc)
    return None


def model_bundle_present(model_root: Path, model: str) -> bool:
    """Report whether ``model``'s exported bundle exists under ``model_root``.

    This is a display hint only; the Rust bundle loader validates the files.
    """
    family = model.rsplit("-", 1)[0]
    folder = model_root / family
    return (folder / "manifest.json").is_file() and (folder / f"{model}.onnx").is_file()


def new_output_dir(root: Path | None) -> Path:
    """Return a fresh, not yet created run directory below ``root``."""
    stamp = datetime.now(UTC).strftime("native-%Y%m%dT%H%M%S%fZ")
    return (root or DETECTOR_OUTPUT_ROOT) / stamp


def build_config(args: Any, models: list[str] | None = None) -> dict:
    """Encode the native detector configuration; Rust owns packets and tensors.

    Each call names a new run directory below ``--output-dir`` (default
    ``data/experiments/detector``), because the backend refuses to reuse one.

    Args:
        args: Parsed ``csi-live`` arguments.
        models: Optional model selection overriding ``args.models``.

    Returns:
        JSON-serializable configuration for ``NativeDetector``.

    Raises:
        ValueError: Missing native libraries or an invalid selection or policy.
    """
    replay = getattr(args, "replay_capture", None)
    core, plugin = native_libraries(args)
    selected = list(models or args.models or ())
    if (
        not selected
        or len(set(selected)) != len(selected)
        or any(model not in MODELS for model in selected)
    ):
        raise ValueError("Select a unique nonempty subset of the sequence models")
    if args.hop_ms <= 0 or args.grace_ms < 0 or not 0 <= args.minimum_coverage <= 1:
        raise ValueError("Invalid hop, grace, or coverage policy")
    output = new_output_dir(args.output_dir)
    config = {
        "model_root": str(args.model_root.resolve()),
        "core_library": str(core.resolve()),
        "webgpu_plugin": str(plugin.resolve()) if plugin else None,
        "backend": args.backend,
        "adapter_id": args.adapter_id,
        "models": selected,
        "output_dir": str(output.resolve()),
        "hop_ms": args.hop_ms,
        "delivery_grace_ms": args.grace_ms,
        "minimum_coverage": args.minimum_coverage,
        "packet_capacity": args.packet_capacity,
    }
    if replay:
        if args.replay_speed <= 0:
            raise ValueError("--replay-speed must be positive")
        config["replay"] = {
            "captures": [str(Path(path).resolve()) for path in replay],
            "speed": args.replay_speed,
            "repeat": args.replay_repeat,
        }
        return config
    from fall_detection.radio.settings import resolve_settings

    # Resolving first fills an omitted --gateway-port from the settings file.
    settings = resolve_settings(args)
    if not args.gateway_port:
        raise ValueError("a gateway USB port is required (--gateway-port)")
    config["serial_path"] = str(args.gateway_port)
    config["radio_config"] = settings.native_radio_config()
    return config


def new_backend(config: dict) -> Any:
    """Create a ``NativeDetector`` from ``config``; nothing starts yet."""
    from fall_detection.radio.native import require_native

    native = require_native()
    if not hasattr(native, "NativeDetector"):
        raise RuntimeError("Rebuild the native extension to enable NativeDetector")
    return native.NativeDetector(json.dumps(config, allow_nan=False))


def run_headless(args: Any) -> int:
    """Print detector results as JSON lines until stopped, finished or failed.

    Args:
        args: Parsed ``csi-live`` arguments with at least one model.

    Returns:
        Process exit status.

    Raises:
        RuntimeError: The backend reported an error.
    """
    backend = new_backend(build_config(args))
    stopped = False

    def interrupt(*_):
        nonlocal stopped
        stopped = True

    previous = signal.signal(signal.SIGINT, interrupt)
    began = time.monotonic()
    try:
        backend.start()
        while not stopped and (
            args.duration is None or time.monotonic() - began < args.duration
        ):
            for row in json.loads(backend.poll(64)):
                print(json.dumps(row, allow_nan=False), flush=True)
            health = json.loads(backend.health())
            if health.get("error"):
                raise RuntimeError(health["error"])
            if health.get("state") == "finished":
                for row in json.loads(backend.poll(64)):
                    print(json.dumps(row, allow_nan=False), flush=True)
                break
            time.sleep(0.025)
        return 0
    finally:
        backend.stop()
        signal.signal(signal.SIGINT, previous)


def preview_images(
    raw: bytes, model_input: bytes, frames: int
) -> tuple[np.ndarray, np.ndarray]:
    """Decode one preview window into display images.

    Args:
        raw: Little-endian float32 magnitudes, ``[frames, 980]``.
        model_input: Little-endian float32 model input, ``[frames, 1964]``.
        frames: Window length in samples.

    Returns:
        Raw magnitudes and normalized model signals, both ``[frames, 980]`` in
        receiver-major tone order, with NaN wherever the sample was missing.

    Raises:
        ValueError: Buffer sizes do not match the window length.
    """
    magnitudes = np.frombuffer(raw, dtype="<f4")
    tensor = np.frombuffer(model_input, dtype="<f4")
    if magnitudes.size != frames * 980 or tensor.size != frames * 1964:
        raise ValueError("preview buffers do not match the window length")
    tensor = tensor.reshape(frames, 1964)
    signals = np.where(tensor[:, 980:1960] > 0.5, tensor[:, :980], np.nan)
    return magnitudes.reshape(frames, 980).copy(), signals


class StreamBuffer:
    """Rolling raw magnitudes ``[rounds, 980]`` indexed by sequence round.

    Rows are placed by round, so late or out-of-order receiver batches land in
    the correct column. A new generation (segment) clears the buffer.
    """

    def __init__(self, rounds: int = 1200) -> None:
        self.rounds = rounds
        self.data = np.full((rounds, 980), np.nan, dtype=np.float32)
        self.latest: int | None = None
        self.generation: int | None = None

    def add(
        self,
        generations: list[int],
        rounds: list[int],
        receivers: list[int],
        magnitudes: bytes,
    ) -> bool:
        """Insert rows from ``NativeDetector.stream``; return whether any changed.

        Args:
            generations: Segment generation of each row.
            rounds: Sequence round of each row.
            receivers: Receiver slot (0–3) of each row.
            magnitudes: Little-endian float32 ``[rows, 245]``.

        Returns:
            True when at least one row was stored.

        Raises:
            ValueError: Metadata and magnitude buffer lengths differ.
        """
        values = np.frombuffer(magnitudes, dtype="<f4")
        count = len(rounds)
        if values.size != count * 245 or not (
            len(generations) == len(receivers) == count
        ):
            raise ValueError("stream metadata does not match magnitudes")
        if count == 0:
            return False
        values = values.reshape(count, 245)
        generation = np.asarray(generations, dtype=np.int64)
        changes = np.flatnonzero(np.diff(generation)) + 1
        stored = False
        for part in np.split(np.arange(count), changes):
            if generation[part[0]] != self.generation:
                self.data.fill(np.nan)
                self.latest = None
                self.generation = int(generation[part[0]])
            stored |= self._place(
                np.asarray(rounds, dtype=np.int64)[part],
                np.asarray(receivers, dtype=np.int64)[part],
                values[part],
            )
        return stored

    def _place(self, rounds: np.ndarray, receivers: np.ndarray, values) -> bool:
        newest = int(rounds.max())
        if self.latest is None:
            self.latest = newest
        elif newest > self.latest:
            if newest - self.latest >= self.rounds:
                self.data.fill(np.nan)
            else:
                cleared = np.arange(self.latest + 1, newest + 1) % self.rounds
                self.data[cleared] = np.nan
            self.latest = newest
        keep = rounds > self.latest - self.rounds
        rows = (rounds[keep] % self.rounds)[:, None]
        columns = receivers[keep][:, None] * 245 + np.arange(245)
        self.data[rows, columns] = values[keep]
        return bool(keep.any())

    def image(self) -> np.ndarray:
        """Return rows ordered oldest to newest, ending at the latest round."""
        if self.latest is None:
            return self.data
        start = (self.latest + 1) % self.rounds
        return np.concatenate((self.data[start:], self.data[:start]))


def status_text(health: dict) -> str:
    """Summarize backend health for the status line."""
    if health.get("error"):
        return f"Error: {health['error']}"
    parts = [f"{health.get('source', 'gateway')}: {health.get('state', 'starting')}"]
    records = health.get("records")
    if records:
        parts.append("records " + " / ".join(str(count) for count in records))
    if health.get("segments"):
        parts.append(f"segment {health['segments']}")
    if health.get("radio_error"):
        parts.append(f"last radio error: {health['radio_error']}")
    return " · ".join(parts)
