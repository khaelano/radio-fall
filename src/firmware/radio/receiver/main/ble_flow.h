#ifndef CSI_BLE_FLOW_H
#define CSI_BLE_FLOW_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define BLE_FLOW_LIMIT 16
typedef struct { uint32_t serial, batch; uint16_t bytes; bool used; } ble_flow_entry_t;
typedef struct {
    ble_flow_entry_t entries[BLE_FLOW_LIMIT];
    uint32_t next_serial, acked;
    unsigned count, peak;
    uint32_t bytes, peak_bytes;
    uint64_t last_progress;
    bool have_issued, have_acked;
} ble_flow_t;

static inline bool ble_flow_after(uint32_t a, uint32_t b)
{ uint32_t d=a-b; return d && d<0x80000000U; }

/* Credit is independent of application record/batch ownership. Clear only after
 * connection teardown, or an empty ledger at a new run's configuration. */
static inline bool ble_flow_reserve(ble_flow_t *f, unsigned limit, uint32_t batch,
    uint16_t bytes, uint64_t now, uint32_t *serial)
{
    if (!limit || limit>BLE_FLOW_LIMIT || f->count>=limit || !bytes) return false;
    for(unsigned i=0;i<BLE_FLOW_LIMIT;++i) if(!f->entries[i].used) {
        if(!f->have_issued) {f->next_serial=1;f->have_issued=true;}
        *serial=f->next_serial++;
        f->entries[i]=(ble_flow_entry_t){.serial=*serial,.batch=batch,.bytes=bytes,.used=true};
        if(!f->count) f->last_progress=now;
        ++f->count;f->bytes+=bytes;
        if(f->count>f->peak)f->peak=f->count;
        if(f->bytes>f->peak_bytes)f->peak_bytes=f->bytes;
        return true;
    }
    return false;
}
static inline void ble_flow_cancel(ble_flow_t *f,uint32_t serial)
{
    for(unsigned i=0;i<BLE_FLOW_LIMIT;++i) if(f->entries[i].used && f->entries[i].serial==serial) {
        f->bytes-=f->entries[i].bytes;--f->count;f->entries[i].used=false;return;
    }
}
static inline bool ble_flow_ack(ble_flow_t *f,uint32_t serial,uint64_t now)
{
    if(!f->have_issued || ble_flow_after(serial,f->next_serial-1)) return false;
    if(f->have_acked && !ble_flow_after(serial,f->acked)) return true;
    for(unsigned i=0;i<BLE_FLOW_LIMIT;++i) if(f->entries[i].used &&
        !ble_flow_after(f->entries[i].serial,serial)) {
        f->bytes-=f->entries[i].bytes;--f->count;f->entries[i].used=false;
    }
    f->acked=serial;f->have_acked=true;f->last_progress=now;return true;
}
static inline bool ble_flow_has_batch(const ble_flow_t *f,uint32_t batch)
{
    for(unsigned i=0;i<BLE_FLOW_LIMIT;++i)
        if(f->entries[i].used && f->entries[i].batch==batch) return true;
    return false;
}
static inline bool ble_admission_allowed(uint64_t now,uint64_t capture,
    uint16_t deadline_ms,uint16_t budget_ms)
{
    return now>=capture && deadline_ms>budget_ms &&
        now-capture <= (uint64_t)(deadline_ms-budget_ms)*1000;
}
#endif
