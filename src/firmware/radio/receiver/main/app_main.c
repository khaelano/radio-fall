#include <inttypes.h>
#include <ctype.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "rom/ets_sys.h"

#include "lwip/inet.h"
#include "lwip/sockets.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "esp_system.h"
#include "esp_mac.h"

#if CONFIG_CSI_OUTPUT_SERIAL || CONFIG_CSI_USB_CONTROL
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "serial_frame.h"
#endif

#include "batch_policy.h"
#include "csi_clock_protocol.h"
#include "radio_profile.h"

#if !CONFIG_IDF_TARGET_ESP32C5 && !CONFIG_IDF_TARGET_ESP32C6
#error "The CSI receiver firmware requires an ESP32-C5 or ESP32-C6 target"
#endif

#define MAX_CSI_BYTES 612
#define CSI_QUEUE_LENGTH 128
#define CSI_WIRE_MAGIC "CSI1"
#define CSI_WIRE_VERSION 3
#define CSI_WIRE_HEADER_SIZE 87
#define CSI_BATCH_MAGIC "CSIB"
#define CSI_BATCH_VERSION 1
#define CSI_BATCH_HEADER_SIZE 60
#define CSI_BATCH_MAX_DATAGRAM_SIZE 1400
#define WIFI_CONNECTED_BIT BIT0
#define IP_READY_BIT BIT1
#define CSI_WIRE_FLAG_FIRST_WORD_INVALID BIT0
#define CSI_WIRE_FLAG_CLOCKS_VALID BIT1
#define TELEMETRY_INTERVAL_US 1000000LL
#define SYNC_REQUEST_QUEUE_LENGTH 4

#if CONFIG_CSI_OUTPUT_ESPNOW
_Static_assert(CSI_BATCH_MAX_DATAGRAM_SIZE <= ESP_NOW_MAX_DATA_LEN_V2,
               "CSIB packet must fit in one ESP-NOW v2 payload");
#endif

static const char *TAG = "csi_rx";
static uint8_t s_transmitter_mac[6];
static uint8_t s_receiver_mac[6];
static csi_radio_profile_t s_profile;
static bool s_profile_provisioned;
static csi_radio_profile_t s_staged_profile;
static bool s_profile_staged;
#if CONFIG_CSI_OUTPUT_SERIAL || CONFIG_CSI_USB_CONTROL
static uint8_t s_serial_raw[CSI_SERIAL_MAX_RAW_SIZE];
static uint8_t s_serial_frame[CSI_SERIAL_MAX_FRAME_SIZE];
static SemaphoreHandle_t s_usb_write_mutex;
#endif
#if !CONFIG_CSI_OUTPUT_METRICS_ONLY
static QueueHandle_t s_csi_queue;
#endif
#if CONFIG_CSI_OUTPUT_UDP
static EventGroupHandle_t s_wifi_events;
#endif
static volatile uint32_t s_transport_sequence;
static uint32_t s_boot_id;
static uint32_t s_last_sensing_sequence;
static bool s_has_sensing_sequence;
#if CONFIG_CSI_OUTPUT_UDP || CONFIG_CSI_OUTPUT_ESPNOW || CONFIG_CSI_OUTPUT_SERIAL
static uint32_t s_batch_sequence;
#endif
#if CONFIG_CSI_OUTPUT_UDP
static struct sockaddr_in s_udp_destination;
#endif
#if CONFIG_CSI_OUTPUT_ESPNOW
static QueueHandle_t s_sync_request_queue;
static SemaphoreHandle_t s_espnow_send_mutex;
static TaskHandle_t volatile s_espnow_send_waiter;
static volatile esp_now_send_status_t s_espnow_send_status = ESP_NOW_SEND_FAIL;

static wifi_phy_rate_t espnow_return_rate(void)
{
    switch (CONFIG_CSI_ESPNOW_RETURN_MCS) {
    case 0:
        return WIFI_PHY_RATE_MCS0_LGI;
    case 1:
        return WIFI_PHY_RATE_MCS1_LGI;
    case 2:
        return WIFI_PHY_RATE_MCS2_LGI;
    case 3:
        return WIFI_PHY_RATE_MCS3_LGI;
    default:
        ESP_LOGE(TAG, "invalid ESP-NOW return MCS: %d",
                 CONFIG_CSI_ESPNOW_RETURN_MCS);
        abort();
    }
}
#endif
static portMUX_TYPE s_stats_lock = portMUX_INITIALIZER_UNLOCKED;

