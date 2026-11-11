"""Compare v1 and v2 window loaders on one dataset under warm OS caches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from fall_detection.analysis.sequence_training_data import (
    Normalizer,
    SegmentStore,
    SequenceDataset,
    ShardStore,
)


def main() -> None:
    """Time two paired passes per format, with the same normalization cost."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("akmal", "khaelano", "continuous_non_fall"))
    parser.add_argument("--duration", type=int, default=2, choices=(2, 4, 6))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / "data/processed"
    normalizer = Normalizer(
        np.zeros(980, dtype=np.float32),
        np.ones(980, dtype=np.float32),
        np.ones(980, dtype=np.int64),
    )
    observations = []
    for pass_number, version in enumerate((1, 2, 2, 1), 1):
        folder = root / f"amplitude_sequence_v{version}" / args.dataset
        frame = (
            pl.read_parquet(folder / "window_index.parquet")
            .filter(pl.col("duration") == args.duration)
            .with_columns(
                pl.col("signal" if version == 2 else "shard")
                .map_elements(
                    lambda p: str((folder / p).resolve()), return_dtype=pl.String
                )
                .alias("path")
            )
        )
        store = SegmentStore() if version == 2 else ShardStore(128 * 1024**2)
        dataset = SequenceDataset(frame, normalizer, store)
        started, count = perf_counter(), 0
        for _, rows in dataset.batches(32, seed=45):
            count += len(rows)
        result = dict(
            pass_number=pass_number,
            version=version,
            windows=count,
            seconds=perf_counter() - started,
        )
        observations.append(result)
        print(json.dumps(result), flush=True)
    v1 = observations[-1]["seconds"]
    v2 = observations[-2]["seconds"]
    result = dict(
        dataset=args.dataset,
        duration=args.duration,
        cache_condition="OS cache retained; no cache drop; sequential ABBA passes",
        passes=observations,
        repeat_v2_over_v1=v2 / v1,
        gate_passed=v2 <= 1.05 * v1,
    )
    destination = root / "amplitude_sequence_v2" / args.dataset / "reports"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f"loader-benchmark-{args.duration}s.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
