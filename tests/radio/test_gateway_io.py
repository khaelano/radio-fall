"""Exercise actual send serialization with a deterministic ESP-IDF callback seam."""

import shutil
import subprocess
from pathlib import Path

import pytest


def _idf_headers(tmp_path):
    include = tmp_path / "include"
    include.mkdir()
    (include / "fake.h").write_text(r"""
#ifndef FAKE_IDF_H
#define FAKE_IDF_H
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#define ESP_OK 0
#define ESP_ERROR_CHECK(x) assert((x)==0)
#define pdTRUE 1
#define pdMS_TO_TICKS(x) (x)
#define WIFI_IF_STA 0
#define WIFI_PHY_MODE_HE20 1
#define WIFI_PHY_MODE_HT20 2
#define WIFI_PHY_RATE_MCS0_LGI 3
#define WIFI_PHY_RATE_MCS1_LGI 4
#define WIFI_PHY_RATE_MCS2_LGI 5
#define WIFI_PHY_RATE_MCS3_LGI 6
typedef int wifi_phy_rate_t;
#define CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ 80
#define ESP_NOW_SEND_SUCCESS 0
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
typedef int esp_err_t;
typedef int esp_now_send_status_t;
typedef struct {int unused;} esp_now_send_info_t;
typedef struct {const uint8_t *src_addr;} esp_now_recv_info_t;
typedef struct {int channel,ifidx;uint8_t peer_addr[6];} esp_now_peer_info_t;
typedef struct {int phymode,rate;bool ersu,dcm;} esp_now_rate_config_t;
typedef void *QueueHandle_t;
typedef void *TaskHandle_t;
typedef struct {unsigned count;} *SemaphoreHandle_t;
static void (*completed)(const esp_now_send_info_t *,esp_now_send_status_t);
static unsigned waits,delays,sends;static bool finish=true;static uint64_t clock_us;
static inline QueueHandle_t xQueueCreate(unsigned n,unsigned size){(void)n;(void)size;return (void *)1;}
static inline int xQueueSend(QueueHandle_t q,const void *p,unsigned t){(void)q;(void)p;(void)t;return 1;}
static inline SemaphoreHandle_t sem_create(unsigned count){SemaphoreHandle_t s=malloc(sizeof(*s));s->count=count;return s;}
static inline SemaphoreHandle_t xSemaphoreCreateMutex(void){return sem_create(1);}
static inline SemaphoreHandle_t xSemaphoreCreateBinary(void){return sem_create(0);}
static inline int xSemaphoreGive(SemaphoreHandle_t s){s->count=1;return 1;}
static inline int xSemaphoreTake(SemaphoreHandle_t s,unsigned timeout){
    if(!s->count&&timeout){++waits;if(finish)completed(NULL,0);}
    if(!s->count)return 0;
    --s->count;return 1;
}
static inline void vTaskDelay(unsigned t){++delays;clock_us+=t*1000;if(finish)completed(NULL,0);}
static inline int64_t esp_timer_get_time(void){return clock_us;}
static inline int esp_now_init(void){return 0;}
static inline int esp_now_register_send_cb(void (*cb)(const esp_now_send_info_t *,int)){completed=cb;return 0;}
static inline int esp_now_register_recv_cb(void (*cb)(const esp_now_recv_info_t *,const uint8_t *,int)){(void)cb;return 0;}
static bool peer_registered=true;
static int last_phy,last_rate,rate_error;static unsigned rate_calls;
static inline bool esp_now_is_peer_exist(const uint8_t *mac){(void)mac;return peer_registered;}
static inline int esp_now_add_peer(const esp_now_peer_info_t *p){(void)p;return 0;}
static inline int esp_now_set_peer_rate_config(const uint8_t *m,const esp_now_rate_config_t *r){(void)m;last_phy=r->phymode;last_rate=r->rate;++rate_calls;return rate_error;}
static inline int esp_now_send(const uint8_t *mac,const void *p,size_t n){(void)mac;(void)p;(void)n;++sends;return 0;}
static inline int usb_serial_jtag_write_bytes(const void *p,size_t n,unsigned t){(void)p;(void)t;return n;}
static inline int usb_serial_jtag_read_bytes(void *p,size_t n,unsigned t){(void)p;(void)n;(void)t;return 0;}
#endif
""")
    for name in (
        "sdkconfig.h",
        "esp_now.h",
        "esp_timer.h",
        "esp_wifi.h",
        "driver/usb_serial_jtag.h",
        "freertos/FreeRTOS.h",
        "freertos/queue.h",
        "freertos/semphr.h",
    ):
        header = include / name
        header.parent.mkdir(exist_ok=True)
        header.write_text('#include "fake.h"\n')
    return include


