# Gateway USB buffering and grouped processing, 3 November 2026

The host now drains gateway USB into a bounded RAM FIFO while a separate worker
validates and records available groups of data. Bulk reads coalesce small USB
fragments, reducing queue handoffs. The visible Wayland viewer delivered
98.293–98.597 timely records/s each
in the unchanged 30 s warm-up/300 s four-receiver test. Rate and latency checks
passed, but full qualification failed because rx-2's endpoint median queue
increase was +2 records, above the fixed +1 limit. Post-stop gateway counters
show 65,256 received,
65,256 forwarded and **0 new USB forwarding errors**
across the complete run. Maximum conservative delivered delay was 826.14 ms.

This follows the [reference-overload investigation](usb-reference-overload-2026-11-03.md),
whose visible five-minute run recorded 167 failed gateway USB forwards. A first
buffered run reduced that to three failures but produced many tiny read chunks.
The final bulk-read variant is a separate sequential measurement, not proof of
zero loss in other conditions or recovery from faults. Receiver expiry and
planned off-channel capture gaps remain distinct from USB forwarding failures.

## Mechanism

The live path is:

```text
C6 gateway USB → dedicated host read thread → timestamped RAM FIFO
              → bounded groups → validation → journal/receiver recorder
```

| Host setting | Value |
| --- | --- |
| Raw USB read request | At most 4096 bytes |
| Read timeout | 5 ms; reads can complete earlier when full |
| FIFO byte capacity | 256 KiB |
| FIFO chunk capacity | 256 |
| Maximum queued age | 200 ms; exceeding it fails acquisition explicitly |
| Worker group | Up to four already available chunks, at most 16 KiB of read input |
| Preview deferral | More than 16 pending chunks on either reference or gateway input |

The reader keeps consuming the USB endpoint while validation, CSV recording or
journaling is busy. Its 5 ms read timeout coalesces fragmented USB input; the
processing worker wakes as soon as any chunk is available and never waits for
four chunks or a fixed number of CSI records. Each group contains independently
validated envelopes. Partial serial frames continue through the existing COBS
stream decoder; radio envelope size and encoding remain unchanged.

This implements grouped queue consumption and bulk input. Each envelope keeps
its own identity/CRC/profile checks, duplicate tracking, recording and acceptance.
Application ACKs, when enabled, still follow successful storage of that envelope.
Disk flushes and signal calculations are not combined into a new transaction.
ACK-less mode remains ACK-less. A later failure in a group cannot acknowledge
an envelope whose recording failed.

Raw chunks preserve host USB read-completion timestamps. A frame spanning reads
uses the timestamp of the read completing it. The worker passes that arrival
time through recording; `available_ns` still reflects actual acceptance after
queueing and processing. Sensing time remains mapped from transmitter timestamps,
and late delivery cannot revise finalized model-input bins.

The queue has no eviction policy: capacity overflow or excessive queued age
invalidates acquisition rather than silently losing data. An active group owns
its bytes independently of the FIFO. Shutdown stops the producer, drains already
owned work and joins both workers before closing USB/recorders. A stuck worker
produces an explicit shutdown failure. These rules preserve bounded memory and
make sustained overload observable instead of extending delivery indefinitely.

Manifests record `host_usb_buffer` settings. `gateway_host_buffer` journal events
report queued/peak bytes and chunks, groups, consumed chunks and maximum queue
wait, with a final snapshot after draining. Gateway status retains `usb_read_ns`.
These additions do not change raw CSI CSVs or historical decoding contracts.

## Controlled runs

All physical trials retained four C5 receivers, the USB-controlled C5 transmitter
and USB C6 gateway, 120 Hz channel-44 HE20 sensing, channel-6 MCS3 backhaul,
125 ms slots, 96 receiver record slots, 750 ms retention and ACK-less delivery.
Radio/transport fingerprints remain `8b28a906a0fbcd1f` / `fac57223039aef5c`.
No firmware, board provisioning, sensing rate or qualification criterion changed.

| Artifact directory under `data/experiments/gateway/` | Treatment | Result |
| --- | --- | --- |
| `gap-viewer-20261103T021722Z` | Reference fix; synchronous gateway reader | Qualified, 167 USB forwarding failures |
| `buffered-viewer-20261103T040601Z` | Bounded gateway FIFO and available-data groups; opportunistic tiny reads | Completed; three USB forwarding failures; 548,096 consumed read chunks, queue peak 40,219 bytes / 188 chunks; maximum queue wait 155.23 ms |
| `bulk-buffered-viewer-20261103T041610Z` | Same FIFO/groups with 4 KiB / 5 ms bulk reads | Qualification failed; 0 new USB errors; 28,638 consumed chunks |

