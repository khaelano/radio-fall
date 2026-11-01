#include <inttypes.h>
#include <ctype.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "nvs_flash.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_system.h"
#include "esp_mac.h"

#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "serial_frame.h"

#include "csi_clock_protocol.h"
#include "radio_profile.h"
#include "radio_board.h"
#include "radio_diagnostics.h"
#include "ble_transport.h"

#if !CONFIG_IDF_TARGET_ESP32C5 && !CONFIG_IDF_TARGET_ESP32C6
#error "The CSI receiver firmware requires an ESP32-C5 or ESP32-C6 target"
#endif

#define MAX_CSI_BYTES 612
#define CSI_WIRE_MAGIC "CSI1"
#define CSI_WIRE_VERSION 3
#define CSI_WIRE_HEADER_SIZE 87
#define CSI_WIRE_FLAG_FIRST_WORD_INVALID BIT0
#define CSI_WIRE_FLAG_CLOCKS_VALID BIT1

static const char *TAG = "csi_rx";
static uint8_t s_transmitter_mac[6];
static uint8_t s_receiver_mac[6];
static csi_radio_profile_t s_profile;
static bool s_profile_provisioned;
static csi_radio_profile_t s_staged_profile;
static bool s_profile_staged;
static SemaphoreHandle_t s_usb_write_mutex;
static volatile uint32_t s_transport_sequence;
static uint32_t s_boot_id;
static portMUX_TYPE s_stats_lock = portMUX_INITIALIZER_UNLOCKED;

static const char *s_output_mode = "ble";

/* Per-callback rejection counters.  These exist so the host can see why CSI
 * callbacks do not become records, instead of silently getting zero packets. */
typedef struct {
    uint32_t callbacks;
    uint32_t null_info;
    uint32_t foreign_mac;
    uint32_t short_payload;
    uint32_t decode_fail;
    uint32_t fingerprint_mismatch;
    uint32_t empty_csi;
    uint32_t duplicate_frames;
    uint32_t queued;
    uint32_t queue_drops;
    uint32_t espnow_sensing;
    uint32_t matching_mac;
    uint32_t last_channel;
    uint32_t last_format;
    uint32_t last_payload_len;
} csi_diag_t;

static csi_diag_t s_csi_diag;

typedef struct {
    uint32_t transport_sequence;
    uint32_t sequence;
    int8_t rssi;
    int8_t noise_floor;
    uint8_t rate;
    uint8_t sig_mode;
    uint8_t mcs;
    uint8_t bandwidth;
    uint8_t smoothing;
    uint8_t not_sounding;
    uint8_t aggregation;
    uint8_t stbc;
    uint8_t fec_coding;
    uint8_t sgi;
    uint8_t ampdu_count;
    uint8_t channel;
    uint8_t secondary_channel;
    uint32_t timestamp;
    uint64_t tx_timestamp_us;
    uint64_t rx_callback_timestamp_us;
    bool clock_timestamps_valid;
    uint8_t antenna;
    uint16_t sig_len;
    uint8_t rx_state;
    uint16_t csi_len;
    bool first_word_invalid;
    int8_t csi[MAX_CSI_BYTES];
} csi_record_t;

static void stats_add(uint32_t *counter, uint32_t amount)
{
    portENTER_CRITICAL(&s_stats_lock);
    *counter += amount;
    portEXIT_CRITICAL(&s_stats_lock);
}

static void usb_serial_init(void)
{
    if (s_usb_write_mutex == NULL) {
        s_usb_write_mutex = xSemaphoreCreateMutex();
        if (s_usb_write_mutex == NULL) {
            ESP_LOGE(TAG, "unable to allocate USB write mutex");
            abort();
        }
    }
    if (usb_serial_jtag_is_driver_installed()) {
        return;
    }
    usb_serial_jtag_driver_config_t config = {
        .tx_buffer_size = CSI_SERIAL_MAX_FRAME_SIZE * 4,
        .rx_buffer_size = 512,
    };
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&config));
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

