"""Revise the remaining queue of a protocol while a session records."""

import json
from dataclasses import replace

import pytest
from test_controller import FakeClock, ready_health

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.continuous import (
    ContinuousController,
    continuous_protocol,
)
from fall_detection.collection.controller import (
    OperatorCommand,
    SessionController,
    SessionState,
)
from fall_detection.collection.resume import load_session_resume
from fall_detection.protocol.loader import (
    load_protocol,
    protocol_from_mapping,
    select_blocks,
)
from fall_detection.protocol.model import ProtocolError
from fall_detection.protocol.revision import (
    DraftTrial,
    adopt_scenario,
    custom_scenario,
    describe_changes,
    draft_queue,
    protocol_scenarios,
    revise_protocol,
    same_trials,
    standalone_protocol,
)
from fall_detection.session.models import load_session

ENV = {"receiver_ids": {"00:11:22:33:44:55": "rx-1"}}


def source():
    return {
        "schema_version": 1,
        "protocol_id": "revisable",
        "title": "Revisable protocol",
        "defaults": {
            "countdown_seconds": 1,
            "action_seconds": 2,
            "recovery_seconds": 1,
        },
        "blocks": [
            {
                "id": "a",
                "title": "Block A",
                "scenarios": [
                    {
                        "id": "walk",
                        "activity_label": "walk",
                        "title": "Walk",
                        "instruction": "Walk forward",
                        "repetitions": 2,
                    },
                    {
                        "id": "sit",
                        "activity_label": "sit",
                        "title": "Sit",
                        "instruction": "Sit down",
                    },
                ],
            },
            {
                "id": "b",
                "title": "Block B",
                "scenarios": [
                    {
                        "id": "fall",
                        "activity_label": "fall",
                        "title": "Fall",
                        "instruction": "Fall forward",
                    }
                ],
            },
        ],
    }


def ids(protocol):
    return [(trial.scenario.id, trial.repetition) for trial in protocol.trials]


def test_trial_sequence_orders_trials_and_must_match_repetitions():
    value = source()
    value["trial_sequence"] = ["fall", "walk", "sit", "walk"]
    protocol = protocol_from_mapping(value)
    assert ids(protocol) == [("fall", 1), ("walk", 1), ("sit", 1), ("walk", 2)]
    assert [trial.ordinal for trial in protocol.trials] == [1, 2, 3, 4]

    value["trial_sequence"] = ["fall", "walk", "sit"]
    with pytest.raises(ProtocolError, match="appears 1 times"):
        protocol_from_mapping(value)
    value["trial_sequence"] = ["fall", "walk", "sit", "walk", "jump"]
    with pytest.raises(ProtocolError, match="unknown scenario"):
        protocol_from_mapping(value)


def test_select_blocks_filters_an_explicit_sequence():
    value = source()
    value["trial_sequence"] = ["fall", "walk", "sit", "walk"]
    selected = select_blocks(protocol_from_mapping(value), ["a"])
    assert ids(selected) == [("walk", 1), ("sit", 1), ("walk", 2)]


def test_reorder_remove_and_duplicate_renumber_only_the_remaining_trials():
    protocol = protocol_from_mapping(source())  # walk 1, walk 2, sit, fall
    queue = draft_queue(protocol)
    edited = [queue[0], queue[3], queue[1], DraftTrial(queue[3].scenario)]

    revised = revise_protocol(protocol, edited, locked=1, revision=1)

    assert ids(revised) == [("walk", 1), ("fall", 1), ("walk", 2), ("fall", 2)]
    assert revised.trials[0] == protocol.trials[0]
    assert revised.protocol_id == protocol.protocol_id
    assert revised.source_hash != protocol.source_hash
    assert [b[0] for b in revised.blocks] == ["a", "b"]  # "sit" was removed
    assert describe_changes(protocol, edited, locked=1) == [
        "removed 1 trial(s): 3",
        "added 1 more trial(s) of scenarios already in the protocol",
        "reordered the remaining trials",
    ]


