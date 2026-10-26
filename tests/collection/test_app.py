from __future__ import annotations

from types import SimpleNamespace

from fall_detection.collection.app import (
    COLLECTOR_FPS_CHOICES,
    COLLECTOR_FPS_DEFAULT,
    COLLECTOR_RADIO_PREVIEW_POINTS,
    COLLECTOR_RADIO_PREVIEW_SECONDS,
    COLLECTOR_RADIO_REFRESH_MS,
    _RadioStartupGate,
    _frame_to_pixmap,
    _format_radio_metrics,
    _parser,
    _source,
    frame_interval_ms,
)


def test_preview_prefers_annotated_frame_over_raw_frame():
    seen = []

    class Cv2:
        COLOR_BGR2RGB = 1

        @staticmethod
        def cvtColor(image, _code):
            seen.append(image)
            return image

    class QImage:
        class Format:
            Format_RGB888 = 1

        def __init__(self, *_args):
            pass

        def copy(self):
            return self

    class QPixmap:
        @staticmethod
        def fromImage(image):
            return image

    QtGui = SimpleNamespace(QImage=QImage, QPixmap=QPixmap)
    raw = SimpleNamespace(data=b"raw", shape=(2, 3, 3))
    annotated = SimpleNamespace(data=b"annotated", shape=(2, 3, 3))
    frame = SimpleNamespace(frame=raw, display_frame=annotated)

    _frame_to_pixmap(frame, QtGui, Cv2)

    assert seen == [annotated]


def test_collection_parser_defaults_to_espnow_protocol_and_accepts_camera_source():
    args = _parser().parse_args(
        [
            "--port",
            "/dev/ttyUSB0",
            "--camera-source",
            "/dev/video2",
            "--camera-backend",
            "v4l2",
            "--output-dir",
            "data/test-sessions",
        ]
    )

    assert args.transport == "espnow"
    assert args.camera_source == "/dev/video2"
    assert args.camera_backend == "v4l2"
    assert args.output_dir.name == "test-sessions"
    assert args.nominal_rate_hz == 50
    assert _source(args.camera_source) == "/dev/video2"


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


def test_radio_starts_only_after_first_successful_camera_inference():
    class Camera:
        ready = False

    class Reader:
        def __init__(self):
            self.starts = 0
            self.stops = 0

        def start(self):
            self.starts += 1

        def stop(self):
            self.stops += 1

    camera = Camera()
    reader = Reader()
    gate = _RadioStartupGate(camera, reader)

    assert not gate.poll()
    assert reader.starts == 0

    camera.ready = True
    assert gate.poll()
    assert gate.poll()
    assert reader.starts == 1

    gate.stop()
    assert reader.stops == 1


def test_collector_radio_preview_matches_ui_frame_pacing():
    assert COLLECTOR_RADIO_REFRESH_MS == frame_interval_ms(COLLECTOR_FPS_DEFAULT)
    assert 1000 / COLLECTOR_RADIO_REFRESH_MS >= COLLECTOR_FPS_CHOICES[0] - 1
    assert 2 <= COLLECTOR_RADIO_PREVIEW_SECONDS <= 3
    assert COLLECTOR_RADIO_PREVIEW_POINTS < 100 * COLLECTOR_RADIO_PREVIEW_SECONDS
