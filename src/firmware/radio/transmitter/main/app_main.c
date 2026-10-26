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
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_system.h"
#if CONFIG_CSI_ESPNOW_GATEWAY || CONFIG_CSI_USB_CONTROL
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#endif
#include "rom/ets_sys.h"

#include "csi_clock_protocol.h"
#include "radio_profile.h"

#if CONFIG_CSI_ESPNOW_GATEWAY || CONFIG_CSI_USB_CONTROL
#include "serial_frame.h"
#endif

#if !CONFIG_IDF_TARGET_ESP32C5 && !CONFIG_IDF_TARGET_ESP32C6
#error "The CSI transmitter firmware requires an ESP32-C5 or ESP32-C6 target"
#endif

#define CSI_BATCH_MAGIC "CSIB"
#define CSI_BATCH_VERSION 1
#define CSI_BATCH_HEADER_SIZE 60
#define CSI_WIRE_MAGIC "CSI1"
#define CSI_WIRE_VERSION_LEGACY 1
#define CSI_WIRE_VERSION_CLOCKED 3
#define CSI_WIRE_HEADER_SIZE_LEGACY 55
#define CSI_WIRE_HEADER_SIZE_CLOCKED 87
#define CSI_WIRE_RECEIVER_MAC_OFFSET 10
#define CSI_WIRE_PAYLOAD_LENGTH_OFFSET 8
#define CSI_WIRE_CSI_LENGTH_OFFSET 53
#define CSI_WIRE_MAX_CSI_BYTES 612
#define CSI_WIRE_FLAG_FIRST_WORD_INVALID 1
#define CSI_WIRE_FLAG_CLOCKS_VALID 2
#define CSI_GATEWAY_QUEUE_LENGTH 8

#if CONFIG_CSI_ESPNOW_GATEWAY
_Static_assert(CSI_SERIAL_MAX_PAYLOAD <= ESP_NOW_MAX_DATA_LEN_V2,
               "gateway payload must fit ESP-NOW v2");
#if !CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
#error "The CSI gateway requires the native USB Serial/JTAG interface"
#endif
#define CSI_USB_SERIAL_TX_BUFFER_SIZE (CSI_SERIAL_MAX_FRAME_SIZE * 4)
#define CSI_USB_SERIAL_RX_BUFFER_SIZE 256
#endif

static const char *TAG = "csi_tx";
static uint8_t s_transmitter_mac[6];
static csi_radio_profile_t s_profile;
static bool s_profile_provisioned;
static csi_radio_profile_t s_staged_profile;
static bool s_profile_staged;
static portMUX_TYPE s_stats_lock = portMUX_INITIALIZER_UNLOCKED;

#if CONFIG_CSI_ESPNOW_GATEWAY
static QueueHandle_t s_gateway_queue;
static uint32_t s_pending_sync_id;
static uint64_t s_pending_sync_t1_us;
static bool s_sync_request_pending;
#endif

typedef struct {
    uint32_t attempts;
    uint32_t immediate_errors;
    uint32_t asynchronous_successes;
    uint32_t asynchronous_failures;
} transmitter_stats_t;

static transmitter_stats_t s_stats;
static volatile bool s_tx_paused;

#if CONFIG_CSI_ESPNOW_GATEWAY
typedef struct {
    uint8_t frame_type;
    uint16_t length;
    uint8_t data[CSI_SERIAL_MAX_PAYLOAD];
} gateway_packet_t;

typedef struct {
    uint32_t received;
    uint32_t invalid;
    uint32_t queue_drops;
    uint32_t serial_frames;
    uint32_t serial_errors;
} gateway_stats_t;

static gateway_stats_t s_gateway_stats;
#endif

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

#if CONFIG_CSI_ESPNOW_GATEWAY
static void gateway_stats_add(uint32_t *counter, uint32_t amount)
{
    portENTER_CRITICAL(&s_stats_lock);
    *counter += amount;
    portEXIT_CRITICAL(&s_stats_lock);
}

static gateway_stats_t gateway_stats_snapshot(void)
{
    gateway_stats_t snapshot;
    portENTER_CRITICAL(&s_stats_lock);
    snapshot = s_gateway_stats;
    portEXIT_CRITICAL(&s_stats_lock);
    return snapshot;
}

