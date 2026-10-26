import pytest

from fall_detection.radio.visualization.app import (
    GUI_FPS_CHOICES,
    GUI_FPS_DEFAULT,
    GUI_INTERVAL_MS,
    LiveState,
    _parser,
    frame_interval_ms,
)
from fall_detection.radio.acquisition.buffer import RollingCsiBuffer


def test_gui_uses_constant_sixteen_or_twenty_four_fps():
    assert GUI_FPS_CHOICES == (16, 24)
    assert GUI_FPS_DEFAULT == 24
    assert frame_interval_ms(24) == 42
    assert frame_interval_ms(16) == 63
    assert GUI_INTERVAL_MS == frame_interval_ms(GUI_FPS_DEFAULT)
    # Whole-millisecond pacing stays within a frame per second of the target.
    for fps in GUI_FPS_CHOICES:
        assert abs(1000 / frame_interval_ms(fps) - fps) < 1.0


def test_gui_parser_uses_physical_subcarrier_controls():
    args = _parser().parse_args(["--port", "/dev/ttyUSB1"])

    assert args.dashboard_subcarriers == 12
    assert args.inspect_subcarrier == 2


def test_gui_parser_accepts_udp_listener_options():
    args = _parser().parse_args(
        [
            "--transport",
            "udp",
            "--listen-host",
            "192.168.50.1",
            "--listen-port",
            "5501",
            "--receiver-mac",
            "24:6f:28:aa:bb:cc",
        ]
    )

    assert args.transport == "udp"
    assert args.listen_host == "192.168.50.1"
    assert args.listen_port == 5501
    assert args.receiver_mac == "24:6f:28:aa:bb:cc"


def test_gui_parser_accepts_espnow_gateway_serial_options():
    args = _parser().parse_args(
        [
            "--transport",
            "espnow",
            "--port",
            "/dev/ttyUSB0",
            "--baud",
            "921600",
            "--receiver-mac",
            "24:6f:28:aa:bb:cc",
        ]
    )

    assert args.transport == "espnow"
    assert args.port == "/dev/ttyUSB0"
    assert args.receiver_mac == "24:6f:28:aa:bb:cc"


def test_gui_parser_accepts_usb_receiver_selection():
    args = _parser().parse_args(
        [
            "--receiver-config",
            "configs/radio/receivers.json",
            "--radio-profile",
            "configs/radio/profiles/indonesia_2g_ch6.json",
            "--receiver-id",
            "rx-2",
        ]
    )

    assert args.receiver_id == "rx-2"


def test_live_state_switches_between_configured_receiver_buffers():
    first = RollingCsiBuffer()
    second = RollingCsiBuffer()
    state = LiveState()

    state.configure_receivers({"receiver-a": first, "receiver-b": second})
    assert state.selected_receiver_id == "receiver-a"
    assert state.buffer is first

    state.select_receiver("receiver-b")
    assert state.selected_receiver_id == "receiver-b"
    assert state.buffer is second


def test_gui_parser_rejects_removed_range_flags():
    with pytest.raises(SystemExit):
        _parser().parse_args(["--port", "/dev/ttyUSB1", "--start", "0"])