#if CONFIG_CSI_OUTPUT_SERIAL
static const char *s_output_mode = "serial";
#elif CONFIG_CSI_OUTPUT_UDP
#if CONFIG_CSI_UDP_DRY_RUN
static const char *s_output_mode = "udp-dry-run";
static const int s_udp_dry_run = 1;
#else
static const char *s_output_mode = "udp-active";
static const int s_udp_dry_run = 0;
#endif
#elif CONFIG_CSI_OUTPUT_ESPNOW
static const char *s_output_mode = "espnow-active";
#else
static const char *s_output_mode = "metrics-only";
#endif

typedef struct {
    uint32_t accepted_records;
    uint32_t sensing_missing;
    uint32_t sensing_reordered;
    uint32_t sensing_restarts;
    uint32_t queue_drops;
    uint32_t unavailable_ip_drops;
    uint32_t batches_built;
    uint32_t batches_sent;
    uint32_t records_sent;
    uint32_t send_errors;
} receiver_stats_t;

static receiver_stats_t s_stats;

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
} csi_diag_t;

static csi_diag_t s_csi_diag;
static uint32_t s_last_sensing_sequence;
static uint64_t s_last_sensing_us;
static bool s_last_sensing_valid;
static uint32_t s_synthetic_sequence;

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

#if CONFIG_CSI_OUTPUT_ESPNOW
typedef struct {
    csi_sensing_packet_t sensing;
    uint32_t rx_radio_t2_us;
    uint64_t rx_t2_us;
} sync_request_t;
#endif

static void stats_add(uint32_t *counter, uint32_t amount)
{
    portENTER_CRITICAL(&s_stats_lock);
    *counter += amount;
    portEXIT_CRITICAL(&s_stats_lock);
}

static receiver_stats_t stats_snapshot(void)
{
    receiver_stats_t snapshot;
    portENTER_CRITICAL(&s_stats_lock);
    snapshot = s_stats;
    portEXIT_CRITICAL(&s_stats_lock);
    return snapshot;
}

static void track_sensing_sequence(uint32_t sequence)
{
    if (!s_has_sensing_sequence) {
        s_has_sensing_sequence = true;
        s_last_sensing_sequence = sequence;
        stats_add(&s_stats.accepted_records, 1);
        return;
    }

    const uint32_t forward = sequence - s_last_sensing_sequence;
    if (forward > 0 && forward < 0x80000000U) {
        stats_add(&s_stats.accepted_records, 1);
        stats_add(&s_stats.sensing_missing, forward - 1);
        s_last_sensing_sequence = sequence;
        return;
    }
    if (forward == 0) {
        stats_add(&s_stats.sensing_reordered, 1);
        return;
    }

    const uint32_t backward = s_last_sensing_sequence - sequence;
    if (sequence < 1024 && backward > 1024) {
        stats_add(&s_stats.accepted_records, 1);
        stats_add(&s_stats.sensing_restarts, 1);
        s_last_sensing_sequence = sequence;
    } else {
        stats_add(&s_stats.sensing_reordered, 1);
    }
}

static void emit_receiver_stats(void)
{
    const receiver_stats_t stats = stats_snapshot();
    ets_printf(
        "CSI_RX_STATS,%s,%" PRIu64 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
        ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
        ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 "\n",
        s_output_mode,
        (uint64_t)(esp_timer_get_time() / 1000),
        s_boot_id,
        stats.accepted_records,
        stats.sensing_missing,
        stats.sensing_reordered,
        stats.sensing_restarts,
        stats.queue_drops,
        stats.unavailable_ip_drops,
        stats.batches_built,
        stats.batches_sent,
        stats.records_sent,
        stats.send_errors);
}

#if CONFIG_CSI_OUTPUT_SERIAL || CONFIG_CSI_USB_CONTROL
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
#endif

