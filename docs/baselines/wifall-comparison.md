# WiFall compared with the current sequence approach

This page compares WiFall [@wangWiFallDeviceFreeFall2017]
([converted text](../../resources/Papers/md/wifall-2017.md)) with the project's
current approach: amplitude sequences from
[`02_preprocess.ipynb`](../../notebooks/latest/02_preprocess.ipynb) and the CNN,
LSTM, and GRU classifiers in
[`03_training.ipynb`](../../notebooks/latest/03_training.ipynb). The repository's
WiFall adaptation is a separate baseline with only a one-session smoke run so
far; see [wifall.md](wifall.md).

The two result sets use different metrics, labels, data, and evaluation
protocols. The tables place them side by side; they do not rank the methods.

## Design and evaluation

| Aspect | WiFall (2017) | Current approach (November 2026) |
| --- | --- | --- |
| Task | Fall detection; also classifies walking, sitting down, standing up (§§4–6) | Binary fall versus non-fall window classification |
| Radio hardware | TP-LINK TL-WDR7500 routers transmitting; desktops with Intel 5300 NICs and modified firmware receiving (§5.1) | One ESP32-C5 transmitter, four ESP32-C5 receivers, ESP32-C6 USB gateway over ESP-NOW ([radio settings](../../configs/radio.json)) |
| Band, bandwidth, rate | 802.11n, 5 GHz, 100 packets/s (§5.1) | 5 GHz channel 44, 20 MHz, 120 Hz nominal |
| Spatial streams | 3×3 MIMO: 9 antenna-pair streams per link; one or two links (§§4.2, 5.2) | Four separate receivers (`rx-1`…`rx-4`), one stream each |
| Subcarriers | 30 reported by the Intel 5300 CSI tool (§4.2) | 245 HE20 tones per receiver, physical indices −122…122 |
| CSI quantity | Amplitude only; phase left for future work (§4.2) | Amplitude only |
| Denoising | Weighted moving average over past samples (eq. 9); `m` unspecified | Centered Hampel filter: 0.5 s span, threshold 3, scaled-MAD factor 1.4826 ([amplitude preprocessing](../amplitude-preprocessing.md)) |
| Causality | Smoothing uses past samples only | The centered filter uses 0.25 s of future samples; the live detector waits for that context |
| Signal transform | None beyond smoothing and per-stream aggregation | `log1p` of consecutive squared amplitude differences, normalized on training windows only |
| Missing samples | Not discussed | Kept as NaN; the model receives validity flags and receiver-presence flags |
| Motion gating | Local Outlier Factor against a resting profile; majority of 9 streams must be anomalous (§4.3.1) | None; every window is classified |
| Window | 2 s (200 samples) (§4.3.2) | 2, 4, and 6 s with 50% overlap (240, 480, 720 samples) |
| Model input | SVM: 7 statistics per stream. RF: top 3 singular values of the 200×270 window (§§4.3.2, 4.4) | Full sequence: 980 normalized values (4 × 245), 980 validity flags, 4 presence flags = 1,964 features per time step |
| Classifier | One-class SVM (LibSVM), falls as the target class; random forest (§4.4) | Two-layer 1D CNN with temporal mean pooling; single-layer LSTM; single-layer GRU; hidden size 64 |
| Training | Not described beyond the classifier choice | Adam, learning rate 0.001, batch 128, up to 30 epochs, early stopping on validation fall F1 (patience 5), positive-class weighting, seed 42 |
| Participants | Chamber: 1. Lab: 10 (8 M, 2 F). Dormitory: 8 (§5.4) | Two participants (Khaelano, Akmal) and one continuous non-fall session |
| Environments | RF chamber, 8×9 m lab, 4×5 m dormitory (§5.2) | Not recorded in the training notebook |
| Repetitions | Lab: 200 per activity per person over 8 locations. Dormitory: 100 per activity per person over 5 locations (§5.4) | Protocol-driven attempts; counts are not shown in the saved notebook outputs |
| Labels | Assigned by hand once per second by an observer (§5.4) | Collection cues: a fall window is positive when its center lies inside the action cue; other windows from fall attempts are dropped |
| Split | Not described | Attempt-level split, 60/20/20, stratified by dataset and activity, seed 42, shared across durations and models; not independent across sessions or participants |
| Metrics | Detection rate (eq. 15); false alarm = wrong fall detections ÷ total falls (eq. 16) | Window-level accuracy and fall-class precision, recall, F1 at threshold 0.5 |
| Runtime | MATLAB server; under 0.75 s per test case with SVD (§6.4) | Rust with ONNX Runtime, 250 ms hop; `cnn-4s` about 15 ms on WebGPU and 4 ms on CPU (Vega 7). LSTM and GRU take about 1.1–1.2 s per 4 s call and cannot keep up ([detector guide](../live-fall-detection.md)) |

