"""Run PyTorch sequence training on CPU or NVIDIA CUDA."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fall_detection.analysis.pytorch_cpu_training import (
    CpuPilotConfig,
    run_cpu_pilot,
    run_cpu_training,
)


def main() -> None:
    """Run a saved pilot or full split in a fresh process."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tinygrad-run", type=Path)
    parser.add_argument("--frame", type=Path)
    parser.add_argument("--normalizer", type=Path)
    parser.add_argument("--duration", type=int, default=2, choices=(2, 4, 6))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--cpu-threads", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "data/processed/amplitude_sequence_v2",
    )
    args = parser.parse_args()
    if args.cpu_threads < 1 or args.batch_size < 1:
        parser.error("--cpu-threads and --batch-size must be positive")
    pilot = args.tinygrad_run is not None
    if pilot == (args.frame is not None or args.normalizer is not None):
        parser.error("Provide --tinygrad-run or both --frame and --normalizer")
    if (args.frame is None) != (args.normalizer is None):
        parser.error("--frame and --normalizer must be supplied together")
    if hasattr(os, "sched_setaffinity"):
        allowed = sorted(os.sched_getaffinity(0))
        if len(allowed) < args.cpu_threads:
            parser.error("Fewer CPUs are available than requested threads")
        os.sched_setaffinity(0, set(allowed[: args.cpu_threads]))
    config = replace(
        CpuPilotConfig(),
        duration=args.duration,
        epochs=args.epochs,
        patience=args.patience,
        cpu_threads=args.cpu_threads,
        device=args.device,
        batch_size=args.batch_size,
    )
    if pilot:
        result = run_cpu_pilot(
            args.tinygrad_run, args.output, config, data_root=args.data_root
        )
    else:
        result = run_cpu_training(
            args.frame, args.normalizer, args.output, config, data_root=args.data_root
        )
    print(
        "device",
        result["runtime"]["device"],
        "GPU",
        result["runtime"]["gpu_name"],
        flush=True,
    )
    for kind, model in result["models"].items():
        print(
            kind,
            "training_seconds",
            round(model["training_seconds"], 3),
            "peak_rss_bytes",
            model["peak_rss_bytes"],
            "peak_cuda_allocated_bytes",
            model["peak_cuda_allocated_bytes"],
            flush=True,
        )


if __name__ == "__main__":
    main()
