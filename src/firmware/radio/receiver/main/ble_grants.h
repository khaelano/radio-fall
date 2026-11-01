#ifndef CSI_BLE_GRANTS_H
#define CSI_BLE_GRANTS_H
#include "ble_protocol.h"

typedef struct { uint64_t start, end; uint32_t sequence; uint8_t owner; } ble_grant_t;
typedef struct {
    ble_grant_t windows[3];
    uint32_t last_sequence, budget_sequence;
    uint64_t last_observation;
    size_t remaining;
    bool observed, budget_valid;
} ble_grants_t;

static inline bool ble_grants_observe(ble_grants_t *g, const csi_ble_config_t *c,
    uint32_t sequence, uint64_t deadline, uint64_t enqueue, uint64_t received,
    const uint8_t owners[3])
{
    uint32_t period = 1000000U/c->rate_hz;
    uint32_t forward = sequence-g->last_sequence;
    if ((g->observed && (!forward || forward >= 0x80000000U)) ||
        deadline > enqueue || enqueue-deadline >= period) return false;
    for (unsigned i = 0; i < 3; ++i) if (owners[i] >= c->receiver_count) return false;
    ble_grant_t next[3];
    uint8_t rounds = c->slot_rounds ? c->slot_rounds : 1;
    int64_t offset = (int64_t)received-(int64_t)enqueue;
    for (unsigned i = 0; i < 3; ++i) {
        next[i] = (ble_grant_t){
            .sequence=sequence+i, .owner=owners[i],
            .start=deadline+(uint64_t)i*period+offset+((sequence+i)%rounds ? 0 : c->start_guard_us),
            .end=deadline+(uint64_t)(i+1)*period+offset-((sequence+i+1)%rounds ? 0 : c->end_guard_us)};
        /* Repeated announcements do not move an existing window later. */
        for (unsigned j = 0; g->observed && j < 3; ++j)
            if (g->windows[j].sequence == next[i].sequence && g->windows[j].start < next[i].start)
                next[i] = g->windows[j];
    }
    memcpy(g->windows, next, sizeof(next));
    g->last_observation = received; g->last_sequence = sequence; g->observed = true;
    return true;
}

static inline bool ble_grants_available(ble_grants_t *g, const csi_ble_config_t *c,
                                        uint8_t receiver, uint64_t now)
{
    if (!g->observed || now-g->last_observation > 3*(1000000U/c->rate_hz)) return false;
    if (c->continuous_upload) return true; /* Explicit experiment; still needs sensing synchronization. */
    for (unsigned i = 0; i < 3; ++i) {
        ble_grant_t *w = &g->windows[i];
        if (w->owner != receiver || now < w->start || now >= w->end) continue;
        uint32_t slot = w->sequence / (c->slot_rounds ? c->slot_rounds : 1);
        if (!g->budget_valid || g->budget_sequence != slot) {
            g->budget_valid = true; g->budget_sequence = slot;
            g->remaining = (size_t)c->records_per_grant*699*(c->slot_rounds ? c->slot_rounds : 1);
        }
        return g->remaining > 0;
    }
    return false;
}
#endif