static uint16_t read_u16(const uint8_t *source)
{
    return ((uint16_t)source[0] << 8) | source[1];
}

static bool gateway_packet_valid(const esp_now_recv_info_t *info,
                                 const uint8_t *data, int length)
{
    if (info == NULL || info->src_addr == NULL || data == NULL ||
        length < CSI_BATCH_HEADER_SIZE + 2 + CSI_WIRE_HEADER_SIZE_LEGACY ||
        length > CSI_SERIAL_MAX_PAYLOAD) {
        return false;
    }
    if (memcmp(data, CSI_BATCH_MAGIC, 4) != 0 ||
        data[4] != CSI_BATCH_VERSION ||
        data[5] != 0 ||
        read_u16(data + 6) != CSI_BATCH_HEADER_SIZE ||
        read_u16(data + 18) != 0) {
        return false;
    }
    const uint16_t record_count = read_u16(data + 16);
    if (record_count == 0 || record_count > 4) {
        return false;
    }

    size_t offset = CSI_BATCH_HEADER_SIZE;
    for (uint16_t index = 0; index < record_count; ++index) {
        if (offset + sizeof(uint16_t) > (size_t)length) {
            return false;
        }
        const uint16_t record_length = read_u16(data + offset);
        offset += sizeof(uint16_t);
        if (record_length < CSI_WIRE_HEADER_SIZE_LEGACY ||
            offset + record_length > (size_t)length ||
            memcmp(data + offset, CSI_WIRE_MAGIC, 4) != 0 ||
            (data[offset + 4] != CSI_WIRE_VERSION_LEGACY &&
             data[offset + 4] != CSI_WIRE_VERSION_CLOCKED)) {
            return false;
        }
        const bool clocked = data[offset + 4] == CSI_WIRE_VERSION_CLOCKED;
        const uint16_t header_size = clocked ? CSI_WIRE_HEADER_SIZE_CLOCKED :
                                               CSI_WIRE_HEADER_SIZE_LEGACY;
        const uint8_t allowed_flags = clocked ?
            CSI_WIRE_FLAG_FIRST_WORD_INVALID | CSI_WIRE_FLAG_CLOCKS_VALID :
            CSI_WIRE_FLAG_FIRST_WORD_INVALID;
        if ((data[offset + 5] & ~allowed_flags) != 0 ||
            read_u16(data + offset + 6) != header_size) {
            return false;
        }
        const uint16_t payload_length =
            read_u16(data + offset + CSI_WIRE_PAYLOAD_LENGTH_OFFSET);
        const uint16_t csi_length =
            read_u16(data + offset + CSI_WIRE_CSI_LENGTH_OFFSET);
        if (payload_length == 0 || payload_length > CSI_WIRE_MAX_CSI_BYTES ||
            (payload_length & 1U) != 0 || payload_length != csi_length ||
            record_length != header_size + payload_length ||
            memcmp(data + offset + CSI_WIRE_RECEIVER_MAC_OFFSET,
                   info->src_addr, ESP_NOW_ETH_ALEN) != 0) {
            return false;
        }
        offset += record_length;
    }
    return offset == (size_t)length;
}

static bool gateway_queue_frame(uint8_t frame_type, const uint8_t *data,
                                size_t length)
{
    if (data == NULL || length > CSI_SERIAL_MAX_PAYLOAD) {
        return false;
    }
    // ESP-NOW callbacks run serially in the Wi-Fi task. Static storage avoids
    // putting the 1,400-byte gateway packet on that task's small stack.
    static gateway_packet_t packet;
    packet.frame_type = frame_type;
    packet.length = (uint16_t)length;
    memcpy(packet.data, data, length);
    if (xQueueSend(s_gateway_queue, &packet, 0) != pdTRUE) {
        gateway_stats_add(&s_gateway_stats.queue_drops, 1);
        return false;
    }
    return true;
}