def test_send_timeout_keeps_sender_owned_until_callback(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    include = _idf_headers(tmp_path)
    root = Path(__file__).resolve().parents[2]
    common = root / "src/firmware/radio/common"
    source = tmp_path / "check.c"
    # Include the real module in one translation unit so callback injection and
    # the driver stubs share state. No replacement of the send implementation.
    source.write_text(
        '#include "'
        + str(common / "gateway_io.c")
        + '"\n'
        + r"""
static unsigned wake_count;static bool woke_idle;
static void wake_observer(void *context){++*(unsigned *)context;woke_idle=gw_send_idle();}
int main(void){
    uint8_t mac[6]={0},data[8]={0};gw_io_init();
    gw_peer(mac,true);assert(last_phy==WIFI_PHY_MODE_HE20&&last_rate==WIFI_PHY_RATE_MCS0_LGI);
    for(unsigned mcs=0;mcs<4;++mcs){assert(gw_peer_set_mcs(mac,mcs));assert(last_phy==WIFI_PHY_MODE_HT20&&last_rate==WIFI_PHY_RATE_MCS0_LGI+(int)mcs);}
    unsigned calls=rate_calls;assert(!gw_peer_set_mcs(mac,4)&&rate_calls==calls);
    peer_registered=false;assert(!gw_peer_set_mcs(mac,1)&&rate_calls==calls);peer_registered=true;
    rate_error=1;assert(!gw_peer_set_mcs(mac,1));rate_error=0;
    assert(gw_send(mac,data,8,5));assert(sends==1);
    finish=false;assert(gw_send(mac,data,8,2)); /* Submission accepted, callback lost. */
    assert(!gw_send_idle());
    unsigned before=sends;assert(!gw_send(mac,data,8,0)&&sends==before);
    completed(NULL,ESP_NOW_SEND_SUCCESS);
    assert(gw_send_idle());
    assert(gw_send(mac,data,8,2)); /* Old completion cannot satisfy this send. */
    before=sends;assert(!gw_send(mac,data,8,0)&&sends==before);
    completed(NULL,1);assert(gw_io_mac_failures()==1);
    finish=true;assert(gw_send(mac,data,8,2));
    uint8_t upload[8]={'C','G','W','Y'};gw_send_stats_t stats;
    assert(gw_measure_sends_begin(clock_us+10000,true));
    assert(gw_send(mac,upload,sizeof(upload),2));
    assert(gw_measure_sends_finish(&stats)&&stats.samples==1&&stats.maximum_us==1000&&!stats.failures);
    assert(gw_measure_sends_begin(clock_us+2000,true));finish=false;
    assert(gw_send(mac,upload,sizeof(upload),1));assert(!gw_measure_sends_finish(&stats));
    clock_us+=3000;completed(NULL,1);
    assert(gw_measure_sends_finish(&stats)&&stats.samples==1&&stats.failures==1&&stats.maximum_failure_us==4000&&stats.late==1);
    gw_io_set_wakeup(wake_observer,&wake_count);finish=false;
    assert(gw_send(mac,data,sizeof(data),0)&&!gw_send_idle()&&!wake_count);
    esp_now_recv_info_t info={.src_addr=mac};received(&info,data,sizeof(data));
    assert(wake_count==1&&!woke_idle&&!gw_send_idle());
    completed(NULL,0);assert(wake_count==2&&woke_idle&&gw_send_idle());
    gw_io_set_wakeup(NULL,NULL);assert(gw_send(mac,data,sizeof(data),0));completed(NULL,0);assert(wake_count==2);
    return 0;
}
"""
    )
    executable = tmp_path / "check"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(include),
            "-I",
            str(common / "include"),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)


