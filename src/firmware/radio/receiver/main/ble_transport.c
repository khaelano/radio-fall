/* BLE notification transport. Application grants do not reserve RF airtime. */
#include "sdkconfig.h"
#if CONFIG_CSI_OUTPUT_BLE
#include <inttypes.h>
#include <stdio.h>
#include "ble_transport.h"
#include "radio_diagnostics.h"
#include "radio_board.h"
#include "ble_queue.h"
#include "ble_grants.h"
#include "ble_delivery_policy.h"
#include "ble_flow.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

/* Highest received sequence proves earlier controller submissions have drained
 * only on the single ordered ATT bearer used by this transport. */
_Static_assert(CONFIG_BT_NIMBLE_EATT_CHAN_NUM == 0, "CSI progress credits require EATT_CHAN_NUM=0");

#define UUID_BYTES(t) t,0x18,0xb7,0x1b,0xc0,0x52,0xe0,0xae,0x67,0x4a,0x51,0x8a,0x10,0xc5,0x71,0x4d
static const ble_uuid128_t service_uuid = BLE_UUID128_INIT(UUID_BYTES(0));
static const ble_uuid128_t status_uuid = BLE_UUID128_INIT(UUID_BYTES(1));
static const ble_uuid128_t data_uuid = BLE_UUID128_INIT(UUID_BYTES(2));
static const ble_uuid128_t control_uuid = BLE_UUID128_INIT(UUID_BYTES(3));
static const ble_uuid128_t stats_uuid = BLE_UUID128_INIT(UUID_BYTES(4));
static const ble_uuid128_t timing_uuid = BLE_UUID128_INIT(UUID_BYTES(5));
static const ble_uuid128_t flow_uuid = BLE_UUID128_INIT(UUID_BYTES(6));
static const char *TAG = "csi_ble";
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static csi_radio_profile_t radio_profile;
static csi_ble_config_t config;
static uint8_t receiver_mac[6], own_address_type, receiver_index;
static uint32_t receiver_boot, transmitter_boot, next_batch;
static uint64_t drain_until;
static uint32_t last_sequence;
static bool configured, epoch_known, observed;
static uint16_t connection = BLE_HS_CONN_HANDLE_NONE, data_handle, mtu = 23;
static uint16_t interval, latency, supervision, tx_octets=27, rx_octets=27;
static uint8_t tx_phy, rx_phy;
static bool subscribed, notify_busy;
static uint32_t pending_batch;
static ble_record_queue_t records;
static uint32_t built, sent, send_errors, retries, callbacks, connection_changes;
static uint32_t sensing_missing, sensing_reordered;
static uint64_t last_submit_us, last_complete_us;
static TaskHandle_t writer_handle;
static ble_flow_t flow;
static uint64_t flow_run;
static uint32_t flow_tx_boot, flow_tag;
static uint32_t flow_receipts, flow_invalid_receipts, admission_drops, transfer_expired;
static uint32_t credit_wait_ticks, credit_disconnects, submitted_fragments, submitted_bytes;
static uint32_t submission_failures, last_submission_error;

/* Sampled diagnostics only: this ring never stores CSI bytes or controls ownership. */
typedef struct {
    uint32_t id, flags;
    uint64_t capture, built, first, last, ack, expired;
} batch_timing_t;
static batch_timing_t timings[8];
static batch_timing_t *timing_for(uint32_t id)
{
    batch_timing_t *t = &timings[id % 8];
    return t->flags && t->id == id ? t : NULL;
}

static void writer_wait(void)
{
    ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1));
}

typedef struct {
    bool used;
    uint32_t id;
    uint16_t length, offset;
    uint8_t attempts;
    uint64_t oldest, waiting_since, started;
    uint8_t data[CSI_BLE_MAX_PACKET];
} batch_t;
static batch_t batches[4];
static ble_grants_t grant_state;

static void advertise(void);

static batch_t *find_batch(uint32_t id)
{
    for (unsigned i = 0; i < 4; ++i)
        if (batches[i].used && batches[i].id == id) return &batches[i];
    return NULL;
}

static void reset_epoch(void)
{
    ble_queue_reset(&records, config.queue_capacity);
    memset(batches, 0, sizeof(batches));
    memset(&grant_state, 0, sizeof(grant_state));
    memset(timings, 0, sizeof(timings));
    observed = false;
}

