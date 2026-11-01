# Radio configuration

`receivers.json` is the versioned physical inventory. It must be populated
with the actual MAC addresses and placements discovered from the boards before
collecting data. Selectable on-air settings live in `profiles/`; provisioning
one profile writes it to every connected board's NVS before collection.

The repository profiles use the Indonesia (`ID`) regulatory domain, 20 MHz
bandwidth, and a configurable integer 50–100 Hz sensing rate. The 5 GHz profile intentionally
uses a non-DFS channel. A 5 GHz session requires ESP32-C5 for the transmitter
and every receiver; 2.4 GHz sessions may mix ESP32-C5 and ESP32-C6 boards.

For provisioning, connect boards through native USB Serial/JTAG. During
collection receivers send CSI over BLE and need only power; the transmitter
retains its USB data connection for control and timing. `/dev/ttyACM*` names are intentionally not stored here: the
collector binds each link by the firmware-reported MAC and stable device ID.
Provisioning can instead use one USB-connected board at a time with
`csi-radio-provision --sequential`. Every invocation must use the same complete
inventory and radio profile, including all disconnected receivers in slot order.
Discover all identities before starting that provisioning pass.

The BLE starting profile for C6 or mixed C5/C6 boards is
`profiles/indonesia_2g_ch6_80hz.json`. All-C5 setups can also use
`profiles/indonesia_5g_ch44_80hz.json`.
`ble_transport.json` contains the separate round-robin transport policy.
See [BLE transport](../../docs/ble-transport.md) for provisioning, fixed slot
order, queue limits, experimental random scheduling, and measured benchmarks.
