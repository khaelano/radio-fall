# Radio fall detection

Wi-Fi channel-state-information (CSI) fall-detection research for a bachelor's
thesis. This `wifi-bt` branch carries receiver CSI over BLE. USB remains for
provisioning and the transmitter's control, round logs, and clock reference.
USB CSI streaming is maintained on a separate branch.

The transmitter and one to four ESP32-C5/C6 receivers use ESP-NOW HE20 MCS0.
Round robin is the default upload scheduler; random grants are experimental.
The initial sensing rate is 80 Hz. C6 or mixed inventories require 2.4 GHz;
5 GHz requires C5 on every board. Four receivers are required for collection.

```text
USB control/timing <-> transmitter -> Wi-Fi sensing -> receivers -> BLE -> laptop
```

Acquisition, recording, operator labels, and historical-session inspection are
implemented. BLE throughput, coverage, thermal behavior, and a production fall
classifier remain under evaluation. Earlier USB results are not BLE benchmarks.
The [initial C6 hardware test](docs/ble-c6-quality-2026-11-01.md) verified recorded
bytes but found excessive delivery latency under the current grant/deadline settings.

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

Build and provision all boards using the [BLE setup procedure](docs/ble-transport.md).
The same complete inventory must be provisioned on every board. Sequential
provisioning is supported. Then keep the transmitter on USB data and power the
receivers independently. Replace the inventory and port below with your setup:

```sh
uv run csi-viewer --port /dev/ttyACM0 \
  --receiver-config data/interim/ble/c6-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json

uv run fall-collection --port /dev/ttyACM0 \
  --receiver-config data/interim/ble/c6-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --protocol configs/collection/fall_v1.json \
  --output-dir data/raw/sessions

uv run fall-session-inspector --sessions-dir data/raw/sessions
```

Both acquisition applications use BLE by default and verify identities,
configuration fingerprints, decoding, and the USB transmitter reference.
They do not connect to receiver USB ports or silently change provisioned profiles.

The collector uses the same dashboard as `csi-viewer`, wrapped in a collection
sidebar. The start dialog asks for session metadata and which scenario blocks
this session covers; the full protocol expands to 576 trials, so a session
usually selects only the blocks it can finish. The operator then sees the live
CSI plots, the scenario queue with per-trial progress, the current scenario and
instruction, the phase countdown, and the collection controls in one window.
Double-clicking any queued trial — or pressing **Details** on the current one —
opens a read-only card with its instruction, phase timings, start and end
direction, safety note, and scenario id.
A second display shows the full-screen performer guidance.

The separate session inspector scans recorded manifests, then loads CSI and
timing files only when an attempt is selected. It provides searchable session
and trial views, interactive signal plots, exact CSV tables, and reviewed
labels, inclusion, quality, and notes. Review edits are saved to
`session_review.json`; acquisition manifests and raw CSV files remain
unchanged. The inspector can also create a portable curated copy that retains
and flags excluded attempts.

Two protocols are available. `fall_v1.json` samples all eight directions
(cardinals plus diagonals) for 576 trials; `fall_simple.json` samples only
front, left, right, and back for 160 trials. Pass either one with
`--protocol`; see [`configs/collection/README.md`](configs/collection/README.md).

## Band and channel

Profiles live in `configs/radio/profiles/`:

- `indonesia_2g_ch6_80hz.json` — 2.4 GHz, channel 6, 80 Hz
- `indonesia_5g_ch44_80hz.json` — 5 GHz, channel 44, 80 Hz

Copy one, change `profile_id`, `band`, and `channel`, and pass it to the
provisioner and then the viewer or collector. The Indonesia country table is enforced: 2.4 GHz channels
1–13 and non-DFS 5 GHz channels only. Bandwidth is fixed at 20 MHz.

## Recording format

Each session writes one directory under `data/raw/sessions/<session-id>/`:

- `session.json` — session identity, protocol hash, radio environment, status.
- `protocol.json` — pinned protocol snapshot used for the trial queue.
- `events.jsonl` — append-only phase and operator events.
- `trials/<trial>/attempt_<n>/attempt.json` — attempt disposition and telemetry.
- `trials/<trial>/attempt_<n>/receivers/<rx>/csi.csv` — one row per sensing
  frame for that receiver.
- `trials/<trial>/attempt_<n>/receivers/<rx>/radio_timing.csv` — timing row for
  each CSI row.
- `trials/<trial>/attempt_<n>/receivers/<rx>/ble_timing.jsonl` — mapped sensing
  times, original receiver timestamps, run/boot identities, and uncertainty.
- `transport/ble/<run-id>/` — raw batch envelopes, clock exchanges, round logs,
  connection/queue events, and immutable availability bins.

The same transmitted frame appears once under every receiver that heard it; do
not merge those rows. Historical USB captures can include ambient traffic; BLE firmware verifies the
sensing transmitter, run, and profile before retaining records. See [`docs/dataset-format.md`](docs/dataset-format.md)
for every field and the exact CSV schemas.

## Firmware

Requires ESP-IDF 6.1 or newer.

Both firmware projects build BLE-mode images by default. Use an explicit target
and isolated configuration/build directory; see [build and flash instructions](docs/ble-transport.md#firmware-and-board-setup).
The transmitter caps RF power at 11 dBm initially and turns Wi-Fi off while idle
or after host control expires. Actual temperature reduction is unmeasured.

## Tests

```sh
uv run pytest -q      # run the complete test suite
```

## Known limitations

- A production classifier and independent-session evaluation are not implemented.
- BLE RF throughput and joint coverage with four receivers require hardware tests.
- Lower transmit power changes link margin; validate it at the intended placements.
- Reset diagnostics distinguish reported reset causes; a lost power supply may
  prevent the board from reporting anything until it is powered again.

## License

Not chosen yet. Add a license before publishing if you intend others to reuse
the code.