static void espnow_receive_callback(const esp_now_recv_info_t *info,
                                    const uint8_t *data, int length)
{
    const uint64_t tx_t4_us = (uint64_t)esp_timer_get_time();
    if (gateway_packet_valid(info, data, length)) {
        gateway_stats_add(&s_gateway_stats.received, 1);
        gateway_queue_frame(CSI_SERIAL_TYPE_PACKET, data, (size_t)length);
        return;
    }

    csi_sync_response_t response;
    if (info == NULL || info->rx_ctrl == NULL ||
        !csi_sync_response_decode(data, (size_t)length, &response) ||
        tx_t4_us < response.tx_t1_us) {
        gateway_stats_add(&s_gateway_stats.invalid, 1);
        return;
    }
    portENTER_CRITICAL(&s_stats_lock);
    const bool matches_request = s_sync_request_pending &&
        response.sync_id == s_pending_sync_id &&
        response.tx_t1_us == s_pending_sync_t1_us;
    if (matches_request) {
        s_sync_request_pending = false;
    }
    portEXIT_CRITICAL(&s_stats_lock);
    if (!matches_request) {
        gateway_stats_add(&s_gateway_stats.invalid, 1);
        return;
    }

    csi_clock_sample_t sample = {
        .sync_id = response.sync_id,
        .sensing_sequence = response.sensing_sequence,
        .receiver_boot_id = response.receiver_boot_id,
        .tx_t1_us = response.tx_t1_us,
        .rx_t2_us = response.rx_t2_us,
        .rx_t3_us = response.rx_t3_us,
        .tx_t4_us = tx_t4_us,
        .rx_radio_t2_us = response.rx_radio_t2_us,
        .tx_radio_t4_us = info->rx_ctrl->timestamp,
    };
    memcpy(sample.receiver_mac, info->src_addr, sizeof(sample.receiver_mac));
    uint8_t encoded[CSI_CLOCK_SAMPLE_SIZE];
    const size_t encoded_length = csi_clock_sample_encode(
        encoded, sizeof(encoded), &sample);
    if (encoded_length == 0 ||
        !gateway_queue_frame(CSI_SERIAL_TYPE_CLOCK_SYNC,
                             encoded, encoded_length)) {
        gateway_stats_add(&s_gateway_stats.invalid, 1);
    }
}

static bool serial_write_frame(uint8_t type, const uint8_t *payload,
                               size_t payload_length, uint8_t *raw,
                               size_t raw_capacity, uint8_t *frame,
                               size_t frame_capacity)
{
    const size_t frame_length = csi_serial_encode_frame(
        type, payload, payload_length, raw, raw_capacity, frame, frame_capacity);
    if (frame_length == 0) {
        return false;
    }
    return usb_serial_jtag_write_bytes(
               frame, frame_length, portMAX_DELAY) == (int)frame_length;
}

static void gateway_serial_init(void)
{
    if (usb_serial_jtag_is_driver_installed()) {
        ESP_LOGE(TAG, "USB Serial/JTAG driver was installed before gateway setup");
        abort();
    }
    usb_serial_jtag_driver_config_t config = {
        .tx_buffer_size = CSI_USB_SERIAL_TX_BUFFER_SIZE,
        .rx_buffer_size = CSI_USB_SERIAL_RX_BUFFER_SIZE,
    };
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&config));
    usb_serial_jtag_vfs_use_driver();
}

static void gateway_serial_task(void *arg)
{
    (void)arg;
    gateway_packet_t packet;
    uint8_t *raw = malloc(CSI_SERIAL_MAX_RAW_SIZE);
    uint8_t *frame = malloc(CSI_SERIAL_MAX_FRAME_SIZE);
    if (raw == NULL || frame == NULL) {
        free(raw);
        free(frame);
        gateway_stats_add(&s_gateway_stats.serial_errors, 1);
        vTaskDelete(NULL);
        return;
    }

    while (xQueueReceive(s_gateway_queue, &packet, portMAX_DELAY) == pdTRUE) {
        if (!serial_write_frame(packet.frame_type, packet.data,
                                packet.length, raw, CSI_SERIAL_MAX_RAW_SIZE,
                                frame, CSI_SERIAL_MAX_FRAME_SIZE)) {
            gateway_stats_add(&s_gateway_stats.serial_errors, 1);
            continue;
        }
        gateway_stats_add(&s_gateway_stats.serial_frames, 1);
    }

    free(raw);
    free(frame);
    vTaskDelete(NULL);
}
#endif

