from __future__ import annotations

from fall_detection.collection.app import (
    COLLECTOR_FPS_CHOICES,
    COLLECTOR_FPS_DEFAULT,
    COLLECTOR_UI_INTERVAL_MS,
    COLLECTOR_VIEW_SECONDS,
    _format_radio_metrics,
    _parser,
    frame_interval_ms,
)
from fall_detection.radio.visualization.app import GUI_FPS_CHOICES, GUI_INTERVAL_MS
from fall_detection.radio.visualization.dashboard import DEFAULT_VIEW_SECONDS


def test_collection_parser_defaults_to_ble_protocol():
    args = _parser().parse_args(
        [
            "--port",
            "/dev/ttyUSB0",
            "--output-dir",
            "data/test-sessions",
        ]
    )

    assert args.transport == "ble"
    assert args.output_dir.name == "test-sessions"
    assert args.nominal_rate_hz == 50


def test_collection_metrics_show_unavailable_telemetry_explicitly():
    class Reader:
        class Buffer:
            received_records = 2

        buffer = Buffer()

        def telemetry_snapshot(self):
            from fall_detection.radio.acquisition.telemetry import (
                BackhaulTelemetrySnapshot,
            )

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


def test_collector_shares_the_viewer_frame_pacing_and_window():
    assert COLLECTOR_FPS_CHOICES == GUI_FPS_CHOICES
    assert frame_interval_ms(COLLECTOR_FPS_DEFAULT) == GUI_INTERVAL_MS
    assert COLLECTOR_UI_INTERVAL_MS == frame_interval_ms(COLLECTOR_FPS_DEFAULT)
    assert COLLECTOR_VIEW_SECONDS == DEFAULT_VIEW_SECONDS
    assert 2 <= COLLECTOR_VIEW_SECONDS <= 5
