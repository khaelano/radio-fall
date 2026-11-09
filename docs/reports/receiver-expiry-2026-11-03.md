# Receiver retention investigation

The receiver buffer remains at 96 records, with 750 ms retention. This
investigation separates how long a measurement waits before transmission from
how long its receiver-side allocation remains occupied afterward. The UI's
cumulative `Expired` counter combines both and cannot establish how many unique
measurements are missing from the laptop recording.

## Evidence from preserved recordings

The existing channel-11 five-minute viewer recording contains 1,616 records in
batches subsequently reported as expired by their receivers. Every observed
batch-expiry identity joined to an envelope already stored in that same run's
`envelopes.bin`. No receiver restart occurred within that run. These were expired
receiver-side copies, not absent laptop records.

A more recent collection run (`data/raw/sessions/20261103T102647134517Z/`, transport
run `8b80c3eea6becdbe`) shows the same pattern:

| Receiver | Observed unsent-record expiry events | Records in expired batches already stored on laptop |
| --- | ---: | ---: |
| rx-1 | 49 | 592 |
| rx-2 | 11 | 724 |
| rx-3 | 10 | 436 |
| rx-4 | 0 | 404 |

These are counts in received queue-event diagnostics, not a claim of complete
on-air diagnostic delivery. Counter snapshot endpoints and event observation
windows differ. The receiver's diagnostic-loss flag detects its local queue
loss; a clear flag does not prove every radio diagnostic reached the host.
In particular, reconstructing exact outstanding-batch occupancy from incomplete
creation/completion diagnostics is unsafe and was not used as a result.

Normal return-to-return revisit intervals were approximately 567 ms: the four
125 ms slots also require announcement, switching and verified-return handoff.
In the newer run, observed maximum revisit intervals were 574–575 ms. Once a
batch was built, its first submission followed in roughly 0.29 ms median.
Delivered samples typically became available on the laptop in about 290–320 ms
median. Thus the ordinary delay is mostly waiting for the upload turn, rather
than waiting hundreds of milliseconds after a batch is built.

There are genuine slow-send cases too. An earlier run recorded a 76.83 ms MAC
completion and a 1,123 ms receiver revisit gap. Missing one upload opportunity
can push old unsent samples beyond 750 ms. The newer run's 70 observed unsent
expiries are separate from its 2,156 already-delivered batch-copy expiries.
A precise attribution of each unsent expiry needs an instrumented hardware
comparison; delayed delivery alone does not prove loss of a recording.

## Reproduced ownership race

The ACK-less worker checked for a completed send at loop entry, then processed
other work before checking whether it could send another batch. A MAC callback
could complete in that interval:

1. Loop-entry cleanup sees the previous send still busy and retains its owner.
2. The callback completes; the shared sender becomes idle.
3. The upload branch starts another batch and replaces `unconfirmed_send`.
4. The old batch's allocation remains owned, despite its transmission having
   completed. Its records are eventually released through expiry.

This also consumes one of the four outstanding-batch entries until expiry,
which can reduce upload capacity. The matched probes below establish its effect
on owned-copy expiry. Its causal contribution to subsequent unsent expiry has
not been isolated from radio and startup variability.

`tests/radio/test_receiver_completion.py` compiles and executes the real
`gateway_io.c` and receiver `gateway_transport.c` with deterministic IDF stubs.
It injects the actual completion callback after loop-entry cleanup but before
upload admission. Both successful- and failed-MAC-completion cases failed on the
old source: the preceding record remained allocated. Both pass with the fix; the full suite passes 509 tests.
The test also verifies that the new send's bytes remain owned until its own
callback and that completion does not increment expiry.

The receiver now reaps the completed owner at upload admission and requires that
owner to be cleared before permitting another send. If completion arrives too
late for that check, the next worker iteration handles it. Slot/return guards,
MAC/application ACK semantics, buffer capacity and expiry duration are unchanged.

## Validation status

The corrected C5 receiver builds with ESP-IDF 6.1, the event-driven upload worker
and fixed 160 MHz CPU settings. The app image is 941,232 bytes (about 919 KiB).
Each board's actual partition table was checked before its app-only write;
all four factory partitions are 1,500 KiB. NVS was preserved.

Receiver rx-2 (`44:bd:8d:d0:b3:50`) has been updated after a private full-flash
backup and inspection of its actual 1,500 KiB factory partition. Only the app
at `0x10000` was written; NVS and the partition table were preserved. Discovery
after reboot verified its identity, event worker, 160 MHz setting and unchanged
sensing fingerprint `8b28a906a0fbcd1f`.

Matched gateway probes used 5 s warm-up and 60 s measurement with the same
96-record/750 ms policy. Only rx-2 changed firmware between probes:

