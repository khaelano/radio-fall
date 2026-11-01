#ifndef CSI_BLE_TRANSPORT_H
#define CSI_BLE_TRANSPORT_H
#include "ble_protocol.h"
#include "radio_profile.h"

void csi_ble_init(const csi_radio_profile_t *profile, const uint8_t *mac, uint32_t boot);
bool csi_ble_observe(const uint8_t *data, size_t length, uint64_t received);
bool csi_ble_enqueue(const uint8_t *record, uint16_t length, uint64_t captured);
#endif
