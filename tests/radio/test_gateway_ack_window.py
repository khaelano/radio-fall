"""Exercise gateway acceptance caching while immediate ACK forwarding is limited."""

from pathlib import Path
import shutil, subprocess
import pytest
from test_gateway_io import _idf_headers
from test_gateway_tuning import identities
from fall_detection.radio.espnow_config import EspnowTransportConfig


@pytest.mark.parametrize("ackless", [False, True])
@pytest.mark.parametrize("ack_age_ms", [5, 50, None])
def test_gateway_aged_ack_stays_cached_for_poll(tmp_path, ack_age_ms, ackless):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    inc = _idf_headers(tmp_path)
    sdkconfig = '#include "fake.h"\n#define CONFIG_IDF_TARGET_ESP32C6 1\n'
    if ack_age_ms is not None:
        sdkconfig += f"#define CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS {ack_age_ms}\n"
    (inc / "sdkconfig.h").write_text(sdkconfig)
    with (inc / "fake.h").open("a") as f:
        f.write(r"""
#ifndef GW_APP_FAKE_H
#define GW_APP_FAKE_H
#include <stdio.h>
#define MACSTR "%02x:%02x:%02x:%02x:%02x:%02x"
#define MAC2STR(m) (m)[0],(m)[1],(m)[2],(m)[3],(m)[4],(m)[5]
#define WIFI_BW20 0
#define WIFI_PS_NONE 0
#define WIFI_MODE_STA 0
#define WIFI_PROTOCOL_11B 1
#define WIFI_PROTOCOL_11G 2
#define WIFI_PROTOCOL_11N 4
#define portMAX_DELAY 1000
typedef struct {int unused;} wifi_init_config_t;
typedef struct {int tx_buffer_size,rx_buffer_size;} usb_serial_jtag_driver_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() ((wifi_init_config_t){0})
static inline int csi_board_init(void){return 0;}
static inline int nvs_flash_init(void){return 0;}
static inline int esp_read_mac(uint8_t *m,int type){(void)m;(void)type;return 0;}
static inline uint32_t esp_random(void){return 1;}
static inline void esp_restart(void){}
static inline uint32_t esp_get_free_heap_size(void){return 50000;}
static inline uint32_t esp_get_minimum_free_heap_size(void){return 45000;}
static inline int usb_serial_jtag_driver_install(const usb_serial_jtag_driver_config_t *c){(void)c;return 0;}
static inline int esp_netif_init(void){return 0;}
static inline int esp_event_loop_create_default(void){return 0;}
static inline int esp_wifi_init(const wifi_init_config_t *c){(void)c;return 0;}
#define WIFI_STORAGE_RAM 0
#define ESP_MAC_WIFI_STA 0
static inline int esp_wifi_set_storage(int x){(void)x;return 0;}
static inline int esp_wifi_set_mode(int x){(void)x;return 0;}
static inline int esp_wifi_start(void){return 0;}
static inline int esp_wifi_set_protocol(int x,int y){(void)x;(void)y;return 0;}
static inline int esp_wifi_set_bandwidth(int x,int y){(void)x;(void)y;return 0;}
static inline int esp_wifi_set_country_code(const char *s,bool x){(void)s;(void)x;return 0;}
static inline int esp_wifi_set_channel(int x,int y){(void)x;(void)y;return 0;}
#define WIFI_SECOND_CHAN_NONE 0
static inline int esp_wifi_set_ps(int x){(void)x;return 0;}
static inline unsigned uxQueueMessagesWaiting(void *q){(void)q;return 0;}
static inline int xQueueReceive(void *q,void *p,unsigned t){(void)q;(void)p;(void)t;return 0;}
static inline int xTaskCreate(void (*f)(void *),const char *n,int s,void *a,int p,void *h){(void)f;(void)n;(void)s;(void)a;(void)p;(void)h;return 1;}
#define pdPASS 1
#endif
""")
    for n in [
        "radio_board.h",
        "esp_event.h",
        "esp_netif.h",
        "esp_mac.h",
        "esp_random.h",
        "esp_system.h",
        "nvs_flash.h",
        "freertos/task.h",
    ]:
        (inc / n).write_text('#include "fake.h"\n')
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "ack.c"
    source.write_text(
        '#include "'
        + str(root / "src/firmware/radio/gateway/main/app_main.c")
        + '"\n'
        + r"""
static bool sender_idle=true,usb_accept=true;static uint8_t last_sent[1400];static unsigned last_size;
void wl_init(uint8_t r,const uint8_t m[6],wl_emit_t e,void *c){(void)r;(void)m;(void)e;(void)c;}
bool wl_pair(const uint8_t *p,size_t n){(void)p;(void)n;return false;}
bool wl_send(uint8_t t,const uint8_t *p,size_t n){(void)t;(void)p;(void)n;return false;}
bool wl_paired(void){return false;}bool wl_ready(void){return false;}bool wl_faulted(void){return false;}
const char *wl_failure_reason(void){return "disabled";}
const char *wl_debug(void){return "disabled";}
uint32_t wl_drops(void){return 0;}uint32_t wl_peer_changes(void){return 0;}
void wl_session_active(bool a){(void)a;}
void wl_host_failure(void){}
void wl_expect_peer_restart(void){}
void gw_io_init(void){}
QueueHandle_t gw_incoming(void){return (void *)1;}
uint32_t gw_io_drops(void){return 0;}
uint32_t gw_io_mac_failures(void){return 0;}
bool gw_send_idle(void){return sender_idle;}
void gw_peer(const uint8_t *m,bool h){(void)m;(void)h;}
bool gw_peer_set_mcs(const uint8_t *m,uint8_t rate){(void)m;return rate<=3;}
bool gw_send(const uint8_t *m,const void *p,size_t n,uint32_t w){(void)m;(void)w;if(!sender_idle)return false;++sends;memcpy(last_sent,p,n);last_size=n;return true;}
bool gw_usb_write(uint8_t t,const uint8_t *p,size_t n){(void)t;(void)p;(void)n;return usb_accept;}
bool gw_usb_read(uint8_t *t,uint8_t *p,size_t *n){(void)t;(void)p;(void)n;return false;}
int main(int argc,char **argv){
 usb_accept=false;relay_used=4;assert(relay_flush());
 configured=true;relay_used=4;assert(!relay_flush());
 configured=false;usb_accept=true;
 (void)argc;uint8_t raw[108];for(unsigned i=0;i<108;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);raw[i]=b;}
 assert(gw_config_decode(raw,108,&configuration));configured=true;transmitter_boot=11;last_rx_boot[0]=21;
 gw_message_t m={.size=GW_ACK_SIZE};m.source[0]=GW_ACK;memcpy(m.data,"CGAK",4);
 csi_clock_write_u64(m.data+4,123);csi_clock_write_u32(m.data+12,11);csi_clock_write_u32(m.data+16,21);
 csi_clock_write_u32(m.data+20,99);memcpy(m.data+24,raw+44,6);gw_crc(m.data,m.size);
 if(!configuration.application_ack){
    command(&m);assert(!host_acks&&!ack_submissions&&!sends&&!cache_next);
    memcpy(m.source,raw+44,6);memcpy(m.data,"CGPL",4);gw_crc(m.data,m.size);radio(&m);
    assert(!polls&&!sends);
    gw_message_t data={.size=45};memcpy(data.source,raw+44,6);memcpy(data.data,"CGWY",4);data.data[4]=1;
    csi_clock_write_u16(data.data+6,40);csi_clock_write_u64(data.data+8,123);csi_clock_write_u32(data.data+16,11);
    csi_clock_write_u32(data.data+20,21);memcpy(data.data+28,raw+44,6);csi_clock_write_u16(data.data+34,1);gw_crc(data.data,data.size);
    radio(&data);assert(received==1&&forwarded==1&&!sends);return 0;
 }
 last_seen[0]=1000;clock_us=1000+CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS*1000;command(&m);assert(!sends&&ack_skipped_age==1);
 assert(!memcmp(cache[0],m.data,GW_ACK_SIZE)); /* Retain real host acceptance. */
 gw_message_t poll={.size=GW_ACK_SIZE,.received=clock_us};memcpy(poll.source,raw+44,6);memcpy(poll.data,m.data,GW_ACK_SIZE);memcpy(poll.data,"CGPL",4);gw_crc(poll.data,poll.size);
 radio(&poll);assert(sends==1&&last_size==GW_ACK_SIZE&&!memcmp(last_sent,m.data,GW_ACK_SIZE));
 last_seen[0]=clock_us;clock_us+=4000;command(&m);assert(sends==2);
 last_seen[0]=clock_us;sender_idle=false;command(&m);assert(sends==2&&ack_skipped_busy==1);
 csi_clock_write_u64(m.data+4,124);gw_crc(m.data,m.size);unsigned saved=host_acks;command(&m);assert(host_acks==saved);
 return 0;
}
"""
    )
    exe = tmp_path / "ack"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(inc),
            "-I",
            str(root / "src/firmware/radio/common/include"),
            str(source),
            str(root / "src/firmware/radio/common/reference_relay.c"),
            "-o",
            str(exe),
        ],
        check=True,
    )
    inv, profile = identities()
    subprocess.run(
        [
            str(exe),
            EspnowTransportConfig(
                schema_version=5 if ackless else 4,
                maximum_retries=0 if ackless else 2,
                application_acknowledgements=not ackless,
            )
            .encode(123, inv, profile)
            .hex(),
        ],
        check=True,
    )