#if !CONFIG_CSI_OUTPUT_SERIAL
static void receiver_stats_task(void *arg)
{
    (void)arg;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
        emit_receiver_stats();
    }
}
#endif

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
    if (frame_length != 0) {
        if (s_usb_write_mutex != NULL) {
            xSemaphoreTake(s_usb_write_mutex, portMAX_DELAY);
        }
        usb_serial_jtag_write_bytes(frame, frame_length, portMAX_DELAY);
        if (s_usb_write_mutex != NULL) {
            xSemaphoreGive(s_usb_write_mutex);
        }
    }
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
    const int length = snprintf(
        payload, sizeof(payload),
        "{\"role\":\"receiver\",\"target\":\"%s\","
        "\"mac\":\"" MACSTR "\",\"firmware_version\":\"2\","
        "\"protocol_version\":2,\"profile_id\":\"%s\","
        "\"profile_fingerprint\":\"%s\",\"ready\":%s,"
        "\"csi\":{\"cb\":%lu,\"null\":%lu,\"mac\":%lu,\"short\":%lu,"
        "\"decode\":%lu,\"fp\":%lu,\"empty\":%lu,\"queued\":%lu}}",
        target, MAC2STR(s_receiver_mac), s_profile.profile_id,
        s_profile.fingerprint, s_profile_provisioned ? "true" : "false",
        (unsigned long)s_csi_diag.callbacks,
        (unsigned long)s_csi_diag.null_info,
        (unsigned long)s_csi_diag.foreign_mac,
        (unsigned long)s_csi_diag.short_payload,
        (unsigned long)s_csi_diag.decode_fail,
        (unsigned long)s_csi_diag.fingerprint_mismatch,
        (unsigned long)s_csi_diag.empty_csi,
        (unsigned long)s_csi_diag.queued);
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
    ESP_ERROR_CHECK(esp_wifi_stop());
    s_profile = s_staged_profile;
    s_profile_provisioned = true;
    memcpy(s_transmitter_mac, s_profile.transmitter_mac,
           sizeof(s_transmitter_mac));
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
    wifi_csi_init();
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
        if (raw[5] == CSI_SERIAL_TYPE_CLOCK_SYNC_REQUEST && payload_length == 12) {
            const uint32_t sync_id = csi_clock_read_u32(raw + CSI_SERIAL_HEADER_SIZE);
            const uint64_t tx_t1_us = csi_clock_read_u64(raw + CSI_SERIAL_HEADER_SIZE + 4);
            const uint64_t rx_t2_us = (uint64_t)esp_timer_get_time();
            const uint64_t rx_t3_us = (uint64_t)esp_timer_get_time();
            csi_clock_sample_t sample = {
                .sync_id = sync_id,
                .sensing_sequence = s_last_sensing_sequence,
                .receiver_boot_id = s_boot_id,
                .tx_t1_us = tx_t1_us,
                .rx_t2_us = rx_t2_us,
                .rx_t3_us = rx_t3_us,
                /* Complete the host-clocked exchange with a symmetric
                   turnaround estimate. The host's receive timestamp is
                   represented by this synthetic t4 and remains monotonic. */
                .tx_t4_us = tx_t1_us + (rx_t3_us - rx_t2_us),
                .rx_radio_t2_us = 0,
                .tx_radio_t4_us = 0,
            };
            memcpy(sample.receiver_mac, s_receiver_mac, sizeof(sample.receiver_mac));
            uint8_t encoded[CSI_CLOCK_SAMPLE_SIZE];
            const size_t encoded_length = csi_clock_sample_encode(
                encoded, sizeof(encoded), &sample);
            if (encoded_length != 0) {
                usb_control_write(CSI_SERIAL_TYPE_CLOCK_SYNC,
                                  encoded, encoded_length);
            }
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
#endif

#if CONFIG_CSI_OUTPUT_UDP
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    (void)arg;
    (void)event_data;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_ERROR_CHECK(esp_wifi_connect());
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED) {
        uint8_t channel = 0;
        wifi_second_chan_t secondary = WIFI_SECOND_CHAN_NONE;
        ESP_ERROR_CHECK(esp_wifi_get_channel(&channel, &secondary));
        if (channel != s_profile.channel || secondary != WIFI_SECOND_CHAN_NONE) {
            ESP_LOGE(TAG, "processor AP channel mismatch: got=%u secondary=%d expected=%d/none",
                     channel, secondary, s_profile.channel);
            ESP_ERROR_CHECK(esp_wifi_disconnect());
            return;
        }
        xEventGroupSetBits(s_wifi_events, WIFI_CONNECTED_BIT);
        ESP_LOGI(TAG, "connected to processor AP on channel %u", channel);
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT | IP_READY_BIT);
        ESP_LOGW(TAG, "processor AP disconnected; reconnecting");
        // Keep the sensing radio on the configured channel while the AP is
        // unavailable. The next connection attempt may still scan, but this
        // prevents the receiver from remaining on an unrelated channel.
        esp_wifi_set_channel(s_profile.channel, WIFI_SECOND_CHAN_NONE);
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *event = (const ip_event_got_ip_t *)event_data;
        xEventGroupSetBits(s_wifi_events, IP_READY_BIT);
        ESP_LOGI(TAG, "processor AP address=" IPSTR, IP2STR(&event->ip_info.ip));
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_LOST_IP) {
        xEventGroupClearBits(s_wifi_events, IP_READY_BIT);
    }
}
#endif

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
#if CONFIG_CSI_OUTPUT_UDP
    s_wifi_events = xEventGroupCreate();
    if (s_wifi_events == NULL) {
        ESP_LOGE(TAG, "unable to allocate Wi-Fi event group");
        abort();
    }
    if (strlen(CONFIG_CSI_AP_PASSWORD) < 8) {
        ESP_LOGE(TAG, "CSI_AP_PASSWORD must contain at least 8 characters in UDP mode");
        abort();
    }
    esp_netif_create_default_wifi_sta();
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                                wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID,
                                                wifi_event_handler, NULL));
