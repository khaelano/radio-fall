# Historical scheduled BLE CSI transport

Live BLE has been retired on `codex/espnow-gateway`. Use
[the ESP-NOW gateway procedure](espnow-gateway.md) for current firmware and commands.
The following contract is retained to interpret historical recordings.


The BLE mode uses one USB-connected ESP32-C5 or ESP32-C6 transmitter and up to four
ESP32-C5/C6 receivers connected to the laptop through BLE. Round robin is the
collection default. Random assignment is an opt-in experimental policy. Model
training is outside this implementation. USB CSI streaming has been removed from
this branch; USB remains for board provisioning and transmitter control/timing.

Use `indonesia_2g_ch6_80hz.json` for C6 boards or a mixed C5/C6 inventory. A 5 GHz
profile requires C5 for every board. Registered targets must match actual USB
and BLE identities; changing the build target does not update the inventory.

Firmware builds and offline tests do not establish RF throughput, capture
coverage, timing precision, or detection accuracy. Initial hardware preflight
identified and fixed unframed transmitter statistics on the USB reference link;
40 subsequent clock exchanges succeeded. The initial one-receiver byte-integrity
and delivery measurements are in [the C6 quality report](reports/ble-c6-quality-2026-11-01.md);
they do not establish four-receiver or detector performance.
The versioned default inventory describes the historical two-receiver C5 cohort.
Use the actual provisioned C6 inventory for this setup; four-receiver collection
requires four verified identities and never substitutes virtual receivers.

## Scheduling and retention

The configured receiver list defines slot order. Sensing round `n` assigns its
upload window to slot `n % receiver_count`. A disconnected slot remains in the
rotation. Sequence wrap uses uint32 arithmetic. Random mode instead uses the
specified uint32 counter mixer in `radio/ble_config.py` and `ble_protocol.h`, with
a recorded seed; repeated owners are permitted. Neither mode changes the radio
profile automatically after a benchmark.

Each sensing round repeats the current and next two grants. A receiver only
submits CSI notifications inside a received, unexpired grant assigned to its
slot. The initial start/end guards are 1 ms. Missing announcements cannot create
an unlimited grant. Repeated announcements do not replenish a window's byte
allowance. Without fresh observations, authorization expires within three round
periods. Local window estimates include Wi-Fi delivery delay; they are not a
precision cross-radio clock synchronization mechanism.

The receiver retains the first valid observation of each sensing round, including
observations made during its upload window. It does not discard data to manufacture
25% missingness. Consequently, 80 sensing rounds/s does not imply either 60 captured
records/s per receiver or a guaranteed BLE workload.

Application grants cannot cancel controller traffic already submitted or BLE
maintenance events. BLE and Wi-Fi still compete for RF resources. Use measured
capture loss and notification submission/completion timing to assess the policy;
do not infer blindness from grant ownership. Espressif documents the coexistence
constraints in its [ESP-IDF guide](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32c5/api-guides/coexist.html).
C6 uses a shared 2.4 GHz RF module for Wi-Fi and BLE; its coexistence behavior
must be measured separately from C5. See the [C6 coexistence guide](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32c6/api-guides/coexist.html).

### Timing experiments

`python -m fall_detection.radio.experiments.ble_timing` runs explicit development
comparisons and records each command, policy, raw session, and derived report.
It supports continuous submission, multi-round turns, batch size, requested
connection interval, and submission pacing. Normal collection rejects a non-null
`experiment` configuration. Collection defaults and existing fingerprints are
unchanged; experiments never borrow absent receivers' turns implicitly.

CBLC control version 2 uses its final eight bytes for `slot_rounds` (uint8),
`batch_records` (uint8), connection interval in 1.25 ms units (uint16), submission
pacing in microseconds (uint16), continuous-upload flag (uint8), and a reserved
zero byte. Multi-byte fields use network byte order. Version 1 remains the normal
collection contract. Experimental controls require updated transmitter and receiver
firmware; CBLE envelopes remain version 1 and sensing packets remain version 3.

