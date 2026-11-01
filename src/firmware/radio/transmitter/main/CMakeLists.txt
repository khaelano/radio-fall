idf_component_register(SRCS "app_main.c" "ble_transmitter.c"
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES
                           esp_driver_usb_serial_jtag
                           common
                           esp_event
                           esp_netif
                           esp_timer
                           esp_wifi
                           nvs_flash
                           vfs)
