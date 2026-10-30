from __future__ import annotations

import json
from pathlib import Path

import pytest

from fall_detection.collection.capture import TrialCapture
from fall_detection.radio.acquisition.clock_sync import (
    ClockSyncEstimate,
    ClockSyncSample,
)
from fall_detection.radio.acquisition.protocol import CSI_HEADER, CsiRecord


def record(receiver_mac: str = "AA:BB:CC:DD:EE:FF") -> CsiRecord:
    return CsiRecord(
        sequence=7,
        mac="1a:00:00:00:00:00",
        rssi=-42,
        noise_floor=-96,
        timestamp_us=123_456,
        csi=(complex(3, 4), complex(-2, 1)),
        receiver_mac=receiver_mac,
        transport_sequence=9,
        tx_timestamp_us=120_000,
        rx_callback_timestamp_us=123_500,
    )


def clock_estimate() -> ClockSyncEstimate:
    return ClockSyncEstimate(
        receiver_boot_id=1,
        reference_transmitter_us=2_000_000,
        receiver_minus_transmitter_us=10.0,
        drift_ppm=2.5,
        uncertainty_us=15.0,
        sample_count=3,
        minimum_round_trip_us=900,
    )


def test_trial_capture_writes_receiver_split_schema_two(tmp_path: Path):
    capture = TrialCapture(
        tmp_path / "attempt_01",
        {"trial_ordinal": 1, "activity_label": "walk"},
        receiver_ids={"aa:bb:cc:dd:ee:ff": "rx-1"},
    )

    capture.write_radio(record(), host_receive_monotonic_ns=10)
    capture.write_clock_sync(
        ClockSyncSample(
            sync_id=1,
            sensing_sequence=7,
            receiver_boot_id=1,
            tx_t1_us=1_000,
            rx_t2_us=2_000,
            rx_t3_us=2_100,
            tx_t4_us=1_200,
            rx_radio_t2_us=2_000,
            tx_radio_t4_us=1_200,
            receiver_mac="aa:bb:cc:dd:ee:ff",
        ),
        clock_estimate(),
        host_receive_monotonic_ns=11,
    )
    metadata = capture.finish("accepted", ended_monotonic_ns=12)

    attempt = tmp_path / "attempt_01"
    assert metadata["artifact_schema_version"] == 2
    assert metadata["status"] == "accepted"
    assert not (attempt / "csi.csv").exists()
    assert not (attempt / "clock_sync.csv").exists()

    receiver = attempt / "receivers" / "rx-1"
    csi_lines = (receiver / "csi.csv").read_text(encoding="utf-8").splitlines()
    timing_lines = (receiver / "radio_timing.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    clock_lines = (receiver / "usb_clock_sync.csv").read_text(
        encoding="utf-8"
    ).splitlines()
    assert csi_lines[0] == CSI_HEADER
    assert csi_lines[1].startswith("CSI_DATA,7,1a:00:00:00:00:00")
    assert timing_lines[1].split(",")[0] == "7"
    assert timing_lines[1].split(",")[-1] == "10"
    assert clock_lines[1].split(",")[0] == "11"

    manifest = json.loads((attempt / "attempt.json").read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == 2
    assert manifest["status"] == "accepted"
    assert manifest["ended_monotonic_ns"] == 12


def test_trial_capture_ignores_unknown_receivers(tmp_path: Path):
    capture = TrialCapture(
        tmp_path / "attempt_01",
        {},
        receiver_ids={"aa:bb:cc:dd:ee:ff": "rx-1"},
    )

    capture.write_radio(record("11:22:33:44:55:66"), host_receive_monotonic_ns=1)
    capture.finish("accepted")

    csi = tmp_path / "attempt_01" / "receivers" / "rx-1" / "csi.csv"
    assert csi.read_text(encoding="utf-8").splitlines() == [CSI_HEADER]


def test_trial_capture_requires_a_receiver_inventory(tmp_path: Path):
    with pytest.raises(ValueError, match="receiver binding"):
        TrialCapture(tmp_path / "attempt_01", {}, receiver_ids={})
