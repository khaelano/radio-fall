"""Time the complete Polars/Rust pipeline and optionally verify previous arrays."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import polars as pl

from fall_detection.analysis.amplitude_pipeline import load_amplitude_session, preprocess_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--parquet-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--verify-dir", type=Path)
    parser.add_argument("--recordings", type=int)
    parser.add_argument("--compression-level", type=int, default=1)
    args = parser.parse_args()
    if args.recordings is not None and args.recordings < 1:
        parser.error("--recordings must be positive")
    if args.verify_dir is not None and args.output_dir.resolve() == args.verify_dir.resolve():
        parser.error("Verification requires independent output directories")
    started = perf_counter()
    session = load_amplitude_session(
        args.session_dir,
        args.parquet_dir or Path("data/interim/parquet") / args.session_dir.name,
    )
    recordings = (
        session.attempts.filter(
            (pl.col("status") == "accepted")
            & (pl.col("inclusion") != "exclude").fill_null(True)
        ).explode("receiver_ids").drop_nulls("receiver_ids")
        .sort("trial_ordinal", "attempt", "receiver_ids")
    )
    if args.recordings is not None:
        recordings = recordings.head(args.recordings)
    loaded = perf_counter()
    summary = preprocess_dataset(
        session, recordings, args.output_dir, compression_level=args.compression_level,
    )
    ended = perf_counter()
    verified = 0
    if args.verify_dir is not None:
        for row in summary.iter_rows(named=True):
            path = Path(row["output"])
            relative = path.relative_to(args.output_dir.resolve())
            with np.load(path) as actual, np.load(args.verify_dir / relative) as previous:
                assert set(actual.files) == set(previous.files), str(relative)
                for name in actual.files:
                    if name != "provenance_json":
                        np.testing.assert_array_equal(
                            actual[name], previous[name], err_msg=f"{relative}: {name}",
                        )
            verified += 1
    print(json.dumps({
        "recordings": len(summary), "startup_seconds": loaded-started,
        "pipeline_seconds": ended-loaded, "total_seconds": ended-started,
        "verified_recordings": verified,
        "stage_seconds": {
            name: summary[name].sum()
            for name in ("read_seconds", "prepare_seconds", "hampel_seconds")
        },
        "compression_level": args.compression_level,
    }, indent=2))


if __name__ == "__main__":
    main()
