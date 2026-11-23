"""CSI preprocessing and time-frequency analysis for FallDeFi (paper §§4–5.1).

Each receiver stands in for one of the paper's antenna pairs. Its tones are
scaled to relative amplitude, wavelet-denoised, decorrelated with principal
component analysis (PCA), and each leading component is transformed by a
short-time Fourier transform (STFT). The detector then whitens each
receiver's spectrogram by its resting noise floor and averages the receivers,
in place of the plain average of Algorithm 1, line 11.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pywt
from threadpoolctl import threadpool_limits


@dataclass(frozen=True)
class Spectrogram:
    """Averaged STFT magnitude of one trace.

    Attributes:
        magnitude: Nonnegative magnitudes ``[frame, frequency]``.
        frequencies_hz: Center frequency of each one-sided FFT bin.
        frame_seconds: Center time of each frame from the trace start.
    """

    magnitude: np.ndarray
    frequencies_hz: np.ndarray
    frame_seconds: np.ndarray


def wavelet_denoise(
    values: np.ndarray, *, wavelet: str = "sym3", levels: int = 1
) -> np.ndarray:
    """Soft-threshold detail coefficients using a finest-level noise estimate.

    This follows the released FallDeFi code, equivalent to MATLAB
    ``wden(x, 'sqtwolog', 's', 'sln', levels, wavelet)``: the noise scale is
    ``median(|d1|) / 0.6745`` from the finest detail level, the threshold is
    that scale times ``sqrt(2 ln N)``, and every detail level is soft
    thresholded while the approximation is kept.

    Args:
        values: Finite signals with time on axis zero, such as ``[time, tone]``.
        wavelet: PyWavelets discrete wavelet name.
        levels: Number of decomposition levels.

    Returns:
        Denoised signals with the input shape.

    Raises:
        ValueError: If values are not finite or the level is unsupported.
    """
    array = np.asarray(values, dtype=np.float64)
    if array.ndim < 1 or not len(array) or not np.isfinite(array).all():
        raise ValueError("Wavelet denoising requires finite, nonempty signals")
    filter_length = pywt.Wavelet(wavelet).dec_len
    if (
        isinstance(levels, bool)
        or not isinstance(levels, (int, np.integer))
        or not 1 <= levels <= pywt.dwt_max_level(len(array), filter_length)
    ):
        raise ValueError("Wavelet level must be positive and supported by the length")
    coefficients = pywt.wavedec(array, wavelet, mode="symmetric", level=levels, axis=0)
    scale = np.median(np.abs(coefficients[-1]), axis=0) / 0.6745
    threshold = scale * np.sqrt(2 * np.log(len(array)))
    denoised = [coefficients[0]] + [
        np.sign(detail) * np.maximum(np.abs(detail) - threshold, 0)
        for detail in coefficients[1:]
    ]
    return pywt.waverec(denoised, wavelet, mode="symmetric", axis=0)[: len(array)]


def principal_components(values: np.ndarray, *, components: int = 3) -> np.ndarray:
    """Project centered tones onto a fixed number of leading components.

    The paper selects, per activity, the fewest components reaching 95 % of the
    variance (§4.2, equation 2), "usually 2 to 3". That rule keeps nearly every
    component of a quiet resting segment, whose averaged spectrogram would then
    not be comparable with an activity trace's. The released code fixes three
    components; this adaptation does the same for traces and resting segments.

    Args:
        values: Finite amplitudes ``[time, tone]``.
        components: Number of leading components to keep, at most the tone count.

    Returns:
        Component time series ``[time, component]``; components of a signal
        without variance are zero.

    Raises:
        ValueError: If the input shape or component count is invalid.
    """
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2 or not array.size or not np.isfinite(array).all():
        raise ValueError("PCA requires finite [time, tone] amplitudes")
    if (
        isinstance(components, bool)
        or not isinstance(components, (int, np.integer))
        or not 1 <= components <= min(array.shape)
    ):
        raise ValueError("components must be positive and at most min(time, tones)")
    centered = array - array.mean(axis=0)
    # A trace's SVD is small; more BLAS threads only slow it down.
    with threadpool_limits(limits=1, user_api="blas"):
        _, _, rows = np.linalg.svd(centered, full_matrices=False)
    return centered @ rows[:components].T


def stft_magnitude(
    signal: np.ndarray,
    *,
    sample_rate_hz: float,
    window_samples: int,
    hop_samples: int,
    fft_samples: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the one-sided Hamming-window STFT magnitude of one signal.

    Args:
        signal: Finite one-dimensional samples.
        sample_rate_hz: Sampling frequency.
        window_samples: Symmetric Hamming window length.
        hop_samples: Frame advance; the paper uses half the window.
        fft_samples: FFT length, at least the window length.

    Returns:
        Magnitudes ``[frame, frequency]``, bin frequencies, and frame centers in
        seconds from the first sample.

    Raises:
        ValueError: If the signal is shorter than one window or settings are
            inconsistent.
    """
    samples = np.asarray(signal, dtype=np.float64)
    if (
        samples.ndim != 1
        or not np.isfinite(samples).all()
        or not 0 < hop_samples <= window_samples <= fft_samples
        or len(samples) < window_samples
    ):
        raise ValueError("STFT needs one finite window and hop <= window <= FFT")
    frames = np.lib.stride_tricks.sliding_window_view(samples, window_samples)
    frames = frames[::hop_samples] * np.hamming(window_samples)
    magnitude = np.abs(np.fft.rfft(frames, n=fft_samples, axis=1))
    frequencies = np.fft.rfftfreq(fft_samples, d=1 / sample_rate_hz)
    centers = (np.arange(len(frames)) * hop_samples + window_samples / 2) / (
        sample_rate_hz
    )
    return magnitude, frequencies, centers


