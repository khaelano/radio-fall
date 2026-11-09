# Higher-throughput ESP-NOW trials, 2 November 2026

## Scope and implementation

These experiments target 80 unique valid records/s per receiver, accepted within
one second of the sensing reference time. They retain the existing architecture,
single-owner return interlock, 1400-byte complete envelopes, raw CSI encoding,
subsecond delivery metric and bounded queues. No detector changes or accuracy
claims are included. The original four-receiver qualification requirement remains
separate; a paced single receiver cannot qualify four radios.

CGCF-v6 retains the 108-byte configuration and adds a two-bit backhaul MCS index
in byte 103 bits 3–4. Values 0–3 select explicit HT20 MCS0–3 with long guard
interval on both receiver/gateway peers. Higher bits remain invalid; older
configuration versions reject the new bits and retain their original PHY.
The 5 GHz sensing PHY remains HE20 MCS0. The configured PHY is included in the
transport fingerprint, and the gateway reports its negotiated MCS in status.
The host rejects transmitter/gateway firmware without v6 support before start;
receiver readiness requires adoption of the matching sensing configuration.

Radio profile schema v2 explicitly permits 50–120 Hz on 5 GHz C5 sensing links.
Schema-v1 profiles retain 50–100 Hz, preserving the historical BLE contracts.
The profile/NVS binary layout and raw record encoding are unchanged; firmware
validates the extended rate only on 5 GHz, and transport versions below v6 cannot
use extended profiles. The new 120 Hz profile has its own rate fingerprint.

The receiver's existing opt-in event worker submits without a fixed wait and
wakes on MAC completion, retaining one sender and the original return cutoff.
The optional `sdkconfig.performance160` overlay fixes CPU operation at 160 MHz
with dynamic frequency scaling disabled. Normal builds retain their 80 MHz cap
and automatic DFS initialization. This is a CPU-policy comparison, not a claim
that frequency alone accounts for a measured difference. Status reports the
configured CPU maximum. Normalized SDK comparisons differ only in the CPU/PM
policy and, where selected, event-worker enablement. The bounded diagnostic
queue grows from 32 to 128 entries to retain larger burst traces; CSI queue
capacity remains 64 records. All trial controls use this same instrumentation.

The benchmark's explicit `--target-records-s 80` applies the stronger rate target
to reports. The default remains 50; this experiment does not lower a threshold,
lengthen a slot automatically or replace measured timing with simulation.

## Hardware procedure

Only rx-1 (`44:bd:8d:d0:b1:4c`) is powered, with the C5 transmitter (USB identity
`44:bd:8d:d0:b6:80`, radio identity `1a:00:00:00:00:00`) and XIAO C6 gateway
(`10:bd:a3:9e:cd:68`). Factory application partitions were backed up directly
from all three identified boards before flashing. The C6 built-in antenna
selection is retained. Placement is not a controlled room-coverage study.

All comparisons use channel 44 for sensing, channel 6 for backhaul, 125 ms
maximum upload authorization, a 600 ms per-receiver minimum revisit, 750 ms
record lifetime, 900 ms availability grace, four batch buffers and 64 record
slots. Start/send/return guards stay 5/10/10 ms. Changing PHY never shortens
these reserves. MAC timing summaries are enabled throughout. Initial screens
use 5 s warm-up/30 s measurement; selected combinations receive 30 s warm-up/60 s
repeats. These durations are probes, not four-radio sustained qualification.

The staged matrix compares legacy/event workers at 80 MHz, receiver 160 MHz,
receiver/gateway 160 MHz, all three devices at 160 MHz, backhaul MCS0–3, a
64-record allowance, and finally 120 Hz sensing with 48/64-record allowances.
An acknowledged 120 Hz combination additionally tests whether end-to-end
acceptance can be retained. ACK-less runs use zero application retries;
acknowledged trials use two with a 150 ms timeout. All other policy fields and
raw CSI bytes are retained.

Artifacts, source/binary hashes, SDK settings, policies, backups and raw journals
are under `data/experiments/gateway/throughput-20261102T074745Z/`. Candidate
selection for further experiments is distinct from qualification: it ranks
healthy screens with bounded stable queues and no observed after-deadline
recovery, while incomplete evidence remains explicitly failed.

