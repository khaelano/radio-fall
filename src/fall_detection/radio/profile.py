"""Validated radio inventory and selectable on-air profiles.

The profile module is the host-side seam for radio configuration.  It keeps
the physical inventory (which boards exist) separate from the experiment
profile (which band/channel is active), and computes the same stable
fingerprint that firmware places in sensing packets and status frames.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


class RadioProfileError(ValueError):
    """Raised when an inventory or radio profile cannot be used safely."""


MAC_PATTERN = re.compile(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}\Z")
WIRE_VERSION = 2
SUPPORTED_TARGETS = frozenset({"esp32c5", "esp32c6"})
SUPPORTED_BANDS = frozenset({"2.4ghz", "5ghz"})
# ESP-IDF's Indonesia country table permits channels 1--13 in 2.4 GHz.
# Channel 14 is a Japan-only channel and must not leak into an ID profile.
INDONESIA_2GHZ_CHANNELS = frozenset(range(1, 14))
NON_DFS_5GHZ_CHANNELS = frozenset(
    {36, 40, 44, 48, 149, 153, 157, 161, 165}
)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RadioProfileError(f"{field} must be a non-empty string")
    return value.strip()


def _mac(value: Any, field: str) -> str:
    text = _text(value, field).lower()
    if MAC_PATTERN.fullmatch(text) is None:
        raise RadioProfileError(f"{field} must be a six-octet MAC address")
    return text


@dataclass(frozen=True)
class RadioDevice:
    """One physical radio board in the experiment inventory."""

    id: str
    role: str
    target: str
    mac: str
    placement: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, index: int) -> "RadioDevice":
        device_id = _text(value.get("id"), f"devices[{index}].id")
        role = _text(value.get("role"), f"devices[{index}].role").lower()
        if role not in {"transmitter", "receiver", "gateway"}:
            raise RadioProfileError(f"devices[{index}].role must be transmitter, receiver or gateway")
        target = _text(value.get("target"), f"devices[{index}].target").lower()
        if target not in SUPPORTED_TARGETS:
            raise RadioProfileError(f"devices[{index}].target is unsupported: {target}")
        return cls(
            id=device_id,
            role=role,
            target=target,
            mac=_mac(value.get("mac"), f"devices[{index}].mac"),
            placement=str(value.get("placement", "")).strip(),
        )


@dataclass(frozen=True)
class RadioInventory:
    """Validated physical inventory, independent of the active channel."""

    schema_version: int
    transmitter: RadioDevice
    receivers: tuple[RadioDevice, ...]
    gateway: RadioDevice | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RadioInventory":
        schema_version = value.get("schema_version")
        if schema_version not in (1, 2):
            raise RadioProfileError("inventory schema_version must be 1 or 2")

        raw_transmitter = value.get("transmitter")
        if not isinstance(raw_transmitter, Mapping):
            raise RadioProfileError("inventory.transmitter must be an object")
        transmitter = RadioDevice.from_mapping(raw_transmitter, index=0)
        if transmitter.role != "transmitter":
            raise RadioProfileError("inventory.transmitter.role must be transmitter")

        raw_receivers = value.get("receivers")
        if not isinstance(raw_receivers, list) or not raw_receivers:
            raise RadioProfileError("inventory.receivers must be a non-empty list")
        receivers = tuple(
            RadioDevice.from_mapping(item, index=index + 1)
            for index, item in enumerate(raw_receivers)
            if isinstance(item, Mapping)
        )
        if len(receivers) != len(raw_receivers):
            raise RadioProfileError("each receiver entry must be an object")
        if any(device.role != "receiver" for device in receivers):
            raise RadioProfileError("inventory.receivers entries must have role receiver")

        raw_gateway = value.get("gateway")
        gateway = RadioDevice.from_mapping(raw_gateway, index=5) if isinstance(raw_gateway, Mapping) else None
        if schema_version == 2 and (gateway is None or gateway.role != "gateway" or gateway.target != "esp32c6"):
            raise RadioProfileError("inventory v2 requires an ESP32-C6 gateway")
        if raw_gateway is not None and schema_version == 1:
            raise RadioProfileError("gateway requires inventory schema_version 2")
        devices = (transmitter, *receivers, *((gateway,) if gateway else ()))
        ids = [device.id for device in devices]
        macs = [device.mac for device in devices]
        if len(set(ids)) != len(ids):
            raise RadioProfileError("device IDs must be unique")
        if len(set(macs)) != len(macs):
            raise RadioProfileError("device MAC addresses must be unique")
        return cls(schema_version=schema_version, transmitter=transmitter, receivers=receivers, gateway=gateway)

    @classmethod
    def load(cls, path: Path) -> "RadioInventory":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RadioProfileError(f"unable to read inventory {path}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise RadioProfileError("inventory root must be an object")
        return cls.from_mapping(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transmitter": _device_dict(self.transmitter),
            "receivers": [_device_dict(device) for device in self.receivers],
            **({"gateway": _device_dict(self.gateway)} if self.gateway else {}),
        }


@dataclass(frozen=True)
class RadioProfile:
    """Validated experiment-level band/channel settings."""

    schema_version: int
    profile_id: str
    country_code: str
    band: str
    channel: int
    bandwidth_mhz: int
    nominal_rate_hz: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RadioProfile":
        if type(value.get("schema_version")) is not int or value["schema_version"] not in (1, 2):
            raise RadioProfileError("radio profile schema_version must be 1 or 2")
        profile_id = _text(value.get("profile_id"), "profile_id")
        country_code = _text(value.get("country_code"), "country_code").upper()
        if country_code != "ID":
            raise RadioProfileError("only the Indonesia country profile (ID) is supported")
        band = _text(value.get("band"), "band").lower().replace(" ", "")
        if band in {"2.4g", "2.4ghz", "24ghz"}:
            band = "2.4ghz"
        elif band in {"5g", "5ghz"}:
            band = "5ghz"
        else:
            raise RadioProfileError("band must be 2.4ghz or 5ghz")
        if value["schema_version"] == 2 and band != "5ghz":
            raise RadioProfileError("radio profile version 2 requires 5ghz gateway sensing")
        try:
            channel = int(value.get("channel"))
            bandwidth = int(value.get("bandwidth_mhz"))
            rate = int(value.get("nominal_rate_hz"))
        except (TypeError, ValueError) as exc:
            raise RadioProfileError("channel, bandwidth_mhz, and nominal_rate_hz must be integers") from exc
        if bandwidth != 20:
            raise RadioProfileError("only 20 MHz bandwidth is supported")
        if isinstance(value.get("nominal_rate_hz"), bool) or rate != value.get("nominal_rate_hz") or not 50 <= rate <= (120 if value["schema_version"] == 2 else 100):
            raise RadioProfileError("nominal_rate_hz must be an integer between 50 and 100 (120 in profile version 2)")
        if band == "2.4ghz" and channel not in INDONESIA_2GHZ_CHANNELS:
            raise RadioProfileError("2.4ghz channel is not permitted in Indonesia")
        if band == "5ghz":
            if channel not in NON_DFS_5GHZ_CHANNELS:
                raise RadioProfileError(
                    "5ghz channel must be a supported non-DFS channel"
                )
        return cls(value["schema_version"], profile_id, country_code, band, channel, bandwidth, rate)

    @classmethod
    def load(cls, path: Path) -> "RadioProfile":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RadioProfileError(f"unable to read radio profile {path}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise RadioProfileError("radio profile root must be an object")
        return cls.from_mapping(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "country_code": self.country_code,
            "band": self.band,
            "channel": self.channel,
            "bandwidth_mhz": self.bandwidth_mhz,
            "nominal_rate_hz": self.nominal_rate_hz,
        }


def _device_dict(device: RadioDevice) -> dict[str, str]:
    return {
        "id": device.id,
        "role": device.role,
        "target": device.target,
        "mac": device.mac,
        "placement": device.placement,
    }


def validate_inventory_for_profile(
    inventory: RadioInventory, profile: RadioProfile
) -> None:
    """Validate target capabilities for one complete experiment profile."""

    if profile.band == "5ghz":
        incompatible = [
            device.id
            for device in (inventory.transmitter, *inventory.receivers)
            if device.target != "esp32c5"
        ]
        if incompatible:
            raise RadioProfileError(
                "5ghz profiles require ESP32-C5 for sensing devices: "
                + ", ".join(incompatible)
            )


def profile_fingerprint(
    profile: RadioProfile,
    inventory: RadioInventory,
    *,
    wire_version: int = WIRE_VERSION,
) -> str:
    """Return a deterministic short fingerprint for the on-air profile."""

    validate_inventory_for_profile(inventory, profile)
    canonical = {
        "wire_version": wire_version,
        "country_code": profile.country_code,
        "band": profile.band,
        "channel": profile.channel,
        "bandwidth_mhz": profile.bandwidth_mhz,
        "nominal_rate_hz": profile.nominal_rate_hz,
        "transmitter_mac": inventory.transmitter.mac,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def load_inventory_and_profile(
    inventory_path: Path, profile_path: Path
) -> tuple[RadioInventory, RadioProfile, str]:
    """Load, validate, and fingerprint the pair used by collection commands."""

    inventory = RadioInventory.load(inventory_path)
    profile = RadioProfile.load(profile_path)
    fingerprint = profile_fingerprint(profile, inventory)
    return inventory, profile, fingerprint
