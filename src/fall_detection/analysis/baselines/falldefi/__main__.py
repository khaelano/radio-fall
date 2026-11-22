"""Run a reproducible FallDeFi adaptation on recorded session archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ...sequence.alignment import RECEIVERS
from .dataset import FALLDEFI_SUBCARRIERS, load_traces
from .experiment import run_experiment, save_experiment
from .model import FallDeFiConfig


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
        "--split-by", choices=("attempt", "session", "participant"), default="attempt"
    )
    parser.add_argument("--test-fraction", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--margin-seconds", type=float, default=1.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--minimum-seconds", type=float, default=1.0)
    parser.add_argument("--max-gap-seconds", type=float, default=0.25)
    parser.add_argument("--minimum-coverage", type=float, default=0.7)
    parser.add_argument("--minimum-receivers", type=int, default=2)
    parser.add_argument("--wavelet-levels", type=int, default=1)
    parser.add_argument("--components", type=int, default=3)
    parser.add_argument(
        "--threshold-k",
        type=float,
        default=None,
        help="Fixed noise-threshold k (the released code uses 4.3); "
        "calibrated on training traces when omitted.",
    )
    parser.add_argument(
        "--detection-target",
        type=float,
        default=0.95,
        help="Share of training traces that must contain an event when calibrating k.",
    )
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument(
        "--receivers",
        nargs="+",
        default=list(RECEIVERS),
        help="Receivers to use, each treated as one link.",
    )
    parser.add_argument(
        "--subcarriers",
        type=int,
        nargs="+",
        default=FALLDEFI_SUBCARRIERS,
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
        config = FallDeFiConfig(
            wavelet_levels=args.wavelet_levels,
            components=args.components,
            threshold_k=args.threshold_k,
            detection_target=args.detection_target,
            cv_folds=args.cv_folds,
            random_seed=args.seed,
        )
        dataset = load_traces(
            sources,
            root=root,
            fall_labels=tuple(args.fall_label),
            non_fall_labels=tuple(args.non_fall_label),
            margin_seconds=args.margin_seconds,
            interval_seconds=args.interval_seconds,
            minimum_seconds=args.minimum_seconds,
            receivers=tuple(args.receivers),
            minimum_receivers=args.minimum_receivers,
            subcarriers=tuple(args.subcarriers),
            max_gap_seconds=args.max_gap_seconds,
            minimum_coverage=args.minimum_coverage,
        )
        result = run_experiment(
            dataset,
            config,
            split_by=args.split_by,
            test_fraction=args.test_fraction,
        )
        save_experiment(result, output)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))
    report = result.report
    print(
        json.dumps(
            {
                "output": str(output),
                "held_out": report["held_out"],
                "held_out_event_detection": report["held_out_event_detection"],
                "held_out_false_alarms": report["held_out_false_alarms"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
