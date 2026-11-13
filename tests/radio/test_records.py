from math import isclose, isnan
from pathlib import Path

from csi_line import record_from_csi_line

from fall_detection.radio.records import CSI_HEADER, format_csi_record

FIXTURE = Path(__file__).parent / "fixtures" / "csi_sample.csv"


def test_csi_line_record_decodes_interleaved_imaginary_real_values():
    line = FIXTURE.read_text(encoding="utf-8").splitlines()[1]

    record = record_from_csi_line(line)

    assert record.sequence == 10
    assert record.mac == "1a:00:00:00:00:00"
    assert record.csi == (complex(4, 3), complex(5, 0))
    assert record.amplitudes == (5.0, 5.0)
    assert record.real == (4.0, 5.0)
    assert record.imaginary == (3.0, 0.0)
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


def test_he_ltf_calibration_is_lazy_until_a_phase_view_requests_it():
    values = [component for pair in ([0, 20] for _ in range(256)) for component in pair]
    line = (
        'CSI_DATA,21,aa:bb:cc:dd:ee:ff,-40,11,4,0,0,0,0,0,0,0,0,-95,0,11,0,100,0,36,0,512,0,"'
        + str(values).replace("'", "")
        + '"'
    )

    record = record_from_csi_line(line)

    assert record._ltf_blocks_cache is None
    assert record.mean_i == 20.0
    assert record.mean_q == 0.0
    assert record._ltf_blocks_cache is None

    assert record.channel_estimate_block is not None
    assert record._ltf_blocks_cache is not None


def test_format_csi_record_round_trips_a_python_record_to_its_row():
    line = FIXTURE.read_text(encoding="utf-8").splitlines()[1]

    row = format_csi_record(record_from_csi_line(line))

    assert row == line
    assert len(row.split(",", 24)) == len(CSI_HEADER.split(","))
