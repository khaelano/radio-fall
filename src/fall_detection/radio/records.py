"""CSI record types and the Espressif-compatible CSV row serialization.

Two classes implement the same read-only record surface:

* ``NativeRecord`` wraps a record accepted by the Rust session. Live code and
  the collector use it; array views and phase blocks come from Rust lazily.
* ``CsiRecord`` is a pure-Python value. The session inspector rebuilds it from
  the typed frame tables and tests construct it directly. Rust records have no
  Python constructor, so the two cannot be merged without a Rust change.

``AnyCsiRecord`` names either type in annotations.
"""

from __future__ import annotations

import cmath
import json
from dataclasses import dataclass, field
from math import fsum, isfinite, nan
from types import SimpleNamespace
from typing import Any

import numpy as np

from .phase import LtfBlock, decode_ltf_blocks

CSI_HEADER = (
    "type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,"
    "aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,"
    "secondary_channel,local_timestamp,ant,sig_len,rx_state,len,first_word,data"
)


@dataclass(frozen=True)
class CsiRecord:
    """One validated CSI measurement."""

    sequence: int
    mac: str
    rssi: int
    noise_floor: int
    timestamp_us: int
    csi: tuple[complex, ...]
    receiver_mac: str = ""
    transport_sequence: int = 0
    run_id: int | None = None
    transmitter_boot_id: int | None = None
    receiver_boot_id: int | None = None
    capture_host_monotonic_ns: int | None = None
    capture_clock_uncertainty_us: float | None = None
    tx_timestamp_us: int | None = None
    rx_callback_timestamp_us: int | None = None
    first_word_invalid: bool = False
    rate: int = 0
    sig_mode: int = 0
    mcs: int = 0
    bandwidth: int = 0
    smoothing: int = 0
    not_sounding: int = 0
    aggregation: int = 0
    secondary_channel: int = 0
    stbc: int = 0
    fec_coding: int = 0
    sgi: int = 0
    ampdu_count: int = 0
    channel: int = 0
    antenna: int = 0
    sig_len: int = 0
    rx_state: int = 0
    csi_length: int = 0
    raw_csi: tuple[complex, ...] = ()
    profile_fingerprint: str = ""
    transport: str = ""
    _mean_i: float = field(init=False, repr=False, compare=False)
    _mean_q: float = field(init=False, repr=False, compare=False)
    _derived_views_cache: (
        tuple[
            tuple[float, ...], tuple[float, ...], tuple[float, ...], tuple[float, ...]
        ]
        | None
    ) = field(init=False, default=None, repr=False, compare=False)
    _ltf_blocks_cache: tuple[LtfBlock, ...] | None = field(
        init=False, default=None, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        # The compact collector monitor only needs scalar I/Q means. Keep
        # full per-subcarrier views and LTF calibration lazy so raw ingestion
        # at the configured sensing rate does not pay for visualizations that
        # are not being shown.
        real_values: list[float] = []
        imaginary_values: list[float] = []
        for value in self.csi:
            if isfinite(value.real):
                real_values.append(value.real)
            if isfinite(value.imag):
                imaginary_values.append(value.imag)
        object.__setattr__(
            self,
            "_mean_i",
            fsum(real_values) / len(real_values) if real_values else nan,
        )
        object.__setattr__(
            self,
            "_mean_q",
            fsum(imaginary_values) / len(imaginary_values) if imaginary_values else nan,
        )
        raw_csi = self.raw_csi or self.csi
        object.__setattr__(self, "raw_csi", tuple(raw_csi))

    def _derived_views(
        self,
    ) -> tuple[
        tuple[float, ...],
        tuple[float, ...],
        tuple[float, ...],
        tuple[float, ...],
    ]:
        cached = self._derived_views_cache
        if cached is not None:
            return cached

        amplitudes: list[float] = []
        phases: list[float] = []
        real: list[float] = []
        imaginary: list[float] = []
        for value in self.csi:
            real.append(value.real)
            imaginary.append(value.imag)
            amplitudes.append(abs(value))
            phases.append(
                cmath.phase(value)
                if isfinite(value.real) and isfinite(value.imag)
                else nan
            )
        cached = (
            tuple(amplitudes),
            tuple(phases),
            tuple(real),
            tuple(imaginary),
        )
        object.__setattr__(self, "_derived_views_cache", cached)
        return cached

    @property
    def mean_i(self) -> float:
        """Return the finite-sample mean in-phase component."""

        return self._mean_i

    @property
    def mean_q(self) -> float:
        """Return the finite-sample mean quadrature component."""

        return self._mean_q

    @property
    def amplitudes(self) -> tuple[float, ...]:
        """Return magnitude for each complex CSI subcarrier."""

        return self._derived_views()[0]

    @property
    def phases(self) -> tuple[float, ...]:
        """Return phase in radians for each complex CSI subcarrier."""

        return self._derived_views()[1]

    @property
    def real(self) -> tuple[float, ...]:
        """Return the in-phase component for each subcarrier."""

        return self._derived_views()[2]

    @property
    def imaginary(self) -> tuple[float, ...]:
        """Return the quadrature component for each subcarrier."""

        return self._derived_views()[3]

    @property
    def phase_views_ready(self) -> bool:
        """Return whether LTF preparation has completed without triggering work."""
        return self._ltf_blocks_cache is not None

    @property
    def ltf_blocks(self) -> tuple[LtfBlock, ...]:
        """Return decoded CSI LTF blocks, or empty for unsupported layouts."""

        cached = self._ltf_blocks_cache
        if cached is None:
            cached = decode_ltf_blocks(
                self.raw_csi,
                sig_mode=self.sig_mode,
                bandwidth=self.bandwidth,
                stbc=self.stbc,
                first_word_invalid=self.first_word_invalid,
            )
            object.__setattr__(self, "_ltf_blocks_cache", cached)
        return cached

    @property
    def htltf_block(self) -> LtfBlock | None:
        """Return the HT-LTF block used by the calibrated phase path."""

        return next(
            (block for block in self.ltf_blocks if block.name == "HT-LTF"),
            None,
        )

    @property
    def channel_estimate_block(self) -> LtfBlock | None:
        """Return the HE- or HT-LTF block used by the calibrated phase path."""

        return next(
            (
                block
                for name in ("HE-LTF", "HT-LTF")
                for block in self.ltf_blocks
                if block.name == name
            ),
            None,
        )


def format_csi_record(record: CsiRecord) -> str:
    """Serialize a record using the existing Espressif CSV schema."""

    native = getattr(record, "_native", None)
    if native is not None:
        return native.csv_line

    raw_csi = record.raw_csi or record.csi
    values: list[int] = []
    for value in raw_csi:
        values.extend((int(value.imag), int(value.real)))
    data = json.dumps(values, separators=(",", ":"))
    return (
        f"CSI_DATA,{record.sequence},{record.mac},{record.rssi},"
        f"{record.rate},{record.sig_mode},{record.mcs},{record.bandwidth},"
        f"{record.smoothing},{record.not_sounding},{record.aggregation},"
        f"{record.stbc},{record.fec_coding},{record.sgi},{record.noise_floor},"
        f"{record.ampdu_count},{record.channel},{record.secondary_channel},"
        f"{record.timestamp_us},{record.antenna},{record.sig_len},{record.rx_state},"
        f'{len(values)},{int(record.first_word_invalid)},"{data}"'
    )


class NativeRecord:
    """Immutable native CSI with cheap Python context and lazy array views."""

    __slots__ = ("_block", "_context", "_native", "_views")

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


AnyCsiRecord = CsiRecord | NativeRecord
