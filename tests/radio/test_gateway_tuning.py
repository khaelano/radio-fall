"""Version-3 cadence, guard and selective ACK contracts against the real C header."""

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from fall_detection.radio.espnow_config import EspnowTransportConfig
from fall_detection.radio.profile import RadioInventory, RadioProfile


def tuning_policy():
    return EspnowTransportConfig(
        schema_version=7,
        outstanding_batches=8,
        minimum_revisit_ms=150,
        batch_acknowledgements=True,
        measure_send_completions=True,
    )


def identities():
    inventory = RadioInventory.from_mapping(
        {
            "schema_version": 2,
            "transmitter": {
                "id": "tx",
                "role": "transmitter",
                "target": "esp32c5",
                "mac": "02:00:00:00:00:01",
            },
            "receivers": [
                {
                    "id": "rx",
                    "role": "receiver",
                    "target": "esp32c5",
                    "mac": "02:00:00:00:00:02",
                }
            ],
            "gateway": {
                "id": "gw",
                "role": "gateway",
                "target": "esp32c6",
                "mac": "02:00:00:00:00:03",
            },
        }
    )
    profile = RadioProfile.from_mapping(
        {
            "schema_version": 1,
            "profile_id": "test",
            "country_code": "ID",
            "band": "5ghz",
            "channel": 44,
            "bandwidth_mhz": 20,
            "nominal_rate_hz": 80,
        }
    )
    return inventory, profile


def test_tuning_policy_encoding_and_fingerprints():
    inv, profile = identities()
    policy = tuning_policy()
    raw = policy.encode(123, inv, profile)
    assert len(raw) == 108 and raw[4] == 7 and raw[100:104] == bytes([0, 30, 10, 3])
    for changes in [
        {"minimum_revisit_ms": 200},
        {"send_completion_guard_ms": 5},
        {"batch_acknowledgements": False},
        {"measure_send_completions": False},
    ]:
        assert replace(policy, **changes).fingerprint(
            inv, profile
        ) != policy.fingerprint(inv, profile)
    for changes in [
        {"schema_version": 2},
        {"minimum_revisit_ms": 151},
        {"minimum_revisit_ms": 1005},
        {"send_completion_guard_ms": 0},
        {"send_completion_guard_ms": 21},
        {"batch_acknowledgements": 1},
        {"measure_send_completions": 1},
    ]:
        with pytest.raises(ValueError):
            replace(policy, **changes)


def test_c_revisit_and_bitmap_acceptance_contract(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "check.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "gateway_protocol.h"
int main(int argc,char **argv){
    (void)argc;uint8_t raw[108];for(unsigned i=0;i<108;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);raw[i]=b;}
    gw_config_t c;assert(gw_config_decode(raw,108,&c));
    assert(c.revisit_ms==150&&c.send_guard_ms==10&&c.bitmap_ack&&c.measure_sends&&c.return_ms==10);
    uint8_t saved[108];memcpy(saved,raw,108);
    raw[103]=4;gw_crc(raw,108);assert(!gw_config_decode(raw,108,&c));
    memcpy(raw,saved,108);raw[102]=0;gw_crc(raw,108);assert(!gw_config_decode(raw,108,&c));
    memcpy(raw,saved,108);raw[101]=201;gw_crc(raw,108);assert(!gw_config_decode(raw,108,&c));
    memcpy(raw,saved,108);assert(gw_config_decode(raw,108,&c));
    for(unsigned receivers=1;receivers<=4;receivers*=2){
        c.count=receivers;gw_schedule_t s={0};uint64_t previous[4]={0};uint64_t now=1000;
        for(unsigned i=0;i<1000;++i){
            uint64_t old_end=s.end;assert(gw_schedule_next(&s,&c,now));
            assert(s.owner==i%receivers&&s.start>=old_end&&s.start>=now+25000);
            if(previous[s.owner])assert(s.start-previous[s.owner]>=150000);
            previous[s.owner]=s.start;
            assert(!gw_schedule_next(&s,&c,s.end+1000000));
            assert(!gw_schedule_return(&s,s.owner,s.id-1,s.end,GW_CAPTURE));
            assert(gw_schedule_probe(&s,s.owner,s.id,s.start+1,GW_CONFIRM));
            assert(!gw_schedule_next(&s,&c,s.end));
            now=s.start+30000;assert(gw_schedule_return(&s,s.owner,s.id,now,GW_CAPTURE));
        }
    }
    uint8_t q[GW_BITMAP_SIZE]={0},a[GW_BITMAP_SIZE],cache[2][GW_ACK_SIZE]={{0}};
    memcpy(q,"CGPQ",4);q[4]=1;q[5]=3;csi_clock_write_u64(q+8,123);
    csi_clock_write_u32(q+16,11);csi_clock_write_u32(q+20,21);memcpy(q+24,saved+44,6);
    csi_clock_write_u32(q+32,42);uint32_t ids[3]={UINT32_MAX,0,9};
    for(unsigned i=0;i<3;++i)csi_clock_write_u32(q+36+4*i,ids[i]);
    gw_crc(q,sizeof(q));
    assert(gw_bitmap_valid(q,sizeof(q),false));
    assert(gw_bitmap_reply(q,NULL,0,a)&&a[6]==0&&gw_bitmap_matches(q,a)); /* MAC receipt is not acceptance. */
    for(unsigned i=0;i<2;++i){
        memcpy(cache[i],"CGAK",4);csi_clock_write_u64(cache[i]+4,123);
        csi_clock_write_u32(cache[i]+12,11);csi_clock_write_u32(cache[i]+16,21);
        csi_clock_write_u32(cache[i]+20,ids[i?2:0]);memcpy(cache[i]+24,q+24,6);gw_crc(cache[i],GW_ACK_SIZE);
    }
    assert(gw_bitmap_reply(q,&cache[0][0],2,a)&&a[6]==5&&gw_bitmap_matches(q,a));
    a[6]=8;gw_crc(a,sizeof(a));assert(!gw_bitmap_valid(a,sizeof(a),true));
    assert(gw_bitmap_reply(q,&cache[0][0],2,a));a[35]^=1;gw_crc(a,sizeof(a));assert(!gw_bitmap_matches(q,a));
    cache[0][19]^=1;gw_crc(cache[0],GW_ACK_SIZE);
    assert(gw_bitmap_reply(q,&cache[0][0],2,a)&&a[6]==4); /* Stale receiver boot. */
    q[5]=9;gw_crc(q,sizeof(q));assert(!gw_bitmap_valid(q,sizeof(q),false));
    return 0;
}
""")
    executable = tmp_path / "check"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(root / "src/firmware/radio/common/include"),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    inv, profile = identities()
    subprocess.run(
        [str(executable), tuning_policy().encode(123, inv, profile).hex()], check=True
    )
