import pytest

from radio_processor.gui.app import (
    GUI_INTERVAL_MS,
    _parser,
)


def test_gui_requests_at_least_twenty_four_frames_per_second():
    assert 1000 / GUI_INTERVAL_MS >= 24
    assert 1000 / GUI_INTERVAL_MS < 25


def test_gui_parser_uses_physical_subcarrier_controls():
    args = _parser().parse_args(["--port", "/dev/ttyUSB1"])

    assert args.dashboard_subcarriers == 12
    assert args.inspect_subcarrier == 1


def test_gui_parser_rejects_removed_range_flags():
    with pytest.raises(SystemExit):
        _parser().parse_args(["--port", "/dev/ttyUSB1", "--start", "0"])
