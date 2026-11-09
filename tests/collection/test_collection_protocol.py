from __future__ import annotations

import json
from itertools import groupby
from pathlib import Path

import pytest

from fall_detection.collection.protocol import (
    ProtocolError,
    load_protocol,
    protocol_from_mapping,
)


def protocol(**overrides):
    value = {
        "schema_version": 1,
        "protocol_id": "test",
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
                        "id": "one",
                        "activity_label": "walk",
                        "title": "Walk",
                        "instruction": "Walk forward",
                        "repetitions": 2,
                    },
                    {
                        "id": "two",
                        "activity_label": "fall",
                        "title": "Fall",
                        "instruction": "Perform the fall",
                    },
                ],
            }
        ],
    }
    value.update(overrides)
    return value


def test_protocol_expands_repetitions_in_declared_order():
    parsed = protocol_from_mapping(protocol())

    assert [trial.ordinal for trial in parsed.trials] == [1, 2, 3]
    assert [trial.scenario.id for trial in parsed.trials] == ["one", "one", "two"]
    assert [trial.repetition for trial in parsed.trials] == [1, 2, 1]
    assert len(parsed.source_hash) == 64


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("schema_version", 2, "only version 1"),
        ("protocol_id", "", "non-empty string"),
        (
            "defaults",
            {"countdown_seconds": 1, "action_seconds": 2},
            "recovery_seconds",
        ),
    ],
)
def test_protocol_rejects_invalid_fields(path, value, message):
    source = protocol()
    source[path] = value

    with pytest.raises(ProtocolError, match=message):
        protocol_from_mapping(source)


def test_protocol_rejects_unknown_and_duplicate_fields():
    source = protocol()
    source["unexpected"] = True
    with pytest.raises(ProtocolError, match="unknown field"):
        protocol_from_mapping(source)

    source = protocol()
    source["blocks"][0]["scenarios"].append(
        {
            "id": "one",
            "activity_label": "other",
            "title": "Duplicate",
            "instruction": "Duplicate",
        }
    )
    with pytest.raises(ProtocolError, match="duplicate id"):
        protocol_from_mapping(source)


def test_protocol_loads_direction_manifest_and_expands_cartesian_product(tmp_path):
    manifest_path = tmp_path / "walk_to_sit.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "family_id": "walk-to-sit",
                "title": "Walk to sit",
                "activity_label": "walk_to_sit",
                "instruction_template": "Walk {start_direction}, then sit {end_direction}.",
                "start_directions": ["front", "left"],
                "end_directions": ["front", "right"],
                "repetitions": 2,
                "direction_frame": "participant_relative",
            }
        ),
        encoding="utf-8",
    )
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_id": "manifest-test",
                "title": "Manifest test",
                "defaults": {
                    "countdown_seconds": 1,
                    "action_seconds": 2,
                    "recovery_seconds": 1,
                },
                "scenario_manifests": [manifest_path.name],
            }
        ),
        encoding="utf-8",
    )

    parsed = load_protocol(protocol_path)

    assert len(parsed.blocks) == 1
    assert len(parsed.blocks[0][2]) == 4
    assert len(parsed.trials) == 8
    assert parsed.blocks[0][2][0].id == "walk-to-sit__start_front__end_front"
    assert parsed.blocks[0][2][0].attributes["direction_frame"] == "participant_relative"
    assert parsed.source["resolved_manifest_sources"][0]["path"] == manifest_path.name
    assert len(parsed.source_hash) == 64


def test_directional_protocol_has_expected_matrix_size():
    parsed = load_protocol(Path("configs/collection/fall_v1.json"))

    assert [len(block[2]) for block in parsed.blocks] == [64, 24, 64, 64, 64, 8]
    assert len(parsed.trials) == 576
    assert parsed.blocks[-1][2][0].attributes["end_direction"] is None


