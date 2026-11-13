"""Worker for tests that convert one session from several processes at once."""

from __future__ import annotations

from typing import Any


def ensure_tables(source: str, frames: str, barrier: Any, results: Any) -> None:
    """Convert ``source`` into ``frames`` and read every table back.

    Args:
        source: Session directory or archive.
        frames: Directory for the converted tables.
        barrier: Barrier that releases all workers together.
        results: Queue that receives the published fingerprint, the progress
            messages, and the row counts, or the error text on failure.
    """
    from fall_detection._radio_native import FrameStore

    messages: list[str] = []
    try:
        barrier.wait(timeout=60)
        store = FrameStore.ensure(source, frames, progress=messages.append)
        results.put(
            {
                "fingerprint": store.source_fingerprint,
                "messages": messages,
                "frames": store.frames().num_rows,
                "attempts": store.attempts().num_rows,
                "phases": store.phases().num_rows,
            }
        )
    except Exception as error:  # noqa: BLE001 - reported to the parent test
        results.put({"error": repr(error)})
