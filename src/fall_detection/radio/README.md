# BLE radio acquisition and visualization

This branch acquires receiver CSI through BLE. USB remains for provisioning,
and for transmitter control, round logs, and clock alignment. Live USB CSI
readers and ESP-NOW-to-USB gateway capture have been removed; shared record
and clock decoders remain for historical data analysis.

Follow [BLE setup](../../../docs/ble-transport.md) to flash and provision the
same complete inventory on every board. Sequential provisioning is supported.
C6 or mixed C5/C6 setups use the 2.4 GHz 80 Hz profile. All-C5 setups can also
use 5 GHz. Neither collector nor viewer changes profiles during startup.

```sh
uv run csi-radio-discover --json
uv run csi-radio-provision --sequential \
  --receiver-config data/interim/ble/c6-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json

uv run csi-viewer --port /dev/ttyACM0 \
  --receiver-config data/interim/ble/c6-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --receiver-id rx-1
```

Replace the inventory path and transmitter port with the actual setup. Keep
transmitter USB data connected; receivers need only power during BLE collection.
BLE is the default and sole acquisition choice in the collector and viewer.
The receiver selector changes the preview without merging receiver streams.

The host verifies MAC, compiled target, radio/policy fingerprints, ordered
inventory CRC, run and boot identities, batch lengths and CRCs. Each receiver
has an independent connection, queue, and missingness state. Collection requires
four verified receivers. Hardware benchmarks report observed delivery and
missingness separately from synthetic replay or classifier results.