bool csi_ble_observe(const uint8_t *data, size_t length, uint64_t received)
{
    if (length < CSI_BLE_SENSING_SIZE || data[4] != 3 ||
        csi_serial_crc32(data, 84) != csi_clock_read_u32(data + 84)) return false;
    portENTER_CRITICAL(&lock);
    ++callbacks;
    bool valid = configured && !drain_until &&
        csi_clock_read_u64(data + 40) == config.run_id &&
        !memcmp(data + 52, config.fingerprint, 16) &&
        !memcmp(data + 24, radio_profile.fingerprint, 16) &&
        csi_clock_read_u32(data + 68) == 1000000U / config.rate_hz && data[83] == 0;
    for (unsigned i = 0; valid && i < 3; ++i)
        valid = data[80+i] < config.receiver_count;
    if (!valid) { portEXIT_CRITICAL(&lock); return false; }
    uint32_t boot = csi_clock_read_u32(data + 48);
    if (!epoch_known || transmitter_boot != boot) {
        if (epoch_known && config.credit_flow) {
            /* A transmitter restart needs a new run. Credit debt is retained
             * until its old receipt arrives or the connection is torn down. */
            reset_epoch();configured=false;epoch_known=false;
            portEXIT_CRITICAL(&lock);return false;
        }
        reset_epoch(); transmitter_boot = boot; epoch_known = true;
        if(config.credit_flow && !flow.count) {
            flow_run=config.run_id;flow_tx_boot=boot;flow_tag=config.flow_token;
        }
    }
    uint32_t sequence = csi_clock_read_u32(data + 8);
    if (observed) {
        uint32_t forward = sequence - last_sequence;
        if (!forward || forward >= 0x80000000U) {
            if (forward) ++sensing_reordered;
            portEXIT_CRITICAL(&lock); return false;
        }
        sensing_missing += forward - 1;
    }
    uint64_t enqueue = csi_clock_read_u64(data + 16);
    uint64_t deadline = csi_clock_read_u64(data + 72);
    if (!ble_grants_observe(&grant_state, &config, sequence, deadline, enqueue, received, data+80)) {
        portEXIT_CRITICAL(&lock); return false;
    }
    last_sequence = sequence; observed = true;
    portEXIT_CRITICAL(&lock);
    if (writer_handle) xTaskNotifyGive(writer_handle);
    return true;
}

bool csi_ble_enqueue(const uint8_t *record, uint16_t length, uint64_t captured)
{
    portENTER_CRITICAL(&lock);
    bool ok = configured && epoch_known && !drain_until &&
              ble_queue_push(&records, record, length, captured);
    portEXIT_CRITICAL(&lock);
    if (ok && writer_handle) xTaskNotifyGive(writer_handle);
    return ok;
}

