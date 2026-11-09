# Eight-batch window and early return

Both optimizations are implemented and available through explicit trial policies.
Early return shortened observed blank periods, but delivery gains were not
repeatable and median latency regressed. Normal collection therefore retains
the previous four-batch, deadline-return policy. No qualification threshold,
sensing rate, PHY rate, slot length or switching reserve was relaxed.

## Policies and implementation

| Policy | Outstanding batches | Early return |
| --- | ---: | --- |
| `configs/radio/espnow_transport.json` — default | 4 | Disabled |
| `configs/radio/espnow_transport_eight_batches.json` — trial | 8 | Disabled |
| `configs/radio/espnow_transport_early_return.json` — trial | 8 | Enabled; 5 ms idle grace |

The receiver has eight fixed batch buffers. A run uses only the configured
number. The 64-record pool, 500 ms retention, one application retry and
16-record slot submission limit remain in place. Complete envelopes remain at
most 1400 bytes; the current CSI format typically fits two records per envelope.
Batch construction respects the remaining record allowance. With eight batches,
cached-ACK polls are interleaved with fresh data so that polling eight retained
batches cannot consume the whole upload window before new data is attempted.
Bytes stay owned until host acceptance or expiry, including after an early return.

Early return requires an idle MAC sender and one of these conditions: the slot
submission budget is spent, no queued/outstanding work remains, no admissible
work has appeared for the configured idle grace, or no further send can fit
before the existing send cutoff. The hard deadline overrides a missing MAC
completion. The 50 ms slot remains a maximum authorization window, with the
original 5 ms departure guard and 10 ms return reserve.

After retuning to 5 GHz, the receiver sends the existing `CONFIRM_RETURN` status.
A matching request makes the transmitter resume sensing probes to that receiver.
The request does not close the grant or authorize another departure. Actual
sensing-frame reception and the subsequent `CAPTURE` status still provide return
proof, and the next departure remains behind the previous slot-end barrier.
Return requests stop after a second without sensing; a new valid sensing stream
can recover the receiver. Processor acceptance ACKs remain on the 2.4 GHz gateway
path. The deferred 5 GHz host-ACK relay was not implemented.

The trial policies use `CGCF` configuration version 2. It remains 108 bytes;
bytes 100–101 encode `early_return_idle_ms` and bytes 102–103 remain reserved.
Version 1 continues to require four or fewer batches, zero extension bytes and
deadline return. Historical policy loading and fingerprints are preserved.
Version-2 policies require compatible firmware on all three roles; USB rejection
aborts preflight before sensing starts. Tests cover that rejection path.
`CSIT` v4, `CGWY` v1, `CGAK` and raw CSI record encoding remain unchanged.

`CGQE` event 9 records an early-exit decision, submitted-record count and detail
code (1: completed budget/empty work or send cutoff; 2: idle grace). Event 10
records completion of the return channel API. `CGPR` records resumed sensing
probes. Status still timestamps the first subsequent sensing frame, so API return
and observed sensing recovery remain distinct. Startup cleanup clears the prior
run's transition timestamps rather than relabeling them under a new run ID.

## Hardware comparison

The verified hardware was one C5 transmitter, one C5 receiver
(`44:bd:8d:d0:b3:50`) and the XIAO C6 gateway (`10:bd:a3:9e:cd:68`). The main
runs each used 30 seconds of warm-up and a 60-second measurement. These are
single-receiver comparisons, not the required four-receiver, 300-second
qualification. Ambient traffic and room motion were uncontrolled.

| Metric | Previous policy | Eight batches, deadline return | Eight batches, early return with interleaving | Early-return repeat |
| --- | ---: | ---: | ---: | ---: |
| Valid records/s within one second | 41.08 | 40.25 | 46.23 | 30.15 |
| Delivered records within one second | 100% | 100% | 100% | 100% |
| Median delivery latency, including uncertainty | 53.33 ms | 53.54 ms | 468.86 ms | 489.86 ms |
| P99 delivery latency, including uncertainty | 493.51 ms | 454.06 ms | 516.14 ms | 525.45 ms |
| Median conservative blank/recovery interval | 42.63 ms | 42.64 ms | 29.18 ms | 31.08 ms |
| Maximum conservative blank/recovery interval | 44.28 ms | 45.81 ms | 45.55 ms | 46.85 ms |
| Record-pool peak | 33/64 | 31/64 | 30/64 | 32/64 |
| First-to-last queue-window median change | −3 records | 0 | +4 records | −1 record |
| Recovery deadlines uncertain | 2 | 10 | 1 | 25 |

