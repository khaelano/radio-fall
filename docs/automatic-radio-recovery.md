# Automatic radio recovery

The viewer and collector reconnect automatically after an interrupted radio
link while the application remains open. The transmitter still waits for a host
run configuration and start command after boot; it does not transmit autonomously
when the desktop application is closed.

## Recovery behavior

The native session (`radio_transport::session`, driven through
`NativeAcquisition` by `radio/live.py` and directly by `fall-detect`) owns
recovery. A transmitter, companion or gateway restart ends the affected run.
USB framing errors after acceptance starts also end that run; a damaged frame
is never treated as a valid packet. Recovery then:

1. Reports the failure once through `health()`. `LiveRadio` calls the
   interruption callback immediately, including while GUI refreshes are paused.
   An active collection attempt becomes invalid and its partial CSI/video files
   are retained. The operator must retry or skip it.
2. Closes the serial port, sending best-effort stop commands to the gateway and
   relayed transmitter. Reconnection starts after three seconds (two in
   `fall-detect`) and backs off
   linearly to at most 30 seconds while hardware remains unavailable; a run that
   accepted data resets the backoff. Stopping the application cancels retries.
3. Discovers the configured gateway identity. A gateway still configured for an
   older run receives that run's stop command. After a failure, a faulted relay
   epoch is restarted with USB frame type 31 and payload `CRRC`; firmware without
   `relay_recovery_version` 1 makes the session stop. The gateway reboots to
   restart the epoch. The session then waits up to eight seconds for relay
   readiness and, after that reboot, for the new gateway `boot_id`. It drops
   queued gateway statuses from the old boot: acquisition replays queued
   startup frames before reading the port, and an old-boot status would fail
   its boot check. Pairing keys and radio profiles remain in NVS.
4. Reconnects the paired C6s. An inactive companion can discard its ended stream
   and clear a recoverable fault when it receives a new authenticated peer boot
   epoch. Active runs still fail on a peer restart.
5. Starts a fresh run ID, clock fit, receiver ledger, availability grid and
   transport journal. The journal manifest's `recovery` field and a
   `run_resuming` event name the previous run and failure. Readiness returns
   after fresh status and data arrive from all configured receivers.

The C5 and companion release a latched UART fault only after their active run
ends. The C5's three-second control lease still stops sensing if host control
disappears.

Failures that would recur on every run stop the session instead of retrying:
identity, profile or boot mismatches, refused or rejected control commands,
missing firmware capabilities, invalid configuration and journal or storage
errors (`radio_transport::session::recoverable`). Interrupted links, timeouts,
lost status or reference evidence, receiver reboots and record-queue overflow
start a new run. Python storage failures do not stop acquisition: the Rust
journal already holds every acknowledged envelope, and `LiveRadio` reports the
failure and invalidates the attempt.

