#ifndef CSI_BATCH_POLICY_H
#define CSI_BATCH_POLICY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

static inline bool csi_batch_record_fits(size_t packet_length,
                                         size_t record_header_length,
                                         size_t csi_length,
                                         size_t capacity)
{
    const size_t entry_length = sizeof(uint16_t) + record_header_length + csi_length;
    return packet_length <= capacity && entry_length <= capacity - packet_length;
}

static inline bool csi_batch_sequence_boundary(uint32_t sensing_sequence,
                                               uint16_t records_per_batch)
{
    return records_per_batch > 0 &&
           ((sensing_sequence + 1U) % records_per_batch) == 0;
}

static inline bool csi_batch_wait_expired(uint32_t elapsed, uint32_t maximum_wait)
{
    return elapsed >= maximum_wait;
}

#endif
