"""Run the four-receiver EDA, shifted preprocessing and CNN comparison."""

import argparse
from pathlib import Path

from support import FOLDER, read_json


def main() -> None:
    """Execute explicit stages into a separate derived artifact directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=FOLDER / "config.json")
    parser.add_argument("--output", type=Path, default=FOLDER / "artifacts/four_rx_v1")
    parser.add_argument(
        "--stage",
        choices=["all", "prepare", "eda", "train", "evaluate", "report"],
        default="all",
    )
    args = parser.parse_args()
    config, output = read_json(args.config.resolve()), args.output.resolve()
    raw = (FOLDER / config["session_path"]).resolve()
    if output.is_relative_to(raw) or raw.is_relative_to(output):
        raise ValueError("Output overlaps raw session")
    if args.stage in {"all", "prepare"}:
        from prepare import prepare

        prepare(config, output)
    if args.stage in {"all", "eda"}:
        from reporting import eda

        eda(config, output)
    if args.stage in {"all", "train"}:
        from training import train

        train(config, output)
    if args.stage in {"all", "evaluate"}:
        from training import evaluate

        evaluate(config, output)
    if args.stage in {"all", "report"}:
        from reporting import report

        report(config, output)


if __name__ == "__main__":
    main()
