#ifndef CSI_CLOCK_PROTOCOL_H
#define CSI_CLOCK_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "serial_frame.h"

#define CSI_SENSING_MAGIC "CSIT"
#define CSI_SENSING_VERSION 1
#define CSI_SENSING_FLAG_SYNC_REQUEST (1U << 0)
#define CSI_PROFILE_FINGERPRINT_SIZE 16
#define CSI_SENSING_HEADER_SIZE (24 + CSI_PROFILE_FINGERPRINT_SIZE)
#define CSI_SENSING_PAYLOAD_OFFSET 15
#define CSI_SYNC_ID_NONE UINT32_MAX

#define CSI_SYNC_RESPONSE_MAGIC "CSYR"
#define CSI_SYNC_RESPONSE_VERSION 1
#define CSI_SYNC_RESPONSE_SIZE 48

#define CSI_CLOCK_SAMPLE_MAGIC "CSYS"
#define CSI_CLOCK_SAMPLE_VERSION 1
#define CSI_CLOCK_SAMPLE_SIZE 72

typedef struct {
    uint32_t sequence;
    uint8_t version;
    uint32_t sync_id;
    uint64_t tx_t1_us;
    bool sync_requested;
    uint8_t profile_fingerprint[CSI_PROFILE_FINGERPRINT_SIZE];
} csi_sensing_packet_t;

typedef struct {
    uint32_t sync_id;
    uint32_t sensing_sequence;
    uint32_t receiver_boot_id;
    uint32_t rx_radio_t2_us;
    uint64_t tx_t1_us;
    uint64_t rx_t2_us;
    uint64_t rx_t3_us;
} csi_sync_response_t;

typedef struct {
    uint32_t sync_id;
    uint32_t sensing_sequence;
    uint32_t receiver_boot_id;
    uint64_t tx_t1_us;
    uint64_t rx_t2_us;
    uint64_t rx_t3_us;
    uint64_t tx_t4_us;
    uint32_t rx_radio_t2_us;
    uint32_t tx_radio_t4_us;
    uint8_t receiver_mac[6];
} csi_clock_sample_t;

static inline uint16_t csi_clock_read_u16(const uint8_t *source)
{
    return ((uint16_t)source[0] << 8) | source[1];
}

static inline uint32_t csi_clock_read_u32(const uint8_t *source)
{
    return ((uint32_t)source[0] << 24) |
           ((uint32_t)source[1] << 16) |
           ((uint32_t)source[2] << 8) |
           source[3];
}

static inline uint64_t csi_clock_read_u64(const uint8_t *source)
{
    return ((uint64_t)csi_clock_read_u32(source) << 32) |
           csi_clock_read_u32(source + 4);
}

static inline void csi_clock_write_u16(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)(value >> 8);
    destination[1] = (uint8_t)value;
}

static inline void csi_clock_write_u32(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value >> 24);
    destination[1] = (uint8_t)(value >> 16);
    destination[2] = (uint8_t)(value >> 8);
    destination[3] = (uint8_t)value;
}

static inline void csi_clock_write_u64(uint8_t *destination, uint64_t value)
{
    csi_clock_write_u32(destination, (uint32_t)(value >> 32));
    csi_clock_write_u32(destination + 4, (uint32_t)value);
}

static inline size_t csi_sensing_encode(uint8_t *destination, size_t capacity,
                                        const csi_sensing_packet_t *packet)
{
    if (destination == NULL || packet == NULL ||
        capacity < CSI_SENSING_HEADER_SIZE) {
        return 0;
    }
    memcpy(destination, CSI_SENSING_MAGIC, 4);
    destination[4] = CSI_SENSING_VERSION;
    destination[5] = packet->sync_requested ? CSI_SENSING_FLAG_SYNC_REQUEST : 0;
    csi_clock_write_u16(destination + 6, CSI_SENSING_HEADER_SIZE);
    csi_clock_write_u32(destination + 8, packet->sequence);
    csi_clock_write_u32(destination + 12,
                        packet->sync_requested ? packet->sync_id : CSI_SYNC_ID_NONE);
    csi_clock_write_u64(destination + 16, packet->tx_t1_us);
    memcpy(destination + 24, packet->profile_fingerprint,
           CSI_PROFILE_FINGERPRINT_SIZE);
    return CSI_SENSING_HEADER_SIZE;
}

