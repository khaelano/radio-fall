"""Run the self-contained EDA/preprocessing/training/evaluation experiment."""

import argparse
from pathlib import Path

from data_pipeline import prepare, read_json


def main() -> None:
    """Execute requested stages using paths relative to this folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["all", "prepare", "eda", "train", "evaluate", "report"],
        default="all",
    )
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).parent / "config.json"
    )
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).parent / "artifacts" / "pilot_v1"
    )
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    config = read_json(args.config.resolve())
    output = args.output.resolve()
    session = (folder / config["session_path"]).resolve()
    if output.is_relative_to(session) or session.is_relative_to(output):
        raise ValueError("Output must be separate from the raw session tree")
    if args.stage in ["all", "prepare"]:
        prepare(config, folder, output)
    if args.stage in ["all", "eda", "report"]:
        from reporting import eda

        eda(config, output)
    if args.stage in ["all", "train"]:
        from modeling import train

        train(config, output)
    if args.stage in ["all", "evaluate"]:
        from modeling import evaluate

        evaluate(config, output)
    if args.stage in ["all", "report"]:
        from reporting import report

        report(config, output)


if __name__ == "__main__":
    main()
