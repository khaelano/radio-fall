#ifndef CSI_RADIO_PROFILE_H
#define CSI_RADIO_PROFILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CSI_RADIO_PROFILE_VERSION 2
#define CSI_RADIO_PROFILE_ID_MAX 64
#define CSI_RADIO_PROFILE_FINGERPRINT_MAX 17
#define CSI_RADIO_PROFILE_COUNTRY_MAX 3
#define CSI_RADIO_PROFILE_MAX_RECEIVERS 4

typedef enum {
    CSI_RADIO_BAND_2G = 0,
    CSI_RADIO_BAND_5G = 1,
} csi_radio_band_t;

typedef struct {
    uint32_t version;
    uint8_t band;
    uint8_t channel;
    uint8_t bandwidth_mhz;
    uint16_t nominal_rate_hz;
    char country_code[CSI_RADIO_PROFILE_COUNTRY_MAX];
    char profile_id[CSI_RADIO_PROFILE_ID_MAX];
    char fingerprint[CSI_RADIO_PROFILE_FINGERPRINT_MAX];
    uint8_t transmitter_mac[6];
    /* Sensing frames are sent unicast at a fixed HE rate, so the transmitter
     * needs the receiver addresses at boot while it is untethered. */
    uint8_t receiver_count;
    uint8_t receiver_macs[CSI_RADIO_PROFILE_MAX_RECEIVERS][6];
} csi_radio_profile_t;

void csi_radio_profile_defaults(csi_radio_profile_t *profile,
                                const uint8_t transmitter_mac[6]);
bool csi_radio_profile_validate(const csi_radio_profile_t *profile,
                                bool supports_5ghz);
bool csi_radio_profile_load(csi_radio_profile_t *profile);
bool csi_radio_profile_save(const csi_radio_profile_t *profile);

/* Parse the compact JSON payload emitted by the host provisioner. */
bool csi_radio_profile_from_json(const uint8_t *payload, size_t length,
                                 csi_radio_profile_t *profile);

#endif
