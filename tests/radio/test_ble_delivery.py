"""Fresh admission, durable transport credits, and receipt wire contracts."""

from dataclasses import asdict
import json
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from fall_detection.radio.ble_config import (
    BleDeliveryExperiment,
    BleTimingExperiment,
    BleTransportConfig,
    flow_token,
)
from fall_detection.radio.acquisition.ble_protocol import FlowFragment, progress_receipt


def test_delivery_config_is_explicit_and_roundtrips(tmp_path):
    config = BleTransportConfig(
        experiment=BleTimingExperiment(
            connection_interval_units=6, delivery=BleDeliveryExperiment()
        )
    )
    raw = config.encode(123, 4, 80)
    assert len(raw) == 80 and raw[4] == 3
    assert raw[64:80] == struct.pack(
        "!HHHHBBHI", 100, 60, 150, 1000, 8, 4, 10, flow_token(123)
    )
    p = tmp_path / "config.json"
    p.write_text(json.dumps(asdict(config)))
    assert BleTransportConfig.load(p) == config
    assert BleTransportConfig().fingerprint == "edd8925808ad05ba"


def test_flow_fragment_scope_bounds_and_progress_crc():
    raw = struct.pack("!4sIIIHH", b"CBL2", 17, 0xFFFFFFFF, 3, 0, 100) + b"abc"
    item = FlowFragment.decode(raw, 17)
    assert item.serial == 0xFFFFFFFF and item.classic[:4] == b"CBLF"
    with pytest.raises(ValueError):
        FlowFragment.decode(raw, 18)
    with pytest.raises(ValueError):
        FlowFragment.decode(raw[:20], 17)
    ack = progress_receipt(123, 11, 21, 17, item.serial)
    import zlib

    assert len(ack) == 32 and ack[:4] == b"CBPR"
    assert struct.unpack("!I", ack[-4:])[0] == zlib.crc32(ack[:-4])


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(completion_budget_ms=100),
        dict(credit_fragments=0),
        dict(progress_every=9),
        dict(transfer_timeout_ms=59),
        dict(progress_interval_ms=0),
    ],
)
def test_delivery_rejects_inconsistent_limits(kwargs):
    with pytest.raises(ValueError):
        BleDeliveryExperiment(**kwargs)


def test_flow_report_does_not_subtract_counters_across_receiver_boots(tmp_path):
    from fall_detection.radio.experiments.ble import summarize

    manifest = dict(
        run_id="1",
        inventory={"receivers": [dict(id="rx-1", mac="aa")]},
        radio_profile={"nominal_rate_hz": 80},
        transport_config=asdict(BleTransportConfig()),
    )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    events = [
        dict(kind="sensing_started", start_ns=0, host_monotonic_ns=0),
        dict(kind="measurement_started", at_ns=0, host_monotonic_ns=0),
    ]
    for stamp, boot, count in [(1, 1, 10), (2, 2, 2)]:
        events.append(
            dict(
                kind="receiver_status",
                receiver="rx-1",
                host_monotonic_ns=stamp,
                status=dict(
                    boot_id=boot,
                    flow_inflight_fragments=0,
                    flow_submitted_fragments=count,
                ),
            )
        )
    events.append(dict(kind="measurement_finished", at_ns=3, host_monotonic_ns=3))
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    d = summarize(tmp_path)["receivers"]["rx-1"]["diagnostics"]
    assert d["receiver_restarted"]
    assert d["flow"]["flow_submitted_fragments_delta"] is None


