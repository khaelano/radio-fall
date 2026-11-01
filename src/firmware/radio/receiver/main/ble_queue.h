#ifndef CSI_BLE_QUEUE_H
#define CSI_BLE_QUEUE_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define BLE_QUEUE_LIMIT 64
#define BLE_RECORD_LIMIT 699

typedef struct {
    uint8_t state; /* 0 free, 1 pending, 2 owned by an outstanding batch */
    uint32_t batch;
    uint64_t captured;
    uint16_t length;
    uint8_t data[BLE_RECORD_LIMIT];
} ble_record_slot_t;

typedef struct {
    ble_record_slot_t slots[BLE_QUEUE_LIMIT];
    uint16_t capacity;
    uint32_t captured, acknowledged, evicted, expired, rejected;
    uint32_t epoch_dropped, peak;
} ble_record_queue_t;

/* Caller serializes access; no allocation, blocking, or radio APIs here. */
static inline unsigned ble_queue_count(const ble_record_queue_t *q)
{
    unsigned count = 0;
    for (unsigned i = 0; i < q->capacity; ++i) count += q->slots[i].state != 0;
    return count;
}

static inline void ble_queue_reset(ble_record_queue_t *q, uint16_t capacity)
{
    q->epoch_dropped += ble_queue_count(q);
    memset(q->slots, 0, sizeof(q->slots));
    q->capacity = capacity;
}

static inline void ble_queue_expire(ble_record_queue_t *q, uint64_t now, uint64_t age)
{
    for (unsigned i = 0; i < q->capacity; ++i) {
        ble_record_slot_t *s = &q->slots[i];
        /* Outstanding slots are released by their batch owner, never here. */
        if (s->state == 1 && now >= s->captured && now - s->captured >= age) {
            s->state = 0;
            ++q->expired;
        }
    }
}

static inline bool ble_queue_push(ble_record_queue_t *q, const uint8_t *data,
                                  uint16_t length, uint64_t captured)
{
    if (!q->capacity || !length || length > BLE_RECORD_LIMIT) return false;
    ++q->captured;
    int free_slot = -1, oldest = -1;
    for (unsigned i = 0; i < q->capacity; ++i) {
        if (!q->slots[i].state) { free_slot = (int)i; break; }
        if (q->slots[i].state == 1 &&
            (oldest < 0 || q->slots[i].captured < q->slots[oldest].captured)) oldest = (int)i;
    }
    if (free_slot < 0) {
        if (oldest < 0) { ++q->rejected; return false; }
        free_slot = oldest;
        ++q->evicted;
    }
    ble_record_slot_t *s = &q->slots[free_slot];
    s->state = 1; s->captured = captured; s->length = length;
    memcpy(s->data, data, length);
    unsigned count = ble_queue_count(q);
    if (count > q->peak) q->peak = count;
    return true;
}

static inline ble_record_slot_t *ble_queue_oldest(ble_record_queue_t *q)
{
    ble_record_slot_t *s = NULL;
    for (unsigned i = 0; i < q->capacity; ++i)
        if (q->slots[i].state == 1 && (!s || q->slots[i].captured < s->captured)) s = &q->slots[i];
    return s;
}

static inline unsigned ble_queue_release(ble_record_queue_t *q, uint32_t batch, bool ack)
{
    unsigned count = 0;
    for (unsigned i = 0; i < q->capacity; ++i)
        if (q->slots[i].state == 2 && q->slots[i].batch == batch) {
            q->slots[i].state = 0;
            ++count;
        }
    if (ack) q->acknowledged += count;
    else q->expired += count;
    return count;
}
#endif
