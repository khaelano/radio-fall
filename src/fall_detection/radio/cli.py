"""``csi-radio``: check, provision and pair the CSI radio boards.

Running ``csi-radio`` without a command prints an overview: the configuration
in use, every configured board matched to what is connected over USB, the
sensing profile each connected board reports, and the next step. The commands
mirror the setup procedure:

* ``check`` validates ``configs/radio.json`` without opening hardware;
* ``provision`` writes the sensing profile to the C5 boards, guiding a pass
  in which boards are connected one at a time;
* ``pair`` pairs the companion C6 relay with the gateway (new hardware only);
* ``transmitter`` reads or provisions the untethered transmitter through the
  gateway relay.

Board protocol, validation and commit semantics live in :mod:`.provisioning`
and :mod:`.wireless_control`; this module only presents them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .profile import RadioDevice
from .provisioning import (
    DeviceStatus,
    Discovery,
    ProvisioningError,
    RadioProvisioner,
    discover_boards,
)
from .settings import RadioSettings, add_config_argument, resolve_settings

PROTOCOL_VERSION = 3
OK, BAD, TODO, ABSENT = "✓", "✗", "●", "○"
EXAMPLES = """\
typical use:
  csi-radio                      what is configured, what is connected, what to do next
  csi-radio check                validate configs/radio.json without hardware
  csi-radio provision            write the sensing profile, one board at a time
  csi-radio transmitter          read the transmitter through the gateway relay
  csi-radio pair                 pair the companion relay and gateway (new hardware)

