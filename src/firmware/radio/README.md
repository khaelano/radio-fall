# Scheduled dual-band CSI firmware

Build C5 transmitter/receiver and C6 gateway firmware with ESP-IDF 6.1 using the
[gateway procedure](../../../docs/espnow-gateway.md). Bluetooth is disabled.
Images report protocol 3 and sensing version 4. Use isolated build/config paths;
old BLE binaries are incompatible with live gateway acquisition. Historical BLE
control sources remain only as offline regression fixtures.

## Board setup

C5 boards perform 5 GHz sensing; the C6 stays on the fixed 2.4 GHz upload channel.
On a XIAO C6 gateway, select the shared XIAO board overlay. GPIO3 low enables its
RF switch, and GPIO14 low selects the built-in antenna. The external-antenna
option requires an attached external antenna. See the gateway procedure for the
exact overlay/build command and verified-identity provisioning.

## Power and timing

Defaults retain an 80 MHz CPU cap and dynamic frequency scaling initialization.
The transmitter initially caps Wi-Fi transmit power at 44 quarter-dBm (11 dBm),
reports the quantized setting, and stops Wi-Fi while idle or when its three-second
host-control lease expires. Automatic light sleep is not enabled. Power and
temperature improvements remain unmeasured; lower transmit power can affect link
margin and CSI delivery.

The transmitter continues sensing while one receiver has an upload grant.
Receivers use dual-band mode without AP association, own bounded record pools,
and return to sensing independently of application ACKs. The transmitter waits
for explicit 5 GHz return confirmation before the next departure. Actual round
submissions, skipped rounds, grants and return statuses are recorded. An accepted
ESP-NOW submission is not evidence of delivery to the processor.

## Upload experiments

The receiver's `CONFIG_CSI_GATEWAY_EVENT_UPLOAD` is disabled by default. It
uses nonblocking upload submissions and task notifications while preserving
single-send ownership and the existing return cutoff. USB status reports
`upload_worker: event` or `legacy`.

The gateway's `CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS` defaults to 50 ms. A shorter
value limits immediate host-ACK forwarding by age of receiver activity; skipped
ACKs remain cached for receiver polling. This is an activity heuristic, not a
verified channel lease. The selected window and diagnostic counters appear in
gateway status. Reconfigure cached build directories after adding Kconfig
options. See [measured burst/ACK results](../../../docs/espnow-burst-ack-2026-11-02.md)
before selecting experimental firmware. No change is enabled by default.

## Reset and USB diagnostics

C5 discovery reports reset reason, uptime, radio state and profile. Gateway boot
identity changes identify a restart; disappearance alone cannot distinguish reset,
lost power, USB disconnection or disabled USB. A board cannot report while its
supply is absent. Check a power bank's low-current cutoff with the actual load;
do not infer overheating or shutdown from an LED alone.

If the C6 disappears, check kernel USB enumeration before the serial reader.
Bootloader mode bypasses the application: hold BOOT and tap RESET. Use a known
working data cable and host port. A cable/path recovery does not prove which
original component failed. Keep these observations separate from transport
throughput or detector claims.

### Opt-in throughput builds

The normal 80 MHz/DFS configuration and legacy upload worker remain defaults.
`receiver/sdkconfig.event_upload` enables nonblocking uploads with bounded MAC
completion wakeups. `common/sdkconfig.performance160` selects fixed 160 MHz CPU
operation and disables DFS for a controlled CPU-policy trial. Use separate build
and SDK configuration paths; changing a defaults file does not override an
existing cached SDK configuration automatically. For example, from the repo root:

```sh
idf.py -C src/firmware/radio/receiver -B /tmp/csi-rx-fast \
  -DIDF_TARGET=esp32c5 -DSDKCONFIG=/tmp/csi-rx-fast/sdkconfig \
  -D"SDKCONFIG_DEFAULTS=$PWD/src/firmware/radio/receiver/sdkconfig.defaults;$PWD/src/firmware/radio/receiver/sdkconfig.defaults.esp32c5;$PWD/src/firmware/radio/receiver/sdkconfig.event_upload;$PWD/src/firmware/radio/common/sdkconfig.performance160" build
```

The transmitter and gateway can use the same CPU overlay without the receiver
worker overlay. Preserve the XIAO C6 antenna defaults when building for that
identified board. Device status reports `cpu_max_mhz`, receiver worker mode and
maximum transport version; the gateway also reports negotiated `backhaul_mcs`.
CGCF-v6 selects HT20 MCS0–3 without changing the HE20 MCS0 sensing link. The
explicit 120 Hz profile requires updated C5 firmware and profile schema v2;
restore an 80 Hz profile before returning to older application binaries.
See [throughput experiments](../../../docs/espnow-throughput-2026-11-02.md) for
measurements and qualification limits. Builds and single-receiver probes do not
qualify four receivers or detector accuracy.

CGCF-v7 optionally increases active CSI storage to 96 records for the explicit
120 Hz/750 ms retention experiment; normal policies still use 64. Receiver and
transmitter control queues retain 32 entries with maximum payloads of 180 and
96 bytes respectively. Gateway data ingress remains 1400 bytes. These role
limits save more receiver RAM than the extra 32 record slots consume. Oversized
control messages are counted and rejected; CSI data and envelope encoding are
unchanged. All roles must advertise v7 support before using the 96-slot policy.
