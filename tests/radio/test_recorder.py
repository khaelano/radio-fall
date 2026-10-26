from pathlib import Path
from dataclasses import replace

from fall_detection.radio.acquisition.protocol import parse_csi_line
from fall_detection.radio.acquisition.recorder import CsiRecorder


def test_recorder_writes_header_and_valid_csi_line(tmp_path: Path):
    line = (
        'CSI_DATA,1,aa:bb:cc:dd:ee:ff,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,1000,0,36,0,4,0,"[3,4,0,5]"'
    )
    parse_csi_line(line)
    recorder = CsiRecorder(tmp_path)
    try:
        recorder.write(line)
        output = recorder.path
    finally:
        recorder.close()

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("type,id,mac")
    assert lines[1] == line


def test_recorder_writes_cross_clock_timing_sidecar(tmp_path: Path):
    line = (
        'CSI_DATA,1,aa:bb:cc:dd:ee:ff,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,1000,0,36,0,4,0,"[3,4,0,5]"'
    )
    record = replace(
        parse_csi_line(line),
        receiver_mac="24:6f:28:aa:bb:cc",
        transport_sequence=9,
        tx_timestamp_us=800,
        rx_callback_timestamp_us=1_020,
    )
    recorder = CsiRecorder(tmp_path)
    try:
        recorder.write_record(record, host_receive_monotonic_ns=123_456)
        timing_path = recorder.timing_path
    finally:
        recorder.close()

    lines = timing_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("sequence,receiver_mac,transport_sequence")
    assert lines[1] == "1,24:6f:28:aa:bb:cc,9,800,1000,1020,123456"
