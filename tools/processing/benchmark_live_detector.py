"""Read-only saved-array/model parity and native CNN preprocessing measurements."""

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from fall_detection.radio.acquisition.native import require_native
from fall_detection.detection.model import ModelBundle, load_ensemble, score_tensor
from fall_detection.detection.replay import load_attempt


def python_inputs(rows: list, start: int, bundle: ModelBundle) -> np.ndarray:
    """Cache canonical packet features for a Python/NumPy binning comparison."""
    packets = [[] for _ in range(4)]
    for record, rx, capture in rows:
        phase = record.phase_bytes()
        if (
            phase is None
            or record.sig_mode != 4
            or record.mcs != 0
            or record.bandwidth != 0
        ):
            continue
        indices, amplitude, raw, calibrated = phase
        indices = np.asarray(indices)
        order = np.argsort(indices)
        order = order[(np.abs(indices[order]) <= 122) & (np.abs(indices[order]) > 1)]
        a, r, c = [
            np.frombuffer(v, dtype="=f8")[order] for v in [amplitude, raw, calibrated]
        ]
        values = np.where(
            np.isfinite(r) & np.isfinite(c) & (record.rx_state == 0),
            np.log1p(a),
            np.nan,
        )
        packets[rx].append((capture, values))
    return packets


def python_bin(packets: list, start: int, bundle: ModelBundle) -> np.ndarray:
    """Use the pilot's NumPy reduction and float32 scaling conventions."""
    raw = np.full((1, 4, 100, 242), np.nan, dtype="float32")
    for rx, values in enumerate(packets):
        times = np.array([t for t, _ in values], dtype=np.int64)
        matrix = np.array([v for _, v in values])
        indices = np.floor(((times - start) / 1e9) * 25).astype(int)
        selected = (indices >= 0) & (indices < 100)
        indices, matrix = indices[selected], matrix[selected]
        finite = np.isfinite(matrix)
        total = np.zeros((100, 242), dtype="float64")
        count = np.zeros_like(total)
        np.add.at(total, indices, np.where(finite, matrix, 0))
        np.add.at(count, indices, finite)
        raw[0, rx] = np.divide(
            total, count, out=np.full_like(total, np.nan), where=count > 0
        ).astype("float32")
    finite = np.isfinite(raw)
    return np.concatenate(
        [np.where(finite, (raw - bundle.mean) / bundle.scale, 0), finite], axis=1
    ).astype("float32")