## Initial measurements

Each screen below has a 5 s warm-up and 30 s measurement unless specified.
Rates are unique validated records accepted within one second, including clock
uncertainty. The sensing rate is 80 Hz until the last six rows.

| Treatment | Sensing Hz | Timely records/s | Queue check |
| --- | --- | --- | --- |
| Legacy worker, all devices capped at 80 MHz | 80 | 50.73 | pass |
| Event worker on receiver, same CPU policies | 80 | 55.00 | fail, +4 growth |
| Receiver event worker and fixed 160 MHz | 80 | 65.00 | pass |
| Receiver and gateway fixed 160 MHz | 80 | 66.13 | pass |
| All three fixed 160 MHz, MCS0 | 80 | 66.67 | pass |
| All three fixed 160 MHz, MCS1 | 80 | 66.60 | pass |
| All three fixed 160 MHz, MCS2 | 80 | 65.93 | pass |
| All three fixed 160 MHz, MCS3 | 80 | 66.60 | pass |
| MCS0 bracket repeat | 80 | 65.80 | pass |
| MCS0, allowance increased to 64 | 80 | 66.40 | pass |
| MCS0, allowance 48 | 120 | 79.27 | fail, pool full |
| MCS0, allowance 64 | 120 | 85.07 | fail, pool full |
| MCS0, allowance 64, application ACKs | 120 | 71.57 | fail, pool full |
| MCS0, allowance 64, 30/60 s repeat | 120 | 88.40 | fail, pool full |
| MCS0, allowance 64, ACKs, 30/60 s repeat | 120 | 74.68 | fail, pool full |
| MCS3, allowance 64 | 120 | 98.47 | pass |
| MCS3, allowance 64, application ACKs | 120 | 95.23 | fail, pool full |

At 80 Hz, the receiver's capture counter was approximately 65–67 records/s;
CPU/worker improvements brought delivery close to this capture limit. MCS3
reduced measured mean MAC completion from 2528 to 1302 microseconds, but cannot
recover packets missed on the other band. The nearly tied 80 Hz delivery rates
cannot establish a statistically preferred PHY; MCS0 was selected by the
initial screen-ranking code and MCS3 was independently tested under the higher
120 Hz load to measure service headroom.

One initial matrix attempt stopped at a provisioning helper error before sensing;
that helper was corrected to provision the two C5 boards individually. The
first 120 Hz acquisition also stopped before measurement because the host
reference parser retained a 100 Hz minimum period. A real-round regression
reproduced that failure; the parser now checks the exact integer period for the
configured rate, with legacy bounds retained for callers without a profile.
The interrupted attempt is preserved and excluded from rate comparisons.

Receiver queue peak is a boot-level counter. Early high-rate cases reused a
boot and may inherit an earlier full-pool peak; those original queue-check
failures remain failed. Later high-rate cases explicitly reset only the
identified receiver before starting the clock fit and measurement. Reset logs
and boot identities distinguish these cases. The MCS3 screens and sustained
run use fresh receiver boots.

The MCS3 ACK-less screen passed rate/latency/queue checks, so it received a
30 s warm-up/300 s single-receiver measurement. That run delivered 90.69 timely
records/s but filled the 64-record pool and failed the fixed queue-growth check
(+1.5 records). All 500 mapped recoveries were before deadline; complete timing
evidence still failed due to an unproven grant. This is a throughput result,
not qualification. The 128-entry diagnostic queue reported no event loss.

## Retention-sized queue follow-up

At 120 Hz, 750 ms retention can contain 90 records before allowing for an
in-flight batch. Simply growing the pool would consume 23,040 more bytes while
the 64-slot receiver had only 42,360 free heap bytes (37,996 minimum after boot).
The control receive queue was also reserving 1400 payload bytes in each of
32 entries despite receivers accepting control messages no larger than 180.

A role-specific queue initializer retains 32 entries but stores only the allowed
payload: receiver 180 bytes, transmitter 96, gateway the full 1400. Oversized
messages are rejected and counted. CSI acquisition and gateway envelopes retain
their complete original bytes. Reducing receiver control storage saves 39,040
bytes, more than the extra record storage, for a projected net 16,000-byte saving.

