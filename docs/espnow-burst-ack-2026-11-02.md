# Upload worker and gateway ACK experiments, 2 November 2026

These experiments test the two measured bottleneck candidates from the
four-receiver qualification: approximately 5 ms between batch submission events,
and gateway MAC failures while returning processor-acceptance ACKs. The previous
trace delivered about four records per receiver turn with a roughly 303 ms
four-receiver cycle. Its 13 records/s per receiver failed the unchanged
50-record/s requirement. More retention alone does not increase burst capacity.

## Scope and controls

The verified inventory is `configs/radio/gateway_inventory.json`. Only rx-1
(`44:bd:8d:d0:b1:4c`) has USB data available for receiver flashing. The other
three receivers remain powered and unmodified. The C6 gateway
(`10:bd:a3:9e:cd:68`) is independently accessible. The transmitter
(`1a:00:00:00:00:00`, USB identity `44:bd:8d:d0:b6:80`) retains the corrected
four-peer roster. Exact factory application partitions were backed up from
rx-1 and the gateway before any flashing; their provisioning/NVS partitions
were not changed.

All treatment runs retain channel-44 HE20 MCS0 80 Hz sensing, channel-6 HT20
MCS0 backhaul, 50 ms slots, 5 ms departure guard, 10 ms send guard, 10 ms return
reserve, 64 record slots, four outstanding batches and 16 submitted records per
turn. Transport policy stays at 750 ms retention, two retries, 150 ms ACK
timeout and 900 ms availability grace. Early return remains disabled. The
original 500 ms/one-retry policy is used only for the final restoration smoke.

The gateway activity-window screens have 5 s warm-up/30 s measurement. Baseline,
receiver-worker and combined screens have 30 s warm-up/60 s measurement.
These are exploratory screens, not the required 30 s warm-up/300 s sustained
qualification. The first gateway-50 screen overlapped background compilation;
a second 50 ms control was run without compilation. Repeated control variation
is retained rather than treating the first comparison as an isolated effect.
The later receiver-worker tests run without background builds.

Original journals, inventory/policy snapshots, application backups, source
snapshots, flash/build/test logs and derived comparisons are retained under
`data/experiments/gateway/burst-ack-20261102T003439Z/`. Existing recordings are
not modified. Per-receiver firmware treatment is identified by flash evidence
and USB status; the three power-only receivers are verified over radio but
cannot have their application binaries read over USB in this setup.

## Implemented experiments

`CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS` in the gateway limits unsolicited immediate
host-ACK forwarding to recently observed receiver activity. The default 50 ms
preserves the original slot-length window (still capped by the configured slot).
The trial uses 5 ms. Genuine host acceptance is cached before this test; skipping
immediate forwarding does not fabricate acceptance or discard it. Existing
receiver polls can retrieve it later. Freshness of radio activity is a heuristic,
not a measured departure deadline or proof that the receiver remains on-channel.

Gateway USB status reports the selected build setting, skipped-old/busy ACKs,
submission errors, and age totals/maximum/counts within 2, 5 and 10 ms. Ages
measure time since the most recent frame from that receiver, not a complete
host/gateway round-trip. MAC failures are separate from API submission and
processor acceptance. These build-time experiments are recorded in status,
firmware hashes and experiment metadata; they do not add fields to CGCF or
change its transport fingerprint.

`CONFIG_CSI_GATEWAY_EVENT_UPLOAD` is an opt-in receiver worker experiment,
disabled by default. Upload submissions use zero fixed wait; the existing single
in-flight sender ownership remains enforced. A short callback wakes the worker
on MAC completion or queued incoming messages. The worker waits on notification
with a maximum one-tick timeout during upload, so missing callbacks cannot make
it wait indefinitely. It checks the existing cutoff and returns regardless of
pending records or ACKs. Radio operations remain outside callbacks. Receiver
USB status identifies `event` or `legacy` upload mode. This differs from the
previously reverted callback-wait experiment: the worker uses nonblocking
submission and event wakeup rather than adding a blocking wait to each send.

The gateway-only screens keep all receiver applications unchanged. The worker
screen changes rx-1 only and restores the original gateway application; the
other three receivers provide concurrent controls. The combined screen applies
the 5 ms gateway limit with only rx-1 using the new worker. It cannot establish
performance when all four receivers use the new worker.

## Hardware results

| Treatment | rx-1 | rx-2 | rx-3 | rx-4 | Gateway MAC failures / ACK submissions |
| --- | --- | --- | --- | --- | --- |
| Original baseline | 13.20 | 13.27 | 13.27 | 13.17 | 147 / 2421 |
| Gateway 50 ms, first screen | 13.30 | 13.27 | 13.60 | 13.20 | 488 / 909 |
| Gateway 5 ms | 13.13 | 13.13 | 13.40 | 12.93 | 1 / 464 |
| Gateway 50 ms repeat | 11.93 | 11.60 | 12.13 | 11.80 | 144 / 866 |
| Event worker on rx-1 only | 18.53 | 13.33 | 13.67 | 13.27 | 380 / 2640 |
| rx-1 event + gateway 5 ms | 15.27 | 13.42 | 13.60 | 13.33 | 3 / 1243 |

