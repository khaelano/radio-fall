"""Opt-in timing diagnostics must preserve normal collection contracts."""

from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil
import subprocess
import struct

import pytest

from fall_detection.radio.ble_config import (
    BleTimingExperiment,
    BleTransportConfig,
    grant_owner,
)
from fall_detection.radio.acquisition.ble_protocol import decode_timing
from fall_detection.radio.acquisition.ble_reader import BleReceiverManager
from fall_detection.radio.experiments.ble import summarize
from fall_detection.radio.experiments.ble_timing import deadline_sweep


def test_experiment_wire_and_default_compatibility(tmp_path):
    default = BleTransportConfig()
    assert default.fingerprint == "edd8925808ad05ba"
    assert default.encode(1, 4, 80)[4] == 1
    experiment = BleTimingExperiment(upload_policy="continuous", slot_rounds=2)
    config = replace(default, experiment=experiment)
    raw = config.encode(1, 4, 80)
    assert raw[4] == 2 and raw[56:64] == bytes([2, 2, 0, 10, 0, 0, 1, 0])
    assert config.fingerprint != default.fingerprint
    path = tmp_path / "config.json"
    path.write_text(json.dumps(asdict(config)))
    assert BleTransportConfig.load(path) == config


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(slot_rounds=0),
        dict(batch_records=5),
        dict(connection_interval_units=5),
        dict(submission_pacing_us=65536),
        dict(upload_policy="adaptive"),
    ],
)
def test_experiment_rejects_unbounded_settings(kwargs):
    with pytest.raises(ValueError):
        BleTimingExperiment(**kwargs)


def test_timing_snapshot_is_single_read_and_strict():
    raw = bytearray(232)
    struct.pack_into("!4sBBH", raw, 0, b"CBTM", 1, 4, 232)
    struct.pack_into("!II6Q", raw, 8, 1, 7, 100, 110, 120, 130, 140, 0)
    values = decode_timing(bytes(raw))
    assert len(values) == 1 and values[0]["ack_us"] == 140
    assert len(raw) <= 247 - 1
    with pytest.raises(ValueError):
        decode_timing(bytes(raw[:-1]))


def test_experiment_cannot_enter_collection(tmp_path):
    with pytest.raises(ValueError, match="development"):
        BleReceiverManager(
            None,
            None,
            tmp_path,
            transmitter_port="test",
            config=BleTransportConfig(experiment=BleTimingExperiment()),
            require_four=True,
        )


def test_multiround_rotation_is_fixed():
    assert [grant_owner(i, 4, slot_rounds=2) for i in range(10)] == [
        0,
        0,
        1,
        1,
        2,
        2,
        3,
        3,
        0,
        0,
    ]


def test_report_distinguishes_requested_and_negotiated_interval(tmp_path):
    manifest = dict(
        run_id="1",
        hardware_backend=True,
        inventory={"receivers": [dict(id="rx-1", mac="aa")]},
        radio_profile={"nominal_rate_hz": 80},
        transport_config=asdict(
            BleTransportConfig(
                experiment=BleTimingExperiment(connection_interval_units=20)
            )
        ),
    )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    events = [
        dict(kind="sensing_started", start_ns=0, host_monotonic_ns=0),
        dict(kind="measurement_started", at_ns=0, host_monotonic_ns=0),
        dict(
            kind="receiver_status",
            receiver="rx-1",
            host_monotonic_ns=1,
            status=dict(boot_id=1, interval_units=6),
        ),
        dict(
            kind="measurement_finished",
            at_ns=1_000_000_000,
            host_monotonic_ns=1_000_000_000,
        ),
    ]
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    report = summarize(tmp_path)
    d = report["receivers"]["rx-1"]["diagnostics"]
    assert d["requested_interval_units"] == 20
    assert d["observed_interval_units"] == [6]
    assert not d["interval_request_verified"]


def test_deadline_counterfactual_preserves_raw_and_uses_availability(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            dict(
                transport_config={"bin_hz": 50},
                inventory={"receivers": [{"mac": "aa"}]},
            )
        )
    )
    events = [
        dict(kind="sensing_started", start_ns=0),
        dict(kind="measurement_started", at_ns=0),
    ]
    for c, a in [(10, 121), (30, 300), (35, 110)]:
        events.append(
            dict(
                kind="record",
                receiver_mac="aa",
                capture_host_ns=c * 1_000_000,
                arrival_ns=0,
                available_ns=a * 1_000_000,
            )
        )
    events.append(dict(kind="measurement_finished", at_ns=100_000_000))
    raw = "\n".join(json.dumps(e) for e in events)
    (tmp_path / "events.jsonl").write_text(raw)
    r = deadline_sweep(tmp_path)["grace_ms"]
    assert r["100"]["aa"]["timely_record_rate_hz"] == 10
    assert r["200"]["aa"]["timely_record_rate_hz"] == 20
    assert r["350"]["aa"]["timely_record_rate_hz"] == 30
    assert r["350"]["aa"]["available_bin_rate_hz"] == 20
    assert (tmp_path / "events.jsonl").read_text() == raw


def test_c_experiment_sync_and_rotation(tmp_path):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "timing.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "ble_grants.h"
int main(int argc, char **argv) {
    assert(argc == 2); uint8_t raw[64];
    for (unsigned i=0; i<64; ++i) {unsigned n; assert(sscanf(argv[1]+i*2,"%2x",&n)==1);raw[i]=n;}
    csi_ble_config_t c; assert(csi_ble_config_decode(raw,64,&c));
    assert(c.slot_rounds==2 && c.batch_records==2 && c.continuous_upload);
    ble_grants_t g={0}; assert(!ble_grants_available(&g,&c,3,2000));
    assert(ble_grants_observe(&g,&c,0,1000,1000,2000,(uint8_t[]){0,0,1}));
    assert(ble_grants_available(&g,&c,3,3000));
    assert(!ble_grants_available(&g,&c,3,40000));
    c.continuous_upload=false;
    assert(ble_grants_available(&g,&c,0,3000));g.remaining=0;
    assert(ble_grants_observe(&g,&c,1,13500,13500,14500,(uint8_t[]){0,1,1}));
    assert(!ble_grants_available(&g,&c,0,15000)); /* no budget reset inside a slot */
    assert(csi_ble_config_owner(7,&c)==3 && csi_ble_config_owner(8,&c)==0);
    return 0;
}""")
    binary = tmp_path / "timing"
    subprocess.run(
        [
            compiler,
            "-std=c11",
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
        experiment=BleTimingExperiment(upload_policy="continuous", slot_rounds=2)
    )
    subprocess.run([str(binary), config.encode(1, 4, 80).hex()], check=True)
