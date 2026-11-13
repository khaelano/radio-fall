"""The inspector reads archived sessions in place, without extracting them."""

import json
import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from inspector_sessions import archive_of

from fall_detection.session import load_session
from fall_detection.session_inspector.exporter import (
    export_curated_bundle,
    session_size,
)
from fall_detection.session_inspector.review import (
    AttemptReview,
    ReviewStore,
)
from fall_detection.session_inspector.video import VideoReader, load_video_timeline


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
