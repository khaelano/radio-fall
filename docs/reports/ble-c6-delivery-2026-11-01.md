# ESP32-C6 admission and receipt-credit evaluation, 1 November 2026

The experimental delivery revision improved freshness and reduced abandoned
partial-batch state, but did not establish a sustained throughput improvement.
It is not lossless collection and has not been qualified with four receivers or
a fall detector. The user's priority is live detection, with delayed processing
acceptable if necessary. Consequently, the report includes total delivery and
alternative bounded-lag inputs, not only the original 100 ms grace metric.

The implementation contract is [BLE delivery policy](../ble-delivery-policy.md).
Normal collection settings remain unchanged. The 100 ms grace is an experimental
input-finalization setting, not a proven detector requirement; neither 50 delivered
records/s nor 50 available bins/s is an established detector acceptance threshold.

## Hardware, procedure, and artifacts

One powered XIAO ESP32-C6 receiver, RX4, used its built-in antenna. Its last
reported laptop distance was approximately 20 cm; positions were held fixed by
instruction. The XIAO C6 transmitter selected its attached external antenna.
Both boards used laptop USB power, with transmitter USB control/reference and
receiver CSI over BLE only. The complete four-receiver inventory and its fixed
round-robin order remained provisioned, including three unused turns.

All conditions used 80 sensing rounds/s, HE20 on 2.4 GHz channel 6, unchanged
raw 512-byte CSI samples, MTU 247, LE 2M, 251-octet link data length, and a
verified 7.5 ms interval. Laptop Wi-Fi was on 2437 MHz. The baseline and candidate
used the same firmware and diagnostic reads. The new protocol adds progress
traffic and eight header bytes per fragment; those are part of its measured cost.

The implementation also guards pending-expiry timestamp underflow and samples
worker time under the queue lock. That correction applies to both paired modes.
The candidate adds a 100 ms receiver-age target minus a fixed 60 ms completion
estimate, a separate 150 ms lifetime from batch admission, and eight host-arrival
credits. Thus pending admission is limited to 40 ms, while a started transfer
does not expire merely because the pending age has passed. The estimate does not
guarantee delivery by 100 ms; host input bins use mapped transmitter enqueue time.

Local ignored artifacts live in `data/experiments/ble/c6-delivery-20261101/`:

- `screen/analysis.json`: five-second warm-ups and 30-second measurements.
- [`confirmation/analysis.json`](../../data/experiments/ble/c6-delivery-20261101/confirmation/analysis.json):
  30-second warm-ups and 300-second measurements for the paired baseline/candidate.
- Per-condition configurations, exact commands, console logs, raw envelope
  journals, transmitter rounds, clocks, receipt status, immutable input bins, and
  sampled receiver timelines remain preserved.
- `provenance.json` and `implementation/` record initial source and firmware hashes
  and archives. `confirmation-provenance.json` and `confirmation-implementation/`
  record the paired build, including the single-ATT-bearer assertion and SDK settings.
- `restore-defaults/` and `post-evaluation-usb-status.json` record restoration and
  the stopped transmitter radio. No experimental policy was promoted automatically.

Runs were sequential, not randomized or repeated sufficiently to estimate
uncertainty. Radio conditions and other host activity were not isolated. The
long pair is primary; short screening gains must not be reported as sustained
performance. These are measured hardware findings, separate from synthetic replay.

## Short screening

| Policy | Delivered records/s | Timely records/s | Median delay, ms |
| --- | ---: | ---: | ---: |
| Baseline, original age policy | 17.83 | 0.00 | 260.83 |
| New policy, eight credits | 29.53 | 18.33 | 99.14 |
| New policy, four credits | 17.27 | 5.80 | 131.50 |
| New policy, twelve credits | 29.50 | 19.17 | 95.76 |

Timely here means accepted by the end of a 50 Hz capture-time bin plus 100 ms.
Four credits constrained completion more strongly. Eight and twelve were close
over 30 seconds; the screen does not establish that twelve is superior. The
paired repeat used eight, retaining the smaller debt bound. Original round-robin
grant timing, guard intervals, byte allowance, and receiver order were unchanged.

## Five-minute paired results

| Metric | Baseline | New policy, eight credits |
| --- | ---: | ---: |
| Captured records/s over status-counter span | 63.70 | 44.84 |
| Delivered measurement records | 6,275 | 6,314 |
| Delivered records/s | 20.92 | 21.05 |
| Timely records at 100 ms bin grace | 13 | 3,137 |
| Timely records/s at that grace | 0.04 | 10.46 |
| Available 50 Hz input bins/s at that grace | 0.04 | 9.40 |
| Median delivery delay, ms | 263.34 | 108.44 |
| 95th-percentile delay, ms | 296.43 | 237.78 |
| 99th-percentile delay, ms | 322.68 | 378.88 |
| Longest timely round-receipt gap, s | 108.29 | 3.10 |
| Sampled median capture-to-first-submission, ms | 227.03 | 29.55 |
| Partial reassembly eviction counter delta | 3,401 | 0 |
| Partial reassembly expiry counter delta | 860 | 168 |
| Application retry counter delta | 14 | 33 |
| Peak queued records | 22 | 8 |