Rates are unique valid records/s accepted within one second during the stated
measurement windows. Gateway counts cover the sampled full run, including
warm-up/draining, so durations differ. They are MAC failures on the gateway's
ACK-response path, not a count of missing CSI records. All received envelopes
were forwarded, and no USB write errors were reported in these screens.

Changing only rx-1's worker increased its rate from 13.20 to 18.53 records/s
(40.4%), while unchanged receivers stayed at 13.27–13.67 records/s. Its median
fresh submissions rose from four to six records per active turn, and median
submission-event spacing fell from about 5 ms to 4.03 ms. The rate gain supports
firmware pacing as a bottleneck, but it remains far below 50 records/s.

The gateway's 5 ms activity limit reduced failed MAC transmissions sharply
without a comparable delivery-rate increase. Both 50 ms controls had higher
failure counts; their differing rates/failure fractions also show variability.
The combined treatment delivered 15.27 records/s on rx-1, below the event-worker
screen's 18.53. These changes cannot be assumed to add their benefits. The
combined gateway recorded three MAC failures, but improved ACK success alone
did not clear the upload-capacity limit.

All delivered records remained within one second. The existing return reserves
and single-owner interlock were retained. These results do not establish that
the MAC driver itself has no timing limit; batching, worker execution, radio
completion and channel switching jointly determine the usable service window.

| Treatment | rx-1 delay p99 / max (ms) | Return before / after / uncertain | Complete evidence |
| --- | --- | --- | --- |
| Original baseline | 758.58 / 761.14 | 798 / 1 / 1 | False |
| Gateway 50 ms, first screen | 770.36 / 777.21 | 401 / 0 / 0 | True |
| Gateway 5 ms | 759.06 / 770.78 | 397 / 2 / 0 | True |
| Gateway 50 ms repeat | 761.62 / 763.65 | 374 / 7 / 4 | False |
| Event worker on rx-1 only | 758.06 / 760.18 | 801 / 0 / 0 | True |
| rx-1 event + gateway 5 ms | 758.48 / 764.97 | 791 / 3 / 3 | True |

Per-receiver one-second rate distributions, queue checks, longest gaps,
availability masks, unproven grants and the remaining latency statistics are
retained in `comparison.json` and original qualification reports. Mask grace
remains 900 ms for treatments; no late arrivals revise finalized bins. None of
these treatments qualifies four receivers at 50 records/s each.

## Power observation and restoration

The user reported that the three power-only receivers share a USB hub. The
power source was not changed as part of these firmware comparisons. Each
receiver and the gateway retained one boot identity within the baseline, worker
and combined runs, with no observed acquisition restart. The experimental
builds enable brownout detection. This does not measure supply voltage or rule
out RF degradation from transient supply dips; no controlled supply swap or
oscilloscope measurement was performed. Later USB detach events occurred after
the recordings ended and do not establish a power cause for their throughput.

The exact original gateway and rx-1 application images were restored. The
final 1 s warm-up/10 s default-policy smoke delivered 13.2, 13.4, 13.6 and
13.2 records/s, respectively. All delivered records were subsecond; all 134
observed recovery intervals were before deadline with complete evidence and
no mapped overlaps. Host stop/draining completed. No further firmware was
flashed after that restoration. A later USB check could not reverify all three
data-connected boards because the transmitter and rx-1 had been disconnected.
The four-peer provisioning and original transport defaults remain preserved.

## Software verification

The replayed four-receiver throughput check failed at 12.85–13.00 records/s.
The actual legacy worker in a deterministic timing harness sent four records
for both nominal modes, so the new regression failed before the worker change.
With the event worker, the same simulated radio timing clears more records
without extending the slot. This is a software check, not a hardware result.
Tests also exercise genuine host-ACK caching/retrieval after the immediate
window closes, old run/boot rejection, busy sender ownership and wakeup before
or after incoming messages. Default and experimental gateway windows are tested
separately. Final checks are recorded below.

The full suite passed 365 tests, including both configured ACK windows and the
legacy cached-build default. C5 transmitter, legacy C5 receiver, generic C6 and
XIAO C6 builds passed with ESP-IDF 6.1. The event-worker C5 image and both
experimental C6 images also built successfully. Existing C6 build directories
initially lacked the newly added Kconfig symbol; reconfiguration and a legacy
50 ms fallback fixed that compatibility check. No experimental flag was enabled
by default.

The event worker remains an opt-in implementation with a measured single-board
gain. The 5 ms gateway heuristic remains experimental because lower MAC failure
counts did not establish better delivered completeness or four-receiver rate.
Neither all-four event-worker performance nor a sustained combined qualification
was measured. Future bulk-window experiments are separate from these screens.
