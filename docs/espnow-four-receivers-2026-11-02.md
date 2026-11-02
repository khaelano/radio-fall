# Four-receiver gateway bring-up, 2 November 2026

All four C5 receivers were verified over the sensing/control link and delivered
valid CSI through the C6 USB gateway. USB data enumeration sees the transmitter,
gateway and one receiver; the other three receivers operate from the user's
power-only USB connections. Six active radio boards do not require six USB data
ports. Receiver USB is used for flashing/provisioning, while the gateway carries
all live CSI to the host.

| Role | Stable ID | Radio MAC | USB data connected |
| --- | --- | --- | --- |
| Transmitter C5 | tx-1 | 1a:00:00:00:00:00 | Yes; USB hardware identity 44:bd:8d:d0:b6:80 |
| Receiver C5 | rx-1 | 44:bd:8d:d0:b1:4c | Yes |
| Receiver C5 | rx-2 | 44:bd:8d:d0:b3:50 | No |
| Receiver C5 | rx-3 | 44:bd:8d:d0:be:9c | No |
| Receiver C5 | rx-4 | 44:bd:8d:d0:b6:6c | No |
| Gateway XIAO C6 | gateway-1 | 10:bd:a3:9e:cd:68 | Yes |

The versioned live inventory is `configs/radio/gateway_inventory.json`, copied
from the user's four-receiver roster with the previously verified gateway added.
The user's `configs/radio/receivers.json` edits are preserved. Old recordings
and their inventory snapshots are unchanged. Both 80 Hz sensing-profile
fingerprints reported over USB matched `949e8d7005d9e9b6`; all four receiver
identities were subsequently checked over radio by the gateway manager.

## Transmitter roster correction

The first four-receiver configuration was rejected before sensing started.
A configuration-only check confirmed that the transmitter still accepted its
previous single-receiver inventory (`44:bd:8d:d0:b3:50`) with CGCF-v4. The
transmitter checks the configured receiver count and ordered MAC list against
its stored profile. It was explicitly reprovisioned with the complete verified
four-receiver inventory, without reflashing or changing receiver provisioning.
All four then passed readiness and delivered data in the short bring-up.

The sensing-profile fingerprint covers channel/rate and transmitter identity;
it does not include the receiver list. Matching that fingerprint alone cannot
establish that the transmitter's stored roster is current. Runtime transport
configuration separately verifies and fingerprints the ordered inventory.
Reprovision the transmitter when its peer list changes, even if its 80 Hz
profile fingerprint remains the same.

The initial failed preflight also logged a cleanup/ingestion exception. Its
journal is preserved as a failed attempt, not included in successful measurement
results. Subsequent bring-up and sustained measurement use separate run IDs.

## Measurement settings

The trial uses 5 GHz channel 44, HE20 MCS0 sensing at 80 rounds/s and the existing
2.4 GHz channel 6 HT20 MCS0 gateway. It tests the previously promising single-RX
policy: 750 ms retention, two application retries, 150 ms ACK timeout and 900 ms
availability grace. Other limits remain four outstanding batches, 64 record
slots, 16 submitted records per upload slot, 50 ms maximum slots, 5 ms departure
guard, 10 ms send guard and 10 ms return reserve. Early return is disabled.
No slot, sensing rate or acceptance threshold was adjusted after seeing results.

The short bring-up used a 1 s warm-up/10 s measurement and delivered
12.8, 14.0, 13.4 and 13.4 timely records/s for rx-1 through rx-4. All delivered
records arrived within one second; median delay was about 738–744 ms. That
confirmed connectivity but failed the required 50 records/s per receiver.
Its 133 observed intervals included one uncertain deadline classification and
132 before deadline. The sustained qualification uses the required 30 s
warm-up/300 s measurement and the same policy.

Original manifests, raw envelopes, clocks, grants, ACKs, queue/transition events
and finalized availability bins are under
`data/experiments/gateway/four-receiver-20261102T000226Z/`.
Configuration snapshots and the transmitter provisioning/check evidence are
retained there. Results are transport measurements, not fall-detector accuracy
or post-switch phase/amplitude qualification.

## Sustained result: qualification failed

