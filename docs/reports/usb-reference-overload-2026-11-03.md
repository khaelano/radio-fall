# Viewer USB reference overload, 3 November 2026

The viewer's reference-log failure was reproduced under plot load. Its original
USB thread stopped reading while it decoded, journaled and dispatched events.
At the same time, CSI ingestion decoded each payload three times and rebuilt
record metadata twice. Live plotting added repeated matrix construction. This
combined host workload produced sustained backpressure; a raw USB capture
contained round 1891 followed by 1893, with no skipped-round marker or framing
error. The transmitter's combined drop counter had already increased.

The host now drains transmitter USB independently through a bounded queue,
reuses validated CSI decoding, applies record metadata once, and avoids unused
raw display matrices. Viewer and collector defer plot refreshes when reference
processing falls behind. Acquisition still rejects real log gaps, corruption,
restarts and overflow. A visible Wayland viewer subsequently completed the
unchanged 30 s warm-up/300 s four-receiver benchmark at 98.207–98.673 timely
valid records/s per receiver, with no reference failure.

This fixes the reproduced reference-continuity problem; it does not establish
loss-free gateway delivery. The same final run recorded 167 gateway USB
forwarding failures, discussed separately below.

The gateway reader was subsequently buffered and given bulk reads/grouped
processing. See [the follow-up measurement](gateway-usb-buffer-2026-11-03.md):
its bulk-read trial had zero USB forwarding errors but failed the separate
receiver queue endpoint criterion. The measurements below remain unchanged.

## Failure evidence and diagnosis

The user's original run is
`data/raw/gateway-bb385de5a458252d/transport/gateway/bb385de5a458252d/`.
It saved rounds 0–3188 across about 26.66 seconds before stopping. Its rejected
round was not retained, so its exact wire-level discontinuity cannot be
reconstructed retrospectively. The stale receiver rows are the last retained
reports after acquisition failed; they do not establish receiver power loss.

Fresh probes used the same fixed four-receiver inventory, provisioned 120 Hz
channel-44 sensing profile, channel-6 MCS3 backhaul, 125 ms slots, 96-record pool,
750 ms retention and ACK-less transport policy. No board was flashed,
reprovisioned or deliberately reset. A passive serial wrapper saved exactly
what the reference reader received, including each chunk's host timestamp.
A second wrapper retained rejected round payloads and timing around event
processing. Offscreen probes used the actual viewer, widgets, phase preparation
and timer path; the final test used the visible Wayland window.

Ranked hypotheses were transmitter logging loss under host backpressure,
a misinterpreted sensing-deadline skip, and host decoding/concurrent-reader
loss. The controls retained USB identity selection and exclusive access.
Independent decoding of the failing wire traces found zero malformed or
oversized frames. The captured discontinuity had no skip marker. The timing
probe measured up to 176.43 ms between completing one USB read and starting the
next, with individual event dispatches taking up to 43.86 ms under load.
The firmware implementation waits only 20 ms for a USB write and can discard
logs on failed writes or full queues.

The counter in `CGRD` combines log/USB failures with incoming radio-queue drops;
it does not identify the source of every discarded event. The evidence
supports host overload affecting the reference logging pipeline, rather than
proving that every counter increment was a USB-write timeout. Missing reference
logs also do not establish that the corresponding sensing frame was never
transmitted. The raw trace, skip semantics, controlled rendering comparison and
successful capture-priority retest distinguish this failure from ordinary
receiver CSI gaps.

## Controlled probes and partial fixes

Artifacts below live under `data/experiments/gateway/`. Elapsed times include
startup and cleanup; they are not qualification measurement durations. Failed
probes remain preserved and were not relabeled as passes.

| Probe directory | Treatment | Elapsed (s) | Outcome |
| --- | --- | --- | --- |
| `gap-viewer-20261103T014847Z` | Original plot path | 8.54 | Transmitter drop counter increased; reference stopped |
| `gap-viewer-20261103T015032Z` | Plot refresh disabled; other viewer paths retained | 91.03 | No reference failure; 10,730 contiguous round logs |
| `gap-viewer-20261103T015259Z` | Plot refresh restored | 14.79 | Reference log overflow reproduced |
| `gap-viewer-20261103T015606Z` | Same rendering, detailed timing capture | 16.65 | Counter increase and missing round 1892 captured |
| `gap-viewer-20261103T020040Z` | Independent bounded USB drain only | 20.33 | Host receive queue reached 256 chunks; explicit failure |
| `gap-viewer-20261103T020704Z` | Add single-decode ingestion and combined metadata | 27.75 | Receive queue still overflowed |
| `gap-viewer-20261103T021043Z` | Also remove unused raw display matrices | 54.42 | Receive queue still overflowed |
| `gap-viewer-20261103T021356Z` | Also defer plots when reference processing is behind | 91.27 | No failure; host queue peak 65/256 |
| `gap-viewer-20261103T021722Z` | Same final code, visible desktop viewer | 333.54 | Completed 30 s warm-up/300 s measurement; qualification passed |

The failed buffering-only trial shows that a larger backlog allowance is not
a substitute for keeping processing within its budget. The final code retains
the same 256-chunk capacity; it does not continually increase storage to hide
slow consumption.

A representative ingestion replay profiled 2,000 batches: nested decode calls
fell from 6,000 to 2,000, and record initializations fell from 19,970 to 7,988.
Profiled ingestion time fell from 7.88 to 3.37 seconds. These are diagnostic
profiles with instrumentation and differing host load, not a controlled
statistical throughput comparison. A separate plot replay identified repeated
NumPy matrix conversion, phase preparation and painting costs.

## Implemented behavior

