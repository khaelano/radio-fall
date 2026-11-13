"""Check a converted frames table against the CSV files of its source archive.

The converter derives ``frames.parquet`` from the raw journal and events. This
tool proves the derivation by comparing it with the independently written
``csi.csv``, ``radio_timing.csv`` and ``gateway_timing.jsonl`` of every
attempt and receiver. It never writes anything.

Example:
    uv run python tools/processing/check_storage_equivalence.py \\
        data/raw/sessions/<id>.zip data/interim/frames/<id>/frames.parquet

The first argument may also be a session directory, which is how a freshly
collected session is checked before the collector stops writing CSV sidecars.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Self

import numpy as np
import pyarrow.parquet as pq

HEADER_COLUMNS = (
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "ant",
    "rx_state",
)


def _frame_index(table: Any) -> tuple[dict[tuple, int], dict[str, np.ndarray]]:
    """Index frames by identity and expose the columns used for comparison."""
    names = [
        "receiver_id",
        "run_id",
        "tx_boot_id",
        "rx_boot_id",
        "sequence",
    ]
    keys = zip(*(table.column(n).to_pylist() for n in names), strict=True)
    index = {key: row for row, key in enumerate(keys)}
    if len(index) != table.num_rows:
        raise ValueError("frame identities are not unique")
    columns: dict[str, np.ndarray] = {}
    columns["transmitter_mac"] = np.array(
        table.column("transmitter_mac").to_pylist(), dtype=object
    )
    for name in (
        "capture_time_ns",
        "capture_uncertainty_us",
        "rx_radio_us",
        "tx_enqueue_us",
        "rssi",
        "noise_floor",
        "sig_len",
        *HEADER_COLUMNS,
    ):
        columns[name] = table.column(name).to_numpy(zero_copy_only=False)
    csi = table.column("csi").combine_chunks()
    width = csi.type.byte_width
    columns["csi"] = np.frombuffer(csi.buffers()[1], dtype=np.int8)[
        csi.offset * width : (csi.offset + len(csi)) * width
    ].reshape(len(csi), width)
    return index, columns


def _check_without_gateway(
    bundle: zipfile.ZipFile,
    name: str,
    timing_name: str,
    receiver: str,
    table: Any,
    columns: dict[str, np.ndarray],
    counts: Counter[str],
) -> None:
    """Compare payload and header of files that predate gateway timing.

    Frames are located by receiver, sequence and radio timestamp, because the
    run and boot identities are not recorded next to those CSV files.
    """
    receivers = table.column("receiver_id").to_pylist()
    sequences = table.column("sequence").to_numpy()
    radio = columns["rx_radio_us"]
    wanted = {
        (int(row["id"]), int(row["local_timestamp"])): row
        for row in csv.DictReader(io.StringIO(bundle.read(name).decode()))
    }
    candidates: dict[tuple[int, int], list[int]] = {}
    for at in np.flatnonzero([r == receiver for r in receivers]):
        key = (int(sequences[at]), int(radio[at]))
        if key in wanted:
            candidates.setdefault(key, []).append(int(at))
    for key, row in wanted.items():
        counts["fallback_rows"] += 1
        payload = np.array(json.loads(row["data"]), dtype=np.int8)
        rows = candidates.get(key)
        if not rows:
            counts["fallback_missing_in_frames"] += 1
        elif not any(np.array_equal(payload, columns["csi"][at]) for at in rows):
            counts["fallback_payload_mismatch"] += 1
    del timing_name


class _DirectoryBundle:
    """Present a session directory like an archive with an ``original/`` tree.

    Collector streams may be stored as ``<name>.zst``; they are decoded
    transparently and listed without the suffix.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._files = {
            "original/" + path.relative_to(root).as_posix().removesuffix(".zst"): path
            for path in root.rglob("*")
            if path.is_file()
        }

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def namelist(self) -> list[str]:
        """List member names as an archive would."""
        return sorted(self._files)

    def read(self, name: str) -> bytes:
        """Read one member, decoding Zstandard streams."""
        path = self._files[name]
        data = path.read_bytes()
        if path.suffix == ".zst":
            import zstandard

            return zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)).read()
        return data


def _open_bundle(source: Path) -> Any:
    return _DirectoryBundle(source) if source.is_dir() else zipfile.ZipFile(source)


