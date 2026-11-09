#include "sdkconfig.h"
#include "wireless_link.h"
#if CONFIG_CSI_WIRELESS_TRANSMITTER
_Static_assert(CONFIG_BT_NIMBLE_MSYS_2_BLOCK_SIZE>=1536,"wireless advertisements require complete-packet mbufs");
_Static_assert(CONFIG_BT_NIMBLE_MSYS_2_BLOCK_COUNT>=8,"wireless stream requires a bounded complete-packet pool");
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/message_buffer.h"
#include "freertos/semphr.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "nvs.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_gap.h"
#include "os/os_mempool.h"
#include "os/os_mbuf.h"
#include "psa/crypto.h"
#include <stdio.h>
static psa_key_id_t authentication_key;
static uint8_t role,local[6],pairing[WL_PAIR_SIZE],address_type;
static bool paired,fault;static volatile bool synced,advertising,ready,session_active;
static volatile bool periodic_link,sync_creating;
static bool scanning,sync_candidate;static ble_addr_t sync_address;static uint16_t sync_handle;
static const char *failure_reason="none";
static volatile uint32_t advertised_packets,received_packets,authenticated_packets;
static volatile uint32_t memory_stalls,ingress_stalls;
static int setup_error;
static bool flush_advertisement;
static uint8_t decompressed[WL_LOGICAL];
static uint32_t uncompressed_bytes,compressed_bytes,echo_misses;
static size_t staged;
static uint32_t expected_restart;
static uint64_t restart_limit;
static void fail(const char *reason){if(!fault)failure_reason=reason;fault=true;}
static uint32_t counter,peer_counter,known_peer_counter,drops,peer_changes;
static uint64_t nonce,peer_nonce,last_received;
static wl_stream_t stream;
static wl_emit_t receiver;static void *receiver_context;
static QueueHandle_t incoming;
static MessageBufferHandle_t outgoing;
/* set_data consumes/frees its mbuf synchronously. One complete application
 * buffer is sufficient; cached controller data belongs to separate MSYS pools. */
