#include <inttypes.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_random.h"
#include "freertos/semphr.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_system.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"

#include "csi_clock_protocol.h"
#include "radio_profile.h"
#include "radio_board.h"
#include "radio_diagnostics.h"
#include "gateway_transmitter.h"
#include "gateway_io.h"

#include "serial_frame.h"

#if !CONFIG_IDF_TARGET_ESP32C5 && !CONFIG_IDF_TARGET_ESP32C6
#error "The CSI transmitter firmware requires an ESP32-C5 or ESP32-C6 target"
#endif

static const char *TAG = "csi_tx";
#if CONFIG_CSI_DIAGNOSTIC_HT20
static const char *s_sensing_phy = "ht20";
#else
static const char *s_sensing_phy = "he20";
#endif
static uint8_t s_transmitter_mac[6];
static csi_radio_profile_t s_profile;
static bool s_profile_provisioned;
static csi_radio_profile_t s_staged_profile;
static bool s_profile_staged;
static portMUX_TYPE s_stats_lock = portMUX_INITIALIZER_UNLOCKED;

typedef struct {
    uint32_t attempts;
    uint32_t immediate_errors;
    uint32_t asynchronous_successes;
    uint32_t asynchronous_failures;
} transmitter_stats_t;

static transmitter_stats_t s_stats;
static volatile bool s_radio_active;
static int8_t s_tx_power_quarter_dbm = -1;
static uint8_t s_radio_mac[6];
static SemaphoreHandle_t s_control_write_mutex;
static bool usb_control_write(uint8_t type, const uint8_t *payload, size_t length);

static void stats_add(uint32_t *counter, uint32_t amount)
{
    portENTER_CRITICAL(&s_stats_lock);
    *counter += amount;
    portEXIT_CRITICAL(&s_stats_lock);
}

static transmitter_stats_t stats_snapshot(void)
{
    transmitter_stats_t snapshot;
    portENTER_CRITICAL(&s_stats_lock);
    snapshot = s_stats;
    portEXIT_CRITICAL(&s_stats_lock);
    return snapshot;
}

static void transmitter_stats_task(void *arg)
{
    (void)arg;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        const transmitter_stats_t stats = stats_snapshot();
        /* ROM printing can reach USB even with the secondary console disabled.
         * Every writer on the transmitter reference link must use the framing mutex. */
        char line[128];
        const int length = snprintf(
            line, sizeof(line),
            "CSI_TX_STATS,%" PRIu64 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
            ",%" PRIu32,
            (uint64_t)(esp_timer_get_time() / 1000),
            stats.attempts,
            stats.immediate_errors,
            stats.asynchronous_successes,
            stats.asynchronous_failures);
        if (length > 0 && (size_t)length < sizeof(line)) {
            usb_control_write(CSI_SERIAL_TYPE_TRANSMITTER_STATS,
                              (const uint8_t *)line, (size_t)length);
        }
    }
}

static bool parse_mac(const char *text, uint8_t mac[6])
{
    if (text == NULL || strlen(text) != 17) {
        return false;
    }
    for (size_t i = 0; i < 17; ++i) {
        if ((i % 3) == 2) {
            if (text[i] != ':') {
                return false;
            }
        } else if (!isxdigit((unsigned char)text[i])) {
            return false;
        }
    }
    for (size_t i = 0; i < 6; ++i) {
        unsigned int octet;
        if (sscanf(text + (i * 3), "%2x", &octet) != 1) {
            return false;
        }
        mac[i] = (uint8_t)octet;
    }
    return true;
}

static size_t usb_decode_cobs(const uint8_t *encoded, size_t length,
                              uint8_t *decoded, size_t capacity)
{
    size_t input = 0;
    size_t output = 0;
    while (input < length) {
        const uint8_t code = encoded[input++];
        if (code == 0 || input + code - 1 > length) return 0;
        for (uint8_t index = 1; index < code; ++index) {
            if (output >= capacity) return 0;
            decoded[output++] = encoded[input++];
        }
        if (code != 0xff && input < length) {
            if (output >= capacity) return 0;
            decoded[output++] = 0;
        }
    }
    return output;
}

static bool usb_control_write(uint8_t type, const uint8_t *payload, size_t length)
{
    /* Control, statistics and round-log tasks share this workspace and mutex. */
    if (xSemaphoreTake(s_control_write_mutex, pdMS_TO_TICKS(20)) != pdTRUE) return false;
    static uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE];
    static uint8_t frame[CSI_SERIAL_MAX_FRAME_SIZE];
    const size_t frame_length = csi_serial_encode_frame(
        type, payload, length, raw, sizeof(raw), frame, sizeof(frame));
    bool ok = frame_length && usb_serial_jtag_write_bytes(frame, frame_length, pdMS_TO_TICKS(20)) == (int)frame_length;
    xSemaphoreGive(s_control_write_mutex);
    return ok;
}