static void usb_control_write(uint8_t type, const uint8_t *payload, size_t length)
{
    /* Only the USB control task calls this function.  Keeping the framing
     * workspace in static storage avoids nesting almost 3 KiB of buffers on
     * that task's 4 KiB stack while it is handling a discovery request. */
    static uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE];
    static uint8_t frame[CSI_SERIAL_MAX_FRAME_SIZE];
    const size_t frame_length = csi_serial_encode_frame(
        type, payload, length, raw, sizeof(raw), frame, sizeof(frame));
    if (frame_length != 0) {
        if (s_usb_write_mutex != NULL) {
            xSemaphoreTake(s_usb_write_mutex, portMAX_DELAY);
        }
        usb_serial_jtag_write_bytes(frame, frame_length, pdMS_TO_TICKS(20));
        if (s_usb_write_mutex != NULL) {
            xSemaphoreGive(s_usb_write_mutex);
        }
    }
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
    const int length = snprintf(
        payload, sizeof(payload),
        "{\"role\":\"receiver\",\"target\":\"%s\","
        "\"mac\":\"" MACSTR "\",\"firmware_version\":\"2\","
        "\"protocol_version\":2,\"profile_id\":\"%s\","
        "\"profile_fingerprint\":\"%s\",\"ready\":%s,"
        "\"csi_transport\":\"ble\",\"reset_reason\":\"%s\","
        "\"uptime_ms\":%" PRIu64 ","
        "\"board\":\"%s\",\"antenna\":\"%s\","
        "\"sensing_version\":3,"
        "\"csi\":{\"cb\":%lu,\"null\":%lu,\"mac\":%lu,\"short\":%lu,"
        "\"decode\":%lu,\"fp\":%lu,\"empty\":%lu,\"queued\":%lu,"
        "\"espnow_sensing\":%lu,\"matching_mac\":%lu,\"channel\":%lu,"
        "\"format\":%lu,\"payload_len\":%lu}}",
        target, MAC2STR(s_receiver_mac), s_profile.profile_id,
        s_profile.fingerprint, s_profile_provisioned ? "true" : "false",
        csi_reset_reason_name(), (uint64_t)(esp_timer_get_time() / 1000),
        csi_board_name(), csi_board_antenna(),
        (unsigned long)s_csi_diag.callbacks,
        (unsigned long)s_csi_diag.null_info,
        (unsigned long)s_csi_diag.foreign_mac,
        (unsigned long)s_csi_diag.short_payload,
        (unsigned long)s_csi_diag.decode_fail,
        (unsigned long)s_csi_diag.fingerprint_mismatch,
        (unsigned long)s_csi_diag.empty_csi,
        (unsigned long)s_csi_diag.queued,
        (unsigned long)s_csi_diag.espnow_sensing,
        (unsigned long)s_csi_diag.matching_mac,
        (unsigned long)s_csi_diag.last_channel,
        (unsigned long)s_csi_diag.last_format,
        (unsigned long)s_csi_diag.last_payload_len);
    if (length > 0 && (size_t)length < sizeof(payload)) {
        usb_control_write(CSI_SERIAL_TYPE_DEVICE_STATUS,
                          (const uint8_t *)payload, (size_t)length);
    }
}

static void wifi_csi_init(void);

/* Apply a committed profile without rebooting: the USB control task stays
 * alive, WiFi is bounced into the new band/channel, and CSI is re-armed. */
static void apply_staged_profile(void)
{
    /* Reload the BLE identity and fixed slot order after acknowledging NVS. */
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
        const int read = usb_serial_jtag_read_bytes(&byte, 1, pdMS_TO_TICKS(100));
        if (read != 1) continue;
        if (byte != 0) {
            if (used < sizeof(encoded)) encoded[used++] = byte;
            else used = 0;
            continue;
        }
        if (used == 0) continue;
        const size_t raw_length = usb_decode_cobs(encoded, used, raw, sizeof(raw));
        used = 0;
        if (raw_length < CSI_SERIAL_HEADER_SIZE + CSI_SERIAL_CRC_SIZE ||
            memcmp(raw, CSI_SERIAL_MAGIC, 4) != 0 ||
            raw[4] != CSI_SERIAL_VERSION) continue;
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
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_STAGE_ACK,
                                  (const uint8_t *)"ok", 2);
            } else {
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_STAGE_ACK,
                                  (const uint8_t *)"error", 5);
            }
        } else if (raw[5] == CSI_SERIAL_TYPE_PROFILE_COMMIT) {
            if (s_profile_staged && csi_radio_profile_save(&s_staged_profile)) {
                s_profile_staged = false;
                apply_staged_profile();
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK,
                                  (const uint8_t *)"ok", 2);
            } else {
                usb_control_write(CSI_SERIAL_TYPE_PROFILE_COMMIT_ACK,
                                  (const uint8_t *)"error", 5);
            }
        }
    }
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_config));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

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
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, s_receiver_mac));

}

