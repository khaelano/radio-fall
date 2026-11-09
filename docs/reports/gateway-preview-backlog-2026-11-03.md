# Gateway backlog during live preview

On 3 November 2026, the visible CSI viewer reproduced the reported
`gateway USB receive buffer age exceeded` failure after 5.60 seconds. The run
used the configured four C5 receivers, 120 Hz sensing and the dedicated C6 UART
reference. The host stopped ingestion when queued USB input exceeded its 200 ms
age limit. Stale receiver rows and zero delivery rates followed that stop.

## Diagnosis

The previous display benchmark used an already prepared window. It did not cover
preparing phase views for fresh live records or switching to an uncached receiver.
A 360-record cold window took about 210 ms in an isolated check using copies of
preserved payload samples. A later interactive test also failed while switching
receivers, despite an earlier one-minute static-view test passing.

Profiling and regression tests found additional avoidable work: NumPy was called
once per usable subcarrier for raw phase, and the wireless pending-envelope path
decoded each validated CSI batch a second time. Removing those costs alone did
not prevent cold-window stalls. Queue length alone also missed old work: even a
single queued chunk can already be close to its deadline.

## Implemented changes

- Wireless ingestion reuses the validated envelope and decoded packet after
  receiver boot evidence arrives. Run, transmitter/receiver identity, profile,
  duplicate, recording and ACK checks still execute at acceptance.
- LTF magnitude and raw-phase preparation operates on whole arrays, preserving
  invalid-slot, finite-value, amplitude-floor and physical-subcarrier masks.
  The calibrated-phase fitting algorithm is unchanged.
- Before drawing a window, the dashboard warms at most 16 uncached records or
  approximately 8 ms of preparation per refresh. It resumes on later ticks
  rather than calibrating the entire window in one callback. One record is the
  smallest work unit, so this is a scheduling budget rather than a hard real-time
  guarantee. Acquisition continues independently.
- Receiver changes clear old traces while the new window prepares. The panel
  shows “Preparing preview…” during warmup and “Preview paused” when ingestion
  needs priority. Fully prepared plots retain every sample in the selected
  window; warmup does not decimate or alter recordings.
- On the current POSIX setup, a small process drains the existing serial
  descriptor, independent of Qt's Python interpreter. It preserves read-completion
  timestamps and ordered bytes through bounded IPC; the parent retains control
  writes. Its additional FIFO is bounded at 256 KiB / 256 chunks, with the same
  200 ms age limit. The parent buffer and its limits remain unchanged. Injected
  serial test adapters and non-POSIX hosts retain the thread reader.
- Optional plotting yields when USB input is older than 25 ms or more than eight
  chunks are pending. The existing reference-backlog check remains. The 200 ms
  ingestion deadline, queue capacities, timestamps and acquisition checks are
  unchanged.

Tests first demonstrated the duplicate decode and insufficient age-based preview
pause, then passed after their fixes. Additional deterministic tests check the
record/time preparation budgets, preview retry behavior, receiver-trace clearing,
non-finite/masked numerical equivalence and complete snapshots after warmup.
Original raw recordings remain unchanged.

## Hardware evidence and limits

The final bounded-preparation implementation completed a one-minute visible
viewer test with automatic receiver changes every ten seconds and dashboard/
phase-detail tab changes every twenty seconds. All four receivers delivered;
there was no ingestion failure. Maximum dequeued USB wait was 91.99 ms, and the
queue drained to zero at shutdown.

The first longer bounded-preparation run avoided the original age error but
failed around 244 seconds when the gateway's 20 ms USB forwarding deadline was
missed. Observed GUI timer gaps reached about 139 ms. A POSIX pseudo-terminal
test now deliberately holds the parent interpreter's GIL for 150 ms and verifies
that the separate process drains input during that pause, preserves its original
timestamps, and forwards the same bytes. Disconnect and shutdown tests exercise
its failure and drain behavior.

With isolation, a later channel-6 run had zero new gateway USB forwarding errors
but stopped around 124 seconds on an RF `peer_timeout`, accompanied by many
companion retries. The laptop and another strong visible access point were on
channel 6. A separate channel-11 trial completed successfully without changing
5 GHz sensing. This supports the interference hypothesis but does not isolate it
from all time-varying RF conditions. Channel 11 is now the configured default;
the two C6 endpoints are paired on that channel.

A separate earlier one-minute static-view test, before bounded cold preparation,
had no new gateway USB forwarding errors, UART errors or relay drops. Its maximum
USB wait was 153.38 ms. That result did not cover receiver switching; the
subsequent switching failure is retained rather than treated as a passing run.

The final channel-11 visible viewer run completed 300 seconds, automatically
switching among all four receivers every ten seconds and between dashboard and
phase-detail views every twenty seconds. It accepted 114,990 records; all were
timely under the configured availability policy. All thirty receiver-view
intervals had continuing plot updates. Gateway received/forwarded counters both
increased by 57,551, with zero new USB errors, rejects, relay drops, UART errors
or peer changes. Three gateway-side and 153 companion-side retransmissions were
recovered. Maximum host USB wait was 109.80 ms, and the queue drained to zero.
This is a GUI stability soak, not the separately defined warmup/measurement
throughput qualification.

The collector then completed a separate one-minute interactive preview check on
channel 11 with all four receivers and no fault; maximum USB wait was 80.98 ms.
Its validation session ended normally with zero activity attempts. No participant
or human activity was simulated. The complete host/native suite passed 507 tests.
Final discovery verified sensing stopped, no UART fault, the relay ready, and the
unchanged sensing fingerprint `8b28a906a0fbcd1f`. The new transport fingerprint is
`2d1b83fe35925a03` because the backhaul channel changed.

Artifacts are under ignored `data/experiments/gateway/usb-backlog-20261103/`.
Failed runs, reset logs, raw envelopes, receiver CSVs and timing journals are
retained. Throwaway probes/profiles live in `.codex-build/usb-backlog/` and are
not production modules. Recovery rebooted endpoints without flashing firmware or
changing the radio profile or pairing keys.

These checks address host ingestion stability. They are not an 80-record/s
throughput qualification, a phase-stability experiment, a fall-detection result
or a camera-load qualification.
