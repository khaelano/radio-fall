# Dedicated UART transmitter relay

The default `espnow_uart` reference connects the sensing transmitter to the
laptop through a separate C6 radio. The data path is:

```text
Laptop ── USB ── gateway C6 ── encrypted ESP-NOW ── companion C6 ── UART ── sensing C5
                  │
                  └── existing ESP-NOW uploads from the four sensing receivers
```

The C5 keeps its provisioned 5 GHz sensing profile. Its reference module uses
UART0 and does not initialize BLE, scan, retune, or send host-reference traffic
through the sensing radio. The companion owns the additional 2.4 GHz radio
traffic. This traffic shares gateway airtime with receiver uploads, so throughput
and clock uncertainty must still be measured. Receiver firmware, record encoding,
slot ownership, and return confirmation are unchanged.

The current setup selects this reference in `configs/radio.json`. USB control
remains available with `--transmitter-link usb`. The older direct-C5 BLE
experiment remains deferred; see [the BLE reference notes](wireless-transmitter.md).

## Wiring and firmware

Connect C5 GPIO11 TX to companion C6 GPIO17 RX, companion GPIO16 TX to C5
GPIO12 RX, and common ground. UART0 uses 921600 baud, eight data bits, no parity,
one stop bit, and no hardware flow control. Both endpoints use CRC-protected
COBS `CSIS` frames. Disable the UART console so log text cannot enter this link.
Native USB discovery and idle provisioning remain available on the C5.

Build all three projects with ESP-IDF 6.1 in separate directories and with
separate `SDKCONFIG` files. Append these defaults to each project's normal
`sdkconfig.defaults`:

| Project | Additional defaults |
| --- | --- |
| `transmitter` | `common/sdkconfig.performance160;common/sdkconfig.uart-reference` |
| `relay` | Appropriate XIAO C6 antenna overlay, if applicable |
| `gateway` | Appropriate C6 board overlay; `common/sdkconfig.performance160;common/sdkconfig.espnow-relay` |

Pass absolute paths in `SDKCONFIG_DEFAULTS`; paths in the table are relative to
`src/firmware/radio/`. The relay defaults already enable UART and the ESP-NOW
relay. Use the built-in antenna overlay unless an external antenna is attached.
The identified companion in this setup uses its built-in antenna, as confirmed
by the user; the previous external-antenna selection was incorrect for it.
The C5 must not enable `CSI_ESPNOW_UART_RELAY` or `CSI_WIRELESS_TRANSMITTER`.
The gateway does not enable the UART reference.

Back up each identified board's complete flash before replacing its image.
Snapshots include NVS credentials and belong in private ignored storage. The
three current builds fit the existing 1 MiB factory partition. Check the
partition table against the board before flashing; preserve the transmitter's
NVS profile and receiver roster. Firmware build success does not prove hardware
reliability.

## Pair and operate

The current boards are already paired. Pair again only for new hardware or
cleared NVS, with sensing stopped and both C6 USB ports connected. The shared
`configs/radio.json` identifies the gateway and companion ports; an explicit
`--port` override for pairing names the companion C6:

```sh
uv run csi-radio transmitter pair
uv run csi-radio transmitter status
```

Pairing checks the companion's role and the gateway's inventory identity,
generates fresh ESP-NOW PMK/LMK material, stores it only in their NVS, and reboots
both C6s. A partial pairing must be repeated on both endpoints. The paired
channel must match the receiver backhaul policy; a conflicting gateway
configuration is rejected. The transmitter's logical sensing MAC is verified
through the complete relay after pairing.

Only the gateway requires laptop USB data during operation. The viewer,
collector and benchmark load the same configuration automatically:

```sh
uv run csi-viewer
uv run fall-collection
uv run csi-gateway-benchmark
```

The benchmark defaults to 30 s warm-up, 300 s measurement and an 80-record/s
per-receiver target. Use `--config <file>` for another setup. Power the C5 and
companion independently after setup. `csi-radio transmitter provision` also
loads the same sensing profile; it is rejected while sensing runs. See the
[configuration guide](radio-configuration.md) before changing a channel or roster.

## Integrity and failure behavior

`CRL1` reference packets use explicitly paired encrypted ESP-NOW unicast peers,
CRC32, persisted boot counters, random boot nonces and peer-nonce echoes.
The reference peers use HT20 MCS0 for link margin, independently of the
receiver-upload PHY. Fault packets preserve the originating endpoint reason.
The four-packet ARQ window preserves message order, suppresses duplicate command
execution and retries missing packets. It shares the bounded lossless block
codec with the earlier BLE implementation. Outstanding packets retain their
original 750 ms lifetime; retries do not extend it. Each endpoint has a bounded
64 KiB source queue so retry bursts can be absorbed within the packet deadline. Radio callback queue loss can be retransmitted; admitted
source loss, expiry and application delivery failure fault the reference.

The UART module has bounded receive/transmit rings. It checks capacity before
submitting a complete frame instead of waiting for a congested transmit ring.
Framing, CRC, FIFO and UART errors during sensing fault that local reference.
The host also retains its strict original-round sequence, boot and log-drop
checks; UART CRC is not a delivery acknowledgement.

The authoritative sensing timestamps and clock-exchange timestamps originate on
the C5. The bridge never substitutes its own time. Clock uncertainty includes
the entire transport round trip; drift fitting requires a ten-second baseline.
CSI envelopes can wait at most 750 ms in the existing bounded host queue for
matching transmitter boot evidence. Failure never becomes a synthetic record
or a silently backfilled model-input bin.

