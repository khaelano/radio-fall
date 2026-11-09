# Notebooks

The primary research workflow is in `latest/`:

1. `01_exploration.ipynb` explores session data and capture quality.
2. `02_preprocess.ipynb` prepares amplitude data and generates windows.
3. `03_training.ipynb` compares CNN, LSTM, GRU, and random forest models.

Reusable analysis code lives in `src/fall_detection/` and is tested under
`tests/`. These notebooks investigate activity phases; they do not replace the
separate experimental live fall detector.

`trash/` retains historical exploration notebooks, the two-receiver pilot,
transport replay, four-receiver CNN experiment, phase-shifted experiment, and
their shared helpers for review. Saved results and provenance are historical;
the relocated experiments require new preparation and training before evaluating
with changed code paths. The detector still loads its separately exported model
from `data/models/phase_random20_v1/`.
