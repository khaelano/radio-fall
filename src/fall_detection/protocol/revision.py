"""Revise the remaining trial queue of a protocol while a session records.

A revision keeps the first ``locked`` trials, the ones already recorded or in
progress, exactly as they were, and replaces the rest with an edited queue:
trials may be reordered, removed, duplicated, or have their label, title,
instruction and phase timing changed.

Trial ordinals stay execution positions, so only trials without attempts are
renumbered. A scenario keeps its id when every remaining occurrence still has
its first occurrence's definition; trials given a different definition move to
a new scenario ``<id>__rev<revision>`` whose attributes name the original. A
recorded trial therefore never changes its planned label in a later revision.
The result is an ordinary protocol with an explicit ``trial_sequence``.

Trials may also come from scenarios the session protocol does not contain: from
another protocol file (:func:`adopt_scenario`) or defined by the operator
(:func:`custom_scenario`). They join their block when the session has it, or a
new block at the end. :func:`standalone_protocol` turns an edited queue into a
new protocol file for later sessions.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .loader import _scenario_source, _slug, protocol_from_mapping
from .model import CollectionProtocol, ProtocolError, Scenario, Trial

EDITABLE_FIELDS = (
    "activity_label",
    "title",
    "instruction",
    "countdown_seconds",
    "action_seconds",
    "recovery_seconds",
)
_TEXT_FIELDS = {"activity_label", "title", "instruction"}


@dataclass(frozen=True)
class DraftTrial:
    """One trial of an edited queue.

    Attributes:
        scenario: The scenario the trial came from.
        changes: Replacement values for some of :data:`EDITABLE_FIELDS`.
        origin: Ordinal of the trial in the protocol being revised, or None
            for a trial added by duplication or from another scenario.
    """

    scenario: Scenario
    changes: Mapping[str, Any] = field(default_factory=dict)
    origin: int | None = None

    def value(self, name: str) -> Any:
        """Return the effective value of one editable field."""
        return self.changes.get(name, getattr(self.scenario, name))

    def effective(self) -> Scenario:
        """Return the scenario with the changes applied."""
        return (
            replace(self.scenario, **dict(self.changes))
            if self.changes
            else self.scenario
        )


def same_trials(left: Sequence[Trial], right: Sequence[Trial]) -> bool:
    """Whether two trial lists define the same trials in the same order.

    A scenario's ``repetitions`` is the protocol's count of its trials, which a
    revision may change; it is not part of what a recorded trial was.
    """
    return len(left) == len(right) and all(
        (a.ordinal, a.repetition, replace(a.scenario, repetitions=0))
        == (b.ordinal, b.repetition, replace(b.scenario, repetitions=0))
        for a, b in zip(left, right, strict=True)
    )


def draft_queue(protocol: CollectionProtocol) -> list[DraftTrial]:
    """Return the protocol's trials as an editable queue."""
    return [DraftTrial(trial.scenario, {}, trial.ordinal) for trial in protocol.trials]


def validate_change(name: str, value: Any) -> Any:
    """Normalize one edited field value.

    Raises:
        ProtocolError: The field is not editable or the value is invalid.
    """
    if name not in EDITABLE_FIELDS:
        raise ProtocolError(f"{name} cannot be edited")
    if name in _TEXT_FIELDS:
        if not isinstance(value, str) or not value.strip():
            raise ProtocolError(f"{name.replace('_', ' ')} cannot be empty")
        return value.strip()
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"{name.replace('_', ' ')} must be a number") from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise ProtocolError(f"{name.replace('_', ' ')} must be zero or more")
    if name == "action_seconds" and seconds <= 0:
        raise ProtocolError("action seconds must be greater than zero")
    return seconds


def _definition(scenario: Scenario) -> tuple[Any, ...]:
    return tuple(getattr(scenario, name) for name in EDITABLE_FIELDS)


def _identity(scenario: Scenario) -> Scenario:
    """A scenario without its protocol-level trial count, for comparison."""
    return replace(scenario, repetitions=0)


def protocol_scenarios(protocol: CollectionProtocol) -> list[Scenario]:
    """Return every scenario of a protocol in block order."""
    return [scenario for _id, _title, group in protocol.blocks for scenario in group]