def test_editing_a_scenario_without_recorded_trials_keeps_its_id():
    protocol = protocol_from_mapping(source())
    queue = draft_queue(protocol)
    queue[3] = replace(queue[3], changes={"activity_label": "fall_forward"})

    revised = revise_protocol(protocol, queue, locked=1, revision=1)

    assert revised.trials[3].scenario.id == "fall"
    assert revised.trials[3].scenario.activity_label == "fall_forward"


def test_editing_a_scenario_with_a_recorded_trial_forks_it():
    protocol = protocol_from_mapping(source())
    queue = draft_queue(protocol)
    queue[1] = replace(
        queue[1], changes={"activity_label": "walk_slow", "action_seconds": 4.0}
    )

    revised = revise_protocol(protocol, queue, locked=1, revision=3)

    fork = revised.trials[1].scenario
    assert same_trials(revised.trials[:1], protocol.trials[:1])
    assert revised.trials[0].scenario.repetitions == 1  # walk 2 moved to the fork
    assert fork.id == "walk__rev3"
    assert (fork.activity_label, fork.action_seconds) == ("walk_slow", 4.0)
    assert fork.attributes == {"revised_from": "walk", "protocol_revision": 3}
    assert revised.trials[1].repetition == 1
    assert describe_changes(protocol, queue, locked=1) == [
        "activity label 'walk' → 'walk_slow' on 1 trial(s)",
        "action seconds 2.0 → 4.0 on 1 trial(s)",
    ]
    # Without recorded trials of its own, the fork is edited in place ...
    again = draft_queue(revised)
    again[1] = replace(again[1], changes={"activity_label": "walk_fast"})
    in_place = revise_protocol(revised, again, locked=1, revision=4)
    assert in_place.trials[1].scenario.id == "walk__rev3"
    # ... and once recorded, a further fork is named after the original id.
    again = draft_queue(revised)
    again.append(DraftTrial(again[1].scenario, {"activity_label": "walk_fast"}))
    forked = revise_protocol(revised, again, locked=2, revision=4)
    assert forked.trials[-1].scenario.id == "walk__rev4"
    assert forked.trials[-1].scenario.attributes["revised_from"] == "walk"


def test_revision_refuses_to_touch_locked_trials():
    protocol = protocol_from_mapping(source())
    queue = draft_queue(protocol)
    with pytest.raises(ProtocolError, match="trial 1 is recorded"):
        revise_protocol(protocol, queue[1:], locked=1, revision=1)
    queue[0] = replace(queue[0], changes={"title": "Changed"})
    with pytest.raises(ProtocolError, match="trial 1 is recorded"):
        revise_protocol(protocol, queue, locked=1, revision=1)
    queue = draft_queue(protocol)
    queue[2] = replace(queue[2], changes={"action_seconds": 0.0})
    with pytest.raises(ProtocolError, match="greater than zero"):
        revise_protocol(protocol, queue, locked=1, revision=1)


def controller(tmp_path, clock, protocol=None):
    return SessionController(
        protocol or protocol_from_mapping(source()),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1e9),
        session_id_factory=lambda: "session",
        environment=dict(ENV),
    )


def record_and_accept(c, clock):
    c.dispatch(OperatorCommand.START_TRIAL)
    for step in (1, 2, 1):
        clock.advance(step)
        c.tick()
    c.dispatch(OperatorCommand.ACCEPT)


