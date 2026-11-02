# Gateway retention and retry experiments, 2 November 2026

These experiments test whether allowing more delivery delay preserves more
captured CSI within the unchanged one-second acceptance deadline. The normal
policy remains 500 ms retention with one application retry. Trial policies use
750 ms retention and 900 ms availability grace; a separate trial adds a second
retry. No experiment changes 80 Hz sensing, four outstanding batches, 64 queue
slots, 16 submitted records per turn, the 50 ms slot, 10 ms send guard, or
10 ms channel-return reserve. The transmitter still requires verified recovery
before another receiver can depart.

## Implementation and method

The existing retention setting already supports 750 ms. CGCF-v4 adds a bounded
budget of up to three retries using the unchanged 108-byte configuration layout;
versions 1–3 continue to reject more than one retry. Firmware checks retry
eligibility against age and ACK timeout. Exhausted batches remain available for
polling host acceptance until expiry; MAC completion does not establish host
acceptance. The host and receiver keep duplicate handling and immutable raw CSI.
The default configuration was not changed.

All hardware measurements use one verified C5 receiver
`44:bd:8d:d0:b3:50`, C5 transmitter USB identity `44:bd:8d:d0:b6:80`
(radio MAC `1a:00:00:00:00:00`), and XIAO C6 gateway
`10:bd:a3:9e:cd:68`. Both C5 boards use the 80 Hz profile fingerprint
`949e8d7005d9e9b6`. The first baseline uses the preceding firmware; later
runs use the version supporting CGCF-v4. A final default control uses the new
firmware. Each comparison has 30 s warm-up and 60 s measurement. Sequential
radio trials are subject to environmental variation and do not establish a
four-receiver result or detector accuracy.

Primary outcomes are unique valid records accepted within one second, latency
including clock uncertainty, and the longest delivery gap in capture time.
Receiver status counters provide approximate-window admissions, reported drops
and expiry counts. Their sampling brackets are retained in the derived summary;
they are not an exact capture-cohort denominator. An expiry can include a batch
already accepted by the host whose ACK did not reach the receiver, so expiry
counts alone do not measure unique data loss. Planned sensing absence remains
separate from loss of already captured records.

Availability masks are reported separately. The default uses 500 ms grace,
whereas retention trials use 900 ms. This change prevents premature model-input
finalization for the longer delivery budget, but the different masks cannot be
attributed solely to transport. Raw finalized bins are never revised.

For the controlled fault comparison, the experiment delays host ACK submission
for a 600 ms interval every three seconds. Capture, USB reading, validation and
journal acceptance continue. A bounded 128-entry queue releases the ACKs when
the interval ends; hold/release events identify the intervention explicitly.
This tests delayed ACK recovery, not absent gateway RF, corrupted payloads or a
complete host disconnect. The receiver may already have delivered records
before their ACK is released.

A second fault screen withholds complete envelopes before host acceptance for
250 ms every three seconds. Those envelopes are preserved separately in
`withheld-envelopes.bin`; they are not fed into the acquisition journal or
acknowledged. Its four policies separate retention, an extra retry and retry
pacing (150 ms ACK timeout). These shorter screens use 5 s warm-up/30 s
measurement. The analysis matches boot/sequence identities against transmitter
rounds and accepted records, excluding records accepted before the first
withholding. It reports exact recovery within one second for that deliberately
withheld subset, not for all possible receiver captures. Matched retransmitted
envelopes are also compared byte-for-byte. This intervention models a loss at
the application acceptance boundary, not physical radio interference.

Original journals, policies, inventory, firmware images and source/build/test
artifacts are preserved under
`data/experiments/gateway/retention-20261101T225758Z/`.
`comparison.json` and each run's `qualification.json` are derived artifacts.
The experiment helpers are retained there for reproduction.

## Delivery and delay screens

