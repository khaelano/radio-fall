# ACK-less ESP-NOW experiment, 2 November 2026

## Implemented scope

CGCF-v5 adds an opt-in `application_acknowledgements=false` policy. It removes
processor acceptance ACKs, receiver ACK polls and application retransmissions.
Unicast ESP-NOW MAC feedback, CRC32, run/boot/batch identities, sequence numbers,
clock exchanges and the returned-to-5-GHz scheduling interlock remain active.
The transmitter remains connected over USB for control, its host lease,
authoritative round logs and clock mapping. Autonomous operation is outside this
experiment.

The receiver keeps batch bytes immutable until the MAC callback releases sender
ownership. It then frees the batch whether that MAC send succeeded or failed.
A lost callback cannot authorize a second send or extend the upload grant;
the worker still attempts channel return at its deadline and the owned batch
remains bounded. Actual recovery timing requires separate evidence. Immediate submission rejection does
not consume a send attempt. Outstanding bytes cannot expire into reuse while
the MAC owns them. `CGQE` code 11 means local completion/release, not host receipt.
The receiver's host-acknowledged counter is never incremented by this path.

The gateway neither caches processor ACKs nor answers acceptance polls in this
mode. The processor still validates the full envelope and CSI, deduplicates,
journals and calls the recorder before emitting `host_acceptance` without a
return ACK. Recorder failure stops acquisition. File-buffer acceptance does not
guarantee power-loss durability. Missing data after receiver submission cannot
be recovered by the application; integrity checking and delivery completeness
are distinct properties.

The complete configuration remains 108 bytes. Byte 103 bit 2 selects ACK-less
operation, with zero retries and no bitmap ACKs required by both Python and C.
Versions 1–4 reject this bit and retain their original fingerprints and behavior.
The transmitter/gateway expose maximum supported configuration version in USB
status; host preflight checks v5 support before sensing starts. Receiver
readiness requires successful adoption of the sensing-channel configuration.
`configs/radio/espnow_transport_ackless.json` leaves the normal default file
unchanged.

## Hardware procedure and evidence

Only rx-1 (`44:bd:8d:d0:b1:4c`) is powered in this experiment, alongside the C5
transmitter (`44:bd:8d:d0:b6:80`, configured radio identity `1a:00:00:00:00:00`)
and C6 gateway (`10:bd:a3:9e:cd:68`). Their factory application partitions were
read from the identified boards before flashing; NVS and partition tables are
preserved. The transmitter roster is temporarily reduced to this one receiver
and restored to its four-peer roster after testing.

The planned comparisons hold sensing at 80 Hz, retention at 750 ms, queue
capacity at 64, outstanding storage at four batches and guards at 5/10/10 ms
(start/send/return). Window/revisit/allowance pairs are 50/300 ms/16 records and
125/600 ms/48 records. ACK mode uses two retries and a 150 ms ACK timeout;
ACK-less mode uses no application retries. Availability grace is 900 ms in both.
Pacing approximates four-receiver scheduling without creating other receivers,
RF contention or synthetic CSI.

The initial all-new-firmware 50 ms acknowledged control delivered one batch
before stalling and zero usable records/s during measurement. The next ACK-less
attempt failed readiness. These runs are retained as failed bring-up evidence,
not a valid comparison of delivery policies. Restoring the original applications
recovered 42.4 records/s in a ten-second unrestricted-default smoke; p99 delay
was 503.59 ms, with all delivered records under one second. Sequential reflash checks with only the receiver updated, then the gateway,
then the transmitter delivered 18.0, 18.4 and 17.6 records/s with paced v4
settings. The same three new applications delivered 18.4 records/s with v5.
The initial stall did not recur in these five-second checks; its cause remains
unidentified, and a reset/reflash recovery does not establish a root cause.
Matched measurements are repeated with a send-stall abort check. The diagnostic
10-record/s floor only detects this stall; qualification remains 50 records/s.

Raw artifacts, backups, failed attempts and exact run policies are under
`data/experiments/gateway/ackless-20261102T072222Z/`. No four-receiver
qualification or detector-accuracy claim follows from this experiment.


## Delivery comparison

These measurements use one physical receiver with paced revisits. Rates count
unique, validated host records whose conservative capture-to-availability delay
is under one second. The full distributions, longest gaps, masks and timing
bounds remain in `comparison.json` and each immutable run journal.

| Window/revisit | Warm-up/measurement | With application ACKs (records/s) | ACK-less (records/s) |
| --- | --- | --- | --- |
| 50/300 ms | 5/30 s | 16.80 | 16.87 |
| 125/600 ms | 5/30 s | 46.27 | 44.33 |
| 125/600 ms repeat | 30/60 s | 43.13 | 42.87 |