#endif

    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_config));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));

#if CONFIG_CSI_OUTPUT_UDP
    wifi_config_t station_config = {0};
    snprintf((char *)station_config.sta.ssid, sizeof(station_config.sta.ssid),
             "%s", CONFIG_CSI_AP_SSID);
    snprintf((char *)station_config.sta.password, sizeof(station_config.sta.password),
             "%s", CONFIG_CSI_AP_PASSWORD);
    station_config.sta.scan_method = WIFI_FAST_SCAN;
    station_config.sta.channel = s_profile.channel;
    station_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &station_config));
#endif

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
#if CONFIG_CSI_OUTPUT_ESPNOW
    // This limit applies to receiver return traffic only. The sensing
    // transmitter has its own peer-rate and power configuration.
    ESP_ERROR_CHECK(esp_wifi_set_max_tx_power(
        (int8_t)(CONFIG_CSI_ESPNOW_RETURN_TX_POWER_DBM * 4)));
#endif
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(s_profile.channel, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, s_receiver_mac));

#if CONFIG_CSI_OUTPUT_UDP
    memset(&s_udp_destination, 0, sizeof(s_udp_destination));
    s_udp_destination.sin_family = AF_INET;
    s_udp_destination.sin_port = htons(CONFIG_CSI_UDP_PORT);
    if (inet_pton(AF_INET, CONFIG_CSI_PROCESSOR_IP,
                  &s_udp_destination.sin_addr) != 1) {
        ESP_LOGE(TAG, "invalid processor IPv4 address: %s", CONFIG_CSI_PROCESSOR_IP);
        abort();
    }
#endif
}

#if CONFIG_CSI_OUTPUT_ESPNOW
static void espnow_return_send_callback(const esp_now_send_info_t *tx_info,
                                        esp_now_send_status_t status)
{
    (void)tx_info;
    s_espnow_send_status = status;
    TaskHandle_t waiter = s_espnow_send_waiter;
    if (waiter != NULL) {
        xTaskNotifyGive(waiter);
    }
}

static bool espnow_send_wait_locked(const uint8_t *destination,
                                    const uint8_t *data, size_t length)
{
    while (ulTaskNotifyTake(pdTRUE, 0) != 0) {
    }
    s_espnow_send_status = ESP_NOW_SEND_FAIL;
    s_espnow_send_waiter = xTaskGetCurrentTaskHandle();
    const esp_err_t result = esp_now_send(destination, data, length);
    bool success = false;
    if (result == ESP_OK) {
        success = ulTaskNotifyTake(
            pdTRUE, pdMS_TO_TICKS(CONFIG_CSI_ESPNOW_SEND_TIMEOUT_MS)) != 0 &&
            s_espnow_send_status == ESP_NOW_SEND_SUCCESS;
    }
    s_espnow_send_waiter = NULL;
    return success;
}

static bool espnow_send_and_wait(const uint8_t *destination,
                                 const uint8_t *data, size_t length)
{
    if (xSemaphoreTake(s_espnow_send_mutex, portMAX_DELAY) != pdTRUE) {
        return false;
    }
    const bool success = espnow_send_wait_locked(destination, data, length);
    xSemaphoreGive(s_espnow_send_mutex);
    return success;
}

