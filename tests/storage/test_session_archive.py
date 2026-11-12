import json
import zipfile

import pytest

from fall_detection.storage.session_archive import create_archive, verify_archive


def test_archive_preserves_originals_and_parquet(tmp_path):
    source = tmp_path / "session"
    receiver = source / "trials/001_test/attempt_01/receivers/rx-1"
    receiver.mkdir(parents=True)
    (source / "session.json").write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "complete", "session_id": "test"}
        )
    )
    (source / "events.jsonl").write_bytes(b'{"event":1}\n')
    csv = b'id,data\r\n01,"[1,2]"\r\n'
    (receiver / "csi.csv").write_bytes(csv)
    destination = tmp_path / "session.zip"
    manifest = create_archive(source, destination)
    assert verify_archive(destination) == manifest
    assert manifest["version"] == 2
    assert manifest["tables"][0]["rows"] == 1
    with zipfile.ZipFile(destination) as archive:
        assert (
            archive.read("original/trials/001_test/attempt_01/receivers/rx-1/csi.csv")
            == csv
        )
        assert archive.read(manifest["tables"][0]["path"])[:4] == b"PAR1"
    with pytest.raises(FileExistsError):
        create_archive(source, destination)


def test_archive_rejects_open_session_and_symlink(tmp_path):
    source = tmp_path / "session"
    source.mkdir()
    session = source / "session.json"
    session.write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "open", "session_id": "test"}
        )
    )
    with pytest.raises(ValueError, match="closed"):
        create_archive(source, tmp_path / "output.zip")
    session.write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "ended", "session_id": "test"}
        )
    )
    (source / "link").symlink_to(session)
    with pytest.raises(ValueError, match="symbolic link"):
        create_archive(source, tmp_path / "output.zip")


def test_verify_rejects_unlisted_member(tmp_path):
    source = tmp_path / "session"
    source.mkdir()
    (source / "session.json").write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "ended", "session_id": "test"}
        )
    )
    destination = tmp_path / "session.zip"
    create_archive(source, destination)
    with zipfile.ZipFile(destination, "a") as archive:
        archive.writestr("original/unlisted", b"unexpected")
    with pytest.raises(ValueError, match="inventory"):
        verify_archive(destination)


def test_verify_rejects_changed_file_bytes(tmp_path):
    source = tmp_path / "session"
    source.mkdir()
    (source / "session.json").write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "ended", "session_id": "test"}
        )
    )
    (source / "payload.bin").write_bytes(b"original bytes")
    destination = tmp_path / "session.zip"
    create_archive(source, destination)
    corrupted = tmp_path / "corrupted.zip"
    with zipfile.ZipFile(destination) as src, zipfile.ZipFile(corrupted, "w") as dst:
        for name in src.namelist():
            data = (
                b"modified bytes" if name == "original/payload.bin" else src.read(name)
            )
            dst.writestr(name, data)
    with pytest.raises(ValueError, match="checksum"):
        verify_archive(corrupted)