def main() -> None:
    """Verify three real attempts at all trained offsets and benchmark cached kernels."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=Path("data/models/four_rx_v1"))
    parser.add_argument(
        "--experiment",
        type=Path,
        required=True,
        help="Experiment artifacts containing manifest.json, trials.csv, and predictions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/experiments/detector/parity-benchmark.json"),
    )
    parser.add_argument("--repetitions", type=int, default=15)
    args = parser.parse_args()
    bundle = ModelBundle.load(args.model)
    manifest = json.loads((args.experiment / "manifest.json").read_text())
    table = pd.read_csv(args.experiment / "trials.csv")
    raw = np.load(args.experiment / "amplitude.npy", mmap_mode="r")
    quality = pd.read_csv(args.experiment / "quality.csv")
    prediction = pd.read_csv(args.experiment / "test_predictions.csv")
    picked = [
        table.index[table.split.eq(split)][0]
        for split in ["train", "validation", "test"]
    ]
    if table.attempt_id.eq("192/01").any():
        picked.append(table.index[table.attempt_id.eq("192/01")][0])
    core = require_native()
    processors = {
        (kernel, workers): core.CnnPreprocessor(
            bundle.mean.ravel().tolist(),
            bundle.scale.ravel().tolist(),
            bundle.metadata["minimum_coverage"],
            workers,
            kernel=kernel,
        )
        for kernel, workers in [("scalar", 1), ("auto", 1), ("auto", 2)]
    }
    parity = []
    models = load_ensemble(bundle)
    try:
        for index in picked:
            row = table.iloc[index]
            early, early_start = load_attempt(
                bundle, Path(manifest["raw_session"]), row.attempt_id, -0.5
            )
            late, _ = load_attempt(
                bundle, Path(manifest["raw_session"]), row.attempt_id, 0.5
            )
            merged = {(rx, t, r.sequence): (r, rx, t) for r, rx, t in [*early, *late]}
            rows = list(merged.values())
            for oi, offset in enumerate(manifest["config"]["offsets_seconds"]):
                start = early_start + round((offset + 0.5) * 1e9)
                frame = processors[("auto", 2)].build(rows, start)
                array = np.frombuffer(frame.raw_bytes(), dtype="=f4").reshape(
                    4, 100, 242
                )
                np.testing.assert_allclose(
                    array, raw[index, oi], rtol=0, atol=1e-6, equal_nan=True
                )
                expected = np.concatenate(
                    [
                        np.where(
                            np.isfinite(raw[index, oi][None]),
                            (raw[index, oi][None] - bundle.mean) / bundle.scale,
                            0,
                        ),
                        np.isfinite(raw[index, oi][None]),
                    ],
                    axis=1,
                ).astype("float32")
                actual = np.frombuffer(frame.tensor_bytes(), dtype="=f4").reshape(
                    1, 8, 100, 242
                )
                np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-5)
                metadata = json.loads(frame.metadata_json())
                expected_q = (
                    quality.loc[
                        quality.attempt_id.eq(row.attempt_id)
                        & quality.offset_seconds.eq(offset)
                        & quality.receiver.isin(bundle.metadata["receivers"])
                    ]
                    .set_index("receiver")
                    .reindex(bundle.metadata["receivers"])
                )
                np.testing.assert_allclose(
                    metadata["phase_change_coverage"],
                    expected_q.phase_change_coverage,
                    atol=1e-12,
                )
                probability, _ = score_tensor(models, frame.tensor_bytes())
                expected_probability, _ = score_tensor(models, expected.tobytes())
                assert abs(probability - expected_probability) < 1e-6
                saved = prediction.loc[
                    prediction.scheme.eq(bundle.metadata["scheme"])
                    & prediction.attempt_id.eq(row.attempt_id)
                    & prediction.offset_seconds.eq(offset)
                ]
                if not saved.empty:
                    assert (
                        abs(probability - float(saved.cnn_probability.iloc[0])) < 1e-6
                    )
                parity.append(
                    dict(
                        attempt_id=row.attempt_id,
                        offset_seconds=offset,
                        max_tensor_error=float(np.max(np.abs(actual - expected))),
                        probability=probability,
                    )
                )
            print(f"Verified {row.attempt_id}: five offsets", flush=True)
        packets = python_inputs(rows, start, bundle)
        expected = python_bin(packets, start, bundle)
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-5)
        benchmark = {}
        for (kernel, workers), processor in processors.items():
            wall, native = [], []
            for _ in range(args.repetitions):
                began = time.perf_counter()
                result = processor.build(rows, start)
                wall.append((time.perf_counter() - began) * 1000)
                native.append(json.loads(result.metadata_json())["preprocessing_ms"])
            benchmark[f"{kernel}_{workers}_workers"] = dict(
                replay_call_median_ms=statistics.median(wall),
                native_window_median_ms=statistics.median(native),
                native_window_max_ms=max(native),
            )
        python_times = []
        for _ in range(args.repetitions):
            began = time.perf_counter()
            python_bin(packets, start, bundle)
            python_times.append((time.perf_counter() - began) * 1000)
        benchmark["python_cached_binning_normalization"] = dict(
            median_ms=statistics.median(python_times)
        )
        output = dict(
            parity=parity,
            benchmark=benchmark,
            repetitions=args.repetitions,
            kernel=core.simd_kernel(),
            scope="Read-only recorded windows. Native window timings exclude one-time per-packet feature preparation; replay calls include it. Python timing uses cached packet log amplitudes. No live-radio or detector-accuracy qualification.",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
        print(json.dumps(benchmark, indent=2), flush=True)
    finally:
        for processor in processors.values():
            processor.close()


if __name__ == "__main__":
    main()
