"""Inspect recorded BLE bytes and timing without changing raw journals."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from ..acquisition.ble_journal import iter_envelopes
from ..acquisition.wire import decode_csi_packet
from ..preprocessing.phase import DEFAULT_PHASE_AMPLITUDE_FLOOR, phase_slot_mask


def analyze_ble_quality(run_dir: Path) -> dict[str, Any]:
    """Verify envelopes, authoritative timing, and raw subcarrier statistics.

    Args:
        run_dir: Directory containing one BLE manifest and immutable journals.

    Returns:
        Integrity and signal summaries. A benchmark's mapped capture-time
        interval defines its sample population; otherwise the whole journal is
        inspected. These checks do not establish motion sensitivity or accuracy.
    """
    records, rounds = {}, {}
    start = end = None
    for line in (run_dir / "events.jsonl").open(encoding="utf-8"):
        event = json.loads(line)
        if event["kind"] == "measurement_started":
            start = event["at_ns"]
        elif event["kind"] == "measurement_finished":
            end = event["at_ns"]
        elif event["kind"] == "round" and not event.get("skipped_rounds"):
            rounds[event["transmitter_boot_id"], event["sequence"]] = event[
                "tx_enqueue_us"
            ]
        elif event["kind"] == "record":
            key = (
                event["transmitter_boot_id"],
                event["receiver_boot_id"],
                event["receiver_mac"],
                event["sequence"],
            )
            records[key] = event
    selected = {
        key: event
        for key, event in records.items()
        if event.get("capture_host_ns") is not None
        and (start is None or start <= event["capture_host_ns"])
        and (end is None or event["capture_host_ns"] < end)
    }
    inconsistent = sum(
        rounds.get((event["transmitter_boot_id"], event["sequence"]))
        != event["tx_enqueue_us"]
        for event in selected.values()
    )
    seen, hashes = set(), set()
    rssi, noise, snr, uncertainty = [], [], [], []
    layouts: Counter[str] = Counter()
    states: Counter[str] = Counter()
    envelopes = raw_records = first_invalid = eligible = usable = edges = (
        unsupported
    ) = 0
    for _, batch in iter_envelopes(run_dir / "envelopes.bin"):
        envelopes += 1
        packet = decode_csi_packet(batch.payload)
        raw_records += len(packet.records)
        for item in packet.records:
            record = item.record
            key = (
                batch.transmitter_boot_id,
                batch.receiver_boot_id,
                item.receiver_mac,
                record.sequence,
            )
            if key not in selected or key in seen:
                continue
            seen.add(key)
            raw = np.asarray(record.raw_csi, dtype=np.complex64)
            hashes.add(hashlib.sha256(raw.tobytes()).digest())
            rssi.append(record.rssi)
            noise.append(record.noise_floor)
            snr.append(record.rssi - record.noise_floor)
            u = selected[key].get("clock_uncertainty_us")
            if u is not None:
                uncertainty.append(u)
            layouts[
                f"format={record.sig_mode},bytes={record.csi_length},pairs={len(raw)}"
            ] += 1
            states[str(record.rx_state)] += 1
            first_invalid += int(record.first_word_invalid)
            mask = phase_slot_mask(
                sig_mode=record.sig_mode,
                bandwidth=record.bandwidth,
                stbc=record.stbc,
                pair_count=len(raw),
                first_word_invalid=record.first_word_invalid,
            )
            if len(mask) != len(raw):
                unsupported += 1
                continue
            active = raw[np.asarray(mask, dtype=bool)]
            eligible += len(active)
            usable += int(
                np.count_nonzero(
                    np.isfinite(active.real)
                    & np.isfinite(active.imag)
                    & (np.abs(active) >= DEFAULT_PHASE_AMPLITUDE_FLOOR)
                )
            )
            edges += int(np.count_nonzero((active.real <= -128) | (active.real >= 127)))
            edges += int(np.count_nonzero((active.imag <= -128) | (active.imag >= 127)))

    def percentiles(values: list) -> dict[str, float]:
        return (
            {str(p): float(np.percentile(values, p)) for p in (5, 50, 95)}
            if values
            else {}
        )

    return dict(
        scope="benchmark capture-time interval"
        if start is not None and end is not None
        else "entire journal",
        envelopes_crc_verified=envelopes,
        envelope_crc_errors=0,
        journal_raw_records=raw_records,
        measurement_unique_records=len(seen),
        measurement_record_events=len(selected),
        measurement_metadata_round_mismatches=inconsistent,
        measurement_records_missing_from_raw_journal=len(set(selected) - seen),
        layouts=dict(layouts),
        rx_state_counts=dict(states),
        first_word_invalid_records=first_invalid,
        unsupported_layout_records=unsupported,
        eligible_phase_slots=eligible,
        usable_phase_fraction_of_eligible=usable / eligible if eligible else None,
        phase_amplitude_floor=DEFAULT_PHASE_AMPLITUDE_FLOOR,
        iq_encoding_limit_fraction=edges / (2 * eligible) if eligible else None,
        distinct_raw_csi_contents=len(hashes),
        rssi_dbm=percentiles(rssi),
        driver_noise_floor_dbm=percentiles(noise),
        driver_estimated_snr_db=percentiles(snr),
        clock_fit_uncertainty_us=percentiles(uncertainty),
        limitations=[
            "CRC errors stop inspection; zero is reported only after the complete journal validates.",
            "IQ encoding limits are not a calibrated RF ADC clipping measurement.",
            "Different CSI byte contents do not by themselves prove motion sensitivity.",
            "Timing uses transmitter enqueue time, not an exact over-air timestamp.",
        ],
    )
