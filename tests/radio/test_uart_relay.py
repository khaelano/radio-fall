"""Exercise the actual relay state machine and UART framing on a native compiler."""

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "src/firmware/radio/common"


def test_serial_uart_parser_recovers_boundaries_and_rejects_corruption(tmp_path):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    source = tmp_path / "serial.c"
    source.write_text(r"""
#include <assert.h>
#include "serial_stream.h"
int main(void) {
    csi_serial_decoder_t d={0};
    uint8_t payload[1400],raw[CSI_SERIAL_MAX_RAW_SIZE],frame[CSI_SERIAL_MAX_FRAME_SIZE];
    for(unsigned i=0;i<sizeof(payload);++i)payload[i]=i;
    size_t n=csi_serial_encode_frame(23,payload,sizeof(payload),raw,sizeof(raw),frame,sizeof(frame));
    assert(n);
    uint8_t type;const uint8_t *p;size_t size;unsigned frames=0,errors=0;
    for(unsigned i=0;i<20;++i)assert(csi_serial_feed(&d,'x',&type,&p,&size)==0);
    for(unsigned repeat=0;repeat<100;++repeat)
        for(size_t i=0;i<n;++i){int r=csi_serial_feed(&d,frame[i],&type,&p,&size);
            assert(r>=0);if(r){++frames;assert(type==23&&size==sizeof(payload)&&!memcmp(p,payload,size));}}
    assert(frames==100);
    frame[n-3]^=1;
    for(size_t i=0;i<n;++i)if(csi_serial_feed(&d,frame[i],&type,&p,&size)<0)++errors;
    assert(errors==1);
    frame[n-3]^=1;
    for(unsigned i=0;i<2000;++i)csi_serial_feed(&d,1,&type,&p,&size);
    assert(csi_serial_feed(&d,0,&type,&p,&size)==-1);
    for(size_t i=0;i<n;++i)if(csi_serial_feed(&d,frame[i],&type,&p,&size)>0)++frames;
    assert(frames==101);
}
""")
    executable = tmp_path / "serial"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(COMMON / "include"),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)


