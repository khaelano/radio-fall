from __future__ import annotations

from fall_detection.collection.app import (
    COLLECTOR_FPS_CHOICES,
    COLLECTOR_FPS_DEFAULT,
    COLLECTOR_RADIO_PREVIEW_POINTS,
    COLLECTOR_RADIO_PREVIEW_SECONDS,
    COLLECTOR_RADIO_REFRESH_MS,
    _format_radio_metrics,
    _parser,
    frame_interval_ms,
)


def test_collection_parser_defaults_to_espnow_protocol():
    args = _parser().parse_args(
        [
            "--port",
            "/dev/ttyUSB0",
            "--output-dir",
            "data/test-sessions",
        ]
    )

    assert args.transport == "espnow"
    assert args.output_dir.name == "test-sessions"
    assert args.nominal_rate_hz == 50


def test_collection_metrics_show_unavailable_telemetry_explicitly():
    class Reader:
        class Buffer:
            received_records = 2

        buffer = Buffer()

        def telemetry_snapshot(self):
            from fall_detection.radio.acquisition.telemetry import BackhaulTelemetrySnapshot

            return BackhaulTelemetrySnapshot(
                captured_monotonic_ns=1,
                records=2,
                batches=1,
                host_missing_sequences=0,
                transport_missing=0,
                transport_reordered=0,
                batch_missing=0,
                batch_reordered=0,
                malformed=0,
                foreign=0,
                receiver_restarts=0,
                serial_frames=None,
                receiver_boot_id=None,
                receiver_stats=None,
                transmitter_stats=None,
                gateway_stats=None,
            )

    text = _format_radio_metrics(Reader(), 50)
    assert "unavailable" in text


def test_collector_radio_preview_matches_ui_frame_pacing():
    assert COLLECTOR_RADIO_REFRESH_MS == frame_interval_ms(COLLECTOR_FPS_DEFAULT)
    assert 1000 / COLLECTOR_RADIO_REFRESH_MS >= COLLECTOR_FPS_CHOICES[0] - 1
    assert 2 <= COLLECTOR_RADIO_PREVIEW_SECONDS <= 3
    assert COLLECTOR_RADIO_PREVIEW_POINTS < 100 * COLLECTOR_RADIO_PREVIEW_SECONDS
