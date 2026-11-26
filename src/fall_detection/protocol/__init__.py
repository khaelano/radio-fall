"""Versioned collection protocols and deterministic trial expansion.

This package depends on nothing else in ``fall_detection``; ``collection``,
``session``, ``analysis`` and the collector app all import from it. Import from
the defining module: ``protocol.model`` holds the protocol, scenario, trial and
timing types and ``ProtocolError``; ``protocol.loader`` holds ``load_protocol``,
``protocol_from_mapping`` and ``select_blocks``; ``protocol.revision`` builds
revised protocols from a queue edited while a session records.
"""
