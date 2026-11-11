# USB / ESP-NOW endurance measurement, 3 November 2026

The four-receiver system completed a 30-second warm-up followed by a 1,800-second
measurement. Each receiver averaged 98.465–98.755 usable records/s within one
second, exceeding the unchanged 80-record/s benchmark target. Every delivered
record met the one-second limit including clock uncertainty. Queues stayed
bounded, all six devices retained their observed boot identities, and complete
grant evidence showed no overlapping receiver upload intervals.

The run was not loss-free. The gateway reported one USB forwarding failure,
receiver expiry counters increased, and four recorded CSI observations had
nonzero driver receive-status flags. Excluding those four observations leaves
710,274 usable records and preserves the benchmark pass. Some individual
one-second bins fell below 80 records; acceptance uses the average over the
whole measurement, not a minimum in every second.

## Setup and scope

The acquisition ran on 3 November, approximately 01:17–01:47 WIB
(2 November, 18:17–18:47 UTC). The transmitter and C6 gateway used laptop USB
for control/reference and delivery respectively. Four C5 receivers uploaded
CSI through scheduled 2.4 GHz ESP-NOW. The user previously reported powering
the receivers through a replacement hub and phone charger; the supply was not
electrically measured or reconfirmed for this run.

| Setting | Recorded value |
| --- | --- |
| Inventory | `configs/radio/gateway_inventory.json`, four fixed C5 receiver identities |
| Transmitter | USB identity `44:bd:8d:d0:b6:80`; sensing MAC `1a:00:00:00:00:00` |
| Receivers, inventory order | rx-1 `44:bd:8d:d0:b1:4c`; rx-2 `44:bd:8d:d0:b3:50`; rx-3 `44:bd:8d:d0:be:9c`; rx-4 `44:bd:8d:d0:b6:6c` |
| Gateway | XIAO C6 `10:bd:a3:9e:cd:68`, built-in antenna |
| Sensing profile | `indonesia_5g_ch44_120hz.json`, 120 rounds/s, channel 44, HE20 MCS0 |
| Profile fingerprint | `8b28a906a0fbcd1f` |
| Transport policy | `espnow_transport_throughput_mcs3_queue96.json`, fingerprint `fac57223039aef5c` |
| Backhaul | Channel 6, HT20 MCS3, long guard interval |
| Upload authorization | 125 ms maximum slot, 5 ms start guard, 10 ms send guard/return reserve |
| Storage | 96 records, 750 ms lifetime, four batch buffers, at most 64 records submitted per slot |
| Delivery mode | No application ACKs or application retries; MAC feedback, CRCs and return interlock retained |
| CPU / firmware | Previously deployed fixed-160-MHz images; TX/gateway exact pre-BLE restorations; receivers unchanged |
| Qualification | 30 s warm-up, 1,800 s measurement, four receivers, target 80 timely records/s each |
| Availability | 50 Hz bins, 900 ms grace, separate from one-second latency criterion |

No firmware, PHY, profile, retention or slot changes were made during the run.
No automatic restart or retry of the experiment occurred. The test exercised
the acquisition manager, receiver recorders and full transport journals
headlessly. It did not open the viewer or collector GUI and did not capture
phone video. Concurrent DroidCam recording therefore remains unqualified.

## Delivery, latency and gaps

The table excludes the four records with driver status `rx_state=65`. Counts
use sensing-reference capture times inside the exact 1,800-second window.
Latency is host recorder/journal acceptance minus mapped sensing time plus
clock uncertainty. File-buffer acceptance does not guarantee power-loss durability.

