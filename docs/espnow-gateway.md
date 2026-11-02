# Scheduled dual-band ESP-NOW gateway

The live transport on `codex/espnow-gateway` uses an ESP32-C5 transmitter and
C5 receivers for 5 GHz HE20 sensing. Each receiver temporarily switches to
2.4 GHz to upload complete batches to a dedicated ESP32-C6 gateway. The gateway
forwards bytes over native USB Serial/JTAG. Bluetooth is disabled. Historical
BLE recordings, parsers, reports and replay inputs remain available; their
measurements do not qualify this transport.

## Hardware and configuration

Normal collection requires four actual C5 receivers. A switching probe can use
one to four registered receivers and is never labeled four-receiver qualification.
Use `configs/radio/gateway_inventory.json` for the verified four-C5 roster and
XIAO C6 gateway. This schema-v2 inventory contains the `transmitter`, ordered
`receivers`, and a `gateway` object with `id`, `role: gateway`,
`target: esp32c6`, and its discovered MAC. `configs/radio/receivers.json` retains
the user's sensing-only roster in the legacy schema. Sensing entries must target `esp32c5`.
All IDs and MACs must be unique. Do not substitute guessed or virtual devices.

Use `configs/radio/profiles/indonesia_5g_ch44_80hz.json` and
`configs/radio/espnow_transport.json`. The policy fixes channel 6 and HT20 MCS0
long-GI backhaul, 50 ms slots, a 5 ms departure guard, a 10 ms return reserve,
64 record slots, 500 ms retention, four outstanding batches, one retry and
16 records per slot. Policy and ordered physical identities are fingerprinted.
These timing margins are initial engineering settings, not measured guarantees.
Eight-batch and early-return trial policies are available separately. Early
return shortened blank periods but regressed latency and had inconsistent
throughput, so the four-batch/deadline-return default remains. See
[window and return trials](espnow-window-return-2026-11-02.md).
The first hardware probe is recorded in
[espnow-hardware-probe-2026-11-01.md](espnow-hardware-probe-2026-11-01.md):
single-receiver delivery works, but the rate and queue-stability checks failed.

Build with ESP-IDF 6.1. Use absolute build/config paths to isolate targets:

```sh
source ~/.espressif/v6.1/esp-idf/export.sh
CSI_REPO="$PWD"
CSI_ROLE=receiver   # transmitter: C5; gateway: C6
CSI_TARGET=esp32c5
CSI_PROJECT="$CSI_REPO/src/firmware/radio/$CSI_ROLE"
CSI_BUILD="$CSI_PROJECT/build-gateway-$CSI_TARGET"
idf.py -C "$CSI_PROJECT" -B "$CSI_BUILD" \
  -D IDF_TARGET="$CSI_TARGET" -D SDKCONFIG="$CSI_BUILD/sdkconfig" \
  -D SDKCONFIG_DEFAULTS="$CSI_PROJECT/sdkconfig.defaults" build
```

For a XIAO C6 gateway, append the receiver's
`sdkconfig.defaults.xiao_esp32c6` overlay to `SDKCONFIG_DEFAULTS`; the shared board
component then enables GPIO3 and selects the built-in antenna on GPIO14.
Only select an external antenna when the corresponding hardware is attached.
Flash a positively identified device using `idf.py -C ... -B ... -p <stable-port>
flash`. All images report protocol 3; C5 sensing frames use version 4.

Provision the same complete sensing inventory/profile on the C5 transmitter and
receivers. Connect sensing boards one at a time and use:

```sh
uv run csi-radio-discover --json
uv run csi-radio-provision --sequential \
  --receiver-config configs/radio/gateway_inventory.json \
  --radio-profile configs/radio/profiles/indonesia_5g_ch44_80hz.json
```

The C6 gateway does not store a sensing profile. Its identity is verified and its
channel, sender registry, run and transmitter boot are configured over USB at
startup. Keep both transmitter and gateway USB data links connected. Receiver
USB is for provisioning only; receivers need power during capture.
After changing the sensing receiver roster, explicitly provision the transmitter
with the complete new inventory as well. Its stored peer list is checked against
the run configuration. The sensing-profile fingerprint covers radio settings and
transmitter identity, so an unchanged fingerprint does not prove the receiver
list is current. The transport fingerprint includes the ordered roster.
See [the four-receiver hardware report](espnow-four-receivers-2026-11-02.md).

