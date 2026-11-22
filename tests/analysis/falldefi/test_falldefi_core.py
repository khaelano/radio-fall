"""FallDeFi signal processing, event detection, features and classifier."""

import numpy as np
import pytest
from sklearn.exceptions import NotFittedError
from synthetic_traces import burst_trace

from fall_detection.analysis.falldefi.events import (
    box_counting_dimension,
    detect_events,
    log_noise_statistics,
    main_region,
    spectral_entropy,
)
from fall_detection.analysis.falldefi.model import FallDeFiConfig, FallDeFiDetector
from fall_detection.analysis.falldefi.signal import (
    principal_components,
    stft_magnitude,
    wavelet_denoise,
)

RATE = 120


def test_wavelet_denoise_preserves_length_and_reduces_fine_scale_noise():
    rng = np.random.default_rng(3)
    time = np.arange(1200) / RATE
    clean = np.sin(2 * np.pi * 2 * time)[:, None] * [1.0, 2.0]
    noisy = clean + rng.normal(0, 0.3, clean.shape)
    denoised = wavelet_denoise(noisy, levels=1)
    assert denoised.shape == noisy.shape
    assert np.std(denoised - clean) < np.std(noisy - clean)
    with pytest.raises(ValueError, match="level"):
        wavelet_denoise(noisy[:8], levels=1)


def test_principal_components_projects_centered_leading_directions():
    rng = np.random.default_rng(4)
    source = rng.normal(0, 1, 500)
    values = 5 + source[:, None] * [3.0, -1.0, 2.0] + rng.normal(0, 0.01, (500, 3))
    projected = principal_components(values, components=2)
    assert projected.shape == (500, 2)
    np.testing.assert_allclose(projected.mean(axis=0), 0, atol=1e-9)
    assert projected[:, 0].var() > 1e4 * projected[:, 1].var()
    with pytest.raises(ValueError, match="components"):
        principal_components(values, components=4)


def test_stft_magnitude_peaks_at_the_sinusoid_frequency():
    signal = np.sin(2 * np.pi * 15 * np.arange(600) / RATE)
    magnitude, frequencies, centers = stft_magnitude(
        signal, sample_rate_hz=RATE, window_samples=64, hop_samples=32, fft_samples=64
    )
    assert magnitude.shape == (1 + (600 - 64) // 32, 33)
    assert frequencies[1] == pytest.approx(RATE / 64)
    assert centers[0] == pytest.approx(32 / RATE)
    assert np.all(frequencies[magnitude.argmax(axis=1)] == 15)


def test_detect_events_merges_runs_separated_by_less_than_the_gap():
    curve = np.array([0, 5, 5, 0, 5, 0, 0, 5, 0], dtype=float)
    assert detect_events(curve, 1, hop_seconds=0.25, merge_gap_seconds=0.5) == [
        (1, 5),
        (7, 8),
    ]
    assert detect_events(np.zeros(4), 1, hop_seconds=0.25, merge_gap_seconds=0.5) == []


def test_main_region_keeps_the_largest_eight_connected_region():
    magnitude = np.zeros((6, 6))
    magnitude[[0, 1, 2], [0, 1, 2]] = 5
    magnitude[5, 4:] = 5
    region = main_region(magnitude, 5)
    np.testing.assert_array_equal(np.argwhere(region), [[0, 0], [1, 1], [2, 2]])
    assert not main_region(magnitude, 6).any()
    band = np.zeros(6, dtype=bool)
    band[4:] = True
    np.testing.assert_array_equal(
        np.argwhere(main_region(magnitude, 5, band)), [[5, 4], [5, 5]]
    )
    assert not main_region(magnitude, 5, ~band & (np.arange(6) == 3)).any()


def test_box_counting_dimension_distinguishes_lines_and_areas():
    assert box_counting_dimension(np.eye(32, dtype=bool)) == pytest.approx(1)
    assert box_counting_dimension(np.ones((32, 32), dtype=bool)) == pytest.approx(2)
    assert box_counting_dimension(np.zeros((4, 4), dtype=bool)) == 0


def test_spectral_entropy_and_noise_threshold_follow_their_definitions():
    frequencies = np.arange(8) * 2.0
    flat = np.ones((3, 8))
    assert spectral_entropy(flat, frequencies, low_hz=1, high_hz=10) == pytest.approx(
        np.log(4)
    )
    assert spectral_entropy(0 * flat, frequencies, low_hz=1, high_hz=10) == 0
    mean, spread = log_noise_statistics(
        np.r_[flat, 100 * flat], frequencies, low_hz=4, high_hz=12
    )
    assert (mean, spread) == pytest.approx((1, 1))


def test_detector_trains_on_events_and_flags_fall_like_bursts():
    rng = np.random.default_rng(7)
    falls = [burst_trace(rng, frequency=15, start=4, stop=6.5) for _ in range(4)]
    others = [
        burst_trace(rng, frequency=8, start=2, stop=7, amplitude=1) for _ in range(4)
    ]
    quiet = [burst_trace(rng, frequency=15, start=0, stop=1, amplitude=0)]
    resting = [burst_trace(rng, frequency=15, start=0, stop=1, seconds=4, amplitude=0)]
    config = FallDeFiConfig(cv_folds=2, svm_log2_c=(0, 4), svm_log2_gamma=(0, 2))
    detector = FallDeFiDetector(config)
    with pytest.raises(NotFittedError):
        detector.analyze(falls[0])
    detector.fit([*falls, *others], np.repeat([1, 0], 4), resting)
    assert detector.training_events_["fall"] == 4
    assert detector.training_events_["non_fall"] >= 4
    assert detector.training_detection_rate_ >= config.detection_target
    assert detector.threshold_k_ in config.k_grid
    analysis = detector.analyze(falls[0])
    assert len(analysis.events) == 1 and analysis.main_event == 0
    assert analysis.features[0, 0] == pytest.approx(2.4, abs=0.3)
    np.testing.assert_array_equal(
        detector.predict([*falls, *others, *quiet]), [1] * 4 + [0] * 5
    )
    dropped = falls[0].copy()
    dropped[:, 1] = np.nan
    assert detector.predict([dropped]).tolist() == [1]
    with pytest.raises(ValueError, match="training events per class"):
        FallDeFiDetector(config).fit(falls, np.ones(4, dtype=int), resting)
