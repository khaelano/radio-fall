#ifndef CSI_REFERENCE_RELAY_PROTOCOL_H
#define CSI_REFERENCE_RELAY_PROTOCOL_H

#include "serial_frame.h"
#include "wireless_link_protocol.h"

/* The reliable stream/codec is shared with CWL2; the transport is ESP-NOW.
 * Encrypted, explicitly paired ESP-NOW peers authenticate these packets. */
#define RR_VERSION 1
#define RR_HEADER 39
#define RR_PACKET (RR_HEADER + WL_PAYLOAD + 4)
#define RR_PAIR_SIZE 48
#define RR_LIFETIME_US 750000ULL
#define RR_HEARTBEAT_US 100000ULL
#define RR_PEER_TIMEOUT_US 1000000ULL
#define RR_QUEUE_BYTES 65536
#define RR_STATS_TYPE 30
#define RR_STATS_SIZE 24
#define RR_USB_RECOVER 31

static inline const char *rr_fault_name(uint8_t code)
{
    static const char *const names[] = {"fault", "peer_restart", "peer_timeout",
        "packet_expired", "source_overflow", "uart_fault", "uart_ingress",
        "delivery_failed", "host_usb_failure", "queue_lock", "encode_failed",
        "invalid_ack"};
    return code < sizeof(names) / sizeof(names[0]) ? names[code] : names[0];
}
static inline uint8_t rr_fault_code(const char *name)
{
    for (uint8_t code = 1; code <= 11; ++code)
        if (!strcmp(rr_fault_name(code), name)) return code;
    return 0;
}

static inline size_t rr_packet_encode(uint8_t *out, uint8_t role, bool fault,
                                     uint32_t boot, uint64_t nonce, uint64_t echo,
                                     const wl_stream_t *stream,
                                     const wl_slot_t *slot)
{
    size_t size = slot ? slot->size : 0;
    memcpy(out, "CRL1", 4);
    out[4] = RR_VERSION;
    out[5] = role;
    out[6] = fault;
    out[7] = 0;
    wl_w32(out + 8, boot);
    wl_w64(out + 12, nonce);
    wl_w64(out + 20, echo);
    wl_w32(out + 28, slot ? slot->sequence : WL_EMPTY);
    wl_w32(out + 32, stream->next_rx);
    out[36] = wl_stream_mask(stream);
    wl_w16(out + 37, size);
    if (size) memcpy(out + RR_HEADER, slot->data, size);
    csi_serial_write_u32(out + RR_HEADER + size,
                         csi_serial_crc32(out, RR_HEADER + size));
    return RR_HEADER + size + 4;
}

static inline bool rr_packet_valid(const uint8_t *p, size_t size, uint8_t role)
{
    if (size < RR_HEADER + 4 || size > RR_PACKET || memcmp(p, "CRL1", 4) ||
        p[4] != RR_VERSION || p[5] != (role ^ 1) || p[6] > 1 ||
        (!p[6] && p[7]) || p[7] > 11 ||
        wl_u16(p + 37) != size - RR_HEADER - 4 || !wl_u32(p + 8) ||
        !wl_u64(p + 12) || p[36] & 0xf0) return false;
    if ((wl_u32(p + 28) == WL_EMPTY) != (wl_u16(p + 37) == 0)) return false;
    return csi_serial_crc32(p, size - 4) == wl_u32(p + size - 4);
}

#endif