| Receiver | Usable records | Timely records/s | Delay median (ms) | Delay p99 (ms) | Delay max (ms) | Longest capture gap (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| rx-1 | 177,759 | 98.755 | 282.26 | 474.83 | 765.46 | 241.97 |
| rx-2 | 177,627 | 98.682 | 282.31 | 475.74 | 772.94 | 425.00 |
| rx-3 | 177,651 | 98.695 | 281.49 | 474.26 | 763.46 | 257.97 |
| rx-4 | 177,237 | 98.465 | 285.79 | 618.36 | 792.71 | 425.02 |

The maximum-delay column conservatively retains the maximum from all accepted
records. All delivered records had finite clock mappings and conservative
latency below one second. Capture gaps describe consecutive delivered sensing
observations, including window boundaries; they do not identify a loss cause.

Each row below summarizes 1,800 nonoverlapping, capture-time one-second bins.
The 80-record target applies to the whole-run average. Short dips remain visible
rather than being hidden by the average.

| Receiver | Min | p01 | p05 | Median | p95 | p99 | Max | Bins below 80 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rx-1 | 55 | 96 | 96 | 96 | 108 | 108 | 109 | 3 |
| rx-2 | 58 | 94 | 96 | 96 | 108 | 108 | 109 | 7 |
| rx-3 | 58 | 94 | 96 | 96 | 108 | 108 | 109 | 4 |
| rx-4 | 54 | 84 | 96 | 96 | 108 | 108 | 109 | 11 |

## Queue behavior and delivery failures

All receivers passed the existing queue criterion: no reported peak reached
96 records, and the last/first 30-status median difference was at most one
record. Reported high-water marks were 80/96 throughout; these boot-level
counters can include earlier activity. Actual sampled maxima within each
five-minute window remained at most 79. Window medians stayed at 26–28 records,
with no sustained backlog growth.

| Receiver | Five-minute queue median/max, earliest to latest | Endpoint median growth | Expiry counter increase | Send-error counter increase |
| --- | --- | --- | --- | --- |
| rx-1 | 26/79, 26/78, 26/72, 26/78, 26/69, 26/67 | +1.0 | 3,121 | 5 |
| rx-2 | 27/78, 26/78, 26/61, 26/79, 26/77, 26/78 | +1.0 | 3,411 | 1 |
| rx-3 | 26/79, 26/64, 26/78, 26/79, 26/75, 26/78 | -0.5 | 3,504 | 2 |
| rx-4 | 27/78, 28/79, 26/74, 28/79, 26/71, 26/78 | -2.0 | 3,554 | 10 |

Counter increases span first-to-last observed status, including warm-up and
shutdown, rather than the exact measurement window. Expiry and send-error
counts are firmware events, not an independently verified count of unique
missing sensing records. Send errors can include control traffic. There were
no increases in the reported combined drop counters, no receiver diagnostic-loss
flags and no transmitter log drops. These observations do not imply zero losses.

Gateway counters increased by **361,446 received** and **361,445 forwarded**
envelopes; USB errors increased by one, rejected traffic stayed zero, and the
last reported gateway queue was empty. The one-envelope deficit is consistent
with the recorded USB forwarding failure. ACK-less delivery offers no host
acceptance retry to recover that failure; the exact affected CSI records are
not established. Absolute counters include 5,313 envelopes from earlier
activity and are not used as this run's totals.

## Scheduling and receiver availability

All required grants had mapped return evidence. The measurement overlaps
12,707 conservative departure-to-capture-recovery intervals. None of their
uncertainty-expanded bounds overlapped another receiver's interval. No grant
was unproven and no transmitter event log was dropped. This supports the
single-departure interlock under the measured conditions.

Return/deadline comparisons classified 12,676 intervals before deadline,
zero after deadline and 31 as uncertain; none was unmapped. The uncertain
comparisons cannot be certified as before deadline. Mean upload-start spacing
was 141.66 ms (p99 143.03 ms), including scheduling overhead. Interval bounds
include clock uncertainty and sensing recovery; they are not direct timings
of the channel-switch API.

The 90,000 finalized 50 Hz bins retained the following original host masks,
in rx-1/rx-2/rx-3/rx-4 order. A `1` means that receiver supplied data accepted
before the bin's 900 ms grace expired. The masks remain immutable, including
the four subsequently flagged observations; the derived quality check does
not retrospectively rewrite model-input availability.

| Mask | Finalized bins |
| --- | --- |
| `0000` | 0 |
| `0001` | 6 |
| `0010` | 3 |
| `0011` | 8 |
| `0100` | 16 |
| `0101` | 73 |
| `0110` | 20 |
| `0111` | 13,915 |
| `1000` | 2 |
| `1001` | 18 |
| `1010` | 192 |
| `1011` | 13,892 |
| `1100` | 15 |
| `1101` | 13,951 |
| `1110` | 14,054 |
| `1111` | 33,835 |

At least three receivers were available in 89,647 bins (99.608%). There were
353 bins with only one or two receivers, and no all-missing bin. This is
availability of delivered data after the grace period, not proof of continuous
simultaneous RF reception, a guaranteed live sampling rate, or detector accuracy.

## Integrity audit and reproducibility

Raw artifacts are retained under
`data/experiments/gateway/endurance-usb-20261102T181708Z/`. The settings, inventory,
profile, policy, host source snapshots/hashes and firmware restoration
provenance were saved before acquisition. The run used dirty workspace sources
based on commit `20bae5686029f07956506690e125b619e9967c88`; the snapshots record
what actually ran. No receiver was reflashed or reprovisioned for this test.

The raw journal is
`measurement/gateway-a98637db259eb525/transport/gateway/a98637db259eb525/`
inside that directory. Independent decoding traversed all 361,445 complete
envelopes and 722,663 nested records across warm-up, measurement and draining.
Every envelope passed CRC/length decoding; all nested records matched run,
transmitter epoch, receiver identity and sensing profile, with no duplicate
record identities. Every record reported HE20 on the sensing channel and
490 CSI bytes. Four records nevertheless reported nonzero driver status;
CRC integrity does not establish their signal quality, and the status cause
was not diagnosed here.

The original acceptance-based report counts 710,278 measurement records.
`analysis/quality-qualification.json` excludes two flagged rx-1 and two flagged
rx-3 records, passes the same criteria, and supplies the usable-rate table.
Original CSI CSVs, timing sidecars, envelopes, events and masks are unchanged.
The current host ingestion path preserves these status flags rather than
rejecting those records, so stricter live signal-quality gating remains work.

The approximately 991 MB event journal was streamed into derived inputs
containing the fields consumed by the unchanged canonical `evaluate()`
function. This bounds analysis memory without editing raw artifacts. Round
extrema retain the exact measurement window and maximum diagnostic-drop count;
full-stream checks independently recorded round counts, boot identities and
counter changes. The raw audit observed 219,797 transmitter round messages,
zero reported skipped rounds and no backward sequence transitions.

Derived evidence in `analysis/` includes `qualification.json`,
`quality-qualification.json`, `quality-audit.json`, `summary.json` with SHA256
hashes/sizes of the four raw journal files, derived evaluator inputs, and
copies of `analyze.py`, `quality.py` and `plot.py`. Per-receiver raw recordings
remain separately under `measurement/rx-*/`. `process.json` records successful
completion and shutdown; independent post-run status confirms transmitter
radio-off and gateway unconfigured. Software validation before the endurance
run passed all 423 tests; no product code was changed during measurement.

This result qualifies sustained transport under this setup and policy. It does
not establish fault recovery, supply causality, post-switch phase stability,
operation in other rooms, concurrent phone-video performance, or fall-detector
accuracy. No criterion was relaxed to obtain the pass.
