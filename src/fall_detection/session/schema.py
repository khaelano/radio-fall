"""On-disk schema version of recorded sessions.

Kept in a leaf module so ``collection`` can import it without loading the
session models, which in turn depend on ``collection.protocol``.
"""

ARTIFACT_SCHEMA_VERSION = 2
"""Current on-disk layout for a recorded session bundle.

Schema 1 (root-level ``csi.csv``/``radio_timing.csv``/``clock_sync.csv`` plus
camera comparator artifacts) is obsolete and is neither written nor read.
Schema 2 may optionally add attempt-level video and frame timing sidecars.
"""
