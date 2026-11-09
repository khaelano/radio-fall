"""Compare the previous batched NumPy Hampel filter with native modes on real CSI.

Run: uv run --no-sync python tools/benchmark_amplitude_preprocessing.py SESSION_DIR
"""
import argparse
import json
from pathlib import Path
from time import perf_counter
import warnings

import numpy as np

from fall_detection.analysis.amplitude import hampel_subcarriers, normalize_subcarriers
from fall_detection.analysis.phase_signals import phase_signal_from_packets
from fall_detection.analysis.session_parquet import load_parquet_session

HAMPEL_WINDOW_SECONDS = 0.1
HAMPEL_MIN_PERIODS = 5
HAMPEL_THRESHOLD = 5.0
HAMPEL_BATCH_ROWS = 256

# Preserved notebook implementation for independent parity and timing checks.
def numpy_hampel_subcarriers(amplitude, times):
    """Replace isolated outliers in each subcarrier using a centered time window."""
    if np.any(~np.isfinite(times)) or np.any(np.diff(times) < 0):
        raise ValueError("Capture times must be finite and sorted.")
    filtered = amplitude.copy()
    replaced = np.zeros(amplitude.shape, dtype=bool)
    half = HAMPEL_WINDOW_SECONDS / 2
    starts = np.searchsorted(times, times - half, side="left")
    stops = np.searchsorted(times, times + half, side="right")
    sizes = stops - starts

    for size in np.unique(sizes):
        if size < HAMPEL_MIN_PERIODS:
            continue
        rows = np.flatnonzero(sizes == size)
        for offset in range(0, len(rows), HAMPEL_BATCH_ROWS):
            batch = rows[offset:offset + HAMPEL_BATCH_ROWS]
            indices = starts[batch, None] + np.arange(size)
            windows = amplitude[indices]
            enough = np.isfinite(windows).sum(axis=1) >= HAMPEL_MIN_PERIODS
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
                median = np.nanmedian(windows, axis=1)
                mad = np.nanmedian(np.abs(windows - median[:, None, :]), axis=1)
            center = amplitude[batch]
            outlier = (
                enough & np.isfinite(center) & np.isfinite(median) & (mad > 0)
                & (np.abs(center - median) > HAMPEL_THRESHOLD * 1.4826 * mad)
            )
            row_idx, tone_idx = np.nonzero(outlier)
            filtered[batch[row_idx], tone_idx] = median[row_idx, tone_idx]
            replaced[batch[row_idx], tone_idx] = True
    return filtered, replaced



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--parquet-dir", type=Path)
    parser.add_argument("--recordings", type=int, default=4)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.recordings < 1 or args.repeats < 1:
        parser.error("recordings and repeats must be positive")
    parquet_dir = args.parquet_dir or Path("data/interim/parquet") / args.session_dir.name
    session = load_parquet_session(args.session_dir, parquet_dir)
    attempts = session.attempts
    recordings = (
        attempts.loc[attempts.status.eq("accepted") & attempts.inclusion.ne("exclude")]
        .explode("receiver_ids").dropna(subset=["receiver_ids"])
        .sort_values(["trial_ordinal", "attempt", "receiver_ids"])
        .head(args.recordings)
    )
    modes = {
        "numpy": numpy_hampel_subcarriers,
        "rust_scalar": lambda a, t: hampel_subcarriers(a, t, parallel=False, simd=False),
        "rust_simd": lambda a, t: hampel_subcarriers(a, t, parallel=False),
        "rust_parallel_simd": hampel_subcarriers,
    }
    observations = []
    for row in recordings.itertuples(index=False):
        started = perf_counter()
        packets = session.read_packets(filters=[
            ("attempt_key", "==", row.attempt_key),
            ("receiver_id", "==", row.receiver_ids),
        ])
        loaded = perf_counter()
        signal = phase_signal_from_packets(packets)
        decoded = perf_counter()
        metadata = packets.loc[packets.is_sensing]
        if signal.skipped_layout_rows or len(metadata) != len(signal.time_seconds):
            raise ValueError("Unsupported layout or unaligned metadata")
        amplitude = np.abs(signal.complex_csi)
        valid = (
            np.isfinite(amplitude) & np.isfinite(signal.raw_phase)
            & metadata.driver_valid.fillna(False).to_numpy(dtype=bool)[:, None]
        )
        amplitude[~valid] = np.nan
        values, _, _ = normalize_subcarriers(amplitude)
        normalized = perf_counter()
        expected, expected_mask = numpy_hampel_subcarriers(values, signal.time_seconds)
        timings = {name: [] for name in modes}
        for function in modes.values():
            actual, mask = function(values, signal.time_seconds)
            np.testing.assert_array_equal(actual, expected)
            np.testing.assert_array_equal(mask, expected_mask)
        # Alternate order to reduce systematic warm-up/thermal bias.
        for repeat in range(args.repeats):
            names = list(modes) if repeat % 2 == 0 else list(reversed(modes))
            for name in names:
                start = perf_counter()
                modes[name](values, signal.time_seconds)
                timings[name].append(perf_counter() - start)
        observations.append({
            "attempt_key": row.attempt_key, "receiver": row.receiver_ids,
            "shape": list(values.shape), "read_seconds": loaded - started,
            "decode_seconds": decoded - loaded, "normalize_seconds": normalized - decoded,
            "hampel_median_seconds": {k: float(np.median(v)) for k, v in timings.items()},
            "exact_parity": True,
        })
    print(json.dumps({"repeats": args.repeats, "recordings": observations}, indent=2))


if __name__ == "__main__":
    main()