Multi-round turns derive ownership from `sequence // slot_rounds`. Their byte
allowance scales by the number of rounds, preserving the nominal bytes per second;
inner round boundaries have no guard and do not replenish the allowance. Continuous
upload is only a diagnostic baseline: it bypasses ownership and byte allowances,
but still requires fresh sensing observations, bounded record/batch storage, and
the normal expiry policy. Both modes retain valid Wi-Fi captures.

The optional timing characteristic `4d71c510-8a51-4a67-aee0-52c01bb71805`
returns a 232-byte CBTM snapshot, fitting one read at ATT MTU 247. Its eight-byte
header is magic, version 1, count 4, and total uint16 length. Four rows contain
batch ID and flags (uint32 each), then receiver-local uint64 microseconds for
oldest capture, batch construction, first/last submission, ACK, and expiry.
Flags are built=1, fully submitted=2, ACK while outstanding=4, age expiry=8,
and ACK after release=16. Samples expose four recent entries from an eight-entry
ring; they are incomplete diagnostics, not a capture ledger. The worker's local
notification callback reports a submission attempt, not RF completion or host
receipt. Controller backlog cannot be inferred from that callback alone.

Host journals additionally record first/last fragment arrival, acceptance, and
ACK-write completion during experiments. ACKs still follow validated recorder
acceptance. The diagnostic read adds traffic, so comparisons use the same
instrumentation. Short screening runs must be distinguished from runs using a
30-second warm-up and five-minute measurement. No benchmark automatically changes
the collection default or qualifies a room layout.

Experimental preflight checks the actual connection interval. It retries CBLC
at most twice before sensing if a connect-time update is still in progress,
then stops on a mismatch. Normal collection behavior is unchanged. A paired
five-minute C6 comparison at verified 7.5 ms found improved freshness but lower
total delivery with an 80 ms age limit; neither condition met 50 usable Hz.
See [the measured timing report](reports/ble-c6-timing-2026-11-01.md).

CBLC v3 adds an opt-in delivery experiment with fresh-record admission, a separate
started-batch lifetime, and cumulative host-arrival credits. Its CBL2 fragments
preserve existing raw CSI/envelope encoding; CBPR returns transport credit while
CBAK still confirms validated recorder acceptance. Expiring a batch does not
refund bytes still downstream. The protocol, limits, and measurement procedure
are documented in [the delivery-policy contract](ble-delivery-policy.md).

## Firmware and board setup

