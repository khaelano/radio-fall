"""Versioned collection protocols and deterministic trial expansion.

This package depends on nothing else in ``fall_detection``; ``collection``,
``session``, ``analysis`` and the collector app all import from here.
"""

from .loader import load_protocol, protocol_from_mapping, select_blocks
from .model import (
    CollectionProtocol,
    ProtocolError,
    Scenario,
    TimingDefaults,
    Trial,
)

__all__ = [
    "CollectionProtocol",
    "ProtocolError",
    "Scenario",
    "TimingDefaults",
    "Trial",
    "load_protocol",
    "protocol_from_mapping",
    "select_blocks",
]
