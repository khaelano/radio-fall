"""Spectrogram segmentation, power-burst events and FallDeFi's selected features.

The paper (§§5.2–6.2) leaves several definitions open. Where it does, these
functions follow the authors' released MATLAB code (``time_freq_processing_all
_events.m`` and ``BoxCountfracDim.m`` in github.com/dmsp123/FallDeFi, MIT
licence): a log-normal noise fit, an 8-connected region above the threshold
(ranked by event-band magnitude here, by size in the code), events merged
across gaps shorter than 0.5 s, and the box-counting dimension of the region
mask. Spectral entropy follows the paper's equation, which the released
script does not implement. See docs/falldefi.md for every difference.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

FEATURE_NAMES = (
    "event_duration_seconds",
    "spectral_entropy_1_10_hz",
    "spectral_entropy_10_30_hz",
    "fractal_dimension",
)
"""The paper's selected features (Table 1), in the order they are returned."""

ENTROPY_BANDS_HZ = ((1.0, 10.0), (10.0, 30.0))


def band_mask(frequencies_hz: np.ndarray, low_hz: float, high_hz: float) -> np.ndarray:
    """Select bins with ``low_hz <= f < high_hz``.

    Args:
        frequencies_hz: Bin center frequencies.
        low_hz: Inclusive lower bound.
        high_hz: Exclusive upper bound.

    Returns:
        Boolean mask over the frequency axis.
    """
    frequencies = np.asarray(frequencies_hz, dtype=np.float64)
    return (frequencies >= low_hz) & (frequencies < high_hz)


def log_noise_statistics(
    magnitude: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    low_hz: float,
    high_hz: float,
) -> tuple[float, float]:
    """Return the mean and standard deviation of log10 magnitudes in a band.

    The noise threshold is ``10 ** (mean + k * std)``. The released code fits
    this log-normal model to an activity spectrogram's bins above 200 Hz, where
    its 1000 Hz traces hold only residual noise. At 120 Hz no band is free of
    motion, so this adaptation fits resting segments within the power-burst
    band instead.

    Args:
        magnitude: Spectrogram ``[frame, frequency]``.
        frequencies_hz: Bin center frequencies.
        low_hz: Inclusive lower band edge.
        high_hz: Exclusive upper band edge.

    Returns:
        Mean and population standard deviation of the log10 magnitudes.

    Raises:
        ValueError: If no positive magnitudes lie in the band.
    """
    values = np.asarray(magnitude, dtype=np.float64)
    selected = values[:, band_mask(frequencies_hz, low_hz, high_hz)]
    selected = selected[selected > 0]
    if not selected.size:
        raise ValueError("No positive spectrogram magnitudes in the noise band")
    logarithm = np.log10(selected)
    return float(logarithm.mean()), float(logarithm.std())


def main_region(
    magnitude: np.ndarray, threshold: float, band: np.ndarray | None = None
) -> np.ndarray:
    """Keep one 8-connected region of bins at or above the threshold.

    The released code keeps the largest region. After whitening, a large
    region can lie wholly outside the event band, so a ``band`` mask instead
    selects the region with the most magnitude inside that band.

    Args:
        magnitude: Spectrogram ``[frame, frequency]``.
        threshold: Segmentation threshold.
        band: Optional frequency mask; regions are then ranked by in-band
            magnitude, and none is kept if no region reaches the band.

    Returns:
        Boolean mask of the region; all false when no bin reaches the threshold.
        Ties resolve to the first region in scan order.
    """
    values = np.asarray(magnitude)
    mask = values >= threshold
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if not count:
        return mask
    if band is None:
        scores = np.bincount(labels.ravel())[1:]
    else:
        inside = labels[:, band]
        scores = np.bincount(
            inside.ravel(), weights=values[:, band].ravel(), minlength=count + 1
        )[1:]
        if not scores.any():
            return np.zeros_like(mask)
    return labels == int(np.argmax(scores)) + 1


def power_burst_curve(
    magnitude: np.ndarray,
    region: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    low_hz: float,
    high_hz: float,
) -> np.ndarray:
    """Sum segmented magnitudes over a band in each frame (paper equation 5).

    Args:
        magnitude: Spectrogram ``[frame, frequency]``.
        region: Mask of retained bins.
        frequencies_hz: Bin center frequencies.
        low_hz: Inclusive lower band edge.
        high_hz: Exclusive upper band edge.

    Returns:
        One power-burst value per frame.
    """
    band = band_mask(frequencies_hz, low_hz, high_hz)
    return (np.where(region, magnitude, 0)[:, band]).sum(axis=1)


