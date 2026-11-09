"""Offline contracts for the dual-band transport; no hardware/network access."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import struct
import subprocess
import time
from types import SimpleNamespace
import zlib

import pytest

from fall_detection.radio.espnow_config import EspnowTransportConfig
from fall_detection.radio.profile import (
    RadioInventory,
    RadioProfile,
    profile_fingerprint,
)
from fall_detection.radio.acquisition.gateway_protocol import GatewayBatch
from fall_detection.radio.acquisition.gateway_journal import (
    GatewayJournal,
    iter_envelopes,
)
from fall_detection.radio.acquisition.gateway_reader import GatewayReceiverManager
from fall_detection.radio.acquisition.protocol import CsiRecord
from fall_detection.radio.acquisition.wire import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)
from fall_detection.radio.acquisition.availability import (
    AvailabilityGrid,
    RoundReceipts,
)


def inventory():
    def device(i, role, target="esp32c5"):
        return dict(
            id=f"{role}-{i}", role=role, target=target, mac=f"02:00:00:00:00:{i:02x}"
        )

    return RadioInventory.from_mapping(
        dict(
            schema_version=2,
            transmitter=device(0, "transmitter"),
            receivers=[device(i, "receiver") for i in range(1, 5)],
            gateway=device(5, "gateway", "esp32c6"),
        )
    )


def profile():
    return RadioProfile.from_mapping(
        dict(
            schema_version=1,
            profile_id="test",
            country_code="ID",
            band="5ghz",
            channel=44,
            bandwidth_mhz=20,
            nominal_rate_hz=80,
        )
    )


def batch(inv=None, seq=1, receiver=0, payload=None):
    inv = inv or inventory()
    mac = inv.receivers[receiver].mac
    r = CsiRecord(
        seq,
        inv.transmitter.mac,
        -40,
        -95,
        100,
        (complex(20, 30),) * 245,
        receiver_mac=mac,
        tx_timestamp_us=1000 + seq,
        rx_callback_timestamp_us=1010 + seq,
        csi_length=490,
        sig_mode=4,
        channel=44,
        profile_fingerprint=profile_fingerprint(profile(), inv),
    )
    p = payload or encode_csi_batch(
        (DecodedCsiDatagram(r, mac, seq),),
        boot_id=21,
        batch_sequence=seq,
        receiver_stats=ReceiverStats(*([0] * 10)),
    )
    return GatewayBatch(123, 11, 21, seq, mac, p)


def test_config_inventory_order_and_identity_fingerprint():
    inv, p, c = inventory(), profile(), EspnowTransportConfig()
    c.validate(inv, p)
    raw = c.encode(123, inv, p)
    assert len(raw) == 108 and raw[:4] == b"CGCF" and raw[5:8] == bytes([4, 44, 6])
    assert struct.unpack_from("!I", raw, 104)[0] == zlib.crc32(raw[:104])
    assert raw[84:100] == c.fingerprint(inv, p).encode()
    assert c.fingerprint(
        replace(inv, receivers=tuple(reversed(inv.receivers))), p
    ) != c.fingerprint(inv, p)
    assert RadioInventory.from_mapping(inv.as_dict()) == inv
    old = inv.as_dict()
    old["schema_version"] = 1
    old.pop("gateway")
    assert RadioInventory.from_mapping(old).gateway is None
    with pytest.raises(ValueError):
        c.validate(RadioInventory.from_mapping(old), p)
    with pytest.raises(ValueError):
        c.validate(
            replace(inv, transmitter=replace(inv.transmitter, target="esp32c6")), p
        )


@pytest.mark.parametrize("wireless", [False, True])
def test_gateway_ingestion_decodes_nested_payload_once(tmp_path, monkeypatch, wireless):
    """Full validation and recording must not reparse the same CSI payload."""
    from fall_detection.radio.acquisition import gateway_protocol, packet_reader, wire

    calls = []
    original = wire.decode_csi_packet

    def decode(payload):
        calls.append(payload)
        return original(payload)

    monkeypatch.setattr(wire, "decode_csi_packet", decode)
    monkeypatch.setattr(gateway_protocol, "decode_csi_packet", decode)
    monkeypatch.setattr(packet_reader, "decode_csi_packet", decode)
    seen = []
    m = manager(tmp_path, lambda record, arrival: seen.append(record))
    try:
        arrival = time.monotonic_ns()
        payload = batch().encode()
        if wireless:
            # The wireless USB reader decodes before waiting for boot evidence.
            m._reference_pending.append(
                (arrival, payload, GatewayBatch.decode(payload))
            )
            m._flush_reference_pending()
        else:
            assert m.accept(payload, arrival)
        assert len(seen) == 1
        assert len(calls) == 1
        assert seen[0].transmitter_boot_id == 11
        assert seen[0].receiver_boot_id == 21
        assert seen[0].capture_host_monotonic_ns is not None
    finally:
        m.journal.close()


def test_gateway_replaced_payload_cannot_reuse_validated_identity():
    decoded = GatewayBatch.decode(batch().encode())
    _ = decoded.decoded_packet
    changed = replace(decoded, payload=batch(receiver=1).payload)
    with pytest.raises(ValueError, match="identities disagree"):
        _ = changed.decoded_packet


def test_preview_deferral_does_not_change_acquisition_readiness(tmp_path):
    m = manager(tmp_path, lambda *args: None)
    try:
        m.reference.usb_backlog_chunks = 17
        assert m.clock_sync_ready and not m.preview_ready
        m.reference.usb_backlog_chunks = 0
        assert m.clock_sync_ready and m.preview_ready
        assert m.failure is None
    finally:
        m.journal.close()


def test_eight_batch_policy_and_legacy_config_are_distinct(tmp_path):
    current = EspnowTransportConfig(
        schema_version=2, outstanding_batches=8, early_return_idle_ms=5
    )
    raw = current.encode(123, inventory(), profile())
    assert raw[4] == 2 and raw[29] == 8
    assert struct.unpack_from("!H", raw, 100)[0] == 5
    assert current.fingerprint(inventory(), profile()) != replace(
        current, early_return_idle_ms=0
    ).fingerprint(inventory(), profile())
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(dict(schema_version=1, outstanding_batches=4)))
    legacy = EspnowTransportConfig.load(legacy_path)
    assert legacy.early_return_idle_ms == 0
    assert legacy.encode(123, inventory(), profile())[4] == 1
    from dataclasses import asdict
    import hashlib

    original_policy = asdict(legacy)
    original_policy.pop("early_return_idle_ms")
    original_policy.pop("application_acknowledgements")
    for key in (
        "minimum_revisit_ms",
        "send_completion_guard_ms",
        "batch_acknowledgements",
        "measure_send_completions",
    ):
        original_policy.pop(key)
    historical = dict(
        policy=original_policy,
        inventory=inventory().as_dict(),
        profile=profile().as_dict(),
    )
    expected = hashlib.sha256(
        json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    assert legacy.fingerprint(inventory(), profile()) == expected
    with pytest.raises(ValueError):
        replace(legacy, outstanding_batches=8)
    with pytest.raises(ValueError):
        replace(current, outstanding_batches=9)
    with pytest.raises(ValueError):
        replace(current, early_return_idle_ms=21)


@pytest.mark.parametrize(
    "changes",
    [
        {"slot_ms": 10},
        {"return_reserve_ms": 50},
        {"queue_capacity": 65},
        {"maximum_retries": 2},
        {"phy": "default"},
        {"channel": 14},
        {"ack_timeout_ms": 501},
    ],
)
def test_config_rejects_unsafe_policies(changes):
    with pytest.raises(ValueError):
        EspnowTransportConfig(**changes)


def test_envelope_roundtrip_crc_identity_and_size():
    b = batch()
    raw = b.encode()
    assert len(raw) <= 1400 and GatewayBatch.decode(raw) == b
    damaged = bytearray(raw)
    damaged[-6] ^= 1
    with pytest.raises(ValueError):
        GatewayBatch.decode(damaged)
    damaged = bytearray(raw)
    damaged[28] ^= 1
    struct.pack_into("!I", damaged, len(damaged) - 4, zlib.crc32(damaged[:-4]))
    with pytest.raises(ValueError):
        GatewayBatch.decode(damaged)
    with pytest.raises(ValueError):
        replace(b, payload=b"x" * 1400).encode()
    assert len(b.acknowledgement()) == 34


def test_journal_duplicate_keys_include_receiver_and_conflicts(tmp_path):
    journal = GatewayJournal(tmp_path, 123, {})
    assert journal.accept(batch(), 1)
    assert not journal.accept(batch(), 2)
    assert journal.accept(batch(receiver=1), 3)
    with pytest.raises(ValueError):
        journal.accept(replace(batch(), payload=batch(seq=2).payload), 4)
    journal.close()
    rows = list(iter_envelopes(journal.root / "envelopes.bin"))
    assert len(rows) == 2


class Reference:
    ready = True
    transmitter_boot_id = 11
    estimator = SimpleNamespace(estimate=SimpleNamespace(uncertainty_us=10))

    def capture_time(self, value):
        return time.monotonic_ns() - 1000000


class Connection:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)


def manager(tmp_path, sink=None):
    m = GatewayReceiverManager(
        inventory(),
        profile(),
        tmp_path,
        transmitter_port="tx",
        gateway_port="gw",
        require_four=True,
        run_id=123,
        record_sink=sink,
    )
    m.bind()
    m.reference = Reference()
    m.connection = Connection()
    m.journal = GatewayJournal(tmp_path, 123, {})
    m.grid = AvailabilityGrid(tuple(m.readers), time.monotonic_ns() - 10000000)
    m.receipts = RoundReceipts(tuple(m.readers), m.grid, m.journal.event)
    for s in m.readers.values():
        s.status = {"boot_id": 21}
    return m


def test_acceptance_ack_dedup_and_independent_receivers(tmp_path):
    records = []
    m = manager(tmp_path, lambda r, t: records.append(r))
    assert m.accept(batch().encode(), time.monotonic_ns())
    assert m.accept(batch().encode(), time.monotonic_ns())
    assert m.accept(batch(receiver=1).encode(), time.monotonic_ns())
    assert len(records) == 2 and len(m.connection.writes) == 3
    assert all(r.transport == "espnow_gateway" for r in records)
    assert records[0].receiver_mac != records[1].receiver_mac
    assert not m.accept(replace(batch(), run_id=124).encode(), time.monotonic_ns())
    assert len(m.connection.writes) == 3
    m.journal.close()


def test_recorder_failure_never_acknowledges(tmp_path):
    def fail(*args):
        raise OSError("disk full")

    m = manager(tmp_path, fail)
    with pytest.raises(OSError, match="disk full"):
        m.accept(batch().encode(), time.monotonic_ns())
    assert not m.connection.writes
    m.journal.close()


def test_queue_events_validate_crc_and_preserve_batch_cause(tmp_path):
    m = manager(tmp_path, lambda *args: None)
    event = bytearray(48)
    event[:8] = b"CGQE\x01\x00\x03\x02"
    struct.pack_into("!QIIIIQHBB", event, 8, 123, 11, 21, 17, 9, 12345, 8, 2, 0)
    struct.pack_into("!I", event, 44, zlib.crc32(event[:44]))
    m._event("radio_event", payload_hex=event.hex())
    event[-1] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        m._event("radio_event", payload_hex=event.hex())
    m.journal.close()
    rows = [
        json.loads(line)
        for line in (m.journal.root / "events.jsonl").read_text().splitlines()
    ]
    parsed = [e for e in rows if e["kind"] == "queue_event"]
    assert len(parsed) == 1
    assert (parsed[0]["event_code"], parsed[0]["batch_id"], parsed[0]["attempts"]) == (
        3,
        17,
        2,
    )


def test_mac_metrics_are_journaled_without_application_ack(tmp_path):
    m = manager(tmp_path, lambda *args: None)
    payload = bytearray(64)
    payload[:8] = b"CGMT\x01\x00\x01\x00"
    struct.pack_into(
        "!QIIIHHIIQII", payload, 8, 123, 11, 21, 9, 5, 1, 800, 4000, 9000, 4000, 1
    )
    struct.pack_into("!I", payload, 60, zlib.crc32(payload[:60]))
    m._event("radio_event", payload_hex=payload.hex())
    payload[-1] ^= 1
    with pytest.raises(ValueError):
        m._event("radio_event", payload_hex=payload.hex())
    assert not m.connection.writes
    m.journal.close()
    rows = [
        json.loads(line)
        for line in (m.journal.root / "events.jsonl").read_text().splitlines()
    ]
    metric = next(e for e in rows if e["kind"] == "mac_completion_summary")
    assert (
        metric["samples"] == 5
        and metric["failures"] == 1
        and metric["maximum_us"] == 4000
    )
    assert metric["sender_busy_at_return"] and metric["completions_after_cutoff"] == 1


def test_new_reference_baselines_prior_run_drops_but_rejects_current_loss():
    from fall_detection.radio.acquisition.transmitter_reference import (
        TransmitterReference,
        ROUND,
    )

    events = []
    reference = TransmitterReference(
        "fake",
        inventory().transmitter.mac,
        lambda kind, **values: events.append((kind, values)),
    )
    reference.run_id = 123
    drops = 7

    def command(payload):
        return payload + struct.pack("!QQII", 1000, 1010, 11, drops)

    reference.command = command
    reference.sync(0)
    assert not reference.failure and reference.log_complete
    reference.accept_round(
        ROUND.pack(b"CGRD", 122, 11, 99, 1000, 1000, 12500, 1, 99, 255, 255, 255)
    )
    assert (
        reference.last_round is None
    )  # Interrupted-run frames stay outside this epoch.
    reference.accept_round(
        ROUND.pack(b"CGRD", 123, 11, 0, 1000, 1000, 12500, 1, 7, 255, 255, 255)
    )
    assert reference.last_round["log_drops"] == 0
    assert reference.last_round["lifetime_log_drops"] == 7
    drops = 8
    with pytest.raises(RuntimeError, match="incomplete"):
        reference.sync(1)
    assert not reference.log_complete


def test_short_usb_ack_write_is_fatal(tmp_path):
    m = manager(tmp_path, lambda *args: None)
    m.connection.write = lambda data: 0
    with pytest.raises(OSError, match="short"):
        m.accept(batch().encode(), time.monotonic_ns())
    m.journal.close()


def test_wrong_boot_or_profile_cannot_ack(tmp_path):
    m = manager(tmp_path, lambda *args: None)
    with pytest.raises(ValueError):
        m.accept(replace(batch(), transmitter_boot_id=12).encode(), time.monotonic_ns())
    m.readers["receiver-1"].status = {"boot_id": 22}
    with pytest.raises(ValueError):
        m.accept(batch().encode(), time.monotonic_ns())
    assert not m.connection.writes
    m.journal.close()


def test_c_config_scheduler_crc_queue_and_python_envelope_contract(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    src = tmp_path / "check.c"
    src.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "gateway_protocol.h"
#include "gateway_queue.h"
int main(int argc,char **argv){
    uint8_t p[1400];size_t n=strlen(argv[1])/2;
    for(unsigned i=0;i<n;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);p[i]=b;}
    gw_config_t c;assert(gw_config_decode(p,n,&c));assert(c.rate==80&&c.slot_ms==50&&c.capacity==64);
    assert(c.outstanding==8&&c.early_idle_ms==5);
    uint8_t saved[108];memcpy(saved,p,108);
    p[4]=1;p[29]=4;memset(p+100,0,4);gw_crc(p,108);
    assert(gw_config_decode(p,108,&c)&&c.outstanding==4&&c.early_idle_ms==0);
    p[29]=8;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    p[4]=2;gw_crc(p,108);assert(gw_config_decode(p,108,&c));
    p[101]=21;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    memcpy(p,saved,108);assert(gw_config_decode(p,108,&c));
    assert(gw_upload_exit(&c,12000,50000,10000,true,false,false)==GW_EXIT_NONE);
    assert(gw_upload_exit(&c,15000,50000,10000,true,false,false)==GW_EXIT_IDLE);
    assert(gw_upload_exit(&c,15000,50000,10000,false,false,true)==GW_EXIT_NONE);
    assert(gw_upload_exit(&c,15000,50000,10000,true,true,false)==GW_EXIT_NONE);
    assert(gw_upload_exit(&c,15000,50000,15000,true,true,true)==GW_EXIT_COMPLETE);
    assert(gw_upload_exit(&c,10000,50000,15000,true,false,false)==GW_EXIT_NONE);
    assert(gw_upload_exit(&c,50000,50000,15000,false,true,false)==GW_EXIT_DEADLINE);
    c.early_idle_ms=0;
    assert(gw_upload_exit(&c,49000,50000,0,true,false,true)==GW_EXIT_NONE);
    assert(gw_upload_exit(&c,50000,50000,0,false,false,false)==GW_EXIT_DEADLINE);
    c.early_idle_ms=5;
    assert(gw_return_cutoff(&c,75000,25000)==52500);
    assert(gw_return_cutoff(&c,50000,0)==27500);
    assert(gw_return_cutoff(&c,50000,49000)==0);
    gw_schedule_t s={0};assert(gw_schedule_next(&s,&c,1000));assert(s.owner==0);
    assert(gw_omit_sensing(&c,&s,0,38500,38500));
    assert(!gw_omit_sensing(&c,&s,1,38500,38500));
    /* The receiver must get the return-witness round before slot expiry. */
    assert(!gw_omit_sensing(&c,&s,0,63500,63500));
    assert(!gw_schedule_probe(&s,1,s.id,s.start+1,GW_CONFIRM));
    assert(!gw_schedule_probe(&s,0,s.id-1,s.start+1,GW_CONFIRM));
    assert(!gw_schedule_probe(&s,0,s.id,s.start-1,GW_CONFIRM));
    assert(gw_schedule_probe(&s,0,s.id,s.start+1,GW_CONFIRM));
    assert(!s.returned&&!gw_omit_sensing(&c,&s,0,38500,38500));
    assert(!gw_schedule_next(&s,&c,s.end+1)); /* Silence never grants a successor. */
    assert(!gw_schedule_return(&s,1,s.id,s.end,GW_CAPTURE));
    assert(!gw_schedule_return(&s,0,s.id-1,s.end,GW_CAPTURE));
    assert(!gw_schedule_return(&s,0,s.id,s.end,GW_UPLOAD));
    assert(gw_schedule_return(&s,0,s.id,s.end,GW_CAPTURE));
    assert(gw_schedule_next(&s,&c,s.end+1)&&s.owner==1);
    uint64_t previous_end=s.end,confirmed=s.end-15000;
    uint32_t previous_id=s.id;
    assert(gw_schedule_return(&s,1,s.id,confirmed,GW_CAPTURE));
    assert(!gw_schedule_return(&s,1,s.id,confirmed+1,GW_CAPTURE));
    assert(gw_schedule_next(&s,&c,confirmed)&&s.owner==2);
    assert(s.start>=previous_end&&s.start==confirmed+25000);
    assert(s.start<previous_end+25000); /* No extra end-of-slot wait. */
    assert(!gw_schedule_return(&s,1,previous_id,s.start,GW_CAPTURE));
    assert(!gw_schedule_next(&s,&c,s.end+100000)); /* Missing return still blocks. */
    for(unsigned i=0;i<1000;++i){
        uint8_t owner=s.owner;previous_end=s.end;
        confirmed=s.start+15000+(i%7)*7000;
        assert(gw_schedule_return(&s,owner,s.id,confirmed,GW_CAPTURE));
        assert(gw_schedule_next(&s,&c,confirmed));
        assert(s.owner==(owner+1)%c.count&&s.start>=previous_end&&s.start>=confirmed+25000);
    }
    s.id=UINT32_MAX;assert(gw_schedule_return(&s,s.owner,s.id,s.end,GW_CAPTURE));
    assert(gw_schedule_next(&s,&c,s.end)&&s.id==1); /* Zero means unhandled at boot. */
    gw_record_queue_t q={0};gw_queue_reset(&q,2);uint8_t value[1]={1};
    uint8_t polls=5;unsigned cursor=0;
    assert(gw_poll_next(&polls,5,4,&cursor)==0);polls&=~1U;
    assert(gw_poll_next(&polls,5,4,&cursor)==2);polls&=~4U;
    assert(gw_poll_next(&polls,5,4,&cursor)==-1); /* No duplicate entry polls. */
    polls=15;assert(gw_poll_next(&polls,0,4,&cursor)==-1&&polls==0);
    polls=8;assert(gw_poll_next(&polls,15,2,&cursor)==-1&&polls==0);
    polls=128;assert(gw_poll_next(&polls,255,8,&cursor)==7);polls=0;
    assert(gw_poll_next(&polls,255,8,&cursor)==-1);
    assert(gw_queue_push(&q,value,1,10));gw_record_slot_t *r=gw_queue_oldest(&q);r->state=2;r->batch=42;
    assert(gw_queue_push(&q,value,1,20));assert(gw_queue_push(&q,value,1,30));assert(q.evicted==1);
    gw_queue_expire(&q,100,50);assert(gw_queue_count(&q)==1);assert(gw_queue_release(&q,41,true)==0);
    assert(gw_queue_release(&q,42,true)==1&&q.acknowledged==1);
    gw_sensing_encode(p,&(csi_sensing_packet_t){.sequence=9,.tx_t1_us=1234},&c,11,&s);
    csi_sensing_packet_t decoded;assert(csi_sensing_decode(p,GW_SENSING_SIZE,&decoded));
    p[168]^=1;assert(!csi_sensing_decode(p,GW_SENSING_SIZE,&decoded));
    n=strlen(argv[2])/2;for(unsigned i=0;i<n;++i){unsigned b;sscanf(argv[2]+2*i,"%2x",&b);p[i]=b;}
    assert(gw_envelope_valid(p,n));p[n-1]^=1;assert(!gw_envelope_valid(p,n));
    return 0;
}
""")
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(root / "src/firmware/radio/common/include"),
            "-I",
            str(root / "src/firmware/radio/receiver/main"),
            str(src),
            "-o",
            str(tmp_path / "check"),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(tmp_path / "check"),
            EspnowTransportConfig(
                schema_version=2, outstanding_batches=8, early_return_idle_ms=5
            )
            .encode(123, inventory(), profile())
            .hex(),
            batch().encode().hex(),
        ],
        check=True,
    )


