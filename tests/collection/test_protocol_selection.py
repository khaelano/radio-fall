from __future__ import annotations

from pathlib import Path

import pytest

from fall_detection.collection.protocol import (
    ProtocolError,
    load_protocol,
    protocol_from_mapping,
    select_blocks,
)


def _protocol():
    return protocol_from_mapping(
        {
            "schema_version": 1,
            "protocol_id": "test-selection",
            "title": "Selection protocol",
            "defaults": {
                "countdown_seconds": 1,
                "action_seconds": 2,
                "recovery_seconds": 1,
            },
            "blocks": [
                {
                    "id": "walk",
                    "title": "Walk",
                    "scenarios": [
                        {
                            "id": "walk-forward",
                            "activity_label": "walk",
                            "title": "Walk forward",
                            "instruction": "Walk forward",
                            "repetitions": 2,
                        },
                        {
                            "id": "walk-back",
                            "activity_label": "walk",
                            "title": "Walk back",
                            "instruction": "Walk back",
                            "repetitions": 1,
                        },
                    ],
                },
                {
                    "id": "sit",
                    "title": "Sit",
                    "scenarios": [
                        {
                            "id": "sit-down",
                            "activity_label": "sit",
                            "title": "Sit down",
                            "instruction": "Sit down",
                            "repetitions": 3,
                        }
                    ],
                },
            ],
        }
    )


def test_select_blocks_keeps_every_trial_for_a_full_selection():
    protocol = _protocol()

    selected = select_blocks(protocol, ["walk", "sit"])

    assert selected is protocol
    assert selected.source_hash == protocol.source_hash
    assert [trial.ordinal for trial in selected.trials] == [1, 2, 3, 4, 5, 6]


def test_select_blocks_filters_and_renumbers_in_protocol_order():
    protocol = _protocol()

    selected = select_blocks(protocol, ["sit"])

    assert [trial.scenario.id for trial in selected.trials] == ["sit-down"] * 3
    assert [trial.ordinal for trial in selected.trials] == [1, 2, 3]
    assert [trial.repetition for trial in selected.trials] == [1, 2, 3]
    assert [block[0] for block in selected.blocks] == ["sit"]


def test_select_blocks_ignores_selection_order_and_duplicates():
    protocol = _protocol()

    selected = select_blocks(protocol, ["sit", "walk", "sit"])

    assert [block[0] for block in selected.blocks] == ["walk", "sit"]
    assert len(selected.trials) == len(protocol.trials)


def test_select_blocks_rewrites_source_and_hash_for_a_subset():
    protocol = _protocol()

    selected = select_blocks(protocol, ["walk"])

    assert [block["id"] for block in selected.source["blocks"]] == ["walk"]
    assert selected.source_hash != protocol.source_hash
    assert len(selected.trials) == 3


def test_selected_source_round_trips_through_the_parser():
    protocol = _protocol()

    selected = select_blocks(protocol, ["walk"])

    reparsed = protocol_from_mapping(selected.source)

    assert [trial.scenario.id for trial in reparsed.trials] == [
        trial.scenario.id for trial in selected.trials
    ]
    assert reparsed.source_hash == selected.source_hash


def test_select_blocks_rejects_unknown_and_empty_selections():
    protocol = _protocol()

    with pytest.raises(ProtocolError, match="unknown scenario block"):
        select_blocks(protocol, ["walk", "run"])
    with pytest.raises(ProtocolError, match="at least one"):
        select_blocks(protocol, [])


def test_select_blocks_preserves_equipment_order_and_snapshot():
    protocol = load_protocol(Path("configs/collection/fall_simple.json"))
    wanted = ["sit-to-walk", "walk-to-sit", "sit-to-fall"]

    selected = select_blocks(protocol, wanted)

    expected = [t for t in protocol.trials if t.scenario.block_id in wanted]
    assert [(t.scenario.id, t.repetition) for t in selected.trials] == [
        (t.scenario.id, t.repetition) for t in expected
    ]
    assert [t.ordinal for t in selected.trials] == list(range(1, 89))
    assert selected.source_hash != protocol.source_hash
    assert protocol_from_mapping(selected.source) == selected