CGCF-v7 explicitly permits a bounded 96-slot pool. Versions 1–6 retain their
64-slot maximum and fingerprints; the normal active capacity remains 64.
The 96-slot experiment keeps the 64-record upload allowance, 750 ms lifetime,
125 ms window, 600 ms revisit, guards and 80-record/s target unchanged. This
sizes memory for the already selected rate/retention budget; it does not raise
the delivery deadline or redefine a failed earlier run as a pass.

The new receiver reported 58,344 free heap bytes and 53,980 minimum after boot:
a measured net improvement of 15,984 bytes. All queue depths and the full CSI
encoding are retained. With this same firmware, an active-64-slot control
screen delivered 98.83 records/s but failed queue growth (+2). The active-96-slot
ACK-less screen delivered 98.47/s with +1 growth and passed the unchanged queue
check. The acknowledged screen delivered 97.63/s with -10 growth and also passed.
Both exceeded 80/s with subsecond delivery. The acknowledged screen was preferred
for the first extended validation because it retains host-acceptance feedback.

Its 30 s warm-up/300 s measurement delivered 93.84 timely records/s and stayed
below 79/96 slots, but the first/last median queue difference was +13 records,
so the existing queue-growth criterion failed. All 500 mapped recoveries were
before deadline; complete timing evidence remained incomplete. A matched
300 s ACK-less run is collected separately to isolate feedback-related queue
retention. Both outcomes remain in the report; a failed check is not relaxed.



## Final controlled comparison and restored state

The final ACK-less comparison uses the same v7 firmware, fixed-160-MHz policies,
event worker, 120 Hz sensing, MCS3, 125/600 ms window/revisit, 96-slot pool,
64-record submission allowance and 750 ms retention as the acknowledged case.
It has its own receiver reset, 30 s warm-up and 300 s measurement. Results:

| Application feedback | Valid records/s | Subsecond fraction | Delay p99 / max (ms) | Queue peak | Median growth | Queue check |
| --- | --- | --- | --- | --- | --- | --- |
| Host acceptance ACKs | 93.84 | 100% | 746.27 / 802.47 | 79/96 | +13 | fail |
| ACK-less | 95.77 | 100% | 731.13 / 802.55 | 79/96 | +1 | pass |

The ACK-less run delivered 28,732 unique valid records in the measurement window
and passed the explicit 80-record/s rate, latency, clock-alignment and queue
checks. Median delay was 345.09 ms. Individual one-second rates were 51–108
(median 94), with a longest timely capture gap of 350.00 ms. The result exceeds
80/s on average; it does not guarantee at least 80 records in every second.
There was one receiver boot and no diagnostic-event loss. Gateway status samples
showed matching received/forwarded counts, zero observed USB errors, and no
application ACKs or polls. These observations do not prove loss-free reception
before the gateway or recoverability without feedback.

Both 300 s cases had 500 mapped recoveries conservatively before deadline,
zero mapped after-deadline/uncertain intervals, and one unproven grant (551) in
the current report. Complete timing evidence remains false. Only one physical
receiver was powered, with its revisit artificially paced; the other receivers'
RF traffic, transmitter fan-out, gateway aggregate load and combined availability
were not reproduced. Neither run is four-receiver qualification, and no detector
accuracy or post-switch phase-stability result is inferred. The acknowledged
run remains failed on queue growth despite its sufficient delivered rate; it is
not promoted by substituting its short-screen outcome.

After the ACK-less sustained run, receiver free heap was 58,108 bytes and the
boot minimum was 37,884 bytes. These are actual post-load measurements from
`receiver-96-slot-noack-postrun-heap.json`. The similarly named generic postrun
snapshot was also taken after this ACK-less run, not the earlier acknowledged
run. The observed memory budget supports this single-board experiment; a full
four-radio fault/aggregate-load qualification remains necessary.

