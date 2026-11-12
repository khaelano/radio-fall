"""Higher-rate experiments retain old flags, identities and channel interlocking."""

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_gateway_tuning import identities

from fall_detection.radio.espnow_config import EspnowTransportConfig
from fall_detection.radio.profile import RadioProfile, RadioProfileError


@pytest.mark.parametrize("mcs", range(4))
def test_throughput_python_c_contract(tmp_path, mcs):
    inventory, old_profile = identities()
    profile = RadioProfile.from_mapping(
        dict(old_profile.as_dict(), schema_version=2, nominal_rate_hz=120)
    )
    policy = EspnowTransportConfig(
        schema_version=7,
        phy=f"ht20_mcs{mcs}_lgi",
        application_acknowledgements=False,
        maximum_retries=0,
        slot_ms=125,
        records_per_slot=64,
        minimum_revisit_ms=600,
        maximum_age_ms=750,
    )
    raw = policy.encode(123, inventory, profile)
    assert len(raw) == 108 and raw[4] == 7 and raw[103] == 4 | (mcs << 3)
    assert policy.fingerprint(inventory, profile) != replace(
        policy, phy=f"ht20_mcs{(mcs + 1) % 4}_lgi"
    ).fingerprint(inventory, profile)
    with pytest.raises(ValueError):
        replace(policy, schema_version=5).encode(123, inventory, profile)
    with pytest.raises(ValueError):
        replace(policy, phy="ht20_mcs4_lgi")
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    source = tmp_path / "contract.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "gateway_protocol.h"
int main(int argc,char **argv){
    (void)argc;uint8_t p[108];for(unsigned i=0;i<108;++i){unsigned v;sscanf(argv[1]+2*i,"%2x",&v);p[i]=v;}
    gw_config_t c;assert(gw_config_decode(p,108,&c)&&c.rate==120&&c.allowance==64);
    assert(c.backhaul_mcs==(unsigned)atoi(argv[2])&&!c.application_ack&&c.return_ms==10);
    uint8_t saved[108];memcpy(saved,p,108);
    p[4]=5;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    memcpy(p,saved,108);p[103]|=32;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    memcpy(p,saved,108);csi_clock_write_u16(p+16,121);gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    memcpy(p,saved,108);assert(gw_config_decode(p,108,&c));
    gw_schedule_t s={0};assert(gw_schedule_next(&s,&c,1000));
    assert(!gw_schedule_next(&s,&c,s.end+1000000));
    assert(!gw_schedule_return(&s,s.owner,s.id-1,s.end,GW_CAPTURE));
    assert(!gw_schedule_return(&s,s.owner,s.id,s.end,GW_CONFIRM));
    assert(gw_schedule_return(&s,s.owner,s.id,s.end,GW_CAPTURE));
    uint64_t earliest=s.next_allowed[0];assert(gw_schedule_next(&s,&c,s.end)&&s.start>=earliest);
    return 0;
}
""")
    executable = tmp_path / "contract"
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-include",
            "stdlib.h",
            "-I",
            str(root / "src/firmware/radio/common/include"),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable), raw.hex(), str(mcs)], check=True)


@pytest.mark.parametrize(
    "rate,band", [(121, "5ghz"), (120.5, "5ghz"), (True, "5ghz"), (120, "2.4ghz")]
)
def test_profile_rejects_unsupported_throughput_rate(rate, band):
    _, profile = identities()
    with pytest.raises(RadioProfileError):
        RadioProfile.from_mapping(
            dict(
                profile.as_dict(),
                schema_version=2,
                nominal_rate_hz=rate,
                band=band,
                channel=6 if band == "2.4ghz" else 44,
            )
        )


def test_c_provisioning_profile_accepts_120_only_on_5ghz(tmp_path):
    import json

    from fall_detection.radio.profile import profile_fingerprint
    from fall_detection.radio.provisioning import _profile_payload

    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    inventory, old_profile = identities()
    profile = RadioProfile.from_mapping(
        dict(old_profile.as_dict(), schema_version=2, nominal_rate_hz=120)
    )
    payload = _profile_payload(
        inventory, profile, profile_fingerprint(profile, inventory)
    )
    if isinstance(payload, bytes):
        payload = payload.decode()
    elif isinstance(payload, dict):
        payload = json.dumps(payload, separators=(",", ":"))
    (tmp_path / "nvs.h").write_text("""
#include <stddef.h>
#include <stdint.h>
typedef int nvs_handle_t;typedef int esp_err_t;
#define NVS_READONLY 0
#define NVS_READWRITE 1
#define ESP_OK 0
static inline int nvs_open(const char *n,int m,nvs_handle_t *h){(void)n;(void)m;(void)h;return 1;}
static inline void nvs_close(nvs_handle_t h){(void)h;}
static inline int nvs_get_blob(nvs_handle_t h,const char *k,void *p,size_t *n){(void)h;(void)k;(void)p;(void)n;return 1;}
static inline int nvs_set_blob(nvs_handle_t h,const char *k,const void *p,size_t n){(void)h;(void)k;(void)p;(void)n;return 0;}
static inline int nvs_commit(nvs_handle_t h){(void)h;return 0;}
""")
    source = tmp_path / "profile.c"
    source.write_text("""
