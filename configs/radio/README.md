# Radio configuration

`receivers.json` contains the user's four-C5 sensing roster in legacy schema v1.
The live gateway inventory is `gateway_inventory.json`, containing one C5
`transmitter`, four ordered C5
`receivers`, and a C6 `gateway`, each with a verified unique ID and MAC address.
Historical schema-v1 inventories remain readable for offline analysis; saved
recording inventories remain immutable. Do not fabricate additional devices.

Use `profiles/indonesia_5g_ch44_80hz.json` for sensing and
`espnow_transport.json` for the fixed-channel 2.4 GHz ESP-NOW upload policy.
Other legacy profiles remain versioned for historical sessions. Runtime fingerprints
include ordered identities, both channels and transport settings.

The default gateway policy retains four batches and deadline return. Opt-in
trials are `espnow_transport_eight_batches.json` and
`espnow_transport_early_return.json` (version 2, eight batches; the latter enables
a 5 ms idle-return grace). Compatible firmware is required on all three roles.
See [measured results and limits](../../docs/espnow-window-return-2026-11-02.md)
before treating either as a collection candidate.

CGCF-v3 experiments add `espnow_transport_revisit_150ms.json` and
`espnow_transport_revisit_200ms.json` for per-receiver cadence, then
`espnow_transport_revisit_150ms_eight_batches.json` and
`espnow_transport_bitmap_ack.json` for burst/ACK comparisons. The latter polls
up to eight explicit batch IDs in one gateway request. All keep 50 ms slots,
the 10 ms channel-return reserve and deadline return.
`espnow_transport_send_metrics.json` enables aggregate MAC-completion timing;
`espnow_transport_send_guard_5ms.json` is an unqualified shorter-send-guard trial,
not a collection default. Failed-send measurements are required before using it.
`profiles/indonesia_5g_ch44_100hz.json` is a separate sensing-rate trial; provision
both C5 roles to its fingerprint and restore 80 Hz afterward. See
[cadence measurements](../../docs/espnow-cadence-2026-11-02.md).

`espnow_transport_retention_750ms.json` tests a 750 ms record lifetime with
900 ms availability grace and the original four-batch/one-retry scheduling.
`espnow_transport_retention_750ms_retry2.json` changes the budget to two retries
and requires CGCF-v4 firmware on all roles. Version 4 supports at most three
retries; versions 1–3 retain their one-retry limit. These experiments leave the
normal default file unchanged. See
[retention and retry measurements](../../docs/espnow-retention-2026-11-02.md).
`espnow_transport_retention_750ms_retry2_paced.json` additionally spaces retry
eligibility using a 150 ms ACK timeout, so a brief interruption need not consume
all attempts immediately. It retains the same lifetime and channel deadlines.

`espnow_transport_bulk_80ms.json`, `espnow_transport_bulk_100ms.json` and
`espnow_transport_bulk_125ms.json` test larger authorization windows with
32/40/48 submitted records per turn. They retain the 10 ms send/return reserves,
750 ms lifetime and one-second delivery target. These explicitly changed
settings are experimental, not promoted defaults. Single-receiver measurements
used additional revisit pacing, stored in their recording manifests; they do
not qualify these policies on four physical receivers. See
[bulk measurements and the timing model](../../docs/espnow-bulk-timing-2026-11-02.md).

Provision C5 boards sequentially using the complete inventory; the C6 gateway is
configured per run over its own USB link. See the
[gateway procedure](../../docs/espnow-gateway.md). `ble_transport.json` is retained
for historical experiments, not current collection.
Reprovision the transmitter after changing the receiver list even when the
sensing-profile fingerprint is unchanged; runtime transport checks compare the
stored peer list separately. Receiver USB data connections are unnecessary
during acquisition. The four-radio bring-up is recorded in
[the hardware report](../../docs/espnow-four-receivers-2026-11-02.md).

`espnow_transport_ackless.json` is an opt-in CGCF-v5 trial with no application
ACKs or retries. It retains unicast MAC feedback and the 5 GHz return interlock;
the transmitter still requires USB control and clock mapping. All three roles
need v5-capable firmware. Default collection remains acknowledged. See
[ACK-less scope and measurements](../../docs/espnow-ackless-2026-11-02.md).

CGCF-v6 throughput trials use `espnow_transport_throughput_mcs0.json` through
`espnow_transport_throughput_mcs3.json`: HT20 long-GI MCS0–3, 125 ms windows,
64 submitted records per slot, 750 ms lifetime and ACK-less application delivery.
The receiver's event worker and optional fixed-160-MHz CPU overlay are build
choices recorded separately from the transport fingerprint. Profile
`profiles/indonesia_5g_ch44_120hz.json` uses profile schema v2 and requires v6
transport plus compatible C5 firmware. Historical profile schema v1 retains
its 100 Hz maximum. No normal default is changed. Use the benchmark's explicit
`--target-records-s 80`; real four-receiver qualification remains necessary.
See [higher-throughput trials](../../docs/espnow-throughput-2026-11-02.md).

The CGCF-v7 `espnow_transport_throughput_mcs3_queue96.json` and corresponding
`_ack.json` variant explicitly size the record pool to 96 for 120 Hz/750 ms
retention; the upload allowance remains 64. The ACK variant retains genuine
processor-acceptance feedback and two bounded retries. Upgraded firmware sizes
control-only ingress messages to 180/96 bytes on receiver/transmitter, retaining
32 entries and full 1400-byte data ingress at the gateway. This offsets the
larger record reservation; defaults and v1–v6 active capacities remain 64.
These remain experimental policies; see the throughput report for failed checks
as well as achieved rates.