All three original application partitions were restored after returning both
C5s to the 80 Hz profile. The final unrestricted-default ten-second smoke
delivered 42.6 records/s, with stable queues, 211.95 ms p99 and 243.97 ms maximum
delay; all delivered records were subsecond. This smoke uses a different slot,
retention and revisit policy and is not a control for the paced throughput tests.
The original four-peer transmitter roster was then reprovisioned. A separate
configuration-only four-receiver handshake and stop both returned `ok`, without
starting sensing. The boards are left running their original applications and
normal defaults, with sensing stopped. Candidate configurations and upgraded
firmware source are available for a later explicitly identified four-board
flash/qualification; no default configuration was promoted automatically.

## Software verification

`uv run pytest` passed 401 tests. Actual C/Python contracts cover rate/profile
versions, HT20 peer-rate selection, invalid flags/capacities, 96-slot retention,
control-queue payload bounds and unchanged sender ownership/deadline behavior.
Host tests cover configured 120 Hz round periods, incompatible firmware,
startup/shutdown, validation, deduplication, recorder failure and the stronger
80-record/s target. Historical BLE fixtures remain readable. The reference-log
regression was observed failing before its fix.

ESP-IDF 6.1 builds passed for C5 transmitter at normal/fixed-160-MHz policies,
C5 receiver legacy/event-80/event-160, generic C6 gateway, and XIAO C6 gateway at
normal/fixed-160-MHz policies. All eight variants were rebuilt after the v7
memory changes. Firmware/source hashes, build logs, SDK settings, reset logs and
all failed attempts remain with the experiment. Ruff checks and
`git diff --check` passed. No commit, detector change or hardware success beyond
the stated single-receiver measurements is implied.

## Receiver deployment after the experiments

On 2 November, rx-2 (`44:bd:8d:d0:b3:50`), rx-3
(`44:bd:8d:d0:be:9c`) and rx-4 (`44:bd:8d:d0:b6:6c`) were connected over
USB and upgraded to the tested event-worker, fixed-160-MHz C5 receiver image
with CGCF-v7 support. Its SHA256 is
`61615774e19b674911a58360104f25113c8362fdfafb67b7056a104be6d9c13c`.
Each bootloader identity was verified before writing; the original factory
application, NVS and partition table were backed up. Flashing replaced only
the factory application partition.

All three were provisioned individually using the complete ordered inventory
in `configs/radio/gateway_inventory.json` and the 120 Hz channel-44 profile.
After a hardware reset, each reported ready with fingerprint
`8b28a906a0fbcd1f`, the event worker, 160 MHz CPU policy, sensing protocol v4
and transport configuration support through v7. Deployment logs, backups,
profile/inventory snapshots and reset verification are preserved under
`data/experiments/gateway/deploy-receivers-20261102T114515Z/`.

The transmitter, rx-1 and gateway were disconnected during that first batch.
After reconnecting those three and disconnecting rx-2–4, all three were upgraded
to the tested fixed-160-MHz images with v7 support. The transmitter and rx-1
were provisioned with the same full ordered inventory and 120 Hz profile;
rx-1 uses the same event-worker image as rx-2–4. The gateway image retains the
XIAO C6 built-in antenna selection. Each bootloader identity was checked,
original application/NVS backed up, and readiness verified after reset. Images:

| Board | Application SHA256 |
| --- | --- |
| Transmitter | `677060c7e781d28735d7b9869826c514eaf218183de31da3b3b6fb250de7ceeb` |
| rx-1 | `61615774e19b674911a58360104f25113c8362fdfafb67b7056a104be6d9c13c` |
| XIAO C6 gateway | `7e211e3f5d4e2dc1d69a655e0829c8635670326582910181fe3916d49f3c79f3` |

A configuration-only check confirmed that the transmitter accepts the full
four-peer roster at 120 Hz with the v7 MCS3/96-slot ACK-less policy. The gateway
accepted the same configuration and reported channel 6, MCS3 and the expected
transport fingerprint. Both stop commands returned `ok`. A final status check
confirmed transmitter radio-off and gateway unconfigured. The policy is selected
at run startup rather than persisted by radio provisioning. No sensing was
started and no four-receiver qualification was performed. Second-batch logs,
backups, snapshots and verification are under
`data/experiments/gateway/deploy-core-20261102T115029Z/`.
