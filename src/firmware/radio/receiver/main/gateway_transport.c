#include "gateway_transport.h"
#include "sdkconfig.h"
#include "gateway_io.h"
#include "gateway_queue.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/task.h"
#ifndef CONFIG_CSI_GATEWAY_EVENT_UPLOAD
#define CONFIG_CSI_GATEWAY_EVENT_UPLOAD 0
#endif
static uint32_t send_wait(uint32_t milliseconds)
{return CONFIG_CSI_GATEWAY_EVENT_UPLOAD?0:milliseconds;}
static void upload_pause(void)
{
#if CONFIG_CSI_GATEWAY_EVENT_UPLOAD
    ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(1));
#else
    vTaskDelay(1);
#endif
}
#if CONFIG_CSI_GATEWAY_EVENT_UPLOAD
static void notify_upload_worker(void *context){xTaskNotifyGive((TaskHandle_t)context);}
#endif
#include <limits.h>

typedef struct {uint16_t length;uint64_t captured;uint8_t data[699];} capture_t;
typedef struct {bool used;uint32_t id;uint64_t oldest,sent,polled;uint8_t attempts,count;uint16_t length;uint8_t data[1400];} batch_t;
static const csi_radio_profile_t *profile;
static uint8_t mac[6];static uint32_t boot;
static gw_config_t config;
static volatile bool configured;
static QueueHandle_t captures;
static gw_record_queue_t records;
static batch_t batches[GW_MAX_OUTSTANDING];
/* Sender-owned bytes stay immutable until the MAC callback releases busy. */
static batch_t *unconfirmed_send;
static uint32_t batch_id,grant,handled,transition_grant,txboot,built,send_errors;
static uint8_t owner,state=GW_CAPTURE;
static uint64_t start,end,departed,returned,last_sensing,last_status,t1,t2;
static int64_t offset;
static uint64_t uncertainty=UINT64_MAX,clock_updated;
static uint64_t seen[64];
static portMUX_TYPE capture_lock=portMUX_INITIALIZER_UNLOCKED;
static uint32_t capture_rejected;
static QueueHandle_t queue_events;
typedef struct {uint8_t size;uint8_t data[64];} diagnostic_t;
static uint32_t event_drops;
static bool return_notice;
static uint32_t notice_grant;
static uint64_t last_upload_work;
static bool metrics_pending,metrics_busy_return;
static uint32_t metrics_grant;
static uint8_t bitmap_request[GW_BITMAP_SIZE];
static bool bitmap_pending;
static uint32_t bitmap_token;
static uint64_t last_bitmap_poll;
static int slot=-1;
static uint64_t now_us(void){return esp_timer_get_time();}
static void diagnostic(const uint8_t *p,unsigned size)
{
    if(size>64){++event_drops;return;}
    diagnostic_t event={.size=size};memcpy(event.data,p,size);
    if(!xQueueSend(queue_events,&event,0))++event_drops;
}
static void queue_event_detail(uint8_t kind,uint32_t id,unsigned count,unsigned attempts,unsigned detail)
{
    uint8_t p[48]={0};memcpy(p,"CGQE",4);p[4]=1;p[5]=slot;p[6]=kind;p[7]=count;
    csi_clock_write_u64(p+8,config.run);csi_clock_write_u32(p+16,txboot);
    csi_clock_write_u32(p+20,boot);csi_clock_write_u32(p+24,id);
    csi_clock_write_u32(p+28,handled);csi_clock_write_u64(p+32,now_us());
    csi_clock_write_u16(p+40,gw_queue_count(&records));p[42]=attempts;p[43]=detail;gw_crc(p,sizeof(p));
    diagnostic(p,sizeof(p));
}
static void queue_event(uint8_t kind,uint32_t id,unsigned count,unsigned attempts)
{queue_event_detail(kind,id,count,attempts,0);}

