#include "radio_profile.h"

#include <stdio.h>
#include <string.h>

#include "nvs.h"

static bool json_string(const char *text, const char *key, char *out, size_t size)
{
    char needle[64];
    const int written = snprintf(needle, sizeof(needle), "\"%s\":\"", key);
    if (written <= 0 || (size_t)written >= sizeof(needle)) {
        return false;
    }
    const char *start = strstr(text, needle);
    if (start == NULL) {
        return false;
    }
    start += written;
    const char *end = strchr(start, '"');
    if (end == NULL || (size_t)(end - start) + 1 > size) {
        return false;
    }
    memcpy(out, start, (size_t)(end - start));
    out[end - start] = '\0';
    return true;
}

static bool json_uint(const char *text, const char *key, unsigned int *out)
{
    char needle[64];
    const int written = snprintf(needle, sizeof(needle), "\"%s\":", key);
    if (written <= 0 || (size_t)written >= sizeof(needle)) {
        return false;
    }
    const char *start = strstr(text, needle);
    if (start == NULL) {
        return false;
    }
    return sscanf(start + written, "%u", out) == 1;
}

static bool parse_mac(const char *text, uint8_t mac[6])
{
    unsigned int values[6];
    if (sscanf(text, "%2x:%2x:%2x:%2x:%2x:%2x",
               &values[0], &values[1], &values[2], &values[3],
               &values[4], &values[5]) != 6) {
        return false;
    }
    for (size_t index = 0; index < 6; ++index) {
        if (values[index] > 0xff) {
            return false;
        }
        mac[index] = (uint8_t)values[index];
    }
    return true;
}

static bool json_mac_array(const char *text, const char *key,
                           uint8_t macs[][6], uint8_t *count, uint8_t max)
{
    char needle[64];
    const int written = snprintf(needle, sizeof(needle), "\"%s\":[", key);
    if (written <= 0 || (size_t)written >= sizeof(needle)) {
        return false;
    }
    const char *cursor = strstr(text, needle);
    if (cursor == NULL) {
        return false;
    }
    cursor += written;
    *count = 0;
    while (*count < max) {
        const char *close = strchr(cursor, ']');
        const char *start = strchr(cursor, '"');
        if (start == NULL || (close != NULL && close < start)) {
            break;
        }
        const char *end = strchr(start + 1, '"');
        if (end == NULL) {
            return false;
        }
        const size_t length = (size_t)(end - start - 1);
        if (length == 0 || length >= 18) {
            return false;
        }
        char mac[18];
        memcpy(mac, start + 1, length);
        mac[length] = '\0';
        if (!parse_mac(mac, macs[*count])) {
            return false;
        }
        ++(*count);
        cursor = end + 1;
    }
    return *count > 0;
}

void csi_radio_profile_defaults(csi_radio_profile_t *profile,
                                const uint8_t transmitter_mac[6])
{
    memset(profile, 0, sizeof(*profile));
    profile->version = CSI_RADIO_PROFILE_VERSION;
    profile->band = CSI_RADIO_BAND_2G;
    profile->channel = 6;
    profile->bandwidth_mhz = 20;
    profile->nominal_rate_hz = 100;
    memcpy(profile->country_code, "ID", 3);
    snprintf(profile->profile_id, sizeof(profile->profile_id), "fallback-2g-ch6-100hz");
    if (transmitter_mac != NULL) {
        memcpy(profile->transmitter_mac, transmitter_mac, 6);
    }
}