class FakeUsb:
    """A bounded fake USB endpoint, with responses generated by actual wire bytes."""

    def __init__(self, mac="02:00:00:00:00:05", supports_config2=True):
        from threading import Condition

        self.condition = Condition()
        self.pending = bytearray()
        self.mac = mac
        self.supports_config2 = supports_config2
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.pending)

    def inject(self, kind, payload):
        from fall_detection.radio.acquisition.serial_framing import encode_serial_frame

        with self.condition:
            self.pending.extend(encode_serial_frame(kind, payload))
            self.condition.notify_all()

    def read(self, n):
        with self.condition:
            if not self.pending:
                self.condition.wait(0.02)
            data = bytes(self.pending[:n])
            del self.pending[:n]
            return data

    def write(self, data):
        from fall_detection.radio.acquisition.serial_framing import decode_serial_frame

        frame = decode_serial_frame(data[1:-1])
        self.writes.append(frame)
        if frame.type == 5:
            self.inject(
                6,
                json.dumps(
                    dict(
                        role="gateway",
                        target="esp32c6",
                        mac=self.mac,
                        protocol_version=3,
                        transport_config_max_version=7 if self.supports_config2 else 1,
                        csi_transport="espnow_gateway",
                        boot_id=99,
                    )
                ).encode(),
            )
        elif frame.type == 20:
            unsupported = (
                frame.payload[:4] == b"CGCF"
                and frame.payload[4] > 1
                and not self.supports_config2
            )
            self.inject(21, b"error" if unsupported else b"ok")
        return len(data)

    def close(self):
        self.closed = True
        with self.condition:
            self.condition.notify_all()


