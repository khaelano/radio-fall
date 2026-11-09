"""One validated configuration for acquisition, provisioning and relay control."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, fields
import json
from pathlib import Path
from typing import Any

from .espnow_config import EspnowTransportConfig
from .profile import RadioInventory, RadioProfile, profile_fingerprint


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs/radio.json"


def _object(value: Any, name: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f"unknown {name} fields: {', '.join(sorted(unknown))}")
    return value


@dataclass(frozen=True)
class RadioSettings:
    """Resolved settings with the existing on-air contracts and fingerprints."""

    inventory: RadioInventory
    profile: RadioProfile
    transport: EspnowTransportConfig
    connection: dict[str, str]

    @property
    def profile_fingerprint(self) -> str:
        """Return the provisioned fingerprint independently of host port names."""
        return profile_fingerprint(self.profile, self.inventory)

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG) -> RadioSettings:
        """Read one strict JSON document and validate it before opening devices."""
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"unable to read radio configuration {path}: {exc}"
            ) from exc
        value = _object(
            value,
            "configuration",
            {
                "schema_version",
                "connection",
                "inventory",
                "sensing",
                "transport",
            },
        )
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("radio configuration schema_version must be 1")
        connection = _object(
            value.get("connection", {}),
            "connection",
            {
                "transmitter_link",
                "gateway_port",
                "transmitter_port",
                "companion_port",
            },
        )
        connection = {"transmitter_link": "espnow_uart", **connection}
        for key, item in connection.items():
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"connection.{key} must be a non-empty string")
        if connection["transmitter_link"] not in {"usb", "ble", "espnow_uart"}:
            raise ValueError("unsupported connection.transmitter_link")
        inventory_value = _object(
            value.get("inventory"),
            "inventory",
            {
                "schema_version",
                "transmitter",
                "receivers",
                "gateway",
            },
        )
        if type(inventory_value.get("schema_version")) is not int:
            raise ValueError("inventory.schema_version must be an integer")
        devices = [inventory_value.get("transmitter"), inventory_value.get("gateway")]
        receivers = inventory_value.get("receivers")
        if isinstance(receivers, list):
            devices.extend(receivers)
        for device in devices:
            _object(device, "device", {"id", "role", "target", "mac", "placement"})
        profile_value = _object(
            value.get("sensing"),
            "sensing",
            {field.name for field in fields(RadioProfile)},
        )
        for key in ("schema_version", "channel", "bandwidth_mhz", "nominal_rate_hz"):
            if type(profile_value.get(key)) is not int:
                raise ValueError(f"sensing.{key} must be an integer")
        policy = _object(
            value.get("transport"),
            "transport",
            {field.name for field in fields(EspnowTransportConfig)},
        )
        inventory = RadioInventory.from_mapping(inventory_value)
        profile = RadioProfile.from_mapping(profile_value)
        transport = EspnowTransportConfig(**policy)
        transport.validate(inventory, profile, require_four=False)
        return cls(inventory, profile, transport, connection)


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    """Expose one settings file, retaining hidden flags for historical commands."""
    parser.add_argument(
        "--config",
        type=Path,
        help="radio settings JSON (default: repository configs/radio.json)",
    )
    for flag in ("--receiver-config", "--radio-profile", "--gateway-config"):
        parser.add_argument(flag, type=Path, help=argparse.SUPPRESS)


def resolve_settings(args: argparse.Namespace) -> RadioSettings:
    """Resolve the file and explicit connection overrides before hardware access."""
    legacy = any((args.receiver_config, args.radio_profile, args.gateway_config))
    if legacy:
        if args.config is not None:
            raise ValueError(
                "--config cannot be combined with legacy configuration flags"
            )
        if not args.receiver_config or not args.radio_profile:
            raise ValueError(
                "--receiver-config and --radio-profile must be provided together"
            )
        inventory = RadioInventory.load(args.receiver_config)
        profile = RadioProfile.load(args.radio_profile)
        settings = RadioSettings(
            inventory,
            profile,
            EspnowTransportConfig.load(args.gateway_config),
            {"transmitter_link": "usb"},
        )
    else:
        args.config = args.config or DEFAULT_CONFIG
        settings = RadioSettings.load(args.config)
    for argument, key in (
        ("transmitter_link", "transmitter_link"),
        ("gateway_port", "gateway_port"),
        ("port", "transmitter_port"),
    ):
        if hasattr(args, argument) and getattr(args, argument) is None:
            setattr(args, argument, settings.connection.get(key))
    return settings
