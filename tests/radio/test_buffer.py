from fall_detection.radio.acquisition.buffer import RollingCsiBuffer
from fall_detection.radio.acquisition.protocol import parse_csi_line


def record(sequence: int):
    return parse_csi_line(
        f'CSI_DATA,{sequence},aa:bb:cc:dd:ee:ff,-40,11,1,0,0,1,1,0,0,0,0,-95,0,11,0,{sequence * 1000},0,36,0,4,0,"[3,4,0,5]"'
    )


def test_buffer_counts_missing_sequences_and_keeps_recent_records():
    buffer = RollingCsiBuffer(nominal_rate=2, seconds=2)
    buffer.append(record(10))
    buffer.append(record(12))

    snapshot = buffer.snapshot()

    assert buffer.missing_sequences == 1
    assert buffer.received_records == 2
    assert snapshot.start_sequence == 10
    assert snapshot.end_sequence == 12
    assert snapshot.amplitudes == ((5.0, 5.0), (5.0, 5.0))
    assert snapshot.phases[0][0] > 0.0
    assert snapshot.real == ((4.0, 5.0), (4.0, 5.0))
    assert snapshot.imaginary == ((3.0, 0.0), (3.0, 0.0))
    assert snapshot.rssi == (-40, -40)
    assert snapshot.noise_floor == (-95, -95)


def test_buffer_has_bounded_history():
    buffer = RollingCsiBuffer(nominal_rate=2, seconds=2)
    for sequence in range(5):
        buffer.append(record(sequence))

    snapshot = buffer.snapshot()

    assert len(snapshot.timestamps) == 4
    assert snapshot.start_sequence == 1


def test_snapshot_can_limit_materialization_to_visible_seconds():
    buffer = RollingCsiBuffer(nominal_rate=100, seconds=10, max_records=100)
    for sequence in range(5):
        buffer.append(record(sequence))

    snapshot = buffer.snapshot(seconds=0.002)

    assert snapshot.start_sequence == 2
    assert snapshot.end_sequence == 4
    assert len(snapshot.timestamps) == 3


def test_buffer_repairs_a_late_packet_within_reorder_window():
    buffer = RollingCsiBuffer(nominal_rate=100, seconds=10)
    buffer.append(record(10))
    buffer.append(record(12))
    assert buffer.missing_sequences == 1

    buffer.append(record(11))

    assert buffer.missing_sequences == 0


def test_buffer_unwraps_uint32_device_timestamp():
    buffer = RollingCsiBuffer(nominal_rate=100, seconds=10, max_records=100)
    first = record(1)
    second = record(2)
    # Replace the tiny fixture timestamp with values around the ESP32 counter
    # wrap while keeping the records otherwise valid.
    from dataclasses import replace

    buffer.append(replace(first, timestamp_us=0xFFFFFFF0))
    buffer.append(replace(second, timestamp_us=0x00000010))

    assert buffer.snapshot().timestamps == (0.0, 32 / 1_000_000)


def test_buffer_keeps_progress_after_device_timestamp_reset():
    from dataclasses import replace

    buffer = RollingCsiBuffer(nominal_rate=100, seconds=10, max_records=100)
    buffer.append(replace(record(1), timestamp_us=1_000_000))
    buffer.append(replace(record(2), timestamp_us=2_000_000))
    buffer.append(replace(record(3), timestamp_us=10))
    buffer.append(replace(record(4), timestamp_us=20))

    timestamps = buffer.snapshot().timestamps
    assert timestamps[-1] > timestamps[-2]


def test_monitor_snapshot_contains_only_compact_scalar_traces_and_downsamples():
    buffer = RollingCsiBuffer(nominal_rate=100, seconds=10, max_records=100)
    records = []
    for sequence in range(11):
        parsed = record(sequence)
        records.append(parsed)
        buffer.append(parsed)

    snapshot = buffer.monitor_snapshot(seconds=1.0, max_points=4)

    assert snapshot.timestamps == (0.0, 0.003, 0.006, 0.01)
    assert snapshot.mean_i == (4.5, 4.5, 4.5, 4.5)
    assert snapshot.mean_q == (1.5, 1.5, 1.5, 1.5)
    assert snapshot.rssi == (-40, -40, -40, -40)
    assert snapshot.noise_floor == (-95, -95, -95, -95)
    assert not hasattr(snapshot, "amplitudes")
    assert not hasattr(snapshot, "phases")
    assert all(parsed._derived_views_cache is None for parsed in records)
    assert all(parsed._ltf_blocks_cache is None for parsed in records)
    assert buffer.received_records == 11
    assert len(buffer.snapshot().timestamps) == 11
