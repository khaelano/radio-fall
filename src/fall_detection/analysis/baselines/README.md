# Baselines from prior research

Each subpackage adapts one published Wi-Fi fall detector to the four ESP32-C5
receivers. They are comparison points, not our sequence approach, which lives
in `../sequence/` with its notebooks.

| Package | Paper | Guide |
| --- | --- | --- |
| [`wifall/`](wifall/) | WiFall (2017) | [docs/baselines/wifall.md](../../../../docs/baselines/wifall.md) |
| [`falldefi/`](falldefi/) | FallDeFi (2017) | [docs/baselines/falldefi.md](../../../../docs/baselines/falldefi.md) |

Shared by both:

- `_recorded_attempts.py`: reads accepted, labelled attempts from closed
  sessions as 120 Hz amplitude epochs and fills short gaps.
- `_grouped_holdout.py`: the grouped train/test split (by attempt, session or
  participant) and the binary metrics.

Run a baseline as a module, for example:

```bash
uv run python -m fall_detection.analysis.baselines.falldefi --help
```

Outputs belong under `artifacts/baselines/<name>/<run>/`, tracked with
`uv run dvc add`. Tests are in `tests/analysis/baselines/`.