@pytest.fixture(scope="module")
def relay_executable(tmp_path_factory):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    tmp_path = tmp_path_factory.mktemp("relay-native")
    (tmp_path / "fake.h").write_text(r"""
#ifndef RELAY_FAKE_H
#define RELAY_FAKE_H
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
#define CONFIG_CSI_ESPNOW_UART_RELAY 1
#define ESP_OK 0
#define ESP_ERROR_CHECK(x) assert((x)==ESP_OK)
#define WIFI_IF_STA 0
#define WIFI_SECOND_CHAN_NONE 0
#define NVS_READWRITE 1
#define portMAX_DELAY 0xffffffffU
#define pdTRUE 1
#define pdMS_TO_TICKS(x) (x)
typedef void *QueueHandle_t;
typedef void *SemaphoreHandle_t;
typedef int nvs_handle_t;
typedef int wifi_second_chan_t;
typedef struct {uint8_t peer_addr[6],lmk[16];int channel,ifidx;bool encrypt;} esp_now_peer_info_t;
extern uint64_t test_now;
extern uint8_t captured[1400];
extern size_t captured_size;
extern uint8_t pair_config[49];
static inline uint64_t esp_timer_get_time(void){return test_now;}
static inline uint32_t esp_random(void){return 12345;}
static inline void *xSemaphoreCreateMutex(void){return (void *)1;}
static unsigned test_queue_locked;
static inline int xSemaphoreTake(void *m,unsigned t){
    (void)m;(void)t;if(test_queue_locked)return 0;test_queue_locked=1;return 1;
}
static inline int xSemaphoreGive(void *m){(void)m;assert(test_queue_locked);test_queue_locked=0;return 1;}
static inline int nvs_open(const char *n,int mode,nvs_handle_t *h){(void)n;(void)mode;*h=1;return 0;}
static inline int nvs_get_u32(int h,const char *k,uint32_t *v){(void)h;*v=!strcmp(k,"boot")?1:0;return 0;}
static inline int nvs_set_u32(int h,const char *k,uint32_t v){(void)h;(void)k;(void)v;return 0;}
static inline int nvs_commit(int h){(void)h;return 0;}
static inline void nvs_close(int h){(void)h;}
static inline int nvs_get_blob(int h,const char *k,void *p,size_t *n){(void)h;(void)k;assert(*n>=49);memcpy(p,pair_config,49);*n=49;return 0;}
static inline int nvs_set_blob(int h,const char *k,const void *p,size_t n){(void)h;(void)k;(void)p;(void)n;return 0;}
static inline int esp_wifi_get_channel(uint8_t *c,int *s){*c=6;*s=0;return 0;}
static inline int esp_wifi_set_channel(uint8_t c,int s){(void)c;(void)s;return 0;}
static inline int esp_now_set_pmk(const void *p){(void)p;return 0;}
static inline bool esp_now_is_peer_exist(const void *p){(void)p;return false;}
static inline int esp_now_del_peer(const void *p){(void)p;return 0;}
static inline int esp_now_add_peer(const esp_now_peer_info_t *p){assert(p->encrypt&&p->channel==6);return 0;}
#endif
""")
    for name in [
        "sdkconfig.h",
        "esp_now.h",
        "esp_mac.h",
        "esp_random.h",
        "esp_timer.h",
        "esp_wifi.h",
        "nvs.h",
        "freertos/FreeRTOS.h",
        "freertos/queue.h",
        "freertos/semphr.h",
    ]:
        target = tmp_path / name
        target.parent.mkdir(exist_ok=True)
        target.write_text('#include "fake.h"\n')
    source = tmp_path / "relay.c"
    source.write_text(r"""
#include "fake.h"
#include "reference_relay.h"
#include "gateway_io.h"
uint64_t test_now=1000000;
uint8_t captured[1400],pair_config[49];size_t captured_size;
static uint8_t local[6]={2,0,0,0,0,1},remote[6]={2,0,0,0,0,2};
static uint64_t local_nonce;
static unsigned incoming_count,outgoing_count;
static wl_stream_t remote_stream;
static bool inject_ingress;
static size_t encode_with_uart_ingress(const uint8_t *p,size_t n,uint8_t *out,
                                      size_t capacity,size_t *consumed){
    if(inject_ingress){
        inject_ingress=false;
        uint8_t next[4];wl_w32(next,1);
        assert(rr_send(23,next,sizeof(next))); /* UART runs during compression. */
    }
    return wl_encode_frames(p,n,out,capacity,consumed);
}
bool gw_send_idle(void){return true;}
bool gw_peer_set_mcs(const uint8_t *p,uint8_t mcs){(void)p;return mcs<=3;}
bool gw_send(const uint8_t *mac,const void *p,size_t n,uint32_t wait){
    (void)wait;assert(!memcmp(mac,remote,6)&&n<=sizeof(captured));
    memcpy(captured,p,n);captured_size=n;return true;
}
static bool delivery(uint8_t t,const uint8_t *p,size_t n,void *context){
    (void)context;assert(t==23&&n==4&&wl_u32(p)==incoming_count);++incoming_count;return true;
}
static bool remote_delivery(const uint8_t *p,size_t n,void *context){
    (void)context;uint8_t decoded[WL_LOGICAL];assert(n&&p[0]<=1);
    size_t count=p[0]?wl_decompress(p+1,n-1,decoded,sizeof(decoded)):n-1;
    if(!p[0])memcpy(decoded,p+1,count);
    assert(wl_frames_valid(decoded,count));
    for(size_t i=0;i<count;){size_t size=wl_u16(decoded+i+1);
        assert(decoded[i]==23&&size==4&&wl_u32(decoded+i+3)==outgoing_count);
        ++outgoing_count;i+=size+3;}
    return true;
}
static void receive_peer(uint32_t boot,uint64_t nonce,uint64_t echo,wl_slot_t *slot){
    uint8_t packet[RR_PACKET];size_t n=rr_packet_encode(packet,0,false,boot,nonce,echo,&remote_stream,slot);
    assert(rr_receive(remote,packet,n));
}
int main(int argc,char **argv){
    assert(argc==2);memcpy(pair_config,"CRPS",4);memcpy(pair_config+4,remote,6);
    memcpy(pair_config+10,local,6);pair_config[48]=6;
    rr_init(1,local,delivery,NULL);assert(rr_enabled()&&rr_paired()&&!rr_ready());
    rr_poll();assert(rr_packet_valid(captured,captured_size,0));local_nonce=wl_u64(captured+12);
    receive_peer(5,123456,local_nonce,NULL);assert(rr_ready());
    if(!strcmp(argv[1],"ingress_during_encode")){
        assert(rr_send(23,(uint8_t[]){0,0,0,0},4));
        inject_ingress=true;
        for(unsigned i=0;i<2;++i){
            rr_poll();assert(!rr_faulted());
            assert(wl_stream_receive(&remote_stream,wl_u32(captured+28),
                captured+RR_HEADER,wl_u16(captured+37),remote_delivery,NULL));
            receive_peer(5,123456,local_nonce,NULL);test_now+=1000;
        }
        assert(outgoing_count==2&&!rr_queued_bytes()&&!rr_drops());
        return 0;
    }else if(!strcmp(argv[1],"maximum")){
        uint8_t p[WL_PAYLOAD-4];uint32_t seed=987654321;
        for(unsigned i=0;i<sizeof(p);++i){seed=seed*1664525U+1013904223U;p[i]=seed>>24;}
        assert(rr_send(7,p,sizeof(p)));
        assert(!rr_send(7,p,sizeof(p)+1));
        rr_poll();assert(!rr_faulted()&&wl_u16(captured+37)==WL_PAYLOAD);
        return 0;
    }else if(!strcmp(argv[1],"peerfault")){
        uint8_t packet[RR_PACKET];
        size_t n=rr_packet_encode(packet,0,true,5,123456,local_nonce,&remote_stream,NULL);
        packet[7]=rr_fault_code("packet_expired");
        csi_serial_write_u32(packet+n-4,csi_serial_crc32(packet,n-4));
        assert(rr_receive(remote,packet,n));
        assert(rr_faulted()&&!strcmp(rr_failure_reason(),"peer_packet_expired"));
        packet[7]=rr_fault_code("uart_fault");
        csi_serial_write_u32(packet+n-4,csi_serial_crc32(packet,n-4));
        assert(rr_receive(remote,packet,n));
        assert(!strcmp(rr_failure_reason(),"peer_packet_expired"));
    }else if(!strcmp(argv[1],"expiry")){
        assert(rr_send(23,(uint8_t[]){0,0,0,0},4));rr_poll();
        test_now+=RR_LIFETIME_US;rr_poll();assert(rr_faulted()&&!strcmp(rr_failure_reason(),"packet_expired"));
    }else if(!strcmp(argv[1],"recover")){
        assert(rr_send(23,(uint8_t[]){0,0,0,0},4));
        rr_session_active(true);receive_peer(6,999,local_nonce,NULL);
        assert(rr_faulted()&&!rr_ready());
        rr_session_active(false);
        memset(&remote_stream,0,sizeof(remote_stream));
        receive_peer(6,999,local_nonce,NULL);
        assert(!rr_faulted()&&rr_ready()&&!rr_queued_bytes());
        assert(rr_drops()==1); /* historical failure remains observable */
        receive_peer(5,123456,local_nonce,NULL);assert(rr_ready());
    }else if(!strcmp(argv[1],"timeout")){
        rr_session_active(true);test_now+=RR_PEER_TIMEOUT_US;rr_poll();
        assert(rr_faulted()&&!strcmp(rr_failure_reason(),"peer_timeout"));
    }else if(!strcmp(argv[1],"overflow")){
        uint8_t p[1200]={0};unsigned count=0;
        while(rr_send(23,p,sizeof(p)))++count;
        assert(count==54&&rr_faulted()&&!strcmp(rr_failure_reason(),"source_overflow"));
    }else if(!strcmp(argv[1],"delivery")){
        wl_slot_t bad={.size=3,.sequence=0,.data={1,255,255}};
        receive_peer(5,123456,local_nonce,&bad);
        assert(rr_faulted()&&!strcmp(rr_failure_reason(),"delivery_failed"));
    }else{
        for(unsigned i=0;i<1000;++i){
            uint8_t p[4];wl_w32(p,i);assert(rr_send(23,p,sizeof(p)));rr_poll();
            assert(wl_u32(captured+28)!=WL_EMPTY);
            if(i%7==0){test_now+=31000;rr_poll();} /* lost first transmission */
            assert(wl_stream_receive(&remote_stream,wl_u32(captured+28),captured+RR_HEADER,
                wl_u16(captured+37),remote_delivery,NULL));
            assert(wl_stream_receive(&remote_stream,wl_u32(captured+28),captured+RR_HEADER,
                wl_u16(captured+37),remote_delivery,NULL)); /* duplicate */
            receive_peer(5,123456,local_nonce,NULL);test_now+=1000;
        }
        assert(outgoing_count==1000&&rr_retries()>0&&!rr_queued_bytes());
        wl_slot_t slots[4]={0};
        for(unsigned i=0;i<4;++i){slots[i].sequence=i;slots[i].size=8;
            slots[i].data[0]=0;slots[i].data[1]=23;wl_w16(slots[i].data+2,4);wl_w32(slots[i].data+4,i);}
        receive_peer(5,123456,local_nonce,&slots[1]);assert(!incoming_count);
        receive_peer(5,123456,local_nonce,&slots[0]);assert(incoming_count==2);
        receive_peer(5,123456,local_nonce,&slots[3]);receive_peer(5,123456,local_nonce,&slots[2]);
        receive_peer(5,123456,local_nonce,&slots[0]);assert(incoming_count==4);
        receive_peer(4,123456,local_nonce,&slots[0]);assert(incoming_count==4&&!rr_faulted());
        receive_peer(5,123456,local_nonce+1,&slots[0]);assert(incoming_count==4&&!rr_faulted());
        rr_session_active(true);receive_peer(6,999,local_nonce,NULL);
        assert(rr_faulted()&&!strcmp(rr_failure_reason(),"peer_restart")&&rr_peer_changes()==1);
    }
    assert(rr_drops()==1);
    return 0;
}
#define wl_encode_frames encode_with_uart_ingress
#include "reference_relay.c"
""")
    executable = tmp_path / "relay"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(tmp_path),
            "-I",
            str(COMMON / "include"),
            "-I",
            str(COMMON),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    return executable


