# Radio acquisition and visualization

Live acquisition uses `espnow_gateway`: C5 receivers switch between 5 GHz CSI
capture and scheduled 2.4 GHz ESP-NOW uploads to a C6 USB gateway. The transmitter
uses a companion C6 UART relay for clock/control by default. Viewer, collector,
provisioning and gateway benchmark load `configs/radio.json`; use `--config`
for another setup or `--transmitter-link usb` for USB reference recovery.

See the [gateway procedure](../../../docs/espnow-gateway.md) for builds, stable
identity provisioning, commands, wire contracts, and staged hardware evaluation.
Live BLE discovery, hardware collection, and BLE-specific readers have been
retired; no Bluetooth package is required.

The viewer and collector share acquisition setup, plotting, diagnostics pacing
and display caches. Their **CSI gaps** tab compares all receivers on a common
capture-time heatmap, separating empty intervals from pending buffered delivery.
See [live application organization](../../../docs/live-applications.md)
for module ownership, verification and the synthetic refresh benchmark.

## Modules

Rust owns the live session; this package holds the Python side of it.

| Module | Role |
| --- | --- |
| `settings.py`, `profile.py`, `espnow_config.py` | Load and validate `configs/radio.json` (inventory and profile schema 2, gateway policy version 7); the transport values exist only in that file |
| `live.py`, `state.py` | Start `NativeAcquisition`, deliver accepted records to sinks and display buffers, map native health to diagnostics |
| `records.py`, `native.py` | `NativeRecord` (Rust-backed, live) and `CsiRecord` (pure Python, inspector and tests); access to the compiled backend |
| `buffer.py`, `availability.py`, `gateway_diagnostics.py`, `telemetry.py` | Display buffer, availability snapshots, diagnostics and collection telemetry counters |
| `recording_io.py` | Native bounded recording writer used by the collector |
| `provisioning.py`, `wireless_control.py` | USB discovery and profile provisioning, serial framing, one-time wireless pairing |
| `preprocessing/` | Phase layouts and display preparation |
| `experiments/timing.py` | Conservative grant-timing model cited by a dated report; not part of acquisition |