static void sensing_received(const esp_now_recv_info_t *info, const uint8_t *data, int length)
{
    csi_sensing_packet_t sensing;
    if (info && data && length > 0 && !memcmp(info->src_addr, s_transmitter_mac, 6)
        && csi_sensing_decode(data, (size_t)length, &sensing)
        && !memcmp(sensing.profile_fingerprint, s_profile.fingerprint, CSI_PROFILE_FINGERPRINT_SIZE)) {
        stats_add(&s_csi_diag.espnow_sensing, 1);
    }
}

static void espnow_init(void)
{
    static const uint8_t broadcast_mac[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_set_pmk((uint8_t *)"pmk1234567890123"));
    ESP_ERROR_CHECK(esp_now_register_recv_cb(sensing_received));

    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, broadcast_mac, sizeof(broadcast_mac));
    peer.channel = s_profile.channel;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

}

static size_t serialize_csi_record(const csi_record_t *record, uint8_t *buffer, size_t capacity);

static bool copy_rx_metadata(csi_record_t *record,
                             const wifi_pkt_rx_ctrl_t *rx_ctrl)
{
    if (record == NULL || rx_ctrl == NULL) {
        return false;
    }

    record->rssi = rx_ctrl->rssi;
    record->noise_floor = rx_ctrl->noise_floor;
    record->rate = rx_ctrl->rate;
    record->sig_mode = rx_ctrl->cur_bb_format;
    // The sensing peer is fixed to HE20 MCS0, non-DCM, non-STBC, long GI.
    // ESP32-C6 does not expose the classic ESP32 per-packet fields represented
    // by the remaining CSI1 columns, so their zero-initialized values are the
    // stable compatibility representation.
    record->mcs = 0;
    record->bandwidth = 0;
    record->channel = rx_ctrl->channel;
    record->secondary_channel = rx_ctrl->second;
    record->timestamp = rx_ctrl->timestamp;
    record->sig_len = rx_ctrl->sig_len;
    record->rx_state = rx_ctrl->rx_state;
    return true;
}