static int status_read(struct ble_gatt_access_ctxt *ctxt, bool diagnostics)
{
    char json[512];
    portENTER_CRITICAL(&lock);
    unsigned queued = ble_queue_count(&records);
    uint64_t oldest = 0, now = esp_timer_get_time();
    for (unsigned i = 0; i < records.capacity; ++i)
        if (records.slots[i].state && (!oldest || records.slots[i].captured < oldest))
            oldest = records.slots[i].captured;
    uint32_t counts[] = {records.peak, records.captured, records.acknowledged, records.evicted, records.expired, records.rejected, records.epoch_dropped, retries, send_errors, sensing_missing, sensing_reordered, callbacks, connection_changes};
    csi_ble_config_t snapshot = config;
    uint32_t tx_boot_snapshot = transmitter_boot;
    uint16_t mtu_snapshot=mtu, interval_snapshot=interval, latency_snapshot=latency, supervision_snapshot=supervision;
    uint8_t tx_phy_snapshot=tx_phy, rx_phy_snapshot=rx_phy;
    uint16_t tx_octets_snapshot=tx_octets, rx_octets_snapshot=rx_octets;
    uint64_t submit_snapshot=last_submit_us, complete_snapshot=last_complete_us;
    bool ready = configured && subscribed;
    portEXIT_CRITICAL(&lock);
    uint32_t inventory_checksum = csi_serial_crc32((const uint8_t *)radio_profile.receiver_macs, 6*radio_profile.receiver_count);
    int n;
    if (!diagnostics) {
        n = snprintf(json, sizeof(json),
            "{\"protocol_version\":1,\"role\":\"receiver\",\"target\":\"" CONFIG_IDF_TARGET "\","
            "\"mac\":\"%02x:%02x:%02x:%02x:%02x:%02x\",\"boot_id\":%" PRIu32 ","
            "\"run_id\":\"%" PRIu64 "\",\"transmitter_boot_id\":%" PRIu32 ","
            "\"profile_fingerprint\":\"%s\",\"transport_fingerprint\":\"%s\","
            "\"reset_reason\":\"%s\",\"uptime_ms\":%" PRIu64 ",\"csi_transport\":\"ble\","
            "\"board\":\"%s\",\"antenna\":\"%s\","
            "\"sensing_version\":3,"
            "\"ready\":%s,\"inventory_crc\":%" PRIu32 "}",
            receiver_mac[0], receiver_mac[1], receiver_mac[2], receiver_mac[3],
            receiver_mac[4], receiver_mac[5], receiver_boot, snapshot.run_id, tx_boot_snapshot,
            radio_profile.fingerprint, snapshot.fingerprint,
            csi_reset_reason_name(), now / 1000,
            csi_board_name(), csi_board_antenna(),
            ready ? "true" : "false", inventory_checksum);
    } else {
        /* A fixed-width vector fits one read at MTU 247 and avoids changing
         * decimal widths while the counters advance. All values are uint64. */
        uint64_t values[] = {
            mtu_snapshot, tx_phy_snapshot, rx_phy_snapshot, interval_snapshot, latency_snapshot,
            supervision_snapshot, queued, oldest ? now-oldest : 0,
            counts[0], counts[1], counts[2], counts[3], counts[4], counts[5], counts[6],
            counts[7], counts[8], counts[9], counts[10], counts[11], counts[12],
            submit_snapshot, complete_snapshot, tx_octets_snapshot, rx_octets_snapshot,
            heap_caps_get_free_size(MALLOC_CAP_8BIT), heap_caps_get_minimum_free_size(MALLOC_CAP_8BIT)};
        uint8_t vector[8 + 27*8];
        _Static_assert(sizeof(values)/sizeof(values[0]) == 27, "BLE diagnostic vector size");
        memcpy(vector, "CBSS", 4); vector[4] = 1; vector[5] = 27;
        csi_clock_write_u16(vector+6, sizeof(vector));
        for (unsigned i = 0; i < 27; ++i) csi_clock_write_u64(vector+8+8*i, values[i]);
        return os_mbuf_append(ctxt->om, vector, sizeof(vector)) ? BLE_ATT_ERR_INSUFFICIENT_RES : 0;
    }
    if (n < 0 || (size_t)n >= sizeof(json)) return BLE_ATT_ERR_INSUFFICIENT_RES;
    return os_mbuf_append(ctxt->om, json, n) ? BLE_ATT_ERR_INSUFFICIENT_RES : 0;
}

static int timing_read(struct ble_gatt_access_ctxt *ctxt)
{
    /* Fits one ATT read at MTU 247; regenerating a long-read value would tear. */
    uint8_t data[8+4*56] = {0};
    memcpy(data, "CBTM", 4); data[4] = 1; data[5] = 4;
    csi_clock_write_u16(data+6, sizeof(data));
    portENTER_CRITICAL(&lock);
    for (unsigned i=0; i<4; ++i) {
        batch_timing_t empty={0};
        batch_timing_t *t=timing_for(next_batch-1-i);
        if(!t) t=&empty;
        uint8_t *p=data+8+i*56;
        csi_clock_write_u32(p,t->id); csi_clock_write_u32(p+4,t->flags);
        uint64_t values[]={t->capture,t->built,t->first,t->last,t->ack,t->expired};
        for(unsigned j=0;j<6;++j) csi_clock_write_u64(p+8+8*j,values[j]);
    }
    portEXIT_CRITICAL(&lock);
    return os_mbuf_append(ctxt->om,data,sizeof(data)) ? BLE_ATT_ERR_INSUFFICIENT_RES : 0;
}

