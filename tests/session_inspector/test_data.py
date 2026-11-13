from __future__ import annotations

import numpy as np
import pytest
from inspector_sessions import ATTEMPT_LENGTH_NS, FrameSpec, attempt_origin
from journal_builder import TX, mac_text

from fall_detection.radio.buffer import RollingCsiBuffer
from fall_detection.radio.preprocessing.phase import (
    HE20_COMPACT_SLOT_INDICES,
    HE20_SLOT_INDICES,
    HT20_SLOT_INDICES,
)
from fall_detection.radio.records import CSI_HEADER, CsiRecord
from fall_detection.session import load_session
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


def test_attempt_data_synthesizes_csv_rows_and_marks_invalid_first_word(
    session_factory,
):
    origin = attempt_origin(0)
    root = session_factory(
        attempts=((1, 1, "accepted"),),
        frames=(
            FrameSpec(
                10,
                origin + 100_000_000,
                values=(complex(3, 4), complex(-2, 1)),
            ),
            FrameSpec(
                11,
                origin + 200_000_000,
                values=(complex(9, 9), complex(5, 6), complex(7, 8)),
                first_word_invalid=True,
            ),
        ),
    )
    session = load_session(root)

    data = load_attempt_data(session.attempts[0], "rx-1")

    assert data.csi.headers == tuple(CSI_HEADER.split(","))
    assert data.csi.row_count == 2
    first = dict(zip(data.csi.headers, data.csi.rows[0], strict=True))
    assert first["type"] == "CSI_DATA"
    assert first["id"] == "10"
    assert first["mac"] == mac_text(TX)
    assert first["local_timestamp"] == "1100000"
    assert first["len"] == "4"
    assert first["data"] == "[4,3,1,-2]"
    flagged = dict(zip(data.csi.headers, data.csi.rows[1], strict=True))
    assert flagged["first_word"] == "1"
    assert flagged["data"] == "[9,9,6,5,8,7]"
    assert len(data.records) == 2
    assert data.record_row_indices == (0, 1)
    assert np.isnan(data.records[1].csi[0]) and data.records[1].raw_csi[0] == 9 + 9j
    assert data.snapshot is None
    assert data.prepared_frame is None
    assert data.warnings == ()
    assert data.signal_times == (0.1, 0.2)
    assert "capture" in data.time_source
    values = csi_value_rows(data.records[0])
    assert values[0].real == 3
    assert values[0].imaginary == 4
    assert values[0].amplitude == 5

    prepared = prepare_attempt_signals(data)
    assert prepared.snapshot is not None
    assert prepared.snapshot.timestamps == (0.1, 0.2)
    assert prepared.prepared_frame is not None

    compact = load_attempt_data_for_ui(session.attempts[0], "rx-1")
    assert compact.records == ()
    assert compact.record_count == 2
    restored = csi_record_for_table_row(compact, 0)
    assert restored is not None
    assert restored.csi == (complex(3, 4), complex(-2, 1))
    assert csi_record_for_table_row(compact, 2) is None


def test_compact_row_selection_never_reconverts_and_caches_the_window(
    session_factory, monkeypatch
):
    from fall_detection.session_inspector import data as data_module

    root = session_factory(attempts=((1, 1, "accepted"),))
    compact = load_attempt_data_for_ui(load_session(root).attempts[0], "rx-1")
    data_module._FRAME_CACHE.clear()
    calls = {"ensure": 0, "open": 0}
    real = data_module.FrameStore

    class Spy:
        @staticmethod
        def ensure(*args, **kwargs):
            calls["ensure"] += 1
            return real.ensure(*args, **kwargs)

        @staticmethod
        def open(*args, **kwargs):
            calls["open"] += 1
            return real.open(*args, **kwargs)

    monkeypatch.setattr(data_module, "FrameStore", Spy)

    first = csi_record_for_table_row(compact, 0)
    second = csi_record_for_table_row(compact, 1)
    again = csi_record_for_table_row(compact, 0)

    # One cache miss opens the store twice (read, then fingerprint re-check);
    # later selections hit the cache and open nothing.
    assert calls == {"ensure": 0, "open": 2}
    assert first is not None and second is not None and again == first
    assert first.sequence == 1 and second.sequence == 2


def test_compact_row_selection_rejects_changed_frame_tables(session_factory):
    from dataclasses import replace

    from fall_detection.session_inspector import data as data_module

    root = session_factory(attempts=((1, 1, "accepted"),))
    compact = load_attempt_data_for_ui(load_session(root).attempts[0], "rx-1")
    data_module._FRAME_CACHE.clear()
    stale = replace(compact, frames_fingerprint="not-the-loaded-fingerprint")

    assert csi_record_for_table_row(stale, 0) is None
    assert csi_record_for_table_row(compact, 0) is not None


def test_attempt_data_keeps_delivery_order_and_capture_time_axis(session_factory):
    root = session_factory(attempts=((1, 1, "accepted"),))
    session = load_session(root)

    data = load_attempt_data(session.attempts[0], "rx-1")

    # Frames are listed in delivery order; plot times are capture times.
    assert [int(row[1]) for row in data.csi.rows] == [1, 2]
    assert data.signal_times == (1.2, 0.2)
    timing = [
        dict(zip(data.radio_timing.headers, row, strict=True))
        for row in data.radio_timing.rows
    ]
    assert [row["sequence"] for row in timing] == ["1", "2"]
    assert [int(row["capture_time_ns"]) - attempt_origin(0) for row in timing] == [
        1_200_000_000,
        200_000_000,
    ]
    # Host arrival is a separate clock from capture time.
    assert timing[0]["host_receive_monotonic_ns"] == "1"


def test_attempt_data_selects_receiver_and_attempt_window(session_factory):
    origin = attempt_origin(0)
    root = session_factory(
        attempts=((1, 1, "accepted"),),
        frames=(
            FrameSpec(1, origin + 100_000_000, "rx-1"),
            FrameSpec(2, origin + 200_000_000, "rx-2"),
            FrameSpec(3, origin + ATTEMPT_LENGTH_NS, "rx-1"),
            FrameSpec(4, origin - 1, "rx-1"),
        ),
    )
    attempt = load_session(root).attempts[0]

    first = load_attempt_data(attempt, "rx-1")
    second = load_attempt_data(attempt, "rx-2")
    missing = load_attempt_data(attempt, "rx-3")

    assert [row[1] for row in first.csi.rows] == ["1"]
    assert [row[1] for row in second.csi.rows] == ["2"]
    assert missing.csi.row_count == 0
    assert missing.signal_times is None
    assert missing.record_count == 0
    assert any("no frames" in warning for warning in missing.warnings)


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
        csi=TableData(name="CSI"),
        radio_timing=TableData(name="Radio timing"),
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
