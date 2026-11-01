"""Bounded BLE fragment reassembly and epoch-qualified application ACKs."""

from __future__ import annotations

import json
import struct
import time
import zlib
from dataclasses import dataclass

from .wire import decode_csi_packet

ENVELOPE = struct.Struct("!4sBBHQIIIHH")
FRAGMENT = struct.Struct("!4sIHH")
ACK = struct.Struct("!4sQIII")
MAX_BATCH = 1400
MAX_ENVELOPE = ENVELOPE.size + MAX_BATCH + 4
FLOW_FRAGMENT = struct.Struct("!4sIIIHH")
FLOW_FIELDS = (
    "flow_run_id",
    "flow_tx_boot",
    "flow_rx_boot",
    "flow_token",
    "flow_last_issued",
    "flow_last_acked",
    "flow_inflight_fragments",
    "flow_inflight_bytes",
    "flow_peak_fragments",
    "flow_peak_bytes",
    "flow_receipts",
    "flow_invalid_receipts",
    "flow_admission_drops",
    "flow_transfer_expired",
    "flow_credit_wait_ticks",
    "flow_stall_disconnects",
    "flow_submitted_fragments",
    "flow_submitted_bytes",
    "flow_submission_failures",
    "flow_last_error",
)


def decode_flow_status(data: bytes) -> dict[str, int]:
    """Decode one atomic MTU-247 diagnostic read, with fixed field ordering."""
    if (
        len(data) != 168
        or data[:6] != b"CBFS\x01\x14"
        or struct.unpack_from("!H", data, 6)[0] != len(data)
    ):
        raise ValueError("invalid flow diagnostic snapshot")
    return dict(zip(FLOW_FIELDS, struct.unpack_from("!20Q", data, 8), strict=True))


@dataclass(frozen=True)
class FlowFragment:
    """A transport receipt acknowledges arrival, not application acceptance."""

    token: int
    serial: int
    batch_id: int
    offset: int
    total: int
    payload: bytes

    @classmethod
    def decode(cls, data: bytes, expected_token: int) -> "FlowFragment":
        """Validate the run tag and fragment bounds before returning credit."""
        if len(data) <= FLOW_FRAGMENT.size:
            raise ValueError("truncated flow fragment")
        magic, token, serial, batch, offset, total = FLOW_FRAGMENT.unpack_from(data)
        payload = data[FLOW_FRAGMENT.size :]
        if (
            magic != b"CBL2"
            or token != expected_token
            or not ENVELOPE.size + 4 < total <= MAX_ENVELOPE
            or offset + len(payload) > total
        ):
            raise ValueError("invalid flow fragment scope or bounds")
        return cls(token, serial, batch, offset, total, payload)

    @property
    def classic(self) -> bytes:
        """Keep the existing strict envelope reassembler and CSI encoding."""
        return (
            FRAGMENT.pack(b"CBLF", self.batch_id, self.offset, self.total)
            + self.payload
        )


def progress_receipt(
    run: int, tx_boot: int, rx_boot: int, token: int, serial: int
) -> bytes:
    """Encode an epoch-qualified, cumulative host-arrival receipt."""
    raw = struct.pack("!4sQIIII", b"CBPR", run, tx_boot, rx_boot, token, serial)
    return raw + struct.pack("!I", zlib.crc32(raw))


def decode_timing(data: bytes) -> list[dict[str, int]]:
    """Decode a bounded snapshot of the four most recently built batches.

    Timestamps are receiver-local microseconds. Snapshots sample the ring; they
    are not a complete transfer log and never establish RF completion times.
    """
    if (
        len(data) != 232
        or data[:6] != b"CBTM\x01\x04"
        or struct.unpack_from("!H", data, 6)[0] != len(data)
    ):
        raise ValueError("invalid BLE timing snapshot")
    names = (
        "batch_id",
        "flags",
        "capture_us",
        "built_us",
        "first_submit_us",
        "last_submit_us",
        "ack_us",
        "expired_us",
    )
    return [
        dict(zip(names, values))
        for offset in range(8, len(data), 56)
        if (values := struct.unpack_from("!II6Q", data, offset))[1]
    ]


@dataclass(frozen=True)
class BleBatch:
    """A complete transport envelope, validated before ingestion."""

    run_id: int
    transmitter_boot_id: int
    receiver_boot_id: int
    batch_id: int
    payload: bytes

    def encode(self) -> bytes:
        """Encode a complete CBLE envelope with end-to-end CRC32."""
        if not 1 <= len(self.payload) <= MAX_BATCH:
            raise ValueError("invalid batch length")
        data = (
            ENVELOPE.pack(
                b"CBLE",
                1,
                0,
                ENVELOPE.size,
                self.run_id,
                self.transmitter_boot_id,
                self.receiver_boot_id,
                self.batch_id,
                len(self.payload),
                0,
            )
            + self.payload
        )
        return data + struct.pack("!I", zlib.crc32(data))

    @classmethod
    def decode(cls, data: bytes) -> "BleBatch":
        """Validate all lengths, CRC, and nested CSIB identities."""
        if not ENVELOPE.size + 4 < len(data) <= MAX_ENVELOPE:
            raise ValueError("invalid BLE envelope size")
        magic, version, flags, size, run, tx, rx, batch, length, reserved = (
            ENVELOPE.unpack_from(data)
        )
        if (magic, version, flags, size, reserved) != (b"CBLE", 1, 0, ENVELOPE.size, 0):
            raise ValueError("unsupported BLE envelope")
        if len(data) != size + length + 4 or not run:
            raise ValueError("invalid BLE payload length or run")
        if zlib.crc32(data[:-4]) != struct.unpack_from("!I", data, len(data) - 4)[0]:
            raise ValueError("BLE envelope CRC mismatch")
        payload = data[size:-4]
        packet = decode_csi_packet(payload)
        if packet.boot_id != rx or packet.batch_sequence != batch:
            raise ValueError("BLE and CSIB identities disagree")
        return cls(run, tx, rx, batch, payload)

    def acknowledgement(self) -> bytes:
        """Acknowledge application acceptance, not controller submission."""
        raw = ACK.pack(
            b"CBAK",
            self.run_id,
            self.transmitter_boot_id,
            self.receiver_boot_id,
            self.batch_id,
        )
        return raw + struct.pack("!I", zlib.crc32(raw))

    def fragments(self, mtu: int = 247) -> list[bytes]:
        """Split an envelope into ATT notifications of at most MTU minus three."""
        data = self.encode()
        chunk = mtu - 3 - FRAGMENT.size
        if chunk < 1:
            raise ValueError("ATT MTU cannot carry a BLE fragment")
        return [
            FRAGMENT.pack(b"CBLF", self.batch_id, offset, len(data))
            + data[offset : offset + chunk]
            for offset in range(0, len(data), chunk)
        ]


