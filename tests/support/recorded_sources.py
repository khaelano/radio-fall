"""Synthetic four-receiver 120 Hz recordings for the classical baselines."""

import json

import inspector_sessions
from inspector_sessions import FrameSpec, attempt_origin
from journal_builder import TX, mac_text

CUES = (("countdown", 0), ("action", 500_000_000), ("recovery", 1_500_000_000))
"""Cue states and their offsets from the attempt origin, in nanoseconds."""


def four_receiver_source(
    session_factory, monkeypatch, *, cues=CUES, samples=240, first=0, skip=()
):
    """Build a closed 120 Hz, channel 44 session with one accepted attempt.

    Args:
        session_factory: The shared session fixture.
        monkeypatch: Pytest monkeypatch, used to register rx-3 and rx-4.
        cues: Collection cue states with nanosecond offsets from the origin.
        samples: End of the grid, in samples from the attempt origin.
        first: First recorded sample, to start packets after the countdown.
        skip: Receivers that record no packets.

    Returns:
        The session directory.
    """
    receivers = {
        **inspector_sessions.RECEIVERS,
        "rx-3": bytes.fromhex("44bd8dd0be9c"),
        "rx-4": bytes.fromhex("44bd8dd0b66c"),
    }
    for receiver, mac in receivers.items():
        monkeypatch.setitem(inspector_sessions.RECEIVERS, receiver, mac)
    origin = attempt_origin(0)
    frames = [
        FrameSpec(
            sequence=sequence,
            capture_ns=origin + round(sequence / 120 * 1e9),
            receiver_id=receiver,
            # Compact HE20 slot 122 is the positive edge tone. Inspected C5
            # recordings contain zeros here; the default interior schema must
            # still produce windows without inventing amplitudes for that tone.
            values=(10 + 5j,) * 122 + (0j,) + (10 + 5j,) * 122,
        )
        for sequence in range(first, samples)
        for receiver in receivers
        if receiver not in skip
    ]
    source = session_factory(attempts=((1, 1, "accepted"),), frames=frames)
    manifest_path = source / "session.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["environment"].update(
        {
            "radio_inventory": {"transmitter": {"mac": mac_text(TX)}},
            "receiver_ids": {mac_text(mac): rx for rx, mac in receivers.items()},
            "nominal_rate_hz": 120,
            "radio_profile": {
                "band": "5ghz",
                "bandwidth_mhz": 20,
                "channel": 44,
                "nominal_rate_hz": 120,
            },
        }
    )
    manifest_path.write_text(json.dumps(manifest))
    events = [
        {
            "kind": "phase_changed",
            "trial_ordinal": 1,
            "attempt": 1,
            "state": state,
            "monotonic_ns": origin + offset,
        }
        for state, offset in cues
    ]
    (source / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    return source