static int flow_read(struct ble_gatt_access_ctxt *ctxt)
{
    uint8_t data[8+20*8];memcpy(data,"CBFS",4);data[4]=1;data[5]=20;
    csi_clock_write_u16(data+6,sizeof(data));
    portENTER_CRITICAL(&lock);
    uint64_t values[]={flow_run,flow_tx_boot,receiver_boot,flow_tag,
        flow.have_issued ? flow.next_serial-1 : 0,flow.have_acked ? flow.acked : 0,
        flow.count,flow.bytes,flow.peak,flow.peak_bytes,flow_receipts,flow_invalid_receipts,
        admission_drops,transfer_expired,credit_wait_ticks,credit_disconnects,
        submitted_fragments,submitted_bytes,submission_failures,last_submission_error};
    for(unsigned i=0;i<20;++i)csi_clock_write_u64(data+8+8*i,values[i]);
    portEXIT_CRITICAL(&lock);
    return os_mbuf_append(ctxt->om,data,sizeof(data)) ? BLE_ATT_ERR_INSUFFICIENT_RES : 0;
}

static int access(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    (void)conn; (void)attr;
    if ((intptr_t)arg == 1 || (intptr_t)arg == 2) return status_read(ctxt, (intptr_t)arg == 2);
    if ((intptr_t)arg == 3) return timing_read(ctxt);
    if ((intptr_t)arg == 4) return flow_read(ctxt);
    uint8_t data[CSI_BLE_CONFIG_MAX_SIZE];
    uint16_t length = OS_MBUF_PKTLEN(ctxt->om);
    if (length > sizeof(data) || os_mbuf_copydata(ctxt->om, 0, length, data))
        return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
    if ((length == CSI_BLE_CONFIG_SIZE || length == CSI_BLE_CONFIG_MAX_SIZE) && !memcmp(data, "CBLC", 4)) {
        csi_ble_config_t next;
        if (!csi_ble_config_decode(data, length, &next) ||
            next.receiver_count != radio_profile.receiver_count ||
            next.rate_hz != radio_profile.nominal_rate_hz ||
            next.inventory_crc != csi_serial_crc32((const uint8_t *)radio_profile.receiver_macs, 6*radio_profile.receiver_count)) return BLE_ATT_ERR_UNLIKELY;
        portENTER_CRITICAL(&lock);
        if (flow.count) {portEXIT_CRITICAL(&lock);return BLE_ATT_ERR_UNLIKELY;}
        config = next; reset_epoch(); configured = true; epoch_known = false; drain_until = 0;
        memset(&flow,0,sizeof(flow));flow_run=next.run_id;flow_tx_boot=0;flow_tag=next.flow_token;
        portEXIT_CRITICAL(&lock);
        struct ble_gap_upd_params params = {.itvl_min=next.connection_interval_units,
            .itvl_max=next.connection_interval_units, .latency=0, .supervision_timeout=200};
        ble_gap_update_params(conn, &params);
        return 0;
    }
    portENTER_CRITICAL(&lock);
    int result = BLE_ATT_ERR_UNLIKELY;
    if (length==32 && !memcmp(data,"CBPR",4)) {
        if(csi_ble_progress_matches(data,length,flow_run,flow_tx_boot,receiver_boot,flow_tag) &&
           ble_flow_ack(&flow,csi_clock_read_u32(data+24),esp_timer_get_time())) {
            ++flow_receipts;result=0;
        } else ++flow_invalid_receipts;
    } else if (csi_ble_ack_matches(data, length, config.run_id, transmitter_boot, receiver_boot)) {
        batch_t *b = find_batch(csi_clock_read_u32(data+20));
        batch_timing_t *t = timing_for(csi_clock_read_u32(data+20));
        if (t) { t->ack=esp_timer_get_time(); t->flags |= b ? 4 : 16; }
        if (b) { ble_queue_release(&records, b->id, true); b->used = false; }
        result = 0; /* Idempotent ACKs are harmless. */
    } else if (length == 14 && !memcmp(data, "CBDS", 4) &&
               csi_clock_read_u64(data+4) == config.run_id) {
        uint16_t duration = csi_clock_read_u16(data+12);
        if (duration && duration <= 6000) {
            drain_until = esp_timer_get_time() + (uint64_t)duration * 1000;
            result = 0;
        }
    } else if (length == 12 && !memcmp(data, "CBST", 4) &&
               csi_clock_read_u64(data+4) == config.run_id) {
        configured = false; reset_epoch(); result = 0;
    }
    portEXIT_CRITICAL(&lock);
    if (writer_handle) xTaskNotifyGive(writer_handle);
    return result;
}

