# ESP32-C6 BLE timing screening, 1 November 2026

Ten hardware screening conditions completed with one XIAO ESP32-C6 receiver,
RX4. The user reported approximately 20 cm between that receiver and the laptop.
The complete four-receiver inventory and fixed round-robin order were retained;
three absent receivers' turns were unused. These results do not qualify four
simultaneous connections, room coverage, or fall detection.

Each screening condition used a five-second warm-up and 30-second measurement.
After the user reconnected the transmitter, a paired repeat completed with
30-second warm-ups and five-minute measurements at a verified 7.5 ms BLE interval.
The paired results are reported separately below; most screening conditions used
12.5 ms. These sequential runs do not establish repeat-to-repeat uncertainty.

## Conditions and provenance

All conditions used 80 sensing rounds/s, HE20 on 2.4 GHz channel 6, unchanged
raw CSI encoding, and the provisioned receiver order. The transmitter selected
its attached external antenna; RX4 selected its built-in antenna. Both boards
used laptop USB during screening; CSI traveled only over BLE. The laptop Wi-Fi
frequency was 2437 MHz. Its interference contribution was not isolated.

Negotiated MTU was 247, PHY was LE 2M, and link data length was 251 octets.
The default connection interval was 12.5 ms. Each condition recorded negotiated
settings; requested values are not assumed to have taken effect.

Artifacts are under the ignored local directory
`data/experiments/ble/c6-timing-20261101/`. The authoritative derived screening
summary is [`screen-single-read/analysis.json`](../../data/experiments/ble/c6-timing-20261101/screen-single-read/analysis.json).
Each condition retains its configuration, exact invocation, console log, raw
envelopes, session events, immutable availability bins, and integrity report.
`firmware-single-read.json` records the C6 application hashes and SDK settings;
`environment.json` records the available hardware and host radio context.

The earlier `screen/` pilot is excluded from timing conclusions. Its 456-byte
diagnostic value could change across ATT long reads. The corrected 232-byte
snapshot fits one read at MTU 247. Raw pilot files are preserved, with exclusions
recorded in `pilot-exclusions.json`. The continuous pilot was interrupted during
teardown and is not used in the table below.

## Screening results

Capture rates use receiver-counter spans, which differ slightly from the exact
30-second capture-time interval used for delivery rates. Timely means accepted
by the end of the record's 50 Hz input bin plus 100 ms. It does not mean a fixed
100 ms after each packet. Rates below count records; they do not imply 50 Hz
bin availability or detector accuracy.

| Condition | Capture records/s | Delivered records/s | Timely records/s | Median delay, ms |
| --- | ---: | ---: | ---: | ---: |
| Round-robin baseline | 72.06 | 24.20 | 0.00 | 265.53 |
| Continuous submission | 37.98 | 37.63 | 18.17 | 116.67 |
| Continuous, one outstanding batch | 50.85 | 46.60 | 1.77 | 254.43 |
| Round robin, one outstanding batch | 69.05 | 19.77 | 0.00 | 258.22 |
| Round robin, 2 ms fragment pacing | 71.56 | 0.47 | 0.00 | 219.54 |
| Round robin, one record per batch | 47.50 | 17.90 | 0.00 | 265.11 |
| Round robin, two-round turns | 66.81 | 26.60 | 0.00 | 264.42 |
| Round robin, 80 ms maximum record age | 63.70 | 17.17 | 11.67 | 97.53 |
| Round robin, negotiated 7.5 ms interval | 64.54 | 21.93 | 0.00 | 261.82 |
| Round robin, 25 ms requested, 7.5 ms actual | 65.44 | 20.40 | 0.03 | 260.75 |

All other rows negotiated 12.5 ms. The last row did **not** establish performance
at a 25 ms interval. Two-round turns received twice the per-turn byte allowance,
preserving the nominal allowance per second. Continuous submission bypassed
grant ownership only as an explicit experiment; it still required fresh sensing
observations, bounded record/batch storage, and expiry.

The continuous/one-outstanding combination changes the outstanding-batch limit
relative to the continuous row. Other scheduled variations each change one
setting relative to the scheduled baseline. Runs were sequential and not
randomized; environmental variation remains a possible contributor. These are
screening observations without confidence intervals or repeated-run estimates.

