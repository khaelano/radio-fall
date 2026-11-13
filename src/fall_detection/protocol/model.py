"""Dataclasses and error type for versioned collection protocols."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
