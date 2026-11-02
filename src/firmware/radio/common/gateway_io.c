#include "gateway_io.h"
#include "driver/usb_serial_jtag.h"
#include "esp_timer.h"
#include "esp_wifi.h"
static QueueHandle_t incoming;
static uint16_t incoming_maximum;
static SemaphoreHandle_t tx_lock,usb_lock;
static volatile bool busy;
static volatile uint32_t rx_drops,mac_failures;
static portMUX_TYPE metric_lock=portMUX_INITIALIZER_UNLOCKED;
static bool measuring,tracked_send;
static uint64_t send_started,send_deadline;
static gw_send_stats_t send_stats;
static void (*worker_wakeup)(void *);
static void *worker_context;
void gw_io_set_wakeup(void (*wakeup)(void *),void *context)
{
    portENTER_CRITICAL(&metric_lock);worker_wakeup=wakeup;worker_context=context;portEXIT_CRITICAL(&metric_lock);
}
static void wake_worker(void)
{
    portENTER_CRITICAL(&metric_lock);void (*wakeup)(void *)=worker_wakeup;void *context=worker_context;portEXIT_CRITICAL(&metric_lock);
    if(wakeup)wakeup(context);
}
static void sent(const esp_now_send_info_t *info,esp_now_send_status_t status)
{
    (void)info;if(status!=ESP_NOW_SEND_SUCCESS)++mac_failures;
    uint64_t completed=esp_timer_get_time();
    portENTER_CRITICAL(&metric_lock);
    if(measuring&&tracked_send){
        uint64_t elapsed=completed-send_started;
        uint32_t duration=elapsed>UINT32_MAX?UINT32_MAX:(uint32_t)elapsed;
        ++send_stats.samples;send_stats.total_us+=duration;
        if(duration<send_stats.minimum_us)send_stats.minimum_us=duration;
        if(duration>send_stats.maximum_us)send_stats.maximum_us=duration;
        if(status!=ESP_NOW_SEND_SUCCESS){++send_stats.failures;if(duration>send_stats.maximum_failure_us)send_stats.maximum_failure_us=duration;}
        if(completed>send_deadline)++send_stats.late;
    }
    tracked_send=false;portEXIT_CRITICAL(&metric_lock);busy=false;wake_worker();
}
static void received(const esp_now_recv_info_t *info,const uint8_t *data,int n)
{
    if(!info||n<4)return;
    if(n>incoming_maximum){++rx_drops;return;}
    gw_message_t message={.size=n,.received=esp_timer_get_time()};
    memcpy(message.source,info->src_addr,6);memcpy(message.data,data,n);
    if(xQueueSend(incoming,&message,0)!=pdTRUE)++rx_drops; /* bounded; loss is visible in sequences */
    else wake_worker();
}
void gw_io_init(void){gw_io_init_sized(GW_MAX_PACKET);}
void gw_io_init_sized(uint16_t maximum_payload)
{
    if(maximum_payload<4||maximum_payload>GW_MAX_PACKET ||
       (incoming&&incoming_maximum!=maximum_payload))abort();
    incoming_maximum=maximum_payload;
    if(!incoming){incoming=xQueueCreate(32,offsetof(gw_message_t,data)+maximum_payload);tx_lock=xSemaphoreCreateMutex();usb_lock=xSemaphoreCreateMutex();}
    busy=false;
    if(!incoming||!tx_lock||!usb_lock)abort();
    ESP_ERROR_CHECK(esp_now_init());ESP_ERROR_CHECK(esp_now_register_send_cb(sent));
    ESP_ERROR_CHECK(esp_now_register_recv_cb(received));
}
QueueHandle_t gw_incoming(void){return incoming;}
uint32_t gw_io_drops(void){return rx_drops;}
uint32_t gw_io_mac_failures(void){return mac_failures;}
bool gw_send_idle(void){return !busy;}
bool gw_measure_sends_begin(uint64_t deadline,bool enabled)
{
    if(busy)return false;
    portENTER_CRITICAL(&metric_lock);
    memset(&send_stats,0,sizeof(send_stats));send_stats.minimum_us=UINT32_MAX;
    send_deadline=deadline;measuring=enabled;tracked_send=false;
    portEXIT_CRITICAL(&metric_lock);return true;
}
bool gw_measure_sends_finish(gw_send_stats_t *stats)
{
    if(busy)return false;
    portENTER_CRITICAL(&metric_lock);*stats=send_stats;measuring=false;
    portEXIT_CRITICAL(&metric_lock);
    if(!stats->samples)stats->minimum_us=0;
    return true;
}
void gw_peer(const uint8_t *mac,bool he)
{
    if(!esp_now_is_peer_exist(mac)){
        esp_now_peer_info_t peer={.channel=0,.ifidx=WIFI_IF_STA};memcpy(peer.peer_addr,mac,6);
        ESP_ERROR_CHECK(esp_now_add_peer(&peer));
    }
    esp_now_rate_config_t rate={.phymode=he?WIFI_PHY_MODE_HE20:WIFI_PHY_MODE_HT20,
        .rate=WIFI_PHY_RATE_MCS0_LGI,.ersu=false,.dcm=false};
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(mac,&rate));
}
bool gw_peer_set_mcs(const uint8_t *mac,uint8_t mcs)
{
    static const wifi_phy_rate_t rates[]={WIFI_PHY_RATE_MCS0_LGI,WIFI_PHY_RATE_MCS1_LGI,
        WIFI_PHY_RATE_MCS2_LGI,WIFI_PHY_RATE_MCS3_LGI};
    if(mcs>3||!esp_now_is_peer_exist(mac))return false;
    esp_now_rate_config_t rate={.phymode=WIFI_PHY_MODE_HT20,.rate=rates[mcs],.ersu=false,.dcm=false};
    return esp_now_set_peer_rate_config(mac,&rate)==ESP_OK;
}
bool gw_send(const uint8_t *mac,const void *p,size_t n,uint32_t wait_ms)
{
    if(xSemaphoreTake(tx_lock,0)!=pdTRUE)return false;
    if(busy){xSemaphoreGive(tx_lock);return false;}
    portENTER_CRITICAL(&metric_lock);
    tracked_send=measuring&&n>=4&&(!memcmp(p,"CGWY",4)||!memcmp(p,"CGPL",4)||!memcmp(p,"CGPQ",4));
    send_started=esp_timer_get_time();portEXIT_CRITICAL(&metric_lock);
    busy=true;esp_err_t err=esp_now_send(mac,p,n);
    if(err!=ESP_OK){tracked_send=false;busy=false;}
    uint64_t until=esp_timer_get_time()+(uint64_t)wait_ms*1000;
    while(busy && (uint64_t)esp_timer_get_time()<until)vTaskDelay(1);
    bool ok=err==ESP_OK; /* MAC result is not application acceptance. */
    xSemaphoreGive(tx_lock);return ok;
}
bool gw_usb_write(uint8_t type,const uint8_t *p,size_t n)
{
    if(xSemaphoreTake(usb_lock,pdMS_TO_TICKS(20))!=pdTRUE)return false;
    static uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE],frame[CSI_SERIAL_MAX_FRAME_SIZE];
    size_t size=csi_serial_encode_frame(type,p,n,raw,sizeof(raw),frame,sizeof(frame));
    bool ok=size&&usb_serial_jtag_write_bytes(frame,size,pdMS_TO_TICKS(20))==(int)size;
    xSemaphoreGive(usb_lock);return ok;
}
bool gw_usb_read(uint8_t *type,uint8_t *p,size_t *n)
{
    static uint8_t encoded[CSI_SERIAL_MAX_ENCODED_SIZE],raw[CSI_SERIAL_MAX_RAW_SIZE];
    static size_t used;static bool dropping;
    static uint8_t chunk[512];static int position,available;
    for(;;){
    if(position==available){available=usb_serial_jtag_read_bytes(chunk,sizeof(chunk),pdMS_TO_TICKS(5));position=0;if(available<=0){available=0;return false;}}
    uint8_t b=chunk[position++];
    if(b){if(used<sizeof(encoded)&&!dropping)encoded[used++]=b;else dropping=true;continue;}
    if(dropping||!used){used=0;dropping=false;continue;}
    size_t in=0,out=0,total=used;used=0;
    while(in<total){unsigned code=encoded[in++];if(!code||in+code-1>total)return false;
        for(unsigned j=1;j<code;++j){if(out>=sizeof(raw))return false;raw[out++]=encoded[in++];}
        if(code!=255&&in<total){if(out>=sizeof(raw))return false;raw[out++]=0;}}
    if(out<12||memcmp(raw,"CSIS",4)||raw[4]!=1)return false;
    size_t length=csi_clock_read_u16(raw+6);
    if(length>1400||out!=length+12||csi_serial_crc32(raw,out-4)!=csi_clock_read_u32(raw+out-4))return false;
    *type=raw[5];*n=length;memcpy(p,raw+8,length);return true;
    }
}