Every command reads configs/radio.json unless --config names another file.
"""
SENSING_ROLES = ("transmitter", "receiver")


# -- board classification -----------------------------------------------------


@dataclass
class BoardState:
    """One configured board and what discovery found for it.

    Attributes:
        device: The inventory entry.
        port: USB device path when the board answered discovery.
        state: ``current``, ``different``, ``unprovisioned``, ``connected``,
            ``mismatch``, ``firmware``, ``busy`` or ``absent``.
        detail: Short explanation for the operator.
    """

    device: RadioDevice
    port: str | None = None
    state: str = "absent"
    detail: str = ""
    status: DeviceStatus | None = field(default=None, repr=False)

    @property
    def needs_profile(self) -> bool:
        """Whether this connected sensing board should be provisioned."""
        return self.state in {"different", "unprovisioned"}

    @property
    def symbol(self) -> str:
        """Single-character state marker."""
        if self.state in {"current", "connected"}:
            return OK
        if self.state in {"mismatch", "firmware", "busy"}:
            return BAD
        if self.needs_profile:
            return TODO
        return ABSENT


@dataclass
class Survey:
    """Configured boards matched to one discovery pass."""

    boards: list[BoardState]
    unknown: list[tuple[DeviceStatus, str | None]]
    relay: tuple[DeviceStatus, str | None] | None
    silent: list[str]
    unavailable: dict[str, str]

    def sensing(self) -> list[BoardState]:
        """Transmitter and receivers, in inventory order."""
        return [b for b in self.boards if b.device.role in SENSING_ROLES]

    def gateway(self) -> BoardState:
        """The configured gateway."""
        return next(b for b in self.boards if b.device.role == "gateway")


def _port_of(device: Any) -> str | None:
    return getattr(getattr(device, "connection", None), "port", None)


def _same_port(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return os.path.realpath(left) == os.path.realpath(right)


def survey(settings: RadioSettings, discovery: Discovery) -> Survey:
    """Match discovered boards to the configured inventory.

    Args:
        settings: Resolved radio settings.
        discovery: One discovery pass.

    Returns:
        Every configured board with its state, plus boards and ports that
        match nothing in the configuration.
    """
    inventory = settings.inventory
    fingerprint = settings.profile_fingerprint
    configured = [inventory.transmitter, *inventory.receivers, inventory.gateway]
    by_mac = {device.status.mac: device for device in discovery.devices}
    boards = []
    for device in configured:
        board = BoardState(device)
        found = by_mac.pop(device.mac, None)
        if found is None:
            gateway_port = settings.connection.get("gateway_port")
            busy = next(
                (
                    reason
                    for port, reason in discovery.unavailable.items()
                    if device.role == "gateway" and _same_port(port, gateway_port)
                ),
                None,
            )
            if busy is not None:
                board.state = "busy"
                board.port = gateway_port
                board.detail = "port in use; close csi-live or csi-sessions"
            elif device.role == "transmitter":
                board.detail = (
                    "not on USB; normal when untethered (csi-radio transmitter)"
                )
            elif device.role == "receiver":
                board.detail = "not on USB; needed only to provision"
            else:
                board.detail = "not connected; csi-live and csi-sessions need it"
            boards.append(board)
            continue
        status = found.status
        board.status, board.port = status, _port_of(found)
        if (status.role, status.target) != (device.role, device.target):
            board.state = "mismatch"
            board.detail = (
                f"reports {status.role}/{status.target}, configured as "
                f"{device.role}/{device.target}"
            )
        elif status.protocol_version != PROTOCOL_VERSION:
            board.state = "firmware"
            board.detail = (
                f"firmware protocol {status.protocol_version}; flash protocol "
                f"{PROTOCOL_VERSION} firmware"
            )
        elif device.role == "gateway":
            board.state = "connected"
            board.detail = "ready; configured automatically at each run"
        elif status.profile_fingerprint == fingerprint:
            board.state = "current"
            board.detail = f"profile {settings.profile.profile_id}"
        elif status.profile_fingerprint is None:
            board.state = "unprovisioned"
            board.detail = "no sensing profile stored"
        else:
            board.state = "different"
            board.detail = (
                f"stores {status.profile_id or 'another profile'} "
                f"({status.profile_fingerprint})"
            )
        boards.append(board)
    relay = None
    unknown = []
    for device in by_mac.values():
        entry = (device.status, _port_of(device))
        if device.status.role == "relay" and relay is None:
            relay = entry
        else:
            unknown.append(entry)
    return Survey(boards, unknown, relay, discovery.silent, discovery.unavailable)


def next_steps(found: Survey) -> list[str]:
    """Return what the operator should do, most urgent first."""
    steps = []
    for board in found.boards:
        if board.state in {"mismatch", "firmware"}:
            steps.append(f"Fix {board.device.id} on {board.port}: {board.detail}.")
    for status, port in found.unknown:
        steps.append(
            f"Board {status.mac} ({status.role}, {status.target}) on {port or '?'} is "
            "not in the configuration; unplug it or add it to configs/radio.json."
        )
    stale = [board.device.id for board in found.sensing() if board.needs_profile]
    if stale:
        steps.append(
            f"Run `csi-radio provision` to write the sensing profile to {', '.join(stale)}."
        )
    gateway = found.gateway()
    if gateway.state == "absent":
        steps.append("Connect the gateway (C6) by USB to record or view CSI.")
    elif gateway.state == "busy":
        steps.append(
            "The gateway is in use by another program; it is probably recording."
        )
    if not steps:
        steps.append(
            "Ready: power the transmitter and receivers, then start `csi-live` "
            "to view CSI or `csi-sessions` to record."
        )
    if any(board.state == "absent" for board in found.sensing()):
        steps.append(
            "Boards that are not on USB cannot be checked here. After changing "
            "the sensing settings, connect each by USB and run `csi-radio provision`."
        )
    return steps


# -- output helpers -----------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    widths = [
        max(len(str(row[column])) for row in (header, *rows))
        for column in range(len(header))
    ]
    lines = []
    for row in (header, *rows):
        lines.append(
            "  "
            + "  ".join(
                str(value).ljust(width) for value, width in zip(row, widths)
            ).rstrip()
        )
    return "\n".join(lines)


def _settings(args: argparse.Namespace) -> RadioSettings:
    for name in ("gateway_port", "port"):
        if not hasattr(args, name):
            setattr(args, name, None)
    return resolve_settings(args)


def _profile_line(settings: RadioSettings) -> str:
    profile = settings.profile
    return (
        f"{profile.profile_id} · {profile.band} ch {profile.channel} · "
        f"{profile.bandwidth_mhz} MHz · {profile.nominal_rate_hz} rounds/s · "
        f"fingerprint {settings.profile_fingerprint}"
    )


def _ask(prompt: str) -> str:
    """Read one answer; end of input counts as an empty answer."""
    try:
        return input(prompt)
    except EOFError:
        return "q"


def _interactive() -> bool:
    return sys.stdin.isatty()


def _confirm(prompt: str, args: argparse.Namespace) -> bool:
    if getattr(args, "yes", False):
        return True
    if not _interactive():
        print(f"{prompt} — skipped: not a terminal; pass --yes to proceed")
        return False
    return _ask(f"{prompt} [Y/n] ").strip().lower() in {"", "y", "yes"}


# -- commands -----------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    """Print the configured boards matched to what is connected."""
    settings = _settings(args)
    discovery = discover_boards()
    try:
        found = survey(settings, discovery)
    finally:
        discovery.close()
    steps = next_steps(found)
    if args.json:
        print(
            json.dumps(
                {
                    "config": str(args.config),
                    "profile_id": settings.profile.profile_id,
                    "fingerprint": settings.profile_fingerprint,
                    "boards": [
                        {
                            "id": b.device.id,
                            "role": b.device.role,
                            "target": b.device.target,
                            "mac": b.device.mac,
                            "usb_port": b.port,
                            "state": b.state,
                            "detail": b.detail,
                            "reported": asdict(b.status) if b.status else None,
                        }
                        for b in found.boards
                    ],
                    "relay": asdict(found.relay[0]) if found.relay else None,
                    "unknown": [asdict(status) for status, _port in found.unknown],
                    "silent_ports": found.silent,
                    "unavailable_ports": found.unavailable,
                    "next_steps": steps,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"Configuration  {args.config}")
    print(f"  Sensing   {_profile_line(settings)}")
    transport = settings.transport
    print(
        f"  Backhaul  ESP-NOW ch {transport.channel} · {transport.phy} · "
        f"{transport.slot_ms} ms slots"
    )
    print()
    print("Boards")
    rows = [
        [
            board.symbol,
            board.device.id,
            board.device.role,
            board.device.mac,
            board.port or "—",
            board.detail,
        ]
        for board in found.boards
    ]
    if found.relay is not None:
        status, port = found.relay
        rows.append(
            [OK, "relay", "companion", status.mac, port or "—", "pairing relay (C6)"]
        )
    for status, port in found.unknown:
        rows.append(
            [BAD, "?", status.role, status.mac, port or "—", "not in configuration"]
        )
    print(_table(["", "ID", "ROLE", "MAC", "USB", "STATE"], rows))
    for port, reason in found.unavailable.items():
        if not any(_same_port(port, b.port) for b in found.boards):
            print(f"  {BAD} could not open {port}: {reason}")
    for port in found.silent:
        print(f"  {ABSENT} {port} did not answer (other firmware, or still booting)")
    print()
    print("Next")
    for step in steps:
        print(f"  • {step}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Validate the configuration file and print what it sets."""
    settings = _settings(args)
    inventory, profile = settings.inventory, settings.profile
    if args.json:
        print(
            json.dumps(
                {
                    "config": str(args.config),
                    "profile_id": profile.profile_id,
                    "band": profile.band,
                    "channel": profile.channel,
                    "fingerprint": settings.profile_fingerprint,
                    "devices": len(inventory.receivers) + 1,
                    "receivers": [device.id for device in inventory.receivers],
                    "backhaul_channel": settings.transport.channel,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    print(f"{OK} {args.config} is valid")
    print(f"  Sensing     {_profile_line(settings)}")
    transport = settings.transport
    print(
        f"  Backhaul    ESP-NOW ch {transport.channel} · {transport.phy} · "
        f"{transport.slot_ms} ms slots · policy version {transport.schema_version}"
    )
    print(
        f"  Boards      {inventory.transmitter.id} transmitter, "
        f"{len(inventory.receivers)} receivers "
        f"({', '.join(d.id for d in inventory.receivers)}), "
        f"{inventory.gateway.id} gateway"
    )
    for key, label in (
        ("gateway_port", "Gateway"),
        ("companion_port", "Companion"),
        ("transmitter_port", "Transmitter"),
    ):
        port = settings.connection.get(key)
        if port:
            mark = OK if Path(port).exists() else ABSENT
            state = "present" if mark == OK else "not connected"
            print(f"  {label:<11} {mark} {port} ({state})")
    print()
    print(
        "The fingerprint is stored on each C5 board. After changing `sensing` "
        "or the receiver list, run `csi-radio provision`."
    )
    return 0


def _provision_one(
    settings: RadioSettings, board: BoardState, device: Any
) -> tuple[bool, str]:
    try:
        RadioProvisioner([device]).provision(
            settings.inventory, settings.profile, sequential=True
        )
    except ProvisioningError as exc:
        cause = f": {exc.__cause__}" if exc.__cause__ else ""
        return False, f"{exc}{cause}"
    return True, "profile written and verified"


def _checklist(found: Survey, done: set[str]) -> None:
    for board in found.sensing():
        if board.device.mac in done or board.state == "current":
            mark, text = OK, "has the profile"
        elif board.needs_profile:
            mark, text = TODO, f"connected on {board.port}; {board.detail}"
        elif board.state in {"mismatch", "firmware"}:
            mark, text = BAD, board.detail
        else:
            mark, text = ABSENT, "not connected"
        print(f"  {mark} {board.device.id:<6} {board.device.role:<11} {text}")


def cmd_provision(args: argparse.Namespace) -> int:
    """Write the sensing profile to connected C5 boards."""
    settings = _settings(args)
    print(f"Sensing profile  {_profile_line(settings)}")
    if args.all:
        discovery = discover_boards()
        try:
            report = RadioProvisioner(discovery.devices).provision(
                settings.inventory, settings.profile
            )
        finally:
            discovery.close()
        for status in report.devices:
            print(f"  {OK} {status.role} {status.mac}")
        print(f"Provisioned every board with fingerprint {report.fingerprint}.")
        return 0
    done: set[str] = set()
    failures = 0
    while True:
        discovery = discover_boards()
        try:
            found = survey(settings, discovery)
            devices = {d.status.mac: d for d in discovery.devices}
            connected = [
                b for b in found.sensing() if b.port and b.device.mac not in done
            ]
            if args.one and len(connected) != 1:
                names = ", ".join(b.device.id for b in connected) or "none"
                raise ProvisioningError(
                    "--one needs exactly one configured C5 board on USB; "
                    f"connected: {names}"
                )
            print()
            _checklist(found, done)
            for board in connected:
                if board.state == "current" and not (args.force or args.one):
                    done.add(board.device.mac)
                    continue
                if board.state in {"mismatch", "firmware"}:
                    continue
                if not _confirm(
                    f"Write the profile to {board.device.id} on {board.port}?", args
                ):
                    continue
                ok, message = _provision_one(settings, board, devices[board.device.mac])
                print(f"  {OK if ok else BAD} {board.device.id}: {message}")
                if ok:
                    done.add(board.device.mac)
                else:
                    failures += 1
        finally:
            discovery.close()
        remaining = [
            b.device.id
            for b in found.sensing()
            if b.device.mac not in done and b.state != "current"
        ]
        if args.one or not remaining:
            break
        if args.yes or not _interactive():
            print(
                f"\nNot provisioned yet: {', '.join(remaining)}. Connect each by "
                "USB and run `csi-radio provision` again."
            )
            break
        answer = _ask(
            f"\nConnect the next board ({', '.join(remaining)}) by USB and press "
            "Enter; type q to stop: "
        )
        if answer.strip().lower().startswith("q"):
            break
    current = [b.device.id for b in found.sensing() if b.device.mac in done]
    if current:
        print(f"\nVerified this pass: {', '.join(current)}.")
    transmitter = settings.inventory.transmitter
    if not args.force and transmitter.mac in done:
        print(
            "If you changed the receiver list, the transmitter must store the new "
            "list too: rerun with --force while it is connected."
        )
    return 1 if failures else 0


def cmd_pair(args: argparse.Namespace) -> int:
    """Pair the companion C6 relay with the gateway."""
    from .wireless_control import pair_devices

    override = args.port
    settings = _settings(args)
    companion = override or settings.connection.get("companion_port")
    if not companion:
        raise ValueError("no companion port: set connection.companion_port or --port")
    if not args.gateway_port:
        raise ValueError(
            "no gateway port: set connection.gateway_port or --gateway-port"
        )
    channel = settings.transport.channel
    print(
        "Pairing stores a fresh ESP-NOW key on the companion C6 relay and the "
        f"gateway for backhaul channel {channel}, then reboots both.\n"
        f"  companion  {companion}\n  gateway    {args.gateway_port}\n"
        "Pair only new hardware or boards whose storage was erased, with sensing "
        "stopped."
    )
    if not _confirm("Pair now?", args):
        return 1
    pair_devices(
        companion,
        args.gateway_port,
        settings.inventory,
        transmitter_link=settings.connection["transmitter_link"],
        channel=channel,
    )
    print(
        f"{OK} Paired; keys are stored only on the boards. Next: `csi-radio "
        "transmitter` checks the transmitter through the relay."
    )
    return 0


def _transmitter_lines(raw: dict[str, Any], settings: RadioSettings) -> list[str]:
    fingerprint = raw.get("profile_fingerprint")
    matches = fingerprint == settings.profile_fingerprint
    profile = (
        f"{OK} {raw.get('profile_id')} ({fingerprint})"
        if matches
        else f"{TODO} {raw.get('profile_id') or 'none'} ({fingerprint or '-'}); "
        "run `csi-radio transmitter provision`"
    )
    power = raw.get("tx_power_quarter_dbm")
    uptime = raw.get("uptime_ms")
    firmware = raw.get("firmware_version", "?")
    ready = "yes" if raw.get("ready") else "no"
    radio = "active" if raw.get("radio_active") else "idle"
    uptime_text = "?" if uptime is None else f"{uptime / 1000:.0f} s"
    power_text = "?" if power is None else f"{power / 4:g} dBm"
    return [
        f"  MAC        {raw.get('mac')} ({raw.get('target')})",
        f"  Firmware   {firmware}, protocol {raw.get('protocol_version')}",
        f"  Profile    {profile}",
        f"  Ready      {ready} · radio {radio}",
        f"  Uptime     {uptime_text} · last reset {raw.get('reset_reason') or '?'}",
        f"  TX power   {power_text}",
    ]


def cmd_transmitter(args: argparse.Namespace) -> int:
    """Read or provision the transmitter through the gateway relay."""
    from .wireless_control import (
        GatewayWirelessPort,
        WirelessProvisioningDevice,
        discover_port,
    )

    settings = _settings(args)
    inventory = settings.inventory
    if not args.gateway_port:
        raise ValueError(
            "no gateway port: set connection.gateway_port or --gateway-port"
        )
    bridge = GatewayWirelessPort(
        args.gateway_port, transmitter_link=settings.connection["transmitter_link"]
    )
    try:
        if (
            bridge.gateway_status.get("role"),
            bridge.gateway_status.get("target"),
            bridge.gateway_status.get("mac"),
        ) != ("gateway", "esp32c6", inventory.gateway.mac):
            raise RuntimeError(
                "the board on the gateway port is not the configured gateway "
                f"{inventory.gateway.mac} (gateway identity mismatch)"
            )
        raw = discover_port(bridge.serial, timeout=5)
        if (raw.get("mac"), raw.get("role")) != (
            inventory.transmitter.mac,
            "transmitter",
        ):
            raise RuntimeError(
                f"the relay reached {raw.get('role')} {raw.get('mac')}, not the "
                f"configured transmitter {inventory.transmitter.mac}"
            )
        if args.action == "status":
            if args.json:
                print(json.dumps(raw, indent=2, sort_keys=True))
            else:
                print(
                    f"Transmitter {inventory.transmitter.id} through the gateway relay"
                )
                print("\n".join(_transmitter_lines(raw, settings)))
            return 0
        print(f"Sensing profile  {_profile_line(settings)}")
        if not _confirm("Write it to the transmitter through the relay?", args):
            return 1
        adapter = WirelessProvisioningDevice(
            bridge.serial,
            DeviceStatus.from_payload(json.dumps(raw).encode()),
            timeout=5,
        )
        report = RadioProvisioner([adapter]).provision(
            inventory, settings.profile, sequential=True
        )
        print(f"{OK} Transmitter profile committed: {report.fingerprint}")
        return 0
    finally:
        bridge.close()


# -- entry point --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Return the ``csi-radio`` parser with one subcommand per task."""
    parser = argparse.ArgumentParser(
        prog="csi-radio",
        description="Check, provision and pair the CSI radio boards.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(
        dest="command", title="commands", metavar="COMMAND"
    )

    status = commands.add_parser(
        "status",
        help="show configured boards, what is connected and what to do next (default)",
        description="Match the boards connected over USB to configs/radio.json "
        "and say what to do next. Opens each serial port briefly; boards are "
        "not reset.",
    )
    add_config_argument(status)
    status.add_argument("--json", action="store_true", help="machine-readable output")
    status.set_defaults(handler=cmd_status)

    check = commands.add_parser(
        "check",
        help="validate the radio configuration without opening hardware",
        description="Validate the configuration file and print the profile, "
        "fingerprint, boards and ports it sets. Opens no hardware.",
    )
    add_config_argument(check)
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.set_defaults(handler=cmd_check)

    provision = commands.add_parser(
        "provision",
        help="write the sensing profile to USB-connected C5 boards",
        description="Write the sensing profile and receiver list to the C5 "
        "transmitter and receivers. By default this guides a pass: connected "
        "boards that need the profile are written and verified, then you are "
        "asked to connect the next one. Boards that already store the profile "
        "are skipped; the gateway needs no profile.",
    )
    add_config_argument(provision)
    mode = provision.add_mutually_exclusive_group()
    mode.add_argument(
        "--one",
        action="store_true",
        help="write exactly one connected configured board, then stop",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="stage every board together and commit; needs all six boards on USB",
    )
    provision.add_argument(
        "--force",
        action="store_true",
        help="also rewrite boards that already store the profile, e.g. the "
        "transmitter after the receiver list changed",
    )
    provision.add_argument(
        "--yes",
        action="store_true",
        help="do not ask; write what is connected and stop",
    )
    provision.set_defaults(handler=cmd_provision)

    pair = commands.add_parser(
        "pair",
        help="pair the companion C6 relay with the gateway (new hardware only)",
        description="Store a fresh ESP-NOW key on the companion C6 relay and the "
        "gateway, on the backhaul channel from the configuration. Both reboot.",
    )
    add_config_argument(pair)
    pair.add_argument("--port", help="companion C6 USB port (default: from config)")
    pair.add_argument("--gateway-port", help="gateway USB port (default: from config)")
    pair.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    pair.set_defaults(handler=cmd_pair)

    transmitter = commands.add_parser(
        "transmitter",
        help="read or provision the transmitter through the gateway relay",
        description="Reach the untethered transmitter through the gateway and "
        "companion relay. `status` (default) prints what it reports; "
        "`provision` writes the sensing profile to it.",
    )
    transmitter.add_argument(
        "action", nargs="?", choices=("status", "provision"), default="status"
    )
    add_config_argument(transmitter)
    transmitter.add_argument(
        "--gateway-port", help="gateway USB port (default: from config)"
    )
    transmitter.add_argument(
        "--json", action="store_true", help="print the raw status as JSON"
    )
    transmitter.add_argument(
        "--yes", action="store_true", help="do not ask before provisioning"
    )
    transmitter.set_defaults(handler=cmd_transmitter)
    return parser


def _hint(exc: BaseException) -> str:
    text = str(exc)
    lowered = text.lower()
    if "busy" in lowered or "lock" in lowered or "resource temporarily" in lowered:
        return "the port is in use; close csi-live or csi-sessions and retry"
    if "no such file" in lowered or "could not open port" in lowered:
        return "the board is not connected at that path; run `csi-radio` to list boards"
    if "timed out" in lowered:
        return "the board did not answer; check power and firmware, then retry"
    return ""


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``csi-radio``.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        Process exit status: 0 on success, 1 when an operation failed or was
        declined, 2 for invalid input.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or (
        arguments[0].startswith("-") and arguments[0] not in {"-h", "--help"}
    ):
        arguments.insert(0, "status")
    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        return args.handler(args)
    except ValueError as exc:
        print(f"csi-radio {args.command}: {exc}", file=sys.stderr)
        return 2
    except (ProvisioningError, RuntimeError, OSError, TimeoutError) as exc:
        cause = exc.__cause__
        message = (
            f"{exc}: {cause}" if cause and str(cause) not in str(exc) else str(exc)
        )
        print(f"csi-radio {args.command}: {message}", file=sys.stderr)
        hint = _hint(exc) or (_hint(cause) if cause else "")
        if hint:
            print(f"  hint: {hint}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