static const struct ble_gatt_svc_def services[] = {
    {.type = BLE_GATT_SVC_TYPE_PRIMARY, .uuid = &service_uuid.u,
     .characteristics = (struct ble_gatt_chr_def[]) {
        {.uuid=&status_uuid.u, .access_cb=access, .arg=(void *)1, .flags=BLE_GATT_CHR_F_READ},
        {.uuid=&stats_uuid.u, .access_cb=access, .arg=(void *)2, .flags=BLE_GATT_CHR_F_READ},
        {.uuid=&timing_uuid.u, .access_cb=access, .arg=(void *)3, .flags=BLE_GATT_CHR_F_READ},
        {.uuid=&flow_uuid.u, .access_cb=access, .arg=(void *)4, .flags=BLE_GATT_CHR_F_READ},
        {.uuid=&data_uuid.u, .access_cb=access, .val_handle=&data_handle, .flags=BLE_GATT_CHR_F_NOTIFY},
        {.uuid=&control_uuid.u, .access_cb=access, .flags=BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_NO_RSP},
        {0}}}, {0}
};

static int gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    struct ble_gap_conn_desc desc;
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status) { advertise(); break; }
        int description_result = ble_gap_conn_find(event->connect.conn_handle, &desc);
        portENTER_CRITICAL(&lock);
        connection = event->connect.conn_handle; ++connection_changes;
        if (!description_result) {
            interval = desc.conn_itvl; latency = desc.conn_latency; supervision = desc.supervision_timeout;
        }
        portEXIT_CRITICAL(&lock);
        ble_att_set_preferred_mtu(247);
        ble_hs_hci_util_set_data_len(connection, 251, 2120);
        ble_gap_set_prefered_le_phy(connection, BLE_HCI_LE_PHY_2M_PREF_MASK,
                                  BLE_HCI_LE_PHY_2M_PREF_MASK, 0);
        struct ble_gap_upd_params params = {.itvl_min=10, .itvl_max=10,
            .latency=0, .supervision_timeout=200};
        ble_gap_update_params(connection, &params);
        break;
    case BLE_GAP_EVENT_DISCONNECT:
        portENTER_CRITICAL(&lock);
        connection = BLE_HS_CONN_HANDLE_NONE; subscribed = false; notify_busy = false;
        configured = false; reset_epoch(); ++connection_changes;
        memset(&flow,0,sizeof(flow));flow_run=0;flow_tx_boot=0;flow_tag=0;
        mtu = 23; tx_phy = rx_phy = 0;
        portEXIT_CRITICAL(&lock);
        advertise(); break;
    case BLE_GAP_EVENT_SUBSCRIBE:
        if (event->subscribe.attr_handle == data_handle) {
            portENTER_CRITICAL(&lock); subscribed = event->subscribe.cur_notify;
            portEXIT_CRITICAL(&lock);
        }
        break;
    case BLE_GAP_EVENT_MTU:
        portENTER_CRITICAL(&lock); mtu = event->mtu.value; portEXIT_CRITICAL(&lock); break;
    case BLE_GAP_EVENT_CONN_UPDATE:
        if (!ble_gap_conn_find(event->conn_update.conn_handle, &desc)) {
            portENTER_CRITICAL(&lock);
            interval = desc.conn_itvl; latency = desc.conn_latency; supervision = desc.supervision_timeout;
            portEXIT_CRITICAL(&lock);
        }
        break;
    case BLE_GAP_EVENT_DATA_LEN_CHG:
        portENTER_CRITICAL(&lock);
        tx_octets = event->data_len_chg.max_tx_octets; rx_octets = event->data_len_chg.max_rx_octets;
        portEXIT_CRITICAL(&lock); break;
    case BLE_GAP_EVENT_PHY_UPDATE_COMPLETE:
        portENTER_CRITICAL(&lock);
        if (!event->phy_updated.status) {
            tx_phy = event->phy_updated.tx_phy; rx_phy = event->phy_updated.rx_phy;
        }
        portEXIT_CRITICAL(&lock); break;
    case BLE_GAP_EVENT_NOTIFY_TX:
        portENTER_CRITICAL(&lock);
        notify_busy = false; last_complete_us = esp_timer_get_time();
        if (!config.credit_flow && event->notify_tx.status && event->notify_tx.status != BLE_HS_EDONE) {
            ++send_errors;
            batch_t *b = find_batch(pending_batch);
            if (b) { b->offset = b->length; b->waiting_since = last_complete_us; }
        }
        portEXIT_CRITICAL(&lock);
        if (writer_handle) xTaskNotifyGive(writer_handle);
        break;
    default: break;
    }
    return 0;
}

