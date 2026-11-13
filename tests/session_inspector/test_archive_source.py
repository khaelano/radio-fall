"""The inspector reads archived sessions in place, without extracting them."""

import json
import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from fall_detection._radio_native import storage_archive_session

from fall_detection.session_inspector.exporter import (
    export_curated_bundle,
    session_size,
)
from fall_detection.session_inspector.models import load_session, scan_sessions
from fall_detection.session_inspector.review import (
    AttemptReview,
    ReviewStore,
)
from fall_detection.session_inspector.source import SessionSource
from fall_detection.session_inspector.video import VideoReader, load_video_timeline


def archive_of(directory: Path, root: Path) -> Path:
    """Archive ``directory`` at ``<root>/data/raw/sessions/<name>.zip``."""
    destination = root / "data/raw/sessions" / f"{directory.name}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    storage_archive_session(str(directory), str(destination))
    return destination


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


def test_a_review_of_an_archived_session_is_saved_under_annotations(
    session_factory, tmp_path
):
    root = session_factory(attempts=((1, 1, "accepted"),))
    repo = tmp_path / "repo"
    archive = archive_of(root, repo)
    session = load_session(archive)
    store = ReviewStore(session)
    expected = repo / "data/annotations" / session.session_id / "session_review.json"
    assert store.path == expected.resolve() or store.path == expected
    loaded = store.load()
    edited = loaded.document.clone()
    edited.attempts[session.attempts[0].key] = AttemptReview(
        activity_label="fall", inclusion="include"
    )
    store.save(edited, loaded.token)
    assert expected.is_file()
    assert ReviewStore(load_session(archive)).load().document.attempts


def test_a_curated_export_of_an_archive_matches_one_of_its_directory(
    session_factory, tmp_path
):
    root = session_factory(attempts=((1, 1, "accepted"),))
    archive = archive_of(root, tmp_path / "repo")
    review = ReviewStore(load_session(root)).load().document.clone()
    (tmp_path / "out").mkdir()
    from_dir = export_curated_bundle(
        load_session(root), review, tmp_path / "out" / "from-dir"
    )
    review_for_archive = ReviewStore(load_session(archive)).load().document.clone()
    from_archive = export_curated_bundle(
        load_session(archive), review_for_archive, tmp_path / "out" / "from-archive"
    )

    def names(base: Path) -> set[str]:
        return {
            p.relative_to(base).as_posix().removesuffix(".zst")
            for p in base.rglob("*")
            if p.is_file()
        }

    assert names(from_archive) == names(from_dir)
    assert (from_archive / "session_review.json").is_file()
    assert not list((tmp_path / "out").glob(".*"))  # no scratch left behind
    assert session_size(load_session(archive)) == archive.stat().st_size


def test_video_of_an_archived_attempt_extracts_only_that_clip(
    session_factory, tmp_path
):
    av = pytest.importorskip("av")
    from fall_detection.collection.video import VideoConfig, _AttemptVideo

    root = session_factory(attempts=((1, 1, "accepted"), (1, 2, "accepted")))
    for number in (1, 2):
        path = next(root.glob(f"trials/*/attempt_0{number}"))
        origin = json.loads((path / "attempt.json").read_text())["started_monotonic_ns"]
        recorder = _AttemptVideo(
            path, origin, VideoConfig("/dev/video-test", 64, 48, 30)
        )
        for i, offset in enumerate([50_000_000, 100_000_000]):
            frame = av.VideoFrame.from_ndarray(
                np.full((48, 64, 3), 40 * (i + number), dtype=np.uint8), format="rgb24"
            )
            recorder.write(frame, origin + offset - 1_000_000, origin + offset)
        recorder.finish(origin + 2_000_000_000)
    archive = archive_of(root, tmp_path / "repo")
    attempt = load_session(archive).attempts[0]
    timeline = load_video_timeline(attempt)
    media = Path(timeline.path)
    assert media.is_file() and media.name == "camera.mp4"
    assert media.is_relative_to(tmp_path)  # cached beside the frame tables
    cached = [p for p in media.parents[3].rglob("camera.mp4")]
    assert cached == [media]  # the other attempt's clip was not extracted
    reader = VideoReader(timeline)
    try:
        width, height, rgb = reader.read(0)
        assert (width, height) == (64, 48)
        assert np.frombuffer(rgb, dtype=np.uint8).mean() == pytest.approx(40, abs=3)
    finally:
        reader.close()
    # A second load reuses the extracted clip.
    stamp = media.stat().st_mtime_ns
    assert Path(load_video_timeline(attempt).path).stat().st_mtime_ns == stamp
