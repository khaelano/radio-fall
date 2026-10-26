import pytest

from fall_detection.radio.acquisition.clock_sync import (
    MAGIC,
    SAMPLE,
    SAMPLE_SIZE,
    VERSION,
    ClockSyncError,
    ClockSyncEstimator,
    ClockSyncSample,
    decode_clock_sync_sample,
)


def sample(
    midpoint_us: int = 1_000_000,
    offset_us: float = 5_000.0,
    *,
    sync_id: int = 1,
    boot_id: int = 7,
) -> ClockSyncSample:
    tx_t1_us = midpoint_us - 500
    tx_t4_us = midpoint_us + 500
    rx_t2_us = round(tx_t1_us + 300 + offset_us)
    rx_t3_us = rx_t2_us + 400
    return ClockSyncSample(
        sync_id=sync_id,
        sensing_sequence=42 + sync_id,
        receiver_boot_id=boot_id,
        tx_t1_us=tx_t1_us,
        rx_t2_us=rx_t2_us,
        rx_t3_us=rx_t3_us,
        tx_t4_us=tx_t4_us,
        rx_radio_t2_us=1234,
        tx_radio_t4_us=5678,
        receiver_mac="24:6f:28:aa:bb:cc",
    )


def encode(value: ClockSyncSample) -> bytes:
    return SAMPLE.pack(
        MAGIC,
        VERSION,
        0,
        SAMPLE_SIZE,
        value.sync_id,
        value.sensing_sequence,
        value.receiver_boot_id,
        0,
        value.tx_t1_us,
        value.rx_t2_us,
        value.rx_t3_us,
        value.tx_t4_us,
        value.rx_radio_t2_us,
        value.tx_radio_t4_us,
        bytes.fromhex(value.receiver_mac.replace(":", "")),
        0,
    )


def test_clock_sync_sample_round_trip_and_ntp_metrics():
    decoded = decode_clock_sync_sample(encode(sample()))

    assert decoded.round_trip_us == 600
    assert decoded.receiver_minus_transmitter_us == 5_000
    assert decoded.transmitter_midpoint_us == 1_000_000


def test_clock_sync_decoder_rejects_impossible_turnaround():
    value = sample()
    malformed = SAMPLE.pack(
        MAGIC,
        VERSION,
        0,
        SAMPLE_SIZE,
        value.sync_id,
        value.sensing_sequence,
        value.receiver_boot_id,
        0,
        value.tx_t1_us,
        value.rx_t2_us,
        value.rx_t2_us + 2_000,
        value.tx_t4_us,
        value.rx_radio_t2_us,
        value.tx_radio_t4_us,
        bytes.fromhex(value.receiver_mac.replace(":", "")),
        0,
    )

    with pytest.raises(ClockSyncError, match="turnaround"):
        decode_clock_sync_sample(malformed)


def test_clock_sync_estimator_fits_offset_and_drift():
    estimator = ClockSyncEstimator()
    for index, midpoint in enumerate((1_000_000, 11_000_000, 21_000_000)):
        estimator.add(
            sample(
                midpoint,
                5_000 + midpoint * 10 / 1_000_000,
                sync_id=index,
            )
        )

    estimate = estimator.estimate
    assert estimate is not None
    assert estimate.drift_ppm == pytest.approx(10.0)
    transmitter_time = 30_000_000
    receiver_time = transmitter_time + 5_000 + transmitter_time * 10 / 1_000_000
    assert estimate.receiver_to_transmitter(receiver_time) == pytest.approx(
        transmitter_time
    )


def test_clock_sync_estimator_resets_after_receiver_reboot():
    estimator = ClockSyncEstimator()
    estimator.add(sample(sync_id=1, boot_id=7))
    estimate = estimator.add(sample(sync_id=2, boot_id=8))

    assert estimate.receiver_boot_id == 8
    assert len(estimator.samples) == 1


def test_clock_sync_estimator_resets_after_transmitter_reboot():
    estimator = ClockSyncEstimator()
    estimator.add(sample(midpoint_us=10_000_000, sync_id=1))
    estimator.add(sample(midpoint_us=1_000_000, sync_id=0))

    assert len(estimator.samples) == 1