static void advertise(void)
{
    struct ble_hs_adv_fields fields = {0};
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.uuids128 = (ble_uuid128_t *)&service_uuid;
    fields.num_uuids128 = 1; fields.uuids128_is_complete = 1;
    ble_gap_adv_set_fields(&fields);
    struct ble_gap_adv_params params = {.conn_mode=BLE_GAP_CONN_MODE_UND,
                                       .disc_mode=BLE_GAP_DISC_MODE_GEN};
    int rc = ble_gap_adv_start(own_address_type, NULL, BLE_HS_FOREVER, &params, gap_event, NULL);
    if (rc) ESP_LOGW(TAG, "advertising failed: %d", rc);
}

static void synced(void)
{
    if (ble_hs_util_ensure_addr(0) || ble_hs_id_infer_auto(0, &own_address_type)) {
        ESP_LOGE(TAG, "BLE address initialization failed"); return;
    }
    advertise();
}
static void host_task(void *arg)
{
    (void)arg; nimble_port_run(); nimble_port_freertos_deinit();
}

static batch_t *make_batch(uint64_t now)
{
    batch_t *b = NULL;
    for (unsigned i = 0; i < config.outstanding_batches; ++i)
        if (!batches[i].used) { b = &batches[i]; break; }
    ble_record_slot_t *s = ble_queue_oldest(&records);
    if (!b || !s) return NULL;
    if(config.credit_flow) {
        size_t prospective=CSI_BLE_ENVELOPE_SIZE+60+4;
        unsigned count=0;
        uint64_t selected=0;
        while(count<config.batch_records) {
            int oldest=-1;
            for(unsigned i=0;i<records.capacity;++i) if(records.slots[i].state==1 &&
                !(selected & (UINT64_C(1)<<i)) && (oldest<0 ||
                records.slots[i].captured<records.slots[oldest].captured)) oldest=i;
            if(oldest<0 || prospective+2+records.slots[oldest].length>CSI_BLE_MAX_PACKET)break;
            prospective+=2+records.slots[oldest].length;
            selected|=UINT64_C(1)<<oldest;++count;
        }
        if(!ble_admission_allowed(now,s->captured,config.delivery_deadline_ms,config.completion_budget_ms) ||
           (!drain_until && !config.continuous_upload && grant_state.remaining<prospective)) return NULL;
    }
    memset(b, 0, sizeof(*b)); b->used = true; b->id = next_batch++; b->oldest = s->captured;
    b->started=now;
    if (config.timing_experiment) timings[b->id%8]=(batch_timing_t){
        .id=b->id, .flags=1, .capture=s->captured, .built=esp_timer_get_time()};
    uint8_t *p = b->data + CSI_BLE_ENVELOPE_SIZE;
    memset(p, 0, 60); memcpy(p, "CSIB", 4); p[4] = 1;
    csi_clock_write_u16(p+6, 60); csi_clock_write_u32(p+8, receiver_boot);
    csi_clock_write_u32(p+12, b->id);
    uint16_t offset = 60, count = 0;
    while (s && count < (config.batch_records ? config.batch_records : 2) && offset + 2 + s->length <= 1400) {
        csi_clock_write_u16(p+offset, s->length); offset += 2;
        memcpy(p+offset, s->data, s->length); offset += s->length;
        s->state = 2; s->batch = b->id; ++count;
        s = ble_queue_oldest(&records);
    }
    csi_clock_write_u16(p+16, count);
    uint32_t stats[10] = {records.captured, sensing_missing, sensing_reordered, 0,
        records.evicted+records.rejected, 0, ++built, sent, records.acknowledged, send_errors};
    for (unsigned i = 0; i < 10; ++i) csi_clock_write_u32(p+20+4*i, stats[i]);
    b->length = csi_ble_envelope_finish(b->data, sizeof(b->data), offset,
        config.run_id, transmitter_boot, receiver_boot, b->id);
    return b;
}

