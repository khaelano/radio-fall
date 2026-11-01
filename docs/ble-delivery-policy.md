# Experimental BLE admission and host-receipt credits

This revision separates pending-record freshness, started-batch lifetime, and
downstream transmission debt. It is opt-in through `BleTimingExperiment.delivery`;
normal collection rejects experimental configurations. Existing collection and
CBLC v2 configuration fingerprints remain unchanged. Round-robin order, sensing
rate, radio profile, raw CSI records, and the validated batch-ACK contract remain
unchanged. Measured outcomes belong in the hardware report, not this contract.

## Policy

| Setting | Initial experimental value |
| --- | ---: |
| Delivery-age target from receiver callback | 100 ms |
| Estimated completion allowance | 60 ms |
| Maximum age for pending admission | 40 ms |
| Started-transfer lifetime, from admission | 150 ms |
| Unconfirmed fragment window | 8 |
| Preferred progress-receipt cadence | 4 new fragments |
| Progress coalescing timer | 10 ms |
| Repeated receipt when no newer progress | 50 ms |
| No-progress timeout with outstanding debt | 1,000 ms |

The completion allowance is a configured estimate. It is not a measured service
guarantee or a substitute for end-to-end timing. Receiver callback time also
differs from transmitter enqueue time used for host availability bins.

Pending records expire at the smaller of the existing maximum age and delivery
target minus completion allowance. Before constructing a batch, the worker checks
its oldest record's remaining admission budget and reserves enough of the current
grant's byte allowance for the proposed envelope. It retains oldest-first order
within the admissible records. This does not force a fixed sensing-loss fraction
or quantize CSI. Intentional pending drops increment `flow_admission_drops`.

Once admitted, a batch has its own fixed transfer lifetime. Partial batches resume
across grants; retries do not restart their deadline. A fully submitted batch is
not retransmitted while its previous fragments still consume receipt credits.
Final application ACKs continue to require envelope CRC validation, identity
validation, and recorder acceptance. Expiry/retry exhaustion can release original
record storage, counted as started-transfer drops, while physical credit debt
remains independent.

The ledger has at most 16 entries, with a configured limit of eight initially.
Each entry tracks a monotonically increasing uint32 transmission serial, batch
identity, and submitted ATT-value byte count. At MTU 247, eight entries bound
unconfirmed CSI ATT-value bytes to 1,952. This excludes lower-layer headers,
control traffic, and already-delivered host buffers. It is not an exclusive RF
airtime reservation. Submission rejection cancels that reservation; application
expiry, queue reuse, final batch ACKs, and the local notification callback do not
refund it. Duplicate, stale, or future progress cannot free unrelated entries.

The peripheral retains debt across application stop/expiry and rejects a new
configuration while debt remains. Link teardown clears the ledger because that
connection's controller submissions no longer survive. During an active
configuration, lack of new receipt
progress for the timeout stops new submissions and requests disconnect, enabling
ordinary receiver recovery while other receivers continue. A transmitter restart
stops this experimental receiver's submissions until a new run is configured.

Cumulative progress assumes one ordered ATT bearer. Firmware enforces
`CONFIG_BT_NIMBLE_EATT_CHAN_NUM=0` at build time. Newer received serials therefore
establish that earlier submissions left the peripheral/controller path, even if
an application subsequently drops a fragment. Transport credit is not evidence
that a complete record was accepted. Controller traces and exact RF completion
times are not supplied by this mechanism.

## Wire contracts

CBLC v3 is 80 bytes. Bytes 0–63 retain the v2 layout. Its additional fields are
uint16 delivery target, uint16 completion allowance, uint16 transfer lifetime,
uint16 no-progress timeout, uint8 fragment window, uint8 progress cadence, uint16
progress interval, and uint32 run tag. Times use milliseconds; multi-byte fields
use network byte order. The run tag is CRC32 of the big-endian uint64 run ID,
with zero replaced by one. Control receipts additionally carry full run and boot
identities. Transmitter and receiver both validate the v3 configuration.

CBL2 notifications have a 20-byte header: magic (4), run tag (uint32), transmission
serial (uint32), batch ID (uint32), offset (uint16), and total envelope length
(uint16), followed by payload. Fragment size derives from negotiated MTU minus
three ATT bytes and this header. At MTU 247 the payload limit is 224 bytes. Two
599-byte CSI records still occupy six notifications, with 48 more fragment-header
bytes than the legacy six-notification representation. The nested CBLE v1/CSIB
encoding and original CSI bytes remain intact.

CBPR receipts are 32 bytes: magic (4), run ID (uint64), transmitter boot (uint32),
receiver boot (uint32), run tag (uint32), highest received serial (uint32), and
CRC32 over the preceding 28 bytes. They are cumulative and idempotent. All
identities, CRC, and serial bounds are checked before returning credit. Receipts
operate outside sensing-upload grants. They never acknowledge recorder acceptance.
The existing CBAK message continues to perform that separate role.

The host validates fragment tag and bounds before scheduling a progress receipt,
then routes payload into the existing strict reassembler. A separate asyncio task
coalesces/repeats receipts while the recorder works. Callback generation tokens
prevent notifications from an old connection entering the new connection's queue.
Full batches still undergo existing identity checks, deduplication, recording,
capture-time assignment, and immutable availability-bin finalization.

## Diagnostics and verification

The optional flow characteristic is
`4d71c510-8a51-4a67-aee0-52c01bb71806`. CBFS v1 has an eight-byte header with
magic, version, field count 20, and uint16 total length 168. Its 20 uint64 values
follow `FLOW_FIELDS` in `radio/acquisition/ble_protocol.py`. They include epoch
scope, issued/acknowledged serials, current/peak debt, progress receipts, rejected
receipts, pending drops, started-transfer drops, credit wait iterations, timeout
disconnects, submissions, and submission failures. Credit waits are worker-loop
iterations, not lost records. Lifetime counters require measurement-span deltas;
their absolute totals cannot identify new failures in a later run.

Both experimental baseline and candidate read the same available flow diagnostic
on updated firmware. These hardware comparisons use MTU 247 so status/timing
snapshots fit one ATT read. Other MTUs/PHYs are not qualified by those results.

Deterministic tests cover ledger conservation after application release, rejected
and duplicate receipts, serial wrap, pending timestamps newer than an expiry
check, C/Python wire fixtures, and progress while recorder acceptance is blocked.
They also verify that final batch ACKs wait for acceptance and stale callbacks
cannot enter a replacement connection. Hardware byte validation and protocol
counter checks remain necessary; synthetic tests are not throughput evidence.

For a paired hardware comparison, use a new output directory:

```bash
uv run python -m fall_detection.radio.experiments.ble_timing \
  --receiver-config data/interim/ble/c6-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --port /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_10:BD:A3:9C:EE:94-if00 \
  --output-dir data/experiments/ble/c6-delivery-repeat-NEW \
  --conditions scheduled_interval_7p5ms scheduled_delivery_7p5ms \
  --warmup 30 --duration 300 --notes 'Record current hardware and placements'
```

This is a development comparison. It preserves the complete provisioned receiver
order, including absent slots. Four-receiver collection, room coverage, and
detector accuracy require separate measurements. No benchmark promotes this
policy to the collection default automatically.

The initial measured results and limitations are recorded in
[the C6 delivery evaluation](ble-c6-delivery-2026-11-01.md). The longer pair
improved freshness and partial handling but did not establish a throughput gain.