@pytest.mark.parametrize(
    "config_version,ackless",
    [
        (1, False),
        (2, False),
        (3, False),
        (4, False),
        (5, False),
        (5, True),
        (6, False),
        (6, True),
        (7, False),
        (7, True),
    ],
)
def test_fake_usb_full_startup_recording_and_shutdown(
    tmp_path, config_version, ackless
):
    usb = FakeUsb()
    usb.pending.extend(b"\x00\x01\x02\x00")
    commands = []

    class FakeReference(Reference):
        def __init__(self, port, mac, event, **kwargs):
            self.event = event
            self.device_status = {"transport_config_max_version": 7}
            self.ready = True
            self.stopped = False

        def start(self):
            pass

        def sync(self, i):
            pass

        def capture_time(self, value):
            return time.monotonic_ns() - 1000000

        def command(self, data, **kwargs):
            commands.append(data[:4])
            if data[:4] == b"CGGO":
                for slot in range(4):
                    status = bytearray(96)
                    status[:4] = b"CGST"
                    status[4:6] = bytes([1, slot])
                    struct.pack_into("!QII", status, 8, 123, 11, 21)
                    struct.pack_into("!I", status, 92, zlib.crc32(status[:-4]))
                    self.event("radio_event", payload_hex=status.hex())
                    usb.inject(24, batch(receiver=slot).encode())
            return b"ok"

        def stop(self):
            self.stopped = True

    seen = []
    m = GatewayReceiverManager(
        inventory(),
        profile(),
        tmp_path,
        transmitter_port="tx",
        gateway_port="gw",
        run_id=123,
        require_four=True,
        config=EspnowTransportConfig(
            schema_version=config_version,
            outstanding_batches=8 if config_version >= 2 else 4,
            early_return_idle_ms=5 if config_version >= 2 else 0,
            application_acknowledgements=not ackless,
            maximum_retries=0 if ackless else 1,
        ),
        record_sink=lambda r, t: seen.append(r),
        serial_factory=lambda *a, **k: usb,
        reference_factory=FakeReference,
    )
    m.bind()
    m.start()
    until = time.monotonic() + 3
    while (
        (len(seen) < 4 or not m.preflight_ready)
        and not m.failure
        and time.monotonic() < until
    ):
        time.sleep(0.01)
    assert not m.failure
    assert len(seen) == 4 and m.preflight_ready
    m.stop()
    assert m.reference.stopped and usb.closed and commands[-1] == b"CGSP"
    assert len([f for f in usb.writes if f.type == 25]) == (0 if ackless else 4)


