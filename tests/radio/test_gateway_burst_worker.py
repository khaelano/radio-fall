"""Compare actual receiver-worker burst progress with deterministic radio timing."""

from pathlib import Path
import shutil, subprocess
import pytest
from test_gateway_io import _idf_headers
from test_gateway_tuning import identities
from fall_detection.radio.espnow_config import EspnowTransportConfig


@pytest.mark.parametrize(
    "ackless,radio_delay_us", [(False, 1800), (True, 1800), (True, 88000), (True, 0)]
)
def test_event_worker_clears_more_records_without_extending_slot(
    tmp_path, ackless, radio_delay_us
):
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("C compiler unavailable")
    inc = _idf_headers(tmp_path)
    fake = inc / "fake.h"
    s = fake.read_text()
    s = s.replace(
        "static inline void vTaskDelay(unsigned t){++delays;clock_us+=t*1000;if(finish)completed(NULL,0);}",
        "static void test_delay(unsigned t);\nstatic inline void vTaskDelay(unsigned t){++delays;test_delay(t);}",
    )
    s = s.replace(
        "static inline QueueHandle_t xQueueCreate(unsigned n,unsigned size){(void)n;(void)size;return (void *)1;}",
        "static unsigned queue_id=2;\nstatic inline QueueHandle_t xQueueCreate(unsigned n,unsigned size){(void)n;(void)size;return (void *)(uintptr_t)queue_id++;}",
    )
    s += r"""
#ifndef BURST_RX_FAKE_H
#define BURST_RX_FAKE_H
#include <setjmp.h>
#include <stdio.h>
typedef void *TaskHandle_t;
typedef int wifi_second_chan_t;
#define WIFI_SECOND_CHAN_NONE 0
#define pdPASS 1
static unsigned channel=44;
static bool pending_ack,busy_radio;static uint64_t completes_at;static unsigned notifications;
static int receive_pending(void *q,void *p);
static unsigned notify_wait(unsigned clear,unsigned ticks);
static inline int xQueueReset(QueueHandle_t q){(void)q;return 1;}
static inline int xQueueReceive(QueueHandle_t q,void *p,unsigned t){(void)t;return receive_pending(q,p);}
static inline int xQueuePeek(QueueHandle_t q,void *p,unsigned t){(void)q;(void)p;(void)t;return 0;}
static inline int xTaskCreate(void (*f)(void *),const char *n,int stack,void *a,int priority,void *task){(void)f;(void)n;(void)stack;(void)a;(void)priority;if(task)*(TaskHandle_t *)task=(void *)9;return 1;}
static inline int esp_wifi_set_channel(uint8_t c,int second){(void)second;channel=c;clock_us+=5000;return 0;}
static inline int esp_wifi_get_channel(uint8_t *c,int *second){*c=channel;*second=0;return 0;}
static inline unsigned ulTaskNotifyTake(unsigned clear,unsigned ticks){return notify_wait(clear,ticks);}
static inline int xTaskNotifyGive(TaskHandle_t h){(void)h;++notifications;return 1;}
#endif
"""
    fake.write_text(s)
    for name in ["sdkconfig.h", "freertos/task.h"]:
        (inc / name).write_text('#include "fake.h"\n')
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "worker.c"
    source.write_text(
        '#include "'
        + str(root / "src/firmware/radio/receiver/main/gateway_transport.c")
        + '"\n'
        + r"""
static jmp_buf stopped;static gw_message_t reply;static unsigned sent_records;static uint64_t radio_delay;
static void (*notifier)(void *);static void *notifier_ctx;
static void service(void){
 if(busy_radio&&clock_us>=completes_at){busy_radio=false;pending_ack=config.application_ack;if(notifier)notifier(notifier_ctx);}
}
static void test_delay(unsigned ticks){
 if(state==GW_CONFIRM&&channel==44)longjmp(stopped,1);
 clock_us+=(uint64_t)ticks*1000;service();
}
static unsigned notify_wait(unsigned clear,unsigned ticks){
 if(!notifications){uint64_t until=clock_us+(uint64_t)ticks*1000;if(busy_radio&&completes_at<until)until=completes_at;clock_us=until;service();}
 unsigned n=notifications;if(clear)notifications=0;return n;
}
static int receive_pending(void *q,void *p){if(q!=(void *)1||!pending_ack)return 0;memcpy(p,&reply,sizeof(reply));pending_ack=false;return 1;}
void gw_io_set_wakeup(void (*f)(void *),void *p){notifier=f;notifier_ctx=p;}
bool gw_send_idle(void){return !busy_radio;}
bool gw_measure_sends_begin(uint64_t d,bool on){(void)d;(void)on;return true;}
bool gw_measure_sends_finish(gw_send_stats_t *s){memset(s,0,sizeof(*s));return true;}
void gw_peer(const uint8_t *m,bool he){(void)m;(void)he;}
bool gw_peer_set_mcs(const uint8_t *m,uint8_t rate){(void)m;return rate<=3;}
uint32_t gw_io_drops(void){return 0;}
uint32_t gw_io_mac_failures(void){return 0;}
QueueHandle_t gw_incoming(void){return (void *)1;}
bool gw_send(const uint8_t *m,const void *bytes,size_t n,uint32_t wait_ms){
 (void)m;const uint8_t *p=bytes;if(busy_radio)return false;
 if(n<4||memcmp(p,"CGWY",4)){assert(config.application_ack|| (memcmp(p,"CGPL",4)&&memcmp(p,"CGPQ",4)));return true;}
 assert(gw_envelope_valid(p,n));unsigned count=csi_clock_read_u16(p+56);sent_records+=count;
 memset(&reply,0,sizeof(reply));reply.size=GW_ACK_SIZE;memcpy(reply.source,config.wire+32,6);memcpy(reply.data,"CGAK",4);
 csi_clock_write_u64(reply.data+4,config.run);csi_clock_write_u32(reply.data+12,txboot);csi_clock_write_u32(reply.data+16,boot);
 csi_clock_write_u32(reply.data+20,csi_clock_read_u32(p+24));memcpy(reply.data+24,mac,6);gw_crc(reply.data,reply.size);
 busy_radio=true;completes_at=radio_delay?clock_us+radio_delay:UINT64_MAX;uint64_t until=clock_us+(uint64_t)wait_ms*1000;
 while(busy_radio&&clock_us<until){clock_us+=1000;service();}
 return true;
}
int main(int argc,char **argv){
 (void)argc;radio_delay=strtoull(argv[2],NULL,10);uint8_t raw[108];for(unsigned i=0;i<108;++i){unsigned b;sscanf(argv[1]+2*i,"%2x",&b);raw[i]=b;}
 csi_radio_profile_t p={.channel=44,.nominal_rate_hz=80};memcpy(p.transmitter_mac,raw+38,6);
 gw_receiver_init(&p,raw+44,21);assert(gw_config_decode(raw,108,&config));configured=true;txboot=11;gw_queue_reset(&records,config.capacity);
 state=GW_CAPTURE;slot=0;owner=0;grant=1;handled=0;start=100000;end=150000;t1=100000;clock_us=107000;clock_updated=clock_us;uncertainty=250;offset=0;last_sensing=clock_us;
 uint8_t record[577]={0};for(unsigned i=0;i<32;++i)assert(gw_queue_push(&records,record,sizeof(record),clock_us));
 if(!setjmp(stopped))worker(NULL);
 assert(state==GW_CONFIRM&&channel==44&&clock_us<150000);assert(sent_records<=config.allowance);
 if(!config.application_ack){
    assert(!records.acknowledged&&!poll_eligible());
    if(radio_delay==1800)assert(records.sent_unconfirmed>0);
    else assert(unconfirmed_send&&busy_radio&&unconfirmed_send->used);
    /* A stuck/late send must keep its bytes, even across the return deadline.
     * Retire failed sends too, without claiming successful delivery. */
    unsigned expired_before=records.expired;
    busy_radio=false;retire_unconfirmed_send();assert(records.expired==expired_before);
    batch_t *b=build(2);assert(b);b->attempts=1;unconfirmed_send=b;busy_radio=true;
    unsigned owned=gw_queue_count(&records);uint8_t saved[1400];memcpy(saved,b->data,b->length);
    retire_unconfirmed_send();assert(b->used&&gw_queue_count(&records)==owned&&!memcmp(saved,b->data,b->length));
    assert(!gw_batch_ready(&config,1,clock_us,b->oldest,clock_us));
    busy_radio=false;retire_unconfirmed_send();assert(!b->used&&!unconfirmed_send&&gw_queue_count(&records)==owned-2);
    assert(!records.acknowledged&&records.expired==expired_before);
 }
 printf("%u %llu\n",sent_records,(unsigned long long)clock_us);return 0;
}
"""
    )
    inv, profile = identities()
    raw = EspnowTransportConfig(
        schema_version=5 if ackless else 4,
        maximum_age_ms=750,
        maximum_retries=0 if ackless else 2,
        ack_timeout_ms=150,
        application_acknowledgements=not ackless,
    ).encode(123, inv, profile)
    results = []
    for fast in [0, 1]:
        exe = tmp_path / ("worker" + str(fast))
        subprocess.run(
            [
                cc,
                "-std=c11",
                "-Wall",
                "-Werror",
                "-DCONFIG_CSI_GATEWAY_EVENT_UPLOAD=" + str(fast),
                "-I",
                str(inc),
                "-I",
                str(root / "src/firmware/radio/common/include"),
                str(source),
                "-o",
                str(exe),
            ],
            check=True,
        )
        results.append(
            tuple(
                map(
                    int,
                    subprocess.check_output(
                        [str(exe), raw.hex(), str(radio_delay_us)], text=True
                    ).split(),
                )
            )
        )
    if radio_delay_us == 1800:
        assert results[1][0] > results[0][0], results
    else:
        assert results[0][0] == results[1][0] == 2, results
