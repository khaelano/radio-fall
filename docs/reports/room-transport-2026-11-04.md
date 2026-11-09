# Room transport investigation, 4 November 2026

The reported room setup placed the farthest receiver about 5 m from the gateway.
The viewer continued receiving CSI but showed uneven one-second delivery rates
and growing expiry counters. An earlier run ended with
`gateway USB receive buffer age exceeded`. The investigation preserves radio
loss, host processing delay and transmitter-reference failures separately.

## Implemented host correction

The live preview prepared phase views in bounded steps, then took a new snapshot
of the rolling buffer. A receiver upload could append new records between those
operations. Snapshot construction calibrated those fresh records synchronously,
bypassing the 16-record / approximately 8 ms preparation budget.

The live snapshot now checks preparation readiness against the exact immutable
window it will use. If any record is still cold, the dashboard defers drawing
and resumes bounded preparation on later refreshes. Deferred work does not
advance the render cache or change raw records, calibration, capture times or
finalized availability bins. Viewer and collector share this code. The 200 ms
USB-age guard and queue limits are unchanged.

The regression in `tests/radio/test_gui_rendering.py` injects 32 fresh records
after bounded preparation reports readiness. It failed on the old implementation
because the same refresh prepared and plotted all 32. With the correction, that
refresh leaves their phase caches cold; subsequent bounded steps prepare them
and the eventual complete plot contains all 33 records. This proves the preview
budget race, but does not establish it as the sole cause of the earlier physical
USB-age failure. The new hardware attempts below stopped on reference faults
before a sustained host validation could finish.

## C6 relay contention correction: source only

The new attempts also exposed `peer_queue_lock`. The reference relay held its
source-queue mutex while compressing a private block. Incoming UART data waits
only 5 ms for this mutex, so a sufficiently long compression/preemption interval
can fault admission even when queue capacity remains available.

`common/reference_relay.c` now copies a complete prefix under the mutex, releases
the mutex for compression, then reacquires it to consume only the encoded prefix.
The relay task remains the sole consumer; UART producers append. Bytes appended
during compression stay queued in order. Failed encoding does not consume bytes.
The admission timeout, queue capacity, ARQ window and packet lifetime are unchanged.

The native test in `tests/radio/test_uart_relay.py` compiles the actual relay
implementation and injects UART admission at the encoding boundary. It failed
with `queue_lock` before the change and now verifies both frames reach the peer
in order, without a drop. Existing expiry, timeout, overflow, restart, duplicate
and codec scenarios still pass.

Both C6 projects build with ESP-IDF 6.1. Neither board was flashed: the companion
could not be connected over USB data. This correction is therefore not deployed
or hardware validated, and does not establish a fix for the separate packet
expiry failures.

## PHY comparison attempts

Complete experimental configurations differ only in receiver backhaul PHY:
HT20 MCS2 versus MCS3, both with long guard interval. They retain 120 Hz/channel-44
sensing, backhaul channel 11, 125 ms slots, 96-record queues, 750 ms retention and
the ACK-less policy. The reference relay independently retains MCS0.

| Attempt | CSI upload PHY | Observed sensing-round span | Accepted records | Ending reference fault | Maximum dequeued host USB wait |
| --- | --- | ---: | ---: | --- | ---: |
| Original viewer baseline | MCS3 | 3.22 s | 908 | `peer_packet_expired` | 86.18 ms |
| Recovered viewer baseline | MCS3 | 17.67 s | 2,660 | `peer_queue_lock` | 109.69 ms |
| Corrected viewer | MCS2 | 3.16 s | 573 | `peer_queue_lock` | 42.71 ms |
| Headless benchmark | MCS2 | 6.63 s | 2,488 | `peer_packet_expired` | 6.98 ms |
| Headless benchmark | MCS3 | 0.92 s | 46 | `peer_packet_expired` | 0.72 ms |

Round spans exclude setup and shutdown. None completed the required 30 s warm-up
and 300 s measurement. Their different startup windows, receiver participation
and reference failures prevent a defensible rate or reliability ranking. The
headless failures show that removing plot work did not resolve reference packet
expiry. Lower host queue waits do not establish end-to-end subsecond delivery
or a sustained processing fix.

The operational configuration remains MCS3. No receiver, transmitter or gateway
firmware was flashed, and sensing rate, slot duration, retention and acceptance
criteria were not relaxed. After testing, discovery verified the transmitter's
radio stopped, UART fault clear, original sensing fingerprint
`8b28a906a0fbcd1f`, gateway unconfigured and paired relay ready without fault.

All 546 Python/native tests pass. Artifacts are under ignored
`data/experiments/gateway/room-transport-20261104/`, including immutable envelopes
and journals, exact configurations, `attempts.json` and final device status.
Debug probes and build/test logs are under `.codex-build/room-transport-20261104/`.

The remaining sequence is to deploy and verify the C6 correction, investigate
any continuing reference packet expiry, then repeat both full PHY measurements
and the corrected viewer/collector load test at the same room placements. No
PHY improvement, hardware processing cure or detector accuracy is claimed.