No measured run met the 50-record/s requirement. The first interleaved run also
failed the fixed queue-stability test. Both interleaved runs lacked complete
grant/interval evidence; absence of a proven late recovery does not certify the
uncertain or missing cases. A one-receiver run cannot establish that the other
three receivers cover its absence or that four physical intervals never overlap.

The first interleaved run reduced median conservative blank duration by about
32%. Most early exits occurred at the existing send cutoff: the receiver returned
when further transmissions no longer fit, rather than waiting out unused time.
Five exits followed a spent slot budget or empty work. The measured full-run
median from departure to verified return-API completion was 12.55 ms, versus
29.22 ms in the capacity-only run. These local-clock API intervals differ from
the conservative, clock-bounded sensing-recovery intervals in the table.

Before interleaving, eight batches plus early return delivered 41.32 records/s
at 483.97 ms median latency and 30.18 ms median conservative recovery. It exposed
the cost of draining all cached ACK polls ahead of data. Interleaving improved
the next run, but the subsequent repeat did not sustain the throughput gain.
The trials do not establish the architecture's performance ceiling.

## Memory, verification and artifacts

The C5 linker reports 11,520 bytes for the eight-batch array, 5,760 bytes more
than four slots of the same type. All eight slots are statically allocated even
when a four-batch policy is selected. The identified receiver reported 47,316
free heap bytes and 42,956 minimum free heap bytes at the initial preflight.
This is one board's measurement, not a bound on every future workload.

ESP-IDF 6.1 builds pass for C5 transmitter/receiver and generic/XIAO C6 gateway.
`uv run pytest` passes 352 tests.
The identified boards were flashed. Protocol and C-module tests cover version-1
compatibility, version-2 size/CRC/limits, eight-buffer ownership, whole-record
packing, stale/duplicate ACKs, interleaving, idle versus busy-sender early exits,
hard deadlines, and a return request which cannot authorize the next departure.
Host tests cover both policy versions and rejection of an incompatible gateway.
Hardware host-disconnect testing verified transmitter radio-off and restart
without board reset. A final startup regression test covers clearing old-run
transition timestamps; the post-fix ten-second smoke run completed.

Artifacts are local and ignored by Git at
`data/experiments/gateway/early-return-20261101T164311Z/`. They include raw per-run
envelopes/events/availability, derived `comparison.json`, policy files, firmware
images/flash reads, source snapshots, memory output and build/test logs. The
gateway flash read is the authoritative baseline image; a cached gateway build
in the same directory was not assumed to identify the running image. Earlier
recordings remain unchanged.

The first restored-default smoke attempt stopped at discovery while the gateway
USB link was absent. After reconnection, the retry completed with four batches
and early return disabled. Its one-second warm-up and ten-second measurement
delivered 401 valid records (40.1 records/s), all within one second. Median/p99
delivery latency was 41.31/61.74 ms. The record pool peaked at six, its median
growth was zero, and all 134 observed recovery intervals were conservatively
before their slot deadlines, with complete grant/interval evidence for this
measurement. No early-return decisions occurred. Transmitter radio-off was
verified after shutdown. Artifacts are in `restored-default-retry/`; the original
failed attempt remains preserved separately.

This completes the operational startup/data/shutdown smoke check. The rate
remains below 50 records/s, and a ten-second single-receiver run does not qualify
the four-receiver system or establish detector accuracy.

The receiver initially delivered CSI while not answering USB discovery. A
read-only eFuse MAC check followed by the tool's hard reset restored framed USB
status; all three identities were then discovered. The cause of the lost USB
response was not isolated. The reset occurred after recording and shutdown.

To run either trial, provide its explicit policy with `--gateway-config` to
`csi-gateway-benchmark --mode probe`, the viewer or collector, alongside the
verified inventory/profile and both USB paths. Normal collection retains its
four-physical-receiver requirement. See [the operating guide](../espnow-gateway.md).
