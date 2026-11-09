"""Display pacing shared by the viewer and collection console."""

FPS_CHOICES = (16, 24)
FPS_DEFAULT = 24
STATUS_INTERVAL_SECONDS = 0.25


def frame_interval_ms(fps: int) -> int:
    """Return the nearest whole-millisecond display timer interval."""
    if fps < 1:
        raise ValueError("fps must be positive")
    return max(1, int(1000 / fps + 0.5))
