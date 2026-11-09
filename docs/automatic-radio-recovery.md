# Automatic radio recovery

The viewer and collector reconnect automatically after an interrupted radio
link while the application remains open. The transmitter still waits for a host
run configuration and start command after boot; it does not transmit autonomously
when the desktop application is closed.

## Recovery behavior

`radio/live.py` supervises individual `GatewayReceiverManager` runs. A transmitter,
companion or gateway restart ends the affected run. USB stream truncation during
reboot also ends that run; it is never treated as a valid packet. Recovery then:

1. Notifies the collection controller immediately, including when GUI refreshes
   are paused. An active attempt becomes invalid and its partial CSI/video files
   are retained. The operator must retry or skip it.
2. Stops and joins the old workers before opening their ports again. Reconnection
   starts after three seconds and backs off to at most 30 seconds while hardware
   remains unavailable. Closing the application cancels retries.
3. Discovers the configured gateway identity. When an old UART relay epoch needs
   replacing, stops its configuration and requests an idle gateway restart using
   USB frame type 31 with payload `CRRC`. Firmware rejects this request while the
   gateway is configured. Pairing keys and radio profiles remain in NVS.
4. Reconnects the paired C6s. An inactive companion can discard its ended stream
   and clear a recoverable fault when it receives a new authenticated peer boot
   epoch. Active runs still fail on a peer restart. Old boot/nonce packets cannot
   restart the ended stream, and cumulative diagnostic counters are retained.
5. Creates a fresh run ID, clock estimator, receiver states, preview buffers and
   transport journal. It reconfigures the transmitter, gateway and receivers,
   re-establishes timing and resumes sensing. Readiness returns after fresh data
   arrives from all configured receivers.

The C5 and companion release a latched UART fault only after their active run
ends. CRC/framing checks continue on subsequent frames. The C5's existing
three-second control lease still stops sensing if host control disappears.

The specific gateway USB receive-buffer age errors now also end the old run and
trigger recovery. Stale input is not accepted, the interrupted attempt stays
invalid, and the 200 ms guard is unchanged. This allows a transient host stall
to recover without stranding the collection session.

Identity/profile mismatches, storage failures, invalid CSI envelopes and bounded
buffer overflows remain terminal. Other queue-age errors are not broadly
reclassified. A lost or truncated USB reference
frame can trigger a new run, but its damaged run and interrupted attempt remain
failed. Automatic recovery applies to the live `espnow_uart` and USB-reference
applications; the deferred BLE reference path remains unchanged. Hardware
benchmarks retain their strict single-run behavior, so an outage cannot be hidden
inside a passing concatenated benchmark.

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
streams, session events and raw gateway envelope/event/availability journals.
It batches physical writes on a separate thread every five seconds. Use
`--recording-flush-seconds <seconds>` to change the interval. Camera encoding
retains its existing independent process and per-frame timing.

Frequent stream `flush()` calls check memory admission; the dedicated recording
service owns disk flushing. The memory limit includes bytes being written.
Overflow and disk errors fail explicitly. Closing an attempt requests a bounded
drain, and acceptance waits for its streams to finish saving. Normal collector
shutdown drains all admitted records. Enabled application ACKs still wait for
the recording service's file-buffer flush before transmission.

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
include `run_resuming` and, after full readiness, `run_recovered`. Collection also
records `radio_interrupted` in the session event log. No synthetic CSI or
backfilled availability bins fill the gap between run segments. An accepted
attempt cannot silently span the interruption.

Session protocol selection, sensing profile `8b28a906a0fbcd1f`, channel-11 backhaul,
96-record receiver queues, 750 ms retention and the 200 ms host USB guard are
unchanged. Recovery requires the updated C5 and both C6 applications; C6 discovery
advertises `relay_recovery_version: 1`. Receiver firmware needs no additional
change for this feature.

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
