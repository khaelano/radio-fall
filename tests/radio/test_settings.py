"""Validate the operational configuration before any hardware is opened."""

import copy
import json

import pytest

from fall_detection.radio.settings import (
    DEFAULT_CONFIG,
    RadioSettings,
    resolve_settings,
)
from fall_detection.radio.visualization.app import _parser as viewer_parser
from fall_detection.collection.app import _parser as collection_parser


def test_default_configuration_preserves_provisioned_sensing_contract():
    settings = RadioSettings.load()
    assert settings.profile_fingerprint == "8b28a906a0fbcd1f"
    assert settings.profile.nominal_rate_hz == 120
    assert len(settings.inventory.receivers) == 4
    assert settings.transport.schema_version == 7
    assert settings.transport.channel == 11
    assert settings.transport.phy == "ht20_mcs3_lgi"
    assert settings.transport.queue_capacity == 96
    assert settings.transport.slot_ms == 125
    assert settings.transport.maximum_age_ms == 750
    assert not settings.transport.application_acknowledgements
    settings.transport.validate(settings.inventory, settings.profile)


@pytest.mark.parametrize("parser", [viewer_parser, collection_parser])
def test_commands_resolve_same_configuration_outside_repository(
    parser, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    args = parser().parse_args([])
    settings = resolve_settings(args)
    assert args.config == DEFAULT_CONFIG
    assert args.gateway_port.endswith("10:BD:A3:9E:CD:68-if00")
    assert args.transmitter_link == "espnow_uart"
    assert settings.profile.nominal_rate_hz == 120


def test_connection_overrides_preserve_recording_fingerprints(tmp_path):
    original = RadioSettings.load()
    value = json.loads(DEFAULT_CONFIG.read_text())
    value["connection"]["gateway_port"] = "different-laptop-port"
    config = tmp_path / "radio.json"
    config.write_text(json.dumps(value))
    args = viewer_parser().parse_args(
        [
            "--config",
            str(config),
            "--transmitter-link",
            "usb",
            "--port",
            "recovery-usb",
        ]
    )
    settings = resolve_settings(args)
    assert args.gateway_port == "different-laptop-port"
    assert args.port == "recovery-usb"
    assert args.transmitter_link == "usb"
    assert settings.profile_fingerprint == original.profile_fingerprint
    assert settings.transport.fingerprint(settings.inventory, settings.profile) == (
        original.transport.fingerprint(original.inventory, original.profile)
    )


@pytest.mark.parametrize(
    "section", [None, "connection", "inventory", "sensing", "transport"]
)
def test_configuration_rejects_unknown_fields(tmp_path, section):
    value = json.loads(DEFAULT_CONFIG.read_text())
    (value if section is None else value[section])["typo"] = 1
    path = tmp_path / "radio.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="unknown"):
        RadioSettings.load(path)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"inventory": None},
        {"sensing": []},
        {"transport": {"schema_version": 7, "queue_capacity": 97}},
        {"connection": {"transmitter_link": "typo"}},
        {"connection": {"gateway_port": ""}},
    ],
)
def test_configuration_rejects_invalid_settings(tmp_path, change):
    value = copy.deepcopy(json.loads(DEFAULT_CONFIG.read_text()))
    value.update(change)
    path = tmp_path / "radio.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        RadioSettings.load(path)


def test_configuration_rejects_conflicting_legacy_flags():
    args = viewer_parser().parse_args(
        [
            "--config",
            str(DEFAULT_CONFIG),
            "--receiver-config",
            "old-inventory.json",
        ]
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_settings(args)


def test_dry_run_uses_configuration_without_opening_usb(monkeypatch, capsys):
    from fall_detection.radio import provisioning

    monkeypatch.setattr(
        provisioning,
        "_open_serial_devices",
        lambda: pytest.fail("dry run must not open hardware"),
    )
    assert provisioning.provision(["--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["fingerprint"] == "8b28a906a0fbcd1f"
    assert report["devices"] == 5


@pytest.mark.parametrize("override", [None, "explicit-companion-port"])
def test_pairing_uses_companion_port_and_configured_channel(monkeypatch, override):
    from fall_detection.radio import wireless_control

    calls = []
    monkeypatch.setattr(
        wireless_control,
        "pair_devices",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    arguments = ["pair"] + (["--port", override] if override else [])
    assert wireless_control.main(arguments) == 0
    args, kwargs = calls[0]
    assert args[0] == (override or RadioSettings.load().connection["companion_port"])
    assert args[1] == RadioSettings.load().connection["gateway_port"]
    assert kwargs == {
        "transmitter_link": "espnow_uart",
        "channel": RadioSettings.load().transport.channel,
    }


def test_pairing_rejects_channel_mismatch_before_opening_hardware(monkeypatch):
    from fall_detection.radio import wireless_control

    monkeypatch.setattr(
        wireless_control, "pair_devices", lambda *a, **k: pytest.fail("must not pair")
    )
    with pytest.raises(SystemExit):
        wireless_control.main(["pair", "--channel", "1"])
