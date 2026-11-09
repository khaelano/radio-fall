idf_component_register(SRCS "radio_profile.c" "radio_board.c" "gateway_io.c" "wireless_link.c"
                            "reference_relay.c" "uart_reference.c"
                       INCLUDE_DIRS "include"
                       REQUIRES nvs_flash esp_wifi esp_timer esp_driver_usb_serial_jtag
                       PRIV_REQUIRES esp_driver_gpio esp_driver_uart bt mbedtls)
