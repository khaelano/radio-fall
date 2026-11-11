import json

import pytest

from fall_detection.storage import Recording, create_archive
from fall_detection.collection.archive import finalize_recording


def test_archive_extracts_every_original_byte_and_reads_tables(tmp_path):
    source = tmp_path / "session"
    receiver = source / "trials/001/attempt_01/receivers/rx-1"
    receiver.mkdir(parents=True)
    (source / "session.json").write_text(
        json.dumps(
            {"artifact_schema_version": 2, "status": "ended", "session_id": "test"}
        )
    )
    (source / "binary.bin").write_bytes(bytes(range(256)))
    relative = "trials/001/attempt_01/receivers/rx-1/csi.csv"
    (source / relative).write_bytes(b'id,data\r\n001,"[1,-2]"\r\n')
    archive = finalize_recording(source)
    with Recording(archive) as recording, Recording(source) as legacy:
        assert recording.read_json() == legacy.read_json()
        assert recording.read_table(relative).equals(legacy.read_table(relative))
        assert recording.compare_source(source)["files"] == 3
        extracted = recording.extract(tmp_path / "extracted")
        assert recording.compare_source(extracted)["files"] == 3
        with pytest.raises(FileNotFoundError):
            with recording.open("../session.json"):
                pass
        with pytest.raises(FileExistsError):
            recording.extract(extracted)
        (source / "binary.bin").write_bytes(b"changed")
        with pytest.raises(ValueError, match="bytes differ"):
            recording.compare_source(source)
    assert finalize_recording(source).name == "session.revision-001.zip"


def test_collector_finalizes_after_resource_cleanup(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fall_detection.collection import app, archive

    calls = []
    root = tmp_path / "session"

    def run(args, parser, resources):
        args._archive_controller = SimpleNamespace(_store=object(), session_root=root)
        resources.callback(lambda: calls.append("writer closed"))
        return 0

    monkeypatch.setattr(app, "_run", run)
    monkeypatch.setattr(
        archive, "finalize_recording", lambda path: calls.append("archive") or path
    )
    assert app.main([]) == 0
    assert calls == ["writer closed", "archive"]


def test_export_rejects_locked_session(tmp_path):
    fcntl = pytest.importorskip("fcntl")
    source = tmp_path / "session"
    source.mkdir()
    events = source / "events.jsonl"
    events.write_text("")
    with events.open("rb") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="another collector"):
            create_archive(source, tmp_path / "output.zip")