def adopt_scenario(
    scenario: Scenario, known: Iterable[Scenario], *, source_protocol_id: str
) -> Scenario:
    """Fit a scenario from another protocol into a session's ids and blocks.

    An identical scenario already known is returned as is, so its trials are
    more trials of it. Otherwise a clashing scenario id or block id gets a
    suffix naming the source protocol, and the attributes record that source.

    Args:
        scenario: Scenario from the source protocol.
        known: Scenarios of the session protocol and of the edited queue.
        source_protocol_id: Id of the protocol the scenario comes from.

    Returns:
        The scenario to add to the edited queue.
    """
    known = list(known)
    for candidate in known:
        if _identity(candidate) == _identity(scenario):
            return candidate
    ids = {candidate.id for candidate in known}
    blocks = {candidate.block_id: candidate.block_title for candidate in known}
    suffix = _slug(source_protocol_id)
    block_id = scenario.block_id
    if blocks.get(block_id, scenario.block_title) != scenario.block_title:
        block_id = _unique_id(f"{block_id}--{suffix}", set(blocks))
    scenario_id = scenario.id
    if scenario_id in ids:
        scenario_id = _unique_id(f"{scenario_id}__{suffix}", ids)
    attributes = dict(scenario.attributes)
    attributes.setdefault("added_from_protocol", source_protocol_id)
    return replace(scenario, id=scenario_id, block_id=block_id, attributes=attributes)


def custom_scenario(
    known: Iterable[Scenario],
    *,
    title: str,
    activity_label: str,
    instruction: str,
    countdown_seconds: float,
    action_seconds: float,
    recovery_seconds: float,
    block_id: str,
    block_title: str,
) -> Scenario:
    """Define a scenario the operator adds while recording.

    Args:
        known: Scenarios of the session protocol and of the edited queue.
        title: Display title; also the source of the scenario id.
        activity_label: Planned label of its trials.
        instruction: Performer instruction.
        countdown_seconds: Countdown before the action.
        action_seconds: Action phase length; must be positive.
        recovery_seconds: Recovery phase length.
        block_id: Block to place the scenario in.
        block_title: Title of that block.

    Returns:
        A new scenario with a unique ``custom__<title>`` id.

    Raises:
        ProtocolError: A field is empty or a timing is invalid.
    """
    values = {
        "title": title,
        "activity_label": activity_label,
        "instruction": instruction,
        "countdown_seconds": countdown_seconds,
        "action_seconds": action_seconds,
        "recovery_seconds": recovery_seconds,
    }
    values = {name: validate_change(name, value) for name, value in values.items()}
    if not block_id.strip() or not block_title.strip():
        raise ProtocolError("choose a block for the new scenario")
    ids = {scenario.id for scenario in known}
    return Scenario(
        id=_unique_id(f"custom__{_slug(values['title'])}", ids),
        repetitions=1,
        block_id=block_id.strip(),
        block_title=block_title.strip(),
        attributes={"added_by_operator": True},
        **values,
    )


def standalone_protocol(
    protocol: CollectionProtocol,
    *,
    protocol_id: str,
    title: str,
    derived_from: Mapping[str, Any],
) -> CollectionProtocol:
    """Turn a (revised) protocol into a new protocol for later sessions.

    The trial order, scenarios and timing are kept; the protocol gets its own
    id and title, and ``derived_from`` records where it came from.

    Raises:
        ProtocolError: The id or title is empty.
    """
    source = dict(protocol.source)
    # Blocks are explicit, so manifest paths relative to another file would mislead.
    source.pop("scenario_manifests", None)
    source["protocol_id"] = protocol_id
    source["title"] = title
    source["derived_from"] = dict(derived_from)
    return protocol_from_mapping(source)


