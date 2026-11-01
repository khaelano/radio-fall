"""Seeded packet replay; no hardware throughput or loss is inferred here."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import math

import numpy as np


@dataclass(frozen=True)
class Stream:
    """Observed sensing packets for one receiver on the attempt timeline."""

    sequence: np.ndarray
    seconds: np.ndarray
    csi_bytes: np.ndarray


@dataclass
class Pending:
    """A record whose partial transfer can continue in a later grant."""

    index: int
    captured: float
    total_bits: int
    remaining_bits: float
    retries: int = 0


def stable_seed(*parts: object) -> int:
    """Derive a process-independent seed without Python's randomized hash."""
    return int.from_bytes(hashlib.sha256(str(parts).encode()).digest()[:8], "little")


def retain_round(
    sequence: np.ndarray, rate_hz: int, source_hz: int = 100
) -> np.ndarray:
    """Thin the global source grid, preserving original times and sequence IDs.

    An 80 Hz replay retains four of five 100 Hz rounds with 10/20 ms spacing;
    it does not invent uniformly spaced 12.5 ms observations.
    """
    if not 0 < rate_hz <= source_hz:
        raise ValueError("Replay rate must be positive and no higher than source")
    sequence = np.asarray(sequence, dtype=np.int64)
    return sequence * rate_hz // source_hz != (sequence - 1) * rate_hz // source_hz


def wire_bits(csi_bytes: int, config: dict) -> int:
    """Budget existing record/batch metadata plus assumed fragment headers."""
    serialized = int(csi_bytes) + 87 + 2 + 30
    fragments = math.ceil(serialized / config["fragment_payload_bytes"])
    return 8 * (serialized + fragments * config["fragment_header_bytes"])


