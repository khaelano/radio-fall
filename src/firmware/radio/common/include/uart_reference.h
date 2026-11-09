#ifndef CSI_UART_REFERENCE_H
#define CSI_UART_REFERENCE_H

#include "wireless_link_protocol.h"

/* Native UART0 carries the existing CRC-protected CSIS frames. This module
 * never initializes, scans, retunes or transmits on a Wi-Fi/BLE radio. */
void uart_ref_init(wl_emit_t receive, void *context);
bool uart_ref_send(uint8_t type, const uint8_t *payload, size_t size);
void uart_ref_session_active(bool active);
bool uart_ref_enabled(void);
bool uart_ref_faulted(void);
uint32_t uart_ref_errors(void);
uint32_t uart_ref_received(void);

#endif
