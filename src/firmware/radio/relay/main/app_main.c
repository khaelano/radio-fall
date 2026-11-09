#include "sdkconfig.h"
#if !CONFIG_IDF_TARGET_ESP32C6 || !CONFIG_CSI_UART_REFERENCE || !CONFIG_CSI_ESPNOW_UART_RELAY
#error "The UART companion requires C6, native UART and the ESP-NOW reference relay"
#endif
#include <stdio.h>
#include "reference_relay.h"
#include "uart_reference.h"
#include "gateway_io.h"
#include "radio_board.h"
#include "driver/usb_serial_jtag.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include "freertos/task.h"

static uint8_t mac[6];
static uint64_t active_run;
static bool active, stop_sent;
static QueueHandle_t usb_commands;
static uint64_t last_metrics;
static void from_uart(uint8_t type, const uint8_t *p, size_t size, void *context)
{
    (void)context;
    if (rr_paired() && !rr_faulted() && !rr_send(type, p, size)) rr_fail("uart_ingress");
}
static bool to_uart(uint8_t type, const uint8_t *p, size_t size, void *context)
{
    (void)context;
    if (type != CSI_SERIAL_TYPE_DISCOVER_REQUEST && type != CSI_SERIAL_TYPE_PROFILE_STAGE &&
        type != CSI_SERIAL_TYPE_PROFILE_COMMIT && type != GW_CONTROL) return false;
    if (!uart_ref_send(type, p, size)) return false;
    if (type == GW_CONTROL && size == 12) {
        if (!memcmp(p, "CGGO", 4)) {
            active_run = csi_clock_read_u64(p + 4); active = true; stop_sent = false;
        } else if (!memcmp(p, "CGSP", 4)) active = false;
        rr_session_active(active); uart_ref_session_active(active);
    }
    return true;
}
static void status(void)
{
    char p[1000];
    int size = snprintf(p, sizeof(p),
        "{\"role\":\"relay\",\"target\":\"esp32c6\",\"mac\":\"" MACSTR "\","
        "\"firmware_version\":\"1\",\"protocol_version\":3,\"relay_version\":1,"
        "\"relay_transport\":\"espnow_uart\",\"relay_recovery_version\":1,\"relay_paired\":%s,\"relay_ready\":%s,"
        "\"relay_fault\":%s,\"relay_failure_reason\":\"%s\",\"relay_drops\":%lu,"
        "\"relay_peer_changes\":%lu,\"relay_retries\":%lu,\"relay_queued_bytes\":%u,"
        "\"configured\":%s,\"channel\":%u,\"uart_tx_gpio\":%u,\"uart_rx_gpio\":%u,"
        "\"uart_baud\":%u,\"uart_errors\":%lu,\"uart_received\":%lu,"
        "\"board\":\"%s\",\"antenna\":\"%s\",\"free_heap_bytes\":%lu}",
        MAC2STR(mac), rr_paired() ? "true" : "false", rr_ready() ? "true" : "false",
        rr_faulted() ? "true" : "false", rr_failure_reason(), (unsigned long)rr_drops(),
        (unsigned long)rr_peer_changes(), (unsigned long)rr_retries(), (unsigned)rr_queued_bytes(),
        active ? "true" : "false", (unsigned)rr_channel(), CONFIG_CSI_REFERENCE_UART_TX,
        CONFIG_CSI_REFERENCE_UART_RX, CONFIG_CSI_REFERENCE_UART_BAUD,
        (unsigned long)uart_ref_errors(), (unsigned long)uart_ref_received(),
        csi_board_name(), csi_board_antenna(), (unsigned long)esp_get_free_heap_size());
    if (size > 0 && size < sizeof(p)) gw_usb_write(CSI_SERIAL_TYPE_DEVICE_STATUS,
                                                   (const uint8_t *)p, size);
}
static void read_usb(void *arg)
{
    (void)arg;
    static gw_message_t message;
    for (;;) {
        size_t size;
        if (gw_usb_read(&message.source[0], message.data, &size)) {
            message.size = size;
            xQueueSend(usb_commands, &message, 0);
        }
    }
}
void app_main(void)
{
    csi_board_init(); ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    usb_serial_jtag_driver_config_t usb = {.tx_buffer_size = 4096, .rx_buffer_size = 4096};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    ESP_ERROR_CHECK(esp_netif_init()); ESP_ERROR_CHECK(esp_event_loop_create_default());
    wifi_init_config_t wifi = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi)); ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA)); ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N));
    ESP_ERROR_CHECK(esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW20));
    ESP_ERROR_CHECK(esp_wifi_set_country_code("ID", true));
    ESP_ERROR_CHECK(esp_wifi_set_channel(6, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    gw_io_init(); rr_init(0, mac, to_uart, NULL); uart_ref_init(from_uart, NULL);
    usb_commands = xQueueCreate(4, sizeof(gw_message_t));
    if (!usb_commands || xTaskCreate(read_usb, "relay_usb", 4096, NULL, 3, NULL) != pdPASS) abort();
    static gw_message_t message;
    for (;;) {
        if (xQueueReceive(usb_commands, &message, 0)) {
            uint8_t type = message.source[0];
            if (type == CSI_SERIAL_TYPE_DISCOVER_REQUEST) status();
            else if (type == WL_USB_PAIR) {
                bool ok = rr_pair(message.data, message.size);
                gw_usb_write(WL_USB_PAIR_ACK, (const uint8_t *)(ok ? "ok" : "error"), ok ? 2 : 5);
                if (ok) { vTaskDelay(pdMS_TO_TICKS(100)); esp_restart(); }
            }
        }
        while (xQueueReceive(gw_incoming(), &message, 0))
            rr_receive(message.source, message.data, message.size);
        rr_poll();
        uint64_t now = esp_timer_get_time();
        if (active && rr_ready() && now - last_metrics >= 1000000) {
            uint8_t metrics[RR_STATS_SIZE] = {'C','R','S','T'};
            wl_w32(metrics + 4, rr_queued_bytes());
            wl_w32(metrics + 8, rr_queue_peak());
            wl_w32(metrics + 12, rr_retries());
            wl_w32(metrics + 16, uart_ref_errors());
            wl_w32(metrics + 20, uart_ref_received());
            rr_send(RR_STATS_TYPE, metrics, sizeof(metrics));
            last_metrics = now;
        }
        if (uart_ref_faulted()) rr_fail("uart_fault");
        if (rr_faulted() && active && !stop_sent) {
            uint8_t stop[12]; memcpy(stop, "CGSP", 4); csi_clock_write_u64(stop + 4, active_run);
            stop_sent = uart_ref_send(GW_CONTROL, stop, sizeof(stop));
            /* The independent C5 control lease also stops sensing if UART fails. */
            active = false;
            rr_session_active(false); uart_ref_session_active(false);
        }
        /* This USB port is a setup/recovery interface. Unsolicited status
         * would fill its unread ring and stall the live radio loop. */
        vTaskDelay(1);
    }
}
