"""Resolving a recording together with its review."""

import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("pyarrow")

from fall_detection._radio_native import (
    StorageError,
    storage_annotation_path,
    storage_open_session,
    storage_open_source,
    storage_resolve_source,
)
from journal_builder import build_session

from fall_detection.analysis.session_frames import load_analysis_session
from fall_detection.apps.session_inspector.review import (
    AttemptReview,
    ReviewDocument,
    ReviewError,
    ReviewStore,
)
from fall_detection.session import load_session

SessionResolutionError = StorageError


def annotation_path(root, session_id):
    return Path(storage_annotation_path(str(root), session_id))


def open_session(root, session_id):
    return storage_open_session(str(root), session_id)


def open_source(source, annotations_dir=None):
    return storage_open_source(
        str(source), None if annotations_dir is None else str(annotations_dir)
    )


def resolve_source(root, session_id):
    path, version = storage_resolve_source(str(root), session_id)
    return Path(path), version


def by_key(opened):
    return {item["attempt_key"]: item for item in opened["attempts"]}


SESSION = "20261113T000000000000Z"
HASH = "feedface"
KEY = "trials/001_activity/attempt_01"


def review(**attempt) -> dict:
    """A valid review document; ``attempt`` overrides the attempt's fields."""
    decision = {
        "activity_label": "fall",
        "inclusion": "include",
        "quality": "good",
        "notes": "clean",
    } | attempt
    return {
        "schema_version": 1,
        "session_id": SESSION,
        "protocol_hash": HASH,
        "revision": 2,
        "updated_at_utc": "2026-11-13T00:00:00+00:00",
        "metadata": {"participant_id": "p-07"},
        "attempts": {KEY: decision},
        "history": [],
    }


def zipped(directory: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                bundle.write(path, f"original/{path.relative_to(directory)}")
    return destination


def repository(tmp_path: Path) -> tuple[Path, Path]:
    """A repository root holding one archived session."""
    directory = build_session(tmp_path / "scratch" / SESSION)
    archive = zipped(directory, tmp_path / f"data/raw/sessions/{SESSION}.zip")
    return tmp_path, archive


def save(root: Path, document: dict) -> Path:
    path = annotation_path(root, SESSION)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))
    return path


def test_annotation_path_is_one_folder_per_session(tmp_path):
    assert annotation_path(tmp_path, SESSION) == (
        tmp_path / "data/annotations" / SESSION / "session_review.json"
    )
    for bad in ("", "..", "a/b", "../x"):
        with pytest.raises(SessionResolutionError):
            annotation_path(tmp_path, bad)


def test_an_unreviewed_session_keeps_its_recorded_values(tmp_path):
    root, archive = repository(tmp_path)
    opened = open_session(root, SESSION)
    assert Path(opened["source"]) == archive and opened["review"] is None
    attempt = by_key(opened)[KEY]
    assert attempt["activity_label"] == attempt["original_activity_label"]
    assert (attempt["inclusion"], attempt["review_revision"]) == ("unreviewed", 0)


def test_the_review_is_applied_without_touching_the_archive(tmp_path):
    root, archive = repository(tmp_path)
    before = archive.read_bytes()
    save(root, review())
    opened = open_session(root, SESSION)
    attempt = by_key(opened)[KEY]
    assert attempt["activity_label"] == "fall"
    assert attempt["original_activity_label"] != "fall"
    assert (attempt["inclusion"], attempt["quality"]) == ("include", "good")
    assert opened["review"]["origin"] == "annotations"
    assert opened["review"]["metadata"] == {"participant_id": "p-07"}
    assert archive.read_bytes() == before


def test_changing_the_review_changes_its_identity_but_not_the_recording(tmp_path):
    root, _ = repository(tmp_path)
    save(root, review())
    first = open_session(root, SESSION)
    save(root, review(quality="bad"))
    second = open_session(root, SESSION)
    assert first["source_fingerprint"] == second["source_fingerprint"]
    assert first["review"]["content_sha256"] != second["review"]["content_sha256"]


def test_an_annotation_wins_over_a_review_stored_inside_the_source(tmp_path):
    directory = build_session(tmp_path / "scratch" / SESSION)
    (directory / "session_review.json").write_text(
        json.dumps(review(activity_label="walk"))
    )
    embedded = open_source(directory)
    assert embedded["review"]["origin"] == "embedded"
    assert by_key(embedded)[KEY]["activity_label"] == "walk"
    annotations = tmp_path / "annotations"
    (annotations / SESSION).mkdir(parents=True)
    (annotations / SESSION / "session_review.json").write_text(json.dumps(review()))
    preferred = open_source(directory, annotations)
    assert preferred["review"]["origin"] == "annotations"
    assert by_key(preferred)[KEY]["activity_label"] == "fall"
    fallback = open_source(directory, tmp_path / "absent")
    assert fallback["review"]["origin"] == "embedded"


def test_a_directory_and_its_archive_resolve_identically(tmp_path):
    directory = build_session(tmp_path / "scratch" / SESSION)
    (directory / "session_review.json").write_text(json.dumps(review()))
    archive = zipped(directory, tmp_path / "archived.zip")
    assert open_source(directory)["attempts"] == open_source(archive)["attempts"]


