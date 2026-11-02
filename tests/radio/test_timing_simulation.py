"""Grant timing follows the actual single-authority C scheduling contract."""

from pathlib import Path
import shutil
import subprocess

import pytest

from fall_detection.radio.experiments.timing import simulate_receiver_timing


@pytest.mark.parametrize(
    "slot,expected", [(50, 300), (80, 450), (100, 500), (125, 600)]
)
def test_nominal_timing_keeps_three_potential_captures(slot, expected):
    model = simulate_receiver_timing(slot)
    assert model.nominal_revisit_ms == expected
    assert model.maximum_off_channel_or_unconfirmed == 1
    assert model.minimum_potential_sensing_receivers == 3
    assert [g.owner for g in model.grants] == [0, 1, 2, 3] * 2
    assert all(
        b.start_ms >= a.confirmed_ms for a, b in zip(model.grants, model.grants[1:])
    )


def test_lost_return_suspends_new_departures():
    normal = simulate_receiver_timing(100)
    failed = simulate_receiver_timing(100, lost_return_grant=2)
    assert len(failed.grants) == 2 and failed.grants[-1].confirmed_ms is None
    assert failed.horizon_ms == normal.horizon_ms
    assert failed.phases[-1].state == "unconfirmed"
    assert failed.phases[-1].end_ms == failed.horizon_ms
    assert failed.maximum_off_channel_or_unconfirmed == 1
    assert failed.minimum_potential_sensing_receivers == 3


def test_timing_matches_shared_c_scheduler(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    root = Path(__file__).resolve().parents[2]
    src = tmp_path / "timing.c"
    src.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "gateway_protocol.h"
int main(int argc,char **argv){
 (void)argc;gw_config_t c={.count=4,.rate=80,.slot_ms=(uint16_t)atoi(argv[1])};
 gw_schedule_t s={0};uint64_t now=0;
 for(unsigned i=0;i<8;++i){
  assert(gw_schedule_next(&s,&c,now));printf("%u %llu %llu\n",s.owner,(unsigned long long)s.start,(unsigned long long)s.end);
  assert(!gw_schedule_next(&s,&c,s.end+1000000));
  now=((s.end+12499)/12500)*12500;
  assert(gw_schedule_return(&s,s.owner,s.id,now,GW_CAPTURE));
 }
 return 0;
}
""")
    exe = tmp_path / "timing"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(root / "src/firmware/radio/common/include"),
            str(src),
            "-o",
            str(exe),
        ],
        check=True,
    )
    for slot in (50, 80, 100, 125):
        rows = subprocess.check_output([str(exe), str(slot)], text=True).splitlines()
        observed = [tuple(map(int, row.split())) for row in rows]
        model = simulate_receiver_timing(slot)
        assert observed == [
            (g.owner, int(g.start_ms * 1000), int(g.end_ms * 1000))
            for g in model.grants
        ]