def test_revision_is_saved_and_the_next_attempt_follows_it(tmp_path):
    clock = FakeClock()
    c = controller(tmp_path, clock)
    c.start_session(SessionMetadata("p01"))
    c.update_health(ready_health())
    record_and_accept(c, clock)
    assert c.protocol_locked_trials == 1
    queue = draft_queue(c.protocol)
    queue = [
        queue[0],
        replace(queue[3], changes={"activity_label": "fall_forward"}),
        queue[1],
        queue[2],
    ]
    revised = revise_protocol(c.protocol, queue, locked=1, revision=1)

    snapshot = c.revise_protocol(revised, note="mattress arrived early", changes=["x"])

    root = tmp_path / "session"
    assert snapshot.trial.scenario.id == "fall"
    assert "changes apply from trial 2" in snapshot.message
    manifest = json.loads((root / "session.json").read_text())
    (entry,) = manifest["protocol_revisions"]
    assert entry["path"] == "protocol_revisions/001.json"
    assert entry["effective_from_trial"] == 2
    assert entry["note"] == "mattress arrived early"
    assert manifest["protocol_hash"] != entry["protocol_hash"]
    assert (
        json.loads((root / "protocol.json").read_text())["blocks"][0]["scenarios"][0][
            "id"
        ]
        == "walk"
    )  # the starting protocol is never rewritten
    revised_source = json.loads((root / "protocol_revisions/001.json").read_text())
    assert revised_source["trial_sequence"] == ["walk", "fall", "walk", "sit"]

    record_and_accept(c, clock)
    attempt = json.loads((root / "trials/002_fall/attempt_01/attempt.json").read_text())
    assert attempt["activity_label"] == "fall_forward"
    c.dispatch(OperatorCommand.END_SESSION)
    events = [
        json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()
    ]
    assert [e["revision"] for e in events if e["kind"] == "protocol_revised"] == [1]

    session = load_session(root)
    assert session.protocol_hash == manifest["protocol_hash"]
    assert len(session.protocol_revisions) == 1
    assert not session.warnings
    trial = next(t for t in session.trials if t.ordinal == 2)
    assert (trial.scenario_id, trial.activity_label) == ("fall", "fall_forward")
    assert trial.attempts[0].activity_label == "fall_forward"

    saved = load_session_resume(root)
    assert saved.protocol.source_hash == entry["protocol_hash"]
    assert saved.trial_index == 2
    resumed = controller(tmp_path, clock, saved.protocol)
    resumed.resume_session(root)
    assert resumed.protocol_revisions == 1
    resumed.dispatch(OperatorCommand.END_SESSION)


def test_current_trial_locks_once_it_has_an_attempt_and_edits_wait_between_trials(
    tmp_path,
):
    clock = FakeClock()
    c = controller(tmp_path, clock)
    c.start_session(SessionMetadata("p01"))
    c.update_health(ready_health())
    assert c.protocol_locked_trials == 0 and c.can_revise_protocol

    c.dispatch(OperatorCommand.START_TRIAL)
    assert not c.can_revise_protocol
    with pytest.raises(RuntimeError, match="between trials"):
        c.revise_protocol(c.protocol)
    clock.advance(1)
    c.tick()
    c.dispatch(OperatorCommand.ABORT)
    assert c.state is SessionState.REVIEW and c.protocol_locked_trials == 1
    c.dispatch(OperatorCommand.RETRY)
    # Still locked in READY: the trial owns an attempt folder.
    assert c.state is SessionState.READY and c.protocol_locked_trials == 1
    queue = draft_queue(c.protocol)
    moved = protocol_from_mapping(
        {**source(), "trial_sequence": ["walk", "fall", "walk", "sit"]}
    )
    del queue
    with pytest.raises(ValueError, match="recorded trials"):
        c.revise_protocol(
            protocol_from_mapping(
                {**source(), "trial_sequence": ["sit", "walk", "walk", "fall"]}
            )
        )
    c.revise_protocol(moved)
    assert c.protocol.trials[1].scenario.id == "fall"
    c.dispatch(OperatorCommand.END_SESSION)


def test_removing_every_remaining_trial_completes_the_session(tmp_path):
    clock = FakeClock()
    c = controller(tmp_path, clock)
    c.start_session(SessionMetadata("p01"))
    c.update_health(ready_health())
    record_and_accept(c, clock)
    queue = draft_queue(c.protocol)
    revised = revise_protocol(c.protocol, queue[:1], locked=1, revision=1)

    snapshot = c.revise_protocol(revised)

    assert snapshot.state is SessionState.COMPLETE
    manifest = json.loads((tmp_path / "session/session.json").read_text())
    assert manifest["status"] == "complete"


