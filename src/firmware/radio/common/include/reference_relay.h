#ifndef CSI_REFERENCE_RELAY_H
#define CSI_REFERENCE_RELAY_H

#include "reference_relay_protocol.h"

/* One owner calls poll/receive; producers may enqueue from other tasks.
 * role 0 = UART companion C6, role 1 = laptop's USB gateway C6. */
typedef bool (*rr_receive_t)(uint8_t type, const uint8_t *data, size_t size,
                             void *context);
void rr_init(uint8_t role, const uint8_t local_mac[6], rr_receive_t receive,
             void *context);
bool rr_pair(const uint8_t *payload, size_t size);
bool rr_receive(const uint8_t source[6], const uint8_t *data, size_t size);
bool rr_send(uint8_t type, const uint8_t *data, size_t size);
void rr_poll(void);
void rr_session_active(bool active);
void rr_fail(const char *reason);
bool rr_enabled(void);
bool rr_paired(void);
bool rr_ready(void);
bool rr_faulted(void);
const char *rr_failure_reason(void);
uint32_t rr_drops(void);
uint32_t rr_peer_changes(void);
uint32_t rr_retries(void);
size_t rr_queued_bytes(void);
size_t rr_queue_peak(void);
uint8_t rr_channel(void);

#endif
