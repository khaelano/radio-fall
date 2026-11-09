# ESP-NOW switching and upload probe, 1 November 2026

The transport is implemented, but hardware qualification has **not passed**.
One C5 receiver, one C5 transmitter and one C6 gateway were available. The final
single-receiver probe delivered 33.5 valid records/s during its 30-second
measurement after a five-second warm-up. This does not establish the required
four-receiver performance over a 30-second warm-up and 300-second measurement.

## Hardware and conditions

| Role | Verified identity |
| --- | --- |
| C5 transmitter | Radio MAC `1a:00:00:00:00:00`; USB identity `44:bd:8d:d0:b6:80` |
| C5 receiver | `44:bd:8d:d0:b3:50` |
| XIAO C6 gateway | `10:bd:a3:9e:cd:68`; user authorized this board as gateway |

All three boards used the transmitter's working USB controller through a hub.
An earlier controller reported an xHCI failure and disconnected its devices.
Successful enumeration on the healthy controller does not establish whether a
cable also contributed. The C6 then exposed a separate boot failure: IDF rejected
the `11g|11n` protocol bitmap. Enabling the supported `11b|11g|11n` combination
fixed startup; explicit peer configuration still selects HT20 MCS0 long GI.

Settings remained at channel 44, HE20 MCS0 and 80 sensing rounds/s; the gateway
used channel 6. Upload slots remained 50 ms, with a 5 ms departure guard and
10 ms return reserve. Retention remained 500 ms, with 64 record slots, four
outstanding batches, one application retry and a 16-record slot allowance.
Room motion, antenna placement and environmental conditions were not controlled
as an amplitude/phase calibration experiment.

## Measured result

| Metric | Final probe |
| --- | --- |
| Valid records delivered in the measurement | 1,005 |
| Records/s delivered within one second | 33.5 — below 50 |
| Delivered records within one second | 100% |
| Conservative median / p99 latency | 486.3 / 517.9 ms |
| One-second rates | 24–45 records/s; full distribution in the report |
| Longest gap between timely sensing references | 225.1 ms |
| Receiver pool peak | 33 of 64 |
| First-to-last status-window median queue increase | 9 records — fails the fixed stability check |
| Finalized 50 Hz, 500 ms grace availability bins | 659 available; 841 unavailable |
| Complete timing evidence for measurement grants | Yes, for this one receiver |

The one-second latency criterion and the 500 ms availability grace are separate.
Records accepted after a bin's deadline remain recorded without changing its
finalized availability mask. Bounded retention can keep the pool below capacity
while records expire; a bounded pool alone does not prove adequate throughput.

Across the complete final probe, including warm-up and shutdown, 444 recorded
departure-to-recovery intervals had conservative recovery bounds before their
slot deadlines. Their median upper duration was 35.85 ms and maximum was
43.50 ms. The closest conservative recovery bound was 0.96 ms before expiry.
Recovery means reception of the first subsequent sensing packet on 5 GHz;
these measurements do not separately time each channel API call. With one
receiver, absence of overlapping receiver intervals is insufficient evidence
about coordinated operation with four receivers.

The raw complex CSI remains available. A diagnostic compared 441 pairs of
delivered records spanning return markers. The median amplitude ratio was 1.001
and median absolute raw phase change was 1.605 radians. Transport loss can hide
intermediate captures, and room motion was uncontrolled. These numbers do not
establish phase stability or exclude retuning artifacts; controlled post-switch
amplitude/phase qualification remains open.

## Implementation corrections and evidence

The initial upload probe delivered 12.2 records/s. Hardware traces exposed
rejected radio submissions consuming retries and ACK polling repeatedly selecting
the oldest outstanding batch. The receiver now counts attempts only when the
MAC accepts submission, rotates polls, and retrieves earlier ACKs at slot entry.
The gateway retries immediate relay of duplicate host ACKs and retains its
bounded cache for explicit polling. MAC acceptance still does not mean processor
application acceptance.

The transmitter previously suppressed the sensing round intended to witness
return. Its suppression interval now ends at that witness round. A C contract
test verifies this boundary. CRC validation covers the complete sensing grant
in both receiver processing paths. Raw queue events identify build, submission,
retry, host ACK, abandonment, pending expiry, overflow and return failure. Lost
queue-event evidence is explicitly flagged rather than silently certified.

A separate fault test killed the complete host acquisition process group without
graceful shutdown. Discovery five seconds later reported `radio_active: false`
on the verified transmitter, consistent with its three-second host-control
lease. This checks transmitter shutdown on host loss; it does not establish
four-receiver recovery or exact lease-expiry timing.

Subsequent cleanup added explicit deferred-grant logs and reclaims stale receiver
records before admitting new copies. The sustained probe figures above remain
tied to its saved binary hashes, rather than being attributed to later builds.
The disconnect test also exposed cumulative old-run drop counts blocking a new
run. The reference now establishes a run baseline while retaining lifetime
counts, ignores stale-run events, and still fails on new drops. A regression
test covers this distinction. A second forced-disconnect test then stopped and
restarted acquisition without resetting the boards. Its ten-second smoke
measurement delivered 29.9 records/s, with all delivered records within one
second and 520.1 ms p99 latency. It also failed the rate requirement. Artifacts
are in `recovery-regression/`, including the current source/binary snapshot.

Verification at completion: `uv run pytest` passed 346 tests; ESP-IDF 6.1 built
the C5 transmitter, C5 receiver, and generic/XIAO C6 gateway in isolated build
directories. The identified boards were flashed, and the final recovery smoke
test exercised those images. Builds and smoke tests are not qualification.

Raw runs are preserved locally under
`data/experiments/gateway/switch-20261101T152003Z/`. The final report is
`final-switch-probe/gateway-178420b72336d823/transport/gateway/178420b72336d823/qualification.json`.
That directory also contains immutable envelopes/events/availability, binary and
source hashes, and derived `switching-analysis.json` and
`switch-signal-diagnostic.json`. Earlier failed runs remain in separate
directories. Large recordings are ignored by Git.

ESP-IDF 6.1 builds and offline tests establish build/protocol behavior only.
Further work must resolve the failed rate and queue checks, qualify controlled
post-switch CSI, and run the unchanged sustained criteria and fault checks with
four identified C5 receivers. Do not infer detector robustness or change the
criteria to turn this probe into a pass. Operating instructions are in
[espnow-gateway.md](../espnow-gateway.md).
