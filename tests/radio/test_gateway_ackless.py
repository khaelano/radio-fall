"""ACK-less mode is versioned and cannot silently enable retries or bitmap ACKs."""

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_gateway_tuning import identities

from fall_detection.radio.espnow_config import EspnowTransportConfig


def test_ackless_config_contract_and_c_decoder(tmp_path):
    inventory, profile = identities()
    config = EspnowTransportConfig(
        schema_version=7, application_acknowledgements=False, maximum_retries=0
    )
    raw = config.encode(123, inventory, profile)
    assert raw[4] == 7 and raw[103] == 4 and len(raw) == 108
    assert config.fingerprint(inventory, profile) != replace(
        config, application_acknowledgements=True
    ).fingerprint(inventory, profile)
    for change in [
        {"schema_version": 4},
        {"maximum_retries": 1},
        {"batch_acknowledgements": True},
        {"application_acknowledgements": 0},
    ]:
        with pytest.raises(ValueError):
            replace(config, **change)
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    source = tmp_path / "ackless.c"
    source.write_text(r"""
#include <assert.h>
#include <stdio.h>
#include "gateway_protocol.h"
int main(int argc,char **argv){
    (void)argc;uint8_t p[108];for(unsigned i=0;i<108;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);p[i]=b;}
    gw_config_t c;assert(gw_config_decode(p,108,&c)&&!c.application_ack&&!c.retries);
    assert(gw_batch_ready(&c,0,0,1,2));assert(!gw_batch_ready(&c,1,1,1,100000));
    p[30]=1;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));p[30]=0;
    p[103]=5;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));p[103]=4;
    p[4]=4;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    p[4]=5;p[103]=8;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    p[103]=0;gw_crc(p,108);assert(gw_config_decode(p,108,&c)&&c.application_ack);
    p[4]=8;gw_crc(p,108);assert(!gw_config_decode(p,108,&c));
    return 0;
}
""")
    root = Path(__file__).resolve().parents[2]
    executable = tmp_path / "ackless"
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
    subprocess.run([str(executable), raw.hex()], check=True)