- `TransmitterReference` has a dedicated USB drain thread and a FIFO of at most
  256 chunks, each at most 4096 bytes. Persistent overload fails explicitly;
  bytes are never silently evicted. Stop closes and joins both workers.
- `GatewayBatch.decoded_packet` validates and caches its immutable nested
  packet. Ingestion reuses it while retaining physical identity, profile,
  duplicate and storage checks. Replacing an envelope payload invalidates the
  cache. Record context and capture-clock mapping are applied in one copy.
- Display snapshots retain full phase views and cached scalar I/Q means while
  omitting unused raw matrices. Historical full snapshots and offline fallbacks
  remain supported. Frame equivalence is tested in all three phase modes.
- Viewer and collector postpone expensive plot work while more than 16
  reference USB chunks await processing. Deferred frames do not mark their
  render gate complete; the next permitted frame uses current data. Operator
  controls and status updates continue. Display FPS can decrease under load;
  sensing frequency, record lifetime, latency criteria and finalized masks are
  unchanged. This is a preview rule, not an acquisition-readiness gate.
- `transmitter_round_rejected` journals expected/received sequence numbers,
  raw rejected bytes, run/boot identity and drop counts. `transmitter_log_loss`
  retains counter-change evidence. The first failure remains the reported
  cause rather than being overwritten by secondary shutdown errors.

The shared acquisition and dashboard changes apply to both applications. The
collector was covered by software tests; the final physical run exercised the
viewer, without phone video or an operator collection session.

## Visible viewer verification

The final run used the same inventory/profile/transport files described in the
[endurance report](espnow-endurance-2026-11-03.md), with radio fingerprint
`8b28a906a0fbcd1f` and transport fingerprint `fac57223039aef5c`. The ordinary
24 FPS timer, 12 dashboard traces, 3 s display window and calibrated phase were
retained. The operating platform was Wayland, with the viewer window visible.
The final screenshot showed all four receivers online and approximately
19 plot FPS; this is an instantaneous display measurement.

The unchanged canonical evaluator, reading the full raw journal, qualified
the exact 300-second capture-time window after 30 seconds of warm-up:

| Receiver | Valid records | Timely records/s | Delay median (ms) | Delay p99 (ms) | Delay max (ms) | Queue median growth |
| --- | --- | --- | --- | --- | --- | --- |
| rx-1 | 29,554 | 98.513 | 323.92 | 475.49 | 756.19 | -1 |
| rx-2 | 29,462 | 98.207 | 312.23 | 524.94 | 784.54 | -2 |
| rx-3 | 29,602 | 98.673 | 280.74 | 489.84 | 767.59 | +1 |
| rx-4 | 29,590 | 98.633 | 278.02 | 475.47 | 768.57 | -2 |

Every delivered record had finite timing evidence and a conservative delay
below one second. All reported queue high-water marks were 80/96; queues
passed their stability check. Independent envelope decoding found no nonzero
driver-status records in this run. Counts describe host file-buffer acceptance,
not guaranteed power-loss durability.

The reference wire trace contains **39,764 contiguous rounds, 0–39,763**, with
zero skipped-round markers, framing errors, counter changes or replay failures.
All six devices retained one boot identity; no receiver diagnostic-loss flags
were observed. The host receive queue peaked at 69/256 chunks and repeatedly
drained to zero. Logs labelled `rendered_frames` in the probe actually count
refresh calls, including deferred calls; they are not used as rendered-FPS
measurements.

Complete grant evidence covered 2,119 conservative off-channel intervals,
without cross-receiver overlap or unproven grants. Return/deadline comparisons
were 1,902 before, zero after, 217 uncertain and zero unmapped. Uncertain
comparisons are not certified as before deadline. The 15,000 finalized 50 Hz
bins use the existing 900 ms grace: none was all-missing, and 14,949 (99.66%)
had at least three receivers. These are delivered-data masks, not RF occupancy
or detector accuracy.

### Remaining gateway loss

Across warm-up, measurement and draining, gateway counters increased by
**65,419 received**, **65,252 forwarded**, **167 USB errors**, and zero rejected
envelopes. The received/forwarded deficit matches the USB-error increase,
about 0.255% of received envelopes. Exact affected sensing identities and the
gateway writer's failure mode were not isolated by this reference investigation.
At the time of this trial, the gateway's host reader performed ingestion
synchronously; the later buffering change is linked above. ACK-less transport has no host
acceptance retry for those failed forwards.

Receiver expiry counters also increased. Consequently the passing delivered-rate
and latency criteria must not be described as loss-free sensing or delivery.
The reference fix protects timing-log continuity; it does not recover discarded
gateway batches or establish detector robustness.

## Reproduction and evidence

The final directory retains the run settings, source snapshots/hashes, passive
USB trace, read/event/render timing observations, final screenshot and raw CSI
recordings. Its native journal is
`capture/gateway-a6aa675f4f1a3b40/transport/gateway/a6aa675f4f1a3b40/`.
`wire-audit.json` contains the independent reference check;
`analysis/qualification.json` contains the canonical benchmark result;
`analysis/summary.json` records latency maxima, boot identities, counters and
raw-envelope checks. Analysis scripts and profiling evidence are retained under
`diagnosis/` for local replay. Large raw artifacts remain ignored by Git.

Regression tests cover USB draining while event storage is blocked, bounded
receive-queue failure, preserved rejection evidence/first failure, one nested
decode per accepted batch, identity invalidation after payload replacement,
phase-display equivalence and preview deferral without weakening acquisition
readiness. The full suite passed **431 tests**. Transmitter radio-off and gateway
unconfigured were independently verified after the desktop run.
