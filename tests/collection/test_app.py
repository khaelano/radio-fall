from __future__ import annotations

from fall_detection.apps.collector.app import (
    COLLECTOR_UI_INTERVAL_MS,
    COLLECTOR_VIEW_SECONDS,
    DEFAULT_PROTOCOL,
    _parser,
)
from fall_detection.apps.common.dashboard import DEFAULT_VIEW_SECONDS
from fall_detection.apps.common.pacing import (
    FPS_CHOICES,
    FPS_DEFAULT,
    frame_interval_ms,
)
from fall_detection.apps.csi_viewer.app import GUI_INTERVAL_MS
from fall_detection.apps.csi_viewer.app import _parser as viewer_parser


def test_collection_parser_defaults_to_gateway_protocol():
    args = _parser().parse_args(
        [
            "--gateway-port",
            "/dev/ttyACM0",
            "--output-dir",
            "data/test-sessions",
        ]
    )

    assert args.gateway_port == "/dev/ttyACM0"
    assert args.output_dir.name == "test-sessions"
    assert args.config is None  # resolved centrally to configs/radio.json
    assert args.protocol is None  # selected in the startup dialog
    assert DEFAULT_PROTOCOL.name == "fall_simple.json"


def test_collection_protocol_can_be_selected_from_command_line():
    args = _parser().parse_args(["--protocol", "configs/collection/fall_simple.json"])

    assert str(args.protocol) == "configs/collection/fall_simple.json"


def test_collector_shares_the_viewer_frame_pacing_and_window():
    for parser in (_parser(), viewer_parser()):
        fps = next(a for a in parser._actions if a.dest == "fps")
        assert tuple(fps.choices) == FPS_CHOICES and fps.default == FPS_DEFAULT
    assert frame_interval_ms(FPS_DEFAULT) == GUI_INTERVAL_MS
    assert COLLECTOR_UI_INTERVAL_MS == frame_interval_ms(FPS_DEFAULT)
    assert COLLECTOR_VIEW_SECONDS == DEFAULT_VIEW_SECONDS
    assert 2 <= COLLECTOR_VIEW_SECONDS <= 5


def test_collection_video_is_optional_and_device_is_explicit():
    assert _parser().parse_args([]).video_device is None
    args = _parser().parse_args(["--video-device", "/dev/video2", "--video-fps", "25"])
    assert args.video_device == "/dev/video2"
    assert args.video_fps == 25 and args.fps == FPS_DEFAULT