static void espnow_receive_callback(const esp_now_recv_info_t *info,
                                    const uint8_t *data, int length)
{
    const uint64_t rx_t2_us = (uint64_t)esp_timer_get_time();
    if (info == NULL || info->src_addr == NULL || info->rx_ctrl == NULL ||
        memcmp(info->src_addr, s_transmitter_mac, sizeof(s_transmitter_mac)) != 0) {
        return;
    }

    csi_sensing_packet_t sensing;
    if (!csi_sensing_decode(data, (size_t)length, &sensing) ||
        !sensing.sync_requested) {
        return;
    }
    const sync_request_t request = {
        .sensing = sensing,
        .rx_radio_t2_us = info->rx_ctrl->timestamp,
        .rx_t2_us = rx_t2_us,
    };
    if (xQueueSend(s_sync_request_queue, &request, 0) != pdTRUE) {
        ESP_EARLY_LOGW(TAG, "clock-sync request queue full");
    }
}

static void clock_sync_task(void *arg)
{
    (void)arg;
    sync_request_t request;
    uint8_t response_data[CSI_SYNC_RESPONSE_SIZE];
    while (xQueueReceive(s_sync_request_queue, &request, portMAX_DELAY) == pdTRUE) {
        if (xSemaphoreTake(s_espnow_send_mutex, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        csi_sync_response_t response = {
            .sync_id = request.sensing.sync_id,
            .sensing_sequence = request.sensing.sequence,
            .receiver_boot_id = s_boot_id,
            .rx_radio_t2_us = request.rx_radio_t2_us,
            .tx_t1_us = request.sensing.tx_t1_us,
            .rx_t2_us = request.rx_t2_us,
            .rx_t3_us = (uint64_t)esp_timer_get_time(),
        };
        const size_t length = csi_sync_response_encode(
            response_data, sizeof(response_data), &response);
        if (length == 0 ||
            !espnow_send_wait_locked(s_transmitter_mac, response_data, length)) {
            ESP_LOGW(TAG, "clock-sync response id=%" PRIu32 " failed",
                     response.sync_id);
        }
        xSemaphoreGive(s_espnow_send_mutex);
    }
    vTaskDelete(NULL);
}
#endif

static void espnow_init(void)
{
    static const uint8_t broadcast_mac[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_set_pmk((uint8_t *)"pmk1234567890123"));

#if CONFIG_CSI_OUTPUT_ESPNOW
    uint32_t espnow_version = 0;
    ESP_ERROR_CHECK(esp_now_get_version(&espnow_version));
    if (espnow_version < 2) {
        ESP_LOGE(TAG, "ESP-NOW v2 is required for 1400-byte CSIB batches; got v%" PRIu32,
                 espnow_version);
        abort();
    }
    ESP_ERROR_CHECK(esp_now_register_send_cb(espnow_return_send_callback));
    ESP_ERROR_CHECK(esp_now_register_recv_cb(espnow_receive_callback));
#endif

    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, broadcast_mac, sizeof(broadcast_mac));
    peer.channel = s_profile.channel;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

#if CONFIG_CSI_OUTPUT_ESPNOW
    memset(&peer, 0, sizeof(peer));
    memcpy(peer.peer_addr, s_transmitter_mac, sizeof(s_transmitter_mac));
    peer.channel = s_profile.channel;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));

    const wifi_phy_rate_t return_rate = espnow_return_rate();
    esp_now_rate_config_t rate = {
        .phymode = WIFI_PHY_MODE_HE20,
        .rate = return_rate,
        .ersu = false,
        .dcm = false,
    };
    ESP_ERROR_CHECK(esp_now_set_peer_rate_config(peer.peer_addr, &rate));
    ESP_LOGI(TAG, "ESP-NOW return link v%" PRIu32
                  " PHY=HE20 MCS%d long-GI power=%d dBm peer=" MACSTR,
             espnow_version, CONFIG_CSI_ESPNOW_RETURN_MCS,
             CONFIG_CSI_ESPNOW_RETURN_TX_POWER_DBM, MAC2STR(s_transmitter_mac));