Every delivered record in these six runs arrived within one second. In the
longer repeat, acknowledged/ACK-less p99 delays were 766.98/770.68 ms and maxima
812.88/814.01 ms. The ACK-less runs generated no host application ACKs, gateway
ACK transmissions or acceptance polls. The gateway forwarded all received
batches without observed USB errors. This does not measure batches lost before
gateway receipt or prove loss-free recording under faults.

The 50 ms pair had stable bounded queues. The initial 125 ms acknowledged screen
failed the fixed growth check (+7 records); its ACK-less counterpart passed
(-0.5). In the longer repeat, acknowledged growth was -6 and ACK-less growth +2,
so the latter failed queue stability despite remaining below capacity. None of these six runs
met 50 records/s. Complete timing evidence failed except in the initial 125 ms
acknowledged screen; there were no mapped after-deadline intervals, but other
runs had uncertain intervals and/or unproven grants. One receiver cannot verify
non-overlapping four-radio operation.

An initial diagnostic-accounting bug classified local ACK-less buffer release
as expiry. The host-derived delivery rates above remain valid, but the original
ACK-less expiry counters cannot quantify true expiry. It was fixed by separating
local completion, host acceptance and expiry counters, with actual C-worker
regression checks covering late and missing callbacks. Longer bursts also
set the existing diagnostic-event-loss flag; event counts are incomplete and
must not be used as exact transport-loss denominators. Corrected-firmware
hardware checks are recorded separately below.

Removing application feedback simplified the data path but did not demonstrate
a consistent throughput improvement under these settings. The healthy-link results remain
consistent with switching and worker/MAC pacing constraints. Retaining the
acknowledged default preserves recovery from application-path loss; this
experiment does not justify replacing it for collection.


## Corrected build, restoration and verification

The final receiver separates `sent_unconfirmed`, `acknowledged` and `expired`
accounting. With the same 125/600 ms policy, a new 5 s warm-up/30 s matched pair
produced:

| Mode | Timely records/s | p99 delay (ms) | Maximum delay (ms) | Queue growth (records) | Stable |
| --- | --- | --- | --- | --- | --- |
| Acknowledged | 49.07 | 765.97 | 780.08 | -1 | yes |
| ACK-less | 50.93 | 766.71 | 780.13 | +2 | no |

The short ACK-less run exceeded the rate threshold but failed the unchanged
queue-growth criterion. It delivered 37–61 records per one-second bin (median
52.5), with a longest timely capture gap of 250.00 ms. Its acknowledged control
had 31–59 records per bin (median 50.5) and a 488.01 ms longest gap. Both queue
peaks were 51/64. Every delivered record was subsecond. Receiver expiry counters
now describe expiry separately from local completion. Zero application ACKs
and polls were observed in the ACK-less run. Both gateway paths had matching
received/forwarded counters and zero observed USB errors.

Both corrected runs had diagnostic-event loss and one unproven grant despite
50 mapped recoveries before deadline; complete timing evidence therefore failed.
The bounded queues and high short-run rate do not qualify sustained operation.
The change of direction between short and longer comparisons prevents treating
the short gain as an established performance benefit. No real ACK-less gateway
outage, host-disconnect recovery, four-radio qualification or detector evaluation
was performed. The initial send stall also remains unexplained.

The original application partitions were restored on all three identified
boards. A final unrestricted-default 1 s warm-up/10 s smoke delivered 40.0
records/s with stable queues, 103.73 ms p99 delay and 128.56 ms maximum delay.
This smoke has different retention/cadence from the matched comparisons and
must not be used as their control. Its complete timing check also failed due
to one unproven grant. The transmitter's four-peer roster was reprovisioned
and verified by an accepted four-receiver configuration-only handshake followed
by an accepted stop command; sensing was not started during that check. Normal
transport defaults remain acknowledged. The experimental code and opt-in
configuration remain available; the restored boards are not left in ACK-less
mode.

`uv run pytest` passed all 383 tests. Tests cross-check Python/C configuration
encoding and reject incompatible flags/versions, exercise actual receiver-worker
code with ordinary, 88 ms and missing MAC callbacks, retain bytes through local
completion, and distinguish completion from acceptance/expiry. Actual gateway
code rejects ACK traffic and polls in the new mode while forwarding envelopes;
fake-serial tests cover startup/shutdown, old-firmware preflight rejection,
validation, deduplication and fatal recorder failures. Historical decoding tests
remain included. C5 transmitter, C5 receiver, generic C6 gateway and XIAO C6
gateway builds passed with ESP-IDF 6.1; the final corrected receiver was rebuilt
and tested on hardware. Ruff checks and `git diff --check` passed.
