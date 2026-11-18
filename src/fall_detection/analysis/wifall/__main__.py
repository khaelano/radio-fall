"""Run a reproducible WiFall adaptation on recorded session archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dataset import DEFAULT_SUBCARRIERS, load_dataset
from .experiment import run_experiment, save_experiment
from .model import WiFallConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--session",
        type=Path,
        action="append",
        required=True,
        help="Raw session archive or directory; repeat to combine sessions.",
    )
    parser.add_argument("--fall-label", action="append", required=True)
    parser.add_argument("--non-fall-label", action="append", required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New result directory."
    )
    parser.add_argument(
        "--classifier",
        choices=("random_forest", "one_class_svm"),
        default="random_forest",
    )
    parser.add_argument(
        "--representation",
        choices=("statistics", "singular_values"),
        default="statistics",
    )
    parser.add_argument(
        "--split-by", choices=("attempt", "session", "participant"), default="attempt"
    )
    parser.add_argument("--test-fraction", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--window-seconds", type=float, default=2.0)
    parser.add_argument("--hop-seconds", type=float, default=1.0)
    parser.add_argument("--smoothing-samples", type=int, default=5)
    parser.add_argument("--lof-neighbors", type=int, default=20)
    parser.add_argument("--lof-threshold", type=float, default=1.5)
    parser.add_argument("--svm-nu", type=float, default=0.1)
    parser.add_argument("--forest-trees", type=int, default=200)
    parser.add_argument("--entropy-bins", type=int, default=16)
    parser.add_argument("--max-stable-windows", type=int, default=128)
    parser.add_argument("--max-gap-seconds", type=float, default=0.025)
    parser.add_argument("--minimum-coverage", type=float, default=0.9)
    parser.add_argument(
        "--subcarriers",
        type=int,
        nargs="+",
        default=DEFAULT_SUBCARRIERS,
        help="Fixed HE20 physical tone indices, chosen before looking at test data.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Train and evaluate from explicit sources, labels, and a new output path.

    Args:
        argv: CLI arguments; process arguments when omitted.

    Returns:
        Zero after publishing the result; argparse reports invalid inputs.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve()
    sources = [path.resolve() for path in args.session]
    protected = [root / "data/raw", root / "data/old_raw", *sources]
    if output.exists():
        parser.error("--output must be a new directory")
    if any(output.is_relative_to(path) for path in protected):
        parser.error("--output must be outside raw recording paths")
    try:
        config = WiFallConfig(
            sample_rate_hz=120,
            window_seconds=args.window_seconds,
            smoothing_samples=args.smoothing_samples,
            lof_neighbors=args.lof_neighbors,
            lof_threshold=args.lof_threshold,
            svm_nu=args.svm_nu,
            forest_trees=args.forest_trees,
            random_seed=args.seed,
            representation=args.representation,
            entropy_bins=args.entropy_bins,
        )
        dataset = load_dataset(
            sources,
            root=root,
            window_seconds=args.window_seconds,
            hop_seconds=args.hop_seconds,
            subcarriers=tuple(args.subcarriers),
            max_gap_seconds=args.max_gap_seconds,
            minimum_coverage=args.minimum_coverage,
            fall_labels=tuple(args.fall_label),
            non_fall_labels=tuple(args.non_fall_label),
        )
        result = run_experiment(
            dataset,
            config,
            classifier=args.classifier,
            split_by=args.split_by,
            test_fraction=args.test_fraction,
            max_stable_windows=args.max_stable_windows,
        )
        save_experiment(result, output)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {"output": str(output), "held_out": result.report["held_out"]}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
