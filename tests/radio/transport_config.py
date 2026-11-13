"""Explicit ESP-NOW transport policies for firmware and wire contract tests.

The base policy is fixed here so byte-level expectations do not move when the
operational values in ``configs/radio.json`` are tuned.
"""

from typing import Any

from fall_detection.radio.espnow_config import EspnowTransportConfig

CONTRACT_POLICY: dict[str, Any] = {
    "schema_version": 7,
    "channel": 6,
    "phy": "ht20_mcs0_lgi",
    "slot_ms": 50,
    "start_guard_ms": 5,
    "return_reserve_ms": 10,
    "queue_capacity": 64,
    "maximum_age_ms": 500,
    "outstanding_batches": 4,
    "ack_timeout_ms": 50,
    "maximum_retries": 1,
    "records_per_slot": 16,
    "bin_hz": 50,
    "delivery_grace_ms": 500,
    "drain_ms": 1000,
    "application_acknowledgements": True,
    "measure_send_completions": False,
}


def transport_config(**changes: Any) -> EspnowTransportConfig:
    """Return the fixed contract policy with ``changes`` applied."""

    return EspnowTransportConfig(**{**CONTRACT_POLICY, **changes})
