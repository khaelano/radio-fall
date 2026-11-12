"""Versioned dual-band gateway policy; fixed identities and reproducible settings."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .profile import RadioInventory, RadioProfile, profile_fingerprint

CONFIG_SIZE = 108
CONTROL, RESPONSE, ROUND, EVENT, ENVELOPE, ACK = range(20, 26)


def mac_bytes(value: str) -> bytes:
    """Encode a canonical six-octet MAC address."""
    return bytes.fromhex(value.replace(":", ""))


@dataclass(frozen=True)
class EspnowTransportConfig:
    """Bounded transport settings; timing reserves require hardware qualification."""

    schema_version: int = 7
    channel: int = 6
    phy: str = "ht20_mcs0_lgi"
    slot_ms: int = 50
    start_guard_ms: int = 5
    return_reserve_ms: int = 10
    queue_capacity: int = 64
    maximum_age_ms: int = 500
    outstanding_batches: int = 4
    early_return_idle_ms: int = 0
    minimum_revisit_ms: int = 0
    send_completion_guard_ms: int = 10
    batch_acknowledgements: bool = False
    measure_send_completions: bool = False
    application_acknowledgements: bool = True
    ack_timeout_ms: int = 50
    maximum_retries: int = 1
    records_per_slot: int = 16
    bin_hz: int = 50
    delivery_grace_ms: int = 500
    drain_ms: int = 1000

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != 7
            or type(self.phy) is not str
            or self.phy not in {f"ht20_mcs{i}_lgi" for i in range(4)}
        ):
            raise ValueError("unsupported ESP-NOW policy/PHY")
        limits = {
            "channel": (1, 13),
            "slot_ms": (20, 500),
            "start_guard_ms": (1, 100),
            "return_reserve_ms": (1, 100),
            "queue_capacity": (1, 96),
            "maximum_age_ms": (1, 1000),
            "outstanding_batches": (1, 8),
            "early_return_idle_ms": (0, 20),
            "minimum_revisit_ms": (0, 1000),
            "send_completion_guard_ms": (1, 20),
            "ack_timeout_ms": (1, 500),
            "maximum_retries": (0, 3),
            "records_per_slot": (1, 64),
            "bin_hz": (1, 100),
            "delivery_grace_ms": (0, 1000),
            "drain_ms": (1, 2000),
        }
        for name, (low, high) in limits.items():
            if (
                type(getattr(self, name)) is not int
                or not low <= getattr(self, name) <= high
            ):
                raise ValueError(f"invalid {name}")
        if self.minimum_revisit_ms % 5:
            raise ValueError("minimum_revisit_ms must be a multiple of 5 ms")
        if (
            type(self.batch_acknowledgements) is not bool
            or type(self.measure_send_completions) is not bool
            or type(self.application_acknowledgements) is not bool
        ):
            raise ValueError("ACK and measurement options must be boolean")
        if not self.application_acknowledgements and (
            self.maximum_retries or self.batch_acknowledgements
        ):
            raise ValueError(
                "ACK-less delivery requires zero retries and no bitmap ACKs"
            )
        if self.start_guard_ms + self.return_reserve_ms >= self.slot_ms:
            raise ValueError("slot leaves no upload time")
        if (
            self.send_completion_guard_ms
            >= self.slot_ms - self.start_guard_ms - self.return_reserve_ms
        ):
            raise ValueError("send guard leaves no upload budget")
        if (
            self.early_return_idle_ms
            >= self.slot_ms - self.start_guard_ms - self.return_reserve_ms
        ):
            raise ValueError("idle grace exceeds upload budget")
        if (
            self.ack_timeout_ms > self.maximum_age_ms
            or self.drain_ms < self.maximum_age_ms
        ):
            raise ValueError("inconsistent retention/ACK/drain settings")

    @classmethod
    def load(cls, path: Path | None) -> EspnowTransportConfig:
        """Load a strict policy; never adjust failed benchmark settings silently."""
        if path is None:
            return cls()
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError("unknown ESP-NOW policy fields")
        return cls(**value)

    def validate(
        self,
        inventory: RadioInventory,
        profile: RadioProfile,
        *,
        require_four: bool = True,
    ) -> None:
        """Require real registered dual-band sensing devices and one C6 gateway."""
        if (
            profile.band != "5ghz"
            or inventory.transmitter.target != "esp32c5"
            or any(r.target != "esp32c5" for r in inventory.receivers)
        ):
            raise ValueError("gateway sensing requires C5 radios on 5 GHz")
        if not 1 <= len(inventory.receivers) <= 4 or (
            require_four and len(inventory.receivers) != 4
        ):
            raise ValueError("collection requires four registered C5 receivers")
        if inventory.gateway is None or inventory.gateway.target != "esp32c6":
            raise ValueError("inventory requires an identified ESP32-C6 gateway")

    def fingerprint(self, inventory: RadioInventory, profile: RadioProfile) -> str:
        """Fingerprint policy, both channels, PHY and ordered physical identities."""
        policy = asdict(self)
        value = {
            "policy": policy,
            "inventory": inventory.as_dict(),
            "profile": profile.as_dict(),
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]

    def encode(
        self, run_id: int, inventory: RadioInventory, profile: RadioProfile
    ) -> bytes:
        """Encode versioned CGCF configuration shared by C and Python (108 bytes)."""
        self.validate(inventory, profile, require_four=False)
        if not 0 < run_id < 1 << 64:
            raise ValueError("invalid run ID")
        p = bytearray(CONFIG_SIZE)
        struct.pack_into(
            "!4sBBBBQ6H4B",
            p,
            0,
            b"CGCF",
            self.schema_version,
            len(inventory.receivers),
            profile.channel,
            self.channel,
            run_id,
            profile.nominal_rate_hz,
            self.slot_ms,
            self.start_guard_ms,
            self.return_reserve_ms,
            self.maximum_age_ms,
            self.ack_timeout_ms,
            self.queue_capacity,
            self.outstanding_batches,
            self.maximum_retries,
            self.records_per_slot,
        )
        p[32:38] = mac_bytes(inventory.gateway.mac)
        p[38:44] = mac_bytes(inventory.transmitter.mac)
        for i, receiver in enumerate(inventory.receivers):
            p[44 + i * 6 : 50 + i * 6] = mac_bytes(receiver.mac)
        p[68:84] = profile_fingerprint(profile, inventory).encode()
        p[84:100] = self.fingerprint(inventory, profile).encode()
        struct.pack_into(
            "!4B",
            p,
            100,
            self.early_return_idle_ms,
            self.minimum_revisit_ms // 5,
            self.send_completion_guard_ms,
            int(self.batch_acknowledgements)
            | (int(self.measure_send_completions) << 1)
            | (int(not self.application_acknowledgements) << 2)
            | (int(self.phy[len("ht20_mcs")]) << 3),
        )
        struct.pack_into("!I", p, 104, zlib.crc32(p[:104]))
        return bytes(p)