@dataclass
class _Partial:
    started: float
    data: bytearray
    received: bytearray
    count: int = 0


class BleReassembler:
    """Cap concurrent partial envelopes, reject conflicts, and expire fragments."""

    def __init__(
        self, capacity: int = 4, timeout: float = 0.3, *, replace_oldest: bool = False
    ) -> None:
        self.capacity = capacity
        self.timeout = timeout
        self.partials: dict[int, _Partial] = {}
        self.expired = 0
        self.evicted = 0
        self.stale_fragments = 0
        self.replace_oldest = replace_oldest
        self.last_completed_started: float | None = None

    def clear(self) -> None:
        """Forget fragments across a connection or epoch boundary."""
        self.partials.clear()
        self.last_completed_started = None

    def feed(self, fragment: bytes, now: float | None = None) -> BleBatch | None:
        """Consume one notification; return only a complete validated batch."""
        now = time.monotonic() if now is None else now
        for identity, partial in list(self.partials.items()):
            if now - partial.started >= self.timeout:
                del self.partials[identity]
                self.expired += 1
        if len(fragment) <= FRAGMENT.size:
            raise ValueError("empty or truncated BLE fragment")
        magic, identity, offset, total = FRAGMENT.unpack_from(fragment)
        payload = fragment[FRAGMENT.size :]
        if (
            magic != b"CBLF"
            or not ENVELOPE.size + 4 < total <= MAX_ENVELOPE
            or offset + len(payload) > total
        ):
            raise ValueError("invalid BLE fragment bounds")
        partial = self.partials.get(identity)
        if partial is None:
            if len(self.partials) >= self.capacity:
                if not self.replace_oldest:
                    raise ValueError("BLE reassembly capacity exceeded")
                older = [
                    key
                    for key in self.partials
                    if 0 < ((identity - key) & 0xFFFFFFFF) < 0x80000000
                ]
                if not older:
                    self.stale_fragments += 1
                    return None
                oldest = min(older, key=lambda key: self.partials[key].started)
                del self.partials[oldest]
                self.evicted += 1
            partial = _Partial(now, bytearray(total), bytearray(total))
            self.partials[identity] = partial
        if len(partial.data) != total:
            del self.partials[identity]
            raise ValueError("conflicting BLE fragment length")
        for i, value in enumerate(payload, start=offset):
            if partial.received[i] and partial.data[i] != value:
                del self.partials[identity]
                raise ValueError("conflicting BLE fragment bytes")
            if not partial.received[i]:
                partial.data[i] = value
                partial.received[i] = 1
                partial.count += 1
        if partial.count != total:
            return None
        del self.partials[identity]
        batch = BleBatch.decode(bytes(partial.data))
        self.last_completed_started = partial.started
        if batch.batch_id != identity:
            raise ValueError("fragment and envelope identities disagree")
        return batch


STATUS_FIELDS = (
    "mtu",
    "tx_phy",
    "rx_phy",
    "interval_units",
    "latency",
    "supervision_units",
    "queued",
    "oldest_age_us",
    "peak",
    "captured",
    "acknowledged",
    "evicted",
    "expired",
    "rejected",
    "epoch_dropped",
    "retries",
    "send_errors",
    "sensing_missing",
    "sensing_reordered",
    "callbacks",
    "connection_changes",
    "last_submit_us",
    "last_complete_us",
    "tx_octets",
    "rx_octets",
    "free_heap",
    "minimum_free_heap",
)


def decode_status(identity: bytes, diagnostics: bytes) -> dict:
    """Merge bounded GATT identity and versioned counter-vector attributes."""
    status = json.loads(identity)
    if not isinstance(status, dict):
        raise ValueError("invalid BLE identity status")
    vector = struct.Struct("!4sBBH" + "Q" * len(STATUS_FIELDS))
    if len(diagnostics) != vector.size:
        raise ValueError("invalid BLE diagnostic status length")
    magic, version, count, length, *values = vector.unpack(diagnostics)
    if (magic, version, count, length) != (b"CBSS", 1, len(STATUS_FIELDS), vector.size):
        raise ValueError("unsupported BLE diagnostic status")
    return dict(status, **dict(zip(STATUS_FIELDS, values, strict=True)))