A peer restart during an active session, reference timeout, source overflow, or
host USB forwarding failure ends the reference. The companion attempts a local
UART stop when its radio link fails. The independent three-second C5 host-control
lease stops sensing if valid host control stops reaching it, including when the
UART stop cannot arrive. USB and UART cannot take over each other's active
session. A faulted transport ends its current radio run. Updated live
applications automatically reconnect, reset an idle gateway epoch when needed,
and establish a fresh run and clock fit. The collector retains the interrupted
attempt as invalid; retry or skip it after recovery. Both C6s advertise
`relay_recovery_version: 1`; the C5 also needs the idle UART-fault release update.
See [automatic recovery](automatic-radio-recovery.md) for behavior, validation
and the distinction between a resumed collection session and a new radio run.

Gateway and companion status expose `relay_ready`, `relay_fault`,
`relay_failure_reason`, `relay_drops`, `relay_peer_changes`, `relay_retries`, and
`relay_queued_bytes`. Gateway status also carries the companion queue occupancy/peak, retransmissions
and UART error counter. These counters are lifetime diagnostics, not receiver
record counts. The companion additionally reports UART pins, baud rate,
errors and received frames. USB debug output on the companion is not part of
the live reference path.

## Verification

The relay implementation was validated with 454 host/native tests and ESP-IDF 6.1 builds
for the C5 transmitter, C6 companion and C6 gateway. Native tests exercise the
actual relay implementation with deterministic loss, duplicates, reordering,
stale boot/nonce evidence, packet expiry, queue overflow, failed delivery and
preservation of the originating fault reason. UART parser tests cover full-size
frames, corruption, overflow and resynchronization. Host integration tests cover
both wireless modes, four receiver streams, missing pairing and missing boot
evidence. Pairing tests verify both USB identities before any key write.

Hardware validation on 3 November 2026 used the unchanged four-C5 inventory,
120 Hz HE20 sensing profile and v7 125 ms/MCS3 ACK-less receiver upload policy.
The final companion uses its built-in antenna; reference traffic uses MCS0.
Only gateway USB carried the laptop reference during the normal benchmark.
The C5 and companion USB ports were not opened by the benchmark.

| Receiver | USB baseline, 30 s (records/s) | UART relay, 300 s (records/s) | Relay p99 delay (ms) |
| --- | ---: | ---: | ---: |
| rx-1 | 98.93 | 97.73 | 706.25 |
| rx-2 | 98.90 | 98.84 | 480.41 |
| rx-3 | 98.80 | 98.88 | 480.04 |
| rx-4 | 98.90 | 98.84 | 480.33 |

The relay run followed 30 s of warm-up and passed the existing four-receiver
80-record/s qualification. All 118,288 records delivered in its measurement
window were below one second, including clock uncertainty. Receiver queue peaks
were 80/96 and all operational queue-growth checks passed. Across the complete
331.5 s sensing span, all 39,786 round logs were retained with zero skipped
sensing rounds, no transmitter boot change and no transmitter log loss.
Gateway USB errors, reference drops and companion UART errors remained zero.
Thirteen reference retransmissions were recovered; the companion queue peaked
at 1,297/65,536 bytes.

All 2,119 grant intervals had complete timing evidence, and their conservative
off-channel bounds showed no cross-receiver overlap. The independent individual
return/deadline comparison classified 19 intervals before deadline and 2,100 as
uncertain, with none classified after deadline. The wireless reference therefore
does not establish tight slot-return timing or phase stability. Different
baseline/run durations and simultaneous implementation changes do not establish
statistical equivalence to USB.

The host-control-loss check stopped sensing after 3.125 s without valid control,
while USB clock/control takeover of the active UART session was rejected.
Resetting the gateway stopped sensing within 1.078 s without changing the C5's
boot identity. The companion reported packet expiry during that outage and
attempted its local UART stop. These checks used separate recordings; diagnostic
USB ports were held open to observe the C5 without resetting it during the fault.
Fault recovery restarts the C6 endpoints and begins a new session.

Earlier trials are retained. The first 30 s relay probe delivered 97–99 records/s
but had broad clock uncertainty. Polling latency was reduced, and unsolicited
idle USB telemetry was corrected so an absent setup client cannot fault the next
run. Two longer trials with a 16 KiB source queue and the incorrectly selected
external antenna stopped on reference faults; the instrumented trial identified
companion source-queue overflow. The successful configuration selects the
confirmed built-in antenna, uses MCS0 reference peers and retains a bounded
64 KiB queue. Their separate causal effects were not measured.

Raw journals, derived reports, fault-check results and private pre-flash snapshots
are retained under `data/experiments/gateway/uart-relay-20261103/`. The passing
report is in `builtin-mcs0-qualification/`; `qualification-summary.json` and
`hardware-fault-checks.json` provide compact derived evidence. Firmware/source
fingerprints accompany the trials. The maximum 1,276-byte command was also
verified across both C6 radios and UART with a deliberately invalid profile;
validation rejected it and the persisted sensing profile remained unchanged.
Post-recovery wireless and USB fallback smoke runs both completed without
transmitter log loss. The final idle check verified radio-off, stopped gateway
configuration and the unchanged 120 Hz sensing profile. Raw journals were not rewritten.

USB recovery remains available. A five-minute pass and these controlled fault
checks do not qualify longer unattended operation, room changes, movement,
phone-video/GUI load or detector accuracy. Keep USB reference as the default
until the intended collection setup has passed its own longer reliability run.
