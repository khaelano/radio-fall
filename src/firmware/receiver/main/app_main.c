#include <inttypes.h>
#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "rom/ets_sys.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_wifi.h"

#define MAX_CSI_BYTES 612
#define PAYLOAD_SEQUENCE_OFFSET 15
#define CSI_QUEUE_LENGTH 32
#define CSI_LINE_BUFFER_SIZE (MAX_CSI_BYTES * 5 + 512)

static const char *TAG = "csi_rx";
static uint8_t s_transmitter_mac[6];
static QueueHandle_t s_csi_queue;
static volatile uint32_t s_queue_drops;

typedef struct {
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
    uint8_t antenna;
    uint16_t sig_len;
    uint8_t rx_state;
    uint16_t csi_len;
    bool first_word_invalid;
    int8_t csi[MAX_CSI_BYTES];
} csi_record_t;

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

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t wifi_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_config));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW20));
    ESP_ERROR_CHECK(esp_wifi_set_protocol(
        WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_channel(CONFIG_CSI_CHANNEL, WIFI_SECOND_CHAN_NONE));
}

static void espnow_init(void)
{
    static const uint8_t broadcast_mac[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

    ESP_ERROR_CHECK(esp_now_init());
    ESP_ERROR_CHECK(esp_now_set_pmk((uint8_t *)"pmk1234567890123"));

    esp_now_peer_info_t peer = {0};
    memcpy(peer.peer_addr, broadcast_mac, sizeof(broadcast_mac));
    peer.channel = CONFIG_CSI_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    ESP_ERROR_CHECK(esp_now_add_peer(&peer));
}

static void wifi_csi_callback(void *ctx, wifi_csi_info_t *info)
{
    (void)ctx;
    if (info == NULL || info->buf == NULL || info->payload == NULL) {
        return;
    }
    if (memcmp(info->mac, s_transmitter_mac, sizeof(s_transmitter_mac)) != 0) {
        return;
    }
    if (info->payload_len < PAYLOAD_SEQUENCE_OFFSET + sizeof(uint32_t)) {
        return;
    }

    csi_record_t record = {0};
    memcpy(&record.sequence, info->payload + PAYLOAD_SEQUENCE_OFFSET, sizeof(record.sequence));
    record.rssi = info->rx_ctrl.rssi;
    record.noise_floor = info->rx_ctrl.noise_floor;
    record.rate = info->rx_ctrl.rate;
    record.sig_mode = info->rx_ctrl.sig_mode;
    record.mcs = info->rx_ctrl.mcs;
    record.bandwidth = info->rx_ctrl.cwb;
    record.smoothing = info->rx_ctrl.smoothing;
    record.not_sounding = info->rx_ctrl.not_sounding;
    record.aggregation = info->rx_ctrl.aggregation;
    record.stbc = info->rx_ctrl.stbc;
    record.fec_coding = info->rx_ctrl.fec_coding;
    record.sgi = info->rx_ctrl.sgi;
    record.ampdu_count = info->rx_ctrl.ampdu_cnt;
    record.channel = info->rx_ctrl.channel;
    record.secondary_channel = info->rx_ctrl.secondary_channel;
    record.timestamp = info->rx_ctrl.timestamp;
    record.antenna = info->rx_ctrl.ant;
    record.sig_len = info->rx_ctrl.sig_len;
    record.rx_state = info->rx_ctrl.rx_state;
    record.csi_len = info->len > MAX_CSI_BYTES ? MAX_CSI_BYTES : info->len;
    // CSI is serialized as imaginary/real pairs. Drop a dangling byte (or an
    // empty callback) instead of emitting a row the host cannot interpret.
    record.csi_len &= (uint16_t)~1U;
    if (record.csi_len == 0) {
        return;
    }
    record.first_word_invalid = info->first_word_invalid;
    memcpy(record.csi, info->buf, record.csi_len);

    if (xQueueSend(s_csi_queue, &record, 0) != pdTRUE) {
        ++s_queue_drops;
    }
}

static void wifi_csi_init(void)
{
    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));

    wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = true,
        .manu_scale = false,
        .shift = 0,
        .dump_ack_en = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_callback, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));
}

static bool append_text(char *buffer, size_t capacity, size_t *used, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    int written = vsnprintf(buffer + *used, capacity - *used, format, arguments);
    va_end(arguments);
    if (written < 0 || (size_t)written >= capacity - *used) {
        return false;
    }
    *used += (size_t)written;
    return true;
}

static bool format_csv_record(const csi_record_t *record, char *line, size_t capacity)
{
    size_t used = 0;
    int written = snprintf(
        line, capacity,
        "CSI_DATA,%" PRIu32 "," MACSTR ",%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%" PRIu32 ",%d,%d,%d,%d,%d,\"[%d",
        record->sequence,
        MAC2STR(s_transmitter_mac),
        record->rssi,
        record->rate,
        record->sig_mode,
        record->mcs,
        record->bandwidth,
        record->smoothing,
        record->not_sounding,
        record->aggregation,
        record->stbc,
        record->fec_coding,
        record->sgi,
        record->noise_floor,
        record->ampdu_count,
        record->channel,
        record->secondary_channel,
        record->timestamp,
        record->antenna,
        record->sig_len,
        record->rx_state,
        record->csi_len,
        record->first_word_invalid,
        record->csi[0]);
    if (written < 0 || (size_t)written >= capacity) {
        return false;
    }
    used = (size_t)written;
    for (uint16_t i = 1; i < record->csi_len; ++i) {
        if (!append_text(line, capacity, &used, ",%d", record->csi[i])) {
            return false;
        }
    }
    return append_text(line, capacity, &used, "]\"\n");
}

static void csv_writer_task(void *arg)
{
    (void)arg;
    csi_record_t record;
    char *line = malloc(CSI_LINE_BUFFER_SIZE);
    if (line == NULL) {
        ESP_LOGE(TAG, "unable to allocate CSV line buffer");
        vTaskDelete(NULL);
        return;
    }
    ets_printf("type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,secondary_channel,local_timestamp,ant,sig_len,rx_state,len,first_word,data\n");

    uint32_t reported_drops = 0;
    while (xQueueReceive(s_csi_queue, &record, portMAX_DELAY) == pdTRUE) {
        if (record.csi_len == 0 || !format_csv_record(&record, line, CSI_LINE_BUFFER_SIZE)) {
            ESP_LOGW(TAG, "unable to format CSI record");
            continue;
        }
        // Emit a complete row in one console write. Diagnostics are emitted
        // only after the row, so they cannot split a CSV record.
        ets_printf("%s", line);
        if (reported_drops != s_queue_drops) {
            reported_drops = s_queue_drops;
            ESP_LOGW(TAG, "CSI queue full; dropped=%" PRIu32, reported_drops);
        }
    }
    free(line);
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

    s_csi_queue = xQueueCreate(CSI_QUEUE_LENGTH, sizeof(csi_record_t));
    if (s_csi_queue == NULL) {
        ESP_LOGE(TAG, "unable to allocate CSI queue");
        abort();
    }

    wifi_init();
    espnow_init();
    wifi_csi_init();
    ESP_LOGI(TAG, "channel=%d transmitter=" MACSTR, CONFIG_CSI_CHANNEL, MAC2STR(s_transmitter_mac));
    if (xTaskCreate(csv_writer_task, "csi_csv", 8192, NULL, 4, NULL) != pdPASS) {
        ESP_LOGE(TAG, "unable to create CSV writer task");
        abort();
    }
}
