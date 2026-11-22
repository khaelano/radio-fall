"""Synthetic four-receiver CSI amplitude traces with one motion burst."""

import numpy as np

RATE = 120


def burst_trace(rng, *, frequency, start, stop, seconds=10.0, amplitude=3.0):
    """Return a noisy [time, 4, 6] trace with one windowed sinusoidal burst."""
    time = np.arange(round(seconds * RATE)) / RATE
    trace = 20 + rng.normal(0, 0.2, (len(time), 4, 6))
    inside = (time >= start) & (time < stop)
    envelope = inside * np.sin(np.pi * np.clip((time - start) / (stop - start), 0, 1))
    burst = amplitude * envelope * np.sin(2 * np.pi * frequency * time)
    return trace + burst[:, None, None] * rng.uniform(0.5, 1.5, (1, 4, 6))
