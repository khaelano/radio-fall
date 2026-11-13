"""Collector streams are Zstandard frames that the library reads logically."""

import json

import pytest
from fall_detection._radio_native import (
    StorageError,
    storage_archive_manifest,
    storage_archive_session,
    storage_extract_archive,
    storage_files,
    storage_read,
    storage_read_file,
    storage_verify_archive,
)

from fall_detection.radio.recording_io import RecordingIO


def test_native_writer_emits_zstd_before_close_and_appends_complete_frames(tmp_path):
    path = tmp_path / "events.jsonl"
    writer = RecordingIO(compressed=True)
    stream = writer.open(path, "x")
    stream.write("one\n")
    writer.flush()
    assert not path.exists()
    assert path.with_suffix(".jsonl.zst").read_bytes().startswith(b"\x28\xb5\x2f\xfd")
    assert storage_read_file(path) == b"one\n"
    stream.write("two\n")
    writer.flush()
    assert storage_read_file(path) == b"one\ntwo\n"
    writer.close()
    writer = RecordingIO(compressed=True)
    stream = writer.open(path, "a")
    stream.write("three\n")
    writer.close()
    assert storage_read_file(path) == b"one\ntwo\nthree\n"
    physical = path.with_suffix(".jsonl.zst")
    physical.write_bytes(physical.read_bytes()[:-1])
    with pytest.raises(StorageError, match="events.jsonl.zst"):
        storage_read_file(path)


def test_compressed_writer_rejects_plain_append_without_modifying_file(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"original\n")
    writer = RecordingIO(compressed=True)
    try:
        with pytest.raises(ValueError, match="existing plain file"):
            writer.open(path, "a")
        assert path.read_bytes() == b"original\n"
        assert not path.with_suffix(".jsonl.zst").exists()
    finally:
        writer.close()


def test_archive_keeps_compressed_logs_and_exposes_the_original_logical_files(
    tmp_path,
):
    root = tmp_path / "session"
    receiver = root / "trials/001/attempt_01/receivers/rx-1"
    receiver.mkdir(parents=True)
    (root / "session.json").write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "ended", "session_id": "test"}
        )
    )
    writer = RecordingIO(compressed=True)
    stream = writer.open(receiver / "csi.csv", "x")
    stream.write('id,data\n1,"[1,-2]"\n')
    writer.close()
    archive = tmp_path / "raw.zip"
    report = storage_archive_session(str(root), str(archive))
    assert report["dropped"] == {} and report["table_differences"] == []
    manifest = storage_archive_manifest(str(archive))
    assert manifest["version"] == 3
    names = {member["name"] for member in manifest["members"]}
    assert "original/trials/001/attempt_01/receivers/rx-1/csi.csv.zst" in names
    assert storage_verify_archive(str(archive)) == []
    logical = "trials/001/attempt_01/receivers/rx-1/csi.csv"
    assert logical in storage_files(str(archive))
    assert storage_read(str(archive), logical) == b'id,data\n1,"[1,-2]"\n'
    extracted = tmp_path / "extracted"
    assert storage_extract_archive(str(archive), str(extracted)) == 2
    assert storage_read_file(extracted / logical) == b'id,data\n1,"[1,-2]"\n'
    with pytest.raises(StorageError, match="overwrite"):
        storage_extract_archive(str(archive), str(extracted))