def test_continuous_sessions_have_no_editable_queue(tmp_path):
    clock = FakeClock()
    c = ContinuousController(
        continuous_protocol(10, 3),
        tmp_path,
        clock=clock,
        monotonic_ns=lambda: int(clock.value * 1e9),
        session_id_factory=lambda: "session",
        environment=dict(ENV),
    )
    c.start_session(SessionMetadata("p01"))
    assert not c.can_revise_protocol
    with pytest.raises(RuntimeError, match="continuous"):
        c.revise_protocol(c.protocol)
    c.dispatch(OperatorCommand.END_SESSION)


def other_protocol():
    """A second protocol whose ids and blocks partly clash with ``source()``."""
    return protocol_from_mapping(
        {
            "schema_version": 1,
            "protocol_id": "other",
            "title": "Other protocol",
            "defaults": {
                "countdown_seconds": 2,
                "action_seconds": 4,
                "recovery_seconds": 2,
            },
            "blocks": [
                {
                    "id": "a",
                    "title": "Another block A",
                    "scenarios": [
                        {
                            "id": "walk",
                            "activity_label": "walk_fast",
                            "title": "Fast walk",
                            "instruction": "Walk quickly",
                        },
                        {
                            "id": "kneel",
                            "activity_label": "kneel",
                            "title": "Kneel",
                            "instruction": "Kneel down",
                        },
                    ],
                }
            ],
        }
    )


def test_adopting_a_clashing_scenario_renames_its_id_and_block():
    protocol = protocol_from_mapping(source())
    known = protocol_scenarios(protocol)
    walk, kneel = protocol_scenarios(other_protocol())

    adopted_walk = adopt_scenario(walk, known, source_protocol_id="other")
    adopted_kneel = adopt_scenario(kneel, known, source_protocol_id="other")

    assert adopted_walk.id == "walk__other"
    assert adopted_kneel.id == "kneel"
    for adopted in (adopted_walk, adopted_kneel):
        assert adopted.block_id == "a--other"  # block "a" has another title here
        assert adopted.attributes["added_from_protocol"] == "other"
    # A scenario identical to a known one is the known one.
    assert adopt_scenario(known[2], known, source_protocol_id="revisable") is known[2]


def test_added_scenarios_join_their_block_or_a_new_one_at_the_end():
    protocol = protocol_from_mapping(source())
    known = protocol_scenarios(protocol)
    kneel = adopt_scenario(
        protocol_scenarios(other_protocol())[1], known, source_protocol_id="other"
    )
    custom = custom_scenario(
        known,
        title="Lie down",
        activity_label="lie",
        instruction="Lie on the mattress",
        countdown_seconds=1,
        action_seconds=6,
        recovery_seconds=1,
        block_id="b",
        block_title="Block B",
    )
    queue = draft_queue(protocol)
    queue = queue[:2] + [DraftTrial(custom), DraftTrial(kneel)] + queue[2:]
    queue.append(DraftTrial(kneel, {"activity_label": "kneel_slow"}))

    revised = revise_protocol(protocol, queue, locked=1, revision=2)

    assert ids(revised) == [
        ("walk", 1),
        ("walk", 2),
        ("custom__lie_down", 1),
        ("kneel", 1),
        ("sit", 1),
        ("fall", 1),
        ("kneel__rev2", 1),
    ]
    blocks = {block_id: [s.id for s in group] for block_id, _t, group in revised.blocks}
    assert blocks == {
        "a": ["walk", "sit"],
        "b": ["fall", "custom__lie_down"],
        "a--other": ["kneel", "kneel__rev2"],
    }
    added = revised.trials[2].scenario
    assert added.attributes == {"added_by_operator": True, "protocol_revision": 2}
    assert revised.trials[3].scenario.attributes["added_from_protocol"] == "other"
    assert describe_changes(protocol, queue, locked=1) == [
        "added 3 trial(s) of 2 new scenario(s): Lie down, Kneel",
        "activity label 'kneel' → 'kneel_slow' on 1 trial(s)",
    ]
    # The next revision treats the added scenarios as part of the protocol.
    again = revise_protocol(revised, draft_queue(revised), locked=3, revision=3)
    assert same_trials(again.trials, revised.trials)


