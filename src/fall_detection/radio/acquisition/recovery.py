"""Recover link epochs without reopening a failed recording run."""

from __future__ import annotations

import json
import struct
import time
from typing import Any

from ..espnow_config import CONTROL, RESPONSE
from .serial_framing import (
    TYPE_RELAY_RECOVER,
    SerialFrameStreamDecoder,
    encode_serial_frame,
)


class RecoveryUnavailable(RuntimeError):
    """The connected device cannot perform the requested recovery."""


def can_recover(message: str) -> bool:
    """Distinguish interrupted links from configuration/storage/data failures."""
    text = message.lower()
    # End the damaged run; a new clock/buffer epoch may recover a transient
    # consumer stall. This never accepts the stale bytes or repairs its trial.
    if text in {
        "gateway ingestion failed: gateway usb receive buffer age exceeded",
        "gateway ingestion failed: native usb processing buffer age exceeded",
        "gateway ingestion failed: native usb processing deadline exceeded",
        "gateway usb receive failed: gateway usb receive buffer age exceeded",
        "gateway usb receive failed: gateway usb read process: gateway usb read process buffer age exceeded",
    }:
        return True
    # A reboot can truncate a frame before its new boot status arrives. The
    # damaged run still fails; recovery creates a separate, validated epoch.
    if (
        "gateway usb framing error" in text
        or text == "transmitter reference framing error"
    ):
        return True
    if any(
        word in text
        for word in (
            "overflow",
            "buffer age",
            "queue age",
            "identity/profile",
            "firmware/identity",
            "permission",
            "no space",
            "read-only",
            "malformed",
            "crc",
            "journal",
            "shutdown",
            "lacks",
            "mismatch",
        )
    ):
        return False
    return any(
        word in text
        for word in (
            "restarted; start a new run",
            "wireless transmitter reference failed:",
            "wireless reference handshake timed out",
            "transmitter command timed out",
            "transmitter reference discovery timed out",
            "gateway discovery timed out",
            "transmitter reference lost:",
            "could not open port",
            "no such file",
            "input/output error",
            "device disconnected",
            "device reports readiness",
            "gateway usb disconnected",
            "gateway usb receive failed:",
        )
    )


def recover_gateway(manager: Any) -> None:
    """Restart an idle UART gateway epoch after the failed worker has closed USB.

    Raises:
        RecoveryUnavailable: Identity or firmware cannot support recovery.
        OSError: The USB gateway is absent or inaccessible.
        TimeoutError: The gateway did not answer discovery or control.
    """
    if manager.transmitter_link != "espnow_uart":
        return
    import serial

    decoder = SerialFrameStreamDecoder()
    with serial.Serial(
        manager.gateway_port, 921600, timeout=0.1, write_timeout=0.5, exclusive=True
    ) as link:

        def request(kind: int, payload: bytes, response: int) -> bytes:
            frame = encode_serial_frame(kind, payload)
            if link.write(frame) != len(frame):
                raise OSError("short recovery USB write")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                for item in decoder.feed(link.read(max(1, min(4096, link.in_waiting)))):
                    if item.type == response:
                        return item.payload
            raise TimeoutError("gateway recovery command timed out")

        status = json.loads(request(5, b"", 6))
        if (status.get("role"), status.get("target"), status.get("mac")) != (
            "gateway",
            "esp32c6",
            manager.inventory.gateway.mac,
        ):
            raise RecoveryUnavailable("gateway recovery identity mismatch")
        if status.get("relay_recovery_version") != 1:
            raise RecoveryUnavailable("automatic recovery requires updated C6 firmware")
        if (
            not status.get("configured")
            and not status.get("relay_fault")
            and manager.grid is None
        ):
            return  # Discovery retries need no new epoch when no run began.
        if status.get("configured"):
            stopped = request(
                CONTROL, struct.pack("!4sQ", b"CGSP", int(status["run_id"])), RESPONSE
            )
            if stopped != b"ok":
                raise RecoveryUnavailable("gateway refused to end the interrupted run")
        # An idle gateway waiting for an absent peer need not reboot repeatedly.
        if not status.get("relay_ready") and not status.get("relay_fault"):
            return
        if request(TYPE_RELAY_RECOVER, b"CRRC", RESPONSE) != b"ok":
            raise RecoveryUnavailable("gateway refused recovery")
