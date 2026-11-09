#include "sdkconfig.h"
#ifndef CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS
#define CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS 50
#endif
#if !CONFIG_IDF_TARGET_ESP32C6
#error "Gateway firmware requires ESP32-C6"
#endif
#include "gateway_io.h"
#include "wireless_link.h"
#include "reference_relay.h"
#include "esp_system.h"
#include "radio_board.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "nvs_flash.h"
#include "driver/usb_serial_jtag.h"
#include "freertos/task.h"
#include <stdio.h>
static gw_config_t configuration;
static uint8_t mac[6];static uint32_t boot;
static volatile bool configured;
static uint32_t received,forwarded,usb_errors,rejected,transmitter_boot;
static uint32_t host_acks,ack_submissions,polls;
static uint32_t ack_skipped_age,ack_skipped_busy,ack_submit_errors;
static uint32_t ack_age_samples,ack_age_max_us,ack_age_le_2ms,ack_age_le_5ms,ack_age_le_10ms;
static uint64_t ack_age_total_us;
static QueueHandle_t commands;
static uint8_t cache[128][GW_ACK_SIZE];static unsigned cache_next;
static uint32_t last_rx_boot[4];
static uint64_t last_seen[4];
static uint8_t relay_usb[WL_PAYLOAD+1];
static size_t relay_used=1;
static uint32_t relay_peer_queued,relay_peer_peak,relay_peer_retries,relay_uart_errors;
static bool relay_flush(void)
{
    if(relay_used==1)return true;
    relay_usb[0]=0;
    bool ok=gw_usb_write(WL_USB_RESPONSE,relay_usb,relay_used);
    relay_used=1;
    if(!ok){
        ++usb_errors;
        if(configured)rr_fail("host_usb_failure");
    }
    /* Idle notifications can outlive the setup client. A missing laptop must
     * not poison the next handshake; active recordings still fail closed. */
    return ok||!configured;
}
static bool relay_received(uint8_t type,const uint8_t *p,size_t n,void *context)
{
    (void)context;
    if(type==RR_STATS_TYPE){
        if(n!=RR_STATS_SIZE||memcmp(p,"CRST",4))return false;
        relay_peer_queued=wl_u32(p+4);relay_peer_peak=wl_u32(p+8);
        relay_peer_retries=wl_u32(p+12);relay_uart_errors=wl_u32(p+16);
        return true;
    }
    if(n+4>sizeof(relay_usb))return false;
    if(relay_used+n+3>sizeof(relay_usb)&&!relay_flush())return false;
    relay_usb[relay_used++]=type;wl_w16(relay_usb+relay_used,n);relay_used+=2;
    memcpy(relay_usb+relay_used,p,n);relay_used+=n;
    return true;
}
static void wireless_received(uint8_t type,const uint8_t *p,size_t n,void *context)
{
    (void)context;static uint8_t framed[WL_PAYLOAD+1];static size_t used=1;static bool expect_restart;
    if(type){
        if(n+4>sizeof(framed)){wl_host_failure();return;}
        if(used+n+3>sizeof(framed))wireless_received(0,NULL,0,context);
        if(wl_faulted())return;
        framed[used++]=type;wl_w16(framed+used,n);used+=2;memcpy(framed+used,p,n);used+=n;
        if(type==CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK&&n==2&&!memcmp(p,"ok",2))expect_restart=true;
    }else if(used>1){
        framed[0]=0; /* Batched typed frames, one USB write per BLE packet. */
        if(!gw_usb_write(WL_USB_RESPONSE,framed,used)){++usb_errors;if(configured)wl_host_failure();}
        else if(expect_restart)wl_expect_peer_restart();
        expect_restart=false;
        used=1;
    }
}
static void status(void)
{
    char p[1400];int n=snprintf(p,sizeof(p),
        "{\"role\":\"gateway\",\"target\":\"esp32c6\",\"mac\":\"" MACSTR "\","
        "\"protocol_version\":3,\"transport_config_max_version\":7,\"firmware_version\":\"3\",\"csi_transport\":\"espnow_gateway\","
        "\"wireless_version\":2,\"wireless_paired\":%s,\"wireless_ready\":%s,\"wireless_fault\":%s,\"wireless_failure_reason\":\"%s\",\"wireless_debug\":\"%s\",\"wireless_drops\":%lu,\"wireless_peer_changes\":%lu,\"free_heap_bytes\":%lu,\"minimum_free_heap_bytes\":%lu,"
        "\"cpu_max_mhz\":%u,\"backhaul_mcs\":%u,\"ready\":true,\"boot_id\":%lu,\"configured\":%s,\"run_id\":\"%llu\",\"channel\":%u,"
        "\"transport_fingerprint\":\"%.16s\",\"received\":%lu,\"forwarded\":%lu,"
        "\"usb_errors\":%lu,\"rejected\":%lu,\"queued\":%u,"
        "\"host_acks\":%lu,\"ack_submissions\":%lu,\"polls\":%lu,\"mac_failures\":%lu,"
        "\"ack_max_age_ms\":%u,\"ack_skipped_age\":%lu,\"ack_skipped_busy\":%lu,\"ack_submit_errors\":%lu,"
        "\"ack_age_samples\":%lu,\"ack_age_max_us\":%lu,\"ack_age_total_us\":%llu,"
        "\"ack_age_le_2ms\":%lu,\"ack_age_le_5ms\":%lu,\"ack_age_le_10ms\":%lu}",
        MAC2STR(mac),wl_paired()?"true":"false",wl_ready()?"true":"false",wl_faulted()?"true":"false",wl_failure_reason(),wl_debug(),(unsigned long)wl_drops(),(unsigned long)wl_peer_changes(),(unsigned long)esp_get_free_heap_size(),(unsigned long)esp_get_minimum_free_heap_size(),(unsigned)CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ,(unsigned)configuration.backhaul_mcs,(unsigned long)boot,configured?"true":"false",(unsigned long long)configuration.run,configuration.channel,
        configured?(char *)configuration.wire+84:"",(unsigned long)received,(unsigned long)forwarded,
        (unsigned long)usb_errors,(unsigned long)(rejected+gw_io_drops()),(unsigned)uxQueueMessagesWaiting(gw_incoming()),
        (unsigned long)host_acks,(unsigned long)ack_submissions,(unsigned long)polls,(unsigned long)gw_io_mac_failures(),
        (unsigned)CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS,(unsigned long)ack_skipped_age,(unsigned long)ack_skipped_busy,(unsigned long)ack_submit_errors,
        (unsigned long)ack_age_samples,(unsigned long)ack_age_max_us,(unsigned long long)ack_age_total_us,
        (unsigned long)ack_age_le_2ms,(unsigned long)ack_age_le_5ms,(unsigned long)ack_age_le_10ms);
    if(n>0&&n<sizeof(p)&&rr_enabled()){
        /* Relay images do not enable BLE; omit that disabled transport's
         * verbose debug fields to keep discovery within the 1400-byte frame. */
        char *start=strstr(p,"\"wireless_version\"");
        char *end=strstr(p,"\"free_heap_bytes\"");
        if(start&&end&&end>start){memmove(start,end,strlen(end)+1);n=strlen(p);}
        int extra=snprintf(p+n-1,sizeof(p)-(n-1),
            ",\"relay_version\":1,\"relay_recovery_version\":1,\"relay_transport\":\"espnow_uart\","
            "\"relay_paired\":%s,\"relay_ready\":%s,\"relay_fault\":%s,"
            "\"relay_failure_reason\":\"%s\",\"relay_drops\":%lu,"
            "\"relay_peer_changes\":%lu,\"relay_retries\":%lu,\"relay_queued_bytes\":%u,"
            "\"relay_peer_queued_bytes\":%lu,\"relay_peer_queue_peak\":%lu,"
            "\"relay_peer_retries\":%lu,\"relay_uart_errors\":%lu}",
            rr_paired()?"true":"false",rr_ready()?"true":"false",rr_faulted()?"true":"false",
            rr_failure_reason(),(unsigned long)rr_drops(),(unsigned long)rr_peer_changes(),
            (unsigned long)rr_retries(),(unsigned)rr_queued_bytes(),
            (unsigned long)relay_peer_queued,(unsigned long)relay_peer_peak,
            (unsigned long)relay_peer_retries,(unsigned long)relay_uart_errors);
        if(extra<0||extra>=sizeof(p)-(n-1))return;
        n=n-1+extra;
    }
    if(n>0&&n<sizeof(p))gw_usb_write(CSI_SERIAL_TYPE_DEVICE_STATUS,(uint8_t *)p,n);
}
static void usb_reader(void *arg)
{
    (void)arg;static gw_message_t command;
    for(;;){uint8_t type;size_t n;
        if(gw_usb_read(&type,command.data,&n)){
            command.size=n;command.source[0]=type;
            if(!xQueueSend(commands,&command,pdMS_TO_TICKS(20)))++usb_errors;
        }
    }
}
static void command(const gw_message_t *m)
{
    if(m->source[0]==CSI_SERIAL_TYPE_DISCOVER_REQUEST){status();return;}
    if(m->source[0]==RR_USB_RECOVER){
        bool ok=rr_enabled()&&rr_paired()&&!configured&&m->size==4&&!memcmp(m->data,"CRRC",4);
        gw_usb_write(GW_RESPONSE,(const uint8_t *)(ok?"ok":"error"),ok?2:5);
        if(ok){vTaskDelay(pdMS_TO_TICKS(100));esp_restart();}return;
    }
    if(m->source[0]==WL_USB_PAIR){
        bool ok=!configured&&(rr_enabled()?rr_pair(m->data,m->size):wl_pair(m->data,m->size));
        gw_usb_write(WL_USB_PAIR_ACK,(const uint8_t *)(ok?"ok":"error"),ok?2:5);
        if(ok){vTaskDelay(pdMS_TO_TICKS(100));esp_restart();}return;
    }
    if(m->source[0]==WL_USB_REQUEST){
        if(m->size<1||!(rr_enabled()?rr_send(m->data[0],m->data+1,m->size-1):wl_send(m->data[0],m->data+1,m->size-1))){
            const uint8_t error[]={GW_RESPONSE,'e','r','r','o','r'};gw_usb_write(WL_USB_RESPONSE,error,sizeof(error));
        }return;
    }
    if(m->source[0]==GW_ACK&&configured&&!configuration.application_ack){++rejected;return;}
    if(m->source[0]==GW_ACK&&configured&&gw_check(m->data,m->size,"CGAK",GW_ACK_SIZE)){
        int index=gw_slot(&configuration,m->data+24);
        if(index<0||csi_clock_read_u64(m->data+4)!=configuration.run||
           csi_clock_read_u32(m->data+16)!=last_rx_boot[index]||csi_clock_read_u32(m->data+12)!=transmitter_boot){++rejected;return;}
        ++host_acks;
        /* Cache host acceptance only. Never synthesize it from MAC success. */
        bool cached=false;
        for(unsigned i=0;i<128;++i)if(!memcmp(cache[i],m->data,GW_ACK_SIZE)){cached=true;break;}
        if(!cached)memcpy(cache[cache_next++%128],m->data,GW_ACK_SIZE);
        uint64_t now=esp_timer_get_time(),seen=last_seen[index];
        uint64_t age=now>=seen?now-seen:UINT64_MAX;
        uint64_t limit=(uint64_t)CONFIG_CSI_GATEWAY_ACK_MAX_AGE_MS*1000;
        if(limit>(uint64_t)configuration.slot_ms*1000)limit=(uint64_t)configuration.slot_ms*1000;
        if(seen&&age!=UINT64_MAX){
            ++ack_age_samples;ack_age_total_us+=age;
            if(age>ack_age_max_us)ack_age_max_us=age>UINT32_MAX?UINT32_MAX:(uint32_t)age;
            ack_age_le_2ms+=age<=2000;ack_age_le_5ms+=age<=5000;ack_age_le_10ms+=age<=10000;
        }
        /* Cache first. A shorter activity window is an opt-in experiment,
         * not proof that the receiver is still on-channel or a delivery ACK. */
        if(!seen||age>=limit)++ack_skipped_age;
        else if(!gw_send_idle())++ack_skipped_busy;
        else if(gw_send(m->data+24,m->data,GW_ACK_SIZE,0))++ack_submissions;
        else ++ack_submit_errors;
        return;
    }
    if(m->source[0]!=GW_CONTROL)return;
    bool ok=false;gw_config_t next;
    if(gw_config_decode(m->data,m->size,&next)&&!memcmp(next.wire+32,mac,6)){
        if((!rr_paired()||next.channel==rr_channel())&&
           (!configured||!memcmp(configuration.wire,next.wire,GW_CONFIG_SIZE))){
            configuration=next;
            ESP_ERROR_CHECK(esp_wifi_set_channel(next.channel,WIFI_SECOND_CHAN_NONE));
            for(unsigned i=0;i<next.count;++i){
                gw_peer(next.wire+44+6*i,false);
                if(!gw_peer_set_mcs(next.wire+44+6*i,next.backhaul_mcs))abort();
            }
            if(!configured){memset(cache,0,sizeof(cache));memset(last_rx_boot,0,sizeof(last_rx_boot));}
            configured=true;ok=true;
        }
    }else if(m->size==16&&!memcmp(m->data,"CGTB",4)&&configured&&csi_clock_read_u64(m->data+4)==configuration.run){
        transmitter_boot=csi_clock_read_u32(m->data+12);ok=true;
    }else if(m->size==12&&!memcmp(m->data,"CGSP",4)&&csi_clock_read_u64(m->data+4)==configuration.run){
        configured=false;transmitter_boot=0;memset(cache,0,sizeof(cache));ok=true;
    }
    wl_session_active(configured);
    rr_session_active(configured);
    gw_usb_write(GW_RESPONSE,(const uint8_t *)(ok?"ok":"error"),ok?2:5);
}
static void radio(const gw_message_t *m)
{
    if(rr_receive(m->source,m->data,m->size)){relay_flush();return;}
    if(!configured||!transmitter_boot)return;
    int index=gw_slot(&configuration,m->source);if(index<0){++rejected;return;}
    if(gw_envelope_valid(m->data,m->size)){
        if(memcmp(m->data+28,m->source,6)||csi_clock_read_u64(m->data+8)!=configuration.run||csi_clock_read_u32(m->data+16)!=transmitter_boot){++rejected;return;}
        last_rx_boot[index]=csi_clock_read_u32(m->data+20);last_seen[index]=m->received;++received;
        if(gw_usb_write(GW_DATA,m->data,m->size))++forwarded;else ++usb_errors;
    }else if(configuration.application_ack&&configuration.bitmap_ack&&gw_bitmap_valid(m->data,m->size,false)&&
        csi_clock_read_u64(m->data+8)==configuration.run&&csi_clock_read_u32(m->data+16)==transmitter_boot&&
        !memcmp(m->data+24,m->source,6)){
        uint8_t response[GW_BITMAP_SIZE];
        last_seen[index]=m->received;++polls;
        if(gw_bitmap_reply(m->data,&cache[0][0],128,response))ack_submissions+=gw_send(m->source,response,sizeof(response),1);
    }else if(configuration.application_ack&&gw_check(m->data,m->size,"CGPL",GW_ACK_SIZE)&&
        csi_clock_read_u64(m->data+4)==configuration.run&&!memcmp(m->data+24,m->source,6)){
        last_seen[index]=m->received;++polls;
        uint32_t b=csi_clock_read_u32(m->data+16);
        for(unsigned i=0;i<128;++i)if(!memcmp(cache[i],"CGAK",4)&&!memcmp(cache[i]+24,m->source,6)&&
            csi_clock_read_u32(cache[i]+16)==b&&csi_clock_read_u32(cache[i]+12)==csi_clock_read_u32(m->data+12)&&
            csi_clock_read_u32(cache[i]+20)==csi_clock_read_u32(m->data+20)){
            ack_submissions+=gw_send(m->source,cache[i],GW_ACK_SIZE,1);break;}
    }else ++rejected;
}
void app_main(void)
{
    csi_board_init();ESP_ERROR_CHECK(nvs_flash_init());
    boot=esp_random();ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_WIFI_STA));
    usb_serial_jtag_driver_config_t usb={.tx_buffer_size=16384,.rx_buffer_size=4096};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    ESP_ERROR_CHECK(esp_netif_init());ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t wifi=WIFI_INIT_CONFIG_DEFAULT();ESP_ERROR_CHECK(esp_wifi_init(&wifi));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    /* IDF accepts b/g/n together on 2.4 GHz; per-peer configuration pins the negotiated HT20 long-GI rate. */
    ESP_ERROR_CHECK(esp_wifi_start());ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA,WIFI_PROTOCOL_11B|WIFI_PROTOCOL_11G|WIFI_PROTOCOL_11N));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA,WIFI_BW20));ESP_ERROR_CHECK(esp_wifi_set_country_code("ID",true));
    ESP_ERROR_CHECK(esp_wifi_set_channel(6,WIFI_SECOND_CHAN_NONE));ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    gw_io_init();commands=xQueueCreate(16,sizeof(gw_message_t));
    wl_init(1,mac,wireless_received,NULL);
    rr_init(1,mac,relay_received,NULL);
    if(!commands||xTaskCreate(usb_reader,"gateway_usb",6144,NULL,5,NULL)!=pdPASS)abort();
    static gw_message_t message;uint64_t last_status=0;
    for(;;){
        while(xQueueReceive(commands,&message,0))command(&message);
        if(xQueueReceive(gw_incoming(),&message,pdMS_TO_TICKS(1)))radio(&message);
        rr_poll();
        if((uint64_t)esp_timer_get_time()-last_status>1000000){status();last_status=esp_timer_get_time();}
    }
}
