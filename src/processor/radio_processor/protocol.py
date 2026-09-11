"""Parsing for the Espressif-compatible ESP32 CSI CSV stream."""

from __future__ import annotations

import cmath
import json
from dataclasses import dataclass, field
from math import isfinite, nan
import re
from typing import Iterable

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
    raw_line: str = ""
    first_word_invalid: bool = False
    sig_mode: int = 0
    mcs: int = 0
    bandwidth: int = 0
    secondary_channel: int = 0
    stbc: int = 0
    csi_length: int = 0
    raw_csi: tuple[complex, ...] = ()
    _amplitudes: tuple[float, ...] = field(init=False, repr=False, compare=False)
    _phases: tuple[float, ...] = field(init=False, repr=False, compare=False)
    _real: tuple[float, ...] = field(init=False, repr=False, compare=False)
    _imaginary: tuple[float, ...] = field(init=False, repr=False, compare=False)
    _ltf_blocks: tuple[LtfBlock, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Build every cached view in one pass; the serial thread ingests about
        # 100 records/s, so four separate passes contend with the GUI thread.
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
        object.__setattr__(self, "_amplitudes", tuple(amplitudes))
        object.__setattr__(self, "_phases", tuple(phases))
        object.__setattr__(self, "_real", tuple(real))
        object.__setattr__(self, "_imaginary", tuple(imaginary))
        raw_csi = self.raw_csi or self.csi
        object.__setattr__(self, "raw_csi", tuple(raw_csi))
        object.__setattr__(
            self,
            "_ltf_blocks",
            decode_ltf_blocks(
                raw_csi,
                sig_mode=self.sig_mode,
                bandwidth=self.bandwidth,
                stbc=self.stbc,
                first_word_invalid=self.first_word_invalid,
            ),
        )

    @property
    def amplitudes(self) -> tuple[float, ...]:
        """Return magnitude for each complex CSI subcarrier."""

        return self._amplitudes

    @property
    def phases(self) -> tuple[float, ...]:
        """Return phase in radians for each complex CSI subcarrier."""

        return self._phases

    @property
    def real(self) -> tuple[float, ...]:
        """Return the in-phase component for each subcarrier."""

        return self._real

    @property
    def imaginary(self) -> tuple[float, ...]:
        """Return the quadrature component for each subcarrier."""

        return self._imaginary

    @property
    def ltf_blocks(self) -> tuple[LtfBlock, ...]:
        """Return decoded CSI LTF blocks, or empty for unsupported layouts."""

        return self._ltf_blocks

    @property
    def htltf_block(self) -> LtfBlock | None:
        """Return the HT-LTF block used by the calibrated phase path."""

        return next(
            (block for block in self._ltf_blocks if block.name == "HT-LTF"),
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
    noise_floor = _integer(fields, 14, "noise floor")
    sig_mode = _integer(fields, 5, "signal mode")
    mcs = _integer(fields, 6, "MCS")
    bandwidth = _integer(fields, 7, "bandwidth")
    secondary_channel = _integer(fields, 17, "secondary channel")
    stbc = _integer(fields, 11, "STBC")
    timestamp_us = _integer(fields, 18, "timestamp")
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

    if not isinstance(values, list) or not all(isinstance(value, int) for value in values):
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
        first_word_invalid=bool(first_word_invalid),
        sig_mode=sig_mode,
        mcs=mcs,
        bandwidth=bandwidth,
        secondary_channel=secondary_channel,
        stbc=stbc,
        csi_length=declared_length,
        raw_csi=raw_csi_values,
    )


def iter_csi_lines(lines: Iterable[str]) -> Iterable[CsiRecord]:
    """Yield valid records from a stream, ignoring non-CSI and bad lines."""

    for line in lines:
        if line.lstrip().startswith("CSI_DATA,"):
            try:
                yield parse_csi_line(line)
            except ValueError:
                continue
