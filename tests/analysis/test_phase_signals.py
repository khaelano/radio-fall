"""Check phase decoding, detrending, and event-clock alignment on synthetic CSI."""

import csv
import json

import numpy as np
import pytest

from fall_detection.analysis.phase_signals import load_phase_signal
from fall_detection.radio.preprocessing.phase import HE20_COMPACT_SLOT_INDICES


def _write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def phase_capture(tmp_path):
    root = tmp_path / "session"
    receiver = root / "trials/001_fall/attempt_01/receivers/rx-1"
    receiver.mkdir(parents=True)
    (root / "session.json").write_text(
        json.dumps(
            {
                "artifact_schema_version": 2,
                "environment": {
                    "nominal_rate_hz": 100,
                    "radio_inventory": {
                        "transmitter": {"mac": "aa:bb:cc:dd:ee:ff"},
                    },
                },
            }
        )
    )
    (receiver.parent.parent / "attempt.json").write_text(
        json.dumps(
            {
                "trial_ordinal": 1,
                "started_monotonic_ns": 1_000_000_000,
                "ended_monotonic_ns": 1_400_000_000,
            }
        )
    )
    slots = np.asarray(HE20_COMPACT_SLOT_INDICES)
    csi_rows, timing_rows = [], []
    for index in range(4):
        phase = 0.02 * slots + 0.3
        if index == 1:
            phase += 0.4 * np.sin(slots / 15)
        values = 40 * np.exp(1j * phase)
        values[slots == 20] = 1
        flat = (
            np.column_stack((np.rint(values.imag), np.rint(values.real)))
            .ravel()
            .astype(int)
            .tolist()
        )
        csi_rows.append(
            {
                "type": "CSI_DATA",
                "id": index,
                "mac": "aa:bb:cc:dd:ee:ff" if index < 3 else "foreign",
                "sig_mode": 4,
                "mcs": 0,
                "bandwidth": 0,
                "stbc": 0,
                "first_word": 0,
                "local_timestamp": 100_000 + index * 100_000,
                "len": len(flat),
                "data": json.dumps(flat),
            }
        )
        timing_rows.append(
            {
                "sequence": index,
                "rx_radio_timestamp_us": 100_000 + index * 100_000,
                "rx_callback_timestamp_us": 1_105_000 + index * 100_000,
                "host_receive_monotonic_ns": 1_150_000_000 + index * 100_000_000,
            }
        )
    _write_csv(receiver / "csi.csv", csi_rows)
    _write_csv(receiver / "radio_timing.csv", timing_rows)
    sync_rows = []
    for index, host in enumerate([1_000_000, 1_200_000, 1_400_000]):
        sync_rows.append(
            {
                "host_receive_monotonic_ns": (host + 15_000) * 1000,
                "sync_id": index,
                "sensing_sequence": index,
                "receiver_boot_id": 1,
                "tx_t1_us": host,
                "tx_t4_us": host + 2,
                "rx_t2_us": host + 5000,
                "rx_t3_us": host + 5002,
                "rx_radio_t2_us": 0,
                "tx_radio_t4_us": 0,
                "receiver_mac": "11:22:33:44:55:66",
            }
        )
    _write_csv(receiver / "usb_clock_sync.csv", sync_rows)
    return root, receiver


def test_load_phase_signal_preserves_physical_axis_and_canonical_calibration(
    phase_capture,
):
    root, _ = phase_capture
    signal = load_phase_signal(root, "001/01", "rx-1")
    assert signal.raw_phase.shape == signal.calibrated_phase.shape == (3, 245)
    np.testing.assert_array_equal(signal.subcarriers, np.arange(-122, 123))
    assert np.isnan(
        signal.raw_phase[:, np.isin(signal.subcarriers, [-1, 0, 1, 20])]
    ).all()
    assert signal.removed_slope[0] == pytest.approx(0.02, abs=0.001)
    for index in range(3):
        valid = np.isfinite(signal.raw_phase[index])
        unwrapped = np.unwrap(signal.raw_phase[index, valid])
        residual = (
            unwrapped
            - signal.removed_slope[index] * signal.subcarriers[valid]
            - signal.removed_offset[index]
        )
        expected = np.angle(np.exp(1j * residual))
        np.testing.assert_allclose(
            expected, signal.calibrated_phase[index, valid], atol=1e-12
        )
    assert np.nanstd(signal.calibrated_phase[1]) > np.nanstd(signal.calibrated_phase[0])
    np.testing.assert_allclose(signal.time_seconds, [0.1, 0.2, 0.3], atol=1e-12)
    assert "USB affine fit" in signal.time_source
    assert signal.skipped_layout_rows == 0


