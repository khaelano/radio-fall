#include "sdkconfig.h"
#if CONFIG_CSI_BLE_SCHEDULER
#include "ble_transmitter.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
static const csi_radio_profile_t *profile;
static csi_ble_config_t configuration;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static uint32_t boot, generation, log_drops;
static bool configured, running;
static uint64_t last_control_us;
static QueueHandle_t log_queue;
static TaskHandle_t waiter;
static esp_timer_handle_t timer;
static bool (*write_frame)(uint8_t, const uint8_t *, size_t);

static void wake(void *arg) { (void)arg; if (waiter) xTaskNotifyGive(waiter); }
void csi_ble_tx_wait(uint64_t deadline)
{
    waiter = xTaskGetCurrentTaskHandle();
    while ((uint64_t)esp_timer_get_time() < deadline) {
        uint64_t now = esp_timer_get_time();
        if (now >= deadline) break;
        uint64_t delay = deadline - now;
        esp_timer_stop(timer);
        if (delay) esp_timer_start_once(timer, delay);
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(100));
    }
}
static void logger(void *arg)
{
    (void)arg; uint8_t payload[51];
    for (;;) if (xQueueReceive(log_queue, payload, portMAX_DELAY)) {
        if (!write_frame(CSI_SERIAL_BLE_ROUND, payload, sizeof(payload))) {
            portENTER_CRITICAL(&lock); ++log_drops; portEXIT_CRITICAL(&lock);
        }
    }
}
void csi_ble_tx_init(const csi_radio_profile_t *p,
                    bool (*writer)(uint8_t, const uint8_t *, size_t))
{
    profile = p; write_frame = writer; boot = esp_random();
    log_queue = xQueueCreate(128, 51);
    const esp_timer_create_args_t args = {.callback=wake, .name="csi_round"};
    ESP_ERROR_CHECK(esp_timer_create(&args, &timer));
    if (!log_queue || xTaskCreate(logger, "csi_round_log", 4096, NULL, 3, NULL) != pdPASS) abort();
}
size_t csi_ble_tx_control(const uint8_t *p, size_t n, uint8_t *response)
{
    if (n == 16 && !memcmp(p, "CBCK", 4)) {
        uint64_t t2 = esp_timer_get_time();
        memcpy(response, p, 16);
        csi_clock_write_u64(response+16, t2);
        csi_clock_write_u64(response+24, esp_timer_get_time());
        csi_clock_write_u32(response+32, boot);
        portENTER_CRITICAL(&lock);
        last_control_us = t2;
        csi_clock_write_u32(response+36, log_drops);
        portEXIT_CRITICAL(&lock);
        return 40;
    }
    bool ok = false;
    if ((n == CSI_BLE_CONFIG_SIZE || n == CSI_BLE_CONFIG_MAX_SIZE) && !memcmp(p, "CBLC", 4)) {
        csi_ble_config_t next;
        if (csi_ble_config_decode(p, n, &next) && next.rate_hz == profile->nominal_rate_hz &&
            next.receiver_count == profile->receiver_count &&
            next.inventory_crc == csi_serial_crc32((const uint8_t *)profile->receiver_macs, 6*profile->receiver_count)) {
            portENTER_CRITICAL(&lock);
            configuration = next; configured = true; running = false; ++generation;
            last_control_us = esp_timer_get_time();
            portEXIT_CRITICAL(&lock);
            ok = true;
        }
    } else if (n == 12 && (!memcmp(p, "CBGO", 4) || !memcmp(p, "CBST", 4))) {
        portENTER_CRITICAL(&lock);
        if (configured && csi_clock_read_u64(p+4) == configuration.run_id) {
            bool start = !memcmp(p, "CBGO", 4);
            if (start && !running) ++generation;
            running = start; ok = true;
            last_control_us = esp_timer_get_time();
        }
        portEXIT_CRITICAL(&lock);
    }
    memcpy(response, ok ? "ok" : "error", ok ? 2 : 5);
    return ok ? 2 : 5;
}
bool csi_ble_tx_snapshot(csi_ble_config_t *c, uint32_t *b, uint32_t *g)
{
    portENTER_CRITICAL(&lock);
    uint64_t now = esp_timer_get_time();
    if (running && now - last_control_us >= (uint64_t)CONFIG_CSI_CONTROL_TIMEOUT_MS * 1000) {
        running = false;
    }
    *c = configuration; *b = boot; *g = generation;
    bool active = running;
    portEXIT_CRITICAL(&lock);
    return active;
}
void csi_ble_tx_round(const csi_ble_config_t *c, uint32_t b, uint32_t sequence,
    uint64_t enqueue, uint64_t deadline, uint32_t result)
{
    uint8_t data[51]; memcpy(data, "CBRD", 4);
    csi_clock_write_u64(data+4, c->run_id); csi_clock_write_u32(data+12, b);
    csi_clock_write_u32(data+16, sequence); csi_clock_write_u64(data+20, enqueue);
    csi_clock_write_u64(data+28, deadline); csi_clock_write_u32(data+36, 1000000U/c->rate_hz);
    csi_clock_write_u32(data+40, result);
    portENTER_CRITICAL(&lock); csi_clock_write_u32(data+44, log_drops); portEXIT_CRITICAL(&lock);
    for (unsigned i = 0; i < 3; ++i)
        data[48+i] = csi_ble_config_owner(sequence+i, c);
    if (!xQueueSend(log_queue, data, 0)) {
        portENTER_CRITICAL(&lock); ++log_drops; portEXIT_CRITICAL(&lock);
    }
}
#endif
