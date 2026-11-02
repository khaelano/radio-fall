idf_component_register(SRCS "app_main.c" "gateway_transport.c"
                       INCLUDE_DIRS "."
                       PRIV_REQUIRES
                           common
                           esp_driver_usb_serial_jtag
                           esp_event
                           esp_netif
                           esp_timer
                           esp_wifi
                           nvs_flash
                           vfs)
