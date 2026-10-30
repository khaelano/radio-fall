# Data layout

Raw recordings are immutable. `data/raw/` and the other capture directories are
git-ignored, so nothing here is published with the repository. The complete
file-by-file reference is [`docs/dataset-format.md`](../docs/dataset-format.md);
this page is the short map.

```text
data/
├── raw/
│   ├── sessions/<session-id>/       collector output, one directory per session
│   │   ├── session.json
│   │   ├── protocol.json
│   │   ├── events.jsonl
│   │   ├── session_review.json      optional review overlay
│   │   └── trials/<trial>/attempt_<n>/receivers/<rx>/
│   │       ├── csi.csv
│   │       ├── radio_timing.csv
│   │       └── usb_clock_sync.csv
│   └── receivers/<rx>/              ad-hoc captures, not session bundles
├── archive/                         compressed obsolete material (local only)
├── interim/                         extracted windows and features
├── annotations/                     reviewed labels
├── processed/                       model-ready dataset versions
├── splits/                          train, validation, and test assignments
├── experiments/                     engineering experiment outputs
└── models/                          local model weights
```

The current session layout is **artifact schema 2** (receiver-split). Each CSI
row is one sensing frame for one receiver. The same transmitted frame appears
once under every receiver that heard it; do not merge those rows, they are the
spatial diversity the experiment relies on. Read `session.json` and
`attempt.json` for conditions and dispositions; the CSV `mac` column is the
source transmitter, not the receiver.

`data/raw/receivers/` contains standalone timestamped `csi_*.csv` and
`radio_timing_*.csv` captures. They share the CSV column formats but have no
session manifest, trial metadata, or review sidecar, and generally no clock
synchronization. Treat them as scratch data.

## Archive

Obsolete schema-1 sessions, pre-session flat captures, and the removed camera
model were archived before deletion on 2026-10-27. The archives and their
checksum manifests live in `data/archive/`:

- `legacy-20261027T123855Z.tar.zst` — 114 flat captures, 13 empty sessions, one
  camera-era session, and the YOLO model directory.
- `legacy-flat-timing-20261027T124235Z.tar.zst` — three flat
  `radio_timing_*.csv` captures.

Verify an archive with `sha256sum -c <archive>.sha256`, then restore with
`tar --zstd -xf <archive>.tar.zst` from the repository root. Restored schema-1
sessions are historical and are rejected by the current reader.

## Pruning

`tools/prune_data.py` reports (and with `--apply`, removes) data the current
pipeline no longer uses:

```sh
python3 tools/prune_data.py                       # dry run, safe defaults
python3 tools/prune_data.py --verbose             # list every path
python3 tools/prune_data.py --apply               # delete the reported entries
python3 tools/prune_data.py --viewer-captures --keep-days 0 --apply
```

Categories:

- `empty-session` — session directories with zero CSI rows (aborted runs).
- `legacy-session` — sessions whose artifact schema is not 2.
- `viewer-capture` — ad-hoc `data/raw/receivers/` captures (opt-in only).

Paths modified within `--keep-days` (default 7) are never touched, including
empty and legacy sessions. Archive before deleting if the material may be
needed for provenance.
