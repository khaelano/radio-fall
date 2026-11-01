"""Versioned, reproducible BLE transport settings shared with firmware."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Sequence

CONFIG_SIZE = 64
SERVICE_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71800"
STATUS_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71801"
DATA_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71802"
CONTROL_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71803"
STATS_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71804"
TIMING_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71805"
FLOW_UUID = "4d71c510-8a51-4a67-aee0-52c01bb71806"


@dataclass(frozen=True)
class BleDeliveryExperiment:
    """Independent pending admission, started-transfer lifetime and wire credits."""

    delivery_deadline_ms: int = 100
    completion_budget_ms: int = 60
    transfer_timeout_ms: int = 150
    progress_timeout_ms: int = 1000
    credit_fragments: int = 8
    progress_every: int = 4
    progress_interval_ms: int = 10

    def __post_init__(self) -> None:
        for name, low, high in (
            ("delivery_deadline_ms", 2, 5000),
            ("completion_budget_ms", 1, 4999),
            ("transfer_timeout_ms", 1, 5000),
            ("progress_timeout_ms", 100, 5000),
            ("credit_fragments", 1, 16),
            ("progress_every", 1, 16),
            ("progress_interval_ms", 1, 50),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")
        if self.completion_budget_ms >= self.delivery_deadline_ms:
            raise ValueError("completion budget must leave a positive admission window")
        if self.transfer_timeout_ms < self.completion_budget_ms:
            raise ValueError("transfer timeout is smaller than completion budget")
        if self.progress_every > self.credit_fragments:
            raise ValueError("progress cadence exceeds credit window")


def flow_token(run_id: int) -> int:
    """Return a run tag; full receipt identities remain run/boot-qualified."""
    return zlib.crc32(struct.pack("!Q", run_id)) or 1


@dataclass(frozen=True)
class BleTimingExperiment:
    """Explicit benchmark-only settings; never inferred from receiver presence."""

    upload_policy: str = "scheduled"
    slot_rounds: int = 1
    batch_records: int = 2
    connection_interval_units: int = 10
    submission_pacing_us: int = 0
    delivery: BleDeliveryExperiment | None = None

    def __post_init__(self) -> None:
        if self.delivery is not None and not isinstance(
            self.delivery, BleDeliveryExperiment
        ):
            raise ValueError("delivery must be a BleDeliveryExperiment")
        if self.upload_policy not in {"scheduled", "continuous"}:
            raise ValueError("unsupported experimental upload policy")
        for name, low, high in (
            ("slot_rounds", 1, 8),
            ("batch_records", 1, 4),
            ("connection_interval_units", 6, 40),
            ("submission_pacing_us", 0, 65535),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")


@dataclass(frozen=True)
class BleTransportConfig:
    """Application transport policy; negotiated radio parameters are separate."""

    schema_version: int = 1
    scheduler: str = "round_robin"
    seed: int = 17
    queue_capacity: int = 32
    maximum_age_ms: int = 250
    outstanding_batches: int = 4
    ack_timeout_ms: int = 50
    maximum_retries: int = 1
    records_per_grant: int = 4
    start_guard_us: int = 1000
    end_guard_us: int = 1000
    bin_hz: int = 50
    delivery_grace_ms: int = 100
    drain_ms: int = 300
    experiment: BleTimingExperiment | None = None

    def __post_init__(self) -> None:
        if self.experiment is not None and not isinstance(
            self.experiment, BleTimingExperiment
        ):
            raise ValueError("experiment must be a BleTimingExperiment")
        if self.schema_version != 1 or self.scheduler not in {"round_robin", "random"}:
            raise ValueError("unsupported BLE configuration version or scheduler")
        limits = {
            "seed": (0, 0xFFFFFFFF),
            "queue_capacity": (1, 64),
            "maximum_age_ms": (1, 5000),
            "outstanding_batches": (1, 4),
            "ack_timeout_ms": (1, 5000),
            "maximum_retries": (0, 4),
            "records_per_grant": (1, 16),
            "start_guard_us": (0, 4000),
            "end_guard_us": (0, 4000),
            "bin_hz": (1, 100),
            "delivery_grace_ms": (0, 5000),
            "drain_ms": (1, 6000),
        }
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in [{low}, {high}]")
        if self.ack_timeout_ms > self.maximum_age_ms:
            raise ValueError("ACK timeout exceeds maximum record age")
        if self.drain_ms < self.maximum_age_ms:
            raise ValueError("drain period must cover maximum record age")
        if self.experiment and self.experiment.delivery:
            d = self.experiment.delivery
            if (
                self.drain_ms
                < d.delivery_deadline_ms
                - d.completion_budget_ms
                + d.transfer_timeout_ms
            ):
                raise ValueError(
                    "drain period must cover pending and transfer lifetime"
                )
            if self.ack_timeout_ms > d.transfer_timeout_ms:
                raise ValueError("ACK timeout exceeds started transfer lifetime")

    @classmethod
    def load(cls, path: Path | None) -> "BleTransportConfig":
        """Load strict JSON settings, or use the collection defaults."""
        if path is None:
            return cls()
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError("unknown BLE transport configuration fields")
        if value.get("experiment") is not None:
            if value["experiment"].get("delivery") is not None:
                value["experiment"]["delivery"] = BleDeliveryExperiment(
                    **value["experiment"]["delivery"]
                )
            value["experiment"] = BleTimingExperiment(**value["experiment"])
        return cls(**value)

    @property
    def fingerprint(self) -> str:
        """Return the stable 16-character policy fingerprint."""
        value = asdict(self)
        if self.experiment is None:
            value.pop("experiment")  # Existing collection fingerprints stay stable.
        elif self.experiment.delivery is None:
            value["experiment"].pop("delivery")  # Preserve CBLC v2 fingerprints too.
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def encode(
        self,
        run_id: int,
        receiver_count: int,
        rate_hz: int,
        *,
        receiver_macs: Sequence[str] | None = None,
    ) -> bytes:
        """Encode the fixed-size CBLC control message in network byte order."""
        if not 0 < run_id <= 0xFFFFFFFFFFFFFFFF or not 1 <= receiver_count <= 4:
            raise ValueError("invalid run identity or receiver count")
        if not 50 <= rate_hz <= 100:
            raise ValueError("BLE sensing rate must be between 50 and 100 Hz")
        delivery = self.experiment.delivery if self.experiment else None
        data = bytearray(80 if delivery else CONFIG_SIZE)
        struct.pack_into(
            "!4sBBBBQIHHHBBHHH",
            data,
            0,
            b"CBLC",
            3 if delivery else 2 if self.experiment else 1,
            int(self.scheduler == "random"),
            receiver_count,
            self.maximum_retries,
            run_id,
            self.seed,
            self.maximum_age_ms,
            self.ack_timeout_ms,
            self.queue_capacity,
            self.outstanding_batches,
            self.records_per_grant,
            self.start_guard_us,
            self.end_guard_us,
            rate_hz,
        )
        data[36:52] = self.fingerprint.encode("ascii")
        if receiver_macs is not None:
            if len(receiver_macs) != receiver_count:
                raise ValueError("receiver order does not match count")
            struct.pack_into("!I", data, 52, inventory_crc(receiver_macs))
        if self.experiment:
            e = self.experiment
            struct.pack_into(
                "!BBHHBB",
                data,
                56,
                e.slot_rounds,
                e.batch_records,
                e.connection_interval_units,
                e.submission_pacing_us,
                int(e.upload_policy == "continuous"),
                0,
            )
        if delivery:
            d = delivery
            struct.pack_into(
                "!HHHHBBHI",
                data,
                64,
                d.delivery_deadline_ms,
                d.completion_budget_ms,
                d.transfer_timeout_ms,
                d.progress_timeout_ms,
                d.credit_fragments,
                d.progress_every,
                d.progress_interval_ms,
                flow_token(run_id),
            )
        return bytes(data)


def inventory_crc(receiver_macs: Sequence[str]) -> int:
    """Bind grant indices to the exact ordered MAC inventory stored on boards."""
    values = [bytes.fromhex(mac.replace(":", "")) for mac in receiver_macs]
    if not 1 <= len(values) <= 4 or any(len(value) != 6 for value in values):
        raise ValueError("invalid receiver MAC inventory")
    return zlib.crc32(b"".join(values))


def grant_owner(
    sequence: int,
    receiver_count: int,
    scheduler: str = "round_robin",
    seed: int = 17,
    *,
    slot_rounds: int = 1,
) -> int:
    """Return a fixed-slot owner; random mode uses the firmware's uint32 mixer.

    The counter-based mixer is deterministic across languages and sequence wrap.
    Rejection sampling avoids modulo bias when three receivers are configured.
    """
    if not 1 <= receiver_count <= 4 or not 0 <= sequence <= 0xFFFFFFFF:
        raise ValueError("invalid sequence or receiver count")
    if type(slot_rounds) is not int or not 1 <= slot_rounds <= 8:
        raise ValueError("invalid upload slot length")
    sequence //= slot_rounds
    if scheduler == "round_robin":
        return sequence % receiver_count
    if scheduler != "random":
        raise ValueError("unknown scheduler")
    value = (sequence ^ seed) & 0xFFFFFFFF
    limit = (1 << 32) - ((1 << 32) % receiver_count)
    while True:
        value = (value + 0x9E3779B9) & 0xFFFFFFFF
        x = value
        x = ((x ^ (x >> 16)) * 0x85EBCA6B) & 0xFFFFFFFF
        x = ((x ^ (x >> 13)) * 0xC2B2AE35) & 0xFFFFFFFF
        x ^= x >> 16
        if x < limit:
            return x % receiver_count
