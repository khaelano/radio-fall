import shutil
import subprocess
from pathlib import Path

import pytest


def test_firmware_batch_policy_handles_boundary_timeout_size_and_wrap(tmp_path: Path):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("a host C compiler is required for the firmware policy test")
    repository = Path(__file__).resolve().parents[2]
    include_dir = repository / "src/firmware/radio/receiver/main"
    executable = tmp_path / "batch_policy_test"
    source = r"""
        #include <assert.h>
        #include <stdint.h>
        #include "batch_policy.h"

        int main(void) {
            assert(!csi_batch_sequence_boundary(2, 4));
            assert(csi_batch_sequence_boundary(3, 4));
            assert(csi_batch_sequence_boundary(UINT32_MAX, 4));
            assert(!csi_batch_wait_expired(34, 35));
            assert(csi_batch_wait_expired(35, 35));
            assert(csi_batch_record_fits(60, 55, 612, 1400));
            assert(csi_batch_record_fits(729, 55, 612, 1400));
            assert(!csi_batch_record_fits(1398, 55, 2, 1400));
            return 0;
        }
    """
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(include_dir),
            "-x",
            "c",
            "-",
            "-o",
            str(executable),
        ],
        input=source,
        text=True,
        check=True,
    )
    subprocess.run([str(executable)], check=True)
