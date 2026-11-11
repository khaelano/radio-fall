import json
import zipfile
import pytest

from fall_detection.radio.acquisition.recording_io import RecordingIO
from fall_detection.storage import Recording, create_archive
from fall_detection.storage.compressed import read_bytes


def test_native_writer_emits_zstd_before_close_and_appends_complete_frames(tmp_path):
    path = tmp_path / "events.jsonl"
    writer = RecordingIO(compressed=True)
    stream = writer.open(path, "x")
    stream.write("one\n")
    writer.flush()
    assert not path.exists()
    assert path.with_suffix(".jsonl.zst").read_bytes().startswith(b"\x28\xb5\x2f\xfd")
    assert read_bytes(path) == b"one\n"
    stream.write("two\n")
    writer.flush()
    assert read_bytes(path) == b"one\ntwo\n"
    writer.close()
    writer = RecordingIO(compressed=True)
    stream = writer.open(path, "a")
    stream.write("three\n")
    writer.close()
    assert read_bytes(path) == b"one\ntwo\nthree\n"
    physical = path.with_suffix(".jsonl.zst")
    physical.write_bytes(physical.read_bytes()[:-1])
    with pytest.raises(OSError, match="Truncated"):
        read_bytes(path)


def test_archive_keeps_compressed_bytes_and_exposes_original_logical_files(tmp_path):
    root = tmp_path / "session"
    receiver = root / "trials/001/attempt_01/receivers/rx-1"
    receiver.mkdir(parents=True)
    (root / "session.json").write_text(json.dumps(dict(
        artifact_schema_version=2, status="ended", session_id="test")))
    writer = RecordingIO(compressed=True)
    stream = writer.open(receiver / "csi.csv", "x")
    stream.write('id,data\n1,"[1,-2]"\n')
    writer.close()
    archive = tmp_path / "raw.zip"
    create_archive(root, archive)
    with zipfile.ZipFile(archive) as z:
        member = z.getinfo("original/trials/001/attempt_01/receivers/rx-1/csi.csv.zst")
        assert member.compress_type == zipfile.ZIP_STORED
        assert z.read(member) == (receiver / "csi.csv.zst").read_bytes()
    with Recording(archive) as recording:
        assert recording.manifest["version"] == 2
        assert recording.read_table("trials/001/attempt_01/receivers/rx-1/csi.csv")["id"].to_pylist() == ["1"]
        recording.compare_source(root)
        destination = recording.extract(tmp_path / "extracted")
        assert (destination / "trials/001/attempt_01/receivers/rx-1/csi.csv").read_text() == 'id,data\n1,"[1,-2]"\n'
