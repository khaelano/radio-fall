"""Finalize a drained collector working session into its raw archive."""

from pathlib import Path

from .._radio_native import storage_archive_session


def finalize_recording(root: Path) -> Path:
    """Publish a verified raw archive after all acquisition resources close.

    Working directories remain available for resume and recovery. Resuming a
    previously archived session publishes a numbered revision without replacing
    an earlier raw archive.
    """
    destination = root.with_suffix(".zip")
    revision = 1
    while destination.exists():
        destination = root.parent / f"{root.name}.revision-{revision:03d}.zip"
        revision += 1
    storage_archive_session(root, destination)
    return destination