| Policy | Timely records/s | Delay median / p99 / max (ms) | Longest gap (ms) | Sampled queue maximum | Reported expiries |
| --- | --- | --- | --- | --- | --- |
| Initial default | 40.48 | 49.71 / 477.49 / 515.93 | 124.99 | 23 | 54 |
| 750 ms, one retry | 40.50 | 41.65 / 181.37 / 255.16 | 50.98 | 12 | 0 |
| 750 ms, two retries | 40.02 | 40.86 / 56.58 / 104.82 | 50.68 | 1 | 0 |
| ACK delay, default | 40.00 | 52.88 / 408.01 / 433.42 | 50.14 | 19 | 140 |
| ACK delay, 750 ms | 40.25 | 53.32 / 656.99 / 722.24 | 50.03 | 34 | 28 |
| ACK delay, 750 ms + two retries | 40.05 | 52.96 / 508.21 / 570.90 | 50.25 | 24 | 0 |

All delivered records in these screens were accepted within one second.
Retention alone did not materially increase steady delivery: 40.48 versus
40.50 records/s. The extra-retry screen delivered 40.02 records/s. Those
sequential values do not establish a throughput benefit. The sampled occupancy
column is the largest queue count reported during the measurement; firmware
`peak` is a boot-lifetime high-water mark and can include earlier runs.

Under delayed ACKs, the default still delivered 40.00 records/s with a 50.14 ms
maximum capture-time gap between timely deliveries. Its 140 reported expiries
therefore cannot be read as 140 missing host records. The 750 ms policy delivered
40.25 records/s and shifted 103 records into the 500–1000 ms delay range; its
maximum delay was 722.24 ms. Adding the second retry delivered 40.05 records/s
with 56 records in that range and 570.90 ms maximum delay. This demonstrates
that additional latency is usable, but this ACK-only intervention does not
establish improved completeness: the default already retained a near-continuous
captured stream.

## Rate distributions, masks and timing

| Policy | One-second count min / median / p95 / max | Availability mask 0 / 1 | Grace (ms) | Return before / uncertain / after | Unproven grants |
| --- | --- | --- | --- | --- | --- |
| Initial default | 33 / 41 / 43.05 / 46 | 1179 / 1821 | 500 | 791 / 5 / 0 | 1 |
| 750 ms | 39 / 40 / 44.05 / 47 | 1177 / 1823 | 900 | 801 / 0 / 0 | 1 |
| 750 ms + two retries | 39 / 40 / 41 / 42 | 1200 / 1800 | 900 | 800 / 0 / 0 | 1 |
| ACK delay/default | 39 / 40 / 41 / 41 | 1200 / 1800 | 500 | 800 / 0 / 0 | 1 |
| ACK delay/750 ms | 39 / 40 / 41.05 / 48 | 1194 / 1806 | 900 | 798 / 0 / 0 | 0 |
| ACK delay/two retries | 39 / 40 / 41 / 43 | 1198 / 1802 | 900 | 801 / 0 / 0 | 0 |
| New-firmware default | 39 / 40 / 41 / 41 | 1200 / 1800 | 500 | 800 / 0 / 0 | 1 |

Each availability table row contains 3000 finalized 20 ms bins for the one
registered receiver. Mask 0 means no timely model-input record; mask 1 means
that receiver is available. These mask counts use the stated grace and must
not be confused with the independent one-second transport criterion. The
initial baseline had five intervals with uncertain deadline classification.
The ACK-delay 750 ms and extra-retry trials had complete observed timing
evidence; other screens left one grant unproven. No interval was proven after
deadline. Four-receiver overlap safety is still unmeasured in hardware.

The final new-firmware default control delivered 40.00 records/s, with
41.64 ms median and 56.78 ms p99 delay, zero median queue growth and no late
records. This checks the unchanged default path after the retry-budget update;
it does not establish a sustained four-receiver qualification.

## Recovery of explicitly withheld records

| Policy | Timely records/s | Recovered withheld records within 1 s | Delay p99 / max (ms) | Longest gap (ms) | Sampled queue maximum |
| --- | --- | --- | --- | --- | --- |
| Default: 500 ms, one retry, 50 ms ACK timeout | 38.30 | 20/77 (26.0%) | 509.82 / 517.00 | 312.01 | 30 |
| 750 ms, one retry, 50 ms timeout | 39.43 | 16/68 (23.5%) | 516.89 / 646.02 | 211.99 | 30 |
| 750 ms, two retries, 50 ms timeout | 39.53 | 24/52 (46.2%) | 307.85 / 366.01 | 125.00 | 18 |
| 750 ms, two retries, 150 ms timeout | 40.60 | 60/60 (100.0%) | 414.74 / 454.58 | 50.02 | 15 |

