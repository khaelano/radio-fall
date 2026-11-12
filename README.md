# Radio fall detection

Live CSI processing uses a compiled Rust backend with native worker threads and
runtime AVX2 acceleration. A Rust toolchain is required when installing from
source; see [native processing](docs/rust-radio-pipeline.md).

Wi-Fi channel-state-information (CSI) fall-detection research for a bachelor's
thesis. This branch replaces live BLE with scheduled dual-band ESP-NOW uploads:

```text
C5 transmitter -> 5 GHz sensing -> C5 receivers
                                     -> 2.4 GHz ESP-NOW -> C6 gateway -> USB -> laptop
```

The default setup uses four C5 receivers, 120 sensing rounds/s, and 125 ms
round-robin uploads on 2.4 GHz HT20 MCS3. A companion C6 carries transmitter
control and timing over UART and encrypted ESP-NOW to the laptop's USB gateway.
The sensing C5 keeps its radio dedicated to 5 GHz sensing. USB control remains
available with `--transmitter-link usb`.

All operational radio settings are in [`configs/radio.json`](configs/radio.json):
verified identities, sensing profile, upload policy and stable USB paths.
The [configuration guide](docs/radio-configuration.md) explains the defaults and
which edits require provisioning. The [relay procedure](docs/uart-transmitter-relay.md)
records the five-minute hardware qualification and its limits. Historical
recordings and research reports remain on disk.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/firmware/radio/` | ESP-IDF transmitter, receiver, gateway and UART relay projects |
| `src/fall_detection/` | Python package: acquisition, radio processing, collection, evaluation |
| `configs/` | One radio settings file, collection protocols and scenarios |
| `tests/` | Unit tests mirroring the package modules |
| [`docs/`](docs/README.md) | Current guides, engineering reports and presentations |
| `draft/` | Local thesis drafts and exports; ignored by Git |
| `resources/Papers/` | Local, ignored literature library (PDFs plus Markdown conversions) |
| [`tools/`](tools/README.md) | Paper, data, analysis, runtime, and draft tools |
| `data/` | Raw recordings and reusable derived datasets, versioned with DVC |
| `artifacts/notebooks/` | History grouped by notebook and run, tracked by `artifacts/notebooks.dvc` |
| `artifacts/model/` | Latest ONNX bundles by model name, tracked by `artifacts/model.dvc` |
| [`notebooks/`](notebooks/README.md) | Current analysis and experiment notebooks |

## Setup

```sh
uv sync --extra radio
```

## Quick start

The current boards are provisioned and paired. With the gateway connected and
all sensing boards powered, the checked-in configuration supplies the ports
and radio settings:

```sh
uv run csi-viewer
uv run fall-collection
uv run csi-gateway-benchmark
uv run fall-session-inspector --sessions-dir data/raw/sessions
```

Use `--config /path/to/radio.json` for another setup. USB path or reference-link
overrides are available for recovery, for example `csi-viewer --transmitter-link usb`.
For new boards, follow the [gateway build and provisioning procedure](docs/espnow-gateway.md)
and [relay pairing procedure](docs/uart-transmitter-relay.md).
Use `uv run csi-radio discover` to inspect connected boards and
`uv run csi-radio provision --dry-run` to validate the radio settings.

Both live applications use `espnow_gateway`; receiver IDs and model channels
remain stable regardless of USB arrival order. Firmware protocol 3 is required.

The separate experimental detector uses Rust preprocessing and an isolated
three-seed CPU CNN scorer. With an exported four-receiver model available
locally, launch its GUI with:

```sh
uv sync --extra radio --extra detection
.venv/bin/fall-detect --model data/models/phase_random20_v1
```

Add `--headless` for JSON output. The [live detector guide](docs/live-fall-detection.md)
covers model export, read-only replay, timing, quality gating and benchmarks.
The current default uses phase change without fitted normalization, trained on
20 random shifts plus the central window per training attempt. See the
[historical model pilot summary](docs/reports/fall-model-pilots.md).
Live accuracy remains unqualified; the earlier amplitude bundle is preserved.

Optional synchronized phone video is available through a DroidCam USB virtual
webcam. Install with `uv sync --extra radio --extra video` and add
`--video-device /dev/video2` using the actual DroidCam device. Each attempt saves
an MP4 and frame timing sidecars, with no inference model. See
[video recording](docs/video-recording.md) for setup and synchronization limits.

The collector uses the same dashboard as `csi-viewer`, wrapped in a collection
sidebar. Startup first asks for a scenario protocol JSON, unless `--protocol`
supplies one directly. The default `fall_simple.json` has 116 conditions and
232 trials across nine transitions. The next dialog asks for session metadata
and which scenario blocks this session covers; select the blocks you can finish. The operator then sees the live
CSI plots, the scenario queue with per-trial progress, the current scenario and
instruction, the phase countdown, and the collection controls in one window.
Double-clicking any queued trial — or pressing **Details** on the current one —
opens a read-only card with its instruction, phase timings, start and end
direction, safety note, and scenario id.
A second display shows the full-screen performer guidance.

Both live apps share a gateway transport panel with one fixed row per receiver.
It shows host-delivered records/s over the last second, the last reported radio
state, data age, queue occupancy, expiry, dropped records and send errors.
The header shows the requested/applied sensing and backhaul settings plus
reference and gateway freshness. Configured sensing Hz, delivered records/s,
plot refresh FPS and UI FPS are labeled separately. Tooltips retain counters
and explain their limits; sequence gaps alone do not identify a cause.

The separate session inspector scans recorded manifests, then loads CSI and
timing files only when an attempt is selected. It provides searchable session
and trial views, interactive signal plots, exact CSV tables, and reviewed
labels, inclusion, quality, and notes. Review edits are saved to
`session_review.json`; acquisition manifests and raw CSV files remain
unchanged. The inspector can also create a portable curated copy that retains
and flags excluded attempts.
On the **Signals** tab, recorded video plays beside the plots with a shared
attempt-time cursor, scrubbing and frame stepping. Install the `video` extra for
playback. Alignment uses saved host-clock timing; see
[recorded video playback](docs/video-recording.md#recorded-session-playback).

The default `fall_simple.json` uses front, right, back, and left, excluding
backward seated falls. Trials run with a clear floor, chair only, chair and
mattress, then mattress only; chair orientations are grouped across activities.
The earlier eight-direction `fall_v1.json` remains available with 576 trials.
Pass either one with
`--protocol`; see [`configs/collection/README.md`](configs/collection/README.md).

## Band and channel

Edit the `sensing` object in `configs/radio.json`, then provision the C5 boards
before recording with that profile. The current gateway path requires 5 GHz C5
sensing; Indonesia non-DFS channels and 20 MHz bandwidth are validated. The
sensing rate comes from this profile; there is no separate rate override.

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
- `trials/<trial>/attempt_<n>/receivers/<rx>/gateway_timing.jsonl` — mapped sensing
  times, original receiver timestamps, run/boot identities, and uncertainty.
- `transport/gateway/<run-id>/` — raw batch envelopes, clock exchanges, round logs,
  connection/queue events, and immutable availability bins.

The same transmitted frame appears once under every receiver that heard it; do
not merge those rows. Historical USB captures can include ambient traffic; gateway firmware verifies the
sensing transmitter, run, and profile before retaining records. See [`docs/dataset-format.md`](docs/dataset-format.md)
for every field and the exact CSV schemas.

## Firmware

Requires ESP-IDF 6.1 or newer.

The transmitter and receiver build C5 gateway-mode images; the dedicated gateway
builds for C6. Bluetooth is disabled. Use isolated build directories and the
[build and flash instructions](docs/espnow-gateway.md).
The transmitter caps RF power at 11 dBm initially and turns Wi-Fi off while idle
or after host control expires. Actual temperature reduction is unmeasured.

## Tests

```sh
uv run pytest -q      # run the complete test suite
```

## Known limitations

- A production classifier and independent-session evaluation are not implemented.
- Dual-band switching, gateway throughput and four-receiver coverage require hardware qualification.
- Lower transmit power changes link margin; validate it at the intended placements.
- Reset diagnostics distinguish reported reset causes; a lost power supply may
  prevent the board from reporting anything until it is powered again.

## License

Not chosen yet. Add a license before publishing if you intend others to reuse
the code.