## Scheduling and deadlines

The transmitter owns all grants and stays on 5 GHz. Sensing packets carry the
full configuration, run/boot identities, and a CRC-protected future grant. Slots
rotate in configured receiver order, with no discovery-based reassignment.

Receivers progress through capture, switch, upload, return and confirmation.
A four-timestamp exchange bounds transmitter/receiver clock offset. Receivers
skip departure without a fresh exchange or adequate timing margin. They stop
submitting before their hard return cutoff and return regardless of queue
contents or missing ACKs. The cutoff is aligned early enough to recover before
an expected sensing round inside the slot, using the existing return reserve;
otherwise a last-round miss could delay the return witness beyond slot expiry.
Actual switching calls can exceed an initial reserve;
recorded recovery and explicit failure are required rather than claiming a hard
real-time radio guarantee.

With an explicit early-return policy, a completed burst or exhausted send budget
can return sooner once the MAC sender is idle. A short configured grace also
permits return when no admissible work remains. Unacknowledged records stay
retained within their lifetime. A `CONFIRM_RETURN` request on 5 GHz resumes
sensing probes to that receiver; it does not authorize another departure.
Actual sensing recovery still supplies the return proof. The hard deadline
remains effective even if a MAC completion is missing.

The next receiver cannot depart until its predecessor confirms return on
the 5 GHz link and the previous slot has ended. After a matching early return,
the next grant can already be announced with a start no earlier than the old
slot end and the two-round announcement lead. A lost grant is acknowledged as
expired while still on 5 GHz. Pending return notices retry once per sensing round
until the next grant is observed; ordinary health status remains at 100 ms.
Without a valid return, new departures stop; sensing continues. A future grant
is announced at least two sensing rounds ahead. This look-ahead and handoff delays can
make the cycle longer than the nominal four times 50 ms; use actual journals.
No receiver silently extends a grant. The transmitter stops RF after its
three-second USB control lease expires.
`CGDF` events record departures deferred for missing readiness or return evidence.
On host reconnection, a new run filters stale-run events and establishes a
baseline for lifetime drop counters. Any additional drop during that run still
invalidates complete timing evidence; old-run losses remain in the journals.

Capture continues whenever valid 5 GHz frames are received. Scheduled permission
is not evidence that a measurement exists or is missing. Keep actual sequence
IDs, receiver identity, transmitter enqueue time and local capture timestamps.
The enqueue timestamp is a sensing reference, not a measured on-air instant.

## Delivery and storage

A `CGCF` v1–v4 configuration is 108 bytes. Version 2 supports up to eight
outstanding batches and an optional idle-return grace in bytes 100–101.
Version 1 keeps its four-batch limit and zero extension bytes. Older firmware
rejects version 2 during configuration. `CSIT` v4 sensing frames are 180 bytes.
Version 3 packs idle-return milliseconds into byte 100, minimum revisit time
in 5 ms units into byte 101, and the send-completion guard in milliseconds into
byte 102. Byte 103 enables bitmap ACK polling (bit 0) and MAC completion metrics
(bit 1); other bits are rejected. The revisit range is 0–1000 ms and the send
guard range is 1–20 ms. These options require compatible firmware on all roles.
The default v1 policy and historical v1/v2 fingerprints remain unchanged.
Version 4 retains the v3 layout and permits up to three application retries
(at most four submissions including the initial send). Versions 1–3 keep the
one-retry limit and reject larger budgets. Failed MAC results alone never free
a batch. Retries still obey the record lifetime, ACK timeout, slot allowance
and send cutoff; they can span later authorized turns without extending a slot.
The default policy remains v1 with one retry.
A `CGWY` v1 envelope has a 40-byte header, an unchanged `CSIB` payload and CRC32.
The full envelope is at most 1400 bytes, including overhead; unusually wide CSI
therefore forces a smaller batch. There is no fragmentation in this transport.
The versioned policy implies HT20 MCS0/LGI; do not use ESP-NOW's default PHY rate.