The paced two-retry policy recovered all 60 deliberately withheld records
in its measured subset within one second, compared with 20 of 77 for the
default. There were no byte differences among its 48 matched retransmitted
batches over the full run (85 matched batches across all four screens, with
zero differences). Every delivered record was subsecond, including records
outside the deliberately withheld subset. The candidate's maximum conservative
delay was 454.58 ms and its longest capture-time gap returned to 50.02 ms.

These results support using part of the latency budget for retry spacing.
A longer queue lifetime alone did not recover the initially withheld batches
once their attempts were exhausted. The original 50 ms timeout can consume
both retries during a 250 ms interruption. A 150 ms timeout leaves a later
attempt available after that interruption ends. The comparison isolates this
timeout change between the last two rows; results remain sequential short
hardware screens, not a general guarantee of complete delivery.

The 750 ms/one-retry loss screen failed the existing queue-growth check
(median growth 2.5 records); the other three passed. All queues remained below
their 64-record capacity and reported no overflow drops in the sampled status
intervals. Bounded occupancy does not erase the failed growth check. The paced
policy's median queue growth was zero, with 15 records at the largest sampled
occupancy. None of these screens meets the unchanged 50-record/s requirement.

| Loss-screen policy | One-second count min / median / p95 / max | Mask 0 / 1 (grace ms) | Return before / uncertain / after | Unproven grants |
| --- | --- | --- | --- | --- |
| Default: 500 ms, one retry, 50 ms ACK timeout | 29 / 39 / 42 / 44 | 651 / 849 (500) | 398 / 0 / 0 | 0 |
| 750 ms, one retry, 50 ms timeout | 34 / 40 / 46 / 46 | 612 / 888 (900) | 407 / 0 / 0 | 0 |
| 750 ms, two retries, 50 ms timeout | 36 / 39.5 / 41 / 42 | 609 / 891 (900) | 403 / 0 / 0 | 0 |
| 750 ms, two retries, 150 ms timeout | 39 / 40.5 / 43 / 44 | 591 / 909 (900) | 403 / 0 / 0 | 0 |

Each loss-screen mask contains 1500 finalized bins. The paced trial had
complete timing evidence for all 403 observed intervals, each conservatively
before deadline. Other screens' evidence is reported in the table and raw
qualification reports; no overlapping four-receiver intervals were tested.

## Candidate and restoration

The experimental candidate is
`configs/radio/espnow_transport_retention_750ms_retry2_paced.json`: 750 ms
retention, two retries, 150 ms ACK timeout, and 900 ms availability grace.
Four outstanding batches, slot timing and sensing rate remain unchanged.
It is available for further testing and is not promoted to the default.
Longer interruptions, real RF failures and four-receiver contention remain
unqualified. More buffering cannot recover measurements never captured.

After all interventions, the original policy was restored and the final
1 s warm-up/10 s smoke delivered 39.90 records/s, 40.87 ms median latency and
59.97 ms maximum delay, with zero median queue growth and no late records.
All 134 observed intervals were before deadline with complete timing evidence.
Final USB status verified all three identities, matching 80 Hz profiles,
receiver configuration capability v4, transmitter radio off and gateway
unconfigured. Original data and fault traces remain preserved.

## Verification and limits

The full suite passed 361 tests. The new deterministic C/Python contract test
first failed on the unsupported retry policy, then passed after implementation.
Tests cover legacy rejection, bounded retry attempts, expiry at 750 ms,
selective batch ownership/ACK release, hard slot exit and the return interlock.
Fake USB startup and rejection include CGCF-v4, and the actual receiver module
is tested with both v3 and v4 policies. All four ESP-IDF 6.1 builds passed:
C5 transmitter, C5 receiver, XIAO C6 gateway and generic C6 gateway.

The unchanged four-receiver transport acceptance test requires actual four-C5
hardware and a 30 s warm-up/300 s measurement. These single-receiver screens do
not qualify that setup, establish post-switch phase stability, or measure
fall-detection accuracy. A strict deadline cannot guarantee every record will
arrive during radio or host failures; misses remain explicit.