static void espnow_send_callback(const esp_now_send_info_t *tx_info,
                                 esp_now_send_status_t status)
{
    (void)tx_info;
    if (status == ESP_NOW_SEND_SUCCESS) {
        stats_add(&s_stats.asynchronous_successes, 1);
    } else {
        stats_add(&s_stats.asynchronous_failures, 1);
    }
}

static void transmitter_stats_task(void *arg)
{
    (void)arg;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        const transmitter_stats_t stats = stats_snapshot();
#if CONFIG_CSI_ESPNOW_GATEWAY
        const gateway_stats_t gateway = gateway_stats_snapshot();
        char line[192];
        uint8_t raw[256];
        uint8_t frame[260];
        int written = snprintf(
            line, sizeof(line),
            "CSI_TX_STATS,%" PRIu64 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
            ",%" PRIu32,
            (uint64_t)(esp_timer_get_time() / 1000),
            stats.attempts,
            stats.immediate_errors,
            stats.asynchronous_successes,
            stats.asynchronous_failures);
        if (written <= 0 || (size_t)written >= sizeof(line) ||
            !serial_write_frame(CSI_SERIAL_TYPE_TRANSMITTER_STATS,
                                (const uint8_t *)line, (size_t)written,
                                raw, sizeof(raw), frame, sizeof(frame))) {
            gateway_stats_add(&s_gateway_stats.serial_errors, 1);
        }

        written = snprintf(
            line, sizeof(line),
            "CSI_GATEWAY_STATS,%" PRIu64 ",%" PRIu32 ",%" PRIu32
            ",%" PRIu32 ",%" PRIu32 ",%" PRIu32,
            (uint64_t)(esp_timer_get_time() / 1000),
            gateway.received,
            gateway.invalid,
            gateway.queue_drops,
            gateway.serial_frames,
            gateway.serial_errors);
        if (written <= 0 || (size_t)written >= sizeof(line) ||
            !serial_write_frame(CSI_SERIAL_TYPE_GATEWAY_STATS,
                                (const uint8_t *)line, (size_t)written,
                                raw, sizeof(raw), frame, sizeof(frame))) {
            gateway_stats_add(&s_gateway_stats.serial_errors, 1);
        }
#else
        ets_printf(
            "CSI_TX_STATS,%" PRIu64 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
            ",%" PRIu32 "\n",
            (uint64_t)(esp_timer_get_time() / 1000),
            stats.attempts,
            stats.immediate_errors,
            stats.asynchronous_successes,
            stats.asynchronous_failures);
#endif
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

#if CONFIG_CSI_USB_CONTROL
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

static void usb_control_write(uint8_t type, const uint8_t *payload, size_t length)
{
    /* Only the USB control task calls this function.  Keeping the framing
     * workspace in static storage avoids nesting almost 3 KiB of buffers on
     * that task's 4 KiB stack while it is handling a discovery request. */
    static uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE];
    static uint8_t frame[CSI_SERIAL_MAX_FRAME_SIZE];
    const size_t frame_length = csi_serial_encode_frame(
        type, payload, length, raw, sizeof(raw), frame, sizeof(frame));
    if (frame_length != 0) usb_serial_jtag_write_bytes(frame, frame_length, portMAX_DELAY);
}

static void usb_status(void)
{
    /* usb_status() is called only by the USB control task. */
    static char payload[512];
    const char *target =
#if CONFIG_IDF_TARGET_ESP32C5
        "esp32c5";
#else
        "esp32c6";
#endif
    const transmitter_stats_t tx_stats = stats_snapshot();
    const int length = snprintf(
        payload, sizeof(payload),
        "{\"role\":\"transmitter\",\"target\":\"%s\","
        "\"mac\":\"" MACSTR "\",\"firmware_version\":\"2\","
        "\"protocol_version\":2,\"profile_id\":\"%s\","
        "\"profile_fingerprint\":\"%s\",\"ready\":%s,"
        "\"tx\":{\"attempts\":%lu,\"imm_err\":%lu,\"ok\":%lu,\"fail\":%lu}}",
        target, MAC2STR(s_transmitter_mac), s_profile.profile_id,
        s_profile.fingerprint, s_profile_provisioned ? "true" : "false",
        (unsigned long)tx_stats.attempts,
        (unsigned long)tx_stats.immediate_errors,
        (unsigned long)tx_stats.asynchronous_successes,
        (unsigned long)tx_stats.asynchronous_failures);
    if (length > 0 && (size_t)length < sizeof(payload))
        usb_control_write(CSI_SERIAL_TYPE_DEVICE_STATUS, (const uint8_t *)payload, (size_t)length);
}

