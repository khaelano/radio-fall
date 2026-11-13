from math import isclose, isnan
from pathlib import Path

from csi_line import record_from_csi_line

from fall_detection.radio.records import CSI_HEADER, CsiRecord, format_csi_record

FIXTURE = Path(__file__).parent / "fixtures" / "csi_sample.csv"


def test_csi_line_record_decodes_interleaved_imaginary_real_values():
    line = FIXTURE.read_text(encoding="utf-8").splitlines()[1]

    record = record_from_csi_line(line)

    assert record.sequence == 10
    assert record.mac == "1a:00:00:00:00:00"
    assert record.csi == (complex(4, 3), complex(5, 0))
    assert tuple(record.amplitudes) == (5.0, 5.0)
    assert tuple(record.real) == (4.0, 5.0)
    assert tuple(record.imaginary) == (3.0, 0.0)
    assert isclose(record.phases[0], 0.6435011088, rel_tol=1e-9)
    assert record.phases[1] == 0.0


def test_csi_line_record_masks_invalid_first_word_without_shifting_subcarriers():
    line = 'CSI_DATA,2,aa:bb:cc:dd:ee:ff,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,100,0,36,0,6,1,"[9,9,3,4,0,5]"'

    record = record_from_csi_line(line)

    assert record.first_word_invalid is True
    assert isnan(record.amplitudes[0])
    assert isnan(record.amplitudes[1])
    assert isnan(record.phases[0])
    assert isnan(record.real[0])
    assert isnan(record.imaginary[1])
    assert record.csi[2] == complex(5, 0)


def test_parse_ht20_payload_exposes_ltf_blocks_and_raw_csi():
    values = [component for pair in ([20, 0] for _ in range(128)) for component in pair]
    line = (
        'CSI_DATA,20,aa:bb:cc:dd:ee:ff,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,100,0,36,0,256,1,"'
        + str(values).replace("'", "")
        + '"'
    )

    record = record_from_csi_line(line)

    assert record.sig_mode == 1
    assert record.bandwidth == 0
    assert record.csi_length == 256
    assert len(record.raw_csi) == 128
    assert [block.name for block in record.ltf_blocks] == ["LLTF", "HT-LTF"]
    assert record.htltf_block is record.ltf_blocks[1]
    assert record.channel_estimate_block is record.ltf_blocks[1]
    assert record.htltf_block.subcarrier_indices[0:3] == (0, 1, 2)


def test_c6_he20_payload_exposes_he_ltf_channel_estimate():
    values = [component for pair in ([20, 0] for _ in range(245)) for component in pair]
    line = (
        'CSI_DATA,21,aa:bb:cc:dd:ee:ff,-40,11,4,0,0,0,0,0,0,0,0,-95,0,11,0,100,0,36,0,490,0,"'
        + str(values).replace("'", "")
        + '"'
    )

    record = record_from_csi_line(line)

    assert record.sig_mode == 4
    assert record.csi_length == 490
    assert [block.name for block in record.ltf_blocks] == ["HE-LTF"]
    assert record.htltf_block is None
    assert record.channel_estimate_block is record.ltf_blocks[0]


def test_he_ltf_phase_is_prepared_natively_at_construction():
    values = [component for pair in ([0, 20] for _ in range(256)) for component in pair]
    line = (
        'CSI_DATA,21,aa:bb:cc:dd:ee:ff,-40,11,4,0,0,0,0,0,0,0,0,-95,0,11,0,100,0,36,0,512,0,"'
        + str(values).replace("'", "")
        + '"'
    )

    record = record_from_csi_line(line)

    assert record.phase_views_ready
    assert record.mean_i == 20.0
    assert record.mean_q == 0.0
    block = record.channel_estimate_block
    assert block is not None and block.name == "HE-LTF"
    assert block.csi == record.raw_csi


