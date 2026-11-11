"""Run small stratified training pilots inside the notebook's guarded workers."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from fall_detection.analysis.sequence_training_profile import (
    prepare_profile, profile_table, refresh_projections,
)
from fall_detection.analysis.sequence_training_worker import run_worker


def main() -> None:
    """Profile requested models/durations using an existing saved attempt split."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--models", nargs="+", choices=("cnn", "lstm", "gru"),
                        default=["cnn", "lstm", "gru"])
    parser.add_argument("--durations", nargs="+", type=int, choices=(2, 4, 6),
                        default=[2, 4, 6])
    parser.add_argument("--per-stratum", type=int, default=4)
    parser.add_argument("--recurrent-chunk-steps", type=int, default=32)
    parser.add_argument("--micro-batch-size", type=int, default=32)
    parser.add_argument("--reuse-selection", action="store_true")
    args = parser.parse_args()
    if not args.reuse_selection:
        print(prepare_profile(args.run_dir, args.per_stratum), flush=True)
    # Import after argument validation; GPU initialization stays in the worker.
    from fall_detection.analysis.tinygrad_training import TrainingConfig
    results = []
    for duration in args.durations:
        for kind in args.models:
            result = run_worker(
                args.run_dir, "profile", kind=kind, duration=duration,
                config=asdict(TrainingConfig(
                    recurrent_chunk_steps=args.recurrent_chunk_steps,
                    micro_batch_size=args.micro_batch_size,
                )), timeout_seconds=900,
            )
            results.append(result)
            table = profile_table(results)
            table.write_csv(args.run_dir / "profile" / "comparison.csv")
            print(table, flush=True)
        run_worker(args.run_dir, "loading", duration=duration, timeout_seconds=600)
        results = refresh_projections(args.run_dir)
        print(profile_table(results), flush=True)


if __name__ == "__main__":
    main()