| Receiver | Expiry counter increase before | Expiry counter increase after | Observed records before / after |
| --- | ---: | ---: | ---: |
| rx-1 | 90 | 74 | 6,556 / 6,556 |
| rx-2 (updated) | 154 | 0 | 6,572 / 6,573 |
| rx-3 | 162 | 144 | 6,540 / 6,537 |
| rx-4 | 112 | 98 | 6,550 / 6,550 |

Observed unsent-expiry events and send-error counter increases were zero for
every receiver in both probes. The corrected receiver stopped accumulating
owned-copy expiries while all three unchanged controls continued. This supports
the ownership-race diagnosis; these short probes do not establish long-term
loss-free operation. Receivers rx-1, rx-3 and rx-4 were subsequently backed up
and updated by the same app-only procedure, with identity and unchanged profile
verified afterward. All four deployment manifests identify the same app SHA-256
`48cbed3555d0ef3a64e8c02ce24408604a5751506cf201d0ba22573d3d08b847`.

The first combined attempt recorded 312.76 s of transmitter rounds and 123,537
records before a C6 transmitter-reference `peer_timeout` aborted the planned
30 s warm-up/300 s measurement. No receiver reported an owned-copy expiry.
Rx-1 through rx-3 had zero expiry increases; rx-4 increased by eight, with all
received unsent-expiry diagnostics arriving within the first four seconds of
warm-up. Its affected grant (24) had 13 MAC completions, two failures, and a
23.078 ms maximum completion. The previous grant had 28 completions with no
failures and a 3.094 ms maximum. Grant 24 returned with 30 records still queued;
some reached their lifetime limit before the next upload opportunity. This
demonstrates genuine waiting after an incompletely drained upload turn, separate
from the completed-owner race. It does not identify the RF cause of the slow
completions.

A derived 280 s segment after 30 s warm-up delivered 98.825–98.864 timely
records/s per receiver, all subsecond, with stable queues and complete observed
grant evidence without cross-receiver overlap. The complete planned test did
not finish and is not qualified. Gateway USB forwarding errors were zero;
the later relay fault required restarting both C6 reference endpoints. A second
attempt aborted on the same timeout after 43.67 s of transmitter-round coverage;
all four receiver expiry/drop/send-error deltas were zero. No gateway receive
rejections or USB forwarding errors were reported. Both failures leave wireless
reference reliability unresolved, despite successful receiver ownership cleanup.

The monitored repeat completed 30 s warm-up and the full 300 s measurement after
a coordinated C6 reset. Both C6s were connected to laptop USB; the companion's
setup interface was polled every two seconds while sensing/control data still
used the UART/ESP-NOW relay through the gateway. This also changed the companion
power path, so the successful repeat does not isolate power, reset state or
monitoring as the explanation for the preceding timeouts.

| Receiver | Delivered records in 300 s | Timely records/s | Conservative latency p99 (ms) | Expiry / drop / send-error increases, full run |
| --- | ---: | ---: | ---: | --- |
| rx-1 | 29,639 | 98.797 | 486.37 | 0 / 0 / 0 |
| rx-2 | 29,666 | 98.887 | 485.76 | 0 / 0 / 0 |
| rx-3 | 29,651 | 98.837 | 486.07 | 0 / 0 / 0 |
| rx-4 | 29,658 | 98.860 | 485.79 | 0 / 0 / 0 |

All 118,614 delivered records in the measurement were subsecond. No owned-copy
or unsent-expiry events were observed across the full 331.58 s round coverage,
and all receiver expiry counter increases were zero. Queue medians did not
grow; reported peaks were 56–78/96. Gateway USB errors, relay drops, companion
UART errors and MAC failures were zero. Eleven companion relay retransmissions
were recovered without fault. The 171 companion status requests all received
replies. Maximum host USB queue wait was 95.71 ms with the unchanged 200 ms guard.

The benchmark passed its fixed 80-record/s transport target, stable-queue and
observed channel-evidence checks. Complete grant evidence showed no overlapping
upload intervals; all 2,119 individual return/deadline comparisons remained
uncertain, so this does not establish each return's deadline compliance. The
transmitter reported no round-log drops. Transmitter radio-off, unchanged sensing
profile, gateway stopped, and both relay endpoints ready without fault were
verified afterward.

Artifacts are in `all-four-monitored/` beneath the experiment directory,
including `validation-summary.json`, companion status samples and the original
gateway journal with `qualification.json`. The two aborted attempts remain in
`all-four-updated/` and `all-four-updated-repeat/`. This validates the receiver
ownership fix on all four devices; longer unattended reference reliability and
operation on the previous companion supply remain unresolved.

Read-only debug analyses and native/build logs are under
`.codex-build/receiver-expiry/`; a new unchanged-firmware baseline is retained in
`data/experiments/gateway/receiver-expiry-20261103/`. Those ignored artifacts
supplement the original immutable recordings. Per-receiver deployment manifests
and the matched probe artifacts are retained under that experiment directory;
private flash backups are excluded from version control. Radio configuration
and retention settings remain unchanged.