## Five-minute paired repeat

Both conditions retained the fixed four-slot round-robin order, one active RX4,
80 sensing rounds/s, unchanged CSI bytes and C6 firmware, MTU 247, LE 2M,
251-octet link data length, and a verified 7.5 ms connection interval throughout
measurement. Only maximum record age changed, from 250 to 80 ms. The laptop
remained on 2437 MHz Wi-Fi; the last reported receiver/laptop distance was 20 cm,
and the user was asked to keep positions fixed.

An initial 12.5 ms preflight failed because the actual interval remained 7.5 ms;
sensing never started in that attempt. Experimental preflight now retries the
configuration at most twice before sensing and rejects an unachieved interval.
The pair explicitly requested 7.5 ms rather than silently accepting a mismatch.

The local artifact directory is `confirmation-7p5ms/` under the same experiment
root. Its [`analysis.json`](../../data/experiments/ble/c6-timing-20261101/confirmation-7p5ms/analysis.json)
contains raw-journal locations, integrity checks, timing summaries, negotiated
parameters, and counterfactual deadline counts. `confirmation-environment.json`
records matching firmware hashes and host source hashes at launch. The failed
`confirmation/` attempt remains preserved and excluded from measurements.
`confirmation-source-at-launch/` archives the host modules and C6 application
binaries, checked against those launch hashes.

| Metric | 250 ms record-age limit | 80 ms record-age limit |
| --- | ---: | ---: |
| Measurement duration, s | 300.00 | 300.00 |
| Capture counter rate, records/s | 65.88 | 69.67 |
| Delivered records | 6,182 | 3,169 |
| Delivered records/s | 20.61 | 10.56 |
| Timely records | 33 | 2,636 |
| Timely records/s | 0.11 | 8.79 |
| Available input bins/s on the 50 Hz grid | 0.10 | 6.86 |
| Median delivery delay, ms | 262.24 | 88.78 |
| 95th-percentile delivery delay, ms | 295.41 | 127.81 |
| 99th-percentile delivery delay, ms | 320.64 | 158.32 |
| Longest timely round-receipt gap, s | 208.80 | 1.79 |
| Sampled median capture-to-first-submission, ms | 228.57 | 59.45 |
| Host median recorder acceptance, ms | 2.04 | 1.97 |

The shorter age limit improves freshness while reducing total delivery. The
receiver still approaches its age limit before starting many batches. Partial
reassembly eviction counter deltas rose from 3,247 to 6,356, indicating more
abandoned partial envelopes. These observations support investigating admission
and transfer-lifetime policies separately; they do not isolate controller backlog
or establish that a particular replacement policy will solve it.

Both measurement intervals had zero new firmware send-error counter increments,
zero host notification-drop counter increments, no receiver restart, and no
transmitter-reference failure. A live update initially interpreted a cumulative
send-error total as new errors; the measured counter deltas corrected that
interpretation. All 9,351 measurement records decoded with driver state zero,
with zero envelope CRC failures and zero round/enqueue-time mismatches. Firmware
expiry and host delivery counts overlap because already-submitted data can arrive
after receiver release; they must not be added as disjoint losses. Minimum reported
free heap was 10,164 bytes in both runs, a lifetime minimum since boot rather than
a minimum attributable solely to either condition.

An offline 350 ms grace would accept 20.54 records/s and yield 16.33 available
bins/s for the paired baseline. It would not increase its total delivery rate.
Neither paired condition establishes 50 usable Hz or a four-receiver collection
candidate. The 80 ms policy is retained as an experimental setting, not promoted
to the collection default.

## Timing evidence and interpretation

In the baseline, 104 sampled receiver batch timelines had median capture-to-build
time 227.04 ms and capture-to-first-submission time 228.77 ms. These snapshots
expose four recent entries from a bounded ring and do not cover every batch.
Across 357 host batch events, median fragment-arrival span was 5.96 ms, consumer
queue delay 0.78 ms, recorder acceptance 2.26 ms, and ACK-write completion 0.51 ms.
These stage distributions describe different populations and must not be added
as though they were one representative packet.

