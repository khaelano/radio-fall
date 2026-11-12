"""Run the actual transmitter control state machine with a deterministic clock."""

import shutil
import subprocess

import pytest


def test_sensing_send_policy_bounds_pending_frames_and_rotates_without_wrap(tmp_path):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    source = tmp_path / "send.c"
    source.write_text("""
#include <assert.h>
#include "sensing_send_policy.h"
int main(void) {
    csi_sensing_send_policy_t p = {0};
    for (unsigned i=0; i<4; ++i) assert(csi_sensing_reserve(&p, i));
    assert(p.pending_mask == 15);
    for (unsigned i=0; i<4; ++i) assert(!csi_sensing_reserve(&p, i));
    assert(p.busy_skips == 4 && p.pending_mask == 15);
    csi_sensing_complete(&p, 3);
    assert(p.pending_mask == 7 && csi_sensing_reserve(&p, 3));
    csi_sensing_complete(&p, 0);
    csi_sensing_complete(&p, 0);
    assert(p.pending_mask == 14);
    assert(!csi_sensing_reserve(&p, 4));
    csi_sensing_result(&p, 3, false, 1000, 100000);
    assert(!csi_sensing_reserve_at(&p, 3, 100999));
    assert(p.backoff_skips == 1);
    assert(csi_sensing_reserve_at(&p, 3, 101000));
    csi_sensing_result(&p, 3, true, 101001, 100000);
    assert(csi_sensing_reserve_at(&p, 3, 101001));
    for (unsigned count=1; count<=4; ++count) {
        for (unsigned delta=0; delta<8; ++delta) {
            uint32_t sequence = UINT32_MAX-delta;
            unsigned seen=0;
            for (unsigned offset=0; offset<count; ++offset) {
                unsigned peer=csi_sensing_peer(sequence, offset, count);
                assert(peer<count && !(seen & (1U<<peer)));
                seen |= 1U<<peer;
            }
            assert(seen == (1U<<count)-1);
        }
    }
}
""")
    executable = tmp_path / "send"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-I",
            "src/firmware/radio/transmitter/main",
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True)
