"""Explicit access to the unchanged pilot's pinned decoder and CNN helpers."""

from pathlib import Path
import sys

FOLDER = Path(__file__).resolve().parent
PILOT = FOLDER.parent / "03_cnn_baseline"
if str(PILOT) not in sys.path:
    sys.path.append(str(PILOT))

from data_pipeline import read_json, sha256, write_json  # noqa: E402,F401


def code_hashes() -> dict:
    """Fingerprint experiment and reused pilot code."""
    paths = [
        *FOLDER.glob("*.py"),
        PILOT / "data_pipeline.py",
        PILOT / "modeling.py",
        *sorted((PILOT / "vendor").glob("*.py")),
    ]
    return {str(p.relative_to(FOLDER.parent)): sha256(p) for p in sorted(paths)}


def case_path(output: Path, condition: str, seed: int) -> Path:
    """Locate one memory-mapped prepared condition/realization."""
    return output / "arrays" / condition / str(seed)
