#ifndef CSI_SENSING_SEND_POLICY_H
#define CSI_SENSING_SEND_POLICY_H
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t pending_mask;
    uint32_t busy_skips;
    uint32_t backoff_skips;
    uint64_t next_probe_us[4];
} csi_sensing_send_policy_t;

/* Callers serialize reservation/completion against the Wi-Fi callback. */
static inline bool csi_sensing_reserve(csi_sensing_send_policy_t *policy, unsigned peer)
{
    if (peer >= 4) return false;
    uint8_t bit = (uint8_t)(1U << peer);
    if (policy->pending_mask & bit) { ++policy->busy_skips; return false; }
    policy->pending_mask |= bit;
    return true;
}

static inline void csi_sensing_complete(csi_sensing_send_policy_t *policy, unsigned peer)
{
    if (peer < 4) policy->pending_mask &= (uint8_t)~(1U << peer);
}

static inline bool csi_sensing_reserve_at(csi_sensing_send_policy_t *policy,
                                         unsigned peer, uint64_t now)
{
    if (peer >= 4) return false;
    if (now < policy->next_probe_us[peer]) { ++policy->backoff_skips; return false; }
    return csi_sensing_reserve(policy, peer);
}

static inline void csi_sensing_result(csi_sensing_send_policy_t *policy, unsigned peer,
                                     bool success, uint64_t now, uint64_t backoff)
{
    if (peer >= 4) return;
    csi_sensing_complete(policy, peer);
    policy->next_probe_us[peer] = success ? 0 : now + backoff;
}

static inline unsigned csi_sensing_peer(uint32_t sequence, unsigned offset, unsigned count)
{
    /* Reduce before addition so uint32 wrap cannot duplicate a three-peer slot. */
    return (count && count <= 4) ? ((sequence % count) + offset) % count : 4;
}
#endif