def test_ht_ltf_calibration_is_lazy_until_a_phase_view_requests_it():
    values = [component for pair in ([0, 20] for _ in range(128)) for component in pair]
    line = (
        'CSI_DATA,21,aa:bb:cc:dd:ee:ff,-40,11,1,0,0,0,0,0,0,0,0,-95,0,11,0,100,0,36,0,256,0,"'
        + str(values).replace("'", "")
        + '"'
    )

    record = record_from_csi_line(line)

    assert not record.phase_views_ready
    assert record.mean_i == 20.0
    assert record.mean_q == 0.0
    assert not record.phase_views_ready

    assert record.channel_estimate_block is not None
    assert record.phase_views_ready


def test_constructor_rejects_values_the_radio_cannot_report():
    import pytest

    from fall_detection.radio.records import CsiRecord

    for value in (0.5, 128, float("nan")):
        with pytest.raises(ValueError):
            CsiRecord(1, "aa", -40, -95, 1, (complex(value, 0),))


def test_replace_changes_native_fields_and_context_independently():
    from fall_detection.radio.records import CsiRecord

    record = CsiRecord(
        1, "aa", -40, -95, 1, (3 + 4j, 1 + 1j), run_id=7, first_word_invalid=True
    )
    changed = record.replace(sequence=2, capture_host_monotonic_ns=5)
    assert (changed.sequence, changed.run_id, changed.capture_host_monotonic_ns) == (
        2,
        7,
        5,
    )
    assert changed.first_word_invalid and changed.raw_csi == record.raw_csi
    assert record.sequence == 1 and record.capture_host_monotonic_ns is None
    assert record.replace(run_id=9)._native is record._native


def test_csi_record_pickle_and_copy_round_trip_he_record_with_metadata():
    import copy
    import pickle

    import numpy as np

    values = [complex(i % 50 - 25, i % 40 - 20) for i in range(245)]
    record = CsiRecord(
        5,
        "aa:bb:cc:dd:ee:ff",
        -40,
        -90,
        1,
        values,
        sig_mode=4,
        first_word_invalid=True,
        tx_timestamp_us=10,
        rx_callback_timestamp_us=20,
        run_id=3,
    ).with_context({"native_processed_ns": 77})

    for restored in (
        pickle.loads(pickle.dumps(record)),
        copy.copy(record),
        copy.deepcopy(record),
    ):
        assert restored == record
        assert (restored.native_processed_ns, restored.run_id) == (77, 3)
        assert restored.csv_line == record.csv_line
        assert np.array_equal(
            restored.channel_estimate_block.calibrated_phases,
            record.channel_estimate_block.calibrated_phases,
            equal_nan=True,
        )


def test_format_csi_record_round_trips_a_python_record_to_its_row():
    line = FIXTURE.read_text(encoding="utf-8").splitlines()[1]

    row = format_csi_record(record_from_csi_line(line))

    assert row == line
    assert len(row.split(",", 24)) == len(CSI_HEADER.split(","))


def test_format_csi_record_keeps_the_collector_sidecar_bytes():
    # Expected text captured from the previous pure-Python formatter.
    raw = tuple(
        complex(((i * 37) % 255) - 127, ((i * 91 + 5) % 255) - 127) for i in range(6)
    )
    record = CsiRecord(
        sequence=42,
        mac="aa:bb:cc:00:11:22",
        rssi=-61,
        noise_floor=-94,
        timestamp_us=1234567,
        csi=raw,
        first_word_invalid=True,
        rate=11,
        sig_mode=4,
        mcs=7,
        bandwidth=0,
        smoothing=1,
        not_sounding=0,
        aggregation=1,
        stbc=0,
        fec_coding=1,
        sgi=2,
        ampdu_count=3,
        channel=44,
        secondary_channel=0,
        antenna=1,
        sig_len=250,
        rx_state=0,
    )

    assert format_csi_record(record) == (
        "CSI_DATA,42,aa:bb:cc:00:11:22,-61,11,4,7,0,1,0,1,0,1,2,-94,3,44,0,1234567,"
        '1,250,0,12,1,"[-122,-127,-31,-90,60,-53,-104,-16,-13,21,78,58]"'
    )
