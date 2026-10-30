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

## Power and sensing rate

Both projects default to an 80 MHz maximum CPU frequency with ESP-IDF dynamic
frequency scaling initialized at startup (`CONFIG_PM_ENABLE` and
`CONFIG_PM_DFS_INIT_AUTO`). This lets ESP-IDF lower the CPU clock toward the
crystal frequency when driver locks permit it. The transmitter previously
inherited the target's default CPU frequency without power management; this
change aligns it with the receiver defaults. Active Wi-Fi can hold a driver
lock at 80 MHz, so lower idle clocks are not guaranteed during collection.
It does not change the 100 Hz per-peer transmission schedule, HE20 MCS0 rate,
raw CSI payload, or USB batching.

Automatic light sleep is not enabled by this configuration. Wi-Fi remains in
`WIFI_PS_NONE`, and receivers continue promiscuous CSI acquisition. ESP-NOW
receive windows would require coordinated wake timing, while light sleep can
interrupt native USB Serial/JTAG. See Espressif's
[power management guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c5/api-reference/system/power_management.html),
[ESP-NOW guide](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c5/api-reference/network/esp_now.html),
and [USB sleep limitations](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c5/api-guides/usb-serial-jtag-console.html#sleep-mode-considerations).

Existing local `sdkconfig` files override `sdkconfig.defaults`. To apply the
power settings to an existing build, run `idf.py menuconfig` in the transmitter
project and enable power management, automatic DFS initialization, and the
80 MHz default CPU frequency, then rebuild. For a clean build configuration,
use a separate configuration file and build directory:

```sh
# Run from src/firmware/radio/transmitter (use esp32c6 for a C6 board).
idf.py -D IDF_TARGET=esp32c5 -D SDKCONFIG=build-power/sdkconfig \
    -B build-power build
```

The generated configuration stays inside the ignored build directory. Build
success alone does not establish power savings or delivered CSI rate. Before
adopting the image for collection, compare the old and new firmware on the same
board, supply, profile, receiver placement, host, and recording duration:

1. Measure average supply power and energy over equal recording intervals,
   including startup separately. Account for the board regulator and LEDs.
2. Compare transmitter attempts and immediate/asynchronous failures, plus each
   receiver's sensing sequence gaps, queue drops, and received sensing packets
   per second. Count the expected transmitter MAC and HE format separately
   from ambient frames. Two peers produce 200 send attempts/s for 100 Hz each.
3. Compare packet interval distributions and long gaps, USB errors, and clock
   synchronization quality. Repeat with both receivers active under the
   intended radio conditions, including movement and obstructed paths.
4. Choose an acceptable loss and timing budget before the comparison. If
   80 MHz cannot sustain it, try 160 MHz with DFS before reducing sensing rate.

No hardware power or throughput comparison has been recorded for this change.
Reducing transmit power is a separate experiment: it can reduce link margin
and CSI amplitude, so it needs packet-loss and signal-quality validation.
