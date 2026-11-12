"""Connectionless bridge ordering, bounded buffering, and actual host startup."""

import hashlib
import hmac
import json
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path

import pytest
from test_gateway import FakeUsb, batch, inventory, profile

from fall_detection.radio.acquisition.gateway_reader import GatewayReceiverManager
from fall_detection.radio.acquisition.serial_framing import (
    decode_serial_frame,
    encode_serial_frame,
)
from fall_detection.radio.acquisition.transmitter_reference import ROUND
from fall_detection.radio.acquisition.wireless_reference import WirelessReferenceSerial
from fall_detection.radio.espnow_config import EspnowTransportConfig
from fall_detection.radio.profile import profile_fingerprint


def test_wireless_serial_demultiplexes_and_bounds_queue():
    writes = []
    port = WirelessReferenceSerial(
        lambda kind, data: writes.append((kind, data)), capacity=64
    )
    request = encode_serial_frame(20, b"CGSP" + bytes(8))
    port.write(request[:5])
    assert not writes
    port.write(request[5:])
    assert writes == [(26, b"\x14CGSP" + bytes(8))]
    port.feed(b"\x15ok")
    response = port.read(port.in_waiting)
    assert decode_serial_frame(response[1:-1]).payload == b"ok"
    port.feed(b"\x00\x15\x00\x02ok\x17\x00\x04CGST")
    from fall_detection.radio.acquisition.serial_framing import SerialFrameStreamDecoder

    frames = SerialFrameStreamDecoder().feed(port.read(port.in_waiting))
    assert [(f.type, f.payload) for f in frames] == [(21, b"ok"), (23, b"CGST")]
    with pytest.raises(ValueError):
        port.feed(b"\x00\x15\x00\x02ok\x17\x00\x05short"[:-1])
    assert not port.in_waiting
    with pytest.raises(ValueError):
        port.feed(b"")
    with pytest.raises(BufferError):
        port.feed(b"\x06" + bytes(64))
    port.close()
    assert port.read(1) == b""
    with pytest.raises(OSError):
        port.write(request)


