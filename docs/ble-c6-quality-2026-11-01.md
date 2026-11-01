# XIAO ESP32-C6 BLE quality test, 1 November 2026

The corrected firmware transfers valid CSI over BLE, but the tested settings
do not provide timely input for the current 50 Hz grid and its bin-end + 100 ms
deadline. This is a measured one-receiver result, not a four-receiver qualification
or a fall-detection evaluation.

## Conditions

- One Seeed XIAO ESP32-C6 transmitter and receiver `rx-4`, about 50 cm apart
  according to the operator. Both were powered by laptop USB during this test.
  Receiver CSI used BLE; receiver USB was not a CSI transport.
- The transmitter selected its attached external antenna; the receiver selected
  its built-in ceramic antenna. GPIO3 enables the XIAO RF switch and GPIO14
  selects the antenna. The receiver does not require an external antenna in
  this mode; see [Seeed's hardware guide](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/#hardware-overview).
- HE20 MCS0, 2.4 GHz channel 6, 80 rounds/s, 11 dBm transmit-power limit.
  The complete four-receiver inventory and round-robin grants remained fixed;
  only `rx-4` was discovered over BLE. The other three slots stayed missing.
- BLE negotiated LE 2M, MTU 247, data length 251, 12.5 ms connection interval,
  peripheral latency 0, and 2 s supervision timeout.
- A 30-second warm-up preceded a 300.000-second measurement. No firmware builds
  or test-suite runs were performed during that measurement. The laptop's Wi-Fi
  was observed at 2437 MHz/channel 6 immediately afterward; its contribution was
  not isolated. No controlled movement, temperature, or supply-voltage measurement
  was performed. Hub-powered receiver behavior was not tested in this condition.

## Measurements

| Receiver 4 metric | Result |
| --- | ---: |
| Capture rate from firmware status span | 61.36 records/s |
| Delivered records in measurement interval | 7,044 |
| Delivered rate | 23.48 records/s |
| Timely records | 2 |
| Timely rate | 0.0067 records/s |
| Delivery latency, median / p95 / p99 | 262.06 / 309.71 / 335.11 ms |
| Longest missing run for timely input | 171.66 s |
| Receiver restart observed | No |
| Firmware record expirations in status span | 17,057 |
| Application retransmissions in status span | 64 |
| Host partial-batch evictions / expirations | 2,451 / 1,335 |
| Host notification queue drops | 0 |
| Minimum reported free heap | 26,148 bytes |

Firmware counter deltas cover a 298.912-second status-snapshot span, rather
than the exact measurement boundaries. Expiry releases application ownership;
data already queued in the BLE stack can still arrive later. Expired and
delivered counts must not be added as disjoint loss categories.

## Recorded-byte and signal checks

The full journal contained 3,820 CRC-verified envelopes and 7,629 raw records,
including warm-up/drain records. All 7,044 measurement records were present in
the raw journal. Their sensing sequences and enqueue timestamps matched the
authoritative transmitter round logs; no metadata mismatch was found.

All measurement records reported HE format 4 with 512 CSI bytes/256 complex
slots, a supported layout. Of the structurally eligible phase slots, 99.9973%
met the existing amplitude-floor criterion of 4; no eligible I/Q component was
at an int8 encoding limit. All 7,044 raw CSI contents were distinct. These checks
do not establish motion sensitivity, calibrated RF accuracy, or model accuracy.

The driver reported median RSSI -64 dBm and noise floor -99 dBm. Seven records
had nonzero `rx_state=65`; the remaining 7,037 had state 0. Preserve and inspect
those flags when deriving model inputs rather than treating every retained
record as equally valid. Median clock-fit uncertainty was 390 microseconds.
Delivery latency is measured from mapped transmitter enqueue time, not exact
over-air transmission time.

## Fixes and remaining limits

Hardware discovery identified the XIAO antenna switch requirement. Earlier
antenna conditions changed during debugging, so the early HE20/HT20 probes are
not a controlled PHY comparison. Normal HE20 was restored before this condition.

The hardware tests also exposed a raw-ROM statistics writer corrupting USB
reference framing, unreachable-peer queue starvation, inconsistent callback
metadata, and BLE backlog. The current implementation frames all reference
telemetry, bounds per-peer pending sends/retry spacing, uses sensing-header v3
CRC32 and a metadata snapshot, wakes the upload task on BLE completion, uses
write-command ACKs, counts bounded partial replacement, and limits Wi-Fi RX
buffers to preserve BLE heap headroom. Despite these changes, delivery under
the tested grant/queue/deadline settings remains inadequate for timely input.

An earlier 58.1-second idle check received all 30 status replies from each board
without an uptime reset; the transmitter radio stayed off. No cause was
established for the operator's reports of boards turning off on the wall-powered
hub. Antenna configuration explains missing RF communication, not disappearance
of a correctly powered USB device. Actual temperature reduction is unmeasured.

Next hardware work should validate the remaining receivers with the XIAO/v3
image, then separate host Wi-Fi coexistence from grant/queue limits in controlled
comparisons. Keep round robin as the default. Further tuning must be benchmarked;
missingness-aware training does not recover samples that miss finalized bins.

## Artifacts

Raw and derived artifacts are kept locally under
`data/experiments/ble/c6-xiao-he20-rx4-quality-5min-20261101/`:

- `quality-report.json`: extended transport, integrity, and signal summary.
- `firmware-config.json`: selected build settings and binary SHA256 hashes.
- `host-radio-context.json`: observed host Wi-Fi frequency.
- `ble-fac333ca56fb54c0/transport/ble/fac333ca56fb54c0/`: immutable envelopes,
  event journal, manifest, finalized availability bins, and original benchmark.

Recompute the extended summary with `csi-ble-benchmark report RUN_DIRECTORY
--signal-quality`. Earlier smoke/probe directories remain separate and retain
their original failures; raw recordings were not rewritten.