def receiver_spectrogram(
    values: np.ndarray,
    *,
    sample_rate_hz: float,
    wavelet: str,
    wavelet_levels: int,
    components: int,
    window_samples: int,
    hop_samples: int,
    fft_samples: int,
) -> Spectrogram:
    """Average the component spectrograms of one receiver's tones.

    Each tone is first divided by its own mean over the trace. The receivers
    are separate radios with their own gain, so relative amplitude keeps their
    spectrograms on one scale.

    Args:
        values: Finite nonnegative amplitudes ``[time, tone]``.
        sample_rate_hz: Sampling frequency of the trace.
        wavelet: Wavelet used for denoising each tone.
        wavelet_levels: Wavelet decomposition levels.
        components: Principal components kept.
        window_samples: STFT window length.
        hop_samples: STFT frame advance.
        fft_samples: FFT length.

    Returns:
        The receiver's spectrogram, averaged over its components.

    Raises:
        ValueError: If the amplitudes are not finite nonnegative ``[time, tone]``.
    """
    amplitude = np.asarray(values, dtype=np.float64)
    if (
        amplitude.ndim != 2
        or not amplitude.size
        or not np.isfinite(amplitude).all()
        or np.any(amplitude < 0)
    ):
        raise ValueError("Receiver amplitudes must be finite nonnegative [time, tone]")
    means = amplitude.mean(axis=0)
    relative = np.divide(
        amplitude, means, out=np.zeros_like(amplitude), where=means > 0
    )
    denoised = wavelet_denoise(relative, wavelet=wavelet, levels=wavelet_levels)
    projected = principal_components(denoised, components=components)
    spectra = []
    frequencies = centers = None
    for component in projected.T:
        magnitude, frequencies, centers = stft_magnitude(
            component,
            sample_rate_hz=sample_rate_hz,
            window_samples=window_samples,
            hop_samples=hop_samples,
            fft_samples=fft_samples,
        )
        spectra.append(magnitude)
    return Spectrogram(np.mean(spectra, axis=0), frequencies, centers)