def check(
    archive: Path, frames: Path, limit: int | None = None, offset: int = 0
) -> dict[str, int]:
    """Compare every CSV row in ``archive`` with ``frames``.

    Args:
        archive: Session archive containing ``original/`` CSV files, or a
            session directory with ``trials/`` CSV files.
        frames: Converted ``frames.parquet``.
        limit: Optional number of receiver files to check, for quick runs.
        offset: Number of receiver files to skip before checking.

    Returns:
        Counters named after each comparison; ``mismatches`` is the total of
        failed comparisons.
    """
    table = pq.read_table(frames)
    index, columns = _frame_index(table)
    counts: Counter[str] = Counter()
    seen: set[int] = set()
    with _open_bundle(archive) as bundle:
        files = sorted(
            n
            for n in bundle.namelist()
            if n.startswith("original/trials/") and n.endswith("/csi.csv")
        )
        for position, name in enumerate(files):
            if position < offset:
                continue
            if limit is not None and position >= offset + limit:
                break
            receiver = name.split("/")[-2]
            base = name.rsplit("/", 1)[0]
            gateway_name = f"{base}/gateway_timing.jsonl"
            timing_name = f"{base}/radio_timing.csv"
            if gateway_name not in bundle.namelist():
                counts["files_without_gateway_timing"] += 1
                _check_without_gateway(
                    bundle, name, timing_name, receiver, table, columns, counts
                )
                continue
            rows = list(csv.DictReader(io.StringIO(bundle.read(name).decode())))
            gateway = [
                json.loads(line)
                for line in bundle.read(gateway_name).decode().splitlines()
                if line.strip()
            ]
            timing = list(
                csv.DictReader(io.StringIO(bundle.read(timing_name).decode()))
            )
            if not len(rows) == len(gateway) == len(timing):
                counts["row_count_mismatch_files"] += 1
                continue
            for row, wire, extra in zip(rows, gateway, timing, strict=True):
                counts["rows"] += 1
                key = (
                    receiver,
                    int(wire["run_id"]),
                    int(wire["transmitter_boot_id"]),
                    int(wire["receiver_boot_id"]),
                    int(wire["sequence"]),
                )
                at = index.get(key)
                if at is None:
                    counts["missing_in_frames"] += 1
                    continue
                seen.add(at)
                payload = np.array(json.loads(row["data"]), dtype=np.int8)
                if not np.array_equal(payload, columns["csi"][at]):
                    counts["payload_mismatch"] += 1
                if any(
                    int(row[name]) != int(columns[name][at])
                    for name in HEADER_COLUMNS
                    if name != "rx_state"
                ) or int(row["rx_state"]) != int(columns["rx_state"][at]):
                    counts["header_mismatch"] += 1
                if row["mac"].lower() != columns["transmitter_mac"][at]:
                    counts["transmitter_mismatch"] += 1
                if (
                    int(row["rssi"]) != columns["rssi"][at]
                    or int(row["noise_floor"]) != columns["noise_floor"][at]
                    or int(row["sig_len"]) != columns["sig_len"][at]
                ):
                    counts["signal_mismatch"] += 1
                if (
                    int(row["local_timestamp"]) != columns["rx_radio_us"][at]
                    or int(extra["tx_enqueue_timestamp_us"] or 0)
                    != columns["tx_enqueue_us"][at]
                ):
                    counts["timestamp_mismatch"] += 1
                if wire["capture_host_monotonic_ns"] != columns["capture_time_ns"][at]:
                    counts["capture_mismatch"] += 1
                expected = wire.get("clock_uncertainty_us")
                actual = columns["capture_uncertainty_us"][at]
                if expected is None:
                    if not np.isnan(actual):
                        counts["uncertainty_mismatch"] += 1
                elif not np.isclose(actual, expected, rtol=1e-6, atol=1e-3):
                    counts["uncertainty_mismatch"] += 1
    counts["frames_total"] = table.num_rows
    counts["frames_outside_attempts"] = table.num_rows - len(seen)
    counts["mismatches"] = sum(
        value
        for name, value in counts.items()
        if name.endswith("_mismatch")
        or name in {"missing_in_frames", "fallback_missing_in_frames"}
    )
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    """Run the check and print the counters as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archive", type=Path)
    parser.add_argument("frames", type=Path)
    parser.add_argument(
        "--limit", type=int, default=None, help="receiver files to check"
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="receiver files to skip first"
    )
    args = parser.parse_args(argv)
    result = check(args.archive, args.frames, args.limit, args.offset)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["mismatches"] or result.get("row_count_mismatch_files") else 0


if __name__ == "__main__":
    sys.exit(main())