def _unique_id(base: str, taken: set[str]) -> str:
    candidate, suffix = base, 2
    while candidate in taken:
        candidate = f"{base}_{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def revise_protocol(
    protocol: CollectionProtocol,
    queue: Sequence[DraftTrial],
    *,
    locked: int,
    revision: int,
) -> CollectionProtocol:
    """Build the revised protocol for an edited queue.

    Args:
        protocol: The protocol the session currently follows.
        queue: The complete edited queue, locked trials first.
        locked: Number of leading trials that must not change.
        revision: Revision number, used to name scenarios that fork.

    Returns:
        A validated protocol with the same id, title and timing defaults.

    Raises:
        ProtocolError: The queue changes a locked trial or a field is invalid.
    """
    if not 0 <= locked <= len(protocol.trials) or len(queue) < locked:
        raise ProtocolError("the edited queue must keep every recorded trial")
    for index in range(locked):
        trial = protocol.trials[index]
        draft = queue[index]
        if draft.origin != trial.ordinal or draft.effective() != trial.scenario:
            raise ProtocolError(f"trial {trial.ordinal} is recorded and cannot change")
    if not queue:
        raise ProtocolError("a protocol needs at least one trial")
    session = {scenario.id: scenario for scenario in protocol_scenarios(protocol)}
    introduced: dict[str, Scenario] = {}
    for draft in queue:
        for name, value in draft.changes.items():
            if validate_change(name, value) != value:
                raise ProtocolError(f"invalid {name} value {value!r}")
        scenario = draft.scenario
        known = session.get(scenario.id) or introduced.setdefault(scenario.id, scenario)
        if _identity(known) != _identity(scenario):
            raise ProtocolError(
                f"two different scenarios use the id {scenario.id!r}; add it with "
                "adopt_scenario so it gets its own id"
            )

    # Each original id keeps the definition of its first occurrence.
    taken = set(session) | set(introduced)
    kept: dict[str, Scenario] = {}
    forks: dict[str, dict[tuple[Any, ...], Scenario]] = {}
    sequence: list[str] = []
    for draft in queue:
        scenario = draft.effective()
        original = draft.scenario.id
        base = kept.setdefault(original, scenario)
        if _definition(scenario) == _definition(base):
            sequence.append(original)
            continue
        variants = forks.setdefault(original, {})
        fork = variants.get(_definition(scenario))
        if fork is None:
            attributes = dict(scenario.attributes)
            root = attributes.setdefault("revised_from", original)
            attributes["protocol_revision"] = revision
            fork = replace(
                scenario,
                id=_unique_id(f"{root}__rev{revision}", taken),
                attributes=attributes,
            )
            variants[_definition(scenario)] = fork
        sequence.append(fork.id)

    counts: dict[str, int] = {}
    for scenario_id in sequence:
        counts[scenario_id] = counts.get(scenario_id, 0) + 1
    blocks: dict[str, dict[str, Any]] = {}

    def emit(block_id: str, title: str, original: str) -> None:
        block = blocks.setdefault(
            block_id, {"id": block_id, "title": title, "scenarios": []}
        )
        variants = [kept[original]] if original in kept else []
        variants += list(forks.get(original, {}).values())
        for scenario in variants:
            if counts.get(scenario.id):
                rendered = _scenario_source(scenario)
                rendered["repetitions"] = counts[scenario.id]
                if original not in session:
                    rendered["attributes"].setdefault("protocol_revision", revision)
                block["scenarios"].append(rendered)

    for block_id, title, group in protocol.blocks:
        blocks.setdefault(block_id, {"id": block_id, "title": title, "scenarios": []})
        for original in group:
            emit(block_id, title, original.id)
    # New scenarios join their block when the session has it, else a new one.
    for original, scenario in introduced.items():
        title = blocks.get(scenario.block_id, {}).get("title", scenario.block_title)
        emit(scenario.block_id, title, original)
    source = dict(protocol.source)
    source["blocks"] = [block for block in blocks.values() if block["scenarios"]]
    source["trial_sequence"] = sequence
    revised = protocol_from_mapping(source)
    if not same_trials(revised.trials[:locked], protocol.trials[:locked]):
        raise ProtocolError("the revision would change a recorded trial")
    return revised


def describe_changes(
    protocol: CollectionProtocol, queue: Sequence[DraftTrial], *, locked: int
) -> list[str]:
    """Summarize an edited queue for the session log, one line per kind of change."""
    upcoming = [trial.ordinal for trial in protocol.trials[locked:]]
    drafts = list(queue[locked:])
    kept = [draft.origin for draft in drafts if draft.origin is not None]
    lines = []
    removed = sorted(set(upcoming) - set(kept))
    if removed:
        lines.append(
            f"removed {len(removed)} trial(s): " + ", ".join(str(n) for n in removed)
        )
    session = {scenario.id for scenario in protocol_scenarios(protocol)}
    again = [d for d in drafts if d.origin is None and d.scenario.id in session]
    new = [d for d in drafts if d.origin is None and d.scenario.id not in session]
    if again:
        lines.append(
            f"added {len(again)} more trial(s) of scenarios already in the protocol"
        )
    if new:
        titles = list(dict.fromkeys(draft.scenario.title for draft in new))
        lines.append(
            f"added {len(new)} trial(s) of {len(titles)} new scenario(s): "
            + ", ".join(titles)
        )
    if kept != sorted(kept):
        lines.append("reordered the remaining trials")
    for name in EDITABLE_FIELDS:
        edits: dict[tuple[Any, Any], int] = {}
        for draft in drafts:
            if name in draft.changes and draft.changes[name] != getattr(
                draft.scenario, name
            ):
                key = (getattr(draft.scenario, name), draft.changes[name])
                edits[key] = edits.get(key, 0) + 1
        for (before, after), count in edits.items():
            lines.append(
                f"{name.replace('_', ' ')} {before!r} → {after!r} on {count} trial(s)"
            )
    return lines