@pytest.mark.parametrize("config_version", [7])
def test_receiver_retries_return_notice_until_new_grant(tmp_path, config_version):
    from fall_detection.radio.espnow_config import EspnowTransportConfig
    from fall_detection.radio.profile import RadioInventory, RadioProfile

    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    include = _idf_headers(tmp_path)
    (include / "freertos/task.h").write_text('#include "fake.h"\n')
    fake = include / "fake.h"
    fake.write_text(
        fake.read_text()
        + r"""
#ifndef FAKE_RX_IDF_H
#define FAKE_RX_IDF_H
typedef int portMUX_TYPE;
typedef int wifi_second_chan_t;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
#define WIFI_SECOND_CHAN_NONE 0
#define pdPASS 1
static inline int xQueueReset(QueueHandle_t q){(void)q;return 1;}
static inline int xQueueReceive(QueueHandle_t q,void *p,unsigned t){(void)q;(void)p;(void)t;return 0;}
static inline int xQueuePeek(QueueHandle_t q,void *p,unsigned t){(void)q;(void)p;(void)t;return 0;}
static inline int xTaskCreate(void (*f)(void *),const char *n,int stack,void *a,int priority,void *task){(void)f;(void)n;(void)stack;(void)a;(void)priority;(void)task;return 1;}
static inline int esp_wifi_set_channel(uint8_t c,int second){(void)c;(void)second;return 0;}
static inline int esp_wifi_get_channel(uint8_t *c,int *second){*c=44;*second=0;return 0;}
#endif
"""
    )
    root = Path(__file__).resolve().parents[2]
    common = root / "src/firmware/radio/common"
    receiver = root / "src/firmware/radio/receiver/main"
    source = tmp_path / "receiver.c"
    source.write_text(
        '#include "'
        + str(receiver / "gateway_transport.c")
        + '"\n'
        + r"""
static bool accept_sends;
bool gw_send(const uint8_t *m,const void *p,size_t n,uint32_t t){(void)m;(void)p;(void)n;(void)t;++sends;return accept_sends;}
bool gw_send_idle(void){return true;}
bool gw_measure_sends_begin(uint64_t deadline,bool enabled){(void)deadline;(void)enabled;return true;}
bool gw_measure_sends_finish(gw_send_stats_t *s){memset(s,0,sizeof(*s));return true;}
void gw_peer(const uint8_t *m,bool he){(void)m;(void)he;}
bool gw_peer_set_mcs(const uint8_t *m,uint8_t rate){(void)m;return rate<=3;}
uint32_t gw_io_drops(void){return 0;}
uint32_t gw_io_mac_failures(void){return 0;}
QueueHandle_t gw_incoming(void){return (void *)1;}
int main(int argc,char **argv){
    (void)argc;uint8_t wire[108];
    for(unsigned i=0;i<108;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);wire[i]=b;}
    gw_config_t c;assert(gw_config_decode(wire,108,&c));
    csi_radio_profile_t p={.channel=44,.nominal_rate_hz=80};
    memcpy(p.fingerprint,wire+68,16);memcpy(p.transmitter_mac,wire+38,6);
    gw_receiver_init(&p,wire+44,21);
    assert(sizeof(batches)/sizeof(batches[0])==8);
    assert(configured==false);
    gw_schedule_t s={.id=5,.owner=0,.active=true,.start=100000,.end=150000};
    csi_sensing_packet_t sensing={.sequence=1,.tx_t1_us=100000};
    gw_message_t m={.size=GW_SENSING_SIZE,.received=200000};memcpy(m.source,p.transmitter_mac,6);
    gw_sensing_encode(m.data,&sensing,&c,11,&s);observe(&m);assert(configured);
    uint8_t record[579]={0};
    for(unsigned i=0;i<16;++i)assert(gw_queue_push(&records,record,sizeof(record),100000));
    for(unsigned i=0;i<8;++i){batch_t *b=build(16-2*i);assert(b&&b->count==2&&b->length<=1400);}
    for(unsigned i=0;i<8;++i){batches[i].attempts=1;batches[i].sent=10000;}
    assert(!next_burst_batch(120000,16,255)); /* Poll before retrying accepted data. */
    assert(!build(16)); /* All eight sender-owned byte arrays are immutable. */
    assert(gw_queue_count(&records)==16);
    assert(gw_upload_exit(&config,120000,150000,110000,true,false,true)==GW_EXIT_COMPLETE);
    assert(gw_queue_count(&records)==16&&batches[0].used); /* Return is not acceptance. */
    gw_message_t ack={.size=GW_ACK_SIZE};memcpy(ack.source,wire+32,6);memcpy(ack.data,"CGAK",4);
    csi_clock_write_u64(ack.data+4,123);csi_clock_write_u32(ack.data+12,11);
    csi_clock_write_u32(ack.data+16,22);csi_clock_write_u32(ack.data+20,batches[0].id);
    memcpy(ack.data+24,wire+44,6);gw_crc(ack.data,GW_ACK_SIZE);observe(&ack);
    assert(gw_queue_count(&records)==16&&batches[0].used); /* Stale boot ACK rejected. */
    csi_clock_write_u32(ack.data+16,21);gw_crc(ack.data,GW_ACK_SIZE);observe(&ack);
    assert(gw_queue_count(&records)==14&&!batches[0].used&&records.acknowledged==2);
    observe(&ack);assert(gw_queue_count(&records)==14&&records.acknowledged==2);
    assert(gw_queue_push(&records,record,sizeof(record),110000));
    batch_t *fresh=next_burst_batch(120000,1,255);
    assert(fresh==&batches[0]&&fresh->count==1&&!fresh->attempts&&fresh->length<=1400);
    assert(next_burst_batch(120000,1,255)==fresh); /* Reuse its immutable pending bytes. */
    fresh->attempts=config.retries+1;
    assert(!next_burst_batch(120000,16,255));
    assert(next_burst_batch(120000,16,0)==&batches[1]); /* Bounded retry after poll. */
    memset(batches,0,sizeof(batches));gw_queue_reset(&records,64);
    for(unsigned i=0;i<16;++i)assert(gw_queue_push(&records,record,sizeof(record),110000));
    for(unsigned i=0;i<8;++i){batch_t *b=build(16-2*i);assert(b);b->attempts=1;}
    accept_sends=true;assert(poll_bitmap(255,120000));
    gw_message_t bitmap={.size=GW_BITMAP_SIZE};memcpy(bitmap.source,wire+32,6);
    memcpy(bitmap.data,bitmap_request,GW_BITMAP_SIZE);memcpy(bitmap.data,"CGPB",4);gw_crc(bitmap.data,GW_BITMAP_SIZE);
    observe(&bitmap);assert(gw_queue_count(&records)==16&&!bitmap_pending); /* No host ACKs cached. */
    bitmap.data[6]=5;gw_crc(bitmap.data,GW_BITMAP_SIZE);
    assert(poll_bitmap(255,125000));observe(&bitmap); /* Previous request token is stale. */
    assert(gw_queue_count(&records)==16&&bitmap_pending);
    memcpy(bitmap.data,bitmap_request,GW_BITMAP_SIZE);memcpy(bitmap.data,"CGPB",4);bitmap.data[6]=5;gw_crc(bitmap.data,GW_BITMAP_SIZE);
    observe(&bitmap);assert(gw_queue_count(&records)==12&&!batches[0].used&&!batches[2].used&&batches[1].used);
    observe(&bitmap);assert(gw_queue_count(&records)==12); /* Duplicate reply is idempotent. */
    accept_sends=false;
    memset(batches,0,sizeof(batches));gw_queue_reset(&records,64);
    state=GW_CONFIRM;handled=transition_grant=5;last_status=0;
    sensing.tx_t1_us+=12500;m.received+=12500;
    gw_sensing_encode(m.data,&sensing,&c,11,&s);observe(&m);
    assert(return_notice&&notice_grant==5&&last_status==0&&state==GW_CAPTURE);
    accept_sends=true;clock_us=250000;status();assert(last_status==250000&&return_notice);
    sensing.tx_t1_us+=12500;m.received+=12500;
    gw_sensing_encode(m.data,&sensing,&c,11,&s);observe(&m);assert(return_notice);
    s.id=6;s.start=200000;s.end=250000;
    gw_sensing_encode(m.data,&sensing,&c,11,&s);observe(&m);assert(!return_notice);
    /* An expired grant which never departed also needs a reliable notice. */
    accept_sends=false;s.end=100000;sensing.tx_t1_us+=12500;
    gw_sensing_encode(m.data,&sensing,&c,11,&s);observe(&m);
    assert(return_notice&&notice_grant==6&&handled==6&&last_status==250000);
    /* A new run cannot relabel the previous run's channel interval. */
    state=GW_CAPTURE;departed=100000;returned=150000;transition_grant=5;
    c.run=124;csi_clock_write_u64(c.wire+8,124);gw_crc(c.wire,GW_CONFIG_SIZE);
    s.id=0;s.active=false;s.start=s.end=0;
    gw_sensing_encode(m.data,&sensing,&c,11,&s);observe(&m);
    assert(config.run==124&&transition_grant==0&&!departed&&!returned&&!return_notice);
    return 0;
}
"""
    )
    # stdio is a harness dependency, not an addition to the firmware module.
    source.write_text("#include <stdio.h>\n" + source.read_text())
    inventory = RadioInventory.from_mapping(
        {
            "schema_version": 2,
            "transmitter": {
                "id": "tx",
                "role": "transmitter",
                "target": "esp32c5",
                "mac": "02:00:00:00:00:01",
            },
            "receivers": [
                {
                    "id": "rx",
                    "role": "receiver",
                    "target": "esp32c5",
                    "mac": "02:00:00:00:00:02",
                }
            ],
            "gateway": {
                "id": "gw",
                "role": "gateway",
                "target": "esp32c6",
                "mac": "02:00:00:00:00:03",
            },
        }
    )
    profile = RadioProfile.from_mapping(
        {
            "schema_version": 1,
            "profile_id": "test",
            "country_code": "ID",
            "band": "5ghz",
            "channel": 44,
            "bandwidth_mhz": 20,
            "nominal_rate_hz": 80,
        }
    )
    config = EspnowTransportConfig(
        schema_version=config_version,
        maximum_retries=2 if config_version == 4 else 1,
        outstanding_batches=8,
        early_return_idle_ms=5,
        batch_acknowledgements=True,
    ).encode(123, inventory, profile)
    executable = tmp_path / "receiver"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(include),
            "-I",
            str(common / "include"),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable), config.hex()], check=True)


