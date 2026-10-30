from __future__ import annotations

import numpy as np
import pytest

from fall_detection.radio.acquisition.buffer import RollingCsiBuffer
from fall_detection.radio.acquisition.protocol import (
    CSI_HEADER,
    CsiRecord,
    format_csi_record,
)
from fall_detection.radio.preprocessing.phase import (
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HT20_SLOT_INDICES,
)
from fall_detection.session_inspector.data import (
    MAX_PLOT_RECORDS,
    AttemptData,
    TableData,
    _vectorized_snapshot,
    csi_record_for_table_row,
    csi_value_rows,
    downsample_indices,
    load_attempt_data,
    load_attempt_data_for_ui,
    prepare_attempt_signals,
)
from fall_detection.session_inspector.models import load_session


def test_attempt_data_preserves_exact_rows_and_reports_bad_csi(session_factory):
    root = session_factory(attempts=((1, 1, "accepted"),))
    csi_path = next(root.glob("trials/*/attempt_*/receivers/rx-1/csi.csv"))
    record = CsiRecord(
        sequence=10,
        mac="00:11:22:33:44:55",
        rssi=-50,
        noise_floor=-95,
        timestamp_us=1_000,
        csi=(complex(3, 4), complex(-2, 1)),
    )
    csi_path.write_text(
        CSI_HEADER + "\n" + format_csi_record(record) + "\nCSI_DATA,bad\n",
        encoding="utf-8",
    )
    session = load_session(root)

    data = load_attempt_data(session.attempts[0], "rx-1")

    assert data.csi.row_count == 2
    assert len(data.records) == 1
    assert data.record_row_indices == (0,)
    assert data.snapshot is None
    assert data.prepared_frame is None
    assert any("expected 25 CSI fields" in warning for warning in data.warnings)
    values = csi_value_rows(data.records[0])
    assert values[0].real == 3
    assert values[0].imaginary == 4
    assert values[0].amplitude == 5

    prepared = prepare_attempt_signals(data)
    assert prepared.snapshot is not None
    assert prepared.snapshot.timestamps == (0.0,)
    assert prepared.prepared_frame is not None

    compact = load_attempt_data_for_ui(session.attempts[0], "rx-1")
    assert compact.records == ()
    assert compact.record_count == 1
    restored = csi_record_for_table_row(compact, 0)
    assert restored is not None
    assert restored.csi == record.csi


def test_downsample_indices_preserves_endpoints():
    indices = downsample_indices(10_000, maximum=100)

    assert len(indices) == 100
    assert indices[0] == 0
    assert indices[-1] == 9_999
    assert indices == tuple(sorted(set(indices)))


def _record(
    sequence: int,
    layout: tuple[int, ...],
    *,
    sig_mode: int,
    stbc: int = 0,
    blocks: int = 1,
    first_word_invalid: bool = False,
) -> CsiRecord:
    raw = tuple(
        complex(
            12.0 * np.cos(index * 0.071 + sequence * 0.03),
            12.0 * np.sin(index * 0.071 + sequence * 0.03),
        )
        for index in range(len(layout) * blocks)
    )
    # Exercise the amplitude-floor mask as well as ESP-IDF's invalid prefix.
    raw = (*raw[:7], complex(1.0, 1.0), *raw[8:])
    plotted = list(raw)
    if first_word_invalid:
        plotted[:2] = [complex(np.nan, np.nan)] * 2
    return CsiRecord(
        sequence=sequence,
        mac="00:11:22:33:44:55",
        rssi=-50 - sequence,
        noise_floor=-95,
        timestamp_us=1_000 + sequence * 20_000,
        csi=tuple(plotted),
        raw_csi=raw,
        sig_mode=sig_mode,
        bandwidth=0,
        stbc=stbc,
        first_word_invalid=first_word_invalid,
    )


@pytest.mark.parametrize(
    ("layout", "sig_mode", "blocks", "stbc"),
    (
        (HE20_COMPACT_SLOT_INDICES, 4, 1, 0),
        (HE20_SLOT_INDICES, 4, 1, 0),
        (HT20_SLOT_INDICES, 1, 2, 0),
        (HT20_SLOT_INDICES, 1, 3, 1),
    ),
)
def test_vectorized_snapshot_matches_rolling_buffer(layout, sig_mode, blocks, stbc):
    records = tuple(
        _record(
            sequence,
            layout,
            sig_mode=sig_mode,
            blocks=blocks,
            stbc=stbc,
            first_word_invalid=sequence == 1,
        )
        for sequence in range(4)
    )
    expected_buffer = RollingCsiBuffer(max_records=len(records), seconds=60)
    for record in records:
        expected_buffer.append(record)

    expected = expected_buffer.snapshot()
    actual = _vectorized_snapshot(records)

    assert actual.timestamps == expected.timestamps
    assert actual.start_sequence == expected.start_sequence
    assert actual.end_sequence == expected.end_sequence
    assert actual.max_subcarriers == expected.max_subcarriers
    assert actual.phase_subcarriers == expected.phase_subcarriers
    for name in (
        "amplitudes",
        "phases",
        "real",
        "imaginary",
        "phase_amplitudes",
        "raw_phases",
        "calibrated_phases",
    ):
        np.testing.assert_allclose(
            getattr(actual, name),
            getattr(expected, name),
            rtol=1e-11,
            atol=1e-11,
            equal_nan=True,
        )


def test_signal_preparation_caps_plot_records_and_keeps_endpoints():
    records = tuple(
        CsiRecord(
            sequence=index,
            mac="00:11:22:33:44:55",
            rssi=-50,
            noise_floor=-95,
            timestamp_us=index * 20_000,
            csi=(complex(index % 9 + 1, 2),),
        )
        for index in range(MAX_PLOT_RECORDS + 75)
    )
    data = AttemptData(
        attempt_key="trial/attempt",
        receiver_id="rx-1",
        csi=TableData(name="CSI", path=None),
        radio_timing=TableData(name="Radio timing", path=None),
        clock_sync=TableData(name="Clock sync", path=None),
        records=records,
        record_row_indices=tuple(range(len(records))),
    )

    prepared = prepare_attempt_signals(data)

    assert prepared.snapshot is not None
    assert len(prepared.snapshot.timestamps) == MAX_PLOT_RECORDS
    assert prepared.snapshot.start_sequence == 0
    assert prepared.snapshot.end_sequence == len(records) - 1
    assert prepared.prepared_frame is not None
    assert prepared.prepared_frame.timestamps.shape == (MAX_PLOT_RECORDS,)
