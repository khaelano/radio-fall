idf_component_register(SRCS "radio_profile.c" "radio_board.c"
                       INCLUDE_DIRS "include"
                       REQUIRES nvs_flash
                       PRIV_REQUIRES esp_driver_gpio)