@pytest.mark.parametrize(
    "mac,supported,error,config_version",
    [
        ("02:00:00:00:00:ff", True, "identity mismatch", 2),
        ("02:00:00:00:00:05", False, "rejected configuration", 2),
        ("02:00:00:00:00:05", False, "rejected configuration", 3),
        ("02:00:00:00:00:05", False, "rejected configuration", 4),
        ("02:00:00:00:00:05", False, "lacks requested transport version", 5),
    ],
)
def test_gateway_preflight_rejection_stops_without_sensing(
    tmp_path, mac, supported, error, config_version
):
    usb = FakeUsb(mac=mac, supports_config2=supported)
    commands = []

    class FakeReference(Reference):
        def __init__(self, *a, **k):
            self.device_status = {"transport_config_max_version": 7}

        def start(self):
            pass

        def sync(self, i):
            pass

        def command(self, data, **kwargs):
            commands.append(data[:4])
            return b"ok"

        def stop(self):
            pass

    m = GatewayReceiverManager(
        inventory(),
        profile(),
        tmp_path,
        transmitter_port="tx",
        gateway_port="gw",
        run_id=123,
        serial_factory=lambda *a, **k: usb,
        reference_factory=FakeReference,
        config=EspnowTransportConfig(
            schema_version=config_version, outstanding_batches=8, early_return_idle_ms=5
        ),
    )
    m.start()
    until = time.monotonic() + 3
    while not m.failure and time.monotonic() < until:
        time.sleep(0.01)
    m.stop()
    assert m.failure and error in m.failure
    assert b"CGGO" not in commands


