"""Small Python adapters for the Rust acquisition/processing backend."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from .gateway_protocol import GatewayBatch

try:
    from ... import _radio_native as core
except ImportError:
    core = None


def require_native() -> Any:
    """Require the compiled backend before accessing live hardware."""
    if core is None:
        raise RuntimeError(
            "Rust radio backend is not built; run uv sync --extra radio --extra video"
        )
    return core


def backend_info() -> dict[str, Any]:
    """Identify the preparation implementation in immutable run metadata."""
    return {
        "backend": "rust" if core is not None else "unavailable",
        "version": core.BACKEND_VERSION if core is not None else None,
        "iq_kernel": core.simd_kernel() if core is not None else None,
        "phase_algorithm": "he20-centered-weighted-fit-v1",
    }


class NativeRecord:
    """Immutable native CSI with cheap Python context and lazy array views."""

    __slots__ = ("_native", "_context", "_block", "_views")

    def __init__(self, record: Any, context: dict[str, Any] | None = None) -> None:
        self._native = record
        self._context = context or {}
        self._block = ...
        self._views = None

    def __getattr__(self, name: str) -> Any:
        if name in self._context:
            return self._context[name]
        if name in {
            "run_id",
            "transmitter_boot_id",
            "receiver_boot_id",
            "capture_host_monotonic_ns",
            "capture_clock_uncertainty_us",
        }:
            return None
        if name == "transport":
            return ""
        return getattr(self._native, name)

    def with_context(self, updates: dict[str, Any]) -> NativeRecord:
        """Share native samples and prepared phase while adding session metadata."""
        return NativeRecord(self._native, {**self._context, **updates})

    @property
    def phase_views_ready(self) -> bool:
        return True  # The native processing worker prepared supported LTFs.

    @property
    def channel_estimate_block(self) -> SimpleNamespace | None:
        if self._block is ...:
            values = self._native.phase_bytes()
            if values is None:
                self._block = None
            else:
                indices, amplitude, raw, calibrated = values
                self._block = SimpleNamespace(
                    name="HE-LTF",
                    subcarrier_indices=tuple(indices),
                    amplitudes=np.frombuffer(amplitude, dtype="=f8"),
                    raw_phases=np.frombuffer(raw, dtype="=f8"),
                    calibrated_phases=np.frombuffer(calibrated, dtype="=f8"),
                )
        return self._block

    @property
    def ltf_blocks(self) -> tuple[SimpleNamespace, ...]:
        block = self.channel_estimate_block
        return (block,) if block is not None else ()

    def _view(self, index):
        if self._views is None:
            self._views = tuple(
                np.frombuffer(b, dtype="=f8") for b in self._native.views_bytes()
            )
        return self._views[index]

    real = property(lambda self: self._view(0))
    imaginary = property(lambda self: self._view(1))
    amplitudes = property(lambda self: self._view(2))
    phases = property(lambda self: self._view(3))


def gateway_batch(
    native: Any, processed_ns: int | None = None, encoded: bytes | None = None
) -> GatewayBatch:
    """Wrap native-validated data without re-decoding or reconstructing CSI."""
    from .gateway_protocol import GatewayBatch
    from .wire import DecodedCsiPacket, DecodedCsiDatagram, ReceiverStats

    packet = DecodedCsiPacket(
        records=tuple(
            DecodedCsiDatagram(
                NativeRecord(r, {"native_processed_ns": processed_ns}),
                r.receiver_mac,
                r.transport_sequence,
            )
            for r in native.records
        ),
        boot_id=native.receiver_boot_id,
        batch_sequence=native.batch_id,
        receiver_stats=ReceiverStats(*native.receiver_stats),
    )
    batch = GatewayBatch(
        native.run_id,
        native.transmitter_boot_id,
        native.receiver_boot_id,
        native.batch_id,
        native.receiver_mac,
        native.payload,
    )
    object.__setattr__(batch, "_decoded_packet", packet)
    object.__setattr__(batch, "_encoded", encoded)
    return batch


class PipelineStats:
    """Expose native stage and application handoff diagnostics independently."""

    def __init__(self, pipeline: Any) -> None:
        self.pipeline = pipeline
        self.capacity_bytes = 256 * 1024
        self.capacity_chunks = 256
        self.maximum_age_ns = 200_000_000

    def stats(self) -> dict[str, Any]:
        return json.loads(self.pipeline.stats_json())

    def close(self) -> None:
        pass  # Native pipeline shutdown is owned by its acquisition manager.
