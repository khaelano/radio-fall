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
