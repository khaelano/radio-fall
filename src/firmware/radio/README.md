# ESP32-C5/C6 BLE CSI firmware

This branch uses ESP-NOW HE20 MCS0 sensing and BLE receiver-to-laptop CSI.
The transmitter keeps native USB Serial/JTAG for provisioning, start/stop,
clock exchanges, round logs, and diagnostics. Receivers use USB only for
flashing, provisioning, and diagnostics. There is no USB CSI writer or gateway.

ESP32-C6 and mixed C5/C6 inventories require 2.4 GHz. A 5 GHz profile requires
C5 on every board. Profiles select an integer sensing rate from 50 to 100 Hz;
the initial C6 profile is `indonesia_2g_ch6_80hz.json`.

## Build and provision

Use ESP-IDF 6.1 and the [build/flash procedure](../../../docs/ble-transport.md#firmware-and-board-setup).
Both projects now default to BLE mode, including NimBLE/coexistence and the
larger receiver application partition. Use a clean target-specific build and
configuration directory. Old `build/` images may still contain USB firmware.

Before provisioning, boards expose USB identity/status but do not start sensing.
`csi-radio-provision --sequential` supports one connected board at a time using
the same complete inventory and profile. Committing a profile acknowledges the
write and reboots the board so receiver order and BLE identity reload together.
Provisioning remains in NVS across ordinary flashes; do not erase flash.

## XIAO ESP32-C6 antenna setup

Select `CSI_BOARD_XIAO_ESP32C6` for Seeed XIAO boards. GPIO3 is driven low to
activate the RF switch; GPIO14 selects built-in (low) or external (high).
The receiver can use its built-in ceramic antenna without an external antenna.
The generic board setting leaves GPIOs untouched.

Append `sdkconfig.defaults.xiao_esp32c6` to the default-file list for built-in
mode. A transmitter with an attached external antenna can instead use
`sdkconfig.defaults.xiao_esp32c6_external`. Board/antenna selection is exposed in
USB and BLE status. After changing Kconfig definitions, run `idf.py reconfigure`.
See the [board manufacturer's guide](https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/#hardware-overview).

## Transmitter power and timing

Both roles use an 80 MHz maximum CPU frequency with automatic dynamic frequency
scaling. The transmitter's initial maximum Wi-Fi transmit power is 44 quarter-dBm
(11 dBm), set after Wi-Fi starts. The driver reports the quantized value in USB
status. Change `CONFIG_CSI_TX_POWER_QUARTER_DBM` through `idf.py menuconfig` if
range testing requires a different value. Lower RF power changes CSI amplitude
and link margin; record the setting with every hardware comparison.

The transmitter stops its Wi-Fi radio between runs. A valid `CBGO` command starts
sensing; `CBST` stops it. Valid clock/control exchanges renew a 3-second host
lease. If exchanges cease, sensing stops and the transmitter task shuts Wi-Fi
down. A later clock exchange alone cannot restart sensing. The host must start a
new run explicitly. The sensing rate and fixed receiver-slot order are retained. Each peer has one
pending send at most. Failed MAC acknowledgements impose 100 ms retry spacing;
submission order rotates so an absent early peer cannot starve later slots.
Round telemetry records which sends were accepted; acceptance is not proof
of RF delivery.
Receivers keep capturing during valid upload windows; automatic light sleep is
not enabled. Temperature and power reduction have not been measured.

## Diagnosing resets or apparent power loss

USB discovery and BLE identity/status report `reset_reason` and `uptime_ms`.
Transmitter status also reports `radio_active` and `tx_power_quarter_dbm`.
A changing boot identity, restarting uptime, or watchdog/panic/brownout reason
provides evidence of a reset. A device that stops enumerating on USB may have
lost power, disconnected, or reset; disappearance alone does not identify the
cause. Firmware cannot report while its supply is off.

If using a USB power bank, check its low-current auto-off behavior independently
with the actual bank and board load. Do not infer thermal shutdown from a dark
LED. Use a stable supply for firmware and RF validation. Keep reset diagnostics
separate from measured temperature and supply-current results.

Sensing protocol v3 adds CRC32 over the 84-byte scheduling header. Receivers
snapshot and validate it before updating sequence/grant state. Live acquisition
requires v3 on both roles; reflash all boards after this protocol upgrade.
BLE ACKs use write commands, and the writer wakes on notification completion.
Dynamic Wi-Fi RX buffers are capped at 32 to preserve BLE memory headroom.

All runtime USB telemetry is framed and shares a write mutex. Raw ROM printing
is excluded from transmitter statistics; it previously corrupted clock exchanges.
The initial hardware preflight verified 40 clock exchanges after that fix. CSI
quality, sustained four-receiver BLE behavior, and thermal behavior remain to be
measured. Full protocol and benchmark instructions are in [BLE transport](../../../docs/ble-transport.md).