`CGAK` is a 34-byte application acceptance ACK. MAC completion does not release
receiver records. The gateway caches host ACKs; the receiver polls a specific
outstanding batch during its next authorized upload. ACKs are qualified by run,
both boot IDs, batch ID and receiver MAC. Duplicate batches are idempotent.
A bounded retry or expiry releases work without implying delivery. Expiry does
not cancel bytes already in a radio or USB buffer.
Only MAC-accepted submissions consume retry and slot budgets. The receiver
polls each eligible batch at most once at slot entry. With a larger window,
cached-ACK polls interleave with fresh data. Later polls respect the ACK timeout.
ACKed/expired batches leave the entry set.

With v3 bitmap polling enabled, `CGPQ` requests acceptance for up to eight
explicit batch IDs and `CGPB` returns a selective bitmap. Both are 72 bytes,
CRC-protected, and include run, transmitter/receiver boot IDs, receiver MAC,
request token and the exact ordered IDs. Only the gateway's host-acceptance
cache can set a bit. Empty cache entries remain unacknowledged; duplicate or
stale replies cannot release different batches. `CGAK` and the host acceptance
boundary remain unchanged. This path uses the existing 2.4 GHz gateway link.

The optional minimum revisit interval applies separately to each ordered
receiver's scheduled start. It is a lower bound, not a guaranteed cadence:
return confirmation can still defer departure. The send-completion guard stops
new sends before the existing return cutoff; it does not reduce the channel
return reserve or extend a grant. Keep its default 10 ms until both successful
and failed MAC-completion timings support a smaller value.

The host validates the entire envelope and nested receiver/profile identity,
journals it, accepts its CSI records, then ACKs. File-buffer acceptance is not a
power-loss durability guarantee. Storage exceptions stop ingestion without ACK.

An opt-in CGCF-v5 policy disables application acknowledgments while retaining
unicast MAC feedback, clock exchanges and the returned-to-5-GHz interlock.
`application_acknowledgements=false` requires zero application retries and no
bitmap ACKs. Receivers retain sender-owned batch bytes until MAC completion,
then release them without claiming delivery, whether that MAC send succeeded
or failed. Immediate submission errors may be retried within the original
deadline because they never entered the MAC. Gateway acceptance caching and
ACK polling are disabled for this mode. The host still validates, deduplicates,
journals and records data; recorder failures remain fatal. Gateway/USB/host
loss after sending is unrecoverable at the application layer. Transmitter USB
control, lease, timing reference and diagnostics remain required.

All roles must support CGCF-v5. USB preflight checks transmitter and gateway
capabilities before starting sensing; receivers establish readiness only after
accepting the configuration over 5 GHz. Older receivers cannot accept v5 and
prevent acquisition readiness. Existing v1–v4 policies/fingerprints retain their
ACK behavior. See [ACK-less implementation and measurements](espnow-ackless-2026-11-02.md).

Each run adds `transport/gateway/<run-id>/manifest.json`, `envelopes.bin`,
`events.jsonl` and `availability.jsonl`. Attempts add `gateway_timing.jsonl` next
to the unchanged CSI and timing CSVs. Capture-time attribution and deferred close
apply to both gateway and historical BLE sessions. Missing clock alignment is
an error, not permission to substitute arrival time. Derived phase-motion caches
include the new timing sidecar.

Round receipts include all-stream silence. Availability bins finalize at 50 Hz
with a 500 ms grace; late records cannot rewrite finalized bins. The independent
one-second benchmark deadline does not change those model-input bins. Channel
interval diagnostics conservatively map local departure/return times using
clock bounds and uncertainty. Unobserved grants remain unproven, not zero-length
blind intervals. Radio loss, scheduled absence and transport loss are separate
observations; sequence gaps alone do not identify the cause.
`CGQE` v1 events retain batch build, submission, retry, acceptance, abandonment,
expiry, overflow and return-failure causes (codes 1–8). Their 32-entry receiver
queue is bounded; status flags lost diagnostic events. Host USB ACK submissions
are journaled separately from gateway ACK relay and MAC failures. Availability
mask distributions are reported separately from the one-second rate metric.
Trial event 9 records an early-return decision and event 10 records return-API
completion; `CGPR` records resumed sensing probes. These remain separate from
actual sensing-frame recovery.
Optional `CGMT` v1 summaries are 64 bytes and contain run/boot/grant identity,
MAC sample/failure counts, minimum/maximum/total duration, maximum failed-send
duration, completions after cutoff and whether a send was still owned at
return. One bounded aggregate is emitted after return and MAC completion;
missing callbacks do not produce false completion evidence. These measurements
are distinct from gateway and host application acceptance.

