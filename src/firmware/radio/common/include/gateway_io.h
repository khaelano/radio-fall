#ifndef CSI_GATEWAY_IO_H
#define CSI_GATEWAY_IO_H
#include "gateway_protocol.h"
#include "esp_now.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"

typedef struct { uint8_t source[6];uint16_t size;uint64_t received;uint8_t data[1400]; } gw_message_t;
void gw_io_init(void);
/* Control roles retain queue depth with smaller bounded payload storage. */
void gw_io_init_sized(uint16_t maximum_payload);
bool gw_send(const uint8_t *mac,const void *p,size_t n,uint32_t wait_ms);
bool gw_send_idle(void);
/* Optional task wakeup; callbacks remain short and run in Wi-Fi task context. */
void gw_io_set_wakeup(void (*wakeup)(void *),void *context);
typedef struct {
    uint32_t samples, failures, minimum_us, maximum_us, maximum_failure_us, late;
    uint64_t total_us;
} gw_send_stats_t;
bool gw_measure_sends_begin(uint64_t deadline,bool enabled);
bool gw_measure_sends_finish(gw_send_stats_t *stats);
void gw_peer(const uint8_t *mac,bool he);
/* Registered HT20 peer only; explicit long-GI MCS0..3, no scanning or retune. */
bool gw_peer_set_mcs(const uint8_t *mac,uint8_t mcs);
QueueHandle_t gw_incoming(void);
uint32_t gw_io_drops(void);
uint32_t gw_io_mac_failures(void);
bool gw_usb_write(uint8_t type,const uint8_t *p,size_t n);
/* USB parser ignores boot text until delimiter; rejects malformed/CRC frames. */
bool gw_usb_read(uint8_t *type,uint8_t *p,size_t *n);
#endif
