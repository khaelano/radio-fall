"""Offline contracts for the real BLE path; no radios or network required."""

from __future__ import annotations

import asyncio
import json
import shutil
import struct
import subprocess
import time
import zlib
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from fall_detection.radio.acquisition.availability import (
    AvailabilityGrid,
    RoundReceipts,
)
from fall_detection.radio.acquisition.ble_journal import BleJournal, iter_envelopes
from fall_detection.radio.acquisition.ble_protocol import (
    FRAGMENT,
    STATUS_FIELDS,
    BleBatch,
    BleReassembler,
)
from fall_detection.radio.acquisition.ble_reader import (
    BleIngestionError,
    BleReceiverManager,
)
from fall_detection.radio.acquisition.protocol import CsiRecord
from fall_detection.radio.acquisition.wire import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)
from fall_detection.radio.ble_config import (
    STATS_UUID,
    BleTransportConfig,
    grant_owner,
    inventory_crc,
)
from fall_detection.radio.profile import (
    RadioInventory,
    RadioProfile,
    RadioProfileError,
    profile_fingerprint,
)


def inventory(count=4, targets=("esp32c5",)):
    def device(i, role):
        return dict(
            id=f"{'rx' if i else 'tx'}-{i}",
            role=role,
            target=targets[i % len(targets)],
            mac=f"02:00:00:00:00:{i:02x}",
        )

    return RadioInventory.from_mapping(
        dict(
            schema_version=1,
            transmitter=device(0, "transmitter"),
            receivers=[device(i, "receiver") for i in range(1, count + 1)],
        )
    )


def profile(rate=80, band="5ghz"):
    return RadioProfile.from_mapping(
        dict(
            schema_version=1,
            profile_id=f"test-{rate}",
            country_code="ID",
            band=band,
            channel=44 if band == "5ghz" else 6,
            bandwidth_mhz=20,
            nominal_rate_hz=rate,
        )
    )


def batch(
    *,
    run=123,
    tx=11,
    rx=21,
    identity=0,
    sequence=0,
    mac="02:00:00:00:00:01",
    fingerprint="0123456789abcdef",
    captured=1000,
    channel=44,
):
    record = CsiRecord(
        sequence,
        "02:00:00:00:00:00",
        -40,
        -95,
        900,
        (complex(1, 2), complex(3, 4), complex(5, 6)),
        receiver_mac=mac,
        tx_timestamp_us=captured,
        rx_callback_timestamp_us=captured + 1,
        profile_fingerprint=fingerprint,
        csi_length=6,
        sig_mode=4,
        channel=channel,
    )
    payload = encode_csi_batch(
        (DecodedCsiDatagram(record, mac, sequence),),
        boot_id=rx,
        batch_sequence=identity,
        receiver_stats=ReceiverStats(*([0] * 10)),
    )
    return BleBatch(run, tx, rx, identity, payload)


@pytest.mark.parametrize("rate", [50, 60, 70, 80, 100])
def test_rate_contract_accepts_supported_rates(rate):
    assert profile(rate).nominal_rate_hz == rate


@pytest.mark.parametrize("rate", [49, 101, 80.5, True, "80"])
def test_rate_contract_rejects_invalid_rates(rate):
    with pytest.raises(ValueError):
        profile(rate)


def test_scheduler_round_robin_fixed_slots_and_optional_random():
    assert [grant_owner(i, 4) for i in range(12)] == [0, 1, 2, 3] * 3
    assert grant_owner(0xFFFFFFFF, 4) == 3
    assert grant_owner(0, 4) == 0
    random = [grant_owner(i, 4, "random", 23) for i in range(100)]
    assert random == [grant_owner(i, 4, "random", 23) for i in range(100)]
    assert any(a == b for a, b in zip(random, random[1:]))
    assert random != [grant_owner(i, 4, "random", 24) for i in range(100)]
    assert set(random) == set(range(4))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(queue_capacity=65),
        dict(scheduler="adaptive"),
        dict(ack_timeout_ms=251),
        dict(drain_ms=100),
        dict(seed=-1),
        dict(records_per_grant=True),
    ],
)
def test_ble_config_rejects_unbounded_or_inconsistent_settings(kwargs):
    with pytest.raises(ValueError):
        BleTransportConfig(**kwargs)


def test_ble_config_defaults_and_fingerprint(tmp_path):
    config = BleTransportConfig()
    assert config.scheduler == "round_robin"
    assert len(config.encode(123, 4, 80)) == 64
    assert config.encode(123, 4, 80)[36:52] == config.fingerprint.encode()
    p = tmp_path / "config.json"
    p.write_text(json.dumps(asdict(config)))
    assert BleTransportConfig.load(p) == config
    assert replace(config, scheduler="random").fingerprint != config.fingerprint


