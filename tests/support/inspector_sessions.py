"""Journal helpers for synthetic inspector sessions."""

from __future__ import annotations

import json
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from fall_detection._radio_native import storage_archive_session
from journal_builder import RUN, RX1, RX2, TX, envelope, record

RECEIVERS = {"rx-1": RX1, "rx-2": RX2}
FIRST_ATTEMPT_NS = 1_000_000_000_000
ATTEMPT_SPACING_NS = 10_000_000_000
ATTEMPT_LENGTH_NS = 2_000_000_000


def archive_of(directory: Path, root: Path) -> Path:
    """Archive ``directory`` at ``<root>/data/raw/sessions/<name>.zip``."""
    destination = root / "data/raw/sessions" / f"{directory.name}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    storage_archive_session(str(directory), str(destination))
    return destination


def attempt_origin(position: int) -> int:
    """Return the start time of the ``position``-th synthetic attempt."""
    return FIRST_ATTEMPT_NS + position * ATTEMPT_SPACING_NS


def csi_payload(values: Iterable[complex]) -> bytes:
    """Encode complex subcarrier values as firmware bytes, imaginary first."""
    return bytes(
        part & 0xFF for value in values for part in (int(value.imag), int(value.real))
    )


@dataclass(frozen=True)
class FrameSpec:
    """One journal frame: who captured it, when, and what it carries."""

    sequence: int
    capture_ns: int
    receiver_id: str = "rx-1"
    values: tuple[complex, ...] = ()
    payload: bytes | None = None
    first_word_invalid: bool = False

    def data(self) -> bytes:
        """Return the payload bytes."""
        if self.payload is not None:
            return self.payload
        return csi_payload(self.values or (complex(self.sequence, 2),) * 2)


def write_journal(root: Path, frames: Sequence[FrameSpec]) -> None:
    """Write a gateway journal holding ``frames`` in the given arrival order."""
    run_dir = root / "transport" / "gateway" / f"{RUN:016x}"
    run_dir.mkdir(parents=True, exist_ok=True)
    journal, lines = bytearray(), []
    for batch, frame in enumerate(frames):
        data = envelope(
            batch,
            RECEIVERS[frame.receiver_id],
            [
                record(
                    RECEIVERS[frame.receiver_id],
                    frame.sequence,
                    payload=frame.data(),
                    sig_mode=4,
                    flags=int(frame.first_word_invalid),
                    transmitter=TX,
                )
            ],
        )
        journal += struct.pack(">QI", 1 + batch * 1_000, len(data)) + data
        lines.append(
            {
                "kind": "record",
                "receiver_id": frame.receiver_id,
                "sequence": frame.sequence,
                "receiver_boot_id": 77,
                "transmitter_boot_id": 9,
                "capture_host_ns": frame.capture_ns,
                "clock_uncertainty_us": 100.0,
                "timely": True,
            }
        )
    (run_dir / "envelopes.bin").write_bytes(bytes(journal))
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines)
    )
    (run_dir / "manifest.json").write_text("{}")


def default_frames(attempts: Sequence[tuple[int, int, str]]) -> list[FrameSpec]:
    """Return two ``rx-1`` frames per attempt, captured out of delivery order."""
    frames = []
    for position, _ in enumerate(attempts):
        origin = attempt_origin(position)
        first = position * 10 + 1
        frames.append(FrameSpec(first, origin + 1_200_000_000))
        frames.append(FrameSpec(first + 1, origin + 200_000_000))
    return frames
