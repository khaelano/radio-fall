#ifndef CSI_WIRELESS_LINK_H
#define CSI_WIRELESS_LINK_H
#include "wireless_link_protocol.h"
/* role 0 = C5 transmitter, role 1 = C6 USB gateway. USB is the pairing root. */
void wl_init(uint8_t role,const uint8_t local_mac[6],wl_emit_t receive,void *context);
bool wl_pair(const uint8_t *payload,size_t size);
bool wl_send(uint8_t type,const uint8_t *payload,size_t size);
bool wl_paired(void);
bool wl_ready(void);
bool wl_faulted(void);
const char *wl_failure_reason(void);
const char *wl_debug(void);
uint32_t wl_drops(void);
uint32_t wl_peer_changes(void);
void wl_session_active(bool active);
void wl_host_failure(void);
void wl_expect_peer_restart(void);
#endif
