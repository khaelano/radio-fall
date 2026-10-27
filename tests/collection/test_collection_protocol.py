from __future__ import annotations

import json
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


def test_simplified_protocol_uses_four_cardinal_directions():
    parsed = load_protocol(Path("configs/collection/fall_simple.json"))

    assert [len(block[2]) for block in parsed.blocks] == [16, 12, 16, 16, 16, 4]
    assert len(parsed.trials) == 160
    cardinals = {"front", "left", "right", "back"}
    for _block_id, _title, scenarios in parsed.blocks:
        for scenario in scenarios:
            assert scenario.attributes["start_direction"] in cardinals
            end = scenario.attributes["end_direction"]
            assert end is None or end in cardinals
    # Seated backward falls stay out of the simplified protocol.
    sit_to_fall = parsed.blocks[1][2]
    assert {scenario.attributes["end_direction"] for scenario in sit_to_fall} == {
        "front",
        "left",
        "right",
    }


def test_simplified_protocol_reuses_family_ids_so_conditions_stay_comparable():
    full = load_protocol(Path("configs/collection/fall_v1.json"))
    simple = load_protocol(Path("configs/collection/fall_simple.json"))

    assert [block[0] for block in simple.blocks] == [block[0] for block in full.blocks]
    assert simple.protocol_id != full.protocol_id
    assert simple.source_hash != full.source_hash
