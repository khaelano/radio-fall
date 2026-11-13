"""Synthetic sessions with valid gateway journals for the inspector tests."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from inspector_sessions import (
    ATTEMPT_LENGTH_NS,
    RECEIVERS,
    FrameSpec,
    attempt_origin,
    default_frames,
    write_journal,
)
from journal_builder import mac_text


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def session_factory(tmp_path: Path):
    def create(
        name: str = "session-1",
        *,
        status: str = "complete",
        attempts: tuple[tuple[int, int, str], ...] = (),
        frames: Sequence[FrameSpec] | None = None,
    ) -> Path:
        # ``<data>/raw/sessions/<name>`` keeps derived frame tables in tmp_path.
        root = tmp_path / "raw" / "sessions" / name
        root.mkdir(parents=True)
        protocol = {
            "schema_version": 1,
            "protocol_id": "test-protocol",
            "title": "Test protocol",
            "defaults": {
                "countdown_seconds": 1,
                "action_seconds": 2,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "block",
                    "title": "Block",
                    "scenarios": [
                        {
                            "id": "walk",
                            "activity_label": "walk",
                            "title": "Walk",
                            "instruction": "Walk forward",
                            "repetitions": 2,
                            "attributes": {"start_direction": "front"},
                        }
                    ],
                }
            ],
        }
        write_json(root / "protocol.json", protocol)
        write_json(
            root / "session.json",
            {
                "artifact_schema_version": 2,
                "session_id": name,
                "participant_id": "participant-1",
                "operator": "operator-1",
                "location": "lab",
                "notes": "original",
                "protocol_id": "test-protocol",
                "protocol_hash": "test-hash",
                "started_at_utc": "2026-01-01T00:00:00+00:00",
                "status": status,
                "environment": {
                    "receiver_ids": {mac_text(mac): rx for rx, mac in RECEIVERS.items()}
                },
            },
        )
        for position, (ordinal, attempt_number, attempt_status) in enumerate(attempts):
            attempt = (
                root
                / "trials"
                / f"{ordinal:03d}_walk"
                / f"attempt_{attempt_number:02d}"
            )
            write_json(
                attempt / "attempt.json",
                {
                    "artifact_schema_version": 2,
                    "session_id": name,
                    "trial_ordinal": ordinal,
                    "repetition": ordinal,
                    "scenario_id": "walk",
                    "activity_label": "walk",
                    "status": attempt_status,
                    "started_monotonic_ns": attempt_origin(position),
                    **(
                        {}
                        if attempt_status == "recording"
                        else {
                            "ended_monotonic_ns": attempt_origin(position)
                            + ATTEMPT_LENGTH_NS
                        }
                    ),
                },
            )
        if attempts:
            write_journal(root, default_frames(attempts) if frames is None else frames)
        return root

    return create