static inline bool csi_sensing_decode(const uint8_t *source, size_t length,
                                      csi_sensing_packet_t *packet)
{
    if (source == NULL || packet == NULL || length < CSI_SENSING_HEADER_SIZE ||
        memcmp(source, CSI_SENSING_MAGIC, 4) != 0 ||
        (source[4] != CSI_SENSING_VERSION && source[4] != 2 && source[4] != 3 && source[4] != 4) ||
        (source[5] & ~CSI_SENSING_FLAG_SYNC_REQUEST) != 0 ||
        (source[4] == 1 ? csi_clock_read_u16(source + 6) != CSI_SENSING_HEADER_SIZE :
         source[4] == 2 ? (length < 84 || csi_clock_read_u16(source + 6) != 84) :
         source[4] == 4 ? (length < 180 || csi_clock_read_u16(source + 6) != 180 ||
          csi_serial_crc32(source, 176) != csi_clock_read_u32(source + 176)) :
         (length < 88 || csi_clock_read_u16(source + 6) != 88 ||
          csi_serial_crc32(source, 84) != csi_clock_read_u32(source + 84)))) {
        return false;
    }
    packet->version = source[4];
    packet->sequence = csi_clock_read_u32(source + 8);
    packet->sync_id = csi_clock_read_u32(source + 12);
    packet->tx_t1_us = csi_clock_read_u64(source + 16);
    memcpy(packet->profile_fingerprint, source + 24,
           CSI_PROFILE_FINGERPRINT_SIZE);
    packet->sync_requested =
        (source[5] & CSI_SENSING_FLAG_SYNC_REQUEST) != 0;
    return !packet->sync_requested || packet->sync_id != CSI_SYNC_ID_NONE;
}

static inline size_t csi_sync_response_encode(
    uint8_t *destination, size_t capacity, const csi_sync_response_t *response)
{
    if (destination == NULL || response == NULL ||
        capacity < CSI_SYNC_RESPONSE_SIZE) {
        return 0;
    }
    memcpy(destination, CSI_SYNC_RESPONSE_MAGIC, 4);
    destination[4] = CSI_SYNC_RESPONSE_VERSION;
    destination[5] = 0;
    csi_clock_write_u16(destination + 6, CSI_SYNC_RESPONSE_SIZE);
    csi_clock_write_u32(destination + 8, response->sync_id);
    csi_clock_write_u32(destination + 12, response->sensing_sequence);
    csi_clock_write_u32(destination + 16, response->receiver_boot_id);
    csi_clock_write_u32(destination + 20, response->rx_radio_t2_us);
    csi_clock_write_u64(destination + 24, response->tx_t1_us);
    csi_clock_write_u64(destination + 32, response->rx_t2_us);
    csi_clock_write_u64(destination + 40, response->rx_t3_us);
    return CSI_SYNC_RESPONSE_SIZE;
}

static inline bool csi_sync_response_decode(
    const uint8_t *source, size_t length, csi_sync_response_t *response)
{
    if (source == NULL || response == NULL || length != CSI_SYNC_RESPONSE_SIZE ||
        memcmp(source, CSI_SYNC_RESPONSE_MAGIC, 4) != 0 ||
        source[4] != CSI_SYNC_RESPONSE_VERSION || source[5] != 0 ||
        csi_clock_read_u16(source + 6) != CSI_SYNC_RESPONSE_SIZE) {
        return false;
    }
    response->sync_id = csi_clock_read_u32(source + 8);
    response->sensing_sequence = csi_clock_read_u32(source + 12);
    response->receiver_boot_id = csi_clock_read_u32(source + 16);
    response->rx_radio_t2_us = csi_clock_read_u32(source + 20);
    response->tx_t1_us = csi_clock_read_u64(source + 24);
    response->rx_t2_us = csi_clock_read_u64(source + 32);
    response->rx_t3_us = csi_clock_read_u64(source + 40);
    return response->sync_id != CSI_SYNC_ID_NONE &&
           response->rx_t3_us >= response->rx_t2_us;
}

static inline size_t csi_clock_sample_encode(
    uint8_t *destination, size_t capacity, const csi_clock_sample_t *sample)
{
    if (destination == NULL || sample == NULL ||
        capacity < CSI_CLOCK_SAMPLE_SIZE) {
        return 0;
    }
    memcpy(destination, CSI_CLOCK_SAMPLE_MAGIC, 4);
    destination[4] = CSI_CLOCK_SAMPLE_VERSION;
    destination[5] = 0;
    csi_clock_write_u16(destination + 6, CSI_CLOCK_SAMPLE_SIZE);
    csi_clock_write_u32(destination + 8, sample->sync_id);
    csi_clock_write_u32(destination + 12, sample->sensing_sequence);
    csi_clock_write_u32(destination + 16, sample->receiver_boot_id);
    csi_clock_write_u32(destination + 20, 0);
    csi_clock_write_u64(destination + 24, sample->tx_t1_us);
    csi_clock_write_u64(destination + 32, sample->rx_t2_us);
    csi_clock_write_u64(destination + 40, sample->rx_t3_us);
    csi_clock_write_u64(destination + 48, sample->tx_t4_us);
    csi_clock_write_u32(destination + 56, sample->rx_radio_t2_us);
    csi_clock_write_u32(destination + 60, sample->tx_radio_t4_us);
    memcpy(destination + 64, sample->receiver_mac, 6);
    destination[70] = 0;
    destination[71] = 0;
    return CSI_CLOCK_SAMPLE_SIZE;
}

#endif
