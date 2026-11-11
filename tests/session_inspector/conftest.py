from __future__ import annotations

import json
from pathlib import Path

import pytest


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
    ) -> Path:
        root = tmp_path / name
        root.mkdir()
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
                "environment": {"receiver_ids": {"aa": "rx-1"}},
            },
        )
        for ordinal, attempt_number, attempt_status in attempts:
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
                },
            )
            data_root = attempt / "receivers" / "rx-1"
            data_root.mkdir(parents=True, exist_ok=True)
            (data_root / "csi.csv").write_text("header\n", encoding="utf-8")
            (data_root / "radio_timing.csv").write_text("sequence\n", encoding="utf-8")
            (data_root / "usb_clock_sync.csv").write_text("sync_id\n", encoding="utf-8")
        return root

    return create
