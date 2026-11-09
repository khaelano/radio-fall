"""Compare Python and Rust CSI preparation using an immutable gateway journal.

Run with ``uv run python tools/benchmark_radio_pipeline.py <envelopes.bin>``.
This measures decode, CSV preparation and phase views, excluding USB, live
session acceptance, storage and GUI rendering. It is not a radio-rate test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import struct
import time

from fall_detection.radio.acquisition.gateway_protocol import GatewayBatch
from fall_detection.radio.acquisition.native import gateway_batch, require_native
from fall_detection.radio.acquisition.protocol import format_csi_record


def main() -> None:
    """Measure warmed, alternating implementations on identical input bytes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--envelopes", type=int, default=256)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--copies", type=int, default=4)
    args = parser.parse_args()
    if min(args.envelopes, args.repeats, args.copies) < 1:
        parser.error("counts must be positive")
    core = require_native()
    inputs = []
    with args.journal.open("rb") as stream:
        for _ in range(args.envelopes):
            header = stream.read(12)
            if not header:
                break
            if len(header) != 12:
                raise ValueError("truncated journal header")
            _, length = struct.unpack("!QI", header)
            if length > 1400:
                raise ValueError("oversized journal envelope")
            data = stream.read(length)
            GatewayBatch.decode(data)
            inputs.append(data)
    if not inputs:
        raise ValueError("empty journal")

    def prepare(data: bytes, native: bool) -> int:
        batch = (
            gateway_batch(core.decode_envelope(data), encoded=data)
            if native
            else GatewayBatch.decode(data)
        )
        records = batch.decoded_packet.records
        for item in records:
            record = item.record
            format_csi_record(record)
            _ = record.channel_estimate_block
        return len(records)

    for data in inputs:
        prepare(data, False)
        prepare(data, True)
    timings = {"python": [], "rust": []}
    count = 0
    for repeat in range(args.repeats):
        for native in [repeat % 2 == 0, repeat % 2 != 0]:
            start = time.perf_counter()
            count = sum(prepare(data, native) for data in inputs * args.copies)
            timings["rust" if native else "python"].append(time.perf_counter() - start)
    result = {
        name: {
            "seconds": values,
            "median_us_per_record": statistics.median(values) * 1e6 / count,
        }
        for name, values in timings.items()
    }
    print(
        json.dumps(
            {
                "source": str(args.journal),
                "envelopes": len(inputs),
                "records_per_repeat": count,
                "kernel": core.simd_kernel(),
                "results": result,
                "speedup": statistics.median(timings["python"])
                / statistics.median(timings["rust"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