def test_wireless_stream_recovers_loss_and_reordering_in_actual_c(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    common = Path(__file__).resolve().parents[2] / "src/firmware/radio/common/include"
    source = tmp_path / "check.c"
    source.write_text(r"""
#include "wireless_link_protocol.h"
#include <assert.h>
#include <stdlib.h>
static unsigned delivered;
static bool emit(const uint8_t *p,size_t n,void *context){
    (void)context;assert(n==7&&p[0]==23&&wl_u16(p+1)==4&&wl_u32(p+3)==delivered);++delivered;return true;
}
int main(void){
    static wl_stream_t tx,rx;
    assert(!wl_epoch_valid(5,5,111,4,111));
    assert(!wl_epoch_valid(5,5,111,5,222));
    assert(wl_epoch_valid(5,5,111,6,222));
    assert(!wl_epoch_valid(0,0,0,0,222));
    assert(!wl_epoch_valid(UINT32_MAX,0,0,1,222));
    uint8_t frame[7]={23,0,4},raw[WL_PACKET],encoded[1650],decoded[WL_PACKET];
    for(unsigned group=0;group<1000;++group){
        for(unsigned i=0;i<4;++i){wl_w32(frame+3,group*4+i);assert(wl_stream_add(&tx,frame,sizeof(frame),group+1));}
        assert(!wl_stream_add(&tx,frame,sizeof(frame),group+1));
        /* Deliver out of order, lose the oldest packet, and repeat a duplicate. */
        for(int i=3;i>0;--i){assert(wl_stream_receive(&rx,tx.tx[i].sequence,tx.tx[i].data,tx.tx[i].size,emit,NULL));}
        assert(wl_stream_receive(&rx,tx.tx[3].sequence,tx.tx[3].data,tx.tx[3].size,emit,NULL));
        assert(delivered==group*4);
        assert(wl_stream_mask(&rx)==14);
        assert(!wl_stream_ack(&tx,tx.next_tx+1,0));
        assert(!wl_stream_ack(&tx,tx.next_tx,1));
        assert(wl_stream_ack(&tx,rx.next_rx,wl_stream_mask(&rx)));
        assert(tx.tx[0].used&&!tx.tx[1].used&&!tx.tx[2].used&&!tx.tx[3].used);
        assert(!wl_stream_add(&tx,frame,sizeof(frame),group+1)); /* SACK cannot extend the receive window. */
        assert(wl_stream_receive(&rx,tx.tx[0].sequence,tx.tx[0].data,tx.tx[0].size,emit,NULL));
        assert(delivered==(group+1)*4);
        assert(wl_stream_receive(&rx,tx.tx[0].sequence,tx.tx[0].data,tx.tx[0].size,emit,NULL));
        assert(delivered==(group+1)*4);
        assert(wl_stream_ack(&tx,rx.next_rx,0));
        assert(wl_stream_ack(&tx,rx.next_rx-1,0));
    }
    assert(!wl_stream_receive(&rx,rx.next_rx+4,frame,sizeof(frame),emit,NULL));
    assert(!wl_stream_add(&tx,frame,WL_PAYLOAD+1,0));
    tx.next_tx=UINT32_MAX-4;assert(!wl_stream_add(&tx,frame,sizeof(frame),0));
    for(unsigned i=0;i<sizeof(raw);++i)raw[i]=(uint8_t)i;
    size_t n=wl_ad_encode(raw,sizeof(raw),encoded,sizeof(encoded));assert(n&&n<=1650);
    for(unsigned offset=0;offset<n;offset+=encoded[offset]+1)assert(encoded[offset]<=254);
    assert(wl_ad_decode(encoded,n,decoded,sizeof(decoded))==sizeof(raw)&&!memcmp(raw,decoded,sizeof(raw)));
    assert(!wl_ad_encode(raw,sizeof(raw),encoded,10));
    encoded[0]=255;assert(!wl_ad_decode(encoded,10,decoded,sizeof(decoded)));
    assert(!wl_ad_decode((uint8_t[]){0},1,decoded,sizeof(decoded)));
    uint32_t seed=123;uint8_t original[WL_LOGICAL],compact[WL_LOGICAL+64],restored[WL_LOGICAL];
    for(unsigned test=0;test<5000;++test){
        unsigned length=1+test%WL_LOGICAL;
        for(unsigned i=0;i<length;++i){seed=seed*1664525+1013904223;original[i]=test%3==0?0:(test%3==1?i%61:seed>>24);}
        size_t compressed=wl_compress(original,length,compact,sizeof(compact));assert(compressed);
        assert(wl_decompress(compact,compressed,restored,sizeof(restored))==length&&!memcmp(original,restored,length));
    }
    /* A full logical batch can exceed the wire limit after compression while
     * a smaller compressed prefix carries substantially more than raw fallback. */
    for(unsigned i=0;i<40;++i){
        unsigned start=i*100;original[start]=23;wl_w16(original+start+1,97);
        for(unsigned j=3;j<100;++j){seed=seed*1664525+1013904223;original[start+j]=j<55?0:seed>>24;}
    }
    size_t consumed=0,packed=wl_encode_frames(original,4000,compact,WL_PAYLOAD,&consumed);
    assert(packed&&packed<=WL_PAYLOAD&&consumed>1279&&consumed<4000&&consumed%100==0);
    size_t unpacked=compact[0]?wl_decompress(compact+1,packed-1,restored,sizeof(restored)):packed-1;
    if(!compact[0])memcpy(restored,compact+1,unpacked);
    assert(unpacked==consumed&&!memcmp(original,restored,consumed));
    assert(!wl_encode_frames(original,3999,compact,WL_PAYLOAD,&consumed));
    /* Runtime control packets fit one live periodic update. A large profile
     * remains an idle-only extended advertisement, not implicit fragmentation. */
    original[0]=20;wl_w16(original+1,108);memset(original+3,0,108);
    packed=wl_encode_frames(original,111,compact,WL_PERIODIC_PAYLOAD,&consumed);
    assert(packed&&consumed==111&&WL_HEADER+packed+WL_TAG+4<=251);
    original[0]=7;wl_w16(original+1,1000);
    for(unsigned j=0;j<1000;++j){seed=seed*1664525+1013904223;original[j+3]=seed>>24;}
    assert(!wl_encode_frames(original,1003,compact,WL_PERIODIC_PAYLOAD,&consumed));

    for(unsigned test=0;test<1000;++test){
        size_t total=0;
        while(total+200<WL_LOGICAL){
            seed=seed*1664525+1013904223;size_t size=seed%197+1;
            original[total]=23;wl_w16(original+total+1,size);
            for(unsigned j=0;j<size;++j){seed=seed*1664525+1013904223;original[total+3+j]=test%2?seed>>24:j%13;}
            total+=size+3;
        }
        size_t offset=0;
        while(offset<total){
            packed=wl_encode_frames(original+offset,total-offset,compact,WL_PAYLOAD,&consumed);
            assert(packed&&packed<=WL_PAYLOAD&&consumed&&consumed<=total-offset);
            unpacked=compact[0]?wl_decompress(compact+1,packed-1,restored,sizeof(restored)):packed-1;
            if(!compact[0])memcpy(restored,compact+1,unpacked);
            assert(unpacked==consumed&&wl_frames_valid(restored,unpacked)&&!memcmp(original+offset,restored,consumed));
            offset+=consumed;
        }
    }

    assert(!wl_decompress((uint8_t[]){128,0},2,restored,sizeof(restored)));
    assert(!wl_decompress((uint8_t[]){127,1},2,restored,sizeof(restored)));
    assert(!wl_decompress((uint8_t[]){0,1,255,0},4,restored,3));
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
            str(common),
            str(source),
            "-o",
            str(tmp_path / "check"),
        ],
        check=True,
    )
    subprocess.run([str(tmp_path / "check")], check=True)


def test_wireless_c_validator_matches_authenticated_python_packets(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    common = Path(__file__).resolve().parents[2] / "src/firmware/radio/common/include"
    source = tmp_path / "validate.c"
    source.write_text(r"""
#include "wireless_link_protocol.h"
#include <assert.h>
#include <stdio.h>
static uint8_t expected[32];static size_t signed_length;
static bool mac(const uint8_t *p,size_t n,uint8_t out[32]){assert(!memcmp(p,"CWL2",4));signed_length=n;memcpy(out,expected,32);return true;}
int main(int argc,char **argv){
    assert(argc==4);uint8_t p[WL_PACKET];size_t n=strlen(argv[1])/2;assert(n<=sizeof(p));
    unsigned value;for(size_t i=0;i<n;++i){assert(sscanf(argv[1]+2*i,"%2x",&value)==1);p[i]=value;}
    for(unsigned i=0;i<32;++i){assert(sscanf(argv[2]+2*i,"%2x",&value)==1);expected[i]=value;}
    bool valid=wl_packet_valid(p,n,1,mac);assert(valid==(argv[3][0]=='1'));
    if(valid)assert(signed_length==n-WL_TAG);
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
            str(common),
            str(source),
            "-o",
            str(tmp_path / "validate"),
        ],
        check=True,
    )
    header = struct.pack("!4sBBIQQIIBH", b"CWL2", 2, 0, 7, 123, 456, 0, 0, 0, 7)
    body = header + b"\x14\x00\x04CGSP"
    key = bytes(range(32))
    digest = hmac.digest(key, body, hashlib.sha256)
    packet = body + digest[:16]
    cases = [(packet, True)]
    for offset in (4, 5, 10, 26, 35, 39, len(packet) - 1):
        corrupted = bytearray(packet)
        corrupted[offset] ^= 1
        cases.append((bytes(corrupted), False))
    cases.append((packet[:-1], False))
    for value, valid in cases:
        actual_digest = hmac.digest(key, value[:-16], hashlib.sha256)
        subprocess.run(
            [
                str(tmp_path / "validate"),
                value.hex(),
                actual_digest.hex(),
                str(int(valid)),
            ],
            check=True,
        )


class WirelessUsb(FakeUsb):
    """One USB endpoint carrying distinct gateway and transmitter messages."""

    def __init__(self, paired=True, link="ble"):
        super().__init__()
        self.paired = paired
        self.link = link
        self.wireless_commands = []

    def inject(self, kind, payload):
        if kind == 27:
            payload = (
                b"\x00" + struct.pack("!BH", payload[0], len(payload) - 1) + payload[1:]
            )
        super().inject(kind, payload)

    def write(self, data):
        frame = decode_serial_frame(data[1:-1])
        if frame.type == 5:
            status = {
                "role": "gateway",
                "target": "esp32c6",
                "mac": self.mac,
                "protocol_version": 3,
                "transport_config_max_version": 7,
                "csi_transport": "espnow_gateway",
                "boot_id": 99,
                "wireless_version": 2,
                "wireless_paired": self.paired,
                "wireless_ready": True,
                "wireless_fault": False,
                "wireless_drops": 0,
                "wireless_peer_changes": 0,
            }
            if self.link == "espnow_uart":
                status = {
                    (
                        key.replace("wireless_", "relay_")
                        if key.startswith("wireless_")
                        else key
                    ): value
                    for key, value in status.items()
                }
                status.update(relay_version=1, relay_transport="espnow_uart")
            self.inject(6, json.dumps(status).encode())
        elif frame.type == 26:
            kind, payload = frame.payload[0], frame.payload[1:]
            if kind == 5:
                status = {
                    "role": "transmitter",
                    "mac": inventory().transmitter.mac,
                    "protocol_version": 3,
                    "ready": True,
                    "sensing_version": 4,
                    "csi_transport": "espnow_gateway",
                    "sensing_phy": "he20",
                    "transport_config_max_version": 7,
                    "profile_fingerprint": profile_fingerprint(profile(), inventory()),
                }
                self.inject(27, b"\x06" + json.dumps(status).encode())
            elif kind == 20:
                self.wireless_commands.append(payload[:4])
                if payload[:4] == b"CGHC":
                    now = time.monotonic_ns() // 1000
                    response = payload + struct.pack("!QQII", now, now, 11, 0)
                else:
                    response = b"ok"
                self.inject(27, b"\x15" + response)
                if payload[:4] == b"CGGO":
                    now = time.monotonic_ns() // 1000
                    self.inject(
                        27,
                        b"\x16"
                        + ROUND.pack(
                            b"CGRD", 123, 11, 0, now, now, 12500, 15, 0, 255, 255, 255
                        ),
                    )
                    for slot in range(4):
                        status = bytearray(96)
                        status[:4] = b"CGST"
                        status[4:6] = bytes([1, slot])
                        struct.pack_into("!QII", status, 8, 123, 11, 21)
                        struct.pack_into("!I", status, 92, zlib.crc32(status[:-4]))
                        self.inject(27, b"\x17" + status)
                        self.inject(24, batch(receiver=slot).encode())
        else:
            return super().write(data)
        self.writes.append(frame)
        return len(data)


@pytest.mark.parametrize("paired", [True, False])
@pytest.mark.parametrize("link", ["espnow_uart"])
def test_gateway_only_usb_uses_real_wireless_reference(tmp_path, paired, link):
    usb = WirelessUsb(paired, link)
    seen = []
    manager = GatewayReceiverManager(
        inventory(),
        profile(),
        tmp_path,
        transmitter_port=None,
        gateway_port="gateway",
        transmitter_link=link,
        run_id=123,
        require_four=True,
        config=EspnowTransportConfig(drain_ms=500),
        record_sink=lambda record, accepted: seen.append(record),
        serial_factory=lambda *a, **k: usb,
    )
    manager.bind()
    manager.start()
    deadline = time.monotonic() + 3
    while (
        not manager.failure
        and not manager.preflight_ready
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    manager.stop()
    if paired:
        assert manager.failure is None
        assert len(seen) == 4
        assert b"CGCF" in usb.wireless_commands and b"CGGO" in usb.wireless_commands
        assert usb.wireless_commands[-1] == b"CGSP"
    else:
        assert "paired connectionless" in manager.failure
        assert b"CGGO" not in usb.wireless_commands


@pytest.mark.parametrize("link", ["espnow_uart"])
def test_wireless_missing_boot_evidence_fails_within_bound(tmp_path, link):
    class MissingStatusUsb(WirelessUsb):
        def inject(self, kind, payload):
            if kind == 27 and payload[:5] == b"\x17CGST":
                return
            super().inject(kind, payload)

    usb = MissingStatusUsb(link=link)
    manager = GatewayReceiverManager(
        inventory(),
        profile(),
        tmp_path,
        transmitter_port=None,
        gateway_port="gateway",
        transmitter_link=link,
        run_id=123,
        require_four=True,
        config=EspnowTransportConfig(drain_ms=500),
        serial_factory=lambda *a, **k: usb,
    )
    manager.start()
    deadline = time.monotonic() + 3
    while not manager.failure and time.monotonic() < deadline:
        time.sleep(0.01)
    manager.stop()
    assert "boot evidence unavailable" in manager.failure
    assert usb.wireless_commands[-1] == b"CGSP"