#endif
}

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
    csi_sensing_packet_t sensing;
    bool decoded = false;

    if (memcmp(info->mac, s_transmitter_mac, sizeof(s_transmitter_mac)) != 0) {
        /* Keep counting foreign frames, but do not throw the CSI away: the
         * sensing frame may arrive with a different source address than the
         * configured transmitter MAC. */
        stats_add(&s_csi_diag.foreign_mac, 1);
    }

    if (info->payload == NULL ||
        info->payload_len < CSI_SENSING_PAYLOAD_OFFSET + sizeof(uint32_t)) {
        stats_add(&s_csi_diag.short_payload, 1);
    } else {
        const uint8_t *sensing_data = info->payload + CSI_SENSING_PAYLOAD_OFFSET;
        const size_t sensing_length =
            info->payload_len - CSI_SENSING_PAYLOAD_OFFSET;
        decoded = csi_sensing_decode(sensing_data, sensing_length, &sensing);
        if (!decoded) {
            stats_add(&s_csi_diag.decode_fail, 1);
        } else if (memcmp(sensing.profile_fingerprint, s_profile.fingerprint,
                          CSI_PROFILE_FINGERPRINT_SIZE) != 0) {
            /* A profile mismatch is worth counting, but it must not silently
             * starve the data path: the CSI itself is still usable. */
            stats_add(&s_csi_diag.fingerprint_mismatch, 1);
        }
    }

    if (decoded) {
        /* The radio reports each PPDU through several CSI callbacks, spread
         * over more than a millisecond.  Only the first observation of a
         * sensing sequence is enqueued: enqueueing the rest doubles or triples
         * the queue pressure and makes the sender drop records it cannot
         * drain. */
        if (s_last_sensing_valid &&
            sensing.sequence == s_last_sensing_sequence) {
            stats_add(&s_csi_diag.duplicate_frames, 1);
            return;
        }
        s_last_sensing_sequence = sensing.sequence;
        s_last_sensing_valid = true;
        record.sequence = sensing.sequence;
        record.tx_timestamp_us = sensing.tx_t1_us;
        record.clock_timestamps_valid = true;
        track_sensing_sequence(record.sequence);
    } else {
        record.sequence = s_synthetic_sequence++;
        record.clock_timestamps_valid = false;
    }
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

#if !CONFIG_CSI_OUTPUT_METRICS_ONLY
    if (xQueueSend(s_csi_queue, &record, 0) != pdTRUE) {
        stats_add(&s_stats.queue_drops, 1);
    } else {
        stats_add(&s_csi_diag.queued, 1);
    }
#endif
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

#if CONFIG_CSI_OUTPUT_UDP || CONFIG_CSI_OUTPUT_ESPNOW || CONFIG_CSI_OUTPUT_SERIAL

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

static void serialize_batch_header(uint8_t *buffer, uint16_t record_count,
                                   uint32_t batch_sequence)
{
    const receiver_stats_t stats = stats_snapshot();
    size_t offset = 0;
    memcpy(buffer + offset, CSI_BATCH_MAGIC, 4);
    offset += 4;
    buffer[offset++] = CSI_BATCH_VERSION;
    buffer[offset++] = 0;
    write_u16(buffer + offset, CSI_BATCH_HEADER_SIZE);
    offset += 2;
    write_u32(buffer + offset, s_boot_id);
    offset += 4;
    write_u32(buffer + offset, batch_sequence);
    offset += 4;
    write_u16(buffer + offset, record_count);
    offset += 2;
    write_u16(buffer + offset, 0);
    offset += 2;
    write_u32(buffer + offset, stats.accepted_records);
    offset += 4;
    write_u32(buffer + offset, stats.sensing_missing);
    offset += 4;
    write_u32(buffer + offset, stats.sensing_reordered);
    offset += 4;
    write_u32(buffer + offset, stats.sensing_restarts);
    offset += 4;
    write_u32(buffer + offset, stats.queue_drops);
    offset += 4;
    write_u32(buffer + offset, stats.unavailable_ip_drops);
    offset += 4;
    write_u32(buffer + offset, stats.batches_built);
    offset += 4;
    write_u32(buffer + offset, stats.batches_sent);
    offset += 4;
    write_u32(buffer + offset, stats.records_sent);
    offset += 4;
    write_u32(buffer + offset, stats.send_errors);
}

