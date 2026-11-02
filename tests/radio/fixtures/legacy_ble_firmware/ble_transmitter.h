#ifndef CSI_BLE_TRANSMITTER_H
#define CSI_BLE_TRANSMITTER_H
#include "ble_protocol.h"
#include "radio_profile.h"
void csi_ble_tx_init(const csi_radio_profile_t *profile,
                    bool (*write_frame)(uint8_t, const uint8_t *, size_t));
size_t csi_ble_tx_control(const uint8_t *p, size_t n, uint8_t *response);
bool csi_ble_tx_snapshot(csi_ble_config_t *config, uint32_t *boot, uint32_t *generation);
void csi_ble_tx_round(const csi_ble_config_t *c, uint32_t boot, uint32_t sequence,
    uint64_t enqueue, uint64_t deadline, uint32_t result);
void csi_ble_tx_wait(uint64_t deadline);
#endif
