# Gateway cadence and ACK trials, 2 November 2026

The requested changes are implemented as opt-in CGCF-v3 policies: a minimum
per-receiver revisit interval, an independent send-completion guard, selective
bitmap polling through the existing C6 gateway, and a separate 100 Hz sensing
profile. The normal policy remains 80 Hz, four outstanding batches, deadline
return, and a 10 ms send guard. No trial changes the 50 ms maximum slot, the
10 ms channel-return reserve, the return-confirmation interlock, or the
50-record/s qualification requirement.

## Implementation

The transmitter applies the revisit lower bound to each fixed receiver's next
scheduled start. It can announce that window while the receiver captures, but
cannot authorize departure until the previous owner has returned. A missing
return still suspends new departures; no placeholder receivers were added.
The new guard controls when sends stop being initiated before the existing
return cutoff. A receiver returns regardless of ACKs or pending work.

`CGPQ` and `CGPB` carry up to eight explicit batch IDs, a request token, run,
both boot identities, receiver MAC and CRC32. The gateway sets a selective ACK
bit only when its bounded host-acceptance cache contains that exact batch.
Duplicate/stale replies cannot release a different owned batch. Immediate host
ACK forwarding and the original `CGAK` format remain supported. The deferred
5 GHz host-ACK relay is not implemented.

Optional `CGMT` summaries measure API submission to MAC completion for uploads
and ACK polls. They include failures, maximum failed-send duration, completions
after cutoff and sender ownership at return. Summaries wait for MAC completion;
an outstanding callback is not silently treated as success. Metrics do not
constitute processor acceptance. See [the protocol](espnow-gateway.md) for the
108-byte configuration and 72-/64-byte message layouts.

## Hardware and method

Only one physical receiver was available: C5 `44:bd:8d:d0:b3:50`, with C5
transmitter USB identity `44:bd:8d:d0:b6:80` (configured radio MAC
`1a:00:00:00:00:00`) and XIAO C6 gateway `10:bd:a3:9e:cd:68`.
These are sequential single-receiver screens, not the required four-receiver
30 s warm-up/300 s qualification or a detector evaluation. The baseline used the
previous firmware; all tuning trials use the new firmware. Later trials can
also differ in radio conditions, so this is not a controlled attribution of each
individual optimization's effect.

Ignored artifacts are under
`data/experiments/gateway/cadence-20261101T221151Z/`. Each trial retains its
inventory, sensing/transport policy, run/boot identities, original envelopes,
raw control events and immutable availability bins. `comparison.json` is a
derived summary; per-run `qualification.json` files retain full one-second rate
distributions, gaps, queue checks, timing uncertainty and availability masks.
The first absent-gateway attempt aborted because the experiment helper omitted
its reference binding. Its raw journal is retained; a corrected retry is
reported separately.

All latency figures below use the conservative sensing-reference-to-application
acceptance delay including clock uncertainty. Observed recovery intervals bound
receiver departure through the first observed sensing frame, including mapping
uncertainty; they are not direct measurements of only the channel-switch API.
A bounded queue with expiry can remain stable while losing measurements, so
queue stability alone does not establish adequate transport capacity.

## Measured screens

| Policy (sensing 80 Hz) | Warm-up / measure (s) | Timely records/s | Delay median / p99 (ms) | Recovery median / max (ms) | Queue peak |
| --- | --- | --- | --- | --- | --- |
| Default baseline | 30 / 60 | 40.00 | 41.65 / 56.80 | 42.44 / 43.53 | 10 |
| 150 ms, four batches | 30 / 60 | 38.63 | 495.52 / 517.14 | 41.92 / 42.02 | 32 |
| 200 ms, four batches | 5 / 30 | 29.20 | 495.55 / 517.60 | 43.05 / 44.06 | 35 |
| 150 ms, eight batches | 5 / 30 | 36.47 | 495.63 / 518.71 | 43.14 / 46.70 | 35 |
| 150 ms, eight + bitmap | 30 / 60 | 32.23 | 495.08 / 518.14 | 34.51 / 36.95 | 35 |
| Bitmap + timing metrics | 5 / 30 | 27.60 | 496.24 / 516.97 | 34.51 / 35.85 | 35 |

All delivered records in these screens arrived within one second. All queues
were bounded and passed the existing growth check, but every tuning trial
failed the unchanged 50-record/s criterion. The 150/200 ms cadences were
observed as configured; median latency near 495 ms indicates records waiting
close to the 500 ms lifetime. Increasing the outstanding window alone did not
clear that backlog. Bitmap polling reduced the median observed recovery bound
but did not improve delivery. These results do not justify promoting any of
these combinations to the normal collection policy.

One-second rate distributions and receiver availability must remain separate:
the table below reports rate minimum/median/95th percentile/maximum, longest
timely-record gap, and counts of finalized 20 ms bins. In this one-receiver
inventory, mask 0 means no accepted receiver record and mask 1 means the receiver
is available. These are model-input bins with 500 ms grace, independent of the
one-second transport deadline. They do not represent four-receiver masks.