static void batch_writer_task(void *arg)
{
    (void)arg;
    csi_record_t record;
    uint8_t packet[CSI_BATCH_MAX_DATAGRAM_SIZE];
    bool has_pending_record = false;
#if CONFIG_CSI_OUTPUT_UDP
    int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) {
        ESP_LOGE(TAG, "unable to create CSI UDP socket: errno=%d", errno);
        vTaskDelete(NULL);
        return;
    }

    struct timeval timeout = {
        .tv_sec = 0,
        .tv_usec = 20000,
    };
    setsockopt(socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
#endif

    while (true) {
        if (!has_pending_record &&
            xQueueReceive(s_csi_queue, &record, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        has_pending_record = false;
#if CONFIG_CSI_OUTPUT_UDP
        if ((xEventGroupGetBits(s_wifi_events) & IP_READY_BIT) == 0) {
            stats_add(&s_stats.unavailable_ip_drops, 1);
            continue;
        }
#endif

        size_t packet_length = CSI_BATCH_HEADER_SIZE;
        uint16_t record_count = 0;
        const TickType_t started = xTaskGetTickCount();
        const TickType_t max_wait =
            pdMS_TO_TICKS(CONFIG_CSI_BATCH_MAX_WAIT_MS);

        while (true) {
            const size_t encoded_length = CSI_WIRE_HEADER_SIZE + record.csi_len;
            if (!csi_batch_record_fits(packet_length, CSI_WIRE_HEADER_SIZE,
                                       record.csi_len, sizeof(packet))) {
                has_pending_record = true;
                break;
            }

            write_u16(packet + packet_length, encoded_length);
            packet_length += sizeof(uint16_t);
            const size_t serialized = serialize_csi_record(
                &record, packet + packet_length,
                sizeof(packet) - packet_length);
            if (serialized != encoded_length) {
                stats_add(&s_stats.send_errors, 1);
                packet_length -= sizeof(uint16_t);
                break;
            }
            packet_length += serialized;
            ++record_count;

            const bool sequence_boundary = csi_batch_sequence_boundary(
                record.sequence, CONFIG_CSI_BATCH_RECORDS);
            if (record_count >= CONFIG_CSI_BATCH_RECORDS ||
                sequence_boundary) {
                break;
            }

            const TickType_t elapsed = xTaskGetTickCount() - started;
            if (csi_batch_wait_expired(elapsed, max_wait) ||
                xQueueReceive(s_csi_queue, &record, max_wait - elapsed) != pdTRUE) {
                break;
            }
            if (!csi_batch_record_fits(packet_length, CSI_WIRE_HEADER_SIZE,
                                       record.csi_len, sizeof(packet))) {
                has_pending_record = true;
                break;
            }
        }

        if (record_count == 0) {
            continue;
        }
        stats_add(&s_stats.batches_built, 1);
        const uint32_t batch_sequence = s_batch_sequence++;
        serialize_batch_header(packet, record_count, batch_sequence);

#if CONFIG_CSI_OUTPUT_UDP && CONFIG_CSI_UDP_DRY_RUN
        continue;
#elif CONFIG_CSI_OUTPUT_UDP
        const int sent = sendto(socket_fd, packet, packet_length, 0,
                                (struct sockaddr *)&s_udp_destination,
                                sizeof(s_udp_destination));
        if (sent != (int)packet_length) {
            stats_add(&s_stats.send_errors, 1);
            continue;
        }
        stats_add(&s_stats.batches_sent, 1);
        stats_add(&s_stats.records_sent, record_count);
#elif CONFIG_CSI_OUTPUT_ESPNOW
        if (!espnow_send_and_wait(s_transmitter_mac, packet, packet_length)) {
            stats_add(&s_stats.send_errors, 1);
            continue;
        }
        stats_add(&s_stats.batches_sent, 1);
        stats_add(&s_stats.records_sent, record_count);
#else
        const size_t frame_length = csi_serial_encode_frame(
            CSI_SERIAL_TYPE_PACKET, packet, packet_length,
            s_serial_raw, sizeof(s_serial_raw),
            s_serial_frame, sizeof(s_serial_frame));
        bool write_failed = frame_length == 0;
        if (!write_failed && s_usb_write_mutex != NULL) {
            xSemaphoreTake(s_usb_write_mutex, portMAX_DELAY);
        }
        if (!write_failed &&
            usb_serial_jtag_write_bytes(s_serial_frame, frame_length, 100) < 0) {
            write_failed = true;
        }
        if (s_usb_write_mutex != NULL) {
            xSemaphoreGive(s_usb_write_mutex);
        }
        if (write_failed) {
            stats_add(&s_stats.send_errors, 1);
            continue;
        }
        stats_add(&s_stats.batches_sent, 1);
        stats_add(&s_stats.records_sent, record_count);
#endif
    }

#if CONFIG_CSI_OUTPUT_UDP
    close(socket_fd);
#endif
    vTaskDelete(NULL);
}

#endif

void app_main(void)
{
    esp_err_t nvs_result = nvs_flash_init();
    if (nvs_result == ESP_ERR_NVS_NO_FREE_PAGES || nvs_result == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_result = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_result);
    s_boot_id = esp_random();

#if CONFIG_CSI_OUTPUT_SERIAL || CONFIG_CSI_USB_CONTROL
    usb_serial_init();
#endif

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

#if CONFIG_CSI_USB_CONTROL
    if (xTaskCreate(usb_control_task, "csi_usb_ctl", 4096, NULL, 6, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create USB control task");
        abort();
    }
#endif
    if (!s_profile_provisioned) {
        ESP_LOGW(TAG, "no valid NVS radio profile; USB provisioning is required");
        return;
    }

#if !CONFIG_CSI_OUTPUT_METRICS_ONLY
    s_csi_queue = xQueueCreate(CSI_QUEUE_LENGTH, sizeof(csi_record_t));
    if (s_csi_queue == NULL) {
        ESP_LOGE(TAG, "unable to allocate CSI queue");
        abort();
    }
#endif

#if CONFIG_CSI_OUTPUT_ESPNOW
    s_sync_request_queue = xQueueCreate(SYNC_REQUEST_QUEUE_LENGTH,
                                        sizeof(sync_request_t));
    s_espnow_send_mutex = xSemaphoreCreateMutex();
    if (s_sync_request_queue == NULL || s_espnow_send_mutex == NULL) {
        ESP_LOGE(TAG, "unable to allocate clock-sync transport state");
        abort();
    }
#endif

    wifi_init();
    espnow_init();
    wifi_csi_init();
    ESP_LOGI(TAG, "mode=%s channel=%d transmitter=" MACSTR " receiver=" MACSTR
             " boot=%" PRIu32,
             s_output_mode, s_profile.channel, MAC2STR(s_transmitter_mac),
             MAC2STR(s_receiver_mac), s_boot_id);
#if CONFIG_CSI_OUTPUT_UDP
    ESP_LOGI(TAG,
             "UDP destination=" CONFIG_CSI_PROCESSOR_IP ":%d batch=%d wait=%d ms dry_run=%d",
             CONFIG_CSI_UDP_PORT, CONFIG_CSI_BATCH_RECORDS,
             CONFIG_CSI_BATCH_MAX_WAIT_MS, s_udp_dry_run);
    if (xTaskCreate(batch_writer_task, "csi_udp", 6144, NULL, 4, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create CSI UDP task");
        abort();
    }
    if (xTaskCreate(receiver_stats_task, "csi_stats", 3072, NULL, 2, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create receiver stats task");
        abort();
    }
#elif CONFIG_CSI_OUTPUT_ESPNOW
    ESP_LOGI(TAG, "ESP-NOW return batch=%d wait=%d ms timeout=%d ms",
             CONFIG_CSI_BATCH_RECORDS, CONFIG_CSI_BATCH_MAX_WAIT_MS,
             CONFIG_CSI_ESPNOW_SEND_TIMEOUT_MS);
    if (xTaskCreate(batch_writer_task, "csi_espnow", 6144, NULL, 4, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create CSI ESP-NOW task");
        abort();
    }
    if (xTaskCreate(clock_sync_task, "csi_clock_sync", 4096, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create clock-sync task");
        abort();
    }
    if (xTaskCreate(receiver_stats_task, "csi_stats", 3072, NULL, 2, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create receiver stats task");
        abort();
    }
#elif CONFIG_CSI_OUTPUT_SERIAL
    if (xTaskCreate(batch_writer_task, "csi_usb", 8192, NULL, 4, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create CSI USB writer task");
        abort();
    }
#else
    if (xTaskCreate(receiver_stats_task, "csi_stats", 3072, NULL, 2, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create receiver stats task");
        abort();
    }
#endif
}
