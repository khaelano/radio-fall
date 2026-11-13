"""Espressif CSI LTF layouts and phase calibration backed by the Rust kernels.

Layout selection, tone masking and per-packet phase calibration run in
``radio_signal``, the same code used by live acquisition and detection. This
module keeps the Python data types consumed by analysis and display code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

# ESP-IDF serializes the 20 MHz CSI slots in this order.  The slot at zero
# and the outer guard slots are retained for alignment but are not usable
# channel estimates.
HT20_SLOT_INDICES: tuple[int, ...] = tuple(range(32)) + tuple(range(-32, 0))
HT20_VALID_SUBCARRIERS: frozenset[int] = frozenset(
    index for index in range(-28, 29) if index != 0
)
# ESP32-C6 on ESP-IDF 6.1 exposes the complete 256-slot HE20 FFT in
# ascending signed-subcarrier order. Older tooling can emit a compact vector
# containing only -122..122, serialized with the non-negative half first.
HE20_SLOT_INDICES: tuple[int, ...] = tuple(range(-128, 128))
HE20_COMPACT_SLOT_INDICES: tuple[int, ...] = tuple(range(123)) + tuple(range(-122, 0))
HE20_VALID_SUBCARRIERS: frozenset[int] = frozenset(
    index for index in range(-122, 123) if index not in (-1, 0, 1)
)
DEFAULT_PHASE_AMPLITUDE_FLOOR = 4.0


@dataclass(frozen=True)
class LtfBlock:
    """One CSI long-training-field block in physical subcarrier order."""

    name: str
    csi: tuple[complex, ...]
    subcarrier_indices: tuple[int, ...]
    valid_subcarriers: frozenset[int]
    invalid_slots: tuple[bool, ...] = ()
    _amplitudes: tuple[float, ...] = field(init=False, repr=False)
    _raw_phases: tuple[float, ...] = field(init=False, repr=False)
    _calibrated_phases: tuple[float, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if len(self.csi) != len(self.subcarrier_indices):
            raise ValueError("CSI and subcarrier index lengths must match")
        invalid = self.invalid_slots or (False,) * len(self.csi)
        if len(invalid) != len(self.csi):
            raise ValueError("invalid-slot mask length must match CSI length")

        amplitudes, raw_phases, calibrated = _prepare_block(
            self.csi,
            self.subcarrier_indices,
            self.valid_subcarriers,
            invalid,
            DEFAULT_PHASE_AMPLITUDE_FLOOR,
        )
        object.__setattr__(self, "invalid_slots", tuple(invalid))
        object.__setattr__(self, "_amplitudes", amplitudes)
        object.__setattr__(self, "_raw_phases", raw_phases)
        object.__setattr__(self, "_calibrated_phases", calibrated)

    @property
    def amplitudes(self) -> tuple[float, ...]:
        """Return CSI magnitude, retaining invalid samples as NaN only if non-finite."""

        return self._amplitudes

    @property
    def raw_phases(self) -> tuple[float, ...]:
        """Return wrapped phase with null and invalid slots masked."""

        return self._raw_phases

    @property
    def calibrated_phases(self) -> tuple[float, ...]:
        """Return per-packet weighted linear-detrended phase."""

        return self._calibrated_phases


def _native():
    from ..native import require_native

    return require_native()


def _prepare_block(
    csi: Sequence[complex],
    indices: Sequence[int],
    valid_subcarriers: frozenset[int],
    invalid: Sequence[bool],
    amplitude_floor: float,
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    values = np.asarray(tuple(csi), dtype=np.complex128)
    buffers = _native().phase_block(
        np.ascontiguousarray(values.real).tobytes(),
        np.ascontiguousarray(values.imag).tobytes(),
        [int(index) for index in indices],
        set(valid_subcarriers),
        [bool(flag) for flag in invalid],
        float(amplitude_floor),
    )
    return tuple(
        tuple(np.frombuffer(buffer, dtype="=f8").tolist()) for buffer in buffers
    )


@lru_cache(maxsize=64)
def _block_layouts(
    *,
    sig_mode: int,
    bandwidth: int,
    stbc: int,
    pair_count: int,
) -> tuple[tuple[str, tuple[int, ...], frozenset[int]], ...]:
    """Return supported LTF layouts for one CSI payload."""
    return tuple(
        (name, tuple(indices), frozenset(valid))
        for name, indices, valid in _native().ltf_layouts(
            sig_mode, bandwidth, stbc, pair_count
        )
    )


@lru_cache(maxsize=64)
def phase_slot_mask(
    *,
    sig_mode: int,
    bandwidth: int,
    stbc: int,
    pair_count: int,
    first_word_invalid: bool = False,
) -> tuple[bool, ...]:
    """Return eligible LTF slots before masking weak or non-finite samples.

    The immutable mask uses the same layouts as ``decode_ltf_blocks`` and
    excludes null, guard, and invalid first-word slots. Unsupported layouts
    return an empty tuple. Cached masks can be broadcast over packet batches
    without calculating phase or fitting a calibration line.

    Args:
        sig_mode: ESP-IDF baseband format code.
        bandwidth: ESP-IDF bandwidth code (zero for 20 MHz).
        stbc: Space-time block coding flag.
        pair_count: Number of complex values in the payload.
        first_word_invalid: Whether the first two complex slots are invalid.

    Returns:
        One eligibility flag per serialized complex slot, or an empty tuple.
    """
    layouts = _block_layouts(
        sig_mode=sig_mode, bandwidth=bandwidth, stbc=stbc, pair_count=pair_count
    )
    mask = [index in valid for _, indices, valid in layouts for index in indices]
    if first_word_invalid:
        mask[: min(2, len(mask))] = [False] * min(2, len(mask))
    return tuple(mask)


def decode_ltf_blocks(
    csi: Sequence[complex],
    *,
    sig_mode: int,
    bandwidth: int,
    stbc: int,
    first_word_invalid: bool,
) -> tuple[LtfBlock, ...]:
    """Decode supported Espressif CSI payloads into separate LTF blocks.

    Unsupported packet layouts return an empty tuple.  The raw CSI remains
    available on ``CsiRecord`` so a new layout can be added without data loss.
    """

    values = tuple(csi)
    block_layouts = _block_layouts(
        sig_mode=sig_mode,
        bandwidth=bandwidth,
        stbc=stbc,
        pair_count=len(values),
    )
    if not block_layouts:
        return ()

    blocks: list[LtfBlock] = []
    offset = 0
    for name, subcarrier_indices, valid_subcarriers in block_layouts:
        length = len(subcarrier_indices)
        block_values = values[offset : offset + length]
        invalid = [False] * length
        if first_word_invalid and offset == 0:
            invalid[: min(2, length)] = [True] * min(2, length)
        blocks.append(
            LtfBlock(
                name=name,
                csi=block_values,
                subcarrier_indices=subcarrier_indices,
                valid_subcarriers=valid_subcarriers,
                invalid_slots=tuple(invalid),
            )
        )
        offset += length
    return tuple(blocks)


def _wrap_phase(values: np.ndarray) -> np.ndarray:
    """Wrap radians to the conventional [-pi, pi] interval."""

    return (values + np.pi) % (2.0 * np.pi) - np.pi


def calibrate_phase(
    csi: Sequence[complex],
    subcarrier_indices: Sequence[int],
    *,
    invalid_slots: Sequence[bool] | None = None,
    amplitude_floor: float = DEFAULT_PHASE_AMPLITUDE_FLOOR,
    valid_subcarriers: frozenset[int] = HT20_VALID_SUBCARRIERS,
) -> tuple[float, ...]:
    """Remove packet-wise phase offset and frequency slope.

    Phase is unwrapped in ascending signed-subcarrier order, then an
    amplitude-weighted line is fitted and removed. Null, invalid and weak
    samples are excluded from both the fit and output.

    Args:
        csi: Complex CSI in serialized order.
        subcarrier_indices: Signed subcarrier index of each value.
        invalid_slots: Optional per-value invalid flags.
        amplitude_floor: Minimum usable amplitude.
        valid_subcarriers: Physical tones eligible for calibration.

    Returns:
        Calibrated phase per value, NaN where a tone is unusable.

    Raises:
        ValueError: Lengths of CSI, indices or mask differ.
    """

    values = tuple(csi)
    if len(values) != len(tuple(subcarrier_indices)):
        raise ValueError("CSI and subcarrier index lengths must match")
    invalid = () if invalid_slots is None else tuple(invalid_slots)
    if invalid and len(invalid) != len(values):
        raise ValueError("invalid-slot mask length must match CSI length")
    return _prepare_block(
        values, subcarrier_indices, valid_subcarriers, invalid, amplitude_floor
    )[2]


def phase_change_from_baseline(
    phases: np.ndarray,
    timestamps: np.ndarray,
    *,
    window_seconds: float,
) -> np.ndarray:
    """Subtract a robust oldest-window baseline from calibrated phase.

    Subcarriers that are always invalid -- the DC/null tones and any tone that
    stays below the amplitude floor -- are NaN by construction.  Their baseline
    is left NaN and excluded from the median, so an all-NaN column no longer
    raises NumPy's "All-NaN slice" warning.  If the whole baseline window is
    NaN the output stays NaN for that window rather than inventing a baseline.
    """

    if phases.ndim != 2 or timestamps.ndim != 1 or phases.shape[0] != timestamps.size:
        raise ValueError("phase matrix and timestamps must have compatible shapes")
    if timestamps.size == 0:
        return phases.copy()
    baseline_duration = min(0.5, max(0.0, window_seconds) / 4.0)
    cutoff = timestamps[0] + baseline_duration
    baseline_rows = timestamps <= cutoff
    if not baseline_rows.any():
        baseline_rows[0] = True
    window = phases[baseline_rows]
    finite = np.isfinite(window)
    usable = finite.any(axis=0)
    baseline = np.full(phases.shape[1], np.nan, dtype=np.float64)
    if usable.any():
        baseline[usable] = np.nanmedian(window[:, usable], axis=0)
    return _wrap_phase(phases - baseline)