def detect_events(
    curve: np.ndarray,
    threshold: float,
    *,
    hop_seconds: float,
    merge_gap_seconds: float,
) -> list[tuple[int, int]]:
    """Find frame runs above the threshold, merging runs separated by short gaps.

    Args:
        curve: Power-burst curve.
        threshold: Event threshold (paper equation 6).
        hop_seconds: Time between frames.
        merge_gap_seconds: Runs whose separation is shorter are joined.

    Returns:
        Events as ``(start, stop)`` frame indices, ``stop`` exclusive.
    """
    above = np.r_[False, np.asarray(curve) > threshold, False]
    edges = np.flatnonzero(np.diff(above.astype(np.int8)))
    runs = [(int(start), int(stop)) for start, stop in edges.reshape(-1, 2)]
    events: list[tuple[int, int]] = []
    for start, stop in runs:
        if events and (start - events[-1][1]) * hop_seconds < merge_gap_seconds:
            events[-1] = (events[-1][0], stop)
        else:
            events.append((start, stop))
    return events


def main_event(
    events: list[tuple[int, int]], region: np.ndarray, frequencies_hz: np.ndarray
) -> int | None:
    """Return the event with the largest duration times maximum frequency.

    The released code labels only this event of a fall trace as the fall.

    Args:
        events: Detected ``(start, stop)`` frame ranges.
        region: Mask of retained bins.
        frequencies_hz: Bin center frequencies.

    Returns:
        Index into ``events``, or None without events. Ties keep the first.
    """
    if not events:
        return None
    scores = [
        (stop - start) * extreme_frequency(region[start:stop], frequencies_hz).max()
        for start, stop in events
    ]
    return int(np.argmax(scores))


def extreme_frequency(region: np.ndarray, frequencies_hz: np.ndarray) -> np.ndarray:
    """Return the highest retained frequency in each frame, or zero.

    Args:
        region: Mask ``[frame, frequency]``.
        frequencies_hz: Bin center frequencies.

    Returns:
        The extreme-frequency curve.
    """
    mask = np.asarray(region, dtype=bool)
    highest = mask.shape[1] - 1 - np.argmax(mask[:, ::-1], axis=1)
    return np.where(mask.any(axis=1), np.asarray(frequencies_hz)[highest], 0.0)


def spectral_entropy(
    magnitude: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    low_hz: float,
    high_hz: float,
) -> float:
    """Return the natural-log entropy of an event's band power distribution.

    Power ``|S|^2`` is summed over the event's frames per bin and normalized
    within the band, following the paper's equation in §6.1.

    Args:
        magnitude: Segmented spectrogram of the event ``[frame, frequency]``.
        frequencies_hz: Bin center frequencies.
        low_hz: Inclusive lower band edge.
        high_hz: Exclusive upper band edge.

    Returns:
        Entropy in nats; zero when the band holds no power.
    """
    power = (np.asarray(magnitude, dtype=np.float64) ** 2).sum(axis=0)
    power = power[band_mask(frequencies_hz, low_hz, high_hz)]
    total = power.sum()
    if total <= 0:
        return 0.0
    probability = power[power > 0] / total
    return float(max(0.0, -np.sum(probability * np.log(probability))))


def box_counting_dimension(mask: np.ndarray) -> float:
    """Estimate the box-counting (Hausdorff) dimension of a binary image.

    The image is zero-padded to a power-of-two square. Occupied boxes are
    counted for box sizes from one pixel to the whole image, and the dimension
    is the least-squares slope of ``log N`` against ``log(1 / size)``.

    Args:
        mask: Two-dimensional boolean image.

    Returns:
        The dimension estimate; zero for an empty image.
    """
    image = np.asarray(mask, dtype=bool)
    if image.ndim != 2:
        raise ValueError("Box counting requires a two-dimensional mask")
    if not image.any():
        return 0.0
    side = 1 << int(np.ceil(np.log2(max(image.shape))))
    current = np.zeros((side, side), dtype=bool)
    current[: image.shape[0], : image.shape[1]] = image
    sizes, counts = [], []
    size = 1
    while True:
        sizes.append(size)
        counts.append(int(current.sum()))
        if len(current) == 1:
            break
        current = current.reshape(len(current) // 2, 2, -1, 2).any(axis=(1, 3))
        size *= 2
    if len(sizes) < 2:
        return 0.0
    slope = np.polyfit(np.log(1 / np.asarray(sizes)), np.log(counts), 1)[0]
    return float(slope)


def event_features(
    magnitude: np.ndarray,
    region: np.ndarray,
    frequencies_hz: np.ndarray,
    event: tuple[int, int],
    *,
    hop_seconds: float,
) -> np.ndarray:
    """Compute the selected features of one event (paper §6.2).

    Args:
        magnitude: Spectrogram ``[frame, frequency]``.
        region: Retained-bin mask from :func:`main_region`.
        frequencies_hz: Bin center frequencies.
        event: ``(start, stop)`` frame range.
        hop_seconds: Time between frames.

    Returns:
        Values ordered as :data:`FEATURE_NAMES`.
    """
    start, stop = event
    segmented = np.where(region, magnitude, 0)[start:stop]
    return np.array(
        [
            (stop - start) * hop_seconds,
            *(
                spectral_entropy(segmented, frequencies_hz, low_hz=low, high_hz=high)
                for low, high in ENTROPY_BANDS_HZ
            ),
            box_counting_dimension(region[start:stop]),
        ]
    )
