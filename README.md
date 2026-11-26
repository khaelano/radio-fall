# Radio fall detection

Bachelor's thesis project: detecting falls from Wi-Fi channel state
information (CSI) recorded with ESP32-C5 radios. Three desktop commands cover
the daily work:

| Command | Use it to |
| --- | --- |
| `csi-radio` | check that the radio boards are connected and configured |
| `csi-live` | watch live CSI and, optionally, detect falls with a trained model |
| `csi-sessions` | record new collection sessions and review recorded ones |

The hardware: a C5 transmitter sends 5 GHz sensing packets to four C5
receivers; the receivers upload over 2.4 GHz ESP-NOW to a C6 gateway, which is
the only board plugged into the laptop.

```text
C5 transmitter ──5 GHz──> 4 × C5 receiver ──ESP-NOW──> C6 gateway ──USB──> laptop
```

## Install

You need [uv](https://docs.astral.sh/uv/) and a Rust toolchain (1.92 or newer);
the Rust part is compiled during installation. Choose what to install:

| To | Run |
| --- | --- |
| use the three commands | `uv sync --extra radio` |
| also detect falls live | `uv sync --extra radio --extra detect` |
| also run the analysis notebooks (NVIDIA GPU) | `uv sync --extra analysis --extra radio --extra cuda` |

`uv sync` installs exactly the extras you list, so name all of them each time.

Recordings and trained models are stored with DVC, not Git. With access to the
project's DVC remote, fetch what you need:

```sh
uv run dvc pull artifacts/model.dvc   # trained models, needed for detection
uv run dvc pull data/raw.dvc          # recorded sessions
```

## Use it

The boards listed in [`configs/radio.json`](configs/radio.json) are already
set up. Plug the C6 gateway into the laptop, and power the transmitter, its
companion C6 relay and the four receivers.

### 1. Check the radios

```sh
uv run csi-radio
```

It lists every configured board, shows which ones are connected and whether
they store the current settings, and ends with what to do next. If it tells
you to, run `uv run csi-radio provision` and follow the prompts.

### 2. Watch live data and detect falls

```sh
uv run csi-live
```

The window opens on the live CSI plots. To detect falls, open the **Model**
menu in the toolbar, tick a model (`tonepool_tcn-4s` is the default choice)
and press **Start detection**. Choose **None — view live data only** and press
**Switch to live view** to go back. Before relying on the alarms, calibrate
them with the person being monitored; see the
[detector guide](docs/live-fall-detection.md#installation-calibration).

### 3. Record a session

```sh
uv run csi-sessions
```

1. Press **New session**, fill in the form (protocol, participant ID, which
   scenario blocks, optional camera) and press **Start recording**.
2. The collection console opens; the performer's instructions appear
   full-screen on a second display, if one is connected.
3. For each trial: press **Start trial**, press **Confirm action** once the
   performer has done the movement (before the action countdown ends, or the
   attempt is invalid), then **Accept**, **Retry** or **Skip**.
4. Between trials, **Edit…** above the queue lets you reorder, remove, add or
   relabel the trials not yet recorded.
5. Close the console to finish. The recording is saved to
   `data/raw/sessions/` and the session list returns with it selected.

To continue an interrupted session, select its folder in the list and press
**Resume recording**.

### 4. Review a session

In `csi-sessions`, select a session, then an attempt in the table. The
**Signals** tab plots its CSI (with the video, if one was recorded), and the
**Attempt review** tab sets its label, inclusion, quality and notes. Press
**Save review**; reviews go to `data/annotations/` and never change the
recording. **Export curated bundle…** writes a reviewed copy.

### Without hardware

```sh
uv run csi-radio check                 # validate configs/radio.json
uv run csi-sessions                    # browse and review recorded sessions
uv run dvc pull data/experiments/detector/native-capture-20261112-c.dvc
uv run csi-live --backend cpu \
  --replay-capture data/experiments/detector/native-capture-20261112-c
```

The last command replays a recorded capture through the detector. Use
`--backend cpu` on machines without an AMD GPU.

Every command accepts `--help` with examples, `--config <file>` for another
radio setup and `--gateway-port <path>` for another USB path.

## Where things are

| Path | Contents |
| --- | --- |
| `configs/radio.json` | radio boards, sensing settings and USB ports |
| `configs/collection/` | collection protocols (`fall_simple.json` is the default) |
| `data/raw/sessions/` | recorded sessions (DVC) |
| `data/annotations/` | session reviews (Git) |
| `artifacts/model/` | trained models used for live detection (DVC) |
| `notebooks/latest/` | preprocessing, training and comparison notebooks |
| `src/fall_detection/` | Python package: the commands, collection and analysis |
| `src/native/radio_core/` | Rust: radio acquisition, signal processing, live inference |
| `src/firmware/radio/` | ESP-IDF firmware for the boards |
| `docs/` | guides and dated reports ([index](docs/README.md)) |

## More guides

- **Changing radio settings** (channel, boards, ports):
  [radio configuration](docs/radio-configuration.md).
- **New boards or firmware** (ESP-IDF 6.1 or newer):
  [gateway build and provisioning](docs/espnow-gateway.md),
  [relay pairing](docs/uart-transmitter-relay.md),
  [firmware notes](src/firmware/radio/README.md).
- **Recording**: [collection guide](src/fall_detection/collection/README.md),
  [protocols](configs/collection/README.md),
  [video recording](docs/video-recording.md).
- **Detection**: [live detector guide](docs/live-fall-detection.md).
- **Data**: [dataset format](docs/dataset-format.md).
- **Analysis and training**: [notebooks](notebooks/README.md), run in order
  `02_preprocess` → `03_training` → `04`/`05` baselines → `06` comparison.
- **Current state and open questions**: [project knowledge](docs/project-knowledge.md).

## Development

```sh
uv run pytest -q                       # full test suite
uv run ruff format <files>             # format
uv run ruff check <files>              # lint
```

Contribution rules are in [`AGENTS.md`](AGENTS.md); the Rust workspace is
described in [native processing](docs/rust-radio-pipeline.md).

## Limitations

- Live detection accuracy, false alarms per hour and alarm latency are not
  qualified. The models were trained on two participants' sessions and one
  hour of continuous non-fall data, all in one room.
- Gateway throughput and four-receiver coverage need further hardware
  qualification at the intended placements.
- The combined `csi-live` and `csi-sessions` windows and protocol editing are
  tested offline; they have not yet been used with the radio hardware.

## License

Not chosen yet. Add a license before publishing if you intend others to reuse
the code.