bool gw_receiver_observe(const uint8_t *p,size_t n,uint64_t received)
{
    (void)received;
    if(!gw_check(p,n,"CSIT",GW_SENSING_SIZE)||p[4]!=4||!configured||
       memcmp(p+40,config.wire,GW_CONFIG_SIZE)||csi_clock_read_u32(p+148)!=txboot)return false;
    uint64_t identity=csi_clock_read_u64(p+16); /* enqueue timestamp */
    uint32_t seq=csi_clock_read_u32(p+8);
    portENTER_CRITICAL(&capture_lock);
    bool duplicate=seen[seq%64]==identity;
    seen[seq%64]=identity;
    portEXIT_CRITICAL(&capture_lock);
    return !duplicate;
}
bool gw_receiver_enqueue(const uint8_t *p,uint16_t n,uint64_t captured)
{
    if(n>699||!n)return false;
    capture_t item={.length=n,.captured=captured};memcpy(item.data,p,n);
    if(xQueueSend(captures,&item,0)==pdTRUE)return true;
    ++capture_rejected;return false;
}
static void status(void)
{
    uint8_t p[GW_STATUS_SIZE]={0};memcpy(p,"CGST",4);p[4]=1;p[5]=slot;p[6]=state;
    p[7]=event_drops!=0;
    csi_clock_write_u64(p+8,config.run);csi_clock_write_u32(p+16,txboot);
    csi_clock_write_u32(p+20,boot);csi_clock_write_u32(p+24,handled);
    csi_clock_write_u32(p+28,transition_grant);
    csi_clock_write_u16(p+86,records.peak);
    csi_clock_write_u64(p+32,t1);csi_clock_write_u64(p+40,t2);
    csi_clock_write_u64(p+48,now_us());csi_clock_write_u64(p+56,departed);
    csi_clock_write_u64(p+64,returned);csi_clock_write_u32(p+72,records.captured);
    csi_clock_write_u32(p+76,records.evicted+records.rejected+capture_rejected+gw_io_drops());
    csi_clock_write_u32(p+80,records.expired);csi_clock_write_u16(p+84,gw_queue_count(&records));
    csi_clock_write_u32(p+88,send_errors+gw_io_mac_failures());gw_crc(p,sizeof(p));
    if(gw_send(profile->transmitter_mac,p,sizeof(p),1))last_status=now_us();
}
static void accept_batch(uint32_t id)
{
    for(unsigned i=0;i<config.outstanding;++i)if(batches[i].used&&batches[i].id==id){
        gw_queue_release(&records,id,true);queue_event(4,id,batches[i].count,batches[i].attempts);batches[i].used=false;
        last_upload_work=now_us();
    }
}
static void observe(const gw_message_t *m)
{
    if(!memcmp(m->source,profile->transmitter_mac,6)&&gw_check(m->data,m->size,"CSIT",GW_SENSING_SIZE)&&m->data[4]==4){
        gw_config_t next;
        if(!gw_config_decode(m->data+40,GW_CONFIG_SIZE,&next)||
           memcmp(next.wire+68,profile->fingerprint,16)||
           memcmp(next.wire+38,profile->transmitter_mac,6)||
           next.sensing_channel!=profile->channel||next.rate!=profile->nominal_rate_hz)return;
        int index=gw_slot(&next,mac);if(index<0)return;
        uint32_t b=csi_clock_read_u32(m->data+148);
        if(!configured || b!=txboot || memcmp(next.wire,config.wire,GW_CONFIG_SIZE)){
            /* A new epoch is adopted only while physically back on sensing. */
            if((state!=GW_CAPTURE&&state!=GW_CONFIRM)||unconfirmed_send)return;
            configured=false;config=next;txboot=b;slot=index;handled=0;
            transition_grant=0;departed=0;returned=0;last_status=0;notice_grant=0;
            last_upload_work=0;
            metrics_pending=false;
            bitmap_pending=false;bitmap_token=0;last_bitmap_poll=0;
            return_notice=false;
            xQueueReset(queue_events);event_drops=0;
            gw_queue_reset(&records,config.capacity);memset(batches,0,sizeof(batches));
            portENTER_CRITICAL(&capture_lock);memset(seen,0,sizeof(seen));portEXIT_CRITICAL(&capture_lock);xQueueReset(captures);batch_id=0;clock_updated=0;uncertainty=UINT64_MAX;
            gw_peer(profile->transmitter_mac,false);gw_peer(config.wire+32,false);
            if(!gw_peer_set_mcs(config.wire+32,config.backhaul_mcs))abort();
            configured=true;
        }
        last_sensing=m->received;t1=csi_clock_read_u64(m->data+16);t2=m->received;
        grant=csi_clock_read_u32(m->data+152);owner=m->data[156];
        if(return_notice&&grant!=notice_grant)return_notice=false;
        start=csi_clock_read_u64(m->data+160);end=csi_clock_read_u64(m->data+168);
        if(state==GW_CONFIRM){returned=m->received;state=GW_CAPTURE;return_notice=true;notice_grant=handled;status();}
        if(owner==slot&&t1>=end&&handled!=grant){handled=grant;return_notice=true;notice_grant=grant;status();}
    }else if(!memcmp(m->source,profile->transmitter_mac,6)&&
             gw_check(m->data,m->size,"CGCK",GW_CLOCK_SIZE)&&configured){
        const uint8_t *p=m->data;
        if(p[4]!=1||p[5]!=slot||csi_clock_read_u64(p+8)!=config.run||
           csi_clock_read_u32(p+16)!=txboot||csi_clock_read_u32(p+20)!=boot)return;
        int64_t a=csi_clock_read_u64(p+24),b=csi_clock_read_u64(p+32);
        int64_t c=csi_clock_read_u64(p+40),d=csi_clock_read_u64(p+48);
        int64_t rtt=(d-a)-(c-b);if(rtt<0||rtt>8000||c<b||d<a)return;
        if(!clock_updated||now_us()-clock_updated>500000|| (uint64_t)rtt/2<uncertainty){
            offset=((a-b)+(d-c))/2;uncertainty=rtt/2+250;clock_updated=now_us();
        }
    }else if(configured&&config.application_ack&&!memcmp(m->source,config.wire+32,6)&&gw_check(m->data,m->size,"CGAK",GW_ACK_SIZE)){
        const uint8_t *p=m->data;
        if(csi_clock_read_u64(p+4)!=config.run||csi_clock_read_u32(p+12)!=txboot||
           csi_clock_read_u32(p+16)!=boot||memcmp(p+24,mac,6))return;
        uint32_t id=csi_clock_read_u32(p+20);
        accept_batch(id);
    }else if(configured&&config.bitmap_ack&&!memcmp(m->source,config.wire+32,6)&&bitmap_pending&&
             gw_bitmap_valid(m->data,m->size,true)&&gw_bitmap_matches(bitmap_request,m->data)){
        for(unsigned i=0;i<m->data[5];++i)if(m->data[6]&(1U<<i)){
            accept_batch(csi_clock_read_u32(m->data+36+4*i));
        }
        bitmap_pending=false;
    }
}
static batch_t *build(unsigned remaining)
{
    batch_t *b=NULL;
    for(unsigned i=0;i<config.outstanding;++i)if(!batches[i].used){b=&batches[i];break;}
    gw_record_slot_t *s=gw_queue_oldest(&records);if(!b||!s||!remaining)return NULL;
    memset(b,0,sizeof(*b));b->used=true;b->id=batch_id++;b->oldest=s->captured;
    uint8_t *p=b->data+GW_ENVELOPE_HEADER;
    memset(p,0,60);memcpy(p,"CSIB",4);p[4]=1;csi_clock_write_u16(p+6,60);
    csi_clock_write_u32(p+8,boot);csi_clock_write_u32(p+12,b->id);
    unsigned length=60;
    while(s && b->count<4 && b->count<remaining && GW_ENVELOPE_HEADER+length+2+s->length+4<=GW_MAX_PACKET){
        csi_clock_write_u16(p+length,s->length);length+=2;
        memcpy(p+length,s->data,s->length);length+=s->length;
        s->state=2;s->batch=b->id;++b->count;s=gw_queue_oldest(&records);
    }
    csi_clock_write_u16(p+16,b->count);
    uint32_t counters[10]={records.captured,0,0,0,records.evicted+records.rejected+capture_rejected+gw_io_drops(),0,
        ++built,0,records.acknowledged,send_errors};
    for(unsigned i=0;i<10;++i)csi_clock_write_u32(p+20+4*i,counters[i]);
    p=b->data;memset(p,0,40);memcpy(p,"CGWY",4);p[4]=1;csi_clock_write_u16(p+6,40);
    csi_clock_write_u64(p+8,config.run);csi_clock_write_u32(p+16,txboot);
    csi_clock_write_u32(p+20,boot);csi_clock_write_u32(p+24,b->id);memcpy(p+28,mac,6);
    csi_clock_write_u16(p+34,length);b->length=40+length+4;gw_crc(p,b->length);
    queue_event(1,b->id,b->count,0);return b;
}
static bool tune(uint8_t channel)
{
    if(esp_wifi_set_channel(channel,WIFI_SECOND_CHAN_NONE)!=ESP_OK)return false;
    uint8_t actual=0;wifi_second_chan_t secondary;
    return esp_wifi_get_channel(&actual,&secondary)==ESP_OK&&actual==channel;
}
static uint8_t poll_eligible(void)
{
    uint8_t mask=0;
    if(!config.application_ack)return 0;
    for(unsigned i=0;i<config.outstanding;++i)
        if(batches[i].used&&batches[i].attempts)mask|=1U<<i;
    return mask;
}
static bool poll_batch(unsigned i,uint64_t now)
{
    uint8_t poll[GW_ACK_SIZE]={0};memcpy(poll,"CGPL",4);
    csi_clock_write_u64(poll+4,config.run);csi_clock_write_u32(poll+12,txboot);
    csi_clock_write_u32(poll+16,boot);csi_clock_write_u32(poll+20,batches[i].id);
    memcpy(poll+24,mac,6);gw_crc(poll,sizeof(poll));
    if(!gw_send(config.wire+32,poll,sizeof(poll),send_wait(1)))return false;
    batches[i].polled=now;last_upload_work=now_us();return true;
}
static bool poll_bitmap(uint8_t eligible,uint64_t now)
{
    if(!eligible||!gw_send_idle())return false;
    uint8_t p[GW_BITMAP_SIZE]={0};memcpy(p,"CGPQ",4);p[4]=1;
    csi_clock_write_u64(p+8,config.run);csi_clock_write_u32(p+16,txboot);csi_clock_write_u32(p+20,boot);
    memcpy(p+24,mac,6);if(++bitmap_token==0)++bitmap_token;csi_clock_write_u32(p+32,bitmap_token);
    for(unsigned i=0;i<config.outstanding;++i)if(eligible&(1U<<i))csi_clock_write_u32(p+36+4*p[5]++,batches[i].id);
    gw_crc(p,sizeof(p));
    if(!gw_send(config.wire+32,p,sizeof(p),send_wait(1)))return false;
    memcpy(bitmap_request,p,sizeof(p));bitmap_pending=true;last_bitmap_poll=now;last_upload_work=now_us();
    for(unsigned i=0;i<config.outstanding;++i)if(eligible&(1U<<i))batches[i].polled=now;
    return true;
}
static bool upload_work_ready(uint64_t now,unsigned submitted,uint8_t pending_polls)
{
    if(submitted>=config.allowance)return false;
    if(pending_polls&poll_eligible())return true;
    bool free_batch=false;
    for(unsigned i=0;i<config.outstanding;++i){
        batch_t *b=&batches[i];
        if(!b->used){free_batch=true;continue;}
        if(b->count+submitted<=config.allowance&&gw_batch_ready(&config,b->attempts,b->sent,b->oldest,now))return true;
        if(b->attempts&&now>=b->sent&&now>=b->polled&&
           now-b->sent>=(uint64_t)config.ack_ms*1000&&
           now-b->polled>=(uint64_t)config.ack_ms*1000)return true;
    }
    return free_batch&&gw_queue_oldest(&records);
}
static bool upload_empty(void)
{
    if(gw_queue_count(&records))return false;
    for(unsigned i=0;i<config.outstanding;++i)if(batches[i].used)return false;
    return true;
}
static batch_t *next_burst_batch(uint64_t now,unsigned remaining,uint8_t pending_polls)
{
    for(unsigned i=0;i<config.outstanding;++i)
        if(batches[i].used&&!batches[i].attempts&&gw_batch_ready(&config,0,batches[i].sent,batches[i].oldest,now))return &batches[i];
    /* With eight owned batches, draining every cached ACK before any new data
     * can consume the entire short window. Refill released slots between polls. */
    batch_t *fresh=build(remaining);if(fresh)return fresh;
    for(unsigned i=0;i<config.outstanding;++i){
        batch_t *b=&batches[i];
        if(b->used&&!(pending_polls&(1U<<i))&&gw_batch_ready(&config,b->attempts,b->sent,b->oldest,now))return b;
    }
    return NULL;
}
/* Completion means the MAC no longer owns these bytes, not host acceptance.
 * Both successful and failed MAC sends are retired without application retry. */