def test_switching_report_distinguishes_deadline_uncertainty(tmp_path):
    from fall_detection.radio.experiments.gateway import evaluate

    begin = 1_000_000_000
    inv = inventory()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            dict(
                inventory=inv.as_dict(),
                transport_config={"queue_capacity": 64},
            )
        )
    )
    events = [
        dict(kind="round", host_capture_ns=begin),
        dict(kind="round", host_capture_ns=begin + 1_000_000_000),
        dict(
            kind="clock_exchange",
            host_monotonic_ns=begin - 1,
            estimate=dict(
                receiver_boot_id=11,
                reference_transmitter_us=0,
                receiver_minus_transmitter_us=0,
                drift_ppm=0,
                uncertainty_us=100,
                sample_count=8,
                minimum_round_trip_us=200,
            ),
        ),
    ]
    for i, (lower_ms, upper_ms) in enumerate([(48, 49), (49, 51), (51, 52)]):
        start = 1_000_000 + i * 200_000
        grant = bytearray(
            struct.pack("!4sQII B3x QII", b"CGGR", 123, 11, i + 1, 0, start, 50, 0)
        )
        struct.pack_into("!I", grant, 36, zlib.crc32(grant[:36]))
        events.extend(
            [
                dict(
                    kind="radio_event",
                    host_monotonic_ns=begin + i * 200_000_000,
                    payload_hex=grant.hex(),
                ),
                dict(
                    kind="channel_interval",
                    grant_id=i + 1,
                    receiver_id=inv.receivers[0].id,
                    start_lower_ns=start * 1000 + 10_000_000,
                    end_lower_ns=start * 1000 + lower_ms * 1_000_000,
                    end_upper_ns=start * 1000 + upper_ms * 1_000_000,
                ),
            ]
        )
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events)
    )
    report = evaluate(tmp_path, warmup_s=0, measurement_s=1, qualification=False)
    assert report["slot_return_evidence"] == dict(
        before_deadline=1, after_deadline=1, uncertain=1, unmapped=0
    )
    assert report["upload_start_spacing_ms"]["mean"] == 200
    assert (
        report["receivers"][inv.receivers[0].id]["observed_recovery_upper_ms"][
            "intervals"
        ]
        == 3
    )
    assert not report["qualified"]


