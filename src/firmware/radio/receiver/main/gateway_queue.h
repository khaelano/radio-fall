#ifndef CSI_GATEWAY_QUEUE_H
#define CSI_GATEWAY_QUEUE_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define GW_QUEUE_LIMIT 96
#define GW_RECORD_LIMIT 699

/* Each bit identifies one batch present at slot entry. Clear it only after an
 * accepted poll, and discard bits whose batches were ACKed or expired meanwhile. */
static inline int gw_poll_next(uint8_t *pending, uint8_t eligible,
                               unsigned limit, unsigned *cursor)
{
    if(!limit || limit>8)return -1;
    *pending&=eligible&((1U<<limit)-1);
    for(unsigned n=0;n<limit;++n){
        unsigned i=(*cursor)++%limit;
        if(*pending&(1U<<i))return (int)i;
    }
    return -1;
}

typedef struct {
    uint8_t state; /* 0 free, 1 pending, 2 owned by an outstanding batch */
    uint32_t batch;
    uint64_t captured;
    uint16_t length;
    uint8_t data[GW_RECORD_LIMIT];
} gw_record_slot_t;

typedef struct {
    gw_record_slot_t slots[GW_QUEUE_LIMIT];
    uint16_t capacity;
    uint32_t captured, acknowledged, sent_unconfirmed, evicted, expired, rejected;
    uint32_t epoch_dropped, peak;
} gw_record_queue_t;

/* Caller serializes access; no allocation, blocking, or radio APIs here. */
static inline unsigned gw_queue_count(const gw_record_queue_t *q)
{
    unsigned count = 0;
    for (unsigned i = 0; i < q->capacity; ++i) count += q->slots[i].state != 0;
    return count;
}

static inline void gw_queue_reset(gw_record_queue_t *q, uint16_t capacity)
{
    q->epoch_dropped += gw_queue_count(q);
    memset(q->slots, 0, sizeof(q->slots));
    q->capacity = capacity;
}

static inline void gw_queue_expire(gw_record_queue_t *q, uint64_t now, uint64_t age)
{
    for (unsigned i = 0; i < q->capacity; ++i) {
        gw_record_slot_t *s = &q->slots[i];
        /* Outstanding slots are released by their batch owner, never here. */
        if (s->state == 1 && now >= s->captured && now - s->captured >= age) {
            s->state = 0;
            ++q->expired;
        }
    }
}

static inline bool gw_queue_push(gw_record_queue_t *q, const uint8_t *data,
                                  uint16_t length, uint64_t captured)
{
    if (!q->capacity || !length || length > GW_RECORD_LIMIT) return false;
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
    gw_record_slot_t *s = &q->slots[free_slot];
    s->state = 1; s->captured = captured; s->length = length;
    memcpy(s->data, data, length);
    unsigned count = gw_queue_count(q);
    if (count > q->peak) q->peak = count;
    return true;
}

static inline gw_record_slot_t *gw_queue_oldest(gw_record_queue_t *q)
{
    gw_record_slot_t *s = NULL;
    for (unsigned i = 0; i < q->capacity; ++i)
        if (q->slots[i].state == 1 && (!s || q->slots[i].captured < s->captured)) s = &q->slots[i];
    return s;
}

static inline unsigned gw_queue_release_slots(gw_record_queue_t *q, uint32_t batch)
{
    unsigned count = 0;
    for (unsigned i = 0; i < q->capacity; ++i)
        if (q->slots[i].state == 2 && q->slots[i].batch == batch) {
            q->slots[i].state = 0;
            ++count;
        }
    return count;
}

static inline unsigned gw_queue_release(gw_record_queue_t *q, uint32_t batch, bool ack)
{
    unsigned count = gw_queue_release_slots(q, batch);
    if (ack) q->acknowledged += count;
    else q->expired += count;
    return count;
}

/* Local completion is neither host acceptance nor expiry. */
static inline unsigned gw_queue_release_unconfirmed(gw_record_queue_t *q, uint32_t batch)
{
    unsigned count = gw_queue_release_slots(q, batch);
    q->sent_unconfirmed += count;
    return count;
}
#endif
