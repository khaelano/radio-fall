"""Access to the compiled Rust radio backend."""

from __future__ import annotations

from typing import Any

try:
    from .. import _radio_native as core
except ImportError:
    core = None


def require_native() -> Any:
    """Require the compiled backend before accessing live hardware."""
    if core is None:
        raise RuntimeError("Rust radio backend is not built; run uv sync --extra radio")
    return core


def backend_info() -> dict[str, Any]:
    """Identify the preparation implementation in immutable run metadata."""
    return {
        "backend": "rust" if core is not None else "unavailable",
        "version": core.BACKEND_VERSION if core is not None else None,
        "iq_kernel": core.simd_kernel() if core is not None else None,
        "phase_algorithm": "he20-centered-weighted-fit-v1",
    }
