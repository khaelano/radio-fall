# Optimized four-receiver bring-up, 2 November 2026

After moving all four receivers to a replacement hub powered by a phone charger
adapter, the upgraded system completed 30 seconds of warm-up and 300 seconds of
measurement. Every receiver exceeded 98.8 valid records/s on average, every
delivered record was subsecond, queues passed the unchanged stability check,
and channel-interval evidence was complete without observed overlap. The
benchmark passed its explicit 80-record/s target. Earlier failed attempts remain
below; the hardware reset cause has not been established by supply measurements.

## Setup

All six boards were powered. The transmitter, gateway and rx-1 had USB data
connections; rx-2–4 initially had power-only USB. Identities and firmware are
recorded in the deployment section of
[`espnow-throughput-2026-11-02.md`](espnow-throughput-2026-11-02.md).
All four C5 receivers use the event worker and fixed-160-MHz/v7 image, with the
120 Hz channel-44 sensing profile. The C5 transmitter and XIAO C6 gateway use
the matching fixed-160-MHz images. The gateway uses its built-in antenna.

The requested test uses
`configs/radio/espnow_transport_throughput_mcs3_queue96.json`: 125 ms maximum
upload slots, 5 ms start guard, 10 ms send guard and return reserve, 96 record
slots, 750 ms retention, four batch buffers, 64 records submitted per slot,
MCS3 backhaul on channel 6 and no application ACKs. MAC feedback, CRC validation,
clock exchanges and the return interlock remain active. No artificial minimum
revisit pacing is imposed on the actual four-receiver rotation.

The benchmark requests qualification mode, 30 seconds of warm-up, 300 seconds
of measurement and the explicit 80-record/s-per-receiver target. The original
50-record/s requirement is not relaxed, nor are slot lengths or sensing rates
changed to obtain a pass.

## Recorded attempts

Artifacts are under `data/experiments/gateway/`; each directory retains the exact
inventory, profile, policy, source hashes, invocation, raw transport journals,
process result and derived startup-failure analysis. Durations below are partial
authoritative sensing spans, not completed measurement windows.

| Artifact directory | Backhaul | Sensing span (s) | Accepted records, rx-1/2/3/4 | Outcome |
| --- | --- | --- | --- | --- |
| `four-optimized-20261102T115440Z` | MCS3 | 2.15 | 0/0/0/0 | rx-3 boot change; startup stopped |
| `four-optimized-20261102T115547Z` | MCS3 | 7.07 | 0/0/0/0 | rx-3 boot change; startup stopped |
| `four-optimized-20261102T115707Z` | MCS0 control | 14.81 | 0/0/0/0 | receiver preflight timed out |
| `four-optimized-20261102T115747Z` | MCS3, after gateway reset | 8.78 | 116/133/93/110 | all streams live, then rx-3 boot change during warm-up |

In the first two attempts, radio status identified all four receivers, but
recorded MAC completions were predominantly failures and gateway status reported
zero received/forwarded envelopes. The MCS0 control changed only backhaul PHY;
it did not restore delivery. A bootloader identity check and hard reset of the
identified C6 preceded the fourth attempt. That attempt recorded 227 envelopes
received and forwarded by the gateway, zero gateway rejections, and 452 accepted
CSI records across all four receivers. This supports recovery after resetting
the gateway; it does not identify the underlying radio-state fault or isolate
every environmental variable between sequential attempts.

All three MCS3 attempts contain CRC-checked `CGST` packets in the same run with
a changed rx-3 boot ID and a restarted capture counter (0 or 1). Replaying those
status packets through the actual host status handler reproduces
`RuntimeError: receiver restarted; start a new run`. The host's restart guard is
retained. Some shutdown logs also contain a secondary ingestion error after
the reference failure; it does not explain the preceding boot change.

## Diagnosis before the supply comparison

The receiver's reset reason is unavailable over its power-only connection.
Firmware/driver/watchdog failure and a supply interruption remain hypotheses;
neither is established by a boot ID alone. No supply voltage/current measurement
or detector evaluation was performed. USB data access to rx-3 was requested for
reset status and boot logging while keeping every board powered. The requested
sustained measurement and complete channel-timing qualification remain pending.
After the attempts, USB status confirmed transmitter radio-off and gateway
unconfigured. All 401 software tests passed; no firmware or host restart guard
was changed during these hardware attempts. A different hub/supply comparison
was offered as an alternative to first identifying rx-3 over USB; no such
comparison has yet been performed.