On a Seeed XIAO ESP32-C6, enable its RF switch with GPIO3 low. GPIO14 low
selects the built-in ceramic antenna; high selects an attached external antenna.
The receiver needs no external antenna in built-in mode.
See [Seeed's board documentation](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/#hardware-overview).
Append `sdkconfig.defaults.xiao_esp32c6` to the defaults list for XIAO boards;
it selects built-in mode. For a transmitter with an external antenna attached,
use `transmitter/sdkconfig.defaults.xiao_esp32c6_external` instead. Generic C5/C6
builds leave antenna GPIOs untouched. USB and BLE status record the selection.

Use ESP-IDF 6.1. BLE is the default and only receiver CSI transport on this
branch; old USB build directories can contain stale binaries and must not be
flashed. Use explicit target-specific build directories. From the repository root:

```bash
source ~/.espressif/v6.1/esp-idf/export.sh
cd src/firmware/radio/receiver
CSI_TARGET=esp32c6  # use esp32c5 for a C5 board
# For this XIAO C6 receiver; set empty for a generic board.
CSI_BOARD_DEFAULTS="$PWD/sdkconfig.defaults.xiao_esp32c6"
idf.py -B "build-ble-$CSI_TARGET" \
  -D SDKCONFIG="$PWD/build-ble-$CSI_TARGET/sdkconfig" \
  -D SDKCONFIG_DEFAULTS="$PWD/sdkconfig.defaults;$PWD/sdkconfig.defaults.$CSI_TARGET;$CSI_BOARD_DEFAULTS" \
  -D IDF_TARGET="$CSI_TARGET" build

# Replace this with the receiver's actual native USB Serial/JTAG port.
CSI_PORT=/dev/ttyACM0
idf.py -B "build-ble-$CSI_TARGET" -p "$CSI_PORT" flash
```

Repeat the build and flash commands in `src/firmware/radio/transmitter`, selecting
that board's target and USB port. The target-specific build directories prevent
C5 and C6 configurations from being reused accidentally. The transmitter uses
the USB-controlled scheduler; it does not run Bluetooth. Defaults disable secondary
USB console output. Runtime statistics also use binary framing because ROM
printing can bypass the console setting. Receiver defaults enable
NimBLE, coexistence, and a larger application partition. The `.ble` overlays
remain compatible aliases for those defaults. Flash the matching image
to each positively identified board using its build directory and port. Changing
the partition table requires flashing that table as well as the application.

Initial receiver provisioning uses USB. BLE receivers reboot after a committed
profile change so NimBLE identity and receiver-slot bindings reload together. Discover all board identities:

```bash
uv sync --extra radio
uv run csi-radio discover --json
```

Create a four-receiver inventory using those actual addresses and unique IDs.
Preserve the intended receiver order and record placements. Do not use example
addresses as hardware identities. With all five boards connected, provision the
same inventory/profile:

```bash
uv run csi-radio provision \
  --receiver-config data/interim/ble/four-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json
```

Alternatively, provision one board at a time with `--sequential`. First discover
each board over USB and finish the complete inventory, including the transmitter
and all receiver MACs in their intended slot order. If the addresses are not
already known, discovery and provisioning require two passes through the boards.
Then connect exactly one board and run:

```bash
uv run csi-radio provision --sequential \
  --receiver-config data/interim/ble/four-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json
```

Wait for successful provisioning and the `verified device <MAC>` message before
disconnecting it. Attach the next board and repeat the exact command. Each board
stores the full inventory, including disconnected receivers. Do not remove
disconnected entries from the file. The command checks only the attached board;
it does not certify that the remaining boards have been provisioned. Repeat for
every board, keeping the inventory and profile unchanged throughout the pass.
If either changes, provision every board again. Without `--sequential`, the
provisioner still requires all registered boards together.

Keep the transmitter on USB. Disconnect receiver USB data connections and power
them independently. BLE acquisition does not scan or open receiver serial ports.
For already provisioned BLE boards, `csi-ble-discover --receiver-config ...` reports
GATT identities; `--output NEW_FILE` can extend an inventory without overwriting
an existing file. Re-provision all boards after changing receiver membership or
order. The BLE configuration checks a CRC32 over the exact ordered MAC list,
because the existing radio fingerprint does not include receiver membership.

## Power and reset diagnostics

The transmitter initially limits RF power to 11 dBm (44 quarter-dBm), records the
driver's actual limit, and stops Wi-Fi while no sensing run is active. Clock and
control requests renew a 3-second lease; loss of control stops sensing. A new
start command is required after expiry. Receiver dynamic Wi-Fi RX buffers are capped at 32 to retain BLE heap headroom.
The CPU remains capped at 80 MHz with
DFS. These measures target unnecessary RF/CPU activity; actual board temperature
and supply-current reduction have not been measured. Unacknowledged Wi-Fi peers
are probed at a 100 ms spacing, with at most one pending send per peer and rotating
submission order. This limits retries without changing grant ownership. Validate link margin at the
chosen power rather than assuming the same coverage as the previous build.

Discovery/status includes reset reason and uptime. Receiver BLE identity carries
the same diagnostics; transmitter status includes radio activity and RF power.
A USB disappearance or dark LED does not establish a thermal shutdown. If the
supply is a power bank, verify its auto-off behavior with that specific unit.
Firmware resets, brownouts, and supply shutdowns require different evidence.

## Collection, viewing, and hardware benchmarks

Set `CSI_TX_PORT` to the transmitter's actual port. Four-receiver collection:

```bash
uv run fall-collection --transport ble --port "$CSI_TX_PORT" \
  --receiver-config data/interim/ble/four-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --ble-config configs/radio/ble_transport.json
```

The viewer accepts the same transport arguments through `csi-viewer` and supports
one to four receivers for development. Collection requires four registered,
identity-verified receivers, recent decoded records, a fresh transmitter clock
fit, and writable storage before a new attempt starts. Missing receiver data can
continue during an active attempt while the transmitter reference remains valid.
Loss of the transmitter reference interrupts the attempt. Restart the acquisition
with a new run identity before resuming.

The receiver JSON policy defaults are 32 records total, four outstanding batches,
250 ms maximum age, 50 ms ACK timeout, one application retransmission, and four
record-equivalents of notification-envelope bytes per grant. One equivalent is
699 bytes, the maximum encoded CSI record size; fragment headers are additional
radio overhead. Partial transfers and retries consume the same allowance.
Expired data is counted, not silently relabeled as a measurement.

The requested connection parameters are LE 2M, ATT MTU 247, data length 251,
12.5 ms connection interval, zero peripheral latency, and 2 s supervision timeout.
The controller may negotiate different values. Firmware status reports actual
values; the host does not trust BlueZ's `BleakClient.mtu_size` as an observation
of the link. See [Bleak's API notes](https://bleak.readthedocs.io/en/latest/api/client.html).

Run one condition with a 30-second warm-up and five-minute measurement:

```bash
uv run csi-ble-benchmark run --port "$CSI_TX_PORT" \
  --receiver-config data/interim/ble/four-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --ble-config configs/radio/ble_transport.json \
  --output-dir data/experiments/ble
```

`--development` permits fewer than four discovered receivers while retaining the
complete provisioned inventory and grant rotation. Missing startup slots remain
missing throughout that diagnostic run; collection still requires all four.
The journal records the discovered startup IDs. This mode does not change any
board's NVS receiver list. For a development run, `--duration 1800` performs
a 30-minute soak. `--notes` records movement, body blockage, unplug/reconnect,
and other deliberate fault conditions. The report separates capture counter
rates, timely delivery, queue age, expiry/retry counters, latency percentiles,
longest missing runs, joint availability, and reported heap memory. Capture
counter rates explicitly use the counter snapshot interval. Notifications
arriving before a deadline but processed afterwards are not timely input.

Prepare the 50/60/70/80/100 Hz matrix without changing any board:

```bash
uv run csi-ble-benchmark matrix --port "$CSI_TX_PORT" \
  --receiver-config data/interim/ble/four-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --output-dir data/interim/ble/matrix-v1
```

The matrix contains round-robin runs first and secondary random runs with seeds
101, 202, and 303. Its provisioning commands must be completed for each rate;
changing the transport JSON alone does not re-provision a radio profile. Run a
single receiver first, then four, and finally the selected round-robin soak.
`csi-ble-benchmark report RUN_DIRECTORY --signal-quality` also verifies the raw
envelopes, authoritative timing metadata, and CSI subcarrier statistics.
The [initial XIAO C6 hardware report](reports/ble-c6-quality-2026-11-01.md) records observed
limits; it does not establish a collection candidate. Never interpret
these reports as a four-view model evaluation or a guaranteed 50 usable Hz.

## Delivery and files

The queue lifecycle is pending → outstanding → acknowledged/released. Only the
exact run/boots/batch ACK releases an outstanding batch. Duplicate batches are
acknowledged without duplicating CSI rows. The processor ACK follows validation
and journal/consumer acceptance. File flushing is not a power-loss durability
guarantee. A failed write prevents the ACK and stops the run. Host reassembly stays bounded;
when a newer batch supersedes a full pool, the oldest older partial is explicitly
evicted. Old fragments cannot evict newer partials. Expiry/eviction counters are
recorded separately from malformed-envelope errors.

Expiry evicts stale pending records; overflow evicts the oldest unsubmitted
record. Outstanding memory is pinned until its owner releases it. ACK timeout
allows one retry in a later valid grant, bounded by original record age. The
notification pipeline has one controller submission outstanding at a time.

Each run adds `transport/ble/<run-id>/` beneath its session directory:

- `manifest.json`: policy, radio profile, ordered inventory, and fingerprints.
- `envelopes.bin`: network-order `uint64 arrival_ns`, `uint32 length`, then one
  complete CRC-protected BLE envelope. It preserves original CSI bytes.
- `events.jsonl`: transmitter rounds, clock exchanges, receipt timing, statuses,
  connection changes, processing availability, and final failure state.
- `availability.jsonl`: immutable 50 Hz bins finalized at bin end + 100 ms.
- `benchmark.json`: measured summary when the benchmark command completed.

Packet masks, counts, and ages describe available observations, independently of
per-subcarrier validity. Record events preserve finite raw-slot masks. There is
no temporal interpolation or feature/model selection here. Late observations
cannot fill an already finalized bin but may update later sample-age metadata.

Per-attempt `csi.csv` and `radio_timing.csv` keep their existing schemas. BLE adds
`ble_timing.jsonl` per receiver for capture-clock mapping, epochs, and uncertainty.
The collector routes by mapped sensing time and keeps ended attempt writers open
for 300 ms. Later arrivals remain in the session journal. The canonical phase
loader validates this sidecar and sorts only its derived view by capture time;
it refuses to substitute BLE arrival time when a BLE sidecar is missing. Existing
USB recordings retain their prior clock behavior.

Shutdown stops the transmitter, permits up to 300 ms of drain uploads without
sensing grants, then closes connections and deferred writers. CSI arriving after
its prediction deadline stays absent from its original finalized input.

## Wire contract, version 1

All integer fields are network byte order. Reject unknown versions, inconsistent
lengths, incorrect identities, and CRC failures before acknowledging anything.

GATT uses service `4d71c510-8a51-4a67-aee0-52c01bb71800`, with final UUID bytes:
`01` identity JSON/read, `02` CSI notifications, `03` control writes with response,
and `04` diagnostic vector/read. Identity is below 512 bytes. Diagnostics are
224 bytes: `CBSS`, version byte 1, count byte 27, uint16 total length, then 27
uint64 values ordered by `STATUS_FIELDS` in `acquisition/ble_protocol.py`.

`CBLC` is a 64-byte configuration: version/scheduler/count/retry bytes at 4–7;
run ID at 8; seed at 16; age/ACK/capacity uint16 values at 20/22/24; outstanding
batch/grant-equivalent bytes at 26/27; guards/rate uint16 values at 28/30/32;
reserved zero at 34; ASCII policy fingerprint at 36–51; ordered inventory CRC32
at 52; and reserved zero bytes at 56–63. Host-only bin/grace/drain settings are
covered by the policy fingerprint and manifest.

Sensing `CSIT` version 3 is 88 bytes. It retains the original 40-byte sensing prefix, then adds
run ID at 40, transmitter boot at 48, policy fingerprint at 52, period at 68,
round deadline at 72, and three owner bytes at 80–82 plus reserved zero at 83.
CRC32 over bytes 0–83 occupies bytes 84–87. The receiver snapshots and validates
the metadata before sequence/grant state changes. Owners correspond to the
current round and its next two rounds. Normal acquisition requires sensing
version 3 on both roles; older formats remain decodable for historical fixtures,
not live collection. Reflash every board when upgrading this sensing protocol.

A `CBLE` envelope has a 32-byte header: magic, version/flags bytes, uint16 header
length, uint64 run, uint32 transmitter boot, receiver boot, batch ID, uint16 CSIB
length, and reserved uint16 zero. Existing CSIB/CSI1 bytes follow, then CRC32 over
header and payload. Maximum envelope length is 1436 bytes.

Each notification has a 12-byte `CBLF` header: magic, uint32 batch ID, uint16
byte offset, uint16 total envelope length. The remaining bytes are a fragment.
A `CBAK` application ACK is 28 bytes: magic, uint64 run, uint32 transmitter boot,
receiver boot, batch ID, then CRC32. `CBST` + uint64 run stops a receiver;
`CBDS` + uint64 run + uint16 milliseconds requests bounded drain.

USB frame types 12/13/14 carry transmitter controls/responses/round logs.
`CBLC` configures, `CBGO` + uint64 run starts, and `CBST` + uint64 run stops.
`CBCK` + uint32 ID + uint64 host t1 requests a clock exchange. Its 40-byte reply
echoes the request and appends transmitter t2/t3, boot, and cumulative log drops.
A `CBRD` round log is 51 bytes: magic, run, boot, sequence, enqueue/deadline times,
period, immediate enqueue-success bitmask, log-drop counter, and three owners.
The result's high bit instead marks skipped timer rounds; its lower 31 bits give
the skipped count. Enqueue success is not proof of over-air delivery. Queue
or USB write failure invalidates reference completeness; a later clock reply
also exposes cumulative log loss.
