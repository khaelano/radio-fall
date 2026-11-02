#ifndef CSI_GATEWAY_TRANSPORT_H
#define CSI_GATEWAY_TRANSPORT_H
#include "gateway_protocol.h"
#include "radio_profile.h"
void gw_receiver_init(const csi_radio_profile_t *profile,const uint8_t *mac,uint32_t boot);
bool gw_receiver_observe(const uint8_t *p,size_t n,uint64_t received);
bool gw_receiver_enqueue(const uint8_t *p,uint16_t n,uint64_t received);
#endif