def test_load_phase_signal_labels_host_receive_fallback(phase_capture):
    root, receiver = phase_capture
    (receiver / "usb_clock_sync.csv").unlink()
    signal = load_phase_signal(root, "001/01", "rx-1")
    np.testing.assert_allclose(signal.time_seconds, [0.15, 0.25, 0.35])
    assert "buffering included" in signal.time_source
    assert signal.sync_uncertainty_us is None


def test_load_phase_signal_does_not_mix_receiver_boots(phase_capture):
    root, receiver = phase_capture
    path = receiver / "usb_clock_sync.csv"
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    rows[-1]["receiver_boot_id"] = 2
    _write_csv(path, rows)
    signal = load_phase_signal(root, "001/01", "rx-1")
    assert "host receive" in signal.time_source


def test_load_phase_signal_rejects_misaligned_timing(phase_capture):
    root, receiver = phase_capture
    path = receiver / "radio_timing.csv"
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["sequence"] = 100
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="align by sequence"):
        load_phase_signal(root, "001/01", "rx-1")


def test_load_phase_signal_rejects_bad_payload_length(phase_capture):
    root, receiver = phase_capture
    path = receiver / "csi.csv"
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["len"] = 12
    _write_csv(path, rows)
    with pytest.raises(ValueError, match="payload length"):
        load_phase_signal(root, "001/01", "rx-1")


def test_load_phase_signal_retains_only_supported_packets(phase_capture):
    root, receiver = phase_capture
    path = receiver / "csi.csv"
    with path.open() as stream:
        rows = list(csv.DictReader(stream))
    rows[0].update(data="[0,20,0,20,0,20]", len=6)
    _write_csv(path, rows)
    signal = load_phase_signal(root, "001/01", "rx-1")
    assert signal.skipped_layout_rows == 1
    np.testing.assert_allclose(signal.time_seconds, [0.2, 0.3])


def test_load_phase_signal_requires_existing_receiver(phase_capture):
    root, _ = phase_capture
    with pytest.raises(FileNotFoundError):
        load_phase_signal(root, "001/01", "rx-2")


def test_ble_phase_uses_capture_clock_sidecar_and_sorts_derived_view(phase_capture):
    root, receiver = phase_capture
    values = [1_100_000_000, 1_050_000_000, 1_200_000_000, 1_300_000_000]
    rows = [
        dict(
            schema_version=1,
            sequence=i,
            rx_radio_timestamp_us=100000 + i * 100000,
            run_id="123",
            transmitter_boot_id=11,
            capture_host_monotonic_ns=value,
            clock_uncertainty_us=100,
        )
        for i, value in enumerate(values)
    ]
    (receiver / "ble_timing.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    signal = load_phase_signal(root, "001/01", "rx-1")
    np.testing.assert_allclose(signal.time_seconds, [0.05, 0.1, 0.2])
    assert "BLE" in signal.time_source and signal.sync_uncertainty_us == 100
    # The view is sorted; immutable source rows retain their original order.
    assert (
        json.loads((receiver / "ble_timing.jsonl").read_text().splitlines()[0])[
            "sequence"
        ]
        == 0
    )


def test_ble_analysis_refuses_arrival_time_fallback_when_sidecar_missing(phase_capture):
    root, _ = phase_capture
    manifest = json.loads((root / "session.json").read_text())
    manifest["environment"]["transport"] = "ble"
    (root / "session.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="capture-time sidecar"):
        load_phase_signal(root, "001/01", "rx-1")