def test_sized_control_queue_retains_depth_and_rejects_oversize(tmp_path):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    inc = _idf_headers(tmp_path)
    p = inc / "fake.h"
    s = p.read_text().replace(
        "static inline QueueHandle_t xQueueCreate(unsigned n,unsigned size){(void)n;(void)size;return (void *)1;}",
        "static unsigned depth,item_size;\nstatic inline QueueHandle_t xQueueCreate(unsigned n,unsigned size){depth=n;item_size=size;return (void *)1;}",
    )
    p.write_text(s)
    common = Path(__file__).resolve().parents[2] / "src/firmware/radio/common"
    source = tmp_path / "sized.c"
    source.write_text(
        '#include "'
        + str(common / "gateway_io.c")
        + '"\n'
        + r"""
int main(void){
 gw_io_init_sized(GW_SENSING_SIZE);assert(depth==32&&item_size==offsetof(gw_message_t,data)+180);
 uint8_t mac[6]={0},data[181]={0};esp_now_recv_info_t info={.src_addr=mac};
 received(&info,data,180);assert(!gw_io_drops());received(&info,data,181);assert(gw_io_drops()==1);
 gw_io_init_sized(GW_SENSING_SIZE);assert(depth==32);return 0;
}
"""
    )
    executable = tmp_path / "sized"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-Wall",
            "-Werror",
            "-I",
            str(inc),
            "-I",
            str(common / "include"),
            str(source),
            "-o",
            str(executable),
        ],
        check=True,
    )
    subprocess.run([str(executable)], check=True)
