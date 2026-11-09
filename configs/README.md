# Configuration

The operational radio setup lives in one file:

- [`radio.json`](radio.json) contains the verified hardware inventory, stable
  USB paths, sensing profile, upload policy and reference link. All live radio
  commands load it by default; `--config` selects another setup.
- `collection/` contains activity protocols and scenario definitions, selected
  per collection session with `--protocol`.
- `experiments/` is reserved for named evaluation conditions.

See the [configuration guide](../docs/radio-configuration.md). The checked-in
by-id USB paths identify the current boards; override connection paths on another
host. Keep credentials, pairing keys and participant identifiers out of these files.