#include <assert.h>
#include <string.h>
#include "radio_profile.h"
int main(int argc,char **argv){
 (void)argc;csi_radio_profile_t p;assert(csi_radio_profile_from_json((const uint8_t *)argv[1],strlen(argv[1]),&p));
 assert(p.nominal_rate_hz==120&&csi_radio_profile_validate(&p,true));
 assert(!csi_radio_profile_validate(&p,false));p.nominal_rate_hz=121;assert(!csi_radio_profile_validate(&p,true));
 p.nominal_rate_hz=120;p.band=CSI_RADIO_BAND_2G;p.channel=6;assert(!csi_radio_profile_validate(&p,true));
 p.nominal_rate_hz=100;assert(csi_radio_profile_validate(&p,true));return 0;
}
""")
    common = Path(__file__).resolve().parents[2] / "src/firmware/radio/common"
    executable = tmp_path / "profile"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(tmp_path),
            "-I",
            str(common / "include"),
            str(source),
            str(common / "radio_profile.c"),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable), payload], check=True)


@pytest.mark.parametrize("target,passes", [(50, True), (80, False)])
def test_benchmark_uses_explicit_delivery_target(tmp_path, target, passes):
    import json

    from fall_detection.radio.experiments.gateway import evaluate

    inventory, _ = identities()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "inventory": inventory.as_dict(),
                "transport_config": {"queue_capacity": 64},
            }
        )
    )
    begin = 1_000_000_000
    events = [
        {"kind": "round", "host_capture_ns": begin},
        {"kind": "round", "host_capture_ns": begin + 1_000_000_000},
    ]
    for i in range(60):
        t = begin + i * 10_000_000
        events.append(
            {
                "kind": "record",
                "receiver_id": "rx",
                "capture_host_ns": t,
                "available_ns": t + 100_000_000,
                "clock_uncertainty_us": 100,
            }
        )
    for offset in [1, 999_999_999]:
        events.append(
            {
                "kind": "receiver_status",
                "receiver_id": "rx",
                "host_monotonic_ns": begin + offset,
                "queued": 2,
                "peak": 3,
            }
        )
    (tmp_path / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n"
    )
    report = evaluate(
        tmp_path,
        warmup_s=0,
        measurement_s=1,
        qualification=False,
        target_records_s=target,
    )
    assert report["target_records_s"] == target
    assert report["receivers"]["rx"]["timely_records_s"] == 60
    assert report["receivers"]["rx"]["passes"] == passes
    assert not report["qualified"]


def test_reference_accepts_configured_120hz_round_and_rejects_wrong_period():
    from fall_detection.radio.acquisition.transmitter_reference import (
        ROUND,
        TransmitterReference,
    )

    reference = TransmitterReference(
        "tx", "02:00:00:00:00:01", lambda *a, **k: None, expected_sensing_rate_hz=120
    )
    reference.run_id = 123
    reference.accept_round(
        ROUND.pack(b"CGRD", 123, 11, 0, 1000, 1000, 8333, 1, 0, 255, 255, 255)
    )
    assert reference._next_round == 1
    with pytest.raises(ValueError, match="period"):
        reference.accept_round(
            ROUND.pack(b"CGRD", 123, 11, 1, 10000, 10000, 12500, 1, 0, 255, 255, 255)
        )


def test_queue96_requires_new_version_and_fits_control_queue_savings(tmp_path):
    inventory, old_profile = identities()
    profile = RadioProfile.from_mapping(
        dict(old_profile.as_dict(), schema_version=2, nominal_rate_hz=120)
    )
    config = EspnowTransportConfig(
        schema_version=7,
        queue_capacity=96,
        records_per_slot=64,
        slot_ms=125,
        application_acknowledgements=False,
        maximum_retries=0,
    )
    with pytest.raises(ValueError):
        replace(config, schema_version=6)
    with pytest.raises(ValueError):
        replace(config, queue_capacity=97)
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "q96.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "gateway_protocol.h"
#include "gateway_queue.h"
int main(int argc,char **argv){
 (void)argc;uint8_t p[108];for(unsigned i=0;i<108;++i){unsigned v;sscanf(argv[1]+2*i,"%2x",&v);p[i]=v;}
 gw_config_t c;assert(gw_config_decode(p,108,&c)&&c.capacity==96&&c.allowance==64);
 p[4]=6;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));p[4]=7;p[28]=97;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
 gw_record_queue_t q={0};gw_queue_reset(&q,96);uint8_t bytes[577]={0};
 for(unsigned i=0;i<90;++i)assert(gw_queue_push(&q,bytes,sizeof(bytes),i*8333));
 assert(gw_queue_count(&q)==90&&q.peak==90&&!q.evicted&&!q.rejected);
 gw_queue_expire(&q,750000,750000);assert(gw_queue_count(&q)==89&&q.expired==1);
 assert((1400-GW_SENSING_SIZE)*32>32*sizeof(gw_record_slot_t));
 printf("additional_record_bytes=%zu control_queue_bytes_saved=%u\n",32*sizeof(gw_record_slot_t),(1400-GW_SENSING_SIZE)*32);
 return 0;
}
""")
    executable = tmp_path / "q96"
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
    subprocess.run(
        [str(executable), config.encode(123, inventory, profile).hex()], check=True
    )