@pytest.mark.parametrize("mtu", [23, 100, 247, 517])
def test_ble_fragment_roundtrip_out_of_order_duplicate(mtu):
    expected = batch()
    fragments = expected.fragments(mtu)
    assert all(len(f) <= mtu - 3 for f in fragments)
    decoder = BleReassembler()
    assert decoder.feed(fragments[-1], 0) is None if len(fragments) > 1 else True
    result = None
    for fragment in reversed(fragments):
        value = decoder.feed(fragment, 0.1)
        result = value or result
    assert result == expected
    ack = expected.acknowledgement()
    assert len(ack) == 28
    assert zlib.crc32(ack[:-4]) == struct.unpack("!I", ack[-4:])[0]


def test_ble_crc_bounds_conflicts_and_expiration():
    expected = batch()
    raw = bytearray(expected.encode())
    raw[-1] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        BleBatch.decode(bytes(raw))
    decoder = BleReassembler(capacity=1)
    first = expected.fragments(23)[0]
    assert decoder.feed(first, 0) is None
    with pytest.raises(ValueError, match="capacity"):
        decoder.feed(batch(identity=1).fragments(23)[0], 0.1)
    assert decoder.feed(batch(identity=1).fragments(23)[0], 0.31) is None
    assert decoder.expired == 1
    conflict = bytearray(batch(identity=1).fragments(23)[0])
    conflict[-1] ^= 1
    with pytest.raises(ValueError, match="conflicting"):
        decoder.feed(bytes(conflict), 0.32)
    with pytest.raises(ValueError, match="bounds"):
        decoder.feed(FRAGMENT.pack(b"CBLF", 0, 9999, 100) + b"x", 1)


def test_reassembly_replaces_abandoned_batches_without_starving_new_data():
    decoder = BleReassembler(capacity=2, replace_oldest=True)
    assert decoder.feed(batch(identity=0xFFFFFFFE).fragments(23)[0], 0) is None
    assert decoder.feed(batch(identity=0xFFFFFFFF).fragments(23)[0], 0.01) is None
    newest = batch(identity=0)
    parts = newest.fragments(23)
    assert decoder.feed(parts[0], 0.02) is None
    assert decoder.evicted == 1 and len(decoder.partials) == 2
    # A late old fragment cannot displace either newer partial.
    assert decoder.feed(batch(identity=0xFFFFFFFE).fragments(23)[1], 0.03) is None
    assert decoder.stale_fragments == 1
    complete = None
    for part in parts[1:]:
        complete = decoder.feed(part, 0.04) or complete
    assert complete == newest and decoder.evicted == 1


def test_journal_acceptance_dedup_and_truncation(tmp_path):
    journal = BleJournal(tmp_path, 123, {})
    item = batch()
    assert journal.accept(item, 100)
    assert not journal.accept(item, 101)
    with pytest.raises(ValueError, match="reused"):
        journal.accept(batch(sequence=1), 102)
    journal.close()
    path = journal.root / "envelopes.bin"
    assert list(iter_envelopes(path)) == [(100, item)]
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(ValueError, match="truncated"):
        list(iter_envelopes(path))


def test_availability_deadlines_all_silent_and_late_samples():
    rows = []
    grid = AvailabilityGrid(("r1", "r2"), 0, emit=rows.append)
    grid.observe("r1", 10_000_000, 120_000_000)  # exact first-bin deadline
    assert not grid.advance(119_999_999)
    first = grid.advance(120_000_000)[0]
    assert first["receivers"]["r1"]["available"]
    assert not first["receivers"]["r2"]["available"]
    grid.observe(
        "r2", 5_000_000, 130_000_000
    )  # late original bin, may update later age
    second = grid.advance(140_000_000)[0]
    assert not second["receivers"]["r2"]["available"]
    assert second["receivers"]["r2"]["age_ms"] == 35
    assert not first["receivers"]["r2"]["available"]
    assert grid.late["r2"] == 1


def test_round_receipts_detect_all_stream_silence_without_sequence_successor():
    emitted = []
    grid = AvailabilityGrid(("r1", "r2"), 0)
    receipts = RoundReceipts(
        grid.receivers, grid, lambda kind, **v: emitted.append((kind, v))
    )
    receipts.round(dict(transmitter_boot_id=11, sequence=0, host_capture_ns=10_000_000))
    receipts.advance(120_000_000)
    assert emitted[0][1]["availability"] == {"r1": False, "r2": False}
    receipts.receive(11, 0, "r1", 130_000_000)
    assert emitted[0][1]["availability"]["r1"] is False


