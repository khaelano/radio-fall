"""A format upgrade preserves the recorded bytes and never rewrites its source."""

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from fall_detection.storage import Recording, create_archive, session_archive_path

_TOOL = (
    Path(__file__).resolve().parents[2] / "tools/processing/upgrade_session_archive.py"
)
_SPEC = importlib.util.spec_from_file_location("upgrade_session_archive", _TOOL)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
upgrade_archive = _MODULE.upgrade_archive


def version_one_archive(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "session.json").write_text(
        json.dumps({"artifact_schema_version": 2, "status": "ended", "session_id": "s"})
    )
    (session / "events.jsonl").write_bytes(b'{"event":"end"}\n')
    (session / "csi.bin").write_bytes(bytes(range(256)))
    current = tmp_path / "current.zip"
    create_archive(session, current)
    old = tmp_path / "raw.zip"
    with zipfile.ZipFile(current) as src, zipfile.ZipFile(old, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                manifest = json.loads(data)
                manifest["version"] = 1
                data = json.dumps(manifest).encode()
            dst.writestr(name, data)
    return session, old


def test_upgrade_preserves_source_and_original_members(tmp_path):
    session, source = version_one_archive(tmp_path)
    with source.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    destination = tmp_path / "derived" / "session.zip"
    manifest = upgrade_archive(source, destination)
    assert manifest["version"] == 2
    assert manifest["normalized_from"]["archive_version"] == 1
    with source.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == source_hash
    with Recording(destination) as recording:
        assert recording.compare_source(session)["files"] == 3
    with pytest.raises(FileExistsError):
        upgrade_archive(source, destination)


def test_only_current_archives_are_readable_and_discovery_prefers_derived(tmp_path):
    _, old = version_one_archive(tmp_path)
    raw = tmp_path / "data/raw/sessions/s.zip"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(old.read_bytes())
    with pytest.raises(ValueError, match="unsupported archive format"):
        Recording(raw)
    normalized = tmp_path / "data/normalized/sessions/s.zip"
    upgrade_archive(raw, normalized)
    assert session_archive_path(tmp_path, "s") == normalized
    assert (
        session_archive_path(tmp_path, "new") == tmp_path / "data/raw/sessions/new.zip"
    )
    with pytest.raises(ValueError, match="session identifier"):
        session_archive_path(tmp_path, "../s")
    with Recording(normalized) as recording:
        assert recording.read_json()["session_id"] == "s"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(raw, "a") as archive,
    ):
        archive.writestr("manifest.json", '{"version": 1}')
    with pytest.raises(ValueError, match="source manifest differs"):
        session_archive_path(tmp_path, "s")


def test_upgrade_rejects_corrupt_member_without_publishing(tmp_path):
    _, source = version_one_archive(tmp_path)
    broken = tmp_path / "broken.zip"
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(broken, "w") as dst:
        for name in src.namelist():
            dst.writestr(
                name, b"changed" if name == "original/csi.bin" else src.read(name)
            )
    destination = tmp_path / "derived" / "bad.zip"
    with pytest.raises(ValueError, match="checksum mismatch"):
        upgrade_archive(broken, destination)
    assert not destination.exists()
    assert not list(destination.parent.glob(".archive-upgrade-*"))
