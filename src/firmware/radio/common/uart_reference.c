#include "sdkconfig.h"
#include "uart_reference.h"

#if CONFIG_CSI_UART_REFERENCE
#include "serial_stream.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

static SemaphoreHandle_t write_lock;
static QueueHandle_t events;
static volatile bool active, fault;
static volatile uint32_t errors, received;
static wl_emit_t receiver;
static void *receiver_context;

bool uart_ref_enabled(void) { return true; }
bool uart_ref_faulted(void) { return fault; }
uint32_t uart_ref_errors(void) { return errors; }
uint32_t uart_ref_received(void) { return received; }
void uart_ref_session_active(bool value)
{
    active = value;
    /* The failed run has stopped. CRC/framing still validates every new frame;
     * lifetime error counters remain available to the host. */
    if (!value) fault = false;
}
static void failed(void) { ++errors; if (active) fault = true; }
bool uart_ref_send(uint8_t type, const uint8_t *p, size_t size)
{
    if (fault || !write_lock ||
        xSemaphoreTake(write_lock, pdMS_TO_TICKS(5)) != pdTRUE) return false;
    static uint8_t raw[CSI_SERIAL_MAX_RAW_SIZE], frame[CSI_SERIAL_MAX_FRAME_SIZE];
    size_t n = csi_serial_encode_frame(type, p, size, raw, sizeof(raw), frame, sizeof(frame));
    size_t free_bytes = 0;
    /* Never wait for a congested UART ring while sensing is scheduled. */
    bool ok = n && uart_get_tx_buffer_free_size(UART_NUM_0, &free_bytes) == ESP_OK &&
              free_bytes >= n && uart_write_bytes(UART_NUM_0, frame, n) == (int)n;
    xSemaphoreGive(write_lock);
    if (!ok) failed();
    return ok;
}
static void read_uart(void *arg)
{
    (void)arg;
    static csi_serial_decoder_t decoder;
    uint8_t chunk[512]; uart_event_t event;
    for (;;) {
        while (xQueueReceive(events, &event, 0) == pdTRUE) {
            if (event.type == UART_FIFO_OVF || event.type == UART_BUFFER_FULL ||
                event.type == UART_PARITY_ERR || event.type == UART_FRAME_ERR ||
                event.type == UART_BREAK) {
                failed(); memset(&decoder, 0, sizeof(decoder));
                uart_flush_input(UART_NUM_0);
            }
        }
        size_t available = 0;
        uart_get_buffered_data_len(UART_NUM_0, &available);
        size_t request = available ? (available < sizeof(chunk) ? available : sizeof(chunk)) : 1;
        int n = uart_read_bytes(UART_NUM_0, chunk, request, pdMS_TO_TICKS(1));
        for (int i = 0; i < n; ++i) {
            uint8_t type; const uint8_t *payload; size_t size;
            int result = csi_serial_feed(&decoder, chunk[i], &type, &payload, &size);
            if (result < 0) failed();
            if (result > 0 && !fault) {
                ++received; receiver(type, payload, size, receiver_context);
            }
        }
    }
}
void uart_ref_init(wl_emit_t receive, void *context)
{
    receiver = receive; receiver_context = context;
    write_lock = xSemaphoreCreateMutex();
    if (!write_lock || !receiver) abort();
    uart_config_t config = {.baud_rate = CONFIG_CSI_REFERENCE_UART_BAUD,
        .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT};
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 16384, 16384, 64, &events, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, CONFIG_CSI_REFERENCE_UART_TX,
        CONFIG_CSI_REFERENCE_UART_RX, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    if (xTaskCreate(read_uart, "csi_uart_ref", 6144, NULL, 4, NULL) != pdPASS) abort();
}
#else
void uart_ref_init(wl_emit_t f, void *c) { (void)f; (void)c; }
bool uart_ref_send(uint8_t t, const uint8_t *p, size_t n)
{ (void)t; (void)p; (void)n; return false; }
void uart_ref_session_active(bool value) { (void)value; }
bool uart_ref_enabled(void) { return false; }
bool uart_ref_faulted(void) { return false; }
uint32_t uart_ref_errors(void) { return 0; }
uint32_t uart_ref_received(void) { return 0; }
#endif