The measurements establish substantial receiver-side waiting before submission.
They do not isolate every cause of that backlog. Source inspection also verified
that NimBLE invokes the notification event after attempting host-stack submission;
it is not confirmation of RF completion or laptop acceptance. Consequently, the
current callback does not establish a bound on controller backlog. Controller
traces could not be captured because Bluetooth monitor access was denied and
noninteractive privilege elevation was unavailable.

Removing grant limits improved delivery while reducing Wi-Fi capture. Restricting
outstanding batches increased delivered rate in the continuous case but retained
high latency. Longer turns and smaller batches did not resolve timely delivery.
The 80 ms age limit improved freshness by discarding stale work earlier, with a
lower total delivered rate. None of these measurements establishes 50 timely
records/s or a suitable four-receiver collection configuration.

An offline deadline sweep of the baseline would accept 24.20 records/s with
350 ms input-bin grace, corresponding to 18.60 available bins/s on the 50 Hz
grid. With 100 ms grace, both rates were zero. This counterfactual uses unchanged
delivery times: it neither increases transport throughput nor revises finalized
recordings. The derived alternative counts are stored in `analysis.json`.

## Integrity, limits, and next measurements

All ten completed journals decoded with zero envelope CRC failures and zero
measurement record sequence/enqueue-time mismatches against transmitter rounds.
The 6,980 measurement records include 33 with nonzero driver `rx_state=65`;
these flags are retained and must not be treated as clean sensing observations
without investigation. No receiver restart or transmitter-reference failure was
reported during these runs. Zero CRC failures do not establish absence of RF
retries, missing packets, or signal distortion.

Collection defaults remain unchanged. The paired repeat confirms that shorter
retention improves freshness while remaining far below 50 usable Hz. Next work
should investigate admission freshness and actual controller credit accounting.
The continuous result is a diagnostic comparison, not a replacement collection
default. A verified 25 ms interval remains untested.

Four connections, 5 GHz/Ethernet host-network comparisons, room placements,
body blockage, hub-powered stability, and a collection-candidate soak remain
outstanding. Close-range queueing evidence cannot predict those range results.

To repeat the pair, use a new output directory and record the current placement:

```bash
uv run python -m fall_detection.radio.experiments.ble_timing \
  --receiver-config data/interim/ble/c6-receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6_80hz.json \
  --port /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_10:BD:A3:9C:EE:94-if00 \
  --output-dir data/experiments/ble/c6-timing-confirmation-NEW \
  --conditions scheduled_interval_7p5ms scheduled_age_80ms_interval_7p5ms \
  --warmup 30 --duration 300 \
  --notes 'Record actual receiver/laptop placement here'
```

The experiment runner requires compatible CBLC v2 firmware on both connected
boards. Normal collection rejects experimental configurations. Its default
round-robin policy and existing transport fingerprint are preserved.

## Implementation verification and hardware state

The full repository suite passed 316 tests, including cross-language experimental
configuration/rotation checks, strict timing-snapshot decoding, collection guards,
requested-versus-negotiated interval reporting, deadline counterfactuals, and
rejection of interval mismatches before sensing starts.
ESP-IDF builds passed for C5/C6 transmitter and receiver projects. These checks
establish software contracts and build compatibility, not hardware performance.

RX4's normal CBLC v1 policy was reapplied and its default fingerprint
`edd8925808ad05ba` verified over BLE without starting sensing. Disconnect clears
its run authorization. The restoration connection reported a 7.5 ms interval
despite the normal 12.5 ms preference, further demonstrating why negotiated
settings must be recorded. Details are in `receiver-default-restore.json`.
After the paired runs, `restore-after-confirmation/` reapplied the normal CBLC v1
policy to transmitter and receiver through a short restoration session. Its
manifest records `experiment: null`; receiver status verified the default
fingerprint. `post-confirmation-usb-status.json` verifies both provisioned C6
identities, unchanged radio-profile fingerprint, transmitter HE20/external antenna,
and `radio_active: false`. No experiment was promoted to a collection default.
