"""Native principal-component spectrum front end against a NumPy reference."""

import numpy as np
import pytest
from fall_detection._radio_native import PcSpectrumFrontEnd

FRAMES, HOP = 480, 30
INTERIOR = np.r_[2:121, 124:243]


def stream(length: int, seed: int, absent: bool = False) -> np.ndarray:
    """Assembled rows [length, 1964]: low-rank motion plus noise per receiver,
    staggered 12-in-68 receiver gaps, some invalid tones, receiver 4 absent."""
    rng = np.random.default_rng(seed)
    t = np.arange(length)[:, None]
    tones = np.arange(245)[None, :] / 245
    rows = np.zeros((length, 1964), np.float32)
    for r in range(4):
        present = ((t[:, 0] + 17 * r) % 68 >= 12) & (not (absent and r == 3))
        phase = t / 120
        values = (
            2 * np.sin(2 * np.pi * 3 * phase) * tones
            + np.sin(2 * np.pi * 11 * phase + r) * (1 - tones)
            + 0.5 * np.cos(2 * np.pi * 37 * phase) * np.sin(6 * tones)
            + 0.3 * rng.standard_normal((length, 245))
        )
        valid = present[:, None] & ((np.arange(245)[None, :] * 31 + t * 7) % 101 != 0)
        rows[:, r * 245 : (r + 1) * 245] = np.where(valid, values, 0)
        rows[:, 980 + r * 245 : 980 + (r + 1) * 245] = valid
        rows[:, 1960 + r] = present
    return rows


def reference(window: np.ndarray) -> np.ndarray:
    """PCSpectrum.frame_features in evaluation mode, in float64."""
    frames = window.shape[0]
    shape = (frames, 4, 245)
    valid = window[:, 980:1960].reshape(shape)[:, :, INTERIOR].astype(np.float64)
    values = window[:, :980].reshape(shape)[:, :, INTERIOR] * valid
    usable = valid.mean(-1) >= 0.9
    taper = np.hanning(66)[1:-1]
    position = np.arange(64) - 31.5
    count = (frames - 64) // 8 + 1
    logp = np.zeros((4, count, 32))
    ok = np.zeros((4, count), bool)
    for r in range(4):
        weight = usable[:, r].astype(np.float64)
        n = max(weight.sum(), 1.0)
        mean = (values[:, r] * weight[:, None]).sum(0) / n
        centred = (values[:, r] - mean) * weight[:, None]
        axes = np.linalg.eigh(centred.T @ centred / n)[1][:, -5:]
        scores = centred @ axes
        for f in range(count):
            present = weight[8 * f : 8 * f + 64]
            ok[r, f] = present.mean() >= 0.6
            w = present * taper
            total = max(w.sum(), 1e-6)
            offset = position - (w * position).sum() / total
            spread = max((w * offset**2).sum(), 1e-6)
            series = scores[8 * f : 8 * f + 64].T
            level = (w * series).sum(-1) / total
            slope = (w * offset * series).sum(-1) / spread
            tapered = (series - level[:, None] - slope[:, None] * offset) * w
            power = (np.abs(np.fft.rfft(tapered, axis=-1)) ** 2).sum(0)[1:]
            logp[r, f] = np.log(power / max((w**2).sum(), 1e-6) + 1e-6)
    counted = ok.sum(0)
    out = np.zeros((count, 65))
    out[:, :32] = (logp * ok[..., None]).sum(0) / np.maximum(counted, 1)[:, None]
    peak = np.where(ok[..., None], logp, -1e4).max(0)
    out[:, 32:64] = np.where(counted[:, None] > 0, peak, 0.0)
    out[:, 64] = counted / 4
    return out


def features(front: PcSpectrumFrontEnd, window: np.ndarray, shift=None):
    raw, updates, _ = front.features(
        np.ascontiguousarray(window, np.float32).tobytes(), shift
    )
    return np.frombuffer(raw, np.float32).reshape(-1, 65), updates


@pytest.mark.parametrize("simd", [True, False])
@pytest.mark.parametrize("absent", [False, True])
def test_features_match_the_numpy_reference(simd, absent):
    window = stream(FRAMES, seed=1, absent=absent)
    got, updates = features(PcSpectrumFrontEnd(FRAMES, simd=simd), window)
    assert updates == ["full"] * 3 + ["skipped" if absent else "full"]
    np.testing.assert_allclose(got, reference(window), atol=1e-3, rtol=0)


def test_streaming_slides_and_equals_stateless():
    data = stream(FRAMES + 5 * HOP, seed=2)
    streaming, stateless = PcSpectrumFrontEnd(FRAMES), PcSpectrumFrontEnd(FRAMES)
    for hop in range(6):
        window = data[hop * HOP : hop * HOP + FRAMES]
        got, updates = features(streaming, window, shift=HOP)
        assert updates == ["full" if hop == 0 else "sliding"] * 4
        expected, _ = features(stateless, window)
        np.testing.assert_allclose(got, expected, atol=1e-4, rtol=0)


def test_invalid_windows_are_rejected():
    front = PcSpectrumFrontEnd(FRAMES)
    with pytest.raises(ValueError, match="wrong size"):
        front.features(np.zeros((FRAMES - 1, 1964), np.float32).tobytes())
    window = stream(FRAMES, seed=3)
    window[10, 5] = np.nan
    with pytest.raises(ValueError, match="finite"):
        front.features(window.tobytes())
    with pytest.raises(ValueError):
        PcSpectrumFrontEnd(FRAMES, threads=5)
