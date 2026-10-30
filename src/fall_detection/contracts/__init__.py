"""Shared session, annotation, and prediction contracts.

Contracts will be added here when the radio acquisition, collection, and
evaluation modules need to exchange concrete artifacts. Acquisition-specific
samples remain in their own modules.
"""

ARTIFACT_SCHEMA_VERSION = 2
"""Current on-disk layout for a recorded session bundle.

Schema 1 (root-level ``csi.csv``/``radio_timing.csv``/``clock_sync.csv`` plus
camera artifacts) is obsolete and is neither written nor read.
"""
