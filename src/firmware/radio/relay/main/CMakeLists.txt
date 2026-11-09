idf_component_register(SRCS "app_main.c" INCLUDE_DIRS "."
    PRIV_REQUIRES common esp_driver_usb_serial_jtag esp_event esp_netif
                  esp_timer esp_wifi nvs_flash)