Delivery metrics use the exact 300-second mapped capture-time interval. Capture
rates use counter spans of approximately 299 seconds and are not exact delivery
fractions. Partial reassembly counters are events, not necessarily unique lost
records or batches, and must not be summed as a loss population.

The new policy moved many records into transfer while fresh and eliminated the
observed partial-pool evictions. Its credit ledger stayed within eight entries
and 1,952 unconfirmed CSI ATT-value bytes, with zero rejected progress receipts,
zero progress-timeout disconnects, and zero submission-failure increments.
Lifetime minimum reported free heap was 26,452 bytes in both runs; it is not a
minimum attributable solely to either measurement condition.

Total delivered rates were essentially equal. The new policy's 99th-percentile
latency was worse, despite its lower median and 95th percentile. Capture rate was
also lower during the candidate run. Additional BLE traffic can compete with CSI
reception, but this sequential pair does not separate protocol impact from radio
variation. Sensing-packet RSSI medians were -58 dBm and -61 dBm respectively;
these are Wi-Fi measurements, not BLE link RSSI. It would be incorrect to claim
that controller credits alone caused either the capture-rate change or every tail.

The candidate reported 6,879 pending-admission drops and 571 started-record
releases without acceptance over its counter span. Expired records and delivered
records can overlap: submitted bytes may arrive after original record storage is
released. These counters do not establish which individual missing sequence was
lost to each cause. The design bounds memory and stale work; it does not preserve
every captured sample or increase the physical link's capacity by itself.

## Live inputs with a longer bounded lag

The following replay counts use unchanged recorded delivery/acceptance times.
They do not change transport, rerun sensing, revise finalized input bins, or
establish detector accuracy. Grace is measured after each 20 ms bin ends, rather
than exactly after each packet's capture.

| Bin grace | Baseline records/s accepted | New-policy records/s accepted | New-policy available bins/s |
| --- | ---: | ---: | ---: |
| 100 ms | 0.04 | 10.46 | 9.40 |
| 200 ms | 0.66 | 19.47 | 17.38 |
| 250 ms | 8.87 | 20.25 | 18.08 |
| 350 ms | 20.79 | 20.77 | 18.60 |
| 1,000 ms | 20.92 | 21.05 | 18.87 |

A 200–250 ms fixed-lag input is a candidate for the user's preferred live-detection
path. At 250 ms it would admit most of the delivered candidate records, with
missingness still explicit. It cannot recover records never delivered, and it
adds to sensing-window and inference latency. The model must be evaluated using
the measured masks, timing, quality flags, and end-to-end alert delay; 100 ms or
50 Hz must not be presented as universal detector requirements.

Delayed offline processing may tolerate longer arrival times, but complete
continuous collection still needs offered load below sustained delivery capacity
or enough additional storage followed by drain. Increasing the deadline alone
does not solve an accumulating backlog. These experiments did not implement or
verify a lossless archival mode.

## Integrity, verification, and remaining work

Both complete journals passed envelope CRC validation. All 12,589 measurement
record identities and enqueue times matched authoritative transmitter rounds.
The baseline had driver state zero for every measurement record; the candidate
had 6,298 state-zero records and 16 with `rx_state=65`. Flags and original bytes
remain recorded. Zero envelope errors do not establish that every sensing
observation is physically clean or that no packets were lost.

Neither run reported a receiver restart, transmitter-reference failure, new
firmware send error, or host notification-queue drop. The tests cover credit debt
after application expiry, scoped CRC receipts, future/duplicate receipts, wrap,
strict fragment bounds, stale callback generations, progress during blocked
recorder acceptance, and final ACK ordering. The full repository suite passes
326 tests. ESP-IDF C5/C6 transmitter and receiver builds pass; both measured C6
images and source snapshots are archived locally. A report-only regression also
ensures flow counter differences are not invented across receiver boot changes.

Normal CBLC v1 settings were reapplied after evaluation, with the default
transport fingerprint retained. USB status verified the provisioned C6 identities,
radio profile, antenna selections, and transmitter radio-off state. Receiver CSI
remains BLE-only; USB CSI streaming was not reintroduced.

Four simultaneous receivers, room placements, body blockage, host-network
isolation, longer soaks, and detector evaluation remain unqualified. Before
choosing a collection policy, repeat the measurements under those conditions and
investigate reducing offered bytes or better aligning upload service if more
complete data is required. The implemented revision is a measured improvement
in freshness and partial-transfer handling, not a demonstrated throughput cure.
