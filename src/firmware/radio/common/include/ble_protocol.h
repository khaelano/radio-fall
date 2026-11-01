#ifndef CSI_BLE_PROTOCOL_H
#define CSI_BLE_PROTOCOL_H

#include "csi_clock_protocol.h"
#include "serial_frame.h"

#define CSI_BLE_CONFIG_SIZE 64
#define CSI_BLE_CONFIG_MAX_SIZE 80
#define CSI_BLE_SENSING_SIZE 88
#define CSI_BLE_ENVELOPE_SIZE 32
#define CSI_BLE_MAX_PACKET 1436
#define CSI_BLE_FRAGMENT_HEADER 12
#define CSI_BLE_ACK_SIZE 28
#define CSI_BLE_SERVICE_UUID "4d71c510-8a51-4a67-aee0-52c01bb71800"

/* Control/status are distinct from the CSI notification stream. */
#define CSI_SERIAL_BLE_CONTROL 12
#define CSI_SERIAL_BLE_RESPONSE 13
#define CSI_SERIAL_BLE_ROUND 14

typedef struct {
    uint64_t run_id;
    uint32_t seed, inventory_crc;
    uint16_t maximum_age_ms, ack_timeout_ms, queue_capacity;
    uint16_t start_guard_us, end_guard_us, rate_hz;
    uint8_t scheduler, receiver_count, maximum_retries;
    uint8_t outstanding_batches, records_per_grant;
    uint8_t slot_rounds, batch_records;
    uint16_t connection_interval_units, submission_pacing_us;
    bool timing_experiment, continuous_upload;
    bool credit_flow;
    uint16_t delivery_deadline_ms, completion_budget_ms, transfer_timeout_ms;
    uint16_t progress_timeout_ms, progress_interval_ms;
    uint8_t credit_fragments, progress_every;
    uint32_t flow_token;
    char fingerprint[17];
} csi_ble_config_t;

static inline bool csi_ble_config_decode(const uint8_t *p, size_t n,
                                         csi_ble_config_t *c)
{
    if (!p || !c || (n != CSI_BLE_CONFIG_SIZE && n != CSI_BLE_CONFIG_MAX_SIZE) || memcmp(p, "CBLC", 4) ||
        (p[4] < 1 || p[4] > 3) || (p[4]==3 ? n!=80 : n!=64) ||
        p[5] > 1 || p[6] < 1 || p[6] > 4 || p[7] > 4)
        return false;
    memset(c, 0, sizeof(*c));
    c->scheduler = p[5]; c->receiver_count = p[6]; c->maximum_retries = p[7];
    c->run_id = csi_clock_read_u64(p + 8);
    c->seed = csi_clock_read_u32(p + 16);
    c->maximum_age_ms = csi_clock_read_u16(p + 20);
    c->ack_timeout_ms = csi_clock_read_u16(p + 22);
    c->queue_capacity = csi_clock_read_u16(p + 24);
    c->outstanding_batches = p[26]; c->records_per_grant = p[27];
    c->start_guard_us = csi_clock_read_u16(p + 28);
    c->end_guard_us = csi_clock_read_u16(p + 30);
    c->rate_hz = csi_clock_read_u16(p + 32);
    memcpy(c->fingerprint, p + 36, 16);
    c->inventory_crc = csi_clock_read_u32(p + 52);
    for (size_t i = 0; i < 16; ++i)
        if (!((p[36+i] >= '0' && p[36+i] <= '9') ||
              (p[36+i] >= 'a' && p[36+i] <= 'f'))) return false;
    c->slot_rounds = 1; c->batch_records = 2; c->connection_interval_units = 10;
    if (p[4] == 1) {
        for (size_t i = 56; i < n; ++i) if (p[i]) return false;
    } else {
        c->timing_experiment = true;
        c->slot_rounds = p[56]; c->batch_records = p[57];
        c->connection_interval_units = csi_clock_read_u16(p+58);
        c->submission_pacing_us = csi_clock_read_u16(p+60);
        c->continuous_upload = p[62] == 1;
        if (!c->slot_rounds || c->slot_rounds > 8 || !c->batch_records || c->batch_records > 4 ||
            c->connection_interval_units < 6 || c->connection_interval_units > 40 ||
            p[62] > 1 || p[63]) return false;
    }
    if (p[4] == 3) {
        c->credit_flow = true;
        c->delivery_deadline_ms=csi_clock_read_u16(p+64);
        c->completion_budget_ms=csi_clock_read_u16(p+66);
        c->transfer_timeout_ms=csi_clock_read_u16(p+68);
        c->progress_timeout_ms=csi_clock_read_u16(p+70);
        c->credit_fragments=p[72];c->progress_every=p[73];
        c->progress_interval_ms=csi_clock_read_u16(p+74);
        c->flow_token=csi_clock_read_u32(p+76);
        uint32_t token=csi_serial_crc32(p+8,8);if(!token)token=1;
        if(c->delivery_deadline_ms<2 || c->delivery_deadline_ms>5000 ||
           !c->completion_budget_ms || c->completion_budget_ms>=c->delivery_deadline_ms ||
           c->transfer_timeout_ms<c->completion_budget_ms || c->transfer_timeout_ms>5000 ||
           c->progress_timeout_ms<100 || c->progress_timeout_ms>5000 ||
           !c->credit_fragments || c->credit_fragments>16 || !c->progress_every ||
           c->progress_every>c->credit_fragments || !c->progress_interval_ms ||
           c->progress_interval_ms>50 || c->flow_token!=token ||
           c->ack_timeout_ms>c->transfer_timeout_ms) return false;
    }
    return c->run_id && c->rate_hz >= 50 && c->rate_hz <= 100 &&
           c->maximum_age_ms && c->maximum_age_ms <= 5000 &&
           c->ack_timeout_ms && c->ack_timeout_ms <= c->maximum_age_ms &&
           c->queue_capacity && c->queue_capacity <= 64 &&
           c->outstanding_batches && c->outstanding_batches <= 4 &&
           c->records_per_grant && c->records_per_grant <= 16 &&
           c->start_guard_us <= 4000 && c->end_guard_us <= 4000 &&
           p[34] == 0 && p[35] == 0;
}