@pytest.mark.parametrize(
    "scenario",
    [
        "traffic",
        "expiry",
        "timeout",
        "overflow",
        "delivery",
        "peerfault",
        "maximum",
        "recover",
        "ingress_during_encode",
    ],
)
def test_relay_actual_firmware_recovers_or_fails_explicitly(relay_executable, scenario):
    subprocess.run([str(relay_executable), scenario], check=True)


@pytest.mark.parametrize("wrong_gateway", [False, True])
def test_pairing_verifies_both_usb_identities_before_storing_keys(
    monkeypatch, wrong_gateway
):
    import json
    from collections import deque

    import serial

    from fall_detection.radio.acquisition.serial_framing import (
        decode_serial_frame,
        encode_serial_frame,
    )
    from fall_detection.radio.settings import RadioSettings
    from fall_detection.radio.wireless_control import pair_devices

    inventory = RadioSettings.load().inventory
    statuses = [
        dict(role="relay", target="esp32c6", mac="10:bd:a3:9c:ee:94", relay_version=1),
        dict(
            role="gateway", target="esp32c6", mac=inventory.gateway.mac, relay_version=1
        ),
    ]
    if wrong_gateway:
        statuses[1]["mac"] = "02:00:00:00:00:ff"
    monkeypatch.setattr("secrets.token_bytes", lambda size: bytes(range(size)))
    devices = []

    class Usb:
        def __init__(self, status):
            self.status = status
            self.input = deque()
            self.requests = []
            self.closed = False

        @property
        def in_waiting(self):
            return sum(map(len, self.input))

        def read(self, size):
            return self.input.popleft() if self.input else b""

        def write(self, data):
            frame = decode_serial_frame(data[1:-1])
            self.requests.append(frame)
            if frame.type == 5:
                self.input.append(
                    encode_serial_frame(6, json.dumps(self.status).encode())
                )
            elif frame.type == 28:
                self.input.append(encode_serial_frame(29, b"ok"))
            return len(data)

        def close(self):
            self.closed = True

    def factory(*args, **kwargs):
        device = Usb(statuses[len(devices)])
        devices.append(device)
        return device

    monkeypatch.setattr(serial, "Serial", factory)
    if wrong_gateway:
        with pytest.raises(ValueError, match="gateway identity"):
            pair_devices(
                "companion", "gateway", inventory, transmitter_link="espnow_uart"
            )
        assert not any(f.type == 28 for d in devices for f in d.requests)
    else:
        pair_devices("companion", "gateway", inventory, transmitter_link="espnow_uart")
        paired = [[f for f in d.requests if f.type == 28] for d in devices]
        assert all(len(requests) == 1 for requests in paired)
        assert paired[0][0].payload == paired[1][0].payload
        payload = paired[0][0].payload
        assert payload == (
            b"CRPS"
            + bytes.fromhex("10bda39cee94")
            + bytes.fromhex(inventory.gateway.mac.replace(":", ""))
            + bytes(range(32))
            + b"\x06"
        )
    assert all(d.closed for d in devices)


def test_status_rejects_wrong_gateway_before_forwarding_a_transmitter_request(
    monkeypatch,
):
    from fall_detection.radio import wireless_control

    class WrongGateway:
        gateway_status = {
            "role": "gateway",
            "target": "esp32c6",
            "mac": "02:00:00:00:00:ff",
        }
        serial = object()
        closed = False

        def close(self):
            self.closed = True

    bridge = WrongGateway()
    monkeypatch.setattr(wireless_control, "GatewayWirelessPort", lambda *a, **k: bridge)
    monkeypatch.setattr(
        wireless_control,
        "discover_port",
        lambda *a, **k: pytest.fail("a wrong gateway must not forward a request"),
    )
    with pytest.raises(RuntimeError, match="gateway identity"):
        wireless_control.main(
            [
                "status",
                "--transmitter-link",
                "espnow_uart",
                "--gateway-port",
                "wrong",
                "--config",
                str(ROOT / "configs/radio.json"),
            ]
        )
    assert bridge.closed