INVALID = {
    "another session": lambda d: d.update(session_id="other"),
    "another protocol": lambda d: d.update(protocol_hash="zzz"),
    "unknown field": lambda d: d.update(extra=1),
    "unknown attempt": lambda d: d.update(attempts={"trials/009_x/attempt_01": {}}),
    "attempt key outside trials": lambda d: d.update(attempts={"../x": {}}),
    "bad inclusion": lambda d: d["attempts"][KEY].update(inclusion="maybe"),
    "bad quality": lambda d: d["attempts"][KEY].update(quality="great"),
    "blank label": lambda d: d["attempts"][KEY].update(activity_label="  "),
    "unknown attempt field": lambda d: d["attempts"][KEY].update(rating=5),
    "non-text notes": lambda d: d["attempts"][KEY].update(notes=3),
    "unknown metadata": lambda d: d["metadata"].update(shoe_size="9"),
    "non-text metadata": lambda d: d["metadata"].update(notes=3),
    "negative revision": lambda d: d.update(revision=-1),
    "future schema": lambda d: d.update(schema_version=2),
    "history not objects": lambda d: d.update(history=[1]),
}


@pytest.mark.parametrize("name", INVALID)
def test_python_and_rust_reject_the_same_invalid_reviews(tmp_path, name):
    """The Rust reader and the inspector's writer must not drift apart."""
    directory = build_session(tmp_path / "scratch" / SESSION)
    session = load_session(directory)
    document = deepcopy(review())
    INVALID[name](document)
    with pytest.raises(ReviewError):
        ReviewDocument.from_mapping(document, session)
    annotations = tmp_path / "annotations"
    (annotations / SESSION).mkdir(parents=True)
    (annotations / SESSION / "session_review.json").write_text(json.dumps(document))
    with pytest.raises(SessionResolutionError):
        open_source(directory, annotations)


def test_python_and_rust_accept_the_same_valid_review(tmp_path):
    directory = build_session(tmp_path / "scratch" / SESSION)
    session = load_session(directory)
    document = ReviewDocument.from_mapping(review(), session)
    assert document.attempts[KEY].activity_label == "fall"
    annotations = tmp_path / "annotations"
    (annotations / SESSION).mkdir(parents=True)
    (annotations / SESSION / "session_review.json").write_text(json.dumps(review()))
    assert by_key(open_source(directory, annotations))[KEY]["inclusion"] == "include"


def test_the_resolver_checks_identity_and_the_predecessor(tmp_path):
    root, archive = repository(tmp_path)
    assert resolve_source(root, SESSION) == (archive, None)  # not a version-3 archive
    with pytest.raises(SessionResolutionError):
        resolve_source(root, "missing")
    with pytest.raises(SessionResolutionError):
        resolve_source(root, "../escape")


def test_analysis_applies_the_default_annotations_beside_the_archive(tmp_path):
    root, archive = repository(tmp_path)
    plain = load_analysis_session(archive, tmp_path / "derived/a")
    assert plain.manifest["review"] is None
    save(root, review())
    reviewed = load_analysis_session(archive, tmp_path / "derived/b")
    row = reviewed.attempts.iloc[0]
    assert (row["activity_label"], row["inclusion"], row["review_revision"]) == (
        "fall",
        "include",
        2,
    )
    assert row["original_activity_label"] != "fall"
    assert reviewed.manifest["review"]["origin"] == "annotations"
    assert (
        plain.manifest["frames_fingerprint"] == reviewed.manifest["frames_fingerprint"]
    )
    assert (
        plain.manifest["source_fingerprint"] != reviewed.manifest["source_fingerprint"]
    )
    save(root, review(quality="bad"))
    edited = load_analysis_session(archive, tmp_path / "derived/c")
    assert (
        edited.manifest["source_fingerprint"] != reviewed.manifest["source_fingerprint"]
    )


def test_the_inspector_saves_into_annotations_and_migrates_an_embedded_review(
    tmp_path,
):
    directory = build_session(tmp_path / "scratch" / SESSION)
    (directory / "session_review.json").write_text(json.dumps(review(notes="old")))
    session = load_session(directory)
    target = tmp_path / "annotations" / SESSION / "session_review.json"
    store = ReviewStore(session, target)
    loaded = store.load()
    assert loaded.document.attempts[KEY].notes == "old"  # read from the old place
    edited = loaded.document.clone()
    edited.attempts[KEY] = AttemptReview(activity_label="fall", notes="new")
    saved = store.save(edited, loaded.token)
    assert target.is_file() and saved.document.revision == 3
    embedded = (directory / "session_review.json").read_text()
    assert json.loads(embedded)["attempts"][KEY]["notes"] == "old"  # left untouched
    fresh = ReviewStore(session, target).load()
    assert fresh.document.attempts[KEY].notes == "new"
    resolved = open_source(directory, tmp_path / "annotations")
    assert by_key(resolved)[KEY]["notes"] == "new"
