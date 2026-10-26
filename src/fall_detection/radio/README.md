# Radio acquisition and visualization

The receiver emits CRC-protected binary COBS frames over native USB
Serial/JTAG. The host binds each stream by receiver MAC and validates the
profile fingerprint before accepting CSI. UDP, processor-AP, receiver
ESP-NOW-return, and legacy serial-CSV paths are not part of collection.

Provision and inspect devices with:

```sh
uv run csi-radio-discover
uv run csi-radio-provision --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json
```

The viewer requires the same inventory and profile and shows per-receiver CSI
health plus a selectable CSI preview:

```sh
uv run csi-viewer \
  --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json
```

When more than one receiver is connected through the powered hub, use the
receiver selector in the dashboard or choose the initial preview explicitly:

```sh
uv run csi-viewer \
  --receiver-config configs/radio/receivers.json \
  --radio-profile configs/radio/profiles/indonesia_2g_ch6.json \
  --receiver-id rx-1
```

Each receiver keeps its own sequence, timestamp, phase, and loss counters;
switching the selector never combines streams from different boards.

The wire framing uses a versioned envelope, COBS delimiters, and CRC-32. The
receiver status frame carries role, target, MAC, firmware/protocol version,
active profile ID, and fingerprint. CSI batches carry sequence and boot
counters; the host rejects foreign receiver traffic, stale profiles, malformed
frames, and profile mismatches.

Build target-specific images with `idf.py set-target esp32c5` or `idf.py
set-target esp32c6` in each firmware project. Both targets support mixed 2.4
GHz deployments; only C5 supports the 5 GHz profile. The sensing link remains
HE20 MCS0, 20 MHz, and 100 Hz on every profile.
