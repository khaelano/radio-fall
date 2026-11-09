#include "sdkconfig.h"
#include "gateway_transmitter.h"
#include "gateway_io.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/task.h"
static const csi_radio_profile_t *profile;
static gw_config_t config;
static gw_schedule_t schedule;
static uint32_t boot,generation,drops,ready_mask;
static uint64_t last_control;
static uint64_t last_deferred;
static bool configured,running;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static QueueHandle_t logs;
static bool (*write_frame)(uint8_t,const uint8_t *,size_t);
typedef struct {uint8_t type;uint16_t size;uint8_t data[176];} log_t;
static void log_message(uint8_t type,const uint8_t *p,size_t n)
{
    log_t m={.type=type,.size=n};if(n>sizeof(m.data))return;memcpy(m.data,p,n);
    if(!xQueueSend(logs,&m,0))++drops;
}
static void logger(void *arg)
{
    (void)arg;log_t m;
    for(;;)if(xQueueReceive(logs,&m,portMAX_DELAY)&&!write_frame(m.type,m.data,m.size))++drops;
}
void gw_tx_init(const csi_radio_profile_t *p,bool (*writer)(uint8_t,const uint8_t *,size_t))
{
    profile=p;write_frame=writer;boot=esp_random();logs=xQueueCreate(128,sizeof(log_t));
    if(!logs||xTaskCreate(logger,"csi_logs",4096,NULL,3,NULL)!=pdPASS)abort();
}
size_t gw_tx_control(const uint8_t *p,size_t n,uint8_t *response)
{
    if(n==16&&!memcmp(p,"CGHC",4)){
        uint64_t t2=esp_timer_get_time();memcpy(response,p,16);csi_clock_write_u64(response+16,t2);
        csi_clock_write_u64(response+24,esp_timer_get_time());csi_clock_write_u32(response+32,boot);
        csi_clock_write_u32(response+36,drops+gw_io_drops());portENTER_CRITICAL(&lock);last_control=t2;portEXIT_CRITICAL(&lock);return 40;
    }
    bool ok=false;
    portENTER_CRITICAL(&lock);
    if(!running&&n==GW_CONFIG_SIZE){
        gw_config_t next;
        if(gw_config_decode(p,n,&next)&&next.rate==profile->nominal_rate_hz&&
            next.sensing_channel==profile->channel&&next.count==profile->receiver_count&&
            !memcmp(p+38,profile->transmitter_mac,6)&&!memcmp(p+68,profile->fingerprint,16)&&
            !memcmp(p+44,profile->receiver_macs,6*next.count)){
            config=next;configured=true;ready_mask=0;memset(&schedule,0,sizeof(schedule));++generation;ok=true;
        }
    }else if(n==12&&configured&&csi_clock_read_u64(p+4)==config.run&&
             (!memcmp(p,"CGGO",4)||!memcmp(p,"CGSP",4))){
        bool start=!memcmp(p,"CGGO",4);
        if(start&&!running){++generation;ready_mask=0;memset(&schedule,0,sizeof(schedule));}
        running=start;ok=true;
    }
    if(ok)last_control=esp_timer_get_time();
    portEXIT_CRITICAL(&lock);
    memcpy(response,ok?"ok":"error",ok?2:5);return ok?2:5;
}
static void observe(void)
{
    static gw_message_t m;
    if(!gw_incoming())return;
    while(xQueueReceive(gw_incoming(),&m,0)){
        const uint8_t *p=m.data;
        if((gw_check(p,m.size,"CGQE",48)||gw_check(p,m.size,"CGMT",64))&&p[4]==1&&csi_clock_read_u64(p+8)==config.run&&
           csi_clock_read_u32(p+16)==boot){
            int slot=gw_slot(&config,m.source);
            if(slot>=0&&p[5]==slot)log_message(GW_EVENT,p,m.size);
            continue;
        }
        if(!gw_check(p,m.size,"CGST",GW_STATUS_SIZE)||p[4]!=1||
            csi_clock_read_u64(p+8)!=config.run||csi_clock_read_u32(p+16)!=boot)continue;
        int slot=gw_slot(&config,m.source);if(slot<0||p[5]!=slot)continue;
        if(p[6]==GW_CAPTURE)ready_mask|=1U<<slot;
        log_message(GW_EVENT,p,m.size);
        if(config.early_idle_ms&&gw_schedule_probe(&schedule,slot,csi_clock_read_u32(p+24),m.received,p[6])){
            uint8_t event[40]={0};memcpy(event,"CGPR",4);
            csi_clock_write_u64(event+4,config.run);csi_clock_write_u32(event+12,boot);
            csi_clock_write_u32(event+16,schedule.id);event[20]=slot;
            csi_clock_write_u64(event+24,m.received);gw_crc(event,sizeof(event));log_message(GW_EVENT,event,sizeof(event));
        }
        uint8_t clock[GW_CLOCK_SIZE]={0};memcpy(clock,"CGCK",4);clock[4]=1;clock[5]=slot;
        csi_clock_write_u64(clock+8,config.run);csi_clock_write_u32(clock+16,boot);
        csi_clock_write_u32(clock+20,csi_clock_read_u32(p+20));
        memcpy(clock+24,p+32,24);csi_clock_write_u64(clock+48,m.received);gw_crc(clock,sizeof(clock));
        gw_send(m.source,clock,sizeof(clock),1);log_message(GW_EVENT,clock,sizeof(clock));
        if(gw_schedule_return(&schedule,slot,csi_clock_read_u32(p+24),m.received,p[6])){
            /* Returned radio status is accepted only on the fixed 5 GHz link. */
            uint8_t event[40]={0};memcpy(event,"CGRT",4);
            csi_clock_write_u64(event+4,config.run);csi_clock_write_u32(event+12,boot);
            csi_clock_write_u32(event+16,schedule.id);event[20]=slot;
            csi_clock_write_u64(event+24,m.received);gw_crc(event,sizeof(event));log_message(GW_EVENT,event,sizeof(event));
        }
    }
}
bool gw_tx_running(void)
{portENTER_CRITICAL(&lock);bool active=running;portEXIT_CRITICAL(&lock);return active;}
void gw_tx_reference_failure(void)
{portENTER_CRITICAL(&lock);running=false;++drops;portEXIT_CRITICAL(&lock);}
bool gw_tx_snapshot(gw_config_t *c,uint32_t *b,uint32_t *g)
{
    portENTER_CRITICAL(&lock);
    if(running&&(uint64_t)esp_timer_get_time()-last_control>=(uint64_t)CONFIG_CSI_CONTROL_TIMEOUT_MS*1000)running=false;
    bool active=running;*c=config;*b=boot;*g=generation;
    portEXIT_CRITICAL(&lock);
    if(active){
        observe();
        uint64_t now=esp_timer_get_time();
        uint8_t reason=ready_mask!=(1U<<config.count)-1?1:
            (schedule.active&&!schedule.returned&&now>=schedule.end?2:0);
        if(reason&&now-last_deferred>=100000){
            uint8_t p[40]={0};memcpy(p,"CGDF",4);csi_clock_write_u64(p+4,config.run);
            csi_clock_write_u32(p+12,boot);csi_clock_write_u32(p+16,schedule.id);
            p[20]=schedule.owner;p[21]=reason;p[22]=ready_mask;
            csi_clock_write_u64(p+24,now);gw_crc(p,sizeof(p));log_message(GW_EVENT,p,sizeof(p));last_deferred=now;
        }
        if(!reason&&ready_mask==(1U<<config.count)-1&&gw_schedule_next(&schedule,&config,now)){
            uint8_t p[40]={0};memcpy(p,"CGGR",4);csi_clock_write_u64(p+4,config.run);
            csi_clock_write_u32(p+12,boot);csi_clock_write_u32(p+16,schedule.id);p[20]=schedule.owner;
            csi_clock_write_u64(p+24,schedule.start);csi_clock_write_u32(p+32,config.slot_ms);gw_crc(p,sizeof(p));
            log_message(GW_EVENT,p,sizeof(p));
        }
    }
    return active;
}
void gw_tx_schedule(gw_schedule_t *s){*s=schedule;}
void gw_tx_wait(uint64_t deadline)
{
    while((uint64_t)esp_timer_get_time()<deadline){
        if(gw_incoming()&&uxQueueMessagesWaiting(gw_incoming()))return;
        vTaskDelay(1);
    }
}
void gw_tx_round(const gw_config_t *c,uint32_t b,uint32_t seq,uint64_t enqueue,uint64_t deadline,uint32_t result)
{
    uint8_t p[51]={0};memcpy(p,"CGRD",4);csi_clock_write_u64(p+4,c->run);
    csi_clock_write_u32(p+12,b);csi_clock_write_u32(p+16,seq);
    csi_clock_write_u64(p+20,enqueue);csi_clock_write_u64(p+28,deadline);
    csi_clock_write_u32(p+36,1000000U/c->rate);csi_clock_write_u32(p+40,result);
    csi_clock_write_u32(p+44,drops+gw_io_drops());p[48]=schedule.active?schedule.owner:255;p[49]=p[50]=255;
    log_message(GW_ROUND,p,sizeof(p));
}
