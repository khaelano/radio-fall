# Connectionless wireless transmitter reference

This document describes the deferred direct-C5 BLE experiment. Current operation
uses `configs/radio.json` and the [dedicated C6 UART relay](uart-transmitter-relay.md).
The split-file commands below are historical; their preset filenames have been
removed from the live configuration directory. For deliberate BLE experiments,
copy the single file and set `connection.transmitter_link` to `ble`.


These notes describe the direct-C5 BLE experiment. The separate
[dedicated UART/C6 relay](uart-transmitter-relay.md) carries host communication
on a companion radio and does not resume this BLE design.

Status: deferred at the user's request on 3 November 2026. USB transmitter
control and timing are the active setup. The experimental source, failed-run
journals and firmware snapshots are retained for future investigation; the
wireless reference is not qualified for collection.

The transmitter and gateway were restored from their verified pre-BLE full-flash
backups, including the original factory partition layout. Receiver firmware and
provisioning were untouched. The transmitter retains its four-peer 120 Hz
profile (`8b28a906a0fbcd1f`). CSI delivery still uses receiver-to-gateway ESP-NOW;
USB carries the transmitter reference and gateway output. Experimental flash
snapshots are stored privately under the ignored trial directory's
`restore-usb/`; they contain NVS pairing material and must not be published.

The restored USB setup completed a 5 s warm-up/30 s four-receiver smoke test at
67.90–76.43 valid records/s each, with every delivered record subsecond (largest
receiver p99 768.70 ms) and bounded, stable queues. It did not meet the explicit
80-record/s target; one return interval was classified after deadline. This is
a restoration check, not a repeat of the earlier sustained qualification.
Artifacts are under `restored-usb-four-smoke/` within the trial directory.
Transmitter radio-off and gateway shutdown were verified after the run.

The opt-in wireless reference bridges the laptop's gateway USB connection to
the C5 transmitter using extended, nonconnectable BLE advertisements. Commands,
profile setup, four-timestamp clock exchanges and authoritative sensing logs
use the bridge. CSI envelopes retain the existing receiver-to-gateway ESP-NOW
path. Receiver firmware and inventory ordering do not change. The USB reference
remains the default and recovery option.

Hardware qualification was unsuccessful. Wireless discovery has
worked on the identified C5/C6 pair, including profile commit, reboot and
readback. Initial four-receiver trials stopped on buffer exhaustion or packet
expiry. A later no-receiver preflight carried 1,682 round logs without a bridge
fault, but does not qualify operation during receiver uploads. The successful
USB-reference four-receiver result does not qualify this new mode. Current trials and full-flash backups
are under `data/experiments/gateway/wireless-20261102T125003Z/`.

## Firmware and first setup

Build the transmitter for C5 and the gateway for C6 with their normal target
and board overlays, then `common/sdkconfig.performance160` and
`common/sdkconfig.wireless`. Keep the XIAO C6 built-in antenna board overlay.
Use separate build directories. The wireless image exceeds the historical
1 MiB factory partition and selects ESP-IDF's 1500 KiB single-app layout.
Back up the full flash and verify that NVS remains at `0x9000`, PHY at `0xf000`
and factory app at `0x10000` before flashing the matching partition table and
application. Never use the old app-only flashing procedure for this first
layout transition. A full-flash backup permits restoration of the old layout.

Pair the explicitly identified transmitter and gateway once over USB, with
sensing stopped:

```sh
uv run csi-radio transmitter pair --port <transmitter-usb> \
  --gateway-port <gateway-usb> \
  --receiver-config configs/radio/gateway_inventory.json
```

Pairing validates both board identities, generates a fresh 256-bit shared key,
stores it in their NVS, and reboots them. The key is never printed or written
to experiment journals. A partial pairing must be repeated on both boards.
After pairing, only the gateway needs laptop USB data. The transmitter can use
an independent USB supply.

```sh
uv run csi-radio transmitter status --gateway-port <gateway-usb> \
  --receiver-config configs/radio/gateway_inventory.json

uv run csi-radio transmitter provision --gateway-port <gateway-usb> \
  --receiver-config configs/radio/gateway_inventory.json \
  --radio-profile configs/radio/profiles/indonesia_5g_ch44_120hz.json

uv run csi-gateway-benchmark --transmitter-link ble \
  --gateway-port <gateway-usb> \
  --receiver-config configs/radio/gateway_inventory.json \
  --radio-profile configs/radio/profiles/indonesia_5g_ch44_120hz.json \
  --gateway-config configs/radio/espnow_transport_throughput_mcs3_queue96.json \
  --mode qualify --target-records-s 80 --warmup 30 --seconds 300
```

The viewer and collector accept the same `--transmitter-link ble` and gateway
port options; `--port` is unnecessary in this mode. Start/stop and periodic
clock requests use the same validated transmitter control protocol as USB.
Profile changes are rejected during sensing. An intentional idle profile
commit reboots the transmitter and requires the BLE handshake to complete.

## Protocol and failure handling