static void espnow_init(void);

/* Apply a committed profile without rebooting: park the sensing loop, bounce
 * WiFi into the new band/channel, rebuild the unicast peers, resume. */
static void apply_staged_profile(void)
{
    s_tx_paused = true;
    vTaskDelay(pdMS_TO_TICKS(30));
    esp_now_deinit();
    ESP_ERROR_CHECK(esp_wifi_stop());
    s_profile = s_staged_profile;
    s_profile_provisioned = true;
    memcpy(s_transmitter_mac, s_profile.transmitter_mac,
           sizeof(s_transmitter_mac));
    ESP_ERROR_CHECK(esp_wifi_set_mac(WIFI_IF_STA, s_transmitter_mac));
    ESP_ERROR_CHECK(esp_wifi_start());
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
    espnow_init();
    s_tx_paused = false;
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
#endif

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
}

static void espnow_init(void)
{
    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_set_pmk((uint8_t *)"pmk1234567890123"));
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_send_callback));
#if CONFIG_CSI_ESPNOW_GATEWAY
    uint32_t espnow_version = 0;
    ESP_ERROR_CHECK(esp_now_get_version(&espnow_version));
    if (espnow_version < 2) {
        ESP_LOGE(TAG, "ESP-NOW v2 is required for the CSI gateway; got v%" PRIu32,
                 espnow_version);
        abort();
    }
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_receive_callback));
#endif

    // Unicast peers are what makes the configured HE20/MCS0 rate take effect.
    // A broadcast peer is always sent at a basic legacy rate, which produces
    // no HE CSI at the receiver.
    esp_now_rate_config_t rate = {
        .phymode = WIFI_PHY_MODE_HE20,
        .rate = WIFI_PHY_RATE_MCS0_LGI,
        .ersu = false,
        .dcm = false,
    };
    for (uint8_t index = 0; index < s_profile.receiver_count; ++index) {
        esp_now_peer_info_t peer = {0};
        memcpy(peer.peer_addr, s_profile.receiver_macs[index],
               sizeof(peer.peer_addr));
        peer.channel = s_profile.channel;
        peer.ifidx = WIFI_IF_STA;
        peer.encrypt = false;
        ESP_ERROR_CHECK(esp_now_add_peer(&peer));
        ESP_ERROR_CHECK(esp_now_set_peer_rate_config(peer.peer_addr, &rate));
    }
    ESP_LOGI(TAG, "sensing link PHY=HE20 MCS0 long-GI peers=%u",
             s_profile.receiver_count);
#if CONFIG_CSI_ESPNOW_GATEWAY
    ESP_LOGI(TAG, "CSI gateway enabled with ESP-NOW v%" PRIu32,
             espnow_version);
#endif
}

