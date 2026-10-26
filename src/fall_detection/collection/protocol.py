"""Versioned collection protocols and deterministic trial expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


class ProtocolError(ValueError):
    """Raised when a collection protocol is malformed."""


@dataclass(frozen=True)
class TimingDefaults:
    """Default durations, in seconds, for each trial phase."""

    countdown_seconds: float
    action_seconds: float
    recovery_seconds: float


@dataclass(frozen=True)
class Scenario:
    """One performer-facing activity definition."""

    id: str
    activity_label: str
    title: str
    instruction: str
    countdown_seconds: float
    action_seconds: float
    recovery_seconds: float
    repetitions: int
    block_id: str
    block_title: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trial:
    """One expanded trial in the protocol's fixed execution order."""

    ordinal: int
    repetition: int
    scenario: Scenario


@dataclass(frozen=True)
class CollectionProtocol:
    """Validated protocol plus its deterministic trial queue."""

    schema_version: int
    protocol_id: str
    title: str
    defaults: TimingDefaults
    blocks: tuple[tuple[str, str, tuple[Scenario, ...]], ...]
    trials: tuple[Trial, ...]
    source: dict[str, Any]
    source_hash: str


_PROTOCOL_KEYS = {
    "schema_version",
    "protocol_id",
    "title",
    "defaults",
    "blocks",
    "scenario_manifests",
    "resolved_manifest_sources",
}
_DEFAULT_KEYS = {"countdown_seconds", "action_seconds", "recovery_seconds"}
_BLOCK_KEYS = {"id", "title", "scenarios"}
_SCENARIO_KEYS = {
    "id",
    "activity_label",
    "title",
    "instruction",
    "repetitions",
    "countdown_seconds",
    "action_seconds",
    "recovery_seconds",
    "attributes",
}
_MANIFEST_KEYS = {
    "schema_version",
    "family_id",
    "title",
    "activity_label",
    "instruction_template",
    "instruction",
    "start_directions",
    "end_directions",
    "repetitions",
    "direction_frame",
    "safety_note",
    "countdown_seconds",
    "action_seconds",
    "recovery_seconds",
}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{path}: expected an object")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{path}: expected a non-empty string")
    return value.strip()