def test_qualification_reports_losses_uncertainty_and_incomplete_evidence(tmp_path):
    from fall_detection.radio.experiments.gateway import evaluate

    begin = 1_000_000_000
    inv = inventory()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            dict(inventory=inv.as_dict(), transport_config={"queue_capacity": 64})
        )
    )
    events = [
        dict(kind="round", host_capture_ns=begin),
        dict(kind="round", host_capture_ns=begin + 1_000_000_000),
    ]
    for receiver in inv.receivers:
        for i in range(50):
            captured = begin + i * 20_000_000
            events.append(
                dict(
                    kind="record",
                    receiver_id=receiver.id,
                    capture_host_ns=captured,
                    available_ns=captured + 10_000_000,
                    clock_uncertainty_us=10,
                )
            )
        for t in [begin + 1, begin + 999_999_999]:
            events.append(
                dict(
                    kind="receiver_status",
                    receiver_id=receiver.id,
                    host_monotonic_ns=t,
                    queued=1,
                    peak=4,
                )
            )
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events)
    )
    report = evaluate(tmp_path, warmup_s=0, measurement_s=1, qualification=False)
    assert all(
        v["timely_records_s"] == 50 and v["passes"]
        for v in report["receivers"].values()
    )
    assert (
        report["complete"]
        and not report["qualified"]
        and not report["complete_channel_evidence"]
    )
    # A delay over one second reduces useful coverage even if it was recorded.
    row = next(e for e in events if e["kind"] == "record")
    row["available_ns"] = row["capture_host_ns"] + 2_000_000_000
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events)
    )
    report = evaluate(tmp_path, warmup_s=0, measurement_s=1)
    assert report["receivers"][inv.receivers[0].id]["timely_records_s"] == 49
    assert not report["receivers"][inv.receivers[0].id]["passes"]
    row["clock_uncertainty_us"] = None
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events)
    )
    report = evaluate(tmp_path, warmup_s=0, measurement_s=1)
    assert not report["receivers"][inv.receivers[0].id]["clock_alignment_complete"]


def test_ackless_host_validates_deduplicates_without_ack(tmp_path):
    records = []
    m = manager(tmp_path, lambda r, t: records.append(r))
    m.config = EspnowTransportConfig(
        schema_version=5, application_acknowledgements=False, maximum_retries=0
    )
    assert m.accept(batch().encode(), time.monotonic_ns())
    assert m.accept(batch().encode(), time.monotonic_ns())
    assert len(records) == 1 and not m.connection.writes
    with pytest.raises(ValueError):
        m.accept(replace(batch(), transmitter_boot_id=12).encode(), time.monotonic_ns())
    m.journal.close()
    events = (m.journal.root / "events.jsonl").read_text()
    assert '"host_acceptance"' in events and '"host_acceptance_ack"' not in events


def test_ackless_recorder_failure_remains_fatal(tmp_path):
    def fail(*args):
        raise OSError("disk full")

    m = manager(tmp_path, fail)
    m.config = EspnowTransportConfig(
        schema_version=5, application_acknowledgements=False, maximum_retries=0
    )
    with pytest.raises(OSError, match="disk full"):
        m.accept(batch().encode(), time.monotonic_ns())
    assert not m.connection.writes
    m.journal.close()
