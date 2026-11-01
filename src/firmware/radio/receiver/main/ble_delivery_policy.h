#ifndef CSI_BLE_DELIVERY_POLICY_H
#define CSI_BLE_DELIVERY_POLICY_H
#include "ble_protocol.h"
typedef enum { BLE_DELIVERY_SEND, BLE_DELIVERY_WAIT, BLE_DELIVERY_RETRY, BLE_DELIVERY_DROP } ble_delivery_action_t;
static inline ble_delivery_action_t ble_delivery_action(uint64_t now, uint64_t oldest,
    uint64_t waiting_since, bool complete, uint8_t retries, const csi_ble_config_t *c)
{
    if (now-oldest >= (uint64_t)c->maximum_age_ms*1000) return BLE_DELIVERY_DROP;
    if (!complete) return BLE_DELIVERY_SEND;
    if (now-waiting_since < (uint64_t)c->ack_timeout_ms*1000) return BLE_DELIVERY_WAIT;
    return retries < c->maximum_retries ? BLE_DELIVERY_RETRY : BLE_DELIVERY_DROP;
}
#endif
