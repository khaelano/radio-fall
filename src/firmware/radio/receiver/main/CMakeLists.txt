idf_component_register(SRCS "app_main.c" "ble_transport.c"
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES
                           bt
                           common
                           esp_driver_usb_serial_jtag
                           esp_event
                           esp_netif
                           esp_timer
                           esp_wifi
                           nvs_flash
                           vfs)
