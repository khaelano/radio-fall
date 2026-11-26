"""csi-radio presents discovery and provisioning without touching real boards."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fall_detection.radio import cli
from fall_detection.radio.provisioning import DeviceStatus, Discovery
from fall_detection.radio.settings import RadioSettings

SETTINGS = RadioSettings.load()
INVENTORY = SETTINGS.inventory
FINGERPRINT = SETTINGS.profile_fingerprint


class Board:
    """A connected board that answers provisioning like the firmware."""

    def __init__(self, device, port, *, fingerprint=None, role=None, protocol=3):
        self.status = DeviceStatus(
            role or device.role,
            device.target,
            device.mac,
            "test",
            protocol,
            profile_fingerprint=fingerprint,
            profile_id="old-profile" if fingerprint else None,
        )
        self.connection = SimpleNamespace(port=port)
        self.payloads = []
        self.closed = False

    def stage_profile(self, payload):
        self.payloads.append(json.loads(payload))

    def commit_profile(self):
        payload = self.payloads[-1]
        self.status = replace(
            self.status,
            ready=True,
            profile_id=payload["profile"]["profile_id"],
            profile_fingerprint=payload["fingerprint"],
        )

    def refresh_status(self):
        return self.status

    def close(self):
        self.closed = True


def discovery(*boards, silent=(), unavailable=None):
    return Discovery(list(boards), list(silent), dict(unavailable or {}))


def test_status_matches_boards_and_names_the_next_step(monkeypatch, capsys):
    rx1, rx2 = INVENTORY.receivers[:2]
    boards = [
        Board(rx1, "/dev/ttyACM1", fingerprint=FINGERPRINT),
        Board(rx2, "/dev/ttyACM2", fingerprint="0123456789abcdef"),
        Board(INVENTORY.gateway, "/dev/ttyACM0"),
        Board(
            SimpleNamespace(role="relay", target="esp32c6", mac="10:00:00:00:00:01"),
            "/dev/ttyACM3",
        ),
        Board(
            SimpleNamespace(role="receiver", target="esp32c5", mac="44:00:00:00:00:99"),
            "/dev/ttyACM4",
        ),
    ]
    monkeypatch.setattr(cli, "discover_boards", lambda: discovery(*boards))

    assert cli.main([]) == 0

    out = capsys.readouterr().out
    lines = {line.split()[1]: line for line in out.splitlines() if "  rx-" in line}
    assert "/dev/ttyACM1" in lines["rx-1"] and "profile indonesia" in lines["rx-1"]
    assert "stores old-profile" in lines["rx-2"]
    assert "not on USB" in lines["rx-3"]
    assert "pairing relay" in out
    assert "44:00:00:00:00:99" in out and "not in configuration" in out
    assert "csi-radio provision` to write the sensing profile to rx-2" in out
    assert all(board.closed for board in boards)


def test_status_says_ready_and_reports_a_busy_gateway(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "discover_boards",
        lambda: discovery(Board(INVENTORY.gateway, "/dev/ttyACM0")),
    )
    assert cli.main(["status"]) == 0
    assert "Ready: power the transmitter" in capsys.readouterr().out

    gateway_port = SETTINGS.connection["gateway_port"]
    monkeypatch.setattr(
        cli,
        "discover_boards",
        lambda: discovery(unavailable={gateway_port: "Device or resource busy"}),
    )
    assert cli.main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    gateway = next(b for b in report["boards"] if b["role"] == "gateway")
    assert gateway["state"] == "busy"
    assert any("in use" in step for step in report["next_steps"])


def test_check_validates_configuration_without_opening_usb(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "discover_boards", lambda: pytest.fail("check must not open hardware")
    )
    assert cli.main(["check", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["fingerprint"] == "8b28a906a0fbcd1f"
    assert report["devices"] == 5
    assert cli.main(["check"]) == 0
    assert "is valid" in capsys.readouterr().out


def test_invalid_configuration_is_reported_without_a_traceback(tmp_path, capsys):
    broken = tmp_path / "radio.json"
    broken.write_text("{}")
    assert cli.main(["check", "--config", str(broken)]) == 2
    assert "csi-radio check:" in capsys.readouterr().err


def test_guided_provisioning_walks_boards_one_at_a_time(monkeypatch, capsys):
    rx1, rx2 = INVENTORY.receivers[:2]
    first = Board(rx1, "/dev/ttyACM1")
    second = Board(rx2, "/dev/ttyACM1", fingerprint="0123456789abcdef")
    passes = iter([discovery(first), discovery(second)])
    answers = iter(["", "y", "", "q"])
    monkeypatch.setattr(cli, "discover_boards", lambda: next(passes))
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr(cli, "_ask", lambda prompt: next(answers))

    assert cli.main(["provision"]) == 0

    out = capsys.readouterr().out
    for board in (first, second):
        assert board.status.profile_fingerprint == FINGERPRINT
        assert board.payloads[0]["fingerprint"] == FINGERPRINT
        assert board.closed
    assert "rx-1: profile written and verified" in out
    assert "Verified this pass: rx-1, rx-2" in out


def test_provisioning_skips_current_boards_unless_forced(monkeypatch, capsys):
    transmitter = Board(INVENTORY.transmitter, "/dev/ttyACM1", fingerprint=FINGERPRINT)
    monkeypatch.setattr(cli, "discover_boards", lambda: discovery(transmitter))

    assert cli.main(["provision", "--yes"]) == 0
    assert not transmitter.payloads
    out = capsys.readouterr().out
    assert "Not provisioned yet: rx-1" in out
    assert "rerun with --force" in out

    assert cli.main(["provision", "--yes", "--force"]) == 0
    assert transmitter.payloads[0]["receivers"] == [
        device.mac for device in INVENTORY.receivers
    ]


def test_provision_one_ignores_the_gateway_but_needs_one_sensing_board(
    monkeypatch, capsys
):
    receiver = Board(INVENTORY.receivers[0], "/dev/ttyACM1")
    gateway = Board(INVENTORY.gateway, "/dev/ttyACM0")
    monkeypatch.setattr(cli, "discover_boards", lambda: discovery(receiver, gateway))
    assert cli.main(["provision", "--one", "--yes"]) == 0
    assert receiver.status.profile_fingerprint == FINGERPRINT

    monkeypatch.setattr(cli, "discover_boards", lambda: discovery(gateway))
    assert cli.main(["provision", "--one", "--yes"]) == 1
    assert "exactly one configured C5 board" in capsys.readouterr().err


def test_provisioning_failure_is_reported_with_its_cause(monkeypatch, capsys):
    receiver = Board(INVENTORY.receivers[0], "/dev/ttyACM1")
    receiver.refresh_status = lambda: replace(receiver.status, ready=False)
    monkeypatch.setattr(cli, "discover_boards", lambda: discovery(receiver))
    assert cli.main(["provision", "--yes"]) == 1
    assert "did not report the committed profile" in capsys.readouterr().out


def test_non_interactive_provisioning_asks_for_yes(monkeypatch, capsys):
    receiver = Board(INVENTORY.receivers[0], "/dev/ttyACM1")
    monkeypatch.setattr(cli, "discover_boards", lambda: discovery(receiver))
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    assert cli.main(["provision"]) == 0
    assert not receiver.payloads
    assert "pass --yes" in capsys.readouterr().out


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as help_exit:
        cli.main(["--help"])
    assert help_exit.value.code == 0
    out = capsys.readouterr().out
    for command in ("status", "check", "provision", "pair", "transmitter"):
        assert command in out
    with pytest.raises(SystemExit) as error:
        cli.main(["unknown"])
    assert error.value.code == 2
