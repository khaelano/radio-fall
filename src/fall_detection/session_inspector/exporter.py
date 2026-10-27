"""Transactional export of reviewed, self-contained session bundles."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Callable
from uuid import uuid4

from .models import SessionBundle
from .review import ReviewDocument


class ExportCancelled(RuntimeError):
    """Raised when the caller cancels a curated export."""


ProgressCallback = Callable[[int, int, str], None]
CancellationCallback = Callable[[], bool]


def session_size(session: SessionBundle) -> int:
    """Return the total size in bytes of regular files in ``session``."""

    return sum(
        path.stat().st_size
        for path in session.path.rglob("*")
        if path.is_file()
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def export_curated_bundle(
    session: SessionBundle,
    review: ReviewDocument,
    destination: Path,
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
) -> Path:
    """Copy a session and apply its review without altering the source.

    The destination appears only after every file and curated manifest has
    been written successfully.  Excluded attempts remain in the export and are
    marked in their review block.
    """

    review.validate(session)
    source = session.path.resolve()
    target = destination.resolve()
    if target.exists():
        raise FileExistsError(f"export destination already exists: {target}")
    if target == source or _inside(target, source):
        raise ValueError("export destination cannot be inside the source session")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"export parent does not exist: {target.parent}")

    temporary = target.parent / f".{target.name}.partial-{uuid4().hex}"
    files = tuple(path for path in source.rglob("*") if path.is_file())
    total = sum(path.stat().st_size for path in files)
    copied = 0
    exported_at = datetime.now(timezone.utc).isoformat()
    try:
        temporary.mkdir()
        for source_file in files:
            if cancelled is not None and cancelled():
                raise ExportCancelled("curated export cancelled")
            relative = source_file.relative_to(source)
            target_file = temporary / relative
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
            copied += source_file.stat().st_size
            if progress is not None:
                progress(copied, total, relative.as_posix())

        session_manifest = dict(session.manifest)
        session_manifest.update(review.metadata)
        session_manifest["curation"] = {
            "exported_at_utc": exported_at,
            "source_session_id": session.session_id,
            "source_protocol_hash": session.protocol_hash,
            "review_revision": review.revision,
            "excluded_attempts_retained": True,
        }
        _write_json(temporary / "session.json", session_manifest)

        for key, attempt_review in review.attempts.items():
            attempt_path = temporary / key / "attempt.json"
            if not attempt_path.is_file():
                continue
            attempt_manifest = json.loads(attempt_path.read_text(encoding="utf-8"))
            if not isinstance(attempt_manifest, dict):
                continue
            original_label = str(attempt_manifest.get("activity_label") or "")
            effective_label = attempt_review.activity_label or original_label
            if effective_label and effective_label != original_label:
                attempt_manifest.setdefault("original_activity_label", original_label)
                attempt_manifest["activity_label"] = effective_label
            attempt_manifest["review"] = {
                "inclusion": attempt_review.inclusion,
                "quality": attempt_review.quality,
                "notes": attempt_review.notes,
                "reviewed_at_utc": review.updated_at_utc or exported_at,
                "source_review_revision": review.revision,
            }
            _write_json(attempt_path, attempt_manifest)

        _write_json(temporary / "session_review.json", review.to_mapping())
        if cancelled is not None and cancelled():
            raise ExportCancelled("curated export cancelled")
        temporary.replace(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
