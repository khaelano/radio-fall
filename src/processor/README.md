# Processor-side CSI collector

This project uses [uv](https://docs.astral.sh/uv/) for environments,
dependency resolution, installs, and test runs. From this directory, sync the
locked environment:

```sh
cd src/processor
uv sync
```

Launch the live viewer with the receiver's USB serial port:

```sh
uv run csi-viewer \
  --port /dev/ttyUSB1 \
  --baud 921600 \
  --output-dir ../../data/raw
```

The dashboard defaults to twelve representative physical subcarriers. Use
`--dashboard-subcarriers 8`, `12`, or `16` to change that count, and
`--inspect-subcarrier K` to choose the physical subcarrier shown in the detail
trace. The detail tab displays all 64 HT20 slots as a phase heatmap, including
blank guard/DC slots, plus the selected trace.

Run the headless rendering benchmark after GUI changes:

```sh
QT_QPA_PLATFORM=offscreen uv run -m radio_processor.gui.benchmark \
  --view both --frames 120 --points 300
```

Run the processor tests from the repository root:

```sh
uv run --project src/processor pytest -q
```

The viewer records valid `CSI_DATA` lines and displays four synchronized
dashboard views for representative physical subcarriers: CSI amplitude, phase,
I/Q components, and receiver radio levels (RSSI/noise floor). The detail tab
uses one full-band phase heatmap and one selected-subcarrier trace instead of
one graphics plot per subcarrier. Every panel uses a fixed ten-second x-axis
whose newest sample is at zero, so the chart does not grow as the session runs.
It keeps the GUI running across malformed records or temporary serial
disconnects, distinguishes an open port that is still waiting for CSI from a
live stream, retains recent firmware diagnostics, unwraps the ESP32's 32-bit
microsecond timestamp, and records the raw CSV stream. Only the active tab is
redrawn, and unchanged CSI sequences are skipped.