The retry and classification logic is covered offline by
`tests/radio/test_native_session.py` against a fake gateway, which neither
reboots nor faults its relay. The
[18 November hardware check](#hardware-check-18-november-2026) exercised the
native session's USB-loss and relay-recovery paths through `fall-detect`; the
3 November validation predates the native session.

## Resume a saved collection session

After closing the old collector normally, reopen its session directory:

```sh
uv run fall-collection --resume-session data/raw/sessions/20261104T081805521126Z
```

The collector loads the saved protocol, participant metadata and explicit trial
dispositions, and continues at the first unresolved trial. It restores the saved
camera device/settings when no new device is specified. Radio profile, receiver
identities, transport fingerprint and enabled video mode must match. The current
protocol file is not substituted for the saved queue.

Accepted recordings are not reopened. Retried attempts use fresh numbers, and
new radio runs have independent timing journals. Unresolved recording/review
attempts become invalid on resume; their original metadata is retained as
`attempt.before-resume.json`, and their CSI/video bytes remain unchanged. An
accepted attempt whose resolution event was interrupted can recover that explicit
decision. Malformed/conflicting journals or fully resolved sessions are rejected.

The session event log is appended, and `session.json.resumptions` records prior
status, new environment, UTC/monotonic timestamps and host boot identity. POSIX
writer locks prevent a second collector opening the same session; Linux also
checks writers from the older version that did not acquire this lock.

## Buffered collection recording

The collector uses a shared 32 MiB in-memory writer for receiver CSV/timing
streams and session events. It batches physical writes on a separate thread
every five seconds. The native session writes the raw gateway
envelope/event/availability journals itself and flushes each accepted envelope
to the file buffer before its ACK. Use
`--recording-flush-seconds <seconds>` to change the interval. Camera encoding
retains its existing independent process and per-frame timing.

Frequent stream `flush()` calls check memory admission; the dedicated recording
service owns disk flushing. The memory limit includes bytes being written.
Overflow and disk errors fail explicitly. Closing an attempt requests a bounded
drain, and acceptance waits for its streams to finish saving. Normal collector
shutdown delivers and drains all accepted records. Application ACKs certify the
native envelope journal, not the later CSV write: CSV rows are produced from the
same accepted records after the ACK, and the journal can regenerate them.

Live availability timestamps describe validated application-memory acceptance,
not the later physical write. No sensing timestamp or finalized bin is moved.
Neither memory acceptance nor file-buffer flushing is power-loss durability:
a crash can lose queued writes since the preceding flush. Small lifecycle
metadata files still publish atomically at transitions.

The 4 November regression suite passes 559 tests, including slow storage,
periodic flush, byte ownership/capacity, I/O failure, restart progress and
completed-file preservation. The interrupted session above reopened at trial 33
of 232 with all four receivers delivering and zero gateway USB errors during
the startup check. All 640 files in its 32 accepted attempts matched their
pre-resume SHA-256 hashes. No activity attempt was started by this validation.
This startup check does not establish extended GUI/video endurance or prove
which operation caused the earlier host stall.

## Recording evidence

The old transport journal records `run_interrupted`. Each replacement manifest
has a `recovery` object containing `previous_run_id` and `reason`, and its events
include `run_resuming`. The native session does not write the former
`run_recovered` event; readiness is visible in `health()` and the status log.
Collection also records `radio_interrupted` in the session event log. No synthetic CSI or
backfilled availability bins fill the gap between run segments. An accepted
attempt cannot silently span the interruption.

Session protocol selection, sensing profile `8b28a906a0fbcd1f`, channel-11 backhaul,
96-record receiver queues, 750 ms retention and the 200 ms host USB guard are
unchanged. Recovery requires the updated C5 and both C6 applications; C6 discovery
advertises `relay_recovery_version: 1`. Receiver firmware needs no additional
change for this feature.

## Hardware check, 18 November 2026

Headless `fall-detect` sessions (`cnn-4s`) ran on the gateway, companion relay,
C5 transmitter and four receivers. The journals are in
`data/experiments/detector/recovery-20261118/` (DVC); its README maps each
directory to the case below.

In an ordinary detector session, the relay faulted after about seven minutes
(`peer_uart_fault`), and the run ended with `reference failed or stale`.
Recovery sent `CRRC` and the gateway rebooted, but the replacement run stopped
as fatal with `gateway status identity/boot/readiness mismatch`. During startup
the controller had queued periodic statuses from the old gateway boot, and
acquisition replayed them against the new `boot_id`. The rejected frame is not
journaled; because the firmware fixes every other checked field, the boot ID is
the inferred mismatch. The old-boot filtering in step 3 is the resulting fix.

With the fix, the following interruptions were applied by hand during scoring:

| Interruption | Recovery | Result |
| --- | --- | --- |
| Gateway USB unplugged for about 30 s | Failed port-open retries, then a run on the new gateway boot | Scoring resumed |
| Companion relay power removed for about 30 s (`packet_expired`) | `CRRC` rebooted the gateway; that attempt and the next timed out waiting for the relay; the third started normally | Scoring resumed |
| Companion relay power removed for about 8 s (`packet_expired`) | One attempt: `CRRC`, gateway reboot, relay readiness, acquisition 8.3 s after the fault status | Scoring resumed about 20 s after the fault |

Durations are approximate: the operator counted them, and the journals bound
them only by status and run timestamps. The 8-second case repeats the sequence
that failed before the fix. Dropped frames are not journaled, so the check
cannot show how many old-boot statuses that attempt discarded. No kernel USB
disconnect accompanied the `CRRC` reboots. The cause of the original
`peer_uart_fault` is unknown, and detection accuracy was not assessed.

## Hardware validation, 3 November 2026

The C5 and both C6s received app-only updates after private full-flash backups
and checks of their actual application partitions. NVS, pairing and the sensing
profile were preserved; the companion uses its built-in antenna. Stationary
transport checks used four powered sensing receivers and an active collection
attempt; no human activity or detector result is claimed.

| Interrupted device | Reset to verified reception (s) | Interrupted attempt | Resumed receivers |
| --- | ---: | --- | --- |
| Transmitter C5 | 11.620 | Invalid | 4/4 |
| Companion C6 | 11.620 | Invalid | 4/4 |
| Gateway C6 | 9.113 | Invalid | 4/4 |
| C5 application unavailable for 12 s | 20.241 | Invalid | 4/4 |

The reset checks pulsed USB reset control. The longer outage held the C5
application in its ROM bootloader for 12 seconds, then restarted it. Reported
durations include a three-second reception check after readiness. All cases
created fresh run IDs and clock estimators; C5 resets also changed its boot ID.
Every resumed receiver produced new records. The longer outage included a failed
discovery retry before the application returned.

An initial gateway check exposed truncated USB framing as an additional reboot
signal; automatic recovery now covers that case. The successful repeat and the
original failed journals are retained. Sensing-off, unchanged profile and both
C6s ready without a relay fault were verified after testing. Artifacts and
deployment manifests are under
`data/experiments/gateway/automatic-recovery-20261103/`, including
`validation-summary.json` and `final-state.json`. Native/host tests, SDK build
logs and debug harnesses are under `.codex-build/automatic-recovery/`.
All three ESP-IDF builds passed. The final repository test run passed 536 tests,
including native relay epoch recovery, host worker replacement/cancellation,
immediate attempt invalidation and health reconciliation after paused rendering.

These checks verify controlled restart/outage recovery. Electrical supply
removal, camera-enabled recovery and long unattended outage cycles have not
been qualified by these checks. Earlier intermittent C6 reference timeouts
remain a separate RF/power diagnosis; automatic recovery does not establish
their cause or recover the interrupted measurements.