def test_c_flow_credits_survive_application_expiry_and_reject_future_ack(tmp_path):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "flow.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "ble_flow.h"
#include "ble_queue.h"
#include "ble_protocol.h"
int main(int argc,char **argv) {
  ble_flow_t f={0};uint32_t a,b,c;
  assert(ble_flow_reserve(&f,2,9,244,10,&a));
  assert(ble_flow_reserve(&f,2,9,244,11,&b));
  assert(!ble_flow_reserve(&f,2,10,244,12,&c));
  /* Application age expiry releases queue memory, not the independent ledger. */
  ble_record_queue_t q={0};ble_queue_reset(&q,1);uint8_t data[2]={1,2};
  assert(ble_queue_push(&q,data,2,10));ble_record_slot_t *s=ble_queue_oldest(&q);s->state=2;s->batch=9;
  assert(ble_queue_release(&q,9,false)==1);
  assert(f.count==2 && f.bytes==488 && ble_flow_has_batch(&f,9));
  assert(!ble_flow_ack(&f,b+1,20));assert(f.count==2);
  assert(ble_flow_ack(&f,a,20));assert(f.count==1 && f.bytes==244);
  assert(ble_flow_ack(&f,a,21));assert(f.count==1);
  assert(ble_flow_reserve(&f,2,10,100,22,&c));
  ble_flow_cancel(&f,c);assert(f.count==1 && f.bytes==244);
  assert(ble_flow_ack(&f,b,23));assert(f.count==0 && !ble_flow_has_batch(&f,9));
  assert(!ble_admission_allowed(40001,0,100,60));
  assert(ble_admission_allowed(40000,0,100,60));
  assert(!ble_admission_allowed(1,2,100,60));
  assert(ble_queue_push(&q,data,2,100));ble_queue_expire(&q,99,40);assert(ble_queue_count(&q)==1);
  f.next_serial=0xffffffffU;f.acked=0xfffffffeU;f.have_acked=true;
  assert(ble_flow_reserve(&f,2,11,1,30,&a) && a==0xffffffffU);
  assert(ble_flow_reserve(&f,2,11,1,31,&b) && b==0);
  assert(ble_flow_ack(&f,0,32) && f.count==0);
  uint8_t raw[80];assert(argc==3);
  for(unsigned i=0;i<80;++i){unsigned v;assert(sscanf(argv[1]+2*i,"%2x",&v)==1);raw[i]=v;}
  csi_ble_config_t cfg;assert(csi_ble_config_decode(raw,80,&cfg));
  assert(cfg.credit_flow && cfg.delivery_deadline_ms==100 && cfg.completion_budget_ms==60);
  assert(cfg.transfer_timeout_ms==150 && cfg.credit_fragments==8 && cfg.flow_token);
  uint8_t progress[32];
  for(unsigned i=0;i<32;++i){unsigned v;assert(sscanf(argv[2]+2*i,"%2x",&v)==1);progress[i]=v;}
  assert(csi_ble_progress_matches(progress,32,123,11,21,cfg.flow_token));
  assert(!csi_ble_progress_matches(progress,32,124,11,21,cfg.flow_token));
  assert(!csi_ble_progress_matches(progress,32,123,12,21,cfg.flow_token));
  assert(!csi_ble_progress_matches(progress,32,123,11,22,cfg.flow_token));
  progress[31]^=1;assert(!csi_ble_progress_matches(progress,32,123,11,21,cfg.flow_token));
  uint8_t out[32],payload[3]={1,2,3};
  size_t n=csi_ble_flow_fragment_encode(out,sizeof(out),cfg.flow_token,0xffffffffU,9,0,100,payload,3);
  assert(n==23);for(unsigned i=0;i<n;++i)printf("%02x",out[i]);puts("");
  return 0;
}""")
    binary = tmp_path / "flow"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
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
    config = BleTransportConfig(
        experiment=BleTimingExperiment(delivery=BleDeliveryExperiment())
    )
    result = subprocess.run(
        [
            str(binary),
            config.encode(123, 4, 80).hex(),
            progress_receipt(123, 11, 21, flow_token(123), 2).hex(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    fragment = FlowFragment.decode(
        bytes.fromhex(result.stdout.strip()), flow_token(123)
    )
    assert (fragment.batch_id, fragment.serial, fragment.payload) == (
        9,
        0xFFFFFFFF,
        b"\x01\x02\x03",
    )
