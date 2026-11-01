#include "sdkconfig.h"
#include "radio_board.h"

#if CONFIG_CSI_BOARD_XIAO_ESP32C6
#include "driver/gpio.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

void csi_board_init(void)
{
#if CONFIG_CSI_BOARD_XIAO_ESP32C6
    /* Seeed XIAO C6: active-low switch enable, then antenna selection. */
    ESP_ERROR_CHECK(gpio_set_direction(GPIO_NUM_3, GPIO_MODE_OUTPUT));
    ESP_ERROR_CHECK(gpio_set_level(GPIO_NUM_3, 0));
    vTaskDelay(pdMS_TO_TICKS(100));
    ESP_ERROR_CHECK(gpio_set_direction(GPIO_NUM_14, GPIO_MODE_OUTPUT));
    ESP_ERROR_CHECK(gpio_set_level(GPIO_NUM_14,
#if CONFIG_CSI_XIAO_EXTERNAL_ANTENNA
                                 1
#else
                                 0
#endif
                                 ));
#endif
}

const char *csi_board_name(void)
{
#if CONFIG_CSI_BOARD_XIAO_ESP32C6
    return "xiao_esp32c6";
#else
    return "generic";
#endif
}

const char *csi_board_antenna(void)
{
#if CONFIG_CSI_BOARD_XIAO_ESP32C6
#if CONFIG_CSI_XIAO_EXTERNAL_ANTENNA
    return "external";
#else
    return "builtin";
#endif
#else
    return "board_default";
#endif
}
