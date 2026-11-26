"""On-disk schema version of recorded sessions.

Kept in a leaf module so ``collection`` can import it without loading the
session models, which in turn depend on ``protocol``.
"""

ARTIFACT_SCHEMA_VERSION = 2
"""Current on-disk layout for a recorded session bundle.

Schema 1 (root-level ``csi.csv``/``radio_timing.csv``/``clock_sync.csv`` plus
camera comparator artifacts) is obsolete and is neither written nor read.
Schema 2 may optionally add attempt-level video and frame timing sidecars.
"""

PROTOCOL_SNAPSHOT = "protocol.json"
"""The protocol a session started with; never rewritten."""

PROTOCOL_REVISIONS_DIR = "protocol_revisions"
"""Folder of protocols revised during recording, ``<NNN>.json`` each.

``session.json`` lists them in ``protocol_revisions``; the last one is the plan
the session followed when it last recorded. ``protocol_hash`` keeps naming the
starting protocol, so reviews and caches bound to it stay valid.
"""


def protocol_snapshot_name(manifest: dict) -> str:
    """Return the session file holding the most recent protocol.

    Args:
        manifest: The decoded ``session.json``.

    Returns:
        ``protocol.json``, or the last listed revision file.

    Raises:
        ValueError: The last revision entry names a path outside
            :data:`PROTOCOL_REVISIONS_DIR`.
    """
    revisions = manifest.get("protocol_revisions") or []
    if not revisions:
        return PROTOCOL_SNAPSHOT
    path = str(revisions[-1].get("path", ""))
    parts = path.split("/")
    if (
        len(parts) != 2
        or parts[0] != PROTOCOL_REVISIONS_DIR
        or parts[1]
        in {
            "",
            ".",
            "..",
        }
    ):
        raise ValueError(f"invalid protocol revision path {path!r}")
    return path


def latest_protocol_hash(manifest: dict) -> str:
    """Return the hash of the most recent protocol of a session."""
    revisions = manifest.get("protocol_revisions") or []
    if revisions:
        return str(revisions[-1].get("protocol_hash") or "")
    return str(manifest.get("protocol_hash") or "")