bool csi_radio_profile_validate(const csi_radio_profile_t *profile,
                                bool supports_5ghz)
{
    if (profile == NULL || profile->version != CSI_RADIO_PROFILE_VERSION ||
        profile->bandwidth_mhz != 20 || profile->nominal_rate_hz != 100 ||
        strncmp(profile->country_code, "ID", 2) != 0 ||
        profile->profile_id[0] == '\0' || profile->fingerprint[0] == '\0' ||
        (profile->transmitter_mac[0] == 0 && profile->transmitter_mac[1] == 0 &&
         profile->transmitter_mac[2] == 0 && profile->transmitter_mac[3] == 0 &&
         profile->transmitter_mac[4] == 0 && profile->transmitter_mac[5] == 0)) {
        return false;
    }
    if (profile->receiver_count == 0 ||
        profile->receiver_count > CSI_RADIO_PROFILE_MAX_RECEIVERS) {
        return false;
    }
    for (uint8_t index = 0; index < profile->receiver_count; ++index) {
        const uint8_t *mac = profile->receiver_macs[index];
        if (mac[0] == 0 && mac[1] == 0 && mac[2] == 0 &&
            mac[3] == 0 && mac[4] == 0 && mac[5] == 0) {
            return false;
        }
    }
    if (profile->band == CSI_RADIO_BAND_2G) {
        /* Indonesia's country table excludes the Japan-only channel 14. */
        return profile->channel >= 1 && profile->channel <= 13;
    }
    if (!supports_5ghz || profile->band != CSI_RADIO_BAND_5G) {
        return false;
    }
    switch (profile->channel) {
    case 36:
    case 40:
    case 44:
    case 48:
    case 149:
    case 153:
    case 157:
    case 161:
    case 165:
    case 169:
    case 173:
    case 177:
        return true;
    default:
        return false;
    }
}

bool csi_radio_profile_load(csi_radio_profile_t *profile)
{
    nvs_handle_t handle;
    if (nvs_open("radio", NVS_READONLY, &handle) != ESP_OK) {
        return false;
    }
    size_t size = sizeof(*profile);
    const esp_err_t result = nvs_get_blob(handle, "profile", profile, &size);
    nvs_close(handle);
    return result == ESP_OK && size == sizeof(*profile);
}

bool csi_radio_profile_save(const csi_radio_profile_t *profile)
{
    nvs_handle_t handle;
    if (nvs_open("radio", NVS_READWRITE, &handle) != ESP_OK) {
        return false;
    }
    const esp_err_t result = nvs_set_blob(handle, "profile", profile, sizeof(*profile));
    const esp_err_t commit = result == ESP_OK ? nvs_commit(handle) : result;
    nvs_close(handle);
    return commit == ESP_OK;
}

bool csi_radio_profile_from_json(const uint8_t *payload, size_t length,
                                 csi_radio_profile_t *profile)
{
    if (payload == NULL || profile == NULL || length == 0 || length > 1200) {
        return false;
    }
    char text[1201];
    memcpy(text, payload, length);
    text[length] = '\0';
    memset(profile, 0, sizeof(*profile));
    profile->version = CSI_RADIO_PROFILE_VERSION;
    char band[12];
    char mac[18];
    unsigned int channel;
    unsigned int bandwidth;
    unsigned int rate;
    if (!json_string(text, "profile_id", profile->profile_id,
                     sizeof(profile->profile_id)) ||
        !json_string(text, "country_code", profile->country_code,
                     sizeof(profile->country_code)) ||
        !json_string(text, "band", band, sizeof(band)) ||
        !json_string(text, "fingerprint", profile->fingerprint,
                     sizeof(profile->fingerprint)) ||
        !json_string(text, "transmitter_mac", mac, sizeof(mac)) ||
        !json_uint(text, "channel", &channel) ||
        !json_uint(text, "bandwidth_mhz", &bandwidth) ||
        !json_uint(text, "nominal_rate_hz", &rate) ||
        !parse_mac(mac, profile->transmitter_mac) ||
        !json_mac_array(text, "receivers", profile->receiver_macs,
                        &profile->receiver_count,
                        CSI_RADIO_PROFILE_MAX_RECEIVERS)) {
        return false;
    }
    profile->band = strcmp(band, "5ghz") == 0 ? CSI_RADIO_BAND_5G :
                   (strcmp(band, "2.4ghz") == 0 ? CSI_RADIO_BAND_2G : 2);
    profile->channel = (uint8_t)channel;
    profile->bandwidth_mhz = (uint8_t)bandwidth;
    profile->nominal_rate_hz = (uint16_t)rate;
    return true;
}
