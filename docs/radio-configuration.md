# Radio configuration

Edit `configs/radio.json` to configure the current sensing setup. All operational
radio commands use this file by default, including when launched outside the
repository. Pass `--config /path/to/radio.json` to select another complete file.
A missing or invalid file fails before acquisition starts; there is no silent
fallback to another radio policy.

| Section | Purpose | Current setting |
| --- | --- | --- |
| `connection` | Host ports and transmitter reference | C6 UART relay (`espnow_uart`), stable USB by-id paths |
| `inventory` | Verified boards, ordered receivers, placements | One C5 transmitter, four C5 receivers, one C6 gateway |
| `sensing` | Provisioned sensing profile | Indonesia, 5 GHz channel 44, HE20, 120 rounds/s |
| `transport` | Per-run receiver upload and availability policy | Channel 11, HT20 MCS3, 125 ms slots, 96-record queues, 750 ms retention |

The transport has four outstanding batches, 64 records per turn and no
application ACKs or retries. It retains MAC feedback, integrity checks and the
channel-return interlock. The reference relay independently uses MCS0. These
queue, PHY and slot settings come from the earlier five-minute relay
qualification. Channel 11 replaces channel 6 after the interactive backlog
investigation found co-channel traffic and RF timeouts. A five-minute receiver/
tab-switching viewer run passed on channel 11; camera load and other placements
remain unqualified. See [the backlog investigation](reports/gateway-preview-backlog-2026-11-03.md).
These results do not establish reliability at every placement. See [measured results and limits](uart-transmitter-relay.md#verification).

The `connection.gateway_port` identifies the laptop gateway. The
`transmitter_port` supports USB recovery; `companion_port` is used only for
initial relay pairing. Acquisition uses the gateway alone with `espnow_uart`.
These paths are specific to the verified boards on Linux; update them on a
different laptop. Explicit `--gateway-port`, `--port` and `--transmitter-link`
arguments override file values for one command. For example:

```sh
uv run csi-viewer
uv run fall-collection
uv run csi-gateway-benchmark
uv run csi-radio transmitter status
uv run csi-radio provision --dry-run

# USB reference recovery, using the configured C5 USB path:
uv run csi-viewer --transmitter-link usb
```

The host accepts gateway transport policy version 7 and operational inventory
and sensing-profile schema 2 only. Older versions are rejected before hardware
is opened.

## Applying changes

Changes to the sensing profile require provisioning all C5 sensing boards before
acquisition. Changes to receiver identities/order require provisioning the
transmitter's complete roster as well. Connect boards one at a time and run
`csi-radio provision --sequential` with the same file throughout the pass. The
C6 gateway receives its upload configuration automatically at each run.

Changing the backhaul channel also requires pairing both C6 endpoints on that
channel while sensing is stopped: `csi-radio transmitter pair`. Pairing uses
the configured companion and gateway USB ports, verifies their identities and
stores keys only in board NVS. Do not put keys in the JSON file. The already
paired setup does not need pairing or reprovisioning for this consolidation.

USB paths and the choice of host reference do not change sensing or transport
fingerprints. The current sensing fingerprint remains `8b28a906a0fbcd1f`.
Recordings pin the resolved inventory, profile and transport settings rather
than relying on the mutable configuration path. Unknown fields and incompatible
radio/transport settings are rejected. Collection requires four registered C5
receivers; viewer/probe mode can use one to four.

## Defaults and retained experiment definitions

The JSON contains setup-specific values. Omitted optional transport fields keep
the existing versioned protocol defaults: no early return, no minimum revisit,
10 ms send guard and no bitmap ACKs. The file explicitly selects the tested
policy rather than changing defaults in legacy wire-contract constructors.
The benchmark defaults to a 30 s warm-up, 300 s measurement and an 80-record/s
per-receiver target. The viewer and collector use the profile's sensing rate;
there is no independent `--nominal-rate-hz` setting to contradict it.

Output folders, UI controls, optional camera settings and protocol selection
remain command options with their existing defaults. Collection protocols and
scenario manifests under `configs/collection/` define activity labels, trial
counts and cues, so they remain separate experiment definitions. The collector
opens a scenario-file picker at startup, initially pointing to `fall_simple.json`
(the four-direction, nine-transition protocol with 232 trials). Pass
`--protocol configs/collection/fall_simple.json` to skip the picker.

The old radio inventories, profiles, BLE policy and ESP-NOW trial presets were
removed from `configs/radio/`. Historical reports retain the original filenames;
recorded manifests and Git history preserve the original values. Historical
split-file CLI flags remain accepted but hidden from help, and cannot be mixed
with `--config`. New commands should use the single file. Raw recordings and
firmware build overlays are unchanged; ESP-IDF build settings describe compiled
hardware capabilities and are not host runtime radio presets.
