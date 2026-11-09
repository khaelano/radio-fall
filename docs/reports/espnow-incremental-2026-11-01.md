# Incremental ESP-NOW optimization, 1 November 2026

Small scheduling and ACK-polling changes improved delivery and median latency
in one matched single-receiver comparison. They **did not shorten the observed
blank periods**. The candidate still failed the 50-record/s requirement, queue
stability check, and complete timing-evidence requirement. Four-receiver hardware
qualification remains pending. The proposed 5 GHz host-ACK relay remains deferred.

## Implemented changes

- A matching return status closes the previous owner's departure authorization
  immediately. The transmitter can then announce the next grant before the old
  slot expires. Its start remains at or after both the previous slot end and
  the existing two-round announcement lead. Missing return evidence still blocks
  new grants. Duplicate/stale return statuses cannot advance the scheduler;
  grant-ID wrap skips the initial unhandled value zero.
- Slot-entry ACK polls use a bit per outstanding batch. An ACKed or expired batch
  is removed from that set. A lone outstanding batch no longer receives four
  entry polls just because the configured batch capacity is four. Later polls
  respect the existing per-batch ACK timeout. No wire-format change is required.
- Pending return notices retry once per sensing round until a different grant
  is observed. A rejected status submission no longer advances the status timer.
  Ordinary health status retains its 100 ms interval. This addresses measured
  return-status observation delays near 100 ms without changing the return proof.
- The receiver refreshes worker time after retuning before checking whether
  another transmission fits. Report output now separates upload-start spacing,
  conservative recovery intervals, and before/after/uncertain deadline evidence.

The gateway/2.4 GHz host-acceptance ACK path, 80 Hz sensing, HE20/HT20 MCS0 rates,
50 ms slots, 5 ms departure guard, 10 ms return reserve, 500 ms retention,
64-record pool, four outstanding batches and 16-record slot allowance remain
in place. Successful radio submission still does not release records as accepted.

An experiment replaced polling inside `gw_send()` with a callback semaphore.
It regressed the pacing-only screen and was reverted. The retained firmware uses
the original send pacing. The experiment's source and binary remain in the
ignored artifact directory for inspection.

## Matched hardware comparison

The same verified C5 transmitter, C5 receiver and XIAO C6 gateway were used as in
[the earlier probe](espnow-hardware-probe-2026-11-01.md). The transmitter initially
failed USB control operations; unplugging and reconnecting it restored discovery.
Baseline and candidate each had a 30-second warm-up and 60-second measurement.
This duration is a comparison probe, not the required 300-second qualification.
Room motion and ambient radio traffic were uncontrolled; one pair does not
establish a repeatable improvement across placements or sessions.

| Metric | Baseline | Retained candidate |
| --- | ---: | ---: |
| Valid records/s within one second | 34.28 | 40.47 |
| Delivered records within one second | 100% | 100% |
| Median delivery latency, including clock uncertainty | 472.62 ms | 52.34 ms |
| P99 delivery latency, including clock uncertainty | 517.99 ms | 491.88 ms |
| One-second rate range | 23–51 | 18–48 |
| Longest timely capture-reference gap | 436.99 ms | 399.99 ms |
| Mean upload-start spacing | 83.43 ms | 75.10 ms |
| Median conservative blank/recovery interval | 35.78 ms | 42.86 ms |
| Maximum conservative blank/recovery interval | 44.15 ms | 44.92 ms |
| Receiver pool peak | 32/64 | 33/64 |
| First-to-last queue-window median change | −1 record | +12 records |
| Available 50 Hz bins with 500 ms grace | 1,343/3,000 | 1,816/3,000 |
| Observed recovery before slot deadline | 719 | 797 |
| Observed recovery after slot deadline | 0 | 0 |
| Recovery deadline uncertain | 0 | 2 |
| Grants without complete interval evidence | 1 | 1 |

Delivery increased by about 18% in this pair. The large median-latency improvement
did not extend to the tail, and the candidate's queue-stability check failed.
Its longer median recovery interval means this is not evidence of shorter
individual blank periods. Recovery is the first subsequent sensing frame,
bounded using clock uncertainty; it is not an isolated channel-API duration.

With one physical receiver, faster turn rotation sends that same receiver away
more often. Three other sensing views were not present to cover its absence.
The four-receiver scheduling benefit therefore needs actual four-receiver
measurements. No overlapping intervals were observed, but a one-receiver run
cannot establish non-overlap across four radios. Unobserved grants and uncertain
deadlines remain explicitly incomplete evidence.

## Short diagnostic screens

These screens used a five-second warm-up and 30-second measurement. They were
not matched-duration replacements for the baseline/candidate pair. The transmitter
retained its baseline scheduler until the final candidate run.

| Receiver changes | Valid records/s within one second |
| --- | ---: |
| Callback-based send wait only | 23.73 |
| Callback wait plus bounded ACK polls | 37.80 |
| Original send pacing plus bounded ACK polls | 32.13 |
| Original pacing, bounded polls and return-notice retry | 26.67 |

The final candidate combined the receiver changes with the earlier grant
announcement. These variable results do not establish a standalone throughput
benefit for either receiver change. Full-run p99 return-status observation delay
fell from about 102 ms at baseline to 50 ms for the final candidate; this includes
USB/host observation delay and is not a pure radio-ACK latency measurement.

## Verification and artifacts

`uv run pytest` passed 349 tests. C contract tests cover early/late/missing and
duplicate returns, 1,000 four-owner scheduler transitions, the previous-slot
departure barrier, grant wrap and unique ACK-poll selection. Tests compile the
actual sender and receiver modules against deterministic IDF stubs to verify
sender ownership after timeout and return-notice retries after rejected sends.
Report tests distinguish before-deadline, late and uncertain recovery. ESP-IDF
6.1 builds passed for C5 transmitter/receiver and generic/XIAO C6 gateway.
The candidate C5 images were flashed to the identified boards; the gateway
continued using its compatible baseline image. Builds and simulations do not
establish hardware timing or detector accuracy.

Raw runs and derived `comparison.json` are preserved locally at
`data/experiments/gateway/optimization-20261101T161431Z/`. Each run contains its
own envelope, event and availability journals. Baseline/candidate firmware
snapshots and source archives preserve provenance. Earlier raw recordings are
unchanged. The next qualification still requires four identified C5 receivers
and the unchanged 30-second warm-up/300-second measurement and fault checks.
