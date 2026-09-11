# ESP32 CSI firmware

These are independent ESP-IDF projects for the first one-transmitter,
one-receiver prototype. Both projects target the original ESP32 and use
channel 11, HT20, and a 921600-baud USB console by default.

## Build and flash

Activate the installed ESP-IDF environment, then build each project:

```sh
source /home/khaelano/.espressif/tools/activate_idf_v6.1.sh
cd src/firmware/transmitter
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash

cd ../receiver
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB1 flash
```

The transmitter MAC is configured as `1a:00:00:00:00:00`; the receiver
filters CSI to that MAC. Change `CSI_SEND_MAC` in each project's menuconfig
if the transmitter identity is changed. The receiver prints the classic
Espressif `CSI_DATA` CSV stream for the Python processor. Rows are assembled
before writing, and queue drops are reported as warnings after complete rows.

The default 100 Hz text stream is close to the practical capacity of a
921600-baud console for the largest CSI payloads. If the receiver reports
queue drops, lower `CSI_PACKET_RATE` (or reduce the enabled CSI fields) before
increasing the sensing rate.

The project defaults to a 4 MB flash image and restricts channels to the
world-safe 1–11 range. Generated `sdkconfig` files are local build state; run
`idf.py set-target esp32` in a fresh checkout to apply the defaults.