static void retire_unconfirmed_send(void)
{
    if(!unconfirmed_send||!gw_send_idle())return;
    batch_t *b=unconfirmed_send;
    gw_queue_release_unconfirmed(&records,b->id);
    queue_event(11,b->id,b->count,b->attempts);
    b->used=false;unconfirmed_send=NULL;
}
static void worker(void *arg)
{
    (void)arg;static gw_message_t message;static capture_t capture;
    uint64_t hard_return=0;unsigned submitted=0;
    unsigned poll_cursor=0;uint8_t pending_polls=0;uint32_t reported_loss=0;
    bool prefer_poll=true;
    for(;;){
        retire_unconfirmed_send();
        while(xQueueReceive(gw_incoming(),&message,0))observe(&message);
        uint64_t now=now_us();
        if(!configured){vTaskDelay(1);continue;}
        if(metrics_pending&&state==GW_CAPTURE&&gw_send_idle()){
            gw_send_stats_t stats;
            if(gw_measure_sends_finish(&stats)){
                uint8_t p[64]={0};memcpy(p,"CGMT",4);p[4]=1;p[5]=slot;p[6]=metrics_busy_return;
                csi_clock_write_u64(p+8,config.run);csi_clock_write_u32(p+16,txboot);csi_clock_write_u32(p+20,boot);
                csi_clock_write_u32(p+24,metrics_grant);csi_clock_write_u16(p+28,stats.samples);csi_clock_write_u16(p+30,stats.failures);
                csi_clock_write_u32(p+32,stats.minimum_us);csi_clock_write_u32(p+36,stats.maximum_us);csi_clock_write_u64(p+40,stats.total_us);
                csi_clock_write_u32(p+48,stats.maximum_failure_us);csi_clock_write_u32(p+52,stats.late);gw_crc(p,sizeof(p));
                diagnostic(p,sizeof(p));metrics_pending=false;
            }
        }
        /* Reclaim stale pending and owned records before admitting new copies. */
        uint32_t expired=records.expired;
        gw_queue_expire(&records,now,(uint64_t)config.age_ms*1000);
        if(records.expired!=expired)queue_event(6,UINT32_MAX,records.expired-expired,0);
        for(unsigned i=0;i<config.outstanding;++i)if(batches[i].used && &batches[i]!=unconfirmed_send&&now-batches[i].oldest>=(uint64_t)config.age_ms*1000){
            gw_queue_release(&records,batches[i].id,false);queue_event(5,batches[i].id,batches[i].count,batches[i].attempts);batches[i].used=false;
        }
        while(xQueueReceive(captures,&capture,0)){
            if(now>=capture.captured&&now-capture.captured>=(uint64_t)config.age_ms*1000){
                ++records.captured;++records.expired;queue_event(6,UINT32_MAX,1,0);continue;
            }
            if(capture.captured>=last_sensing-((last_sensing>1000000)?1000000:0))
                gw_queue_push(&records,capture.data,capture.length,capture.captured);
        }
        uint32_t loss_now=records.evicted+records.rejected+capture_rejected;
        if(loss_now!=reported_loss){queue_event(7,UINT32_MAX,loss_now-reported_loss,0);reported_loss=loss_now;}
        uint64_t margin=uncertainty==UINT64_MAX?UINT64_MAX:uncertainty+(now-clock_updated)/1000;
        int64_t reference=(int64_t)now+offset;
        uint64_t cutoff=clock_updated?gw_return_cutoff(&config,end,t1):0;
        if(state==GW_CAPTURE&&owner==slot&&grant!=handled&&clock_updated&&now-clock_updated<1000000&&
           margin<(uint64_t)config.start_ms*1000&&reference>=(int64_t)(start+config.start_ms*1000)+ (int64_t)margin&&
           reference+(int64_t)config.send_guard_ms*1000<(int64_t)cutoff-(int64_t)margin&&
           (config.wire[4]<3||gw_send_idle())){
            handled=grant;hard_return=(uint64_t)((int64_t)cutoff-offset-(int64_t)margin);
            state=GW_SWITCH_2G;departed=now;returned=0;transition_grant=grant;submitted=0;pending_polls=poll_eligible();
            last_upload_work=now;
            prefer_poll=true;
            bitmap_pending=false;
            gw_measure_sends_begin(hard_return,config.measure_sends);metrics_pending=config.measure_sends;
            metrics_busy_return=false;metrics_grant=grant;
            if(tune(config.channel)){state=GW_UPLOAD;}else state=GW_RETURN;
        }
        if(state==GW_UPLOAD){
            now=now_us(); /* Retuning may have consumed part of the upload budget. */
            if(now>=hard_return){state=GW_RETURN;}
            else if(hard_return-now>(uint64_t)config.send_guard_ms*1000&&submitted<config.allowance&&
                    ((!CONFIG_CSI_GATEWAY_EVENT_UPLOAD&&config.application_ack)||gw_send_idle())){
                /* Retrieve acceptance of earlier turns before consuming retry
                 * bandwidth. Rotate to prevent an unreceived batch starving ACKs. */
                int poll=gw_poll_next(&pending_polls,poll_eligible(),config.outstanding,&poll_cursor);
                batch_t *b=config.outstanding>4?next_burst_batch(now,config.allowance-submitted,pending_polls):NULL;
                if(config.bitmap_ack&&pending_polls){
                    if(poll_bitmap(pending_polls,now))pending_polls=0;
                    prefer_poll=false;upload_pause();continue;
                }
                if(poll>=0&&(config.outstanding<=4||prefer_poll||!b)){
                    if(poll_batch(poll,now))pending_polls&=~(1U<<poll);
                    prefer_poll=false;
                    upload_pause();continue;
                }
                if(config.outstanding<=4){
                for(unsigned i=0;i<config.outstanding;++i)if(batches[i].used&&
                    gw_batch_ready(&config,batches[i].attempts,batches[i].sent,batches[i].oldest,now)){b=&batches[i];break;}
                if(!b)b=build(config.allowance-submitted);
                }
                if(b&&submitted+b->count<=config.allowance){
                    /* Busy/rejected submissions did not reach the MAC. They must
                     * not consume the single application retry or slot allowance. */
                    if(gw_send(config.wire+32,b->data,b->length,send_wait(2))){
                        ++b->attempts;b->sent=now;submitted+=b->count;
                        last_upload_work=now_us();
                        prefer_poll=true;
                        queue_event(b->attempts==1?2:3,b->id,b->count,b->attempts);
                        if(!config.application_ack)unconfirmed_send=b;
                    }else ++send_errors;
                }else if(config.bitmap_ack){
                    if(now>=last_bitmap_poll&&now-last_bitmap_poll>=(uint64_t)config.ack_ms*1000)poll_bitmap(poll_eligible(),now);
                }else if(config.application_ack){
                    /* Rotate over every outstanding batch: one lost batch must
                     * not prevent retrieval of other host acceptance ACKs. */
                    for(unsigned j=0;j<config.outstanding;++j){
                        unsigned i=poll_cursor++%config.outstanding;
                        if(!batches[i].used||!batches[i].attempts||
                           now-batches[i].sent<(uint64_t)config.ack_ms*1000||
                           now-batches[i].polled<(uint64_t)config.ack_ms*1000)continue;
                        poll_batch(i,now);
                        break;
                    }
                }
            }
            if(state==GW_UPLOAD){
                now=now_us();
                unsigned exit=gw_upload_exit(&config,now,hard_return,last_upload_work,
                    gw_send_idle(),upload_work_ready(now,submitted,pending_polls),
                    submitted>=config.allowance||upload_empty());
                if(exit){
                    if(exit!=GW_EXIT_DEADLINE)queue_event_detail(9,UINT32_MAX,submitted,0,exit);
                    state=GW_RETURN;
                }
            }
        }
        if(state==GW_RETURN){
            if(metrics_pending&&!gw_send_idle())metrics_busy_return=true;
            if(tune(profile->channel)){
                state=GW_CONFIRM;last_status=0;queue_event(10,UINT32_MAX,0,0);
                if(config.early_idle_ms)status(); /* Request sensing probes on 5 GHz. */
            }
            else{state=GW_FAULT;++send_errors;queue_event(8,UINT32_MAX,0,0);}
        }
        if(state==GW_FAULT){if(tune(profile->channel))state=GW_CONFIRM;}
        uint64_t status_period=return_notice?1000000U/config.rate:100000;
        if(state==GW_CONFIRM&&config.early_idle_ms)status_period=1000000U/config.rate;
        if(state==GW_CONFIRM&&config.early_idle_ms&&now>=last_status&&now-last_status>=status_period&&
           now>=last_sensing&&now-last_sensing<1000000)status();
        if(state==GW_CAPTURE&&now>=last_status&&now-last_status>=status_period&&now-last_sensing<500000)status();
        if(state==GW_CAPTURE){
            diagnostic_t event;
            if(xQueuePeek(queue_events,&event,0)&&gw_send(profile->transmitter_mac,event.data,event.size,0))
                xQueueReceive(queue_events,&event,0);
        }
        if(CONFIG_CSI_GATEWAY_EVENT_UPLOAD&&state==GW_UPLOAD)upload_pause();
        else vTaskDelay(1);
    }
}
void gw_receiver_init(const csi_radio_profile_t *p,const uint8_t *address,uint32_t b)
{
    profile=p;memcpy(mac,address,6);boot=b;captures=xQueueCreate(32,sizeof(capture_t));queue_events=xQueueCreate(128,sizeof(diagnostic_t));
    TaskHandle_t worker_handle=NULL;
    if(!captures||!queue_events||xTaskCreate(worker,"csi_gateway",8192,NULL,5,&worker_handle)!=pdPASS)abort();
#if CONFIG_CSI_GATEWAY_EVENT_UPLOAD
    gw_io_set_wakeup(notify_upload_worker,worker_handle);
#endif
}
