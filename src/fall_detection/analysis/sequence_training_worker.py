"""Run GPU jobs in a systemd cgroup so an oversized graph cannot exhaust RAM."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from time import sleep
import uuid

MEMORY_LIMIT = 4_000_000_000


def memory_cgroup() -> Path:
    """Locate this process's unified cgroup, failing closed on unsupported hosts."""
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            return Path("/sys/fs/cgroup") / line[3:].lstrip("/")
    raise RuntimeError("A cgroup v2 memory controller is required for GPU jobs")


def verify_memory_limit(maximum: int) -> Path:
    """Require an enforced kernel limit before importing or executing a model."""
    cgroup = memory_cgroup()
    value = (cgroup / "memory.max").read_text().strip()
    if value == "max" or int(value) > maximum:
        raise RuntimeError("Refusing GPU work without the requested hard memory limit")
    if (cgroup / "memory.swap.max").read_text().strip() != "0":
        raise RuntimeError("Refusing GPU work without the no-swap limit")
    return cgroup


def run_worker(
    run_dir: Path,
    action: str,
    *,
    kind: str | None = None,
    duration: int | None = None,
    config: dict | None = None,
    memory_bytes: int = MEMORY_LIMIT,
    timeout_seconds: int = 7200,
) -> dict | list:
    """Execute one isolated smoke/training job and stream its saved log.

    A worker limit failure terminates the job and raises in the notebook. There
    is no uncapped fallback. Keyboard interruption stops the complete scope.
    """
    if action not in (
        "probe",
        "smoke",
        "train",
        "predict",
        "profile",
        "loading",
        "compare",
    ):
        raise ValueError("Unknown GPU worker action")
    if memory_bytes < 64 * 1024**2 or memory_bytes > MEMORY_LIMIT:
        raise ValueError("Worker memory must be between 64 MiB and 4 GB")
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    if available < 2 * memory_bytes:
        raise RuntimeError(
            "Insufficient free RAM for the guarded worker; close other workloads first"
        )
    job = (
        run_dir
        / "jobs"
        / f"{action}-{kind or 'all'}-{duration or 0}-{uuid.uuid4().hex[:8]}"
    )
    job.mkdir(parents=True)
    request = {
        "run_dir": str(run_dir.resolve()),
        "action": action,
        "kind": kind,
        "duration": duration,
        "config": config,
        "memory_bytes": memory_bytes,
    }
    request_path = job / "request.json"
    request_path.write_text(json.dumps(request, indent=2))
    unit = f"radio-tinygrad-{uuid.uuid4().hex}"
    command = [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        f"--unit={unit}",
        f"--property=MemoryMax={memory_bytes}",
        "--property=MemorySwapMax=0",
        "--property=OOMPolicy=kill",
        "--property=CPUQuota=400%",
        f"--property=RuntimeMaxSec={timeout_seconds}s",
        sys.executable,
        "-u",
        "-m",
        __name__,
        str(request_path),
    ]
    environment = dict(
        os.environ,
        DEV="CL",
        POLARS_MAX_THREADS="4",
        OPENBLAS_NUM_THREADS="4",
        OMP_NUM_THREADS="4",
        RUSTICL_ENABLE=os.environ.get("RUSTICL_ENABLE", "radeonsi"),
    )
    environment["PYTHONPATH"] = (
        str(Path(__file__).resolve().parents[2])
        + os.pathsep
        + environment.get("PYTHONPATH", "")
    )
    log_path = job / "worker.log"
    with log_path.open("w") as log, log_path.open() as reader:
        process = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, env=environment
        )
        try:
            while process.poll() is None:
                text = reader.read()
                if text:
                    print(text, end="", flush=True)
                sleep(1)
            print(reader.read(), end="", flush=True)
        except BaseException:
            subprocess.run(
                ["systemctl", "--user", "stop", f"{unit}.scope"],
                check=False,
                capture_output=True,
            )
            process.wait(timeout=30)
            raise
    if process.returncode != 0:
        details = {
            "status": "failed",
            "exit_code": process.returncode,
            "memory_limit_bytes": memory_bytes,
            "log": str(log_path),
        }
        (job / "status.json").write_text(json.dumps(details, indent=2))
        raise RuntimeError(
            f"Guarded GPU job failed (exit {process.returncode}); log: {log_path}. "
            "The worker has no permission to exceed its memory limit."
        )
    return json.loads((job / "response.json").read_text())