static void wifi_csi_callback(void *ctx, wifi_csi_info_t *info)
{
    (void)ctx;
    const uint64_t rx_callback_timestamp_us = (uint64_t)esp_timer_get_time();
    stats_add(&s_csi_diag.callbacks, 1);
    if (info == NULL || info->buf == NULL || info->len == 0) {
        stats_add(&s_csi_diag.null_info, 1);
        return;
    }

    csi_record_t record = {0};
    s_csi_diag.last_channel = info->rx_ctrl.channel;
    s_csi_diag.last_format = info->rx_ctrl.cur_bb_format;
    s_csi_diag.last_payload_len = info->payload_len;
    csi_sensing_packet_t sensing;
    bool decoded = false;

    if (memcmp(info->mac, s_transmitter_mac, sizeof(s_transmitter_mac)) != 0) {
        /* Keep counting foreign frames, but do not throw the CSI away: the
         * sensing frame may arrive with a different source address than the
         * configured transmitter MAC. */
        stats_add(&s_csi_diag.foreign_mac, 1);
    } else {
        stats_add(&s_csi_diag.matching_mac, 1);
    }

    /* Snapshot callback metadata once: hardware may reuse the backing buffer. */
    uint8_t sensing_bytes[CSI_BLE_SENSING_SIZE];
    if (info->payload == NULL ||
        info->payload_len < CSI_SENSING_PAYLOAD_OFFSET + sizeof(sensing_bytes)) {
        stats_add(&s_csi_diag.short_payload, 1);
        return;
    }
    memcpy(sensing_bytes, info->payload + CSI_SENSING_PAYLOAD_OFFSET, sizeof(sensing_bytes));
    decoded = csi_sensing_decode(sensing_bytes, sizeof(sensing_bytes), &sensing);
    if (!decoded) { stats_add(&s_csi_diag.decode_fail, 1); return; }
    if (memcmp(sensing.profile_fingerprint, s_profile.fingerprint, CSI_PROFILE_FINGERPRINT_SIZE)) {
        stats_add(&s_csi_diag.fingerprint_mismatch, 1); return;
    }
    if (memcmp(info->mac, s_transmitter_mac, 6) ||
        !csi_ble_observe(sensing_bytes, sizeof(sensing_bytes), rx_callback_timestamp_us)) return;
    record.sequence = sensing.sequence;
    record.tx_timestamp_us = sensing.tx_t1_us;
    record.clock_timestamps_valid = true;
    record.rx_callback_timestamp_us = rx_callback_timestamp_us;
    copy_rx_metadata(&record, &info->rx_ctrl);

    record.csi_len = info->len > MAX_CSI_BYTES ? MAX_CSI_BYTES : info->len;
    // CSI is serialized as imaginary/real pairs. Drop a dangling byte (or an
    // empty callback) instead of emitting a row the host cannot interpret.
    record.csi_len &= (uint16_t)~1U;
    if (record.csi_len == 0) {
        stats_add(&s_csi_diag.empty_csi, 1);
        return;
    }
    record.transport_sequence = s_transport_sequence++;
    record.first_word_invalid = info->first_word_invalid;
    memcpy(record.csi, info->buf, record.csi_len);

    uint8_t wire[CSI_WIRE_HEADER_SIZE + MAX_CSI_BYTES];
    size_t length = serialize_csi_record(&record, wire, sizeof(wire));
    if (!length || !csi_ble_enqueue(wire, length, rx_callback_timestamp_us))
        stats_add(&s_csi_diag.queue_drops, 1);
    else stats_add(&s_csi_diag.queued, 1);
}

