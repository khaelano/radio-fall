#ifndef CSI_COMMON_SERIAL_FRAME_H
#define CSI_COMMON_SERIAL_FRAME_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define CSI_SERIAL_MAGIC "CSIS"
#define CSI_SERIAL_VERSION 1
#define CSI_SERIAL_TYPE_PACKET 1
#define CSI_SERIAL_TYPE_TRANSMITTER_STATS 2
#define CSI_SERIAL_TYPE_GATEWAY_STATS 3
#define CSI_SERIAL_TYPE_CLOCK_SYNC 4
#define CSI_SERIAL_TYPE_DISCOVER_REQUEST 5
#define CSI_SERIAL_TYPE_DEVICE_STATUS 6
#define CSI_SERIAL_TYPE_PROFILE_STAGE 7
#define CSI_SERIAL_TYPE_PROFILE_STAGE_ACK 8
#define CSI_SERIAL_TYPE_PROFILE_COMMIT 9
#define CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK 10
#define CSI_SERIAL_TYPE_CLOCK_SYNC_REQUEST 11
#define CSI_SERIAL_HEADER_SIZE 8
#define CSI_SERIAL_CRC_SIZE 4
#define CSI_SERIAL_MAX_PAYLOAD 1400
#define CSI_SERIAL_MAX_RAW_SIZE \
    (CSI_SERIAL_HEADER_SIZE + CSI_SERIAL_MAX_PAYLOAD + CSI_SERIAL_CRC_SIZE)
#define CSI_SERIAL_MAX_ENCODED_SIZE \
    (CSI_SERIAL_MAX_RAW_SIZE + (CSI_SERIAL_MAX_RAW_SIZE / 254) + 1)
#define CSI_SERIAL_MAX_FRAME_SIZE (CSI_SERIAL_MAX_ENCODED_SIZE + 2)

static inline void csi_serial_write_u16(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)(value >> 8);
    destination[1] = (uint8_t)value;
}

static inline void csi_serial_write_u32(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value >> 24);
    destination[1] = (uint8_t)(value >> 16);
    destination[2] = (uint8_t)(value >> 8);
    destination[3] = (uint8_t)value;
}

static inline uint32_t csi_serial_crc32(const uint8_t *data, size_t length)
{
    uint32_t crc = 0xffffffffU;
    for (size_t index = 0; index < length; ++index) {
        crc ^= data[index];
        for (int bit = 0; bit < 8; ++bit) {
            const uint32_t mask = (uint32_t)-(int32_t)(crc & 1U);
            crc = (crc >> 1) ^ (0xedb88320U & mask);
        }
    }
    return crc ^ 0xffffffffU;
}

static inline size_t csi_serial_cobs_encode(const uint8_t *input,
                                            size_t input_length,
                                            uint8_t *output,
                                            size_t output_capacity)
{
    if (input == NULL || output == NULL || output_capacity == 0) {
        return 0;
    }
    size_t read_index = 0;
    size_t write_index = 1;
    size_t code_index = 0;
    uint8_t code = 1;
    while (read_index < input_length) {
        if (input[read_index] == 0) {
            if (code_index >= output_capacity) return 0;
            output[code_index] = code;
            code = 1;
            code_index = write_index++;
            if (write_index > output_capacity) return 0;
            ++read_index;
            continue;
        }
        if (write_index >= output_capacity) return 0;
        output[write_index++] = input[read_index++];
        ++code;
        if (code == 0xff) {
            if (code_index >= output_capacity) return 0;
            output[code_index] = code;
            code = 1;
            code_index = write_index++;
            if (write_index > output_capacity) return 0;
        }
    }
    if (code_index >= output_capacity) return 0;
    output[code_index] = code;
    return write_index;
}

static inline size_t csi_serial_encode_frame(uint8_t type,
                                             const uint8_t *payload,
                                             size_t payload_length,
                                             uint8_t *raw,
                                             size_t raw_capacity,
                                             uint8_t *frame,
                                             size_t frame_capacity)
{
    if (payload == NULL || raw == NULL || frame == NULL ||
        payload_length > CSI_SERIAL_MAX_PAYLOAD || payload_length > UINT16_MAX) {
        return 0;
    }
    const size_t raw_length = CSI_SERIAL_HEADER_SIZE + payload_length +
                              CSI_SERIAL_CRC_SIZE;
    if (raw_capacity < raw_length || frame_capacity < 3) return 0;
    memcpy(raw, CSI_SERIAL_MAGIC, 4);
    raw[4] = CSI_SERIAL_VERSION;
    raw[5] = type;
    csi_serial_write_u16(raw + 6, (uint16_t)payload_length);
    memcpy(raw + CSI_SERIAL_HEADER_SIZE, payload, payload_length);
    csi_serial_write_u32(raw + CSI_SERIAL_HEADER_SIZE + payload_length,
                          csi_serial_crc32(raw, CSI_SERIAL_HEADER_SIZE + payload_length));
    frame[0] = 0;
    const size_t encoded_length = csi_serial_cobs_encode(
        raw, raw_length, frame + 1, frame_capacity - 2);
    if (encoded_length == 0) return 0;
    frame[encoded_length + 1] = 0;
    return encoded_length + 2;
}

#endif
