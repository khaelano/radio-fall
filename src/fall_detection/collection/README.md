# USB radio collection

Collection uses the radio as the primary detector. The transmitter and every
configured receiver are provisioned over USB before a session; the transmitter
may then be disconnected. The operator confirms the planned action during the
action interval and accepts the attempt after recovery.

```sh
uv run csi-radio-discover
uv run csi-radio-provision \
  --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json
uv run fall-collection \
  --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json \
  --protocol configs/collection/fall_v1.json \
  --output-dir data/raw/sessions
```

The two configuration files are read-only session inputs. Changing band or
channel requires rerunning provisioning. A 2.4 GHz profile may mix ESP32-C5
and ESP32-C6 boards. A 5 GHz profile requires C5 for the transmitter and all
receivers and uses only non-DFS channels accepted by the Indonesia country
table.

The collector discovers `/dev/ttyACM*` devices by firmware-reported MAC and
inventory ID, so hub port renumbering and reconnects do not change receiver
assignment. A receiver is healthy only when it reports the expected target,
active profile fingerprint, current USB stream, and clock state. Loss of any
required receiver invalidates an active attempt.

New attempts use artifact schema 2:

```text
attempt.json
receivers/<receiver-id>/csi.csv
receivers/<receiver-id>/radio_timing.csv
receivers/<receiver-id>/usb_clock_sync.csv
```

The session manifest records the inventory, selected profile, fingerprint,
firmware targets, USB bindings, and reconnection events. Only CSI, timing, and
clock-sync data are part of this collection path.
