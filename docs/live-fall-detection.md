# Live four-receiver fall scoring

The native sequence detector uses the ONNX exports and saved normalizers under
`artifacts/model/`: the nine CNN, LSTM and GRU models, `tonepool_tcn-4s`, the
project's most consistent configuration (4 s, burst-centred training positives;
[tone-pooling report](reports/tone-pooling-2026-11-23.md)), `tiny_tcn1-4s`,
a 5,345-parameter model on the motion energy averaged over tones and receivers
that matched it on the session holdouts
([energy-inputs report](reports/energy-inputs-2026-11-26.md)), and
`pcspec_gru-4s`, a GRU on the STFT power of each window's principal
components, which ranked attempts best on the holdouts
([principal-component spectrum report](reports/pc-spectrum-2026-11-26.md)). It requires no
training dataset. Rust owns acquisition, preprocessing, resident ONNX sessions,
inference scheduling and logs; Python supplies controls and displays results.

```sh
uv sync --extra radio --extra detect
uv run fall-detect
```

Connect the gateway and power the sensing radios. The default selection is
`tonepool_tcn-4s`. Select models in the desktop controls,
or run a bounded headless session:

```sh
uv run fall-detect --headless --duration 30 --models tonepool_tcn-4s cnn-4s
```

`tonepool_tcn-4s` and `tiny_tcn1-4s` read the same input as the other models.
`pcspec_gru-4s` reads the signed difference instead (computed from the same
filtered amplitude, with its own normalizer), and a Rust front end turns each
window into 53 × 65 frame features before its ONNX head. That adds about
2.3 ms per window on the CPU. The published bundles, the checks on them and
what remains unverified are in the
[live tone-pool report](reports/live-tonepool-2026-11-24.md), the
[live tiny-TCN report](reports/live-tiny-tcn-2026-11-26.md) and the
[live PC-spectrum report](reports/live-pcspec-2026-11-26.md). Neither
`tiny_tcn1-4s` nor `pcspec_gru-4s` is the default until a new participant
confirms the holdout result. Calibrate each selected model on the installation
movements.

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

## Installation calibration

Scores shift with how a person moves, so calibrate the threshold once the
detector is running, with the person who will be monitored. Everyone else should
stay still or leave the room.

1. Wait until **Start movement** is enabled (the first window of the segment).
2. Press it, perform the movement shown in the status line, and press **Stop
   movement** when it ends. The mark must last at least 1 s.
3. Stay still until the countdown ends (about 6 s for 4 s models). The next movement
   starts where the last one ended.
4. After ten movements the threshold is set so that at most two of them would
   have alarmed, the table shows it as calibrated, and the calibration is saved
   to `calibration.json` in the run's output directory. Further movements refine
   it. **Discard movement** drops the one in progress or the last one, and a
   calibration with fewer than ten is withdrawn.

A movement is rejected, and must be repeated, if a model scored none of its
windows or if acquisition restarted. All selected models are calibrated on the
same movements.

In the recorded sessions, a calibration on the first movements was too strict later: early
movements scored higher, partly because the protocol starts with walking transitions
([replay report](reports/live-replay-evaluation-2026-11-25.md)). Calibrating on later
movements holds the false-positive rate of the non-falls near the target, but those
sessions cannot show its effect on falls.

Use the prompted mix: calibrating on one kind of movement moved the
false-positive rate between 0.12 and 0.50 on one held-out session. Reuse a
calibration with `--calibration FILE`. The detector refuses a file made
for another bundle, hop, delivery grace, coverage gate or source (replay or
gateway). It does not check the age of the file, and how long one lasts is
untested. The rule, its test under live conditions and its limits are in the
[calibration report](reports/live-calibration-2026-11-24.md).

## Runtime

The backend defaults to WebGPU through ONNX Runtime 1.31.1, the separately
packaged WebGPU provider 0.5.0, Dawn and Vulkan. Both libraries are found in
the environment; `ORT_DYLIB_PATH` and `ORT_WEBGPU_PLUGIN`, or `--ort-library`
and `--webgpu-plugin`, override discovery. The only AMD WebGPU adapter is
selected automatically; `--adapter-id` picks one by PCI device ID. Warmup
fails if a model's main operator does not run on WebGPU. `--backend cpu` selects
CPU explicitly; GPU failures never fall back to CPU silently. A CPU session uses at most four
threads and does not spin (about 0.6 of a core for the default model; 20 before the fix;
[replay report](reports/live-replay-evaluation-2026-11-25.md#cpu-use-of-the-product)).

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
errors produce unknown. In the GUI, scores at or above a model's threshold
display a fall candidate; models remain independent. The threshold is the
model's [calibration](#installation-calibration), or `--threshold` (default
0.5) without one; the table shows which. Changing the selection restarts the
backend. Outputs go to
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
[automatic radio recovery](automatic-radio-recovery.md). On 18 November, live
sessions recovered from a gateway USB unplug and from companion relay power
loss; the first relay recovery had exposed a stale-status replay that stopped
the detector, which is now fixed. See the
[hardware check](automatic-radio-recovery.md#hardware-check-18-november-2026).

On the Vega 7, `cnn-4s` inference took about 15 ms on WebGPU and 4 ms on the
CPU during replay. Four-second LSTM and GRU calls took roughly 1.1–1.2 s, so
recurrent models cannot sustain a 250 ms update rate with the serial worker.
These are runtime measurements, not detection-accuracy results. See the
[GPU report](reports/native-webgpu-smoke-2026-11-12.md) and
[native acquisition report](reports/native-capture-2026-11-12.md).

Live gateway sessions of up to ten minutes ran on 18 November. Many `cnn-4s`
windows were unknown because a receiver's coverage fell below 70%: 35–37% in
two uninterrupted five-minute sessions and 76–78% in a ten-minute session. The
dropouts came mainly from `rx-3` (below 70% in 30–63% of windows) and `rx-4`
(4–41%); `rx-1` and `rx-2` stayed near 0.8. Their cause is undiagnosed.
Sustained operation and detection usefulness still require validation.

## Retired Python detector

The earlier Python detector (`--mode legacy`, the CPU PyTorch fall scorer,
notebook-trained phase models, `--export-model` and `--replay-session`) was
removed on 12 November 2026 together with its native `CnnPreprocessor` and its
runtime check and benchmark scripts. Its historical measurements and artifacts
remain under `data/experiments/detector/` and in the
[model pilot summary](reports/fall-model-pilots.md); retrieve the code from Git
history to reproduce them.
