# Data layout

Raw recordings are immutable. `data/raw/` and the other capture directories are
git-ignored, so nothing here is published with the repository.

```text
data/
├── raw/
│   ├── sessions/<session-id>/       collector output, one directory per session
│   │   ├── session.json
│   │   ├── protocol.json
│   │   ├── events.jsonl
│   │   └── trials/<trial>/attempt_<n>/receivers/<rx>/csi.csv
│   └── receivers/<rx>/              ad-hoc captures written by the viewer
├── interim/                         extracted windows and features
├── annotations/                     reviewed labels
├── processed/                       model-ready dataset versions
├── splits/                          train, validation, and test assignments
└── experiments/                     engineering experiment outputs
```

Each CSI row is one sensing frame for one receiver. The same transmitted frame
appears once under every receiver that heard it; do not merge those rows, they
are the spatial diversity the experiment relies on.

## Pruning

`tools/prune_data.py` reports (and with `--apply`, removes) data the current
pipeline no longer uses:

```sh
python tools/prune_data.py                       # dry run, category totals
python tools/prune_data.py --verbose             # list every path
python tools/prune_data.py --apply               # delete the reported entries
python tools/prune_data.py --viewer-captures --keep-days 0 --apply
```

Categories:

- `empty-session` — session directories with zero CSI rows (aborted runs).
- `legacy-raw` — flat `data/raw/*.csv` captures from the pre-session workflow.
- `stale-model` — `data/models/yolo`, unused since the camera comparator was removed.
- `viewer-capture` — ad-hoc `data/raw/receivers/` captures (opt-in only).

Files modified within `--keep-days` (default 7) are never touched.