static void writer_task(void *arg)
{
    (void)arg;
    writer_handle = xTaskGetCurrentTaskHandle();
    uint8_t fragment[244];
    for (;;) {
        portENTER_CRITICAL(&lock);
        uint64_t now = esp_timer_get_time();
        if (!configured) { portEXIT_CRITICAL(&lock); writer_wait(); continue; }
        uint64_t age = (uint64_t)config.maximum_age_ms * 1000;
        uint64_t pending_age=age;
        if(config.credit_flow) {
            uint64_t admission_age=(uint64_t)(config.delivery_deadline_ms-config.completion_budget_ms)*1000;
            if(admission_age<pending_age)pending_age=admission_age;
        }
        uint32_t expired_before=records.expired;
        ble_queue_expire(&records, now, pending_age);
        if(config.credit_flow)admission_drops+=records.expired-expired_before;
        for (unsigned i = 0; i < 4; ++i) {
            batch_t *b = &batches[i];
            bool stale=config.credit_flow ? now-b->started >= (uint64_t)config.transfer_timeout_ms*1000
                                         : now>=b->oldest && now-b->oldest >= age;
            if (b->used && stale) {
                batch_timing_t *t=timing_for(b->id);
                if(t) {t->expired=now;t->flags |= 8;}
                unsigned n=ble_queue_release(&records, b->id, false);
                if(config.credit_flow)transfer_expired+=n;
                b->used = false; /* Physical credit debt deliberately survives. */
            }
        }
        if (drain_until && now >= drain_until) {
            configured = false; reset_epoch(); portEXIT_CRITICAL(&lock); writer_wait(); continue;
        }
        bool permitted = ble_grants_available(&grant_state, &config, receiver_index, now);
        if(config.credit_flow && flow.count && now-flow.last_progress >= (uint64_t)config.progress_timeout_ms*1000) {
            ++credit_disconnects;configured=false;
            uint16_t conn=connection;
            portEXIT_CRITICAL(&lock);
            if(conn!=BLE_HS_CONN_HANDLE_NONE)ble_gap_terminate(conn,BLE_ERR_REM_USER_CONN_TERM);
            writer_wait();continue;
        }
        if (connection == BLE_HS_CONN_HANDLE_NONE || !subscribed || notify_busy ||
            (!drain_until && !permitted) ||
            (config.submission_pacing_us && now-last_submit_us < config.submission_pacing_us)) {
            portEXIT_CRITICAL(&lock); writer_wait(); continue;
        }
        if(config.credit_flow && (flow_tx_boot!=transmitter_boot || flow.count>=config.credit_fragments)) {
            ++credit_wait_ticks;portEXIT_CRITICAL(&lock);writer_wait();continue;
        }
        batch_t *b = NULL;
        for (unsigned i = 0; i < config.outstanding_batches; ++i) {
            batch_t *candidate = &batches[i];
            if (!candidate->used) continue;
            if(config.credit_flow && candidate->offset==candidate->length &&
               ble_flow_has_batch(&flow,candidate->id)) continue;
            csi_ble_config_t policy=config;
            if(config.credit_flow)policy.maximum_age_ms=config.transfer_timeout_ms;
            ble_delivery_action_t action = ble_delivery_action(now, config.credit_flow ? candidate->started : candidate->oldest,
                candidate->waiting_since, candidate->offset == candidate->length,
                candidate->attempts, &policy);
            if (action == BLE_DELIVERY_WAIT) continue;
            if (action == BLE_DELIVERY_DROP) {
                unsigned n=ble_queue_release(&records, candidate->id, false);
                if(config.credit_flow)transfer_expired+=n;
                candidate->used = false; continue;
            }
            if (action == BLE_DELIVERY_RETRY) {
                ++candidate->attempts; ++retries; candidate->offset = 0;
            }
            if (!b || candidate->oldest < b->oldest) b = candidate;
        }
        if (!b) b = make_batch(now);
        if (!b) { portEXIT_CRITICAL(&lock); writer_wait(); continue; }
        unsigned header=config.credit_flow ? 20 : 12;
        size_t chunk = mtu > header+3 ? mtu-header-3 : 0;
        if (chunk > sizeof(fragment)-header) chunk = sizeof(fragment)-header;
        if (chunk > b->length-b->offset) chunk = b->length-b->offset;
        if (!drain_until && !config.continuous_upload && chunk > grant_state.remaining) chunk = grant_state.remaining;
        if (!chunk) { portEXIT_CRITICAL(&lock); writer_wait(); continue; }
        uint32_t serial=0;
        uint16_t old_offset=b->offset;
        if(config.credit_flow) {
            if(!ble_flow_reserve(&flow,config.credit_fragments,b->id,chunk+header,now,&serial)) {
                portEXIT_CRITICAL(&lock);writer_wait();continue;
            }
            if(!csi_ble_flow_fragment_encode(fragment,sizeof(fragment),config.flow_token,
                serial,b->id,b->offset,b->length,b->data+b->offset,chunk)) {
                ble_flow_cancel(&flow,serial);portEXIT_CRITICAL(&lock);writer_wait();continue;
            }
        } else {
            memcpy(fragment, "CBLF", 4); csi_clock_write_u32(fragment+4, b->id);
            csi_clock_write_u16(fragment+8, b->offset); csi_clock_write_u16(fragment+10, b->length);
        }
        if(!config.credit_flow)memcpy(fragment+header, b->data+b->offset, chunk);
        batch_timing_t *t=timing_for(b->id);
        uint64_t submitted_at=esp_timer_get_time();
        if(t && !t->first) t->first=submitted_at;
        b->offset += chunk;
        if (b->offset == b->length) {
            b->waiting_since = now; ++sent;
            if(t) {t->last=submitted_at;t->flags |= 2;}
        }
        if (!drain_until && !config.continuous_upload) grant_state.remaining -= chunk;
        uint16_t conn = connection;
        uint32_t id = b->id;
        pending_batch = id; notify_busy = true; last_submit_us = now;
        portEXIT_CRITICAL(&lock);
        struct os_mbuf *om = ble_hs_mbuf_from_flat(fragment, chunk+header);
        int rc = om ? ble_gatts_notify_custom(conn, data_handle, om) : BLE_HS_ENOMEM;
        if (rc) {
            portENTER_CRITICAL(&lock);
            notify_busy = false; ++send_errors;
            b = find_batch(id);
            if(config.credit_flow) {
                ble_flow_cancel(&flow,serial);++submission_failures;last_submission_error=rc;
                if(b) {b->offset=old_offset;b->waiting_since=0;}
            } else if (b) { b->offset = b->length; b->waiting_since = now; }
            portEXIT_CRITICAL(&lock);
        } else if(config.credit_flow) {
            portENTER_CRITICAL(&lock);++submitted_fragments;submitted_bytes+=chunk+header;
            portEXIT_CRITICAL(&lock);
        }
    }
}

void csi_ble_init(const csi_radio_profile_t *profile, const uint8_t *mac, uint32_t boot)
{
    radio_profile = *profile; memcpy(receiver_mac, mac, 6); receiver_boot = boot;
    receiver_index = UINT8_MAX;
    for (unsigned i = 0; i < profile->receiver_count; ++i)
        if (!memcmp(profile->receiver_macs[i], mac, 6)) receiver_index = i;
    if (receiver_index == UINT8_MAX) { ESP_LOGE(TAG, "receiver missing from inventory"); abort(); }
    ESP_ERROR_CHECK(nimble_port_init());
    ble_svc_gap_init(); ble_svc_gatt_init(); ble_svc_gap_device_name_set("CSI receiver");
    ble_att_set_preferred_mtu(247);
    ESP_ERROR_CHECK(ble_gatts_count_cfg(services));
    ESP_ERROR_CHECK(ble_gatts_add_svcs(services));
    ble_hs_cfg.sync_cb = synced;
    nimble_port_freertos_init(host_task);
    if (xTaskCreate(writer_task, "csi_ble_writer", 4096, NULL, 4, NULL) != pdPASS) abort();
}
#endif
