"""Bounded retention and later-turn retries against the shared firmware contract."""

from dataclasses import replace
from pathlib import Path
import shutil
import subprocess

import pytest

from fall_detection.radio.espnow_config import EspnowTransportConfig
from test_gateway_tuning import identities


def test_retention_retry_version_and_deadline_contract(tmp_path):
    inv, profile = identities()
    policy = EspnowTransportConfig(
        schema_version=4,
        maximum_age_ms=750,
        maximum_retries=2,
        delivery_grace_ms=900,
    )
    raw = policy.encode(123, inv, profile)
    assert len(raw) == 108 and raw[4] == 4 and raw[30] == 2
    assert raw[100:104] == bytes([0, 0, 10, 0])
    for version in (1, 2, 3):
        with pytest.raises(ValueError):
            replace(policy, schema_version=version)
    with pytest.raises(ValueError):
        replace(policy, maximum_retries=4)
    assert replace(policy, maximum_retries=3).fingerprint(
        inv, profile
    ) != policy.fingerprint(inv, profile)
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "retention.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "gateway_protocol.h"
#include "gateway_queue.h"
int main(int argc,char **argv){
    (void)argc;uint8_t raw[108];
    for(unsigned i=0;i<108;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);raw[i]=b;}
    gw_config_t c;assert(gw_config_decode(raw,108,&c)&&c.retries==2&&c.age_ms==750);
    for(unsigned v=1;v<=3;++v){
        raw[4]=v;memset(raw+100,0,4);if(v==3)raw[102]=10;
        raw[30]=2;gw_crc(raw,108);assert(!gw_config_decode(raw,108,&c));
        raw[30]=1;gw_crc(raw,108);assert(gw_config_decode(raw,108,&c));
    }
    raw[4]=4;raw[102]=10;raw[30]=4;gw_crc(raw,108);assert(!gw_config_decode(raw,108,&c));
    raw[30]=3;gw_crc(raw,108);assert(gw_config_decode(raw,108,&c));
    uint64_t oldest=1000,sent=1000;
    assert(gw_batch_ready(&c,0,sent,oldest,oldest));
    assert(!gw_batch_ready(&c,1,sent,oldest,sent+49999));
    assert(gw_batch_ready(&c,1,sent,oldest,sent+50000));
    assert(gw_batch_ready(&c,3,sent,oldest,sent+50000));
    assert(!gw_batch_ready(&c,4,sent,oldest,sent+50000));
    assert(gw_batch_ready(&c,1,sent,oldest,oldest+749999));
    assert(!gw_batch_ready(&c,1,sent,oldest,oldest+750000));
    assert(!gw_batch_ready(&c,0,sent,oldest,oldest+750000));
    assert(!gw_batch_ready(&c,1,sent,oldest,oldest-1));
    assert(gw_upload_exit(&c,50000,50000,10000,false,true,false)==GW_EXIT_DEADLINE);
    gw_schedule_t schedule={0};assert(gw_schedule_next(&schedule,&c,0));
    assert(!gw_schedule_next(&schedule,&c,schedule.end+1000000));
    gw_record_queue_t q={0};gw_queue_reset(&q,2);uint8_t data[2]={1,2};
    assert(gw_queue_push(&q,data,2,oldest));gw_queue_expire(&q,oldest+500000,750000);
    assert(gw_queue_count(&q)==1);q.slots[0].state=2;q.slots[0].batch=9;
    assert(gw_queue_push(&q,data,2,oldest));gw_queue_expire(&q,oldest+750000,750000);
    assert(gw_queue_count(&q)==1&&q.slots[0].state==2);
    assert(gw_queue_release(&q,8,true)==0);assert(gw_queue_release(&q,9,true)==1);
    assert(gw_queue_release(&q,9,true)==0&&q.acknowledged==1);
    return 0;
}
""")
    executable = tmp_path / "retention"
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
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable), raw.hex()], check=True)
