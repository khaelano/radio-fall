# FallDeFi

FallDeFi wavelet denoising, per-receiver PCA, averaged STFT spectrograms,
power-burst event detection, and RBF SVM classification of event features,
with explicit ESP32-C5 and 120 Hz adaptations.

See [the implementation guide](../../../../../docs/baselines/falldefi.md) for the paper
mapping, differences from the released code, run command, and limitations.

```bash
uv run python -m fall_detection.analysis.baselines.falldefi --help
```
