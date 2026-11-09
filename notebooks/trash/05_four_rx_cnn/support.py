"""Access canonical processing and shared CNN experiment helpers."""

from pathlib import Path
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
SHARED = FOLDER.parent / "shared_cnn"
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(ROOT / "src"))

from shared import (  # noqa: E402
    bin_values,
    cluster_intervals,
    metrics,
    predict,
    read_json,
    sha256,
    SmallCNN,
    smooth_valid,
    summarize_features,
    write_json,
)
from fall_detection.analysis.phase_motion import phase_change_matrix  # noqa: E402
from fall_detection.analysis.phase_signals import load_phase_signal  # noqa: E402

__all__ = [
    "FOLDER",
    "ROOT",
    "SHARED",
    "LABELS",
    "SmallCNN",
    "bin_values",
    "cluster_intervals",
    "code_hashes",
    "load_phase_signal",
    "metrics",
    "phase_change_matrix",
    "predict",
    "read_json",
    "sha256",
    "smooth_valid",
    "summarize_features",
    "write_json",
]

LABELS = (
    "walk_to_fall",
    "sit_to_fall",
    "stand_to_fall",
    "walk_to_sit",
    "sit_to_walk",
    "sit_to_stand",
    "walk_to_stand",
    "stand_to_walk",
    "stand_to_sit",
)


def code_hashes() -> dict[str, str]:
    """Hash experiment code and every repository Python dependency for provenance."""
    paths = [
        *FOLDER.glob("*.py"),
        *SHARED.glob("*.py"),
        *(ROOT / "src/fall_detection").rglob("*.py"),
    ]
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(set(paths))}