def _duration(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{path}: expected a non-negative number")
    result = float(value)
    if result < 0 or result != result or result == float("inf"):
        raise ProtocolError(f"{path}: expected a finite non-negative number")
    return result


def _positive_count(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ProtocolError(f"{path}: expected a positive integer")
    return value


def _check_keys(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ProtocolError(f"{path}: unknown field(s): {', '.join(unknown)}")


def _slug(value: str) -> str:
    """Return a stable identifier fragment for a direction label."""

    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return result or "unspecified"


def _directions(value: Any, path: str, *, allow_null: bool = False) -> list[str | None]:
    if not isinstance(value, list) or not value:
        raise ProtocolError(f"{path}: expected a non-empty array")
    result: list[str | None] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if item is None and allow_null:
            result.append(None)
            continue
        result.append(_string(item, item_path))
    if len(set(result)) != len(result):
        raise ProtocolError(f"{path}: duplicate direction")
    return result


def _read_json(path: Path, description: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProtocolError(f"unable to read {description} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProtocolError(
            f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}"
        ) from exc
    return _mapping(value, description)


def _expand_manifest(
    manifest: Mapping[str, Any],
    manifest_path: str,
) -> dict[str, Any]:
    """Expand one direction-product manifest into a protocol block."""

    path = f"manifest {manifest_path}"
    _check_keys(manifest, _MANIFEST_KEYS, path)
    if manifest.get("schema_version", 1) != 1:
        raise ProtocolError(f"{path}.schema_version: only version 1 is supported")
    family_id = _string(manifest.get("family_id"), f"{path}.family_id")
    title = _string(manifest.get("title"), f"{path}.title")
    activity_label = _string(
        manifest.get("activity_label"), f"{path}.activity_label"
    )
    template = manifest.get("instruction_template", manifest.get("instruction"))
    template = _string(template, f"{path}.instruction_template")
    start_directions = _directions(
        manifest.get("start_directions"), f"{path}.start_directions"
    )
    raw_end_directions = manifest.get("end_directions")
    if raw_end_directions is None:
        end_directions: list[str | None] = [None]
    else:
        end_directions = _directions(
            raw_end_directions, f"{path}.end_directions", allow_null=True
        )
    repetitions = _positive_count(
        manifest.get("repetitions", 1), f"{path}.repetitions"
    )
    direction_frame = _string(
        manifest.get("direction_frame", "participant_relative"),
        f"{path}.direction_frame",
    )
    raw_safety_note = manifest.get("safety_note")
    safety_note = (
        ""
        if raw_safety_note is None
        else _string(raw_safety_note, f"{path}.safety_note")
    )

    scenarios: list[dict[str, Any]] = []
    for start_direction in start_directions:
        # A null start direction is intentionally disallowed by _directions.
        assert start_direction is not None
        for end_direction in end_directions:
            start_label = start_direction
            end_label = end_direction if end_direction is not None else "no direction"
            try:
                instruction = template.format(
                    start_direction=start_label,
                    end_direction=end_label,
                    start=start_label,
                    end=end_label,
                )
            except (IndexError, KeyError, ValueError) as exc:
                raise ProtocolError(
                    f"{path}.instruction_template: unsupported placeholder: {exc}"
                ) from exc
            scenario_id = f"{family_id}__start_{_slug(start_label)}__end_{_slug(end_label)}"
            scenario_title = f"{title} ({start_label} → {end_label})"
            attributes: dict[str, Any] = {
                "family_id": family_id,
                "manifest_path": manifest_path,
                "start_direction": start_label,
                "end_direction": end_direction,
                "direction_frame": direction_frame,
            }
            if safety_note:
                attributes["safety_note"] = safety_note
            scenario: dict[str, Any] = {
                "id": scenario_id,
                "activity_label": activity_label,
                "title": scenario_title,
                "instruction": instruction,
                "repetitions": repetitions,
                "attributes": attributes,
            }
            for timing_key in (
                "countdown_seconds",
                "action_seconds",
                "recovery_seconds",
            ):
                if timing_key in manifest:
                    scenario[timing_key] = manifest[timing_key]
            scenarios.append(scenario)

    return {"id": family_id, "title": title, "scenarios": scenarios}


def _resolve_manifest_blocks(
    source: Mapping[str, Any], base_dir: Path | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    references = source.get("scenario_manifests")
    if not isinstance(references, list) or not references:
        raise ProtocolError("protocol.scenario_manifests: expected a non-empty array")
    if base_dir is None:
        raise ProtocolError(
            "protocol.scenario_manifests: paths require load_protocol() with a file path"
        )
    blocks: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for index, raw_reference in enumerate(references):
        reference_path = f"protocol.scenario_manifests[{index}]"
        reference = _string(raw_reference, reference_path)
        manifest_path = (base_dir / reference).resolve()
        manifest = _read_json(manifest_path, f"scenario manifest {reference}")
        resolved.append({"path": reference, "source": dict(manifest)})
        blocks.append(_expand_manifest(manifest, reference))
    return blocks, resolved


def _load_source(
    source: Mapping[str, Any], *, base_dir: Path | None = None
) -> CollectionProtocol:
    _check_keys(source, _PROTOCOL_KEYS, "protocol")
    version = source.get("schema_version")
    if version != 1:
        raise ProtocolError("protocol.schema_version: only version 1 is supported")
    protocol_id = _string(source.get("protocol_id"), "protocol.protocol_id")
    title = _string(source.get("title"), "protocol.title")

    defaults = _mapping(source.get("defaults"), "protocol.defaults")
    _check_keys(defaults, _DEFAULT_KEYS, "protocol.defaults")
    timing = TimingDefaults(
        _duration(defaults.get("countdown_seconds"), "protocol.defaults.countdown_seconds"),
        _duration(defaults.get("action_seconds"), "protocol.defaults.action_seconds"),
        _duration(defaults.get("recovery_seconds"), "protocol.defaults.recovery_seconds"),
    )
    if timing.action_seconds <= 0:
        raise ProtocolError("protocol.defaults.action_seconds: must be greater than zero")

    blocks_value = source.get("blocks")
    resolved_source: dict[str, Any] = dict(source)
    if blocks_value is None and source.get("scenario_manifests") is not None:
        blocks_value, resolved_manifests = _resolve_manifest_blocks(source, base_dir)
        resolved_source["blocks"] = blocks_value
        resolved_source["resolved_manifest_sources"] = resolved_manifests
    if not isinstance(blocks_value, list) or not blocks_value:
        raise ProtocolError("protocol.blocks: expected a non-empty array")

    seen_blocks: set[str] = set()
    seen_scenarios: set[str] = set()
    blocks: list[tuple[str, str, tuple[Scenario, ...]]] = []
    trials: list[Trial] = []
    ordinal = 1
    for block_index, raw_block in enumerate(blocks_value):
        block_path = f"protocol.blocks[{block_index}]"
        block = _mapping(raw_block, block_path)
        _check_keys(block, _BLOCK_KEYS, block_path)
        block_id = _string(block.get("id"), f"{block_path}.id")
        block_title = _string(block.get("title"), f"{block_path}.title")
        if block_id in seen_blocks:
            raise ProtocolError(f"{block_path}.id: duplicate id {block_id!r}")
        seen_blocks.add(block_id)
        raw_scenarios = block.get("scenarios")
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise ProtocolError(f"{block_path}.scenarios: expected a non-empty array")

        scenarios: list[Scenario] = []
        for scenario_index, raw_scenario in enumerate(raw_scenarios):
            scenario_path = f"{block_path}.scenarios[{scenario_index}]"
            raw = _mapping(raw_scenario, scenario_path)
            _check_keys(raw, _SCENARIO_KEYS, scenario_path)
            scenario_id = _string(raw.get("id"), f"{scenario_path}.id")
            if scenario_id in seen_scenarios:
                raise ProtocolError(f"{scenario_path}.id: duplicate id {scenario_id!r}")
            seen_scenarios.add(scenario_id)
            raw_attributes = raw.get("attributes", {})
            attributes = _mapping(raw_attributes, f"{scenario_path}.attributes")
            scenario = Scenario(
                id=scenario_id,
                activity_label=_string(
                    raw.get("activity_label"), f"{scenario_path}.activity_label"
                ),
                title=_string(raw.get("title"), f"{scenario_path}.title"),
                instruction=_string(
                    raw.get("instruction"), f"{scenario_path}.instruction"
                ),
                countdown_seconds=_duration(
                    raw.get("countdown_seconds", timing.countdown_seconds),
                    f"{scenario_path}.countdown_seconds",
                ),
                action_seconds=_duration(
                    raw.get("action_seconds", timing.action_seconds),
                    f"{scenario_path}.action_seconds",
                ),
                recovery_seconds=_duration(
                    raw.get("recovery_seconds", timing.recovery_seconds),
                    f"{scenario_path}.recovery_seconds",
                ),
                repetitions=_positive_count(
                    raw.get("repetitions", 1), f"{scenario_path}.repetitions"
                ),
                block_id=block_id,
                block_title=block_title,
                attributes=dict(attributes),
            )
            if scenario.action_seconds <= 0:
                raise ProtocolError(f"{scenario_path}.action_seconds: must be greater than zero")
            scenarios.append(scenario)
            for repetition in range(1, scenario.repetitions + 1):
                trials.append(Trial(ordinal, repetition, scenario))
                ordinal += 1
        blocks.append((block_id, block_title, tuple(scenarios)))

    canonical = json.dumps(resolved_source, sort_keys=True, separators=(",", ":")).encode()
    return CollectionProtocol(
        schema_version=1,
        protocol_id=protocol_id,
        title=title,
        defaults=timing,
        blocks=tuple(blocks),
        trials=tuple(trials),
        source=resolved_source,
        source_hash=hashlib.sha256(canonical).hexdigest(),
    )


def load_protocol(path: Path) -> CollectionProtocol:
    """Read and validate a JSON collection protocol."""

    source = _read_json(path, "protocol")
    return _load_source(source, base_dir=path.parent)


def protocol_from_mapping(source: Mapping[str, Any]) -> CollectionProtocol:
    """Validate an in-memory protocol, primarily for tests and integrations."""

    return _load_source(_mapping(source, "protocol"))