All counts above use comparable full run spans including warm-up and draining;
rate/latency qualification uses the exact 300-second sensing window after warm-up.
The first buffered run is preserved rather than rewritten as the final treatment.
Neither sequential comparison isolates every source of environmental variation.
Plot render counts also depend on bursty per-receiver delivery and skipping
unchanged snapshots; fewer queue handoffs do not by themselves prove higher FPS.

## Final visible-viewer measurement

| Receiver | Usable records | Timely records/s | Delay median (ms) | Delay p99 (ms) | Delay max (ms) | Receiver queue growth |
| --- | --- | --- | --- | --- | --- | --- |
| rx-1 | 29,557 | 98.523 | 329.80 | 535.38 | 780.05 | +0.0 |
| rx-2 | 29,579 | 98.597 | 316.44 | 541.19 | 826.14 | +2.0 |
| rx-3 | 29,562 | 98.540 | 288.34 | 604.81 | 791.28 | -2.0 |
| rx-4 | 29,488 | 98.293 | 283.21 | 617.12 | 764.05 | -0.5 |

These delays include clock uncertainty and all host queue/processing time.
The canonical qualification result is **failed**; detailed one-second
rate distributions and longest capture gaps remain in `analysis/qualification.json`
and, after driver-status filtering, `analysis/quality-qualification.json`.
The failed criterion was rx-2's receiver queue endpoint median: it increased
from 26 to 28 records (+2), above the fixed +1-record limit. Its five one-minute
queue medians were 26, 27, 26, 28 and 26 records; those additional summaries do
not override the predefined endpoint check. This remains a
qualification failure even though host buffering drained successfully and the
rate/latency checks passed. No criterion, slot, sensing rate or queue policy was
relaxed, and no unchanged rerun was used to obtain a pass.
One rx-3 observation (`sequence=27294`, `rx_state=65`) was excluded in the
derived quality report; its evidence is listed in `analysis/summary.json`. Their original bytes and masks are
preserved. Counts describe file-buffer acceptance, not power-loss durability.

The host FIFO peaked at **45,987 bytes / 13 chunks**,
with maximum observed queue wait **194.60 ms**, and ended
with 0 queued bytes / 0 chunks.
The worker consumed 28,638 chunks in 21,013 groups.
Actual new plot draws averaged 5.20 FPS in the
measurement window under the ordinary 24 FPS timer. UI timer rate, new-data plot
draws and delivered CSI records/s remain different metrics.

The independent transmitter wire audit counted 39,757 round logs,
with 0 holes, 0 malformed frames and
0 drop-counter changes. Device boot identities,
receiver diagnostic-loss flags, observed channel intervals and deadline bounds
are retained in the summary and qualification report. Of
15,000 finalized 50 Hz/900 ms-grace bins,
14,897 had at least three receivers; 0 were all-missing.
Those are delivered-data availability masks, not simultaneous RF occupancy or
detector performance.

## Verification and limitations

The deterministic regression originally failed because blocking the recorder
also blocked USB draining. It now proves that subsequent input is read during
the storage stall, processed in order, and retains its earlier arrival timestamp.
Additional tests cover byte/chunk capacity, stale work, available-data grouping,
failed-recording ACKs, shutdown draining, historical formats and both live apps.
The full software suite passed **440 tests** before the final hardware run.

The final directory retains settings, source snapshots/hashes, CSI recordings,
raw journals, USB reference trace, actual drawn-frame timestamps and a viewer
screenshot. `analysis/summary.json` includes post-stop gateway counter deltas;
`analysis/qualification.json` contains the unchanged evaluator result;
`wire-audit.json` records independent reference decoding. Scripts are copied to
`diagnosis/`; `analysis/queue-windows.json` retains minute-level receiver queue
medians/maxima alongside the strict endpoint statistic. No raw recordings were
modified, and large artifacts remain ignored
by Git. Independent post-run USB discovery verifies transmitter radio-off and
gateway unconfigured.

This is a sustained healthy-path transport test with a visible viewer. Concurrent
phone video, physical power failures, long disk stalls, host disconnect recovery
and fall-detector accuracy were not qualified. A temporary RAM buffer cannot
recover data after process/power loss, or compensate indefinitely when average
processing capacity is below input rate.
