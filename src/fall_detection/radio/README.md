# Radio acquisition and visualization

Live acquisition uses `espnow_gateway`: C5 receivers switch between 5 GHz CSI
capture and scheduled 2.4 GHz ESP-NOW uploads to a C6 USB gateway. The transmitter
has a separate USB clock/control link. Both collection and viewer require
`--port`, `--gateway-port`, a schema-v2 inventory, and a 5 GHz profile.

See the [gateway procedure](../../../docs/espnow-gateway.md) for builds, stable
identity provisioning, commands, wire contracts, and staged hardware evaluation.
Historical BLE and USB recordings remain readable. Live BLE discovery and
hardware collection have been retired; no Bluetooth package is required.