def test_revision_rejects_two_scenarios_with_one_id():
    protocol = protocol_from_mapping(source())
    clash = protocol_scenarios(other_protocol())[0]  # id "walk", other definition
    with pytest.raises(ProtocolError, match="two different scenarios"):
        revise_protocol(
            protocol, [*draft_queue(protocol), DraftTrial(clash)], locked=0, revision=1
        )


def test_custom_scenarios_need_every_field_and_get_unique_ids():
    known = protocol_scenarios(protocol_from_mapping(source()))
    values = {
        "title": "Walk",
        "activity_label": "walk",
        "instruction": "Walk",
        "countdown_seconds": 0,
        "action_seconds": 3,
        "recovery_seconds": 0,
        "block_id": "a",
        "block_title": "Block A",
    }
    first = custom_scenario(known, **values)
    second = custom_scenario([*known, first], **values)
    assert (first.id, second.id) == ("custom__walk", "custom__walk_2")
    with pytest.raises(ProtocolError, match="instruction cannot be empty"):
        custom_scenario(known, **{**values, "instruction": " "})


def test_standalone_protocol_is_a_new_protocol_with_provenance(tmp_path):
    protocol = protocol_from_mapping(source())
    queue = draft_queue(protocol)
    revised = revise_protocol(
        protocol, [queue[3], queue[0], queue[1]], locked=0, revision=1
    )

    saved = standalone_protocol(
        revised,
        protocol_id="revisable-short",
        title="Short",
        derived_from={"protocol_id": "revisable", "session_id": "s1"},
    )

    path = tmp_path / "short.json"
    path.write_text(json.dumps(saved.source))
    loaded = load_protocol(path)
    assert (loaded.protocol_id, loaded.title) == ("revisable-short", "Short")
    assert ids(loaded) == [("fall", 1), ("walk", 1), ("walk", 2)]
    assert loaded.source["derived_from"] == {
        "protocol_id": "revisable",
        "session_id": "s1",
    }
    assert loaded.source_hash == saved.source_hash


def test_a_trial_of_an_added_scenario_records_reads_back_and_resumes(tmp_path):
    clock = FakeClock()
    c = controller(tmp_path, clock)
    c.start_session(SessionMetadata("p01"))
    c.update_health(ready_health())
    record_and_accept(c, clock)
    kneel = adopt_scenario(
        protocol_scenarios(other_protocol())[1],
        protocol_scenarios(c.protocol),
        source_protocol_id="other",
    )
    queue = draft_queue(c.protocol)
    revised = revise_protocol(
        c.protocol, [queue[0], DraftTrial(kneel), *queue[1:]], locked=1, revision=1
    )
    c.revise_protocol(revised, note="extra kneeling trial")
    # The adopted scenario keeps its own timing: 2 s, 4 s and 2 s.
    c.dispatch(OperatorCommand.START_TRIAL)
    for step in (2, 4, 2):
        clock.advance(step)
        c.tick()
    c.dispatch(OperatorCommand.ACCEPT)
    c.dispatch(OperatorCommand.END_SESSION)

    root = tmp_path / "session"
    attempt = json.loads(
        (root / "trials/002_kneel/attempt_01/attempt.json").read_text()
    )
    assert (attempt["scenario_id"], attempt["activity_label"]) == ("kneel", "kneel")
    session = load_session(root)
    trial = next(t for t in session.trials if t.ordinal == 2)
    assert (trial.title, trial.block_title) == ("Kneel", "Another block A")
    assert trial.attempts[0].status == "accepted"
    assert len(session.trials) == 5 and not session.warnings
    assert load_session_resume(root).trial_index == 2