static os_membuf_t advertisement_memory[OS_MEMPOOL_SIZE(1,1536)];
static struct os_mempool advertisement_mempool;
static struct os_mbuf_pool advertisement_pool;
static SemaphoreHandle_t writers;
typedef struct {uint16_t size;ble_addr_t address;bool periodic;uint8_t data[WL_PACKET];} packet_t;
static uint64_t clock_us(void){return esp_timer_get_time();}
static bool store_u32(const char *key,uint32_t value)
{
    nvs_handle_t handle;if(nvs_open("wireless",NVS_READWRITE,&handle)!=ESP_OK)return false;
    bool ok=nvs_set_u32(handle,key,value)==ESP_OK&&nvs_commit(handle)==ESP_OK;nvs_close(handle);return ok;
}
bool wl_pair(const uint8_t *p,size_t n)
{
    if(n!=WL_PAIR_SIZE||memcmp(p,"CWPS",4)||memcmp(p+(role?10:4),local,6))return false;
    uint8_t any=0;for(unsigned i=16;i<48;++i)any|=p[i];if(!any)return false;
    nvs_handle_t handle;if(nvs_open("wireless",NVS_READWRITE,&handle)!=ESP_OK)return false;
    bool ok=nvs_set_blob(handle,"pair",p,n)==ESP_OK&&nvs_set_u32(handle,"boot",0)==ESP_OK&&nvs_set_u32(handle,"peer",0)==ESP_OK&&nvs_commit(handle)==ESP_OK;
    nvs_close(handle);return ok;
}
bool wl_paired(void){return paired;}
bool wl_ready(void){return ready&&!fault&&(role||periodic_link)&&clock_us()-last_received<1000000;}
bool wl_faulted(void){return fault;}
const char *wl_failure_reason(void){return failure_reason;}
const char *wl_debug(void)
{static char value[192];snprintf(value,sizeof(value),"s%u/a%u/t%lu/r%lu/v%lu/m%lu/c%lu/%lu/e%d/h%lu/p%lu/u%lu/q%lu/k%u",synced,advertising,(unsigned long)advertised_packets,(unsigned long)received_packets,(unsigned long)authenticated_packets,(unsigned long)memory_stalls,(unsigned long)compressed_bytes,(unsigned long)uncompressed_bytes,setup_error,(unsigned long)echo_misses,(unsigned long)peer_counter,(unsigned long)((clock_us()-last_received)/1000),(unsigned long)ingress_stalls,periodic_link);return value;}
uint32_t wl_drops(void){return drops;}
uint32_t wl_peer_changes(void){return peer_changes;}
void wl_session_active(bool active){session_active=active;}
void wl_host_failure(void){fail("host_usb_forward");}
void wl_expect_peer_restart(void)
{
    if(role!=1||session_active||!peer_counter||fault)return;
    expected_restart=peer_counter;restart_limit=clock_us()+10000000;ready=false;
    for(unsigned i=0;i<WL_WINDOW;++i)stream.tx[i].used=false;
}
bool wl_send(uint8_t type,const uint8_t *p,size_t n)
{
    if(!paired||!wl_ready()||fault||!type||n+3>=WL_PAYLOAD||xSemaphoreTake(writers,pdMS_TO_TICKS(5))!=pdTRUE)return false;
    static uint8_t frame[WL_PAYLOAD];frame[0]=type;wl_w16(frame+1,n);memcpy(frame+3,p,n);
    bool ok=xMessageBufferSend(outgoing,frame,n+3,0)==n+3;if(!ok)++drops;xSemaphoreGive(writers);return ok;
}
static bool tag(const uint8_t *p,size_t n,uint8_t out[32])
{size_t size=0;return psa_mac_compute(authentication_key,PSA_ALG_HMAC(PSA_ALG_SHA_256),p,n,out,32,&size)==PSA_SUCCESS&&size==32;}
static bool deliver_block(const uint8_t *p,size_t n,void *context)
{
    (void)context;if(n<2||p[0]>1)return false;
    const uint8_t *body=p+1;size_t size=n-1;
    if(p[0]){size=wl_decompress(body,size,decompressed,sizeof(decompressed));body=decompressed;}
    if(!wl_frames_valid(body,size))return false;
    size_t offset=0;
    while(offset<size){size_t length=wl_u16(body+offset+1);receiver(body[offset],body+offset+3,length,receiver_context);if(fault)return false;offset+=length+3;}
    receiver(0,NULL,0,receiver_context);
    return !fault;
}
static void accept_packet(const packet_t *v)
{
    const uint8_t *p=v->data;size_t n=v->size;
    if(!wl_packet_valid(p,n,role,tag))return;
    ++authenticated_packets;
    uint32_t remote_counter=wl_u32(p+6);uint64_t remote_nonce=wl_u64(p+10),echo=wl_u64(p+18);
    if(!wl_epoch_valid(known_peer_counter,peer_counter,peer_nonce,remote_counter,remote_nonce))return;
    if(remote_counter!=peer_counter||remote_nonce!=peer_nonce){
        if(remote_counter==peer_counter||(remote_counter==known_peer_counter&&peer_counter))return;
        /* A persisted boot counter rejects old authenticated sessions after reboot. */
        if(remote_counter>known_peer_counter&&!store_u32("peer",remote_counter)){fail("peer_nvs");return;}
        if(peer_counter){
            ++peer_changes;
            if(session_active){fail("peer_restart");return;}
            memset(&stream,0,sizeof(stream));staged=0;ready=false;expected_restart=0;
            if(xSemaphoreTake(writers,pdMS_TO_TICKS(20))!=pdTRUE){fail("writer_reset");return;}
            xMessageBufferReset(outgoing);xSemaphoreGive(writers);
        }
        peer_counter=known_peer_counter=remote_counter;peer_nonce=remote_nonce;
    }
    if(!role&&v->periodic&&!periodic_link&&!sync_creating){sync_address=v->address;sync_candidate=true;}
    last_received=clock_us();if(echo!=nonce){ready=false;++echo_misses;return;}ready=expected_restart==0;
    if(!wl_stream_ack(&stream,wl_u32(p+30),p[34])){++drops;fail("invalid_ack");return;}
    uint32_t seq=wl_u32(p+26);size_t size=wl_u16(p+35);
    if(seq==WL_EMPTY){if(size){++drops;fail("invalid_empty");}return;}
    if(!wl_stream_receive(&stream,seq,p+WL_HEADER,size,deliver_block,NULL)){++drops;fail("receive_window");}
}
static int gap_event(struct ble_gap_event *event,void *unused)
{
    (void)unused;
    if(event->type==BLE_GAP_EVENT_ADV_COMPLETE){advertising=false;return 0;}
    if(!role&&event->type==BLE_GAP_EVENT_PERIODIC_SYNC){
        sync_creating=false;periodic_link=event->periodic_sync.status==0;
        if(periodic_link)sync_handle=event->periodic_sync.sync_handle;
        return 0;
    }
    if(!role&&event->type==BLE_GAP_EVENT_PERIODIC_SYNC_LOST){
        periodic_link=false;sync_creating=false;
        if(session_active)fail("periodic_sync_lost");
        return 0;
    }
    if(!role&&event->type==BLE_GAP_EVENT_PERIODIC_REPORT){
        if(!periodic_link||event->periodic_report.sync_handle!=sync_handle||event->periodic_report.data_status)return 0;
        packet_t packet={0};
        packet.size=wl_ad_decode(event->periodic_report.data,event->periodic_report.data_length,packet.data,sizeof(packet.data));
        ++received_packets;
        if(packet.size&&xQueueSend(incoming,&packet,0)!=pdTRUE)++ingress_stalls;
        return 0;
    }
    if(event->type!=BLE_GAP_EVENT_EXT_DISC)return 0;
    const struct ble_gap_ext_disc_desc *d=&event->ext_disc;
    /* HCI may split a complete extended advertisement into several reports. */
    static uint8_t partial[1650],source[6];static uint8_t sid;static size_t used;static uint64_t started;
    if(d->sid!=((role^1)+4))return 0;
    ++received_packets;
    if(used&&(memcmp(source,d->addr.val,6)||sid!=d->sid||clock_us()-started>100000)){used=0;}
    if(!used){memcpy(source,d->addr.val,6);sid=d->sid;started=clock_us();}
    if(d->data_status==2||used+d->length_data>sizeof(partial)){used=0;return 0;}
    memcpy(partial+used,d->data,d->length_data);used+=d->length_data;
    if(d->data_status==1)return 0;
    packet_t packet={.address=d->addr,.periodic=d->periodic_adv_itvl!=0};
    packet.size=wl_ad_decode(partial,used,packet.data,sizeof(packet.data));used=0;
    /* Queue admission is before authentication/ARQ acceptance. A missed air
     * datagram receives no new ACK and can be retried within its original TTL. */
    if(packet.size&&xQueueSend(incoming,&packet,0)!=pdTRUE)++ingress_stalls;
    return 0;
}
static bool start_scan(void)
{
    struct ble_gap_ext_disc_params scan={.passive=1,.itvl=40,.window=40};
    setup_error=ble_gap_ext_disc(address_type,0,0,0,0,0,&scan,NULL,gap_event,NULL);
    if(setup_error){fail("scan_start");return false;}
    scanning=true;return true;
}
static void on_sync(void)
{
    if((setup_error=ble_hs_id_infer_auto(0,&address_type))){fail("identity_setup");return;}
    struct ble_gap_ext_adv_params params={0};params.own_addr_type=address_type;
    params.primary_phy=BLE_HCI_LE_PHY_1M;params.secondary_phy=BLE_HCI_LE_PHY_2M;
    params.itvl_min=params.itvl_max=32;params.sid=role+4;params.tx_power=0x7f;
    if((setup_error=ble_gap_ext_adv_configure(0,&params,NULL,gap_event,NULL))){fail("adv_configure");return;}
    if(role){
        struct ble_gap_periodic_adv_params periodic={0};
        periodic.itvl_min=periodic.itvl_max=BLE_GAP_PERIODIC_ITVL_MS(20);
        if((setup_error=ble_gap_periodic_adv_configure(0,&periodic))||
           (setup_error=ble_gap_periodic_adv_start(0))){fail("periodic_start");return;}
        periodic_link=true;
    }
    if(!start_scan())return;
    synced=true;
}
static void host_task(void *unused){(void)unused;nimble_port_run();nimble_port_freertos_deinit();}
static void worker(void *unused)
{
    (void)unused;static packet_t packet;static uint8_t payload[WL_LOGICAL],raw[WL_PACKET],advert[1650];
    for(;;){
        while(xQueueReceive(incoming,&packet,0))if(!fault)accept_packet(&packet);
        uint64_t now=clock_us();
        if(expected_restart&&now>restart_limit)fail("peer_reboot_timeout");
        if(!synced||fault){vTaskDelay(pdMS_TO_TICKS(2));continue;}
        if(!role){
            if(sync_candidate&&!periodic_link&&!sync_creating){
                struct ble_gap_periodic_sync_params params={.skip=0,.sync_timeout=100};
                sync_candidate=false;sync_creating=true;
                int rc=ble_gap_periodic_adv_sync_create(&sync_address,5,&params,gap_event,NULL);
                if(rc){sync_creating=false;setup_error=rc;}
            }
            if(periodic_link&&session_active&&scanning){
                if((setup_error=ble_gap_disc_cancel())){fail("scan_cancel");continue;}
                scanning=false;
            }else if(!session_active&&!scanning&&!start_scan())continue;
        }
        if(ready){
            bool free=stream.next_tx-stream.acknowledged<WL_WINDOW;
            if(free){size_t next;
                while((next=xMessageBufferNextLengthBytes(outgoing))&&staged+next<=WL_LOGICAL){
                    size_t n=xMessageBufferReceive(outgoing,payload+staged,WL_LOGICAL-staged,0);if(!n)break;staged+=n;
                }
                if(staged){
                    size_t chosen=0;
                    size_t capacity=role?WL_PERIODIC_PAYLOAD:WL_PAYLOAD;
                    size_t encoded=wl_encode_frames(payload,staged,raw+WL_HEADER,capacity,&chosen);
                    /* Large provisioning frames use ordinary extended ads only
                     * while the transmitter is idle and scanning. */
                    if(!encoded&&role&&!session_active)encoded=wl_encode_frames(payload,staged,raw+WL_HEADER,WL_PAYLOAD,&chosen);
                    if(!encoded){++drops;fail("logical_frame");continue;}
                    if(!wl_stream_add(&stream,raw+WL_HEADER,encoded,now)){++drops;fail("tx_window");continue;}
                    uncompressed_bytes+=chosen;compressed_bytes+=encoded;
                    memmove(payload,payload+chosen,staged-chosen);staged-=chosen;
                }
            }
        }
        wl_slot_t *selected=NULL;
        for(unsigned i=0;i<WL_WINDOW;++i)if(stream.tx[i].used){
            wl_slot_t *v=&stream.tx[i];
            if(now-v->created>750000){++drops;fail("packet_expired");break;}
            if(!selected||v->sent<selected->sent)selected=v;
        }
        if(fault)continue;
        if(advertising){vTaskDelay(pdMS_TO_TICKS(2));continue;}
        /* Replacing controller-cached large data with an ACK-only packet can
         * release its chained mbufs before retry. Pending bytes/deadlines stay
         * owned by the ARQ window; this empty packet acknowledges no new data. */
        if(flush_advertisement)selected=NULL;
        memcpy(raw,"CWL2",4);raw[4]=2;raw[5]=role;wl_w32(raw+6,counter);wl_w64(raw+10,nonce);wl_w64(raw+18,(!role&&!periodic_link)?0:peer_nonce);
        wl_w32(raw+26,selected?selected->sequence:WL_EMPTY);wl_w32(raw+30,stream.next_rx);raw[34]=wl_stream_mask(&stream);
        size_t n=selected?selected->size:0;
        if(n)memcpy(raw+WL_HEADER,selected->data,n);
        wl_w16(raw+35,n);
        uint8_t digest[32];if(!tag(raw,WL_HEADER+n,digest)){fail("hmac");continue;}memcpy(raw+WL_HEADER+n,digest,WL_TAG);
        size_t size=wl_ad_encode(raw,WL_HEADER+n+WL_TAG,advert,sizeof(advert));
        if(role){
            static uint8_t ack_raw[WL_HEADER+WL_TAG],ack_ad[WL_HEADER+WL_TAG+4];
            const uint8_t *periodic_data=advert;size_t periodic_size=size;
            if(n>WL_PERIODIC_PAYLOAD){
                memcpy(ack_raw,raw,WL_HEADER);wl_w32(ack_raw+26,WL_EMPTY);wl_w16(ack_raw+35,0);
                if(!tag(ack_raw,WL_HEADER,digest)){fail("hmac");continue;}
                memcpy(ack_raw+WL_HEADER,digest,WL_TAG);
                periodic_size=wl_ad_encode(ack_raw,sizeof(ack_raw),ack_ad,sizeof(ack_ad));periodic_data=ack_ad;
            }
            struct os_mbuf *periodic=os_mbuf_get_pkthdr(&advertisement_pool,0);
            if(!periodic){++memory_stalls;vTaskDelay(pdMS_TO_TICKS(2));continue;}
            if(os_mbuf_append(periodic,periodic_data,periodic_size)){os_mbuf_free_chain(periodic);++memory_stalls;continue;}
            int rc=ble_gap_periodic_adv_set_data(0,periodic);
            if(rc){setup_error=rc;++memory_stalls;vTaskDelay(pdMS_TO_TICKS(2));continue;}
        }
        struct os_mbuf *data=os_mbuf_get_pkthdr(&advertisement_pool,0);
        if(!data){++memory_stalls;vTaskDelay(pdMS_TO_TICKS(2));continue;}
        if(os_mbuf_append(data,advert,size)){os_mbuf_free_chain(data);++memory_stalls;vTaskDelay(pdMS_TO_TICKS(2));continue;}
        int rc=ble_gap_ext_adv_set_data(0,data);
        if(rc){
            if(rc==BLE_HS_ENOMEM||rc==BLE_HS_EBUSY||rc==BLE_HS_HCI_ERR(BLE_ERR_MEM_CAPACITY)){setup_error=rc;flush_advertisement=true;++memory_stalls;vTaskDelay(pdMS_TO_TICKS(2));continue;}
            setup_error=rc;++drops;fail("adv_data");continue;
        }
        advertising=true;rc=ble_gap_ext_adv_start(0,0,1);
        if(rc){advertising=false;
            if(rc==BLE_HS_ENOMEM||rc==BLE_HS_EBUSY||rc==BLE_HS_HCI_ERR(BLE_ERR_MEM_CAPACITY)){setup_error=rc;flush_advertisement=true;++memory_stalls;vTaskDelay(pdMS_TO_TICKS(2));continue;}
            setup_error=rc;++drops;fail("adv_start");continue;
        }
        flush_advertisement=false;
        ++advertised_packets;
        if(selected)selected->sent=now;
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
void wl_init(uint8_t r,const uint8_t mac[6],wl_emit_t receive,void *context)
{
    role=r;memcpy(local,mac,6);receiver=receive;receiver_context=context;
    nvs_handle_t handle;size_t size=sizeof(pairing);
    if(nvs_open("wireless",NVS_READWRITE,&handle)!=ESP_OK)return;
    bool ok=nvs_get_blob(handle,"pair",pairing,&size)==ESP_OK&&size==sizeof(pairing)&&!memcmp(pairing,"CWPS",4)&&!memcmp(pairing+(role?10:4),local,6);
    nvs_get_u32(handle,"boot",&counter);nvs_get_u32(handle,"peer",&known_peer_counter);nvs_close(handle);
    if(!ok)return;
    if(counter==UINT32_MAX||!store_u32("boot",++counter)){fail("boot_nvs");return;}
    nonce=((uint64_t)esp_random()<<32)|esp_random();if(!nonce)nonce=1;
    incoming=xQueueCreate(role?8:WL_WINDOW,sizeof(packet_t));outgoing=xMessageBufferCreate(16384);writers=xSemaphoreCreateMutex();
    if(!incoming||!outgoing||!writers)abort();
    paired=true;
    if(os_mempool_init(&advertisement_mempool,1,1536,advertisement_memory,"csi_adv")||
       os_mbuf_pool_init(&advertisement_pool,&advertisement_mempool,1536,1))abort();
    if(psa_crypto_init()!=PSA_SUCCESS)abort();
    psa_key_attributes_t attributes=PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_type(&attributes,PSA_KEY_TYPE_HMAC);psa_set_key_bits(&attributes,256);
    psa_set_key_usage_flags(&attributes,PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attributes,PSA_ALG_HMAC(PSA_ALG_SHA_256));
    if(psa_import_key(&attributes,pairing+16,32,&authentication_key)!=PSA_SUCCESS)abort();
    psa_reset_key_attributes(&attributes);
    ESP_ERROR_CHECK(nimble_port_init());ble_hs_cfg.sync_cb=on_sync;
    nimble_port_freertos_init(host_task);
    if(xTaskCreate(worker,"csi_wireless",6144,NULL,4,NULL)!=pdPASS)abort();
}
#else
void wl_init(uint8_t r,const uint8_t m[6],wl_emit_t receive,void *context){(void)r;(void)m;(void)receive;(void)context;}
bool wl_pair(const uint8_t *p,size_t n){(void)p;(void)n;return false;}
bool wl_send(uint8_t t,const uint8_t *p,size_t n){(void)t;(void)p;(void)n;return false;}
bool wl_paired(void){return false;}bool wl_ready(void){return false;}bool wl_faulted(void){return false;}
const char *wl_failure_reason(void){return "disabled";}
const char *wl_debug(void){return "disabled";}
uint32_t wl_drops(void){return 0;}uint32_t wl_peer_changes(void){return 0;}
void wl_session_active(bool active){(void)active;}
void wl_host_failure(void){}
void wl_expect_peer_restart(void){}
#endif