static void usb_status(void)
{
    /* usb_status() is called only by the USB control task. */
    static char payload[768];
    const char *target =
#if CONFIG_IDF_TARGET_ESP32C5
        "esp32c5";
#else
        "esp32c6";
#endif
    const transmitter_stats_t tx_stats = stats_snapshot();
    portENTER_CRITICAL(&s_stats_lock);
    uint32_t busy_skips = gw_io_mac_failures();
    uint32_t backoff_skips = gw_io_drops();
    portEXIT_CRITICAL(&s_stats_lock);
    const int length = snprintf(
        payload, sizeof(payload),
        "{\"role\":\"transmitter\",\"target\":\"%s\","
        "\"mac\":\"" MACSTR "\",\"firmware_version\":\"3\","
        "\"protocol_version\":3,\"transport_config_max_version\":7,\"cpu_max_mhz\":%u,\"profile_id\":\"%s\","
        "\"profile_fingerprint\":\"%s\",\"ready\":%s,"
        "\"csi_transport\":\"espnow_gateway\",\"reset_reason\":\"%s\","
        "\"uptime_ms\":%" PRIu64 ",\"radio_active\":%s,"
        "\"tx_power_quarter_dbm\":%d,"
        "\"radio_mac\":\"" MACSTR "\",\"mac_failures\":%" PRIu32 ","
        "\"sensing_phy\":\"%s\","
        "\"board\":\"%s\",\"antenna\":\"%s\","
        "\"sensing_version\":4,"
        "\"peer_retry_backoff_ms\":%u,\"rx_control_drops\":%" PRIu32 ","
        "\"tx\":{\"attempts\":%lu,\"imm_err\":%lu,\"ok\":%lu,\"fail\":%lu}}",
        target, MAC2STR(s_transmitter_mac), (unsigned)CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ, s_profile.profile_id,
        s_profile.fingerprint, s_profile_provisioned ? "true" : "false",
        csi_reset_reason_name(), (uint64_t)(esp_timer_get_time() / 1000),
        s_radio_active ? "true" : "false", s_tx_power_quarter_dbm,
        MAC2STR(s_radio_mac), busy_skips,
        s_sensing_phy,
        csi_board_name(), csi_board_antenna(),
        0U, backoff_skips,
        (unsigned long)tx_stats.attempts,
        (unsigned long)tx_stats.immediate_errors,
        (unsigned long)tx_stats.asynchronous_successes,
        (unsigned long)tx_stats.asynchronous_failures);
    if (length > 0 && (size_t)length < sizeof(payload))
        usb_control_write(CSI_SERIAL_TYPE_DEVICE_STATUS, (const uint8_t *)payload, (size_t)length);
}

static void espnow_init(void);

/* Profile changes restart the scheduler and reload the fixed inventory. */
static void apply_staged_profile(void)
{
    usb_control_write(CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK, (const uint8_t *)"ok", 2);
    vTaskDelay(pdMS_TO_TICKS(50));
    esp_restart();
}

