"""Native-record ingress and generation-safe live prediction state."""

from __future__ import annotations

import json
import math
import time

from ..radio.acquisition.native import require_native
from .model import ModelBundle, EnsembleWorker


class DetectorEngine:
    """Keep native preprocessing and isolated inference off the acquisition callback."""

    def __init__(
        self,
        bundle: ModelBundle,
        *,
        workers: int = 2,
        threads: int = 2,
        hop_ms: int = 250,
        grace_ms: int = 900,
        kernel: str = "auto",
        scorer=None,
    ):
        self.bundle = bundle
        self.native = require_native().CnnPreprocessor(
            bundle.mean.ravel().tolist(),
            bundle.scale.ravel().tolist(),
            bundle.metadata["minimum_coverage"],
            workers,
            hop_ms,
            grace_ms,
            4096,
            kernel,
            bundle.metadata["representation"],
        )
        self.scorer = scorer or EnsembleWorker(bundle, threads)
        self.receiver_indices = {
            mac.lower(): i
            for i, mac in enumerate(bundle.metadata["radio"]["receiver_macs"])
        }
        self.failure = ""
        self.last = None
        self.last_quality = None
        self.invalid_end_ns = 0
        self.grace_ms = grace_ms
        self.hop_ms = hop_ms
        self.maximum_result_age_ns = (grace_ms + max(1000, hop_ms * 3)) * 1_000_000

    def start(self) -> None:
        """Load the scorer before radio startup."""
        self.scorer.start()

    def interrupt(self, reason: str) -> None:
        """Invalidate old windows immediately on link loss or clock replacement."""
        self.native.reset()
        self.last = None
        self.last_quality = None
        self.invalid_end_ns = 0

    def on_record(self, record, arrival_ns: int) -> None:
        """Enqueue an Arc-backed native record without decoding arrays in Python."""
        if self.failure:
            return
        try:
            meta = self.bundle.metadata["radio"]
            if (
                record.mac.lower() != meta["transmitter_mac"].lower()
                or record.profile_fingerprint != meta["profile_fingerprint"]
            ):
                return
            if (
                record.capture_host_monotonic_ns is None
                or record.capture_clock_uncertainty_us is None
                or not math.isfinite(record.capture_clock_uncertainty_us)
                or record.capture_clock_uncertainty_us < 0
            ):
                raise ValueError("Capture clock is unavailable")
            if record.capture_host_monotonic_ns > arrival_ns + math.ceil(
                record.capture_clock_uncertainty_us * 1000
            ):
                raise ValueError(
                    "Capture clock lies after receipt beyond its uncertainty"
                )
            self.native.submit(
                record._native,
                self.receiver_indices[record.receiver_mac.lower()],
                record.capture_host_monotonic_ns,
                record.run_id,
                record.transmitter_boot_id,
                record.receiver_boot_id,
            )
        except Exception as exc:
            self.failure = f"Preprocessing input failed: {exc}"
            self.interrupt(self.failure)

    def tick(
        self, *, radio_ready: bool = True, now_ns: int | None = None
    ) -> list[dict]:
        """Return completed/loggable events and suppress invalid, stale or old-run scores."""
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        events = []
        stats = json.loads(self.native.stats_json())
        frame = self.native.poll()
        if frame is not None:
            metadata = json.loads(frame.metadata_json())
            self.last_quality = metadata
            if (
                metadata["generation"] == stats["generation"]
                and radio_ready
                and not self.failure
            ):
                if metadata["valid"]:
                    self.scorer.submit(frame.tensor_bytes(), metadata)
                else:
                    self.last = None
                    self.invalid_end_ns = metadata["end_ns"]
                    events.append(
                        dict(kind="insufficient_data", **metadata, probability=None)
                    )
        result = self.scorer.poll()
        if result is not None:
            if result["kind"] == "error":
                self.failure = result["reason"]
                self.last = None
                events.append(result)
            elif (
                result.get("generation") == stats["generation"]
                and radio_ready
                and not self.failure
                and result["end_ns"] >= self.invalid_end_ns
                and now_ns - result["end_ns"] <= self.maximum_result_age_ns
            ):
                result["candidate"] = (
                    result["probability"] >= self.bundle.metadata["threshold"]
                )
                result["emitted_ns"] = now_ns
                self.last = result
                events.append(result)
        if (
            not radio_ready
            or self.failure
            or (
                self.last is not None
                and (
                    self.last["generation"] != stats["generation"]
                    or now_ns - self.last["end_ns"] > self.maximum_result_age_ns
                )
            )
        ):
            self.last = None
        return events

    def status(self) -> dict:
        """Expose inference freshness, coverage and native queue diagnostics."""
        stats = json.loads(self.native.stats_json())
        if self.last and (
            self.last["generation"] != stats["generation"]
            or time.monotonic_ns() - self.last["end_ns"] > self.maximum_result_age_ns
        ):
            self.last = None
        return dict(
            prediction=self.last,
            quality=self.last_quality,
            failure=self.failure,
            native=stats,
            skipped_inference=self.scorer.dropped,
        )

    def close(self) -> None:
        """Stop scorer and native workers on both normal and failed startup."""
        try:
            self.scorer.close()
        finally:
            self.native.close()
