"""Offline transport contracts for configuration, envelopes and firmware C code."""

import shutil
import struct
import subprocess
import zlib
from dataclasses import replace
from pathlib import Path

import pytest
from envelope_reference import Envelope
from transport_config import transport_config
from wire_encoder import (
    DecodedCsiDatagram,
    ReceiverStats,
    encode_csi_batch,
)

from fall_detection import _radio_native as core
from fall_detection.radio.profile import (
    RadioInventory,
    RadioProfile,
    profile_fingerprint,
)
from fall_detection.radio.records import CsiRecord


def inventory():
    def device(i, role, target="esp32c5"):
        return {
            "id": f"{role}-{i}",
            "role": role,
            "target": target,
            "mac": f"02:00:00:00:00:{i:02x}",
        }

    return RadioInventory.from_mapping(
        {
            "schema_version": 2,
            "transmitter": device(0, "transmitter"),
            "receivers": [device(i, "receiver") for i in range(1, 5)],
            "gateway": device(5, "gateway", "esp32c6"),
        }
    )


def profile():
    return RadioProfile.from_mapping(
        {
            "schema_version": 2,
            "profile_id": "test",
            "country_code": "ID",
            "band": "5ghz",
            "channel": 44,
            "bandwidth_mhz": 20,
            "nominal_rate_hz": 80,
        }
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
    return Envelope(123, 11, 21, seq, mac, p)


def test_config_inventory_order_and_identity_fingerprint():
    inv, p, c = inventory(), profile(), transport_config()
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
    with pytest.raises(ValueError):
        RadioInventory.from_mapping(old)
    with pytest.raises(ValueError):
        c.validate(
            replace(inv, transmitter=replace(inv.transmitter, target="esp32c6")), p
        )


def test_current_policy_encodes_eight_batch_window():
    current = transport_config(outstanding_batches=8, early_return_idle_ms=5)
    raw = current.encode(123, inventory(), profile())
    assert raw[4] == 7 and raw[29] == 8 and raw[100] == 5
    assert current.fingerprint(inventory(), profile()) != replace(
        current, early_return_idle_ms=0
    ).fingerprint(inventory(), profile())
    with pytest.raises(ValueError):
        replace(current, outstanding_batches=9)
    with pytest.raises(ValueError):
        replace(current, schema_version=6)


@pytest.mark.parametrize(
    "changes",
    [
        {"slot_ms": 10},
        {"return_reserve_ms": 50},
        {"queue_capacity": 97},
        {"maximum_retries": 4},
        {"phy": "default"},
        {"channel": 14},
        {"ack_timeout_ms": 501},
    ],
)
def test_config_rejects_unsafe_policies(changes):
    with pytest.raises(ValueError):
        transport_config(**changes)


def test_rust_envelope_decoder_checks_crc_identity_and_size():
    b = batch()
    raw = b.encode()
    decoded = core.decode_envelope(raw)
    assert len(raw) <= 1400
    assert (decoded.run_id, decoded.batch_id, decoded.receiver_mac) == (
        123,
        1,
        b.receiver_mac,
    )
    damaged = bytearray(raw)
    damaged[-6] ^= 1
    with pytest.raises(ValueError):
        core.decode_envelope(bytes(damaged))
    damaged = bytearray(raw)
    damaged[28] ^= 1
    struct.pack_into("!I", damaged, len(damaged) - 4, zlib.crc32(damaged[:-4]))
    with pytest.raises(ValueError):
        core.decode_envelope(bytes(damaged))
    with pytest.raises(ValueError):
        replace(b, payload=b"x" * 1400).encode()
    assert len(b.acknowledgement()) == 34


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
            transport_config(
                schema_version=7, outstanding_batches=8, early_return_idle_ms=5
            )
            .encode(123, inventory(), profile())
            .hex(),
            batch().encode().hex(),
        ],
        check=True,
    )
