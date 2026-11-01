"""Run the transport replay, EDA, preprocessing, training and evaluation."""

import argparse
from pathlib import Path

from support import FOLDER, read_json


def main() -> None:
    """Execute stages with explicit output paths; never overwrite raw sessions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=["all", "prepare", "eda", "train", "evaluate", "report"],
        default="all",
    )
    parser.add_argument("--config", type=Path, default=FOLDER / "config.json")
    parser.add_argument(
        "--output", type=Path, default=FOLDER / "artifacts" / "replay_v1"
    )
    parser.add_argument(
        "--results", type=Path, default=FOLDER / "results" / "replay_v1"
    )
    args = parser.parse_args()
    config, output = read_json(args.config.resolve()), args.output.resolve()
    session = (FOLDER / config["session_path"]).resolve()
    raw = FOLDER.parents[1] / "data" / "raw"
    for target in (output, args.results.resolve()):
        if (
            target.is_relative_to(raw)
            or raw.is_relative_to(target)
            or session.is_relative_to(target)
        ):
            raise ValueError(
                "Output/results must be separate from raw data and its parents"
            )
    if args.stage in ("all", "prepare"):
        from prepare import prepare

        prepare(config, output)
    if args.stage in ("all", "eda"):
        from reporting import eda

        eda(config, output)
    if args.stage in ("all", "train"):
        from experiment_models import train

        train(config, output)
    if args.stage in ("all", "evaluate"):
        from experiment_models import evaluate

        evaluate(config, output)
    if args.stage in ("all", "report"):
        from reporting import report

        report(config, output, args.results.resolve())


if __name__ == "__main__":
    main()