## Reported results

WiFall reports per-scenario averages (Tables 2 and 3). The tables label the
columns "Precision", but §5.3 defines only a detection rate, which works like
recall. The false-alarm denominator is the number of falls.

| WiFall scenario | One-class SVM DR / FA | RF + SVD DR / FA |
| --- | --- | --- |
| Chamber | 96% / 18% | 98% / 15% |
| Lab, one link | 88% / 16% | 93% / 13% |
| Lab, two links | 94% / 11% | 96% / 10% |
| Dormitory | 83% / 14% | 89% / 12% |

The current results come from the outputs saved in `03_training.ipynb`. They
appear to belong to run `20261112T050332052704Z`, the source run named in
[`artifacts/model/cnn/manifest.json`](../../artifacts/model/cnn/manifest.json).
All values are on held-out test windows.

| Model | Window | Accuracy | Fall precision | Fall recall | Fall F1 |
| --- | --- | --- | --- | --- | --- |
| CNN | 2 s | 0.969 | 0.890 | 0.755 | 0.817 |
| CNN | 4 s | 0.964 | 0.849 | 0.805 | 0.827 |
| CNN | 6 s | 0.978 | 0.958 | 0.852 | 0.902 |
| GRU | 2 s | 0.944 | 0.739 | 0.590 | 0.656 |
| GRU | 4 s | 0.927 | 0.667 | 0.623 | 0.644 |
| GRU | 6 s | 0.936 | 0.879 | 0.537 | 0.667 |
| LSTM | 2 s | 0.941 | 0.713 | 0.590 | 0.646 |
| LSTM | 4 s | 0.623 | 0.145 | 0.519 | 0.227 |
| LSTM | 6 s | 0.807 | 0.293 | 0.444 | 0.353 |

The number of test windows per duration is not in the saved outputs. The run's
`metrics.json` files are versioned under `artifacts/notebooks.dvc` and are not
checked out in this workspace.

## Why the numbers are not comparable

- **Metric definitions differ.** WiFall's detection rate corresponds to fall
  recall, but its false-alarm rate divides by falls, not by non-fall windows or
  time. Neither result set reports false alarms per hour or event latency.
- **The unit of evaluation differs.** WiFall counts detected activities after
  LOF gating. The current approach scores overlapping windows, so neighboring
  windows from one attempt are correlated.
- **Neither result tests generalization.** WiFall does not describe its split.
  The current split keeps attempts together but mixes sessions and participants
  across partitions ([project knowledge](../project-knowledge.md#research-limits-and-rules)).
- **Labels are approximate on both sides.** WiFall labels once per second by
  hand and names this as a source of false alarms (§6.3). The current labels
  follow collection cues, not measured movement onset.
- **Accuracy depends on class balance.** Non-fall windows dominate the current
  test set, so accuracy stays high even when fall recall is low, as in the
  GRU rows.

A fair comparison needs both methods run on the same recordings, split, and
metrics. The [WiFall adaptation](wifall.md) is set up for that. Its only run so
far, a one-session smoke run, found no falls through its activity gate
([report](../reports/wifall-smoke-2026-11-22.md)).
