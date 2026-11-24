"""Command line for the live fall-score program; Rust owns acquisition and inference."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fall_detection.radio.settings import add_live_arguments

from .gui import DEFAULT_MODELS, MODELS


def parser() -> argparse.ArgumentParser:
    """Expose native live, replay, GUI and headless detector options."""
    result = argparse.ArgumentParser(description=__doc__)
    add_live_arguments(result)
    result.add_argument("--model-root", type=Path, default=Path("artifacts/model"))
    result.add_argument(
        "--models", nargs="+", choices=MODELS, default=list(DEFAULT_MODELS)
    )
    result.add_argument("--backend", choices=["webgpu", "cpu"], default="webgpu")
    result.add_argument("--ort-library", type=Path)
    result.add_argument("--webgpu-plugin", type=Path)
    result.add_argument(
        "--adapter-id",
        type=lambda value: int(value, 0),
        help="PCI device ID of the AMD GPU; default selects the only one",
    )
    result.add_argument(
        "--replay-capture",
        nargs="+",
        type=Path,
        metavar="CAPTURE_DIR",
        help="Stream recorded native captures in real time instead of the gateway",
    )
    result.add_argument("--replay-speed", type=float, default=1.0)
    result.add_argument(
        "--replay-repeat", action="store_true", help="Loop the replayed captures"
    )
    result.add_argument("--minimum-coverage", type=float, default=0.7)
    result.add_argument("--packet-capacity", type=int, default=2048)
    result.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="decision threshold of models without a calibration",
    )
    result.add_argument(
        "--calibration",
        type=Path,
        metavar="FILE",
        help="calibration.json of an earlier run; the window also records a new one",
    )
    result.add_argument("--headless", action="store_true")
    result.add_argument(
        "--duration", type=float, help="stop live acquisition after this many seconds"
    )
    result.add_argument("--hop-ms", type=int, default=250)
    result.add_argument("--grace-ms", type=int, default=900)
    result.add_argument("--output-dir", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    """Validate arguments and run the native detector frontend.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        Process exit status.
    """
    cli = parser()
    args = cli.parse_args(argv)
    if args.duration is not None and args.duration <= 0:
        cli.error("--duration must be positive")
    if not 0 <= args.threshold <= 1:
        cli.error("--threshold must be between 0 and 1")
    if args.calibration and args.headless:
        cli.error("--calibration needs the window; headless output has no decisions")
    from .gui import run

    try:
        return run(args)
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        print(f"fall-detect: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