| Receiver | Timely records/s | Delay median / p99 / max (ms) | Longest capture-time gap (ms) | Sampled queue maximum |
| --- | --- | --- | --- | --- |
| rx-1 | 13.00 | 743.02 / 759.35 / 774.86 | 787.00 | 59 |
| rx-2 | 12.85 | 742.88 / 759.93 / 772.83 | 787.79 | 58 |
| rx-3 | 12.89 | 742.87 / 759.65 / 771.58 | 1238.01 | 58 |
| rx-4 | 12.94 | 743.07 / 758.99 / 776.14 | 1238.00 | 58 |

The required 30 s warm-up and 300 s measurement completed. All four receivers
delivered valid records, and every delivered record met the one-second deadline
after including clock uncertainty. Every receiver failed the required average
50 timely records/s. The total across all receivers was 51.67 records/s; that
aggregate cannot substitute for the per-receiver requirement.

Queues stayed bounded below 64 records and passed the existing growth check
with zero median growth, but retention/expiry can keep a queue bounded while
discarding measurements. The roughly 743 ms median delays indicate records
waiting near the 750 ms retention limit. This is evidence of transport backlog,
not proof that all captured CSI was delivered. The largest per-receiver gap
between timely sensing-reference records was 1.238 s, independent of the
latency of records that did arrive.

Of 3962 mapped observed recovery intervals, 3909 were conservatively before
their slot deadlines, 30 were after, and 23 had uncertain classification.
Maximum per-receiver recovery bounds reached 65.96–80.66 ms. These intervals
run from departure through first observed sensing-frame recovery; they do not
isolate channel-API execution time or establish a specific failure cause.
No overlaps were observed between mapped intervals, but one grant (4362)
remained unproven, so complete non-overlap evidence was not obtained. Neither
the rate requirement nor the timing/return evidence establishes a qualification
pass. The host report correctly retained `qualified: false`.

## Availability and one-second rate distributions

| Receiver | One-second count min / median / p95 / max |
| --- | --- |
| rx-1 | 4 / 12 / 16 / 16 |
| rx-2 | 2 / 12 / 16 / 16 |
| rx-3 | 2 / 12 / 16 / 16 |
| rx-4 | 2 / 12 / 16 / 16 |

Availability uses fixed receiver order rx-1, rx-2, rx-3, rx-4, 50 Hz bins and
900 ms grace. It is reported separately from the one-second transport metric.
Across 15000 finalized bins, the bit masks were:

| Mask | Bin count |
| --- | --- |
| 0000 | 3400 |
| 0001 | 2891 |
| 0010 | 2894 |
| 0011 | 2 |
| 0100 | 2882 |
| 1000 | 2927 |
| 1001 | 3 |
| 1100 | 1 |

Mask `0000` occurred in 3400 bins (22.67%); the longest consecutive run was
460 ms. This means no accepted record was available in those finalized model
bins. It does not prove simultaneous off-channel absence or identify the cause
of each missing measurement. Late records do not revise finalized bins. The
all-zero mask is distinct from the mapped channel-interval overlap check.

## Restoration and limits

A subsequent 1 s warm-up/10 s default-policy smoke completed with all four
receivers: 13.6, 13.2, 13.2 and 13.4 records/s, respectively. All delivered
records were subsecond; median delays were about 489–493 ms, with zero median
queue growth. All 134 mapped recovery intervals were before deadline with
complete observed evidence and no overlaps. This short restoration check does
not qualify the default or form a matched sustained comparison with the
five-minute candidate run.

The original 500 ms/one-retry transport defaults were restored, while the
transmitter retained the corrected four-receiver roster and both USB-visible C5
profiles remained at 80 Hz. Final status verified all three USB identities,
transmitter radio off and gateway unconfigured after shutdown. The power-only
receivers were verified by their radio status/data during the runs. The full
software suite passed 361 tests; the new inventory validates against both
transport policies. No firmware was reflashed in this bring-up.

The four-receiver setup is operational but does not meet transport qualification.
Four-receiver restart, absent-gateway and host-disconnect fault checks were not
run in this measurement. The single-receiver recovery result does not establish
four-receiver reliability, post-switch CSI quality or detector robustness.
