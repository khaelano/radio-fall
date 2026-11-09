#ifndef CSI_GATEWAY_TRANSMITTER_H
#define CSI_GATEWAY_TRANSMITTER_H
#include "gateway_protocol.h"
#include "radio_profile.h"
void gw_tx_init(const csi_radio_profile_t *p,bool (*writer)(uint8_t,const uint8_t *,size_t));
size_t gw_tx_control(const uint8_t *p,size_t n,uint8_t *response);
bool gw_tx_running(void);
void gw_tx_reference_failure(void);
bool gw_tx_snapshot(gw_config_t *config,uint32_t *boot,uint32_t *generation);
void gw_tx_round(const gw_config_t *c,uint32_t boot,uint32_t sequence,uint64_t enqueue,uint64_t deadline,uint32_t result);
void gw_tx_wait(uint64_t deadline);
void gw_tx_schedule(gw_schedule_t *schedule);
#endif
