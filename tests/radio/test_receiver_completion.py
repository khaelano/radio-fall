"""Execute the real receiver worker across an asynchronous send completion."""

from pathlib import Path
import shutil
import subprocess

import pytest

from test_gateway_io import _idf_headers


@pytest.mark.parametrize("completion_status", [0, 1])
def test_receiver_retires_previous_batch_before_starting_next_send(
    tmp_path, completion_status
):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler unavailable")
    include = _idf_headers(tmp_path)
    (include / "freertos/task.h").write_text('#include "fake.h"\n')
    (include / "sdkconfig.h").write_text(
        '#include "fake.h"\n#define CONFIG_CSI_GATEWAY_EVENT_UPLOAD 1\n'
    )
    root = Path(__file__).resolve().parents[2]
    common = root / "src/firmware/radio/common"
    source = tmp_path / "receiver.c"
    source.write_text(
        r"""
#include "fake.h"
#include <setjmp.h>
static jmp_buf end_iteration;
static bool inject_completion;
static uint8_t tuned_channel;
static int test_receive(void *queue,void *data,unsigned timeout){
 (void)data;(void)timeout;
 if(queue==(void *)1&&inject_completion){inject_completion=false;completed(NULL,COMPLETION_STATUS);}
 return 0;
}
static int xQueuePeek(void *q,void *p,unsigned t){(void)q;(void)p;(void)t;return 0;}
static int xQueueReset(void *q){(void)q;return 1;}
static int xTaskCreate(void (*f)(void *),const char *n,unsigned z,void *a,int p,void *h){
 (void)f;(void)n;(void)z;(void)a;(void)p;(void)h;return 1;
}
#define pdPASS 1
static void xTaskNotifyGive(void *t){(void)t;}
static unsigned ulTaskNotifyTake(int clear,unsigned ticks){(void)clear;(void)ticks;longjmp(end_iteration,1);return 0;}
static int esp_wifi_set_channel(uint8_t c,int s){(void)s;tuned_channel=c;return 0;}
static int esp_wifi_get_channel(uint8_t *c,int *s){*c=tuned_channel;*s=0;return 0;}
typedef int wifi_second_chan_t;
#define WIFI_SECOND_CHAN_NONE 0
#define xQueueReceive test_receive
"""
        + f'\n#include "{common / "gateway_io.c"}"\n#include "{root / "src/firmware/radio/receiver/main/gateway_transport.c"}"\n'
        + r"""
int main(void){
 gw_io_init();finish=false;clock_us=100000;
 static csi_radio_profile_t radio={.channel=44};profile=&radio;
 configured=true;slot=0;owner=0;state=GW_CAPTURE;grant=1;handled=0;
 start=90000;end=200000;t1=100000;last_sensing=100000;
 clock_updated=100000;uncertainty=0;offset=0;
 config=(gw_config_t){.run=123,.rate=120,.channel=11,.slot_ms=125,
 .start_ms=5,.return_ms=10,.send_guard_ms=10,.age_ms=750,
 .outstanding=4,.allowance=64,.capacity=96,.application_ack=false};
 config.wire[4]=7;
 captures=(void *)2;queue_events=(void *)3;
 records.capacity=96;
 records.slots[0]=(gw_record_slot_t){.state=2,.batch=41,.captured=1,.length=1};
 records.slots[1]=(gw_record_slot_t){.state=1,.captured=90000,.length=1,.data={42}};
 batches[0]=(batch_t){.used=true,.id=41,.oldest=1,.attempts=1,.count=1,.length=8};
 unconfirmed_send=&batches[0];batch_id=42;
 assert(gw_send(config.wire+32,batches[0].data,8,0)&&!gw_send_idle());
 /* Completion arrives AFTER retire_unconfirmed_send at loop entry but BEFORE
  * the upload branch checks sender readiness. This is the real callback race. */
 inject_completion=true;
 if(!setjmp(end_iteration))worker(NULL);
 assert(records.sent_unconfirmed==1); /* the old record must be released now */
 assert(records.slots[0].state==0);
 assert(records.expired==0);
 assert(unconfirmed_send&&unconfirmed_send->id==42&&!gw_send_idle());
 assert(gw_queue_count(&records)==1); /* current send still owns its bytes */
 completed(NULL,ESP_NOW_SEND_SUCCESS);retire_unconfirmed_send();
 assert(!unconfirmed_send&&gw_queue_count(&records)==0);
 assert(records.sent_unconfirmed==2&&records.expired==0);
 return 0;
}
"""
    )
    executable = tmp_path / "receiver"
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Werror",
            f"-DCOMPLETION_STATUS={completion_status}",
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