`CWL2` (version 2) packets carry a version, direction, persisted boot counter, random boot
nonce, peer nonce echo, sequence, cumulative ACK, four-entry selective ACK mask,
length and at most 1280 payload bytes. A 128-bit truncated HMAC-SHA256 covers
the header and payload. The unique paired key binds the two boards; persisted
boot counters reject earlier sessions and nonce echoes prevent old-boot
commands from executing after restart. Pairing does not create a BLE connection
or GATT service. Payloads are authenticated, not encrypted. The gateway also advertises a periodic control train every 20 ms. The
transmitter establishes periodic synchronization from an authenticated
advertiser report, then cancels ordinary scanning during sensing. Ordinary
scanning resumes while idle so large profile messages remain available.
Gateway control blocks are limited to 190 encoded bytes for one live periodic
HCI update; larger idle setup blocks use ordinary extended advertisements with
an ACK-only periodic packet. Both paths use the same authenticated ARQ stream.
The gateway continues ordinary scanning for the transmitter reference stream.
These are engineering settings under coexistence qualification.

Payloads contain independently encoded blocks of complete typed reference
messages. Logical blocks are bounded at 4096 bytes; a bounded lossless LZ codec
reduces repeated metadata. The packer chooses a complete-frame prefix when a
full compressed block exceeds the 1280-byte wire payload, with a raw fallback.
Decoded message bytes remain unchanged. The receiver validates the restored
block before dispatch; malformed matches and output overrun are rejected.
A four-packet send/receive
window preserves order and suppresses duplicate execution. Selective ACKs
cannot advance past a missing sequence. Outstanding bytes remain immutable;
unacknowledged packets expire at 750 ms and fail the reference. The source
message queue is bounded at 16 KiB.
One dedicated 1536-byte application advertisement buffer isolates application
ownership from controller receive buffers; the synchronous set-data call frees
it before returning. The small NimBLE pool has 48 blocks of 320 bytes; the large
pool has 16 blocks of 1664 bytes. BLE ingress is bounded at four packets on the
transmitter and eight on the gateway. Pre-admission ingress overflow loses an
unaccepted radio datagram and is retried by ARQ; source-log loss remains fatal. Temporary allocation stalls
retry within the same packet lifetime rather than consuming queued bytes.
On controller capacity errors, a small authenticated ACK-only advertisement
replaces cached advertising data before the same pending data is retried; this
does not extend its deadline or acknowledge unaccepted reference messages.
CRC-protected USB types 26/27 multiplex transmitter requests/responses; types
28/29 perform USB-only pairing. These do not reinterpret historical BLE CSI
messages. CSI never traverses this BLE stream.

An extended advertisement can hold more than 31 bytes, but each advertising
data element still has an eight-bit length. A packet is split into bounded
manufacturer-data elements using the experimental company ID `0xffff`, then
reassembled across HCI report fragments before authentication. Malformed,
truncated or unauthenticated advertisements cannot execute commands.

The source's existing round sequence and log-drop checks remain mandatory.
Clock estimates include the wireless round trip; USB arrival is never a sensing
timestamp substitute. BLE mode requires ten seconds between the selected
low-delay clock observations before fitting drift. Until then it uses an
offset-only estimate with the measured uncertainty. This prevents short
preflight queue jitter from becoming a large extrapolated clock-rate error;
it does not establish a hardware drift bound or tight timing accuracy.
Because CSI can arrive before its BLE receiver-status evidence, host ingestion has a bounded 128-envelope/750 ms wait that retains
the original arrival timestamp. Missing evidence or overflow stops the run.
Host USB forwarding failure during an active session also fails the bridge.
The independent three-second transmitter control lease still stops sensing
after control traffic is lost. No new departure is authorized without the
existing sensing-channel return confirmation.

Failures expose `wireless_failure_reason` and `wireless_drops` in device status.
A failed stream requires both bridge endpoints to restart before a new run;
in-run peer restarts are not silently merged into the current recording.
Idle peer reboot after profile setup is handled separately. Hardware throughput,
clock uncertainty, restart and host-disconnect behavior must be measured for
this reference path before it is used for collection.

## Verification status

The host/native suite has 408 passing tests, including the clock-fit regression.
ESP-IDF 6.1 builds pass
for wireless C5 transmitter and C6 gateway, and for USB-reference C5
transmitter, C6 gateway and C5 receiver. These checks do not establish RF
performance. The dedicated native tests exercise loss, reordering, duplicate
suppression, boot epochs, bounded compression and authentication validation.

The 100 Hz profile was committed and read back wirelessly after the intentional
transmitter reboot; the working profile is restored to 120 Hz. The later
four-receiver 5 s warm-up/30 s probe (`pool16-four-probe`) completed
without an in-run bridge fault, but failed delivery rate, queue and timing
criteria. Its startup clock fit was invalid (about -60,086 ppm), so its derived
latency values are unsuitable for a physical latency claim. Raw timestamps are
preserved. A subsequent attempt exposed packet expiry after shutdown; the
latest small-buffer rebalance and clock-fit guard did not complete a new
four-receiver qualification. A 20% transmitter scan trial improved sensing
submission masks but expired the BLE stream. Periodic control synchronized and
both endpoints reported ready, but its first four-receiver probe also stopped
on command timeout with transmitter packet expiry. Its observed buffer-stall
and ingress-overflow counters were zero. Sensing shutdown was verified after
the failure. Sustained four-receiver BLE-reference throughput, latency,
physical transmitter disconnection and fault qualification remain pending.
