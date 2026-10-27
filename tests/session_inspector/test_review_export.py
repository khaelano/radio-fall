from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fall_detection.session_inspector.exporter import (
    ExportCancelled,
    export_curated_bundle,
)
from fall_detection.session_inspector.models import load_session
from fall_detection.session_inspector.review import (
    AttemptReview,
    ReviewConflictError,
    ReviewDocument,
    ReviewError,
    ReviewStore,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_review_save_is_atomic_versioned_and_does_not_rewrite_acquisition(
    session_factory
):
    root = session_factory(attempts=((1, 1, "accepted", 2),))
    session = load_session(root)
    session_before = (root / "session.json").read_bytes()
    attempt_path = next(root.glob("trials/*/attempt_*/attempt.json"))
    attempt_before = attempt_path.read_bytes()
    store = ReviewStore(session)
    loaded = store.load()
    review = loaded.document.clone()
    review.metadata["notes"] = "reviewed"
    review.attempts[session.attempts[0].key] = AttemptReview(
        activity_label="walk_slow",
        inclusion="include",
        quality="good",
        notes="clean",
    )

    saved = store.save(review, loaded.token)

    assert saved.document.revision == 1
    assert saved.document.history[0]["changes"]
    assert (root / "session.json").read_bytes() == session_before
    assert attempt_path.read_bytes() == attempt_before
    assert not (root / "session_review.json.tmp").exists()


def test_review_store_detects_optimistic_conflict(session_factory):
    session = load_session(session_factory())
    first = ReviewStore(session).load()
    second = ReviewStore(session).load()
    first_edit = first.document.clone()
    first_edit.metadata["notes"] = "first"
    ReviewStore(session).save(first_edit, first.token)
    second_edit = second.document.clone()
    second_edit.metadata["notes"] = "second"

    with pytest.raises(ReviewConflictError, match="changed since"):
        ReviewStore(session).save(second_edit, second.token)


def test_review_validation_rejects_unknown_attempt_and_empty_label(session_factory):
    session = load_session(session_factory())
    review = ReviewDocument.empty(session)
    review.attempts["trials/missing/attempt_01"] = AttemptReview(
        activity_label=""
    )

    with pytest.raises(ReviewError):
        review.validate(session)


def test_active_session_cannot_be_reviewed(session_factory):
    session = load_session(session_factory(status="open"))
    loaded = ReviewStore(session).load()
    loaded.document.metadata["notes"] = "unsafe"

    with pytest.raises(ReviewError, match="read-only"):
        ReviewStore(session).save(loaded.document, loaded.token)


def test_curated_export_applies_review_and_keeps_raw_files_identical(
    session_factory, tmp_path: Path
):
    root = session_factory(attempts=((1, 1, "accepted", 2),))
    session = load_session(root)
    raw_source = next(root.glob("trials/*/attempt_*/receivers/rx-1/csi.csv"))
    review = ReviewDocument.empty(session)
    review.revision = 3
    review.updated_at_utc = "2026-02-01T00:00:00+00:00"
    review.metadata = {"participant_id": "curated-participant", "notes": "checked"}
    review.attempts[session.attempts[0].key] = AttemptReview(
        activity_label="walk_slow",
        inclusion="exclude",
        quality="questionable",
        notes="motion artifact",
    )
    destination = tmp_path / "portable"

    exported = export_curated_bundle(session, review, destination)

    manifest = json.loads((exported / "session.json").read_text())
    attempt = json.loads(
        (exported / session.attempts[0].key / "attempt.json").read_text()
    )
    raw_export = exported / raw_source.relative_to(root)
    assert manifest["participant_id"] == "curated-participant"
    assert manifest["curation"]["excluded_attempts_retained"] is True
    assert attempt["activity_label"] == "walk_slow"
    assert attempt["original_activity_label"] == "walk"
    assert attempt["review"]["inclusion"] == "exclude"
    assert raw_export.exists()
    assert digest(raw_export) == digest(raw_source)
    assert json.loads((root / "session.json").read_text())["participant_id"] == "participant-1"

    with pytest.raises(FileExistsError):
        export_curated_bundle(session, review, destination)


def test_cancelled_export_removes_partial_directory(session_factory, tmp_path: Path):
    session = load_session(session_factory(attempts=((1, 1, "accepted", 2),)))
    review = ReviewDocument.empty(session)
    destination = tmp_path / "cancelled"

    with pytest.raises(ExportCancelled):
        export_curated_bundle(
            session,
            review,
            destination,
            cancelled=lambda: True,
        )

    assert not destination.exists()
    assert not tuple(tmp_path.glob(".cancelled.partial-*"))
