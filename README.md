# Radio fall detection

Wi-Fi 6 channel-state-information (CSI) fall-detection prototype for a
bachelor's thesis. One ESP32-C5 transmitter and two ESP32-C5 receivers stream
CSI over USB to a laptop.

**Status:** acquisition, recording, and the live viewer work end to end on both
2.4 GHz and 5 GHz. The detection model itself is not implemented yet — the
repository currently produces clean CSI datasets plus an operator-confirmed
labelling workflow.

## How it works

```text
ESP32-C5 TX ── ESP-NOW, HE20/MCS0, 100 Hz per receiver ──> ESP32-C5 RX-1 ──USB──┐
                                                             ESP32-C5 RX-2 ──USB──┴──> laptop
```

- The transmitter sends unicast ESP-NOW frames at 100 Hz to each receiver,
  pinned to 802.11ax HE20, MCS0, long guard interval.
- Each receiver captures CSI from the HE-LTF and streams COBS/CRC-framed
  binary batches over native USB Serial/JTAG.
- The host binds receivers by MAC, checks the profile fingerprint,
  de-duplicates the two captures each frame produces, and records one CSV row
  per sensing frame.

## Hardware

- 3× ESP32-C5 (dual-band Wi-Fi 6). ESP32-C6 works too, but 2.4 GHz only.
- Powered USB hub, laptop.
- Optional: MR60FDA2 radar for comparison experiments.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/firmware/radio/` | ESP-IDF transmitter and receiver projects |
| `src/fall_detection/` | Python package: acquisition, radio processing, collection, evaluation |
| `configs/` | Radio profiles, receiver inventory, collection protocol and scenarios |
| `tests/` | Unit tests mirroring the package modules |
| `docs/` | Procedures, notes, figures, presentations |
| `draft/` | Thesis chapters |
| `Resources/Papers/` | Literature library (PDFs plus Markdown conversions) |
| `tools/` | Paper conversion, RAG index, draft builders |
| `data/` | Raw recordings and derived datasets (not versioned) |

## Setup

```sh
uv sync --extra radio
```

## Quick start

```sh
# 1. Confirm the boards are visible
uv run csi-radio-discover

# 2. Live CSI viewer
uv run csi-viewer \
  --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json \
  --fps 24

# 3. Record an operator-confirmed session
uv run fall-collection \
  --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json \
  --protocol configs/collection/fall_v1.json \
  --output-dir data/raw/sessions
```

Both applications reconcile the connected boards at startup: if a board is
still on another band or channel, its profile is applied live (no reflash, no
reboot) before binding.

## Band and channel

Profiles live in `configs/radio/profiles/`:

- `indonesia_2g_ch6.json` — 2.4 GHz, channel 6
- `indonesia_5g_ch36.json` — 5 GHz, channel 36

Copy one, change `profile_id`, `band`, and `channel`, and pass it to the
viewer or collector. The Indonesia country table is enforced: 2.4 GHz channels
1–13 and non-DFS 5 GHz channels only. Bandwidth is fixed at 20 MHz.

## Recording format

Each session writes one directory per receiver under
`data/raw/sessions/<timestamp>/`:

- `csi_<timestamp>.csv` — one row per sensing frame: source MAC, RSSI, channel,
  radio and host timestamps, then the CSI values.
- `radio_timing_<timestamp>.csv` — sequence and timing columns.

Captured frames from other networks are included, so filter on the transmitter
MAC if you need only the sensing link.

## Firmware

Requires ESP-IDF 6.1 or newer.

```sh
cd src/firmware/radio/transmitter && idf.py set-target esp32c5 && idf.py build
cd ../receiver && idf.py set-target esp32c5 && idf.py build
idf.py -p /dev/ttyACM0 flash     # transmitter
idf.py -p /dev/ttyACM1 flash     # receiver
```

See [the firmware notes](src/firmware/radio/README.md) for details.

## Tests

```sh
uv run pytest -q      # 155 tests
```

## Known limitations

- The classifier and evaluation stages are not implemented.
- About 2% of frames are lost, plus occasional USB batch gaps.
- CSI currently also captures ambient traffic; rows are tagged with the source
  MAC rather than filtered on the device.
- Switching band costs roughly half a second of stream gap while the radio
  restarts.

## License

Not chosen yet. Add a license before publishing if you intend others to reuse
the code.
