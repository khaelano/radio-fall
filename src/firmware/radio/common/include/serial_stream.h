#ifndef CSI_SERIAL_STREAM_H
#define CSI_SERIAL_STREAM_H

#include <stdbool.h>
#include "serial_frame.h"

typedef struct {
    size_t used;
    bool synchronized, dropping;
    uint8_t encoded[CSI_SERIAL_MAX_ENCODED_SIZE];
    uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE];
} csi_serial_decoder_t;

/* 0 = incomplete, 1 = complete CRC-checked frame, -1 = framing error.
 * Boot text is ignored until a synchronization delimiter. Payload storage
 * remains owned by the decoder until the next call. */
static inline int csi_serial_feed(csi_serial_decoder_t *d, uint8_t byte,
                                  uint8_t *type, const uint8_t **payload,
                                  size_t *size)
{
    if (byte) {
        if (!d->synchronized || d->dropping) return 0;
        if (d->used == sizeof(d->encoded)) d->dropping = true;
        else d->encoded[d->used++] = byte;
        return 0;
    }
    if (!d->synchronized) { d->synchronized = true; return 0; }
    if (d->dropping) { d->dropping = false; d->used = 0; return -1; }
    if (!d->used) return 0;
    size_t end = d->used, in = 0, out = 0; d->used = 0;
    while (in < end) {
        unsigned code = d->encoded[in++];
        if (!code || in + code - 1 > end) return -1;
        for (unsigned i = 1; i < code; ++i) {
            if (out == sizeof(d->raw)) return -1;
            d->raw[out++] = d->encoded[in++];
        }
        if (code != 255 && in < end) {
            if (out == sizeof(d->raw)) return -1;
            d->raw[out++] = 0;
        }
    }
    if (out < 12 || memcmp(d->raw, CSI_SERIAL_MAGIC, 4) ||
        d->raw[4] != CSI_SERIAL_VERSION) return -1;
    *size = (size_t)d->raw[6] << 8 | d->raw[7];
    if (*size > CSI_SERIAL_MAX_PAYLOAD || out != *size + 12) return -1;
    const uint8_t *crc = d->raw + out - 4;
    uint32_t expected = (uint32_t)crc[0] << 24 | (uint32_t)crc[1] << 16 |
                        (uint32_t)crc[2] << 8 | crc[3];
    if (csi_serial_crc32(d->raw, out - 4) != expected) return -1;
    *type = d->raw[5]; *payload = d->raw + 8;
    return 1;
}
#endif