def simulate(
    streams: list[Stream], condition: dict, config: dict, seed: int, end_seconds: float
) -> dict:
    """Replay scheduled capture losses and a shared, bounded transport service.

    Args:
        streams: Two actual receiver streams; virtual slots create workload only.
        condition: Rate, scheduling, loss and optional service assumptions.
        config: Buffer, source-rate, fragment and guard settings.
        seed: Seed independent of activity label.
        end_seconds: End of replay, including the prediction grace interval.

    Returns:
        Real-stream arrival times/reasons, round schedule and transport counters.

    The selected slot is blind for that retained source round. Upload grants
    use a separate uniform target-rate clock, with a guard. Observed capture
    times retain the thinning jitter. This assumes grants announced ahead of
    time; it is not BLE connection-event emulation.
    """
    if len(streams) != 2 or any(len(s.sequence) == 0 for s in streams):
        raise ValueError("Two nonempty recorded receiver streams are required")
    slots = condition["slots"]
    if slots not in (2, 4):
        raise ValueError("Only two real slots plus zero/two virtual slots supported")
    rate = condition["rate_hz"]
    source_hz = config["source_hz"]
    retain_round(np.array([1]), rate, source_hz)
    all_seq = np.concatenate([s.sequence for s in streams])
    all_t = np.concatenate([s.seconds for s in streams])
    # Fit only an offset for the known source sequence/time grid. Keep each
    # observed packet's own timestamp for enqueue and final model binning.
    offset = float(np.median(all_t - all_seq / source_hz))
    lo, hi = int(all_seq.min()), int(all_seq.max())
    candidates = np.arange(lo, hi + source_hz + 1, dtype=np.int64)
    rounds = candidates[retain_round(candidates, rate, source_hz)]
    times = offset + (rounds * rate // source_hz) / rate
    active = times < end_seconds
    rounds, times = rounds[active], times[active]
    if len(rounds) == 0:
        raise ValueError("No rounds within replay interval")
    rng = np.random.default_rng(stable_seed(seed, "schedule"))
    loss_rng = np.random.default_rng(stable_seed(seed, "capture_loss"))
    retry_rng = np.random.default_rng(stable_seed(seed, "transfer_failure"))
    phase = int(rng.integers(slots))
    if condition["scheduler"] == "round_robin":
        owners = (rounds * rate // source_hz + phase) % slots
    elif condition["scheduler"] == "random":
        owners = rng.integers(slots, size=len(rounds))
    elif condition["scheduler"] == "none":
        owners = np.full(len(rounds), -1)
    else:
        raise ValueError("Unknown scheduler")
    arrivals = [np.full(len(s.sequence), np.inf) for s in streams]
    reasons = [np.full(len(s.sequence), "rate_removed", dtype="U24") for s in streams]
    lookup = []
    for stream in streams:
        if len(np.unique(stream.sequence)) != len(stream.sequence):
            raise ValueError("Duplicate sensing sequences; resolve before replay")
        lookup.append({int(seq): i for i, seq in enumerate(stream.sequence)})
    queues = [deque() for _ in range(slots)]
    burst = np.zeros(slots, dtype=bool)
    counters = [
        dict(
            peak_queue=0,
            overflow=0,
            expired=0,
            retries=0,
            completed=0,
            service_bits=0.0,
        )
        for _ in range(slots)
    ]
    bounded = "service_bps" in condition
    if bounded and (condition["scheduler"] == "none" or condition["service_bps"] <= 0):
        raise ValueError("Bounded service needs a scheduler and positive capacity")
    virtual_size = int(np.median(np.concatenate([s.csi_bytes for s in streams])))

    def mark(slot: int, record: Pending, reason: str) -> None:
        if slot < 2:
            reasons[slot][record.index] = reason

    def expire(slot: int, now: float) -> None:
        queue = queues[slot]
        while queue and now - queue[0].captured >= config["maximum_age_seconds"]:
            mark(slot, queue.popleft(), "expired")
            counters[slot]["expired"] += 1

    for j, (sequence, start, owner) in enumerate(zip(rounds, times, owners)):
        stop = min(times[j + 1] if j + 1 < len(times) else end_seconds, end_seconds)
        for slot in range(slots):
            if burst[slot]:
                burst[slot] = loss_rng.random() >= condition.get("burst_exit", 1.0)
            else:
                burst[slot] = loss_rng.random() < condition.get("burst_enter", 0.0)
            independent = loss_rng.random() < condition.get("independent_loss", 0.0)
            index = lookup[slot].get(int(sequence)) if slot < 2 else -1
            if index is None:
                continue  # Preserve source loss; never synthesize real CSI.
            captured = float(streams[slot].seconds[index]) if slot < 2 else float(start)
            if captured >= end_seconds:
                continue
            reason = (
                "scheduled"
                if slot == owner
                else (
                    "radio_burst"
                    if burst[slot]
                    else "radio_independent"
                    if independent
                    else "pending"
                )
            )
            if slot < 2:
                reasons[slot][index] = reason
            if reason != "pending":
                continue
            if not bounded:
                if slot < 2:
                    arrivals[slot][index] = captured
                    reasons[slot][index] = "delivered"
                continue
            expire(slot, float(start))
            queue = queues[slot]
            if len(queue) >= config["queue_capacity"]:
                mark(slot, queue.popleft(), "overflow")
                counters[slot]["overflow"] += 1
            size = streams[slot].csi_bytes[index] if slot < 2 else virtual_size
            bits = wire_bits(size, config)
            queue.append(Pending(index, captured, bits, float(bits)))
            counters[slot]["peak_queue"] = max(counters[slot]["peak_queue"], len(queue))
        if not bounded:
            continue
        # Only the granted receiver gets application service. Unused service
        # does not accumulate credit and cannot spill into another grant.
        clock = float(start + config["sensing_guard_seconds"])
        while queues[owner] and clock < stop:
            expire(int(owner), clock)
            if not queues[owner]:
                break
            record = queues[owner][0]
            clock = max(clock, record.captured)
            deadline = min(stop, record.captured + config["maximum_age_seconds"])
            budget = max(0.0, deadline - clock) * condition["service_bps"]
            used = min(record.remaining_bits, budget)
            record.remaining_bits -= used
            counters[owner]["service_bits"] += used
            clock += used / condition["service_bps"]
            if record.remaining_bits > 1e-5:
                if clock >= record.captured + config["maximum_age_seconds"] - 1e-9:
                    mark(int(owner), queues[owner].popleft(), "expired")
                    counters[owner]["expired"] += 1
                    continue
                break
            if retry_rng.random() < condition.get("transfer_failure", 0.0):
                if record.retries < condition.get("maximum_retries", 0):
                    record.retries += 1
                    counters[owner]["retries"] += 1
                    record.remaining_bits = float(record.total_bits)
                    continue
                mark(int(owner), queues[owner].popleft(), "retry_limit")
                continue
            queues[owner].popleft()
            if owner < 2:
                arrivals[owner][record.index] = clock
                reasons[owner][record.index] = "delivered"
            counters[owner]["completed"] += 1
    return dict(
        arrivals=arrivals,
        reasons=reasons,
        sequence=rounds,
        times=times,
        owners=owners,
        counters=counters,
        pending=[len(q) for q in queues],
    )


def make_features(
    streams: list[Stream],
    phases: list[np.ndarray],
    arrivals: list[np.ndarray],
    action_start: float,
    config: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bin observed phases causally with a fixed delivery grace per capture bin.

    Packet calibration is already packet-local. No temporal interpolation,
    future fill, or temporal filtering is used. Each bin is finalized at its
    end plus the configured grace. Age uses only packets captured by that bin
    end and delivered by its finalization deadline.
    """
    hz = config["bin_hz"]
    bins = round(config["window_seconds"] * hz)
    tones = phases[0].shape[1]
    values = np.full((4, bins, tones), np.nan, dtype=np.float32)
    counts = np.zeros((2, bins), dtype=np.float32)
    age = np.ones((2, bins), dtype=np.float32)
    ends = action_start + (np.arange(bins) + 1) / hz
    grace = config["prediction_grace_seconds"]
    for rx, (stream, phase, arrival) in enumerate(zip(streams, phases, arrivals)):
        relative = stream.seconds - action_start
        indices = np.floor(relative * hz + 1e-7).astype(int)
        inside = (indices >= 0) & (indices < bins)
        timely = np.zeros(len(indices), dtype=bool)
        timely[inside] = arrival[inside] <= ends[indices[inside]] + grace
        selected = np.flatnonzero(inside & timely)
        for b in np.unique(indices[selected]):
            rows = selected[indices[selected] == b]
            counts[rx, b] = len(rows)
            finite = np.isfinite(phase[rows])
            n = finite.sum(axis=0)
            for component, function in enumerate((np.sin, np.cos)):
                total = np.where(finite, function(phase[rows]), 0).sum(axis=0)
                values[2 * rx + component, b] = np.divide(
                    total, n, out=np.full(tones, np.nan), where=n > 0
                )
        for b, end in enumerate(ends):
            eligible = (stream.seconds < end) & (arrival <= end + grace)
            if eligible.any():
                age[rx, b] = min(
                    1.0,
                    max(0.0, end - stream.seconds[eligible].max())
                    / config["maximum_age_seconds"],
                )
    return values, counts, age