def test_simplified_protocol_has_requested_transition_matrix():
    parsed = load_protocol(Path("configs/collection/fall_simple.json"))
    directions = {"front", "right", "back", "left"}
    expected = {
        "walk-to-stand": (directions, {None}),
        "walk-to-sit": (directions, directions),
        "walk-to-fall": (directions, directions),
        "stand-to-walk": ({None}, directions),
        "stand-to-sit": (directions, directions),
        "stand-to-fall": (directions, directions),
        "sit-to-walk": (directions, directions),
        "sit-to-stand": (directions, directions),
        "sit-to-fall": (directions, {"front", "right", "left"}),
    }

    assert parsed.protocol_id == "fall-collection-simple-v2"
    assert len(parsed.trials) == 232
    assert {block_id for block_id, _title, _scenarios in parsed.blocks} == set(expected)
    for block_id, _title, scenarios in parsed.blocks:
        starts, ends = expected[block_id]
        assert len(scenarios) == len(starts) * len(ends)
        assert {
            (s.attributes["start_direction"], s.attributes["end_direction"])
            for s in scenarios
        } == {(start, end) for start in starts for end in ends}
        assert all(s.repetitions == 2 for s in scenarios)
        assert all(s.action_seconds == 8 for s in scenarios)
    assert [trial.ordinal for trial in parsed.trials] == list(range(1, 233))


def test_simplified_protocol_groups_equipment_and_chair_orientations():
    parsed = load_protocol(Path("configs/collection/fall_simple.json"))
    setups = [
        (key, len(list(group)))
        for key, group in groupby(
            parsed.trials,
            key=lambda trial: (
                trial.scenario.attributes["equipment"],
                trial.scenario.attributes.get("chair_direction"),
            ),
        )
    ]

    assert setups == [
        (("none", None), 16),
        *(
            (("chair", direction), 32)
            for direction in ["front", "right", "back", "left"]
        ),
        *(
            (("chair_and_mattress", direction), 6)
            for direction in ["left", "back", "right", "front"]
        ),
        (("mattress", None), 64),
    ]
    # Chair orientation follows the seated side of each transition.
    for trial in parsed.trials:
        attrs = trial.scenario.attributes
        if attrs["equipment"] in {"chair", "chair_and_mattress"}:
            side = "start" if attrs["family_id"].startswith("sit-") else "end"
            assert attrs["chair_direction"] == attrs[f"{side}_direction"]
    # Each walking/standing fall pair shares a setup before moving to the next.
    falls = [
        t for t in parsed.trials if t.scenario.attributes["equipment"] == "mattress"
    ]
    for offset in range(0, len(falls), 4):
        group = falls[offset : offset + 4]
        assert {t.scenario.block_id for t in group} == {"walk-to-fall", "stand-to-fall"}
        pairs = {
            (
                t.scenario.attributes["start_direction"],
                t.scenario.attributes["end_direction"],
            )
            for t in group
        }
        assert len(pairs) == 1
    for first, second in zip(parsed.trials[::2], parsed.trials[1::2]):
        assert first.scenario.id == second.scenario.id
        assert (first.repetition, second.repetition) == (1, 2)


def test_simplified_protocol_snapshot_recreates_execution_order():
    parsed = load_protocol(Path("configs/collection/fall_simple.json"))

    restored = protocol_from_mapping(parsed.source)

    assert restored == parsed


def test_equipment_order_rejects_missing_setup_metadata():
    source = protocol(trial_order="equipment")
    with pytest.raises(ProtocolError, match="requires equipment"):
        protocol_from_mapping(source)
    for scenario in source["blocks"][0]["scenarios"]:
        scenario["attributes"] = {"equipment": "chair"}
    with pytest.raises(ProtocolError, match="requires chair_direction"):
        protocol_from_mapping(source)


def test_protocol_rejects_unknown_trial_order():
    with pytest.raises(ProtocolError, match="trial_order"):
        protocol_from_mapping(protocol(trial_order="random"))


def test_simplified_protocol_preserves_ids_for_unchanged_conditions():
    full = load_protocol(Path("configs/collection/fall_v1.json"))
    simple = load_protocol(Path("configs/collection/fall_simple.json"))
    full_ids = {s.id for _, _, scenarios in full.blocks for s in scenarios}
    shared_families = {
        "walk-to-fall", "sit-to-fall", "stand-to-fall", "walk-to-sit", "sit-to-walk"
    }

    for block_id, _title, scenarios in simple.blocks:
        if block_id in shared_families:
            assert {s.id for s in scenarios} <= full_ids
    assert simple.protocol_id != full.protocol_id
    assert simple.source_hash != full.source_hash
