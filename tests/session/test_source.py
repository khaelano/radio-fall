"""Directory and archive sources load the same session without extraction."""

import json

import pytest
from inspector_sessions import archive_of

from fall_detection.session import SessionSource, load_session, scan_sessions


def test_source_reads_a_directory_and_its_archive_the_same(session_factory, tmp_path):
    root = session_factory(attempts=((1, 1, "accepted"), (1, 2, "accepted")))
    archive = archive_of(root, tmp_path / "repo")
    plain, packed = SessionSource(root), SessionSource(archive)
    assert not plain.is_archive and packed.is_archive
    assert plain.name == packed.name == root.name
    assert plain.attempt_keys() == packed.attempt_keys()
    assert len(packed.attempt_keys()) == 2
    for relative in ("session.json", "protocol.json"):
        assert plain.exists(relative) and packed.exists(relative)
        assert plain.read_bytes(relative) == packed.read_bytes(relative)
    assert not packed.exists("absent.json")
    with pytest.raises(OSError):
        packed.read_bytes("absent.json")
    assert json.loads(packed.read_text("session.json"))["session_id"]


def test_an_archived_session_loads_like_its_directory(session_factory, tmp_path):
    root = session_factory(attempts=((1, 1, "accepted"), (2, 1, "invalid")))
    archive = archive_of(root, tmp_path / "repo")
    before = archive.read_bytes()
    plain, packed = load_session(root), load_session(archive)
    assert packed.session_id == plain.session_id == root.name
    assert packed.protocol_hash == plain.protocol_hash
    assert [a.key for a in packed.attempts] == [a.key for a in plain.attempts]
    assert [a.status for a in packed.attempts] == [a.status for a in plain.attempts]
    assert [t.ordinal for t in packed.trials] == [t.ordinal for t in plain.trials]
    assert archive.read_bytes() == before
    assert not (archive.parent / root.name).exists()  # nothing was extracted


def test_receivers_resolve_from_an_archive_without_extracting(
    session_factory, tmp_path
):
    root = session_factory(attempts=((1, 1, "accepted"),))
    archive = archive_of(root, tmp_path / "repo")
    plain = load_session(root, resolve_receivers=True)
    packed = load_session(archive, resolve_receivers=True)
    assert packed.receivers_resolved
    assert packed.attempts[0].receiver_ids == plain.attempts[0].receiver_ids
    assert packed.attempts[0].receiver_ids


def test_scan_lists_directories_and_archives(session_factory, tmp_path):
    first = session_factory("20260101T000000000000Z", attempts=((1, 1, "accepted"),))
    sessions = first.parent
    second = session_factory("20260102T000000000000Z", attempts=((1, 1, "accepted"),))
    archive = archive_of(second, tmp_path / "repo")
    found = {bundle.path.name for bundle in scan_sessions(sessions)}
    assert found == {first.name, second.name}
    assert [b.path for b in scan_sessions(archive)] == [archive.resolve()]
    (archive.parent / "broken.zip").write_bytes(b"not a zip")
    assert {b.path.name for b in scan_sessions(archive.parent)} == {archive.name}


def test_compressed_directory_files_are_found_and_materialized(
    session_factory, tmp_path
):
    zstandard = pytest.importorskip("zstandard")
    root = session_factory("20260103T000000000000Z", attempts=((1, 1, "accepted"),))
    manifest = root / "session.json"
    plain = manifest.read_bytes()
    manifest.with_name("session.json.zst").write_bytes(
        zstandard.ZstdCompressor().compress(plain)
    )
    manifest.unlink()

    assert [bundle.path.name for bundle in scan_sessions(root.parent)] == [root.name]
    source = SessionSource(root)
    assert source.exists("session.json")
    decoded = source.materialize("session.json", tmp_path / "cache")
    assert decoded.read_bytes() == plain
    assert decoded.is_relative_to(tmp_path / "cache")
    assert source.materialize("protocol.json", tmp_path / "cache") == (
        root / "protocol.json"
    )