static void wifi_csi_init(void)
{
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    /* ESP-NOW broadcast frames are sent at a basic legacy rate, so HE-SU-only
     * acquisition never fires a callback for them.  Enable legacy and HT20 as
     * well; the record carries the PPDU format so the host can tell them apart. */
    wifi_promiscuous_filter_t filter = {
        .filter_mask = WIFI_PROMIS_FILTER_MASK_ALL,
    };
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous_filter(&filter));

    wifi_csi_config_t csi_config = {
        .enable = true,
        .acquire_csi_legacy = true,
        .acquire_csi_ht20 = true,
        .acquire_csi_ht40 = false,
        .acquire_csi_su = true,
        .acquire_csi_mu = false,
        .acquire_csi_dcm = false,
        .acquire_csi_beamformed = false,
        // ESP32-C5 (Wi-Fi MAC v3) renamed this field; C6 retains the v2 name.
#if CONFIG_SOC_WIFI_MAC_VERSION_NUM == 3
        .acquire_csi_he_stbc_mode = ESP_CSI_ACQUIRE_STBC_HELTF1,
#else
        .acquire_csi_he_stbc = ESP_CSI_ACQUIRE_STBC_HELTF1,
#endif
        .val_scale_cfg = 0,
        .dump_ack_en = false,
        .reserved = 0,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_callback, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

static void write_u16(uint8_t *destination, uint16_t value)
{
    destination[0] = (uint8_t)(value >> 8);
    destination[1] = (uint8_t)value;
}

static void write_u32(uint8_t *destination, uint32_t value)
{
    destination[0] = (uint8_t)(value >> 24);
    destination[1] = (uint8_t)(value >> 16);
    destination[2] = (uint8_t)(value >> 8);
    destination[3] = (uint8_t)value;
}

static size_t serialize_csi_record(const csi_record_t *record, uint8_t *buffer,
                                   size_t capacity)
{
    if (record == NULL || buffer == NULL || record->csi_len > MAX_CSI_BYTES ||
        capacity < CSI_WIRE_HEADER_SIZE + record->csi_len) {
        return 0;
    }

    size_t offset = 0;
    memcpy(buffer + offset, CSI_WIRE_MAGIC, 4);
    offset += 4;
    buffer[offset++] = CSI_WIRE_VERSION;
    buffer[offset++] =
        (record->first_word_invalid ? CSI_WIRE_FLAG_FIRST_WORD_INVALID : 0) |
        (record->clock_timestamps_valid ? CSI_WIRE_FLAG_CLOCKS_VALID : 0);
    write_u16(buffer + offset, CSI_WIRE_HEADER_SIZE);
    offset += 2;
    write_u16(buffer + offset, record->csi_len);
    offset += 2;
    memcpy(buffer + offset, s_receiver_mac, sizeof(s_receiver_mac));
    offset += sizeof(s_receiver_mac);
    memcpy(buffer + offset, s_transmitter_mac, sizeof(s_transmitter_mac));
    offset += sizeof(s_transmitter_mac);
    write_u32(buffer + offset, record->transport_sequence);
    offset += 4;
    write_u32(buffer + offset, record->sequence);
    offset += 4;
    write_u32(buffer + offset, record->timestamp);
    offset += 4;
    buffer[offset++] = (uint8_t)record->rssi;
    buffer[offset++] = (uint8_t)record->noise_floor;
    buffer[offset++] = record->rate;
    buffer[offset++] = record->sig_mode;
    buffer[offset++] = record->mcs;
    buffer[offset++] = record->bandwidth;
    buffer[offset++] = record->smoothing;
    buffer[offset++] = record->not_sounding;
    buffer[offset++] = record->aggregation;
    buffer[offset++] = record->stbc;
    buffer[offset++] = record->fec_coding;
    buffer[offset++] = record->sgi;
    buffer[offset++] = record->ampdu_count;
    buffer[offset++] = record->channel;
    buffer[offset++] = record->secondary_channel;
    buffer[offset++] = record->antenna;
    buffer[offset++] = record->rx_state;
    write_u16(buffer + offset, record->sig_len);
    offset += 2;
    write_u16(buffer + offset, record->csi_len);
    offset += 2;
    csi_clock_write_u64(buffer + offset, record->tx_timestamp_us);
    offset += 8;
    csi_clock_write_u64(buffer + offset, record->rx_callback_timestamp_us);
    offset += 8;
    memcpy(buffer + offset, s_profile.fingerprint,
           CSI_PROFILE_FINGERPRINT_SIZE);
    offset += CSI_PROFILE_FINGERPRINT_SIZE;
    memcpy(buffer + offset, record->csi, record->csi_len);
    offset += record->csi_len;
    return offset;
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
    s_boot_id = esp_random();

    usb_serial_init();

    if (!parse_mac(CONFIG_CSI_SEND_MAC, s_transmitter_mac)) {
        ESP_LOGE(TAG, "invalid CONFIG_CSI_SEND_MAC: %s", CONFIG_CSI_SEND_MAC);
        abort();
    }
    ESP_ERROR_CHECK(esp_read_mac(s_receiver_mac, ESP_MAC_WIFI_STA));
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

    if (xTaskCreate(usb_control_task, "csi_usb_ctl", 4096, NULL, 6, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create USB control task");
        abort();
    }
    if (!s_profile_provisioned) {
        ESP_LOGW(TAG, "no valid NVS radio profile; USB provisioning is required");
        return;
    }

    wifi_init();
    espnow_init();
    csi_ble_init(&s_profile, s_receiver_mac, s_boot_id);
    wifi_csi_init();
    ESP_LOGI(TAG, "mode=%s channel=%d transmitter=" MACSTR " receiver=" MACSTR
             " boot=%" PRIu32,
             s_output_mode, s_profile.channel, MAC2STR(s_transmitter_mac),
             MAC2STR(s_receiver_mac), s_boot_id);
    /* The BLE module owns its worker and bounded pool. */
}