static void usb_control_task(void *arg)
{
    (void)arg;
    /* There is exactly one USB control task.  Its receive workspace must not
     * consume the task stack because profile parsing adds another 1.2 KiB
     * JSON buffer on the same call chain. */
    static uint8_t encoded[CSI_SERIAL_MAX_ENCODED_SIZE];
    static uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE];
    size_t used = 0;
    while (true) {
        uint8_t byte = 0;
        if (usb_serial_jtag_read_bytes(&byte, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (byte != 0) {
            if (used < sizeof(encoded)) encoded[used++] = byte;
            else used = 0;
            continue;
        }
        if (used == 0) continue;
        const size_t raw_length = usb_decode_cobs(encoded, used, raw, sizeof(raw));
        used = 0;
        if (raw_length < CSI_SERIAL_HEADER_SIZE + CSI_SERIAL_CRC_SIZE ||
            memcmp(raw, CSI_SERIAL_MAGIC, 4) != 0 || raw[4] != CSI_SERIAL_VERSION) continue;
        const uint16_t payload_length = ((uint16_t)raw[6] << 8) | raw[7];
        if (raw[5] == CSI_SERIAL_TYPE_DISCOVER_REQUEST) {
            usb_status();
            continue;
        }
        if (payload_length > CSI_SERIAL_MAX_PAYLOAD ||
            raw_length != CSI_SERIAL_HEADER_SIZE + payload_length + CSI_SERIAL_CRC_SIZE ||
            csi_serial_crc32(raw, CSI_SERIAL_HEADER_SIZE + payload_length) !=
                ((uint32_t)raw[8 + payload_length] << 24 |
                 (uint32_t)raw[9 + payload_length] << 16 |
                 (uint32_t)raw[10 + payload_length] << 8 |
                 raw[11 + payload_length])) continue;
        if (raw[5] == GW_CONTROL) {
            uint8_t response[64];
            size_t response_length = gw_tx_control(raw + CSI_SERIAL_HEADER_SIZE, payload_length, response);
            usb_control_write(GW_RESPONSE, response, response_length);
            continue;
        }
        if (raw[5] == CSI_SERIAL_TYPE_PROFILE_STAGE) {
            csi_radio_profile_t staged;
            const bool valid = csi_radio_profile_from_json(
                raw + CSI_SERIAL_HEADER_SIZE, payload_length, &staged) &&
                csi_radio_profile_validate(&staged,
#if CONFIG_SOC_WIFI_SUPPORT_5G
                                           true
#else
                                           false
#endif
                                           );
            if (valid) {
                s_staged_profile = staged;
                s_profile_staged = true;
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_STAGE_ACK, (const uint8_t *)"ok", 2);
            } else usb_control_write(CSI_SERIAL_TYPE_PROFILE_STAGE_ACK, (const uint8_t *)"error", 5);
        } else if (raw[5] == CSI_SERIAL_TYPE_PROFILE_COMMIT) {
            if (s_profile_staged && csi_radio_profile_save(&s_staged_profile)) {
                s_profile_staged = false;
                apply_staged_profile();
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK, (const uint8_t *)"ok", 2);
            } else {
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK, (const uint8_t *)"error", 5);
            }
        }
    }
}

static void usb_control_init(void)
{
    s_control_write_mutex = xSemaphoreCreateMutex();
    if (!s_control_write_mutex) abort();
    gw_tx_init(&s_profile, usb_control_write);
    if (!usb_serial_jtag_is_driver_installed()) {
        usb_serial_jtag_driver_config_t config = {
            .tx_buffer_size = CSI_SERIAL_MAX_FRAME_SIZE * 4,
            .rx_buffer_size = 512,
        };
        ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&config));
    }
    if (xTaskCreate(usb_control_task, "csi_usb_ctl", 4096, NULL, 6, NULL) != pdPASS)
        abort();
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_config));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    // The STA interface must be disabled while its MAC is changed.
    ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA, s_transmitter_mac));
    ESP_ERROR_CHECK(esp_wifi_start());

    // On the dual-band part both the band mode and the protocol selection are
    // only accepted after the driver is started, and bandwidth requires the
    // band mode to be set first.  Doing any of this before esp_wifi_start()
    // aborts with ESP_ERR_WIFI_NOT_STARTED / ESP_ERR_NOT_SUPPORTED.
    if (s_profile.band == CSI_RADIO_BAND_5G) {
#if !CONFIG_SOC_WIFI_SUPPORT_5G
        ESP_LOGE(TAG, "5 GHz profile is not supported by this target");
        abort();
#else
        ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY));
        ESP_ERROR_CHECK(esp_wifi_set_protocol(
            WIFI_IF_STA, WIFI_PROTOCOL_11A | WIFI_PROTOCOL_11N |
                           WIFI_PROTOCOL_11AC | WIFI_PROTOCOL_11AX));
#endif
    } else {
        ESP_ERROR_CHECK(esp_wifi_set_band_mode(WIFI_BAND_MODE_2G_ONLY));
        ESP_ERROR_CHECK(esp_wifi_set_protocol(
            WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G |
                           WIFI_PROTOCOL_11N | WIFI_PROTOCOL_11AX));
    }
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW20));
    ESP_ERROR_CHECK(esp_wifi_set_country_code("ID", true));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(s_profile.channel, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(CONFIG_CSI_TX_POWER_QUARTER_DBM));
    ESP_ERROR_CHECK(esp_wifi_get_max_tx_power(&s_tx_power_quarter_dbm));
}

static void espnow_init(void)
{
    portENTER_CRITICAL(&s_stats_lock);
    portEXIT_CRITICAL(&s_stats_lock);
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, s_radio_mac));
    gw_io_init_sized(GW_STATUS_SIZE);
    for(unsigned i=0;i<s_profile.receiver_count;++i)gw_peer(s_profile.receiver_macs[i],true);
    ESP_LOGI(TAG, "sensing link PHY=HE20 MCS0 long-GI peers=%u",
             s_profile.receiver_count);
}

