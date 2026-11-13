"""Display pacing and its command-line argument, shared by the live GUIs."""

import argparse

FPS_CHOICES = (16, 24)
FPS_DEFAULT = 24
STATUS_INTERVAL_SECONDS = 0.25


def frame_interval_ms(fps: int) -> int:
    """Return the nearest whole-millisecond display timer interval."""
    if fps < 1:
        raise ValueError("fps must be positive")
    return max(1, int(1000 / fps + 0.5))


def add_fps_argument(parser: argparse.ArgumentParser) -> None:
    """Add the constant UI refresh rate option shared by the live GUIs."""
    parser.add_argument(
        "--fps",
        type=int,
        choices=FPS_CHOICES,
        default=FPS_DEFAULT,
        help="constant UI refresh rate in frames per second",
    )
