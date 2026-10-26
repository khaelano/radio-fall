# ESP32-C5/C6 radio firmware

The transmitter and receiver are independent ESP-IDF projects sharing the
profile and USB framing component. They use ESP-NOW for the sensing link and
native USB Serial/JTAG for provisioning and receiver-to-laptop CSI batches.
The on-air profile is fixed at HE20 MCS0, 20 MHz, and 100 Hz; only band and
primary channel are selectable.

## Build

With ESP-IDF 6.1 or newer, build each target explicitly:

```sh
cd src/firmware/radio/transmitter
idf.py set-target esp32c5   # or esp32c6
idf.py build

cd ../receiver
idf.py set-target esp32c5   # or esp32c6
idf.py build
```

Before provisioning, a board reports discovery/status frames over USB but does
not start Wi-Fi, transmit sensing packets, or acquire CSI. The host stages the
validated profile on every expected board, then commits and reboots them. A
5 GHz commit is rejected by C6 at both the host and firmware capability gates;
2.4 GHz profiles may mix C5 and C6.

The receiver's only data output is a CRC-protected COBS-framed binary stream.
Frames contain device status, CSI batches, and sequence/boot counters. Logs are
kept outside the framed stream. The USB control protocol includes discovery,
profile stage/commit, status verification, and clock-sync message types.

The Indonesia country code is applied before selecting the profile channel.
DFS channels are rejected in the shared profile validator, and the profile is
persisted in NVS so the transmitter can be untethered during collection.
