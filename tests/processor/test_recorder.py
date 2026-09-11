from pathlib import Path

from radio_processor.protocol import parse_csi_line
from radio_processor.recorder import CsiRecorder


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
