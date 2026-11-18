from __future__ import annotations

import json
from pathlib import Path

from fall_detection.collection.capture import TrialCapture


def test_trial_capture_keeps_only_the_attempt_manifest(tmp_path: Path):
    capture = TrialCapture(
        tmp_path / "attempt_01", {"trial_ordinal": 1, "activity_label": "walk"}
    )

    capture.update_status("pending_review")
    metadata = capture.finish("accepted", ended_monotonic_ns=12)

    attempt = tmp_path / "attempt_01"
    assert capture.writes_complete
    assert sorted(path.name for path in attempt.iterdir()) == ["attempt.json"]
    manifest = json.loads((attempt / "attempt.json").read_text(encoding="utf-8"))
    assert manifest == metadata
    assert manifest["artifact_schema_version"] == 2
    assert manifest["status"] == "accepted"
    assert manifest["ended_monotonic_ns"] == 12
