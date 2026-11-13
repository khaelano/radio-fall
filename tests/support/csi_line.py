"""Build ``CsiRecord`` fixtures from Espressif ``CSI_DATA`` text lines."""

import json
from math import nan

from fall_detection.radio.records import CsiRecord


def record_from_csi_line(line: str) -> CsiRecord:
    """Return the record of a well-formed ``CSI_DATA`` line.

    CSI values are interleaved imaginary, real pairs. The first two values stay
    in ``raw_csi`` but become non-finite in ``csi`` when ``first_word`` is set.
    """

    fields = line.strip().split(",", 24)
    assert len(fields) == 25 and fields[0] == "CSI_DATA", line
    values = json.loads(fields[24][1:-1])
    raw = tuple(
        complex(values[index + 1], values[index]) for index in range(0, len(values), 2)
    )
    invalid = int(fields[23])
    shown = list(raw)
    if invalid:
        for index in range(min(2, len(shown))):
            shown[index] = complex(nan, nan)
    return CsiRecord(
        sequence=int(fields[1]),
        mac=fields[2].strip().lower(),
        rssi=int(fields[3]),
        noise_floor=int(fields[14]),
        timestamp_us=int(fields[18]),
        csi=tuple(shown),
        first_word_invalid=bool(invalid),
        rate=int(fields[4]),
        sig_mode=int(fields[5]),
        mcs=int(fields[6]),
        bandwidth=int(fields[7]),
        smoothing=int(fields[8]),
        not_sounding=int(fields[9]),
        aggregation=int(fields[10]),
        stbc=int(fields[11]),
        fec_coding=int(fields[12]),
        sgi=int(fields[13]),
        ampdu_count=int(fields[15]),
        channel=int(fields[16]),
        secondary_channel=int(fields[17]),
        antenna=int(fields[19]),
        sig_len=int(fields[20]),
        rx_state=int(fields[21]),
        csi_length=int(fields[22]),
        raw_csi=raw,
    )
