"""Migrate an existing amplitude v1 export to checked, memory-mappable v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fall_detection.analysis.sequence_segments import migrate_v1_dataset


def main() -> None:
    """Migrate one named dataset while retaining the source export."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("akmal", "khaelano", "continuous_non_fall"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / "data/processed"
    result = migrate_v1_dataset(
        root / "amplitude_sequence_v1" / args.dataset,
        root / "amplitude_sequence_v2" / args.dataset,
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
