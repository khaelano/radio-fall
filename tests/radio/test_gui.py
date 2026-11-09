import pytest

from fall_detection.radio.acquisition.buffer import RollingCsiBuffer
from fall_detection.radio.visualization.app import (
    GUI_FPS_CHOICES,
    GUI_FPS_DEFAULT,
    GUI_INTERVAL_MS,
    LiveState,
    _parser,
    frame_interval_ms,
)


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


@pytest.mark.parametrize("transport", ["serial", "espnow", "udp"])
def test_gui_parser_rejects_legacy_transports(transport):
    with pytest.raises(SystemExit):
        _parser().parse_args(["--transport", transport])


def test_gui_defaults_to_gateway():
    assert _parser().parse_args([]).transport == "espnow_gateway"


def test_gui_parser_accepts_gateway_receiver_selection():
    args = _parser().parse_args(
        [
            "--config",
            "configs/radio.json",
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
