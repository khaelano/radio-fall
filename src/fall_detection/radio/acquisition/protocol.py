"""Parsing for the Espressif-compatible ESP32 CSI CSV stream."""

from __future__ import annotations

import cmath
import json
from dataclasses import dataclass, field
from math import fsum, isfinite, nan
import re
from typing import Iterable, Optional

from ..preprocessing.phase import LtfBlock, decode_ltf_blocks


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
    raw_line: str = ""
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
    _derived_views_cache: Optional[
        tuple[
            tuple[float, ...],
            tuple[float, ...],
            tuple[float, ...],
            tuple[float, ...],
        ]
    ] = field(init=False, default=None, repr=False, compare=False)
    _ltf_blocks_cache: Optional[tuple[LtfBlock, ...]] = field(
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


def _integer(fields: list[str], index: int, name: str) -> int:
    try:
        return int(fields[index])
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc


def parse_csi_line(line: str) -> CsiRecord:
    """Parse and validate one CSI_DATA line.

    The layout follows Espressif's classic ESP32 CSI output. CSI values are
    interleaved imaginary, real pairs, so pair [i, r] becomes complex(r, i).
    """

    text = line.strip()
    if not text.startswith("CSI_DATA,"):
        raise ValueError("line is not CSI_DATA")

    # Only the final CSI array contains commas. Splitting the fixed prefix is
    # substantially cheaper than constructing a CSV parser for every packet.
    fields = text.split(",", 24)
    if len(fields) != 25 or fields[0] != "CSI_DATA":
        raise ValueError(f"expected 25 CSI fields, got {len(fields)}")

    sequence = _integer(fields, 1, "sequence")
    mac = fields[2].strip().lower()
    if re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", mac) is None:
        raise ValueError("invalid source MAC")

    rssi = _integer(fields, 3, "RSSI")
    rate = _integer(fields, 4, "rate")
    noise_floor = _integer(fields, 14, "noise floor")
    sig_mode = _integer(fields, 5, "signal mode")
    mcs = _integer(fields, 6, "MCS")
    bandwidth = _integer(fields, 7, "bandwidth")
    smoothing = _integer(fields, 8, "smoothing")
    not_sounding = _integer(fields, 9, "not sounding")
    aggregation = _integer(fields, 10, "aggregation")
    secondary_channel = _integer(fields, 17, "secondary channel")
    stbc = _integer(fields, 11, "STBC")
    fec_coding = _integer(fields, 12, "FEC coding")
    sgi = _integer(fields, 13, "SGI")
    ampdu_count = _integer(fields, 15, "AMPDU count")
    channel = _integer(fields, 16, "channel")
    timestamp_us = _integer(fields, 18, "timestamp")
    antenna = _integer(fields, 19, "antenna")
    sig_len = _integer(fields, 20, "signal length")
    rx_state = _integer(fields, 21, "RX state")
    declared_length = _integer(fields, 22, "CSI length")
    first_word_invalid = _integer(fields, 23, "first_word_invalid")
    if first_word_invalid not in (0, 1):
        raise ValueError("first_word_invalid must be 0 or 1")
    if not 0 <= timestamp_us <= 0xFFFFFFFF:
        raise ValueError("timestamp outside uint32 range")

    data_field = fields[24]
    if len(data_field) < 2 or data_field[0] != '"' or data_field[-1] != '"':
        raise ValueError("CSI array must be a quoted CSV field")
    try:
        values = json.loads(data_field[1:-1])
    except json.JSONDecodeError as exc:
        raise ValueError("CSI array is not valid JSON") from exc

    if not isinstance(values, list) or not all(
        isinstance(value, int) for value in values
    ):
        raise ValueError("CSI data must be an integer array")
    if declared_length != len(values):
        raise ValueError(
            f"CSI length mismatch: declared {declared_length}, received {len(values)}"
        )
    if declared_length == 0 or declared_length % 2:
        raise ValueError("CSI data must contain non-empty imaginary/real pairs")

    raw_csi_values = tuple(
        complex(values[index + 1], values[index])
        for index in range(0, declared_length, 2)
    )
    csi_values = list(raw_csi_values)
    # ESP-IDF marks the first four CSI bytes (two imaginary/real pairs) as
    # invalid when this flag is set. Keep their positions for subcarrier
    # alignment, but make them non-plottable values.
    if first_word_invalid:
        for index in range(min(2, len(csi_values))):
            csi_values[index] = complex(nan, nan)
    return CsiRecord(
        sequence=sequence,
        mac=mac,
        rssi=rssi,
        noise_floor=noise_floor,
        timestamp_us=timestamp_us,
        csi=tuple(csi_values),
        raw_line=text,
        rate=rate,
        first_word_invalid=bool(first_word_invalid),
        sig_mode=sig_mode,
        mcs=mcs,
        bandwidth=bandwidth,
        smoothing=smoothing,
        not_sounding=not_sounding,
        aggregation=aggregation,
        secondary_channel=secondary_channel,
        stbc=stbc,
        fec_coding=fec_coding,
        sgi=sgi,
        ampdu_count=ampdu_count,
        channel=channel,
        antenna=antenna,
        sig_len=sig_len,
        rx_state=rx_state,
        csi_length=declared_length,
        raw_csi=raw_csi_values,
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


def iter_csi_lines(lines: Iterable[str]) -> Iterable[CsiRecord]:
    """Yield valid records from a stream, ignoring non-CSI and bad lines."""

    for line in lines:
        if line.lstrip().startswith("CSI_DATA,"):
            try:
                yield parse_csi_line(line)
            except ValueError:
                continue
