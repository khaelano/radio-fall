# Radio configuration

Operational settings now live in [`../radio.json`](../radio.json). Viewer,
collector, provisioning, relay control and gateway benchmark load that file
by default. See the [configuration guide](../../docs/radio-configuration.md).

The separate inventories, sensing profiles, BLE policy and ESP-NOW trial
presets have been removed. Historical experiment reports describe their
original filenames; their recordings retain resolved settings and fingerprints,
and tracked presets remain available in Git history. Collection protocols and
scenario manifests under `configs/collection/` define experiment labels and
remain separate from hardware settings.
