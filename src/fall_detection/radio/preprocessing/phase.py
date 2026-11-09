"""Espressif CSI LTF layout and phase calibration helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Sequence

import numpy as np


# ESP-IDF serializes the 20 MHz CSI slots in this order.  The slot at zero
# and the outer guard slots are retained for alignment but are not usable
# channel estimates.
HT20_SLOT_INDICES: tuple[int, ...] = tuple(range(0, 32)) + tuple(range(-32, 0))
HT20_VALID_SUBCARRIERS: frozenset[int] = frozenset(
    index for index in range(-28, 29) if index != 0
)
# ESP32-C6 on ESP-IDF 6.1 exposes the complete 256-slot HE20 FFT in
# ascending signed-subcarrier order. Older tooling can emit a compact vector
# containing only -122..122, serialized with the non-negative half first.
HE20_SLOT_INDICES: tuple[int, ...] = tuple(range(-128, 128))
HE20_COMPACT_SLOT_INDICES: tuple[int, ...] = tuple(range(0, 123)) + tuple(
    range(-122, 0)
)
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

        # Prepare a whole LTF at once. Per-tone NumPy dispatch and Python
        # loops can otherwise stall a cold receiver switch beyond the ingestion deadline.
        values = np.asarray(self.csi, dtype=np.complex128)
        with np.errstate(invalid="ignore", over="ignore"):
            amplitudes = np.abs(values)
            phases = np.angle(values)
        usable = (
            ~np.asarray(invalid, dtype=bool)
            & np.isfinite(values.real)
            & np.isfinite(values.imag)
            & (amplitudes > 0)
            & (amplitudes >= DEFAULT_PHASE_AMPLITUDE_FLOOR)
            & np.asarray(
                [index in self.valid_subcarriers for index in self.subcarrier_indices],
                dtype=bool,
            )
        )
        phases[~usable] = np.nan
        amplitudes[~np.isfinite(amplitudes)] = np.nan
        object.__setattr__(self, "invalid_slots", tuple(invalid))
        object.__setattr__(self, "_amplitudes", tuple(map(float, amplitudes)))
        object.__setattr__(self, "_raw_phases", tuple(map(float, phases)))
        object.__setattr__(
            self,
            "_calibrated_phases",
            calibrate_phase(
                self.csi,
                self.subcarrier_indices,
                invalid_slots=invalid,
                valid_subcarriers=self.valid_subcarriers,
            ),
        )

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


def _block_layouts(
    *,
    sig_mode: int,
    bandwidth: int,
    stbc: int,
    pair_count: int,
) -> tuple[tuple[str, tuple[int, ...], frozenset[int]], ...]:
    """Return supported LTF layouts for one CSI payload."""

    if bandwidth != 0:
        return ()

    # Classic ESP32 firmware reports HT as sig_mode=1 and emits one or more
    # padded 64-slot blocks. ESP32-C6 reports HE SU as cur_bb_format=4. Current
    # firmware emits a complete 256-slot FFT; retain the older compact 245-slot
    # representation so existing recordings remain readable.
    if sig_mode == 4 and not stbc:
        if pair_count == len(HE20_SLOT_INDICES):
            return (("HE-LTF", HE20_SLOT_INDICES, HE20_VALID_SUBCARRIERS),)
        if pair_count == len(HE20_COMPACT_SLOT_INDICES):
            return (
                (
                    "HE-LTF",
                    HE20_COMPACT_SLOT_INDICES,
                    HE20_VALID_SUBCARRIERS,
                ),
            )
    if pair_count % len(HT20_SLOT_INDICES) != 0:
        return ()
    block_count = pair_count // len(HT20_SLOT_INDICES)
    if sig_mode == 1 and not stbc and block_count in (1, 2):
        names = ("LLTF", "HT-LTF")
        return tuple(
            (names[index], HT20_SLOT_INDICES, HT20_VALID_SUBCARRIERS)
            for index in range(block_count)
        )
    if sig_mode == 1 and stbc and block_count == 3:
        names = ("LLTF", "HT-LTF", "STBC-HT-LTF")
        return tuple(
            (names[index], HT20_SLOT_INDICES, HT20_VALID_SUBCARRIERS)
            for index in range(block_count)
        )
    if sig_mode != 1 and block_count == 1:
        return (("LLTF", HT20_SLOT_INDICES, HT20_VALID_SUBCARRIERS),)
    return ()


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

    Phase is unwrapped in ascending signed-subcarrier order, then a weighted
    line is fitted and removed.  Amplitude is used as the confidence weight;
    null, invalid, and weak samples are excluded from both the fit and output.
    """

    values = np.asarray(tuple(csi), dtype=np.complex128)
    indices = np.asarray(tuple(subcarrier_indices), dtype=np.float64)
    if values.shape != indices.shape:
        raise ValueError("CSI and subcarrier index lengths must match")
    invalid = np.zeros(values.shape, dtype=bool)
    if invalid_slots is not None:
        invalid = np.asarray(tuple(invalid_slots), dtype=bool)
        if invalid.shape != values.shape:
            raise ValueError("invalid-slot mask length must match CSI length")

    amplitudes = np.abs(values)
    phases = np.angle(values)
    valid = (
        ~invalid
        & np.isfinite(values.real)
        & np.isfinite(values.imag)
        & np.isfinite(amplitudes)
        & (amplitudes >= amplitude_floor)
        & np.asarray([index in valid_subcarriers for index in indices], dtype=bool)
    )
    result = np.full(values.shape, np.nan, dtype=np.float64)
    if int(valid.sum()) < 3:
        return tuple(float(value) for value in result)

    order = np.argsort(indices)
    ordered_valid = valid[order]
    valid_order = order[ordered_valid]
    valid_indices = indices[valid_order]
    valid_phases = np.unwrap(phases[valid_order])
    weights = np.maximum(amplitudes[valid_order], amplitude_floor)
    design = np.column_stack((valid_indices, np.ones(valid_indices.shape)))
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_phases = valid_phases * np.sqrt(weights)
    slope, offset = np.linalg.lstsq(weighted_design, weighted_phases, rcond=None)[0]
    residual = _wrap_phase(valid_phases - (slope * valid_indices + offset))
    result[valid_order] = residual
    return tuple(float(value) for value in result)


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