def main() -> None:
    """Verify containment, then execute the requested job inside its scope."""
    request_path = Path(sys.argv[1])
    request = json.loads(request_path.read_text())
    cgroup = verify_memory_limit(request["memory_bytes"])
    sys.setrecursionlimit(10000)
    from .tinygrad_training import (
        TrainingConfig,
        opencl_preflight,
        smoke_models,
        train_run,
        write_json,
    )

    runtime = opencl_preflight()
    runtime.update(memory_limit_bytes=request["memory_bytes"], cpu_quota_percent=400)
    root = Path(request["run_dir"])
    if request["action"] == "probe":
        result = runtime
    elif request["action"] == "smoke":
        result = smoke_models(features=1960, steps=576, batch_size=1, hidden=64)
        write_json(root / "smoke.json", result)
    elif request["action"] == "compare":
        from .sequence_training_profile import compare_forward

        result = compare_forward(root, request["kind"], request["duration"])
    elif request["action"] == "loading":
        from .sequence_training_profile import measure_loading

        result = measure_loading(root, request["duration"])
    elif request["action"] == "profile":
        from .sequence_training_profile import profile_run

        result = profile_run(
            root,
            request["kind"],
            request["duration"],
            TrainingConfig(**request["config"]),
            runtime,
        )
        result["worker_memory_peak_bytes"] = int((cgroup / "memory.peak").read_text())
        write_json(
            root
            / "profile"
            / f"{request['duration']}s"
            / request["kind"]
            / "metrics.json",
            result,
        )
    elif request["action"] == "predict":
        import numpy as np
        import polars as pl
        from tinygrad import Tensor
        from .tinygrad_training import load_checkpoint, ModelPredictor
        from .sequence_training_data import LABELS, SequenceDataset, SegmentStore

        folder = root / f"{request['duration']}s" / request["kind"]
        model, normalizer, metadata = load_checkpoint(folder)
        sample = (
            pl.read_parquet(root / "window_split.parquet")
            .filter(
                (pl.col("duration") == request["duration"])
                & (pl.col("split") == "test")
            )
            .head(1)
        )
        dataset = SequenceDataset(sample, normalizer, SegmentStore())
        x, rows = next(dataset.batches(1))
        probability = float(ModelPredictor(model)(Tensor(x)).sigmoid().numpy()[0])
        saved = pl.read_parquet(folder / "test_predictions.parquet").filter(
            pl.col("window_id") == rows[0]["window_id"]
        )["probability"][0]
        np.testing.assert_allclose(probability, saved, atol=1e-6)
        result = {
            "actual": LABELS[rows[0]["target"]],
            "predicted": LABELS[int(probability >= metadata["threshold"])],
            "fall_probability": probability,
            "checkpoint": str(folder),
        }
    else:
        import polars as pl
        from .sequence_training_data import Normalizer, SequenceDataset, SegmentStore

        duration = request["duration"]
        frame = pl.read_parquet(root / "window_split.parquet").filter(
            pl.col("duration") == duration
        )
        normalizer = Normalizer.load(root / f"normalizer-{duration}s.npz")
        store = SegmentStore()
        # Establish and validate feature coordinates before writing the checkpoint contract.
        store.read(frame["path"][0])
        datasets = {
            split: SequenceDataset(
                frame.filter(pl.col("split") == split), normalizer, store
            )
            for split in ("train", "validation", "test")
        }
        result = train_run(
            request["kind"],
            duration,
            datasets,
            root / f"{duration}s" / request["kind"],
            TrainingConfig(**request["config"]),
            json.loads((root / "manifest.json").read_text())["provenance"],
            runtime,
            json.loads((root / "preparation_seconds.json").read_text())[str(duration)],
        )
        result["worker_memory_peak_bytes"] = int((cgroup / "memory.peak").read_text())
        write_json(root / f"{duration}s" / request["kind"] / "metrics.json", result)
    write_json(
        request_path.parent / "resources.json",
        {
            "memory_limit_bytes": request["memory_bytes"],
            "memory_peak_bytes": int((cgroup / "memory.peak").read_text()),
            "memory_events": (cgroup / "memory.events").read_text(),
            "cpu_quota_percent": 400,
        },
    )
    write_json(request_path.parent / "response.json", result)
    write_json(request_path.parent / "status.json", {"status": "complete"})


if __name__ == "__main__":
    main()