static void transmitter_task(void *arg)
{
    (void)arg;
    uint32_t sequence = 0, previous_generation = UINT32_MAX;
    uint64_t deadline = 0;
    for (;;) {
        gw_config_t config; uint32_t boot, generation;
        if (!gw_tx_snapshot(&config, &boot, &generation)) {
            if (s_radio_active) {
                ESP_ERROR_CHECK(esp_now_deinit());
                ESP_ERROR_CHECK(esp_wifi_stop());
                s_radio_active = false;
            }
            vTaskDelay(pdMS_TO_TICKS(20));
            previous_generation = UINT32_MAX;
            continue;
        }
        if (!s_radio_active) {
            ESP_ERROR_CHECK(esp_wifi_start());
            ESP_ERROR_CHECK(esp_wifi_set_channel(s_profile.channel, WIFI_SECOND_CHAN_NONE));
            ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(CONFIG_CSI_TX_POWER_QUARTER_DBM));
            ESP_ERROR_CHECK(esp_wifi_get_max_tx_power(&s_tx_power_quarter_dbm));
            espnow_init();
            s_radio_active = true;
            continue; /* Recheck the host lease after radio startup. */
        }
        uint64_t now = esp_timer_get_time();
        uint32_t period = 1000000U/config.rate;
        if (generation != previous_generation) {
            sequence = 0; deadline = now; previous_generation = generation;
        }
        if (now < deadline) { gw_tx_wait(deadline); continue; }
        if (now-deadline >= period) {
            uint32_t skipped = (now-deadline)/period;
            gw_tx_round(&config, boot, sequence, now, deadline, 0x80000000U | skipped);
            sequence += skipped; deadline += (uint64_t)skipped*period;
        }
        csi_sensing_packet_t sensing = {.sequence=sequence, .tx_t1_us=esp_timer_get_time()};
        memcpy(sensing.profile_fingerprint, s_profile.fingerprint, CSI_PROFILE_FINGERPRINT_SIZE);
        uint8_t packet[GW_SENSING_SIZE];
        gw_schedule_t schedule; gw_tx_schedule(&schedule);
        size_t length = gw_sensing_encode(packet, &sensing, &config, boot, &schedule);
        uint32_t sent_mask = 0;
        for(unsigned k=0;k<s_profile.receiver_count;++k){
            unsigned i=(sequence+k)%s_profile.receiver_count;
            uint64_t sent_at=esp_timer_get_time();
            if(gw_omit_sensing(&config,&schedule,i,sensing.tx_t1_us,sent_at))continue;
            stats_add(&s_stats.attempts,1);
            if(gw_send(s_profile.receiver_macs[i],packet,length,1))sent_mask|=1U<<i;
            else stats_add(&s_stats.immediate_errors,1);
        }
        gw_tx_round(&config, boot, sequence, sensing.tx_t1_us, deadline, sent_mask);
        ++sequence; deadline += period;
    }
}

void app_main(void)
{
    csi_board_init();
    esp_err_t nvs_result = nvs_flash_init();
    if (nvs_result == ESP_ERR_NVS_NO_FREE_PAGES || nvs_result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_result = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_result);

    if (!parse_mac(CONFIG_CSI_SEND_MAC, s_transmitter_mac)) {
        ESP_LOGE(TAG, "invalid CONFIG_CSI_SEND_MAC: %s", CONFIG_CSI_SEND_MAC);
        abort();
    }
    csi_radio_profile_defaults(&s_profile, s_transmitter_mac);
    csi_radio_profile_t stored_profile;
    if (csi_radio_profile_load(&stored_profile) &&
        csi_radio_profile_validate(&stored_profile,
#if CONFIG_SOC_WIFI_SUPPORT_5G
                                   true
#else
                                   false
#endif
                                   )) {
        s_profile = stored_profile;
        s_profile_provisioned = true;
        memcpy(s_transmitter_mac, s_profile.transmitter_mac,
               sizeof(s_transmitter_mac));
    }

    usb_control_init();
    if (!s_profile_provisioned) {
        ESP_LOGW(TAG, "no valid NVS radio profile; USB provisioning is required");
        return;
    }

    wifi_init();
    /* Keep USB control available while the RF driver is stopped between runs. */
    ESP_ERROR_CHECK(esp_wifi_stop());
    if (xTaskCreate(transmitter_task, "csi_tx", 4096, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create transmitter task");
        abort();
    }
    if (xTaskCreate(transmitter_stats_task, "csi_tx_stats", 3072, NULL, 2, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create transmitter stats task");
        abort();
    }
}