static void transmitter_task(void *arg)
{
    (void)arg;
    uint32_t sequence = 0;
#if CONFIG_CSI_ESPNOW_GATEWAY
    uint32_t sync_id = 0;
    int64_t next_sync_us = esp_timer_get_time();
#endif
    const int64_t period_us = 1000000LL / s_profile.nominal_rate_hz;
    int64_t next_deadline = esp_timer_get_time();

    ESP_LOGI(TAG, "channel=%d rate=%d Hz mac=" MACSTR,
             s_profile.channel, s_profile.nominal_rate_hz, MAC2STR(s_transmitter_mac));

    while (true) {
        if (s_tx_paused) {
            // A live profile change is bouncing WiFi; do not send into it.
            next_deadline = esp_timer_get_time();
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        const uint32_t packet_sequence = sequence++;
        const int64_t tx_time_us = esp_timer_get_time();
        bool request_sync = false;
        uint32_t packet_sync_id = CSI_SYNC_ID_NONE;
#if CONFIG_CSI_ESPNOW_GATEWAY
        if (tx_time_us >= next_sync_us) {
            request_sync = true;
            packet_sync_id = sync_id++;
            next_sync_us = tx_time_us +
                (int64_t)CONFIG_CSI_CLOCK_SYNC_INTERVAL_MS * 1000;
        }
#endif
        csi_sensing_packet_t sensing = {
            .sequence = packet_sequence,
            .sync_id = packet_sync_id,
            .tx_t1_us = (uint64_t)tx_time_us,
            .sync_requested = request_sync,
        };
        memcpy(sensing.profile_fingerprint, s_profile.fingerprint,
               CSI_PROFILE_FINGERPRINT_SIZE);
        uint8_t packet[CSI_SENSING_HEADER_SIZE];
        const size_t packet_length = csi_sensing_encode(
            packet, sizeof(packet), &sensing);
        if (packet_length == 0) {
            stats_add(&s_stats.immediate_errors, 1);
            continue;
        }
#if CONFIG_CSI_ESPNOW_GATEWAY
        if (request_sync) {
            portENTER_CRITICAL(&s_stats_lock);
            s_pending_sync_id = packet_sync_id;
            s_pending_sync_t1_us = (uint64_t)tx_time_us;
            s_sync_request_pending = true;
            portEXIT_CRITICAL(&s_stats_lock);
        }
#endif
        for (uint8_t peer_index = 0; peer_index < s_profile.receiver_count;
             ++peer_index) {
            stats_add(&s_stats.attempts, 1);
            const esp_err_t result = esp_now_send(
                s_profile.receiver_macs[peer_index], packet, packet_length);
            if (result != ESP_OK) {
#if CONFIG_CSI_ESPNOW_GATEWAY
                if (request_sync) {
                    portENTER_CRITICAL(&s_stats_lock);
                    if (s_sync_request_pending &&
                        s_pending_sync_id == packet_sync_id) {
                        s_sync_request_pending = false;
                    }
                    portEXIT_CRITICAL(&s_stats_lock);
                }
#endif
                stats_add(&s_stats.immediate_errors, 1);
                ESP_LOGW(TAG, "sequence=%" PRIu32 " peer=%u send failed: %s",
                         packet_sequence, peer_index, esp_err_to_name(result));
            }
        }
        next_deadline += period_us;
        const int64_t remaining_us = next_deadline - esp_timer_get_time();
        if (remaining_us > 0) {
            vTaskDelay(pdMS_TO_TICKS((remaining_us + 999) / 1000));
        } else {
            taskYIELD();
        }
    }
}

void app_main(void)
{
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

#if CONFIG_CSI_USB_CONTROL
    usb_control_init();
#endif
    if (!s_profile_provisioned) {
        ESP_LOGW(TAG, "no valid NVS radio profile; USB provisioning is required");
        return;
    }

#if CONFIG_CSI_ESPNOW_GATEWAY
    s_gateway_queue = xQueueCreate(CSI_GATEWAY_QUEUE_LENGTH,
                                   sizeof(gateway_packet_t));
    if (s_gateway_queue == NULL) {
        ESP_LOGE(TAG, "unable to allocate CSI gateway queue");
        abort();
    }
    gateway_serial_init();
#endif

    wifi_init();
    espnow_init();
#if CONFIG_CSI_ESPNOW_GATEWAY
    ESP_LOGI(TAG, "native USB Serial/JTAG gateway ready");
    // Native USB now carries only framed gateway traffic. Suppressing later
    // logs prevents console text from being inserted into a binary frame.
    esp_log_level_set("*", ESP_LOG_NONE);
    if (xTaskCreate(gateway_serial_task, "csi_gateway", 8192, NULL, 3, NULL) != pdPASS) {
        abort();
    }
#endif
    if (xTaskCreate(transmitter_task, "csi_tx", 4096, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create transmitter task");
        abort();
    }
    if (xTaskCreate(transmitter_stats_task, "csi_tx_stats", 3072, NULL, 2, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create transmitter stats task");
        abort();
    }
}
