"""Build small synthetic sessions with valid journals for storage tests."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

RX1 = bytes.fromhex("44bd8dd0b14c")
RX2 = bytes.fromhex("44bd8dd0b350")
TX = bytes.fromhex("10bda39ecd68")
FOREIGN = bytes.fromhex("020000000001")
RUN = 0xABCDEF
WIDTH = 490
START_NS = 5_000_000_000


def mac_text(mac: bytes) -> str:
    """Format a MAC the way the session manifest does."""
    return ":".join(f"{b:02x}" for b in mac)


def payload_for(sequence: int, width: int = WIDTH) -> bytes:
    """Deterministic payload bytes for a frame."""
    return bytes((sequence * 7 + i * 3) % 251 for i in range(width))


def capture_ns(sequence: int) -> int:
    """Deterministic capture time of a frame."""
    return START_NS - 40_000_000 + sequence * 10_000_000


def record(
    receiver: bytes,
    sequence: int,
    width: int = WIDTH,
    *,
    transmitter: bytes = TX,
    payload: bytes | None = None,
    sig_mode: int = 1,
    rx_state: int = 0,
    flags: int = 0,
    radio_us: int | None = None,
    mcs: int = 0,
    bandwidth: int = 0,
    stbc: int = 0,
) -> bytes:
    """Encode one CSI record (87-byte header plus payload)."""
    payload = payload_for(sequence, width) if payload is None else payload
    header = (
        b"CSI1"
        + bytes([3, flags])
        + struct.pack(">HH", 87, len(payload))
        + receiver
        + transmitter
        + struct.pack(
            ">III",
            sequence // 2,
            sequence,
            1_000_000 + sequence * 10_000 if radio_us is None else radio_us,
        )
        + struct.pack(">bb", -40, -95)
        + bytes(
            [11, sig_mode, mcs, bandwidth, 1, 1, 0, stbc, 0, 0, 0, 44, 0, 0, rx_state]
        )
        + struct.pack(">HH", 36, len(payload))
        + struct.pack(">QQ", 5_000 + sequence, 6_000 + sequence)
        + b"0123456789abcdef"
    )
    assert len(header) == 87
    return header + payload


def envelope(
    batch_id: int, receiver: bytes, frames: list[bytes], run: int = RUN
) -> bytes:
    """Encode one gateway envelope holding the given records."""
    batch = (
        b"CSIB"
        + bytes([1, 0])
        + struct.pack(">HIIHH", 60, 77, batch_id, len(frames), 0)
        + bytes(40)
        + b"".join(struct.pack(">H", len(r)) + r for r in frames)
    )
    body = (
        b"CGWY"
        + bytes([1, 0])
        + struct.pack(">HQIII", 40, run, 9, 77, batch_id)
        + receiver
        + struct.pack(">HI", len(batch), 0)
        + batch
    )
    return body + struct.pack(">I", zlib.crc32(body))


def build_session(root: Path, batches: int = 6, era: str = "python") -> Path:
    """Write a session directory with two receivers and one attempt."""
    root.mkdir(parents=True)
    ids = {mac_text(RX1): "rx-1", mac_text(RX2): "rx-2"}
    (root / "session.json").write_text(
        json.dumps(
            {
                "artifact_schema_version": 2,
                "session_id": "20261113T000000000000Z",
                "protocol_hash": "feedface",
                "environment": {
                    "receiver_ids": ids,
                    "nominal_rate_hz": 100,
                    "radio_inventory": {"transmitter": {"mac": mac_text(TX)}},
                },
            }
        )
    )
    attempt = root / "trials" / "001_activity" / "attempt_01"
    attempt.mkdir(parents=True)
    # The window covers the first half of the capture times.
    middle = capture_ns(batches)
    (attempt / "attempt.json").write_text(
        json.dumps(
            {
                "trial_ordinal": 1,
                "repetition": 1,
                "scenario_id": "activity",
                "activity_label": "non_fall",
                "status": "accepted",
                "started_monotonic_ns": capture_ns(0),
                "ended_monotonic_ns": middle,
                "action_confirmed": False,
            }
        )
    )
    events = [
        {
            "kind": "phase_changed",
            "state": "countdown",
            "trial_ordinal": 1,
            "attempt": 1,
            "monotonic_ns": capture_ns(0),
        },
        {
            "kind": "phase_changed",
            "state": "action",
            "trial_ordinal": 1,
            "attempt": 1,
            "monotonic_ns": capture_ns(batches // 2),
        },
    ]
    (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    run_dir = root / "transport" / "gateway" / f"{RUN:016x}"
    run_dir.mkdir(parents=True)
    journal = bytearray()
    lines = []
    arrival = START_NS
    for batch in range(batches):
        for slot, receiver in enumerate((RX1, RX2)):
            sequences = (batch * 2, batch * 2 + 1)
            frames = [record(receiver, s) for s in sequences]
            data = envelope(batch, receiver, frames)
            journal += struct.pack(">QI", arrival, len(data)) + data
            if era == "python":
                for s in sequences:
                    lines.append(
                        {
                            "kind": "record",
                            "receiver_id": f"rx-{slot + 1}",
                            "sequence": s,
                            "receiver_boot_id": 77,
                            "transmitter_boot_id": 9,
                            "capture_host_ns": capture_ns(s),
                            "clock_uncertainty_us": 100.0,
                            "timely": True,
                        }
                    )
            else:
                lines.append(
                    {
                        "kind": "batch_acceptance",
                        "run": str(RUN),
                        "transmitter_boot": 9,
                        "receiver_boot": 77,
                        "receiver": mac_text(receiver),
                        "batch": batch,
                        "arrival_ns": arrival,
                        "available_ns": arrival + 1,
                        "clock_uncertainty_us": 100.0,
                        "records": [
                            {
                                "receiver": mac_text(receiver),
                                "sequence": s,
                                "tx_enqueue_us": 5_000 + s,
                                "capture_ns": capture_ns(s),
                            }
                            for s in sequences
                        ],
                    }
                )
            arrival += 5_000_000
    (run_dir / "envelopes.bin").write_bytes(bytes(journal))
    (run_dir / "events.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    (run_dir / "manifest.json").write_text("{}")
    return root


def write_frames(root: Path, frames: list[dict], *, receivers=(RX1, RX2)) -> None:
    """Write a gateway journal holding one envelope per frame.

    Each frame is a mapping with ``receiver`` (bytes), ``sequence`` and
    ``capture_ns``; every other key is forwarded to :func:`record`, except
    ``run`` (transport run, default :data:`RUN`) and ``uncertainty_us``
    (default 100). Frames are journaled in list order, one run directory per
    distinct ``run``, with strictly increasing arrival times.
    """
    names = {receiver: f"rx-{index + 1}" for index, receiver in enumerate(receivers)}
    runs: dict[int, list[dict]] = {}
    for frame in frames:
        runs.setdefault(frame.get("run", RUN), []).append(frame)
    for run, members in runs.items():
        run_dir = root / "transport" / "gateway" / f"{run:016x}"
        run_dir.mkdir(parents=True)
        journal, events = bytearray(), []
        for arrival, frame in enumerate(members, start=1_000_000):
            options = {
                key: value
                for key, value in frame.items()
                if key not in {"receiver", "sequence", "capture_ns", "run"}
                and key != "uncertainty_us"
            }
            data = envelope(
                arrival,
                frame["receiver"],
                [record(frame["receiver"], frame["sequence"], **options)],
                run=run,
            )
            journal += struct.pack(">QI", arrival, len(data)) + data
            events.append(
                {
                    "kind": "record",
                    "receiver_id": names[frame["receiver"]],
                    "sequence": frame["sequence"],
                    "receiver_boot_id": 77,
                    "transmitter_boot_id": 9,
                    "capture_host_ns": frame["capture_ns"],
                    "clock_uncertainty_us": frame.get("uncertainty_us", 100.0),
                    "timely": True,
                }
            )
        (run_dir / "envelopes.bin").write_bytes(bytes(journal))
        (run_dir / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events)
        )


def write_session(
    root: Path,
    *,
    attempts: list[dict],
    events: list[dict] | None = None,
    frames: list[dict] | None = None,
    receivers=(RX1, RX2),
    rate: int = 100,
    status: str = "complete",
    defaults: tuple[float, float, float] = (1, 2, 1),
    extra_session: dict | None = None,
) -> Path:
    """Write a closed schema-2 session with one scenario and journaled frames.

    Args:
        root: Session directory to create.
        attempts: ``attempt.json`` contents; each needs ``trial_ordinal`` and
            may set ``number`` (attempt number, default 1), which is not stored.
        events: Contents of ``events.jsonl``.
        frames: Journal frames for :func:`write_frames`; no journal when omitted.
        receivers: Receiver MACs, named ``rx-1``, ``rx-2``, ... in order.
        rate: Nominal sampling rate in hertz.
        status: Session status.
        defaults: Countdown, action and recovery seconds of the protocol.
        extra_session: Extra top-level ``session.json`` fields.

    Returns:
        ``root``.
    """
    root.mkdir(parents=True)
    names = {mac_text(mac): f"rx-{index + 1}" for index, mac in enumerate(receivers)}
    session = {
        "artifact_schema_version": 2,
        "session_id": root.name,
        "protocol_hash": "test-hash",
        "status": status,
        "environment": {
            "transport": "espnow_gateway",
            "nominal_rate_hz": rate,
            "radio_inventory": {"transmitter": {"mac": mac_text(TX)}},
            "receiver_ids": names,
        },
        **(extra_session or {}),
    }
    (root / "session.json").write_text(json.dumps(session))
    countdown, action, recovery = defaults
    (root / "protocol.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "protocol_id": "test",
                "title": "Test",
                "defaults": {
                    "countdown_seconds": countdown,
                    "action_seconds": action,
                    "recovery_seconds": recovery,
                },
                "blocks": [
                    {
                        "id": "block",
                        "title": "Block",
                        "scenarios": [
                            {
                                "id": "sit",
                                "activity_label": "sit",
                                "title": "Sit",
                                "instruction": "Sit down",
                                "repetitions": 1,
                            }
                        ],
                    }
                ],
            }
        )
    )
    for attempt in attempts:
        manifest = dict(attempt)
        number = manifest.pop("number", 1)
        directory = root / "trials" / f"{manifest['trial_ordinal']:03d}_sit"
        directory = directory / f"attempt_{number:02d}"
        directory.mkdir(parents=True)
        (directory / "attempt.json").write_text(
            json.dumps({"artifact_schema_version": 2, **manifest})
        )
    (root / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events or [])
    )
    if frames is not None:
        write_frames(root, frames, receivers=receivers)
    return root