@pytest.fixture
def c_contract(tmp_path):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("host C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "ble_contract.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "ble_grants.h"
#include "ble_queue.h"
#include "ble_delivery_policy.h"
int main(int argc, char **argv) {
    uint8_t raw[64]; assert(argc == 2 || argc == 3);
    for (unsigned i=0;i<64;i++) { unsigned x; assert(sscanf(argv[1]+2*i,"%2x",&x)==1);raw[i]=x; }
    csi_ble_config_t c; assert(csi_ble_config_decode(raw,64,&c));
    for (unsigned i=0;i<100;i++) printf("%u",csi_ble_owner(i,4,1,23));
    puts("");
    csi_sensing_packet_t sensing={.sequence=0xffffffffU,.tx_t1_us=1000};
    memcpy(sensing.profile_fingerprint,"0123456789abcdef",16);
    uint8_t packet[88]; assert(csi_ble_sensing_encode(packet,88,&sensing,&c,11,900)==88);
    csi_sensing_packet_t decoded; assert(csi_sensing_decode(packet,88,&decoded));
    assert(decoded.version==3 && decoded.sequence==0xffffffffU);
    packet[8] ^= 1; assert(!csi_sensing_decode(packet,88,&decoded)); packet[8] ^= 1;
    for(unsigned i=0;i<88;i++) printf("%02x",packet[i]); puts("");
    ble_grants_t g={0}; uint8_t owners[]={0,1,2};
    assert(ble_grants_observe(&g,&c,0,1000,1000,2000,owners));
    assert(!ble_grants_available(&g,&c,0,2999));
    assert(ble_grants_available(&g,&c,0,3000));
    g.remaining=0;
    assert(!ble_grants_available(&g,&c,0,4000));
    assert(!ble_grants_observe(&g,&c,0,1000,1000,2100,owners));
    assert(!ble_grants_available(&g,&c,0,50000));
    assert(ble_grants_observe(&g,&c,1,13500,13500,14500,(uint8_t[]){1,2,3}));
    assert(ble_grants_available(&g,&c,1,15500));
    assert(!ble_grants_available(&g,&c,1,26000));
    ble_record_queue_t q={0}; ble_queue_reset(&q,2);
    uint8_t value[]={1,2}; assert(ble_queue_push(&q,value,2,1));
    ble_record_slot_t *s=ble_queue_oldest(&q);s->state=2;s->batch=9;
    assert(ble_queue_push(&q,value,2,2));assert(ble_queue_push(&q,value,2,3));
    assert(q.evicted==1 && s->state==2);
    assert(ble_queue_release(&q,8,true)==0);
    assert(ble_queue_release(&q,9,true)==1);
    ble_queue_expire(&q,100,10);
    assert(q.captured==q.acknowledged+q.evicted+q.expired+q.rejected+q.epoch_dropped+ble_queue_count(&q));
    ble_queue_reset(&q,2);assert(ble_queue_push(&q,value,2,100));
    ble_queue_reset(&q,2);assert(q.epoch_dropped==1);
    assert(ble_delivery_action(20000,1,10000,true,0,&c)==BLE_DELIVERY_WAIT);
    assert(ble_delivery_action(60000,1,10000,true,0,&c)==BLE_DELIVERY_RETRY);
    assert(ble_delivery_action(60000,1,10000,true,1,&c)==BLE_DELIVERY_DROP);
    assert(ble_delivery_action(250001,1,10000,false,0,&c)==BLE_DELIVERY_DROP);
    if(argc==3) {
        uint8_t envelope[1436];size_t n=strlen(argv[2])/2;
        assert(n<=1400);
        for(size_t i=0;i<n;i++) {unsigned x;assert(sscanf(argv[2]+2*i,"%2x",&x)==1);envelope[32+i]=x;}
        n=csi_ble_envelope_finish(envelope,sizeof(envelope),n,123,11,21,0);
        for(size_t i=0;i<n;i++) printf("%02x",envelope[i]);puts("");
    }
    return 0;
}""")
    binary = tmp_path / "ble_contract"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-I",
            str(root / "src/firmware/radio/common/include"),
            "-I",
            str(root / "src/firmware/radio/receiver/main"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
    )
    return binary


def test_c_python_config_sensing_scheduler_and_queue_contract(c_contract):
    config = BleTransportConfig()
    result = subprocess.run(
        [str(c_contract), config.encode(123, 4, 80).hex()],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert result[0] == "".join(
        str(grant_owner(i, 4, "random", 23)) for i in range(100)
    )
    packet = bytes.fromhex(result[1])
    assert len(packet) == 88 and packet[4] == 3
    assert struct.unpack_from("!Q", packet, 40)[0] == 123
    assert struct.unpack_from("!I", packet, 48)[0] == 11
    assert packet[52:68] == config.fingerprint.encode()
    assert packet[80:83] == bytes([3, 0, 1])
    assert zlib.crc32(packet[:84]) == struct.unpack("!I", packet[84:])[0]


class FakeModel:
    def __init__(self, inv, prof):
        self.inventory, self.profile = inv, prof
        self.configs, self.clients = {}, {}
        self.running = False
        self.sequence = 0
        self.task = None
        self.reference = None
        self.acks = []
        self.lose_ack = None

    def status(self, mac):
        config = self.configs.get(mac)
        index = next(i for i, d in enumerate(self.inventory.receivers) if d.mac == mac)
        return dict(
            protocol_version=1,
            sensing_version=3,
            role="receiver",
            target=self.inventory.receivers[index].target,
            mac=mac,
            boot_id=21 + index,
            run_id=str(struct.unpack_from("!Q", config, 8)[0]) if config else "0",
            profile_fingerprint=profile_fingerprint(self.profile, self.inventory),
            inventory_crc=inventory_crc(tuple(d.mac for d in self.inventory.receivers)),
            transport_fingerprint=config[36:52].decode() if config else "",
            ready=config is not None,
            mtu=247,
            tx_phy=2,
            queued=0,
            oldest_age_us=0,
            expired=0,
        )

    async def discover(self, **kwargs):
        self.task = asyncio.create_task(self.tick())
        return list(reversed(self.inventory.receivers))

    async def tick(self):
        while True:
            await asyncio.sleep(0.015)
            if not self.running:
                continue
            seq = self.sequence
            self.sequence += 1
            captured = time.monotonic_ns() // 1000
            self.reference.last_round_time = time.monotonic()
            self.reference.event_sink(
                "round",
                run_id=123,
                transmitter_boot_id=11,
                sequence=seq,
                host_capture_ns=captured * 1000,
                tx_enqueue_us=captured,
                skipped_rounds=0,
                owners=[seq % 4, (seq + 1) % 4, (seq + 2) % 4],
                period_us=12500,
                send_mask=15,
                log_drops=0,
            )
            for index, d in enumerate(self.inventory.receivers):
                client = self.clients.get(d.mac)
                if client and client.is_connected and client.notify:
                    value = batch(
                        identity=seq,
                        sequence=seq,
                        rx=21 + index,
                        mac=d.mac,
                        fingerprint=profile_fingerprint(self.profile, self.inventory),
                        captured=captured,
                        channel=self.profile.channel,
                    )
                    for fragment in value.fragments():
                        client.notify(None, fragment)
                    if (
                        seq == 0
                    ):  # A complete duplicate batch must not duplicate recorded CSI.
                        for fragment in value.fragments():
                            client.notify(None, fragment)

    def client(self, device):
        model = self

        class Client:
            def __init__(self):
                self.is_connected = False
                self.notify = None

            async def __aenter__(self):
                self.is_connected = True
                model.clients[device.mac] = self
                return self

            async def __aexit__(self, *args):
                self.is_connected = False
                self.notify = None

            async def read_gatt_char(self, uuid):
                if not self.is_connected:
                    raise ConnectionError("simulated disconnect")
                status = model.status(device.mac)
                if uuid == STATS_UUID:
                    return struct.pack(
                        "!4sBBH" + "Q" * len(STATUS_FIELDS),
                        b"CBSS",
                        1,
                        len(STATUS_FIELDS),
                        224,
                        *(status.get(k, 0) for k in STATUS_FIELDS),
                    )
                return json.dumps(status).encode()

            async def start_notify(self, uuid, callback):
                self.notify = callback

            async def write_gatt_char(self, uuid, payload, response):
                if not self.is_connected:
                    raise ConnectionError("simulated disconnect")
                if payload[:4] == b"CBLC":
                    model.configs[device.mac] = payload
                elif payload[:4] == b"CBAK":
                    if model.lose_ack == device.mac:
                        model.lose_ack = None
                        self.is_connected = False
                        raise ConnectionError("simulated lost ACK")
                    model.acks.append((device.mac, bytes(payload)))

        return Client()

    def reference_factory(self, port, mac, event_sink, **kwargs):
        model = self

        class Reference:
            def __init__(self):
                self.ready = True
                self.run_id = None
                self.transmitter_boot_id = 11
                self.last_round_time = None
                self.estimator = SimpleNamespace(
                    estimate=SimpleNamespace(uncertainty_us=1)
                )
                self.event_sink = event_sink

            def start(self):
                pass

            def stop(self):
                self.ready = False

            def sync(self, identity):
                pass

            def capture_time(self, captured):
                return captured * 1000

            def command(self, payload):
                if payload[:4] == b"CBLC":
                    assert struct.unpack_from("!I", payload, 52)[0] == inventory_crc(
                        tuple(d.mac for d in model.inventory.receivers)
                    )
                if payload[:4] == b"CBGO":
                    model.running = True
                if payload[:4] == b"CBST":
                    model.running = False
                return b"ok"

        self.reference = Reference()
        return self.reference


async def wait_until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition did not become true")
        await asyncio.sleep(0.01)


@pytest.mark.parametrize(
    "targets,band",
    [
        (("esp32c5",), "5ghz"),
        (("esp32c6",), "2.4ghz"),
        (("esp32c5", "esp32c6"), "2.4ghz"),
    ],
)
def test_four_mock_clients_record_dedup_reconnect_and_drain(tmp_path, targets, band):
    async def exercise():
        inv, prof = inventory(targets=targets), profile(band=band)
        model = FakeModel(inv, prof)
        recorded = []
        manager = BleReceiverManager(
            inv,
            prof,
            tmp_path,
            transmitter_port="fake",
            run_id=123,
            require_four=True,
            scanner=model,
            client_factory=model.client,
            reference_factory=model.reference_factory,
            record_sink=lambda record, arrival: recorded.append(record),
        )
        manager.bind()
        task = asyncio.create_task(manager._run())
        try:
            await wait_until(lambda: len(recorded) >= 12 or manager.failure)
            assert not manager.failure
            assert manager.all_live and manager.clock_sync_ready
            assert {r.receiver_mac for r in recorded} == {d.mac for d in inv.receivers}
            assert len({(r.receiver_mac, r.sequence) for r in recorded}) == len(
                recorded
            )
            model.lose_ack = inv.receivers[1].mac
            await wait_until(lambda: manager.readers["rx-2"].reconnects > 0)
            before = manager.readers["rx-1"].buffer.received_records
            await wait_until(
                lambda: manager.readers["rx-1"].buffer.received_records > before + 2
            )
            assert manager.clock_sync_ready and not manager.failure
            await wait_until(lambda: manager.all_live)
            assert model.acks
        finally:
            manager._stop.set()
            await asyncio.wait_for(task, 5)
            if model.task:
                model.task.cancel()
                await asyncio.gather(model.task, return_exceptions=True)
        assert list(iter_envelopes(manager.journal.root / "envelopes.bin"))
        assert manager.journal.closed
        bins = [
            json.loads(line)
            for line in (manager.journal.root / "availability.jsonl")
            .read_text()
            .splitlines()
        ]
        assert bins and all(len(row["receivers"]) == 4 for row in bins)

    asyncio.run(exercise())


def test_ble_preflight_requires_real_four_receiver_registry(tmp_path):
    manager = BleReceiverManager(
        inventory(2), profile(), tmp_path, transmitter_port="fake", require_four=True
    )
    with pytest.raises(RuntimeError, match="four"):
        manager.bind()


def test_development_missing_receivers_preserves_provisioned_slots(tmp_path):
    async def exercise():
        inv, prof = inventory(targets=("esp32c6",)), profile(band="2.4ghz")
        model = FakeModel(inv, prof)

        class Scanner:
            async def discover(self, **kwargs):
                await model.discover(**kwargs)
                return [inv.receivers[3]]

        manager = BleReceiverManager(
            inv,
            prof,
            tmp_path,
            transmitter_port="fake",
            run_id=123,
            allow_missing_receivers=True,
            scanner=Scanner(),
            client_factory=model.client,
            reference_factory=model.reference_factory,
        )
        manager.bind()
        task = asyncio.create_task(manager._run())
        try:
            await wait_until(lambda: manager.preflight_ready or manager.failure)
            assert manager.failure is None and not manager.all_live
            assert manager._startup_receiver_ids == ("rx-4",)
            assert model.configs[inv.receivers[3].mac][6] == 4
            assert len(manager.readers) == 4
            assert all(
                manager.readers[f"rx-{i}"].buffer.received_records == 0
                for i in (1, 2, 3)
            )
        finally:
            manager._stop.set()
            await asyncio.wait_for(task, 5)
            if model.task:
                model.task.cancel()
                await asyncio.gather(model.task, return_exceptions=True)

    asyncio.run(exercise())


def test_collection_cannot_skip_missing_startup_receivers(tmp_path):
    with pytest.raises(ValueError, match="collection cannot"):
        BleReceiverManager(
            inventory(),
            profile(),
            tmp_path,
            transmitter_port="fake",
            require_four=True,
            allow_missing_receivers=True,
        )


def test_benchmark_failure_survives_clean_transport_shutdown(tmp_path):
    from fall_detection.radio.experiments.ble import summarize

    journal = BleJournal(
        tmp_path,
        123,
        dict(
            transport_config=asdict(BleTransportConfig()),
            radio_profile=profile().as_dict(),
            inventory=inventory(1).as_dict(),
            hardware_backend=True,
        ),
    )
    journal.event("benchmark_failed", error="hardware preflight timed out")
    journal.event("run_finished", failure=None)
    journal.close()
    result = summarize(journal.root)
    assert result["failure"] == "hardware preflight timed out"
    assert not result["measured_hardware"]


def test_quality_inspection_checks_authoritative_metadata_without_inventing_layouts(
    tmp_path,
):
    from fall_detection.radio.experiments.ble_quality import analyze_ble_quality

    journal = BleJournal(tmp_path, 123, {})
    item = batch()
    journal.accept(item, 1100)
    journal.event("measurement_started", at_ns=100)
    journal.event("round", transmitter_boot_id=11, sequence=0, tx_enqueue_us=1000)
    journal.event(
        "record",
        transmitter_boot_id=11,
        receiver_boot_id=21,
        receiver_mac="02:00:00:00:00:01",
        sequence=0,
        tx_enqueue_us=1000,
        capture_host_ns=1000,
        clock_uncertainty_us=1,
    )
    journal.event("measurement_finished", at_ns=2000)
    journal.close()
    report = analyze_ble_quality(journal.root)
    assert report["envelopes_crc_verified"] == 1
    assert report["measurement_unique_records"] == 1
    assert report["measurement_metadata_round_mismatches"] == 0
    assert report["measurement_records_missing_from_raw_journal"] == 0
    assert report["unsupported_layout_records"] == 1
    assert report["usable_phase_fraction_of_eligible"] is None


@pytest.mark.parametrize("targets", [("esp32c6",), ("esp32c5", "esp32c6")])
def test_ble_c6_rejects_5ghz_profile(tmp_path, targets):
    with pytest.raises(RadioProfileError, match="5ghz profiles require ESP32-C5"):
        BleReceiverManager(
            inventory(targets=targets), profile(), tmp_path, transmitter_port="fake"
        )


def test_ble_c6_rejects_wrong_gatt_target(tmp_path):
    inv, prof = inventory(1, targets=("esp32c6",)), profile(band="2.4ghz")
    manager = BleReceiverManager(inv, prof, tmp_path, transmitter_port="fake")
    manager.bind()
    status = FakeModel(inv, prof).status(inv.receivers[0].mac)
    manager._verify_identity(manager.readers["rx-1"], status)
    status["target"] = "esp32c5"
    with pytest.raises(ValueError, match="mismatch"):
        manager._verify_identity(manager.readers["rx-1"], status)


def test_host_notification_backpressure_is_bounded(tmp_path):
    async def exercise():
        manager = BleReceiverManager(
            inventory(1), profile(), tmp_path, transmitter_port="fake"
        )
        manager.bind()
        state = manager.readers["rx-1"]
        state.notifications = asyncio.Queue(maxsize=2)
        for _ in range(5):
            manager._notification(state, b"packet")
        assert state.notifications.qsize() == 2 and state.notification_drops == 3

    asyncio.run(exercise())


def test_benchmark_matrix_keeps_round_robin_primary_and_random_opt_in(tmp_path):
    from fall_detection.radio.experiments.ble import prepare_matrix

    inv = tmp_path / "inventory.json"
    radio = tmp_path / "profile.json"
    inv.write_text(json.dumps(inventory().as_dict()))
    radio.write_text(json.dumps(profile().as_dict()))
    output = tmp_path / "matrix"
    conditions = prepare_matrix(output, inv, radio, BleTransportConfig(), "fake")
    assert len(conditions) == 20
    assert conditions[0]["scheduler"] == "round_robin"
    assert {c["rate_hz"] for c in conditions} == {50, 60, 70, 80, 100}
    assert sum(c["scheduler"] == "random" for c in conditions) == 15
    for c in conditions:
        assert "--port fake" in c["run_command"]
    with pytest.raises(FileExistsError):
        prepare_matrix(output, inv, radio, BleTransportConfig(), "fake")


def test_benchmark_report_uses_processing_availability_and_explicit_spans(tmp_path):
    from fall_detection.radio.experiments.ble import summarize

    inv = inventory(1)
    config = BleTransportConfig()
    journal = BleJournal(
        tmp_path,
        123,
        dict(
            transport_config=asdict(config),
            radio_profile=profile().as_dict(),
            inventory=inv.as_dict(),
        ),
    )
    journal.event("sensing_started", start_ns=1_000_000_000)
    journal.event("measurement_started", at_ns=1_000_000_000)
    journal.event(
        "record",
        receiver_mac=inv.receivers[0].mac,
        capture_host_ns=1_010_000_000,
        arrival_ns=1_020_000_000,
        available_ns=1_130_000_000,
    )
    journal.event(
        "round_availability",
        host_capture_ns=1_010_000_000,
        period_us=12500,
        availability={"rx-1": False},
    )
    journal.event("measurement_finished", at_ns=2_000_000_000)
    journal.event("run_finished", failure=None)
    journal.close()
    report = summarize(journal.root)
    assert report["receivers"]["rx-1"]["timely_rate_hz"] == 0
    assert report["receivers"]["rx-1"]["delivered_rate_hz"] == 1
    assert report["receivers"]["rx-1"]["delay_ms"]["50"] == 120
    assert report["joint_availability"] == {"0": 1}


def test_invalid_identity_and_storage_failure_do_not_ack(tmp_path):
    async def exercise():
        manager = BleReceiverManager(
            inventory(1), profile(), tmp_path, transmitter_port="fake", run_id=123
        )
        manager.bind()
        state = manager.readers["rx-1"]
        bad_status = dict(
            protocol_version=1,
            sensing_version=3,
            role="receiver",
            target="esp32c5",
            mac="02:00:00:00:00:ff",
            profile_fingerprint=manager.expected_fingerprint,
        )
        with pytest.raises(ValueError, match="mismatch"):
            manager._verify_identity(state, bad_status)
        manager.reference = SimpleNamespace(
            transmitter_boot_id=11, capture_time=lambda t: t * 1000
        )
        state.status = {"boot_id": 21}
        state.notifications = asyncio.Queue(maxsize=128)

        class FailingJournal:
            def accept(self, *args):
                raise OSError("disk full")

        manager.journal = FailingJournal()
        item = batch(fingerprint=manager.expected_fingerprint)
        for part in item.fragments():
            manager._notification(state, part)
        acks = []

        class Client:
            async def write_gatt_char(self, *args, **kwargs):
                acks.append(args)

        with pytest.raises(BleIngestionError, match="disk full"):
            await manager._consume(state, Client())
        assert not acks

    asyncio.run(exercise())


def test_c_python_envelope_crc_contract(c_contract):
    config = BleTransportConfig()
    expected = batch()
    result = subprocess.run(
        [str(c_contract), config.encode(123, 4, 80).hex(), expected.payload.hex()],
        check=True,
        capture_output=True,
        text=True,
    )
    assert bytes.fromhex(result.stdout.splitlines()[-1]) == expected.encode()


def test_inventory_order_is_bound_to_firmware_configuration():
    config = BleTransportConfig()
    macs = tuple(d.mac for d in inventory().receivers)
    first = config.encode(123, 4, 80, receiver_macs=macs)
    swapped = config.encode(123, 4, 80, receiver_macs=tuple(reversed(macs)))
    assert first[52:56] != swapped[52:56]
    assert struct.unpack_from("!I", first, 52)[0] == inventory_crc(macs)


def test_status_vector_is_bounded_and_rejects_wrong_schema():
    from fall_detection.radio.acquisition.ble_protocol import decode_status

    identity = json.dumps(dict(protocol_version=1, mac="02:00:00:00:00:01")).encode()
    raw = struct.pack("!4sBBH" + "Q" * 27, b"CBSS", 1, 27, 224, *range(27))
    decoded = decode_status(identity, raw)
    assert len(raw) == 224 and decoded["minimum_free_heap"] == 26
    with pytest.raises(ValueError):
        decode_status(identity, raw[:-1])
    with pytest.raises(ValueError):
        decode_status(identity, raw[:4] + b"\x02" + raw[5:])


def test_experimental_interval_mismatch_stops_before_sensing(tmp_path):
    from fall_detection.radio.ble_config import BleTimingExperiment

    class LockedIntervalModel(FakeModel):
        def status(self, mac):
            return dict(super().status(mac), interval_units=6)

    async def exercise():
        inv, prof = inventory(1), profile()
        model = LockedIntervalModel(inv, prof)
        manager = BleReceiverManager(
            inv,
            prof,
            tmp_path,
            transmitter_port="fake",
            run_id=123,
            config=BleTransportConfig(
                experiment=BleTimingExperiment(connection_interval_units=10)
            ),
            require_four=False,
            allow_missing_receivers=True,
            scanner=model,
            client_factory=model.client,
            reference_factory=model.reference_factory,
        )
        manager.bind()
        try:
            await asyncio.wait_for(manager._run(), 6)
            assert "experimental interval not negotiated" in manager.failure
            assert not model.running
            assert not list(iter_envelopes(manager.journal.root / "envelopes.bin"))
            assert manager.journal.closed
        finally:
            if model.task:
                model.task.cancel()
                await asyncio.gather(model.task, return_exceptions=True)

    asyncio.run(exercise())


def test_progress_receipts_repeat_while_recorder_waits_and_stale_callbacks_are_ignored(
    tmp_path,
):
    from threading import Event
    from fall_detection.radio.ble_config import (
        BleDeliveryExperiment,
        BleTimingExperiment,
        flow_token,
    )
    from fall_detection.radio.acquisition.ble_protocol import FLOW_FRAGMENT

    async def exercise():
        inv, prof = inventory(1), profile()
        manager = BleReceiverManager(
            inv,
            prof,
            tmp_path,
            transmitter_port="fake",
            run_id=123,
            config=BleTransportConfig(
                experiment=BleTimingExperiment(delivery=BleDeliveryExperiment())
            ),
            require_four=False,
            allow_missing_receivers=True,
        )
        manager.bind()
        manager.reference = SimpleNamespace(
            transmitter_boot_id=11,
            capture_time=lambda t: t * 1000,
            estimator=SimpleNamespace(estimate=SimpleNamespace(uncertainty_us=1)),
        )
        manager.journal = BleJournal(tmp_path / "journal", 123, {})
        state = manager.readers["rx-1"]
        state.status = {"boot_id": 21}
        state.notifications = asyncio.Queue(maxsize=128)
        state.flow_event = asyncio.Event()
        generation = object()
        state.notification_generation = generation
        gate = Event()
        original_accept = manager._accept

        def held_accept(*args):
            assert gate.wait(2)
            original_accept(*args)

        manager._accept = held_accept
        writes = []

        class Client:
            async def write_gatt_char(self, uuid, payload, response):
                writes.append(bytes(payload))

        client = Client()
        consumer = asyncio.create_task(manager._consume(state, client))
        progress = asyncio.create_task(manager._progress(state, client))
        item = batch(fingerprint=manager.expected_fingerprint)
        try:
            for serial, part in enumerate(item.fragments(), 1):
                _, identity, offset, total = FRAGMENT.unpack_from(part)
                packet = (
                    FLOW_FRAGMENT.pack(
                        b"CBL2", flow_token(123), serial, identity, offset, total
                    )
                    + part[FRAGMENT.size :]
                )
                manager._notification(state, packet, object())
                assert state.notifications.empty()
                manager._notification(state, packet, generation)
            await wait_until(
                lambda: len([p for p in writes if p[:4] == b"CBPR"]) >= 2, timeout=1
            )
            receipts = [p for p in writes if p[:4] == b"CBPR"]
            assert receipts[0] == receipts[1]
            assert not any(p[:4] == b"CBAK" for p in writes)
            assert not list(iter_envelopes(manager.journal.root / "envelopes.bin"))
            gate.set()
            await wait_until(lambda: any(p[:4] == b"CBAK" for p in writes), timeout=1)
            assert (
                len(list(iter_envelopes(manager.journal.root / "envelopes.bin"))) == 1
            )
        finally:
            gate.set()
            consumer.cancel()
            progress.cancel()
            await asyncio.gather(consumer, progress, return_exceptions=True)
            if manager._accept_tasks:
                await asyncio.gather(*manager._accept_tasks, return_exceptions=True)
            manager.journal.close()

    asyncio.run(exercise())