static inline uint8_t csi_ble_owner(uint32_t sequence, uint8_t count,
                                    uint8_t scheduler, uint32_t seed)
{
    if (count < 1 || count > 4) return UINT8_MAX;
    if (!scheduler) return (uint8_t)(sequence % count);
    uint32_t value = sequence ^ seed;
    const uint64_t limit = (UINT64_C(1) << 32) - ((UINT64_C(1) << 32) % count);
    for (;;) {
        value += UINT32_C(0x9e3779b9);
        uint32_t x = value;
        x = (x ^ (x >> 16)) * UINT32_C(0x85ebca6b);
        x = (x ^ (x >> 13)) * UINT32_C(0xc2b2ae35);
        x ^= x >> 16;
        if ((uint64_t)x < limit) return (uint8_t)(x % count);
    }
}

static inline uint8_t csi_ble_config_owner(uint32_t sequence, const csi_ble_config_t *c)
{
    return csi_ble_owner(sequence / (c->slot_rounds ? c->slot_rounds : 1),
                         c->receiver_count, c->scheduler, c->seed);
}

static inline size_t csi_ble_sensing_encode(uint8_t *p, size_t capacity,
    const csi_sensing_packet_t *packet, const csi_ble_config_t *c,
    uint32_t boot, uint64_t deadline)
{
    if (capacity < CSI_BLE_SENSING_SIZE || !csi_sensing_encode(p, capacity, packet))
        return 0;
    p[4] = 3;
    csi_clock_write_u16(p + 6, CSI_BLE_SENSING_SIZE);
    csi_clock_write_u64(p + 40, c->run_id);
    csi_clock_write_u32(p + 48, boot);
    memcpy(p + 52, c->fingerprint, 16);
    csi_clock_write_u32(p + 68, 1000000U / c->rate_hz);
    csi_clock_write_u64(p + 72, deadline);
    for (unsigned i = 0; i < 3; ++i)
        p[80+i] = csi_ble_config_owner(packet->sequence + i, c);
    p[83] = 0;
    csi_clock_write_u32(p + 84, csi_serial_crc32(p, 84));
    return CSI_BLE_SENSING_SIZE;
}
static inline size_t csi_ble_envelope_finish(uint8_t *e, size_t capacity, uint16_t payload_length,
    uint64_t run, uint32_t tx_boot, uint32_t rx_boot, uint32_t batch)
{
    size_t total = CSI_BLE_ENVELOPE_SIZE + payload_length;
    if (!run || !payload_length || payload_length > 1400 || capacity < total+4) return 0;
    memset(e, 0, CSI_BLE_ENVELOPE_SIZE);
    memcpy(e, "CBLE", 4); e[4] = 1; csi_clock_write_u16(e+6, CSI_BLE_ENVELOPE_SIZE);
    csi_clock_write_u64(e+8, run); csi_clock_write_u32(e+16, tx_boot);
    csi_clock_write_u32(e+20, rx_boot); csi_clock_write_u32(e+24, batch);
    csi_clock_write_u16(e+28, payload_length);
    csi_clock_write_u32(e+total, csi_serial_crc32(e, total));
    return total+4;
}
static inline bool csi_ble_ack_matches(const uint8_t *p, size_t n, uint64_t run,
                                      uint32_t tx_boot, uint32_t rx_boot)
{
    return n == CSI_BLE_ACK_SIZE && !memcmp(p, "CBAK", 4) &&
        csi_serial_crc32(p,24) == csi_clock_read_u32(p+24) &&
        csi_clock_read_u64(p+4) == run && csi_clock_read_u32(p+12) == tx_boot &&
        csi_clock_read_u32(p+16) == rx_boot;
}

static inline bool csi_ble_progress_matches(const uint8_t *p,size_t n,uint64_t run,
    uint32_t tx,uint32_t rx,uint32_t token)
{
    return p && n==32 && !memcmp(p,"CBPR",4) &&
        csi_serial_crc32(p,28)==csi_clock_read_u32(p+28) &&
        csi_clock_read_u64(p+4)==run && csi_clock_read_u32(p+12)==tx &&
        csi_clock_read_u32(p+16)==rx && csi_clock_read_u32(p+20)==token;
}

static inline size_t csi_ble_flow_fragment_encode(uint8_t *out,size_t capacity,
    uint32_t token,uint32_t serial,uint32_t batch,uint16_t offset,uint16_t total,
    const uint8_t *payload,size_t length)
{
    if(!out || !payload || !length || total<=CSI_BLE_ENVELOPE_SIZE+4 ||
       total>CSI_BLE_MAX_PACKET || offset+length>total || capacity<20+length) return 0;
    memcpy(out,"CBL2",4);csi_clock_write_u32(out+4,token);
    csi_clock_write_u32(out+8,serial);csi_clock_write_u32(out+12,batch);
    csi_clock_write_u16(out+16,offset);csi_clock_write_u16(out+18,total);
    memcpy(out+20,payload,length);return 20+length;
}
#endif