## Optimization direction

An optional event-driven upload worker and a gateway ACK-activity-window
experiment are implemented behind build settings. They leave protocol versions,
record encoding and normal defaults unchanged. The mixed four-radio screens
improved rx-1 delivery with the worker but did not qualify throughput; fewer
gateway ACK failures alone did not improve delivered rate. See
[burst/ACK measurements and limits](espnow-burst-ack-2026-11-02.md).

Larger 80/100/125 ms windows and higher per-turn record limits are separate,
explicit experiments requested to amortize switching overhead. A paced
single-receiver comparison improved delivery but stayed below 50 records/s;
four-radio results are not inferred. A timing-only model displays one-owner
grants and lost-return suspension without generating CSI. See
[bulk-window results and model assumptions](espnow-bulk-timing-2026-11-02.md).

Decision (1 November 2026): retain the current gateway/2.4 GHz host-acceptance
ACK path and prioritize small, measured changes. Earlier next-grant announcement,
bounded ACK polls and faster return-notice retry are implemented; switching
reserves and qualification criteria remain intact. A callback-based send-wait
experiment was reverted after a regressive screen. The matched single-receiver
pair improved delivery/median latency but did not shorten observed blank periods
or pass qualification. See [the incremental test report](espnow-incremental-2026-11-01.md).

Deferred fallback: route processor acceptance ACKs through transmitter USB and
then 5 GHz sensing/control packets, allowing receivers to await acceptance on
the sensing channel. This would require host, transmitter, receiver and protocol
changes, plus a bounded batch-window review. The user considers that change too
invasive at this stage. Revisit it only if measurements show that smaller changes
have reached the current architecture's throughput/latency ceiling. The failed
single-receiver probe alone does not establish that ceiling.

## Run and qualify

```sh
uv sync --extra radio
uv run csi-viewer --port <transmitter-usb> --gateway-port <gateway-usb> \
  --receiver-config data/interim/gateway/inventory.json \
  --radio-profile configs/radio/profiles/indonesia_5g_ch44_80hz.json

uv run fall-collection --port <transmitter-usb> --gateway-port <gateway-usb> \
  --receiver-config data/interim/gateway/inventory.json \
  --radio-profile configs/radio/profiles/indonesia_5g_ch44_80hz.json

uv run csi-gateway-benchmark --mode qualify \
  --port <transmitter-usb> --gateway-port <gateway-usb> \
  --receiver-config data/interim/gateway/inventory.json \
  --radio-profile configs/radio/profiles/indonesia_5g_ch44_80hz.json \
  --warmup 30 --seconds 300
```

Start with `--mode probe --warmup 5 --seconds 30` and a verified one-receiver
inventory to measure switching and byte integrity. Verify recovery within the
50 ms slot, actual send completion, ACK/expiry behavior and post-return CSI before
attempting full qualification. Do not change settings automatically if it fails.

Four-receiver qualification requires at least 50 valid timely records/s per
receiver over the entire 300 s measurement and at least 99% of all delivered
records below one second. Delay includes clock uncertainty conservatively.
Report one-second counts and longest gaps, not only the mean. Queue stability
requires a peak below configured capacity and no more than one-record increase
between the first and last 30 status-sample medians. This fixed operational check
is not a statistical claim about stationary traffic. Complete channel evidence
and no overlap of conservative off-channel bounds are also required. Missing
status/clock evidence fails qualification. Report incomplete runs as incomplete.

Raw artifacts are ignored under `data/experiments/`. `qualification.json` is a
derived report; analyses never rewrite raw journals. Builds, offline contracts,
one-receiver probes and historical synthetic CNN results do not establish
four-receiver performance or fall-detection accuracy.


Higher-throughput experiments add explicit v6 MCS0–3 backhaul settings and
profile-v2 120 Hz sensing, then v7 bounded 96-slot retention with compact
control-only queues. The 5 GHz sensing PHY, complete CSI bytes, channel-return
interlock and timing guards are retained. A sustained paced single receiver
exceeded the 80-record/s average target with stable queues in ACK-less mode;
acknowledged mode failed queue growth. Four-receiver qualification and complete
timing evidence remain open. Defaults and original applications were restored.
See [the full throughput report](espnow-throughput-2026-11-02.md) before deploying
experimental settings to the four registered receivers.
