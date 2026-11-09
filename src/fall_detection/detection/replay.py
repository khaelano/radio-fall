"""Read-only capture-aligned replay of one closed collection attempt."""

from dataclasses import replace
import json
from pathlib import Path

from ..radio.acquisition.native import require_native
from ..radio.acquisition.protocol import parse_csi_line
from ..radio.acquisition.wire import encode_csi_datagram
from .model import ModelBundle, load_ensemble, score_tensor


def load_attempt(
    bundle: ModelBundle, session: Path, attempt_id: str, offset: float = 0.0
) -> tuple[list, int]:
    """Validate row/clock/identity alignment and return native records for replay."""
    root = session.resolve()
    manifest = json.loads((root / "session.json").read_text())
    if manifest.get("status") == "open" or manifest.get("artifact_schema_version") != 2:
        raise ValueError("Replay requires a closed schema-2 session")
    ordinal, number = map(int, attempt_id.split("/"))
    matches = list(
        root.glob(f"trials/{ordinal:03d}_*/attempt_{number:02d}/attempt.json")
    )
    if len(matches) != 1:
        raise ValueError("Replay requires one matching attempt")
    directory = matches[0].parent
    attempt = json.loads(matches[0].read_text())
    if attempt["status"] != "accepted":
        raise ValueError("Replay requires an accepted attempt")
    actions = [
        json.loads(line)
        for line in (root / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    actions = [
        e
        for e in actions
        if e.get("kind") == "phase_changed"
        and e.get("state") == "action"
        and e.get("trial_ordinal") == ordinal
        and e.get("attempt") == number
    ]
    if len(actions) != 1:
        raise ValueError("Action cue is missing or ambiguous")
    start = actions[0]["monotonic_ns"] + round(offset * 1e9)
    if (
        start < attempt["started_monotonic_ns"]
        or start + 4_000_000_000 > attempt["ended_monotonic_ns"]
    ):
        raise ValueError("Replay window is outside the recording")
    environment = manifest["environment"]
    radio = bundle.metadata["radio"]
    if (
        environment["radio_profile_fingerprint"] != radio["profile_fingerprint"]
        or environment["radio_inventory"]["transmitter"]["mac"].lower()
        != radio["transmitter_mac"].lower()
    ):
        raise ValueError("Replay radio profile/transmitter differs from model")
    core = require_native()
    rows = []
    epoch = None
    for rx, receiver in enumerate(bundle.metadata["receivers"]):
        path = directory / "receivers" / receiver
        sidecar = [
            json.loads(line)
            for line in (path / "gateway_timing.jsonl").read_text().splitlines()
            if line.strip()
        ]
        identities = {
            (r["run_id"], r["transmitter_boot_id"], r["receiver_boot_id"])
            for r in sidecar
        }
        if len(identities) != 1:
            raise ValueError("Replay sidecar mixes clock epochs")
        shared = next(iter(identities))[:2]
        if epoch is not None and shared != epoch:
            raise ValueError("Replay receivers use different transmitter epochs")
        epoch = shared
        with (path / "csi.csv").open() as stream:
            next(stream)
            for line, timing in zip(stream, sidecar, strict=True):
                record = parse_csi_line(line)
                if (
                    record.sequence != timing["sequence"]
                    or record.timestamp_us != timing["rx_radio_timestamp_us"]
                    or timing["schema_version"] != 1
                    or timing["receiver_mac"].lower()
                    != radio["receiver_macs"][rx].lower()
                ):
                    raise ValueError(
                        "CSI/gateway timing rows or receiver identity differ"
                    )
                if record.mac.lower() != radio["transmitter_mac"].lower():
                    continue
                capture = timing["capture_host_monotonic_ns"]
                if not isinstance(capture, int):
                    raise ValueError("Capture clock is unavailable")
                if start - 150_000_000 <= capture < start + 4_000_000_000:
                    record = replace(
                        record, profile_fingerprint=radio["profile_fingerprint"]
                    )
                    encoded = encode_csi_datagram(
                        record,
                        receiver_mac=radio["receiver_macs"][rx],
                        transport_sequence=record.sequence,
                    )
                    rows.append((core.decode_cnn_record(encoded), rx, capture))
    return rows, start


def replay(
    bundle: ModelBundle,
    session: Path,
    attempt_id: str,
    offset: float,
    *,
    kernel: str = "auto",
    workers: int = 2,
    threads: int = 2,
) -> dict:
    """Run the production native preprocessor and ensemble without opening hardware."""
    rows, start = load_attempt(bundle, session, attempt_id, offset)
    native = require_native().CnnPreprocessor(
        bundle.mean.ravel().tolist(),
        bundle.scale.ravel().tolist(),
        bundle.metadata["minimum_coverage"],
        workers,
        kernel=kernel,
        representation=bundle.metadata["representation"],
    )
    try:
        window = native.build(rows, start)
        result = json.loads(window.metadata_json())
        if result["valid"]:
            probability, seeds = score_tensor(
                load_ensemble(bundle, threads), window.tensor_bytes()
            )
            result.update(
                probability=probability,
                seed_probabilities=seeds,
                candidate=probability >= bundle.metadata["threshold"],
            )
        else:
            result.update(probability=None, candidate=None)
        return dict(
            kind="replay", attempt_id=attempt_id, offset_seconds=offset, **result
        )
    finally:
        native.close()