| Policy | Records per second: min / median / p95 / max | Longest gap (ms) | Bins mask 0 / mask 1 |
| --- | --- | --- | --- |
| Default | 39 / 40 / 41 / 41 | 50.02 | 1200 / 1800 |
| 150 ms, four | 32 / 39 / 41 / 41 | 137.99 | 1482 / 1518 |
| 200 ms, four | 24 / 30 / 30 / 30 | 337.00 | 1062 / 438 |
| 150 ms, eight | 27 / 37 / 40 / 41 | 199.93 | 874 / 626 |
| Bitmap | 25 / 31.5 / 39 / 41 | 213.02 | 1685 / 1315 |
| Bitmap + metrics | 21 / 27 / 33.1 / 37 | 213.01 | 1019 / 481 |

Timing evidence was complete for the baseline, eight-batch screen and metric
screen. The eight-batch screen had 11 intervals whose deadline classification
was uncertain; complete logs do not remove timing uncertainty. The 150 ms,
200 ms and bitmap screens each left one grant unproven. No interval was proven
after its deadline, but incomplete evidence is not a timing pass. No overlapping
owners can be inferred from a single physical receiver; four-receiver hardware
verification remains pending.

## MAC failure timing and guard decision

With the configured gateway running, the metrics screen produced 242 summaries
covering 503 completions, including three failures. Maximum failure duration
was 88.478 ms; five completions were after cutoff, and three summaries reported
sender ownership at return. Mean duration (2.918 ms) does not bound failures.
The separate 15 s absent-gateway retry held the verified C6 in its bootloader
and collected transmitter control/reference logs without pretending to accept
data. It recorded 100 summaries, 102 completions and 99 failures; maximum
failure duration was 88.312 ms, with 96 late completions and 96 busy-at-return
summaries. Its 100 observed sensing-recovery intervals had a maximum
conservative bound of 38.46 ms. The C6 was reset into gateway firmware afterward.

These measurements distinguish the receiver's channel return from outstanding
MAC ownership. They do not establish that every transmission completed before
return. The receiver continues the return process and the transmitter requires
actual recovery/confirmation before the next departure. The existing 10 ms
send guard cannot itself bound an 88 ms failed MAC operation; reducing it to
5 ms is therefore not supported. The 5 ms policy is implemented but was not
activated. Shortening this guard requires a driver/completion strategy backed
by fault measurements, not an average-latency argument.

## 100 Hz sensing trial

Both C5 boards were explicitly provisioned and verified with profile
`indonesia-5g-ch44-100hz`, fingerprint `38b0022110bb30ac`. The trial used
150 ms revisit, four batches, no bitmap polling, deadline return and the 10 ms
send guard: the best-delivering tested v3 policy at 80 Hz. After 30 s warm-up
and 60 s measurement it delivered 36.80 timely records/s, compared
with 38.63 records/s for that policy at 80 Hz. Median/p99 delay was
493.36/511.27 ms, all delivered records were subsecond,
and queue peak increased to 42 records with median growth zero.
Its one-second rate minimum/median/p95/maximum was
28/37/41/41; the
longest timely-record gap was 140.01 ms. Finalized availability
bins were mask 0: 1742, mask 1: 1258. Observed recovery median/max
was 42.38/43.31 ms. All 400 observed intervals
were before deadline, but one grant remained unproven.

Higher offered sensing rate did not increase delivered rate in this screen.
It increased stored demand under an already constrained upload path; this is
consistent with a transport limit, although these sequential measurements do
not isolate a single driver or scheduling cause. Neither 100 Hz nor the other
trial policies are promoted. Both C5 boards were restored and verified at
80 Hz, fingerprint `949e8d7005d9e9b6`; the C6 was running gateway firmware.

The final restored-default smoke used the newly flashed firmware, a 1 s warm-up
and a 10 s measurement. Startup, capture, draining and shutdown completed. It
delivered 40.10 records/s, with median/p99 delay
41.34/63.28 ms, all delivered records subsecond, queue
peak 6 and zero median queue growth. All 134 observed intervals were
conservatively before deadline with complete interval evidence. This short
smoke checks restoration, not sustained qualification. Final USB status verified
all three board identities, matching 80 Hz C5 fingerprints, transmitter radio
off and gateway unconfigured after shutdown (`final-status.json`).



## Validation and remaining limits

The full software suite passed 357 tests. Tests compile the actual C protocol,
queue/receiver and I/O code against deterministic stubs; they cover configuration
compatibility, fixed receiver cadence with the return interlock, selective ACKs,
stale identities/tokens, duplicate batches, failed/in-flight MAC ownership,
clock mapping and fake-USB startup. C5 transmitter, C5 receiver, generic C6 and
XIAO C6 projects built with ESP-IDF 6.1 in separate build directories.
These checks establish software behavior, not four-radio timing, capture
quality after switching, phase stability, or fall-detection accuracy.
