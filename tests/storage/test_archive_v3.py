"""Version-3 archives: migration, verification, and discovery."""

import json
import random
import zipfile

import pytest

pytest.importorskip("pyarrow")

from fall_detection._radio_native import (
    StorageError,
    storage_archive_manifest,
    storage_files,
    storage_migrate,
    storage_resolve_source,
    storage_verify_archive,
)
from journal_builder import build_session

from fall_detection.analysis.session_frames import load_analysis_session

# Incompressible filler, so dropping these members visibly shrinks the archive.
CSV = random.Random(0).randbytes(150_000)


SESSION = "20261113T000000000000Z"  # the id inside the synthetic session


def old_archive(tmp_path, name=SESSION):
    """A source archive in the old layout, with CSV sidecars and table copies."""
    session = build_session(tmp_path / "session", batches=6)
    path = tmp_path / "data/raw/sessions" / f"{name}.zip"
    path.parent.mkdir(parents=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for member in sorted(session.rglob("*")):
            if member.is_file():
                bundle.write(
                    member, "original/" + member.relative_to(session).as_posix()
                )
        for extra in (
            "original/trials/001_activity/attempt_01/receivers/rx-1/csi.csv",
            "original/trials/001_activity/attempt_01/receivers/rx-1/gateway_timing.jsonl",
            "tables/trials/001_activity/attempt_01/receivers/rx-1/csi.parquet",
        ):
            bundle.writestr(extra, CSV)
        bundle.writestr("manifest.json", json.dumps({"format": "old", "version": 2}))
    return session, path


def test_migration_keeps_raw_record_and_drops_derived_members(tmp_path):
    _, source = old_archive(tmp_path)
    before = source.read_bytes()
    destination = tmp_path / "v3" / f"{SESSION}.zip"
    destination.parent.mkdir(parents=True)
    report = storage_migrate(str(source), str(destination))
    assert source.read_bytes() == before  # the source is never modified
    assert report["table_differences"] == []
    assert set(report["dropped"]) == {"csi.csv", "gateway_timing.jsonl", "csi.parquet"}
    assert report["destination_bytes"] < report["source_bytes"]
    manifest = storage_archive_manifest(str(destination))
    assert manifest["version"] == 3
    assert not any("/receivers/" in m["name"] for m in manifest["members"])
    assert storage_verify_archive(str(destination)) == []
    logical = storage_files(str(destination))
    assert any(name.endswith("envelopes.bin") for name in logical)
    assert not any(name.endswith(".zst") for name in logical)
    with pytest.raises(RuntimeError, match="overwrite"):
        storage_migrate(str(source), str(destination))


def test_analysis_reads_the_same_tables_from_a_migrated_archive(tmp_path):
    _, source = old_archive(tmp_path)
    destination = tmp_path / "v3" / f"{SESSION}.zip"
    destination.parent.mkdir(parents=True)
    storage_migrate(str(source), str(destination))
    old = load_analysis_session(source, tmp_path / "derived/old")
    new = load_analysis_session(destination, tmp_path / "derived/new")
    assert old.manifest["packet_count"] == new.manifest["packet_count"]
    assert old.attempts.drop(columns=["receiver_ids"]).equals(
        new.attempts.drop(columns=["receiver_ids"])
    )
    assert old.read_packets().equals(new.read_packets())


def test_discovery_uses_the_raw_version_3_archive_and_checks_its_predecessor(tmp_path):
    _, source = old_archive(tmp_path)
    predecessor = tmp_path / "data/old_raw/sessions" / source.name
    predecessor.parent.mkdir(parents=True)
    source.rename(predecessor)
    destination = tmp_path / "data/raw/sessions" / f"{SESSION}.zip"
    storage_migrate(str(predecessor), str(destination))
    assert storage_resolve_source(str(tmp_path), SESSION) == (str(destination), 3)
    # A changed predecessor no longer matches the recorded provenance.
    with zipfile.ZipFile(predecessor, "a") as bundle:
        bundle.writestr("original/extra.txt", b"changed")
    with pytest.raises(StorageError, match="source differs"):
        storage_resolve_source(str(tmp_path), SESSION)


def test_verification_reports_a_damaged_archive(tmp_path):
    _, source = old_archive(tmp_path)
    destination = tmp_path / "v3.zip"
    storage_migrate(str(source), str(destination))
    data = bytearray(destination.read_bytes())
    data[len(data) // 3] ^= 0xFF
    destination.write_bytes(bytes(data))
    try:
        problems = storage_verify_archive(str(destination))
    except RuntimeError:
        return  # a corrupt member may stop decoding outright
    assert problems