## Charger-powered replacement hub

The user moved all four receivers to a replacement hub powered by a phone
charger adapter. Only the transmitter and gateway remained on laptop USB data.
The same firmware, full inventory, 120 Hz profile, MCS3 policy, slot timing,
retention and 80-record/s qualification target were retained. The new attempt is
`data/experiments/gateway/four-optimized-20261102T120301Z/`; its settings record
the user-reported supply topology. Receiver power cycling accompanies the hub
change, and the gateway also has a different boot ID from the previous attempt.
Consequently this is a useful successful comparison, not an isolated electrical
measurement proving that the old hub alone caused the failures.

The complete 300-second measurement accepted 118,609 unique valid records:

| Receiver | Records | Valid records/s | Delay median / p99 / max (ms) | Queue peak / 96 | Median queue growth | One-second rate min–max |
| --- | --- | --- | --- | --- | --- | --- |
| rx-1 | 29,653 | 98.84 | 280.22 / 473.96 / 639.37 | 64 | +1 | 96–110 |
| rx-2 | 29,657 | 98.86 | 280.57 / 474.29 / 624.01 | 62 | -1 | 96–108 |
| rx-3 | 29,647 | 98.82 | 280.51 / 474.38 / 486.57 | 60 | 0 | 94–108 |
| rx-4 | 29,652 | 98.84 | 280.56 / 474.26 / 482.82 | 60 | +1 | 94–108 |

Every delivered record met the one-second bound using the conservative delay
estimate, including clock uncertainty. One-second rates use sensing-reference
capture-time bins; every observed bin exceeded 80 records. All four queue checks
passed without changing their criteria: no full pool and first/last median
growth at most one record. Longest timely capture gaps were 109.00–109.04 ms.
Each receiver and the gateway retained one boot ID throughout the run, with no
diagnostic-event loss or transmitter log drops.

The raw journal contains 65,521 complete envelopes across warm-up, measurement
and draining. Independent decoding validated every envelope CRC and nested CSI
identity; no duplicate record identity occurred in the measurement window.
Gateway status reported 65,521 received and forwarded envelopes, zero rejected
envelopes and zero USB errors. Application ACKs and polls stayed at zero.
Receiver MAC summaries recorded no failed uploads or outstanding sends at
return. These results establish validity of delivered bytes in this run, not
loss-free capture or a delivery guarantee for ACK-less operation. Receiver
expiry counters remained nonzero and are preserved in `analysis.json`.

All required grants have mapped interval evidence, with no overlapping or
uncertain cross-receiver intervals and no unproven grants. Of 2,119 mapped
recoveries, 2,002 were conservatively before their slot deadline and 117 straddled
the deadline uncertainty bound; none was classified after deadline or unmapped.
Thus complete nonoverlap evidence passed, but this does not prove that every
return preceded its deadline. Mean upload-start spacing was 141.66 ms, giving
approximately 566.64 ms between turns for the same receiver.

Availability was evaluated separately at 50 Hz with the configured 900 ms
grace. Across all 15,000 finalized bins, 5,658 contained all four receivers and
9,342 contained three. In receiver order rx-1/2/3/4, masks were `0111`: 2,350,
`1011`: 2,338, `1101`: 2,317, `1110`: 2,337, `1111`: 5,658. There were no bins
with fewer than three receivers available. These are delivered-data masks at
20 ms resolution; they do not establish continuous detector accuracy.

The benchmark's sustained transport criteria passed at both 80 and 50
records/s per receiver. The derived 50-target result preserves the same data
and other checks; the original 80-target report remains unchanged. Artifacts
include `analysis.json`, `qualification-target50.json`, the original
`qualification.json`, raw envelopes/events/masks, configuration/source hashes
and deployment provenance. No fault-injection or post-switch phase-stability
qualification was added in this comparison. Final USB status verified
transmitter radio-off and gateway unconfigured; upgraded firmware and 120 Hz
provisioning remain installed.
