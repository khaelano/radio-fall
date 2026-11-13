# Live four-receiver fall scoring

The native sequence detector uses the existing nine ONNX exports and saved
normalizers under `artifacts/model/`. It requires no training dataset. Rust owns
acquisition, preprocessing, resident ONNX sessions, inference scheduling and
logs; Python supplies controls and displays results.

```sh
uv sync --extra radio --extra detect
uv run fall-detect
```

Connect the gateway and power the sensing radios. The default selection is
CNN with four-second windows. Select models in the desktop controls,
or run a bounded headless session:

```sh
uv run fall-detect --headless --duration 30 --models cnn-4s
```

## Replay without hardware

`--replay-capture` streams recorded native captures through the same pipeline
in real time instead of opening the gateway. Each capture directory needs
`radio.cgcf` and its `transport/gateway/<run>/` journal; consecutive captures
start new segments. `--replay-speed` changes the pace and `--replay-repeat`
loops. Both the GUI and `--headless` work; headless exits when the replay
finishes.

```sh
uv run dvc pull data/experiments/detector/native-capture-20261112-c.dvc
uv run fall-detect --replay-capture data/experiments/detector/native-capture-20261112-c
```

The GUI also shows a scrolling heatmap of the last ten seconds of raw CSI
magnitudes from all four receivers, redrawn at about 30 frames per second as
packets arrive. Below it, two heatmaps show the latest window of a selected
model: its raw magnitudes and the normalized model input (`log1p` squared
differences in standard units). Scores and window previews change once per hop.
Transparent cells are missing samples. The backend keeps the raw stream and
previews only for the GUI (`preview` in the native configuration).

Captures B and C replay; capture A lacks reference timing evidence. The
`live_detect` example in `radio_detection` (`cargo run -p radio-detection --example live_detect`)
runs the same backend from a JSON configuration without Python.

## Runtime

The backend defaults to WebGPU through ONNX Runtime 1.31.1, the separately
packaged WebGPU provider 0.5.0, Dawn and Vulkan. Both libraries are found in
the environment; `ORT_DYLIB_PATH` and `ORT_WEBGPU_PLUGIN`, or `--ort-library`
and `--webgpu-plugin`, override discovery. The only AMD WebGPU adapter is
selected automatically; `--adapter-id` picks one by PCI device ID. Warmup
fails if a model's main operator does not run on WebGPU. `--backend cpu` selects
CPU explicitly; GPU failures never fall back to CPU silently.

Preprocessing uses the documented settings of the current exports: 120 Hz,
centered 0.5-second Hampel span, threshold 3, MAD scale 1.4826 and minimum five
valid observations; consecutive squared difference, `log1p`, then each saved
normalizer. Inputs contain 980 signals, 980 validity flags and four
receiver-presence flags. On a replayed capture, every live input matched the
offline Python chain bit for bit; see the
[replay report](reports/native-replay-2026-11-12.md).

Each model keeps one latest pending window; one worker runs inference. The hop
defaults to 250 ms. A window is built once its future filter context (0.25 s)
and delivery grace (0.9 s) have passed, so results arrive about 1.2 s after the
window ends. Coverage below 70% for any receiver, stale input and runtime
errors produce unknown. Scores of at least 0.5 display a fall candidate; models
remain independent. Changing the selection restarts the backend. Outputs go to
a fresh directory under `data/experiments/detector/`: `predictions.jsonl`,
`detector.json`, and raw gateway journals in live mode. Git ignores these
`native-<timestamp>` folders; track a run worth keeping with `uv run dvc add`
(the 12 November runs are in `runs-20261112`).

A new run, an all-receiver gap of at least one second, or a history overflow
discards buffered samples and starts a new segment and generation; pending
windows from the old segment are dropped. Live acquisition uses the shared
transport session also used by the viewer and collector. After a recoverable
radio failure it waits `restart_delay_ms` (2 s), increasing linearly up to
30 s while the radio stays unavailable, and configures a fresh run; identity,
configuration and storage failures stop the detector. See
[automatic radio recovery](automatic-radio-recovery.md). The session is tested
against a fake gateway; this recovery path has not been exercised on hardware.

On the Vega 7, `cnn-4s` inference took about 15 ms on WebGPU and 4 ms on the
CPU during replay. Four-second LSTM and GRU calls took roughly 1.1–1.2 s, so
recurrent models cannot sustain a 250 ms update rate with the serial worker.
These are runtime measurements, not detection-accuracy results. See the
[GPU report](reports/native-webgpu-smoke-2026-11-12.md) and
[native acquisition report](reports/native-capture-2026-11-12.md).

Live gateway operation of the complete pipeline, sustained operation and
detection usefulness still require validation.

## Retired Python detector

The earlier Python detector (`--mode legacy`, the CPU PyTorch fall scorer,
notebook-trained phase models, `--export-model` and `--replay-session`) was
removed on 12 November 2026 together with its native `CnnPreprocessor` and its
runtime check and benchmark scripts. Its historical measurements and artifacts
remain under `data/experiments/detector/` and in the
[model pilot summary](reports/fall-model-pilots.md); retrieve the code from Git
history to reproduce them.
