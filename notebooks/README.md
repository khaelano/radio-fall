# Notebooks

Current notebooks live in `latest/`. Start with the shared exploration and
preprocessing path, then use the dedicated input and training experiments as
needed:

Run history, including metrics, splits, checkpoints, normalizers, and ONNX
exports, lives under `artifacts/notebooks/<notebook-name>/<run-id>/`.
The latest verified ONNX bundles are published separately to
`artifacts/model/<model-name>/`. These directories are versioned independently
with `artifacts/notebooks.dvc` and `artifacts/model.dvc`; their contents are
excluded from Git. Recordings and reusable derived datasets remain in `data/`.

- `01_exploration.ipynb` explores session data and capture quality.
- `01_01_amplitude_exp.ipynb` and `01_02_phase_exp.ipynb` compare amplitude
  and phase inputs.
- `01_03_amplitude_spectral.ipynb` compares spectrograms of the squared
  difference, the signed difference and the Hampel-filtered amplitude, from
  the arrays staged by `02_preprocess`.
- `02_preprocess.ipynb` directly defines dataset selection, filtering, squared
  differences, cue labels, windows, exports, and stage figures. Its
  `EXPORT_VARIANTS` also write alternative signals for the same windows to
  `amplitude_sequence/<rate>hz-<variant>/`; `filtered_amplitude` is the
  Hampel-filtered amplitude without difference or log1p, and
  `tone_mean_log_ratio` is one value per receiver: `log1p(1000 · x)` of the
  mean over tones of the squared log-amplitude change.
  `quiet_floor_squared_difference` is the default signal minus each session's
  per-tone mean over its still samples (`quiet_floor.npy` in each export).
  `lag_stack_squared_difference` holds the squared amplitude change over 1,
  2, 4 and 8 samples per tone (`[time, 4, 980]`), a coarse frequency view;
  it is about 19 GB and off by default.
  Its last step writes `main_bursts.parquet` beside each default export: the
  main motion burst of every fall segment, for burst training labels.
- `03_training.ipynb` runs PyTorch sequence models on CPU or NVIDIA
  CUDA, with independent pilot and full-data training sections. Besides the
  CNN, LSTM, GRU and tone-pool models, it defines the tiny energy models
  (`tiny_tcn1`, `tiny_tcn3`, `tiny_cnn3`), which average the default input
  over tones and receivers inside the model. Its final cell
  exports available checkpoints to ONNX and verifies logits with ONNX Runtime.
  It also saves each model's per-window test predictions for the comparison.
  `REPRESENTATION` selects the default export or a variant and is recorded in
  the run manifest; variant models are not copied to `artifacts/model/`,
  because the live detector computes only the default signal.
  Training inputs come from a GPU segment cache, else the same segment cache
  in RAM (`input_cache_gib`), else a RAM window cache or disk streaming.
  `POSITIVE_LABELS = "burst"` keeps only training and validation fall windows
  whose middle half holds the main burst peak; test windows are unchanged.
  `HELD_OUT_SESSION` tests on every attempt of one dataset, or of a tuple such
  as `("akmal", "continuous_non_fall")`, instead
  of a random attempt share (`hold_out_dataset`); such runs are evaluation runs
  and are not copied to `artifacts/model/` either. Datasets in `KEEP_SPLIT`
  (default `continuous_non_fall`) keep their random split in a holdout;
  `KEEP_SPLIT = ()` moves their test attempts into training. 04–06 select
  the 03 run by both settings. Prefer it for comparisons:
  random attempt splits are confounded by the equipment-ordered protocol
  ([report](../docs/reports/generalization-2026-11-22.md)).
- `04_wifall.ipynb` and `05_falldefi.ipynb` run the WiFall and FallDeFi
  baselines ([guides](../docs/baselines/)) on the attempt split of a
  `03_training` run: validation attempts join training, and the test attempts
  are the sequence models' test attempts.
- `06_comparison.ipynb` collects the newest default-representation 03 run for
  its `HELD_OUT_SESSION` and the newest 04 and 05 runs fitted on that run's
  split (matched by split hash; set the same `HELD_OUT_SESSION` and `KEEP_SPLIT` in 03–06), and scores every approach on
  its own unit and per attempt (an attempt is predicted a fall when any of its
  units is). `EXTRA_TRAINING_RUNS` adds sequence runs on the same windows and
  attempts, such as a representation variant.

`SAMPLE = True` in `02_preprocess` and `03_training` limits a run to the Akmal
session (9 November 13:15) and, in training, to 2 s windows with automatic
device choice, so the chain 02 → 06 can be smoke-tested on a laptop. Set it to
`False` for full runs on the training device.

For CPU PyTorch, run `uv sync --inexact --extra analysis --extra train`. For the
CUDA 13.0 wheel on Linux or Windows, use
`uv sync --inexact --extra analysis --extra cuda` instead. The `train` and `cuda`
extras select different PyTorch wheels and cannot be enabled together. Restart the project notebook kernel after switching wheels.
Set `DEVICE = "cuda"` to require an available NVIDIA GPU, or use `"auto"` to
select CUDA when available and CPU otherwise. A compatible NVIDIA GPU and driver
are required for CUDA. The notebook prints and records the device actually used.
Reduce `BATCH_SIZE` for the pilot or the `batch_size` in each model's settings
for a full run if GPU memory is insufficient.

Both the `train` and `cuda` extras include the ONNX export packages (`onnx`,
`onnxruntime`, `onnxscript`). The final notebook
cell writes models, matching training normalizers, and an input/output manifest
under the run’s `onnx/<mode>/<model-name>/` directory and copies the latest
verified bundle to `artifacts/model/<model-name>/`. Inputs are prepared
float32 sequences, with a dynamic batch axis (1–128) and fixed window/feature
dimensions; outputs are fall logits. Preprocessing and normalization are not embedded in the
graphs. The cell verifies batch sizes 1 and 2 against PyTorch before publishing
each model. Set `ONNX_RUN` to an earlier `artifacts/notebooks/03_training/<run-id>/`
to export its matching model bundle. Refresh model versions with
`uv run dvc add artifacts/notebooks artifacts/model` after training/exporting.
Export uses `dynamo=True` (the `torch.export`-based exporter), opset 18, and
embedded weights. The `train` extra includes ONNX Script for this exporter.

Experiment procedures and scientific settings live in the notebooks. Shared
readers, native signal operations, alignment primitives, storage, and training
input validation live in `src/fall_detection/` and are tested under `tests/`.
`03_training.ipynb` is the single implementation of the sequence model experiment;
the separate PyTorch command-line trainer has been removed. The phase notebook
also contains the optional burst measurement definition.
These notebooks investigate activity phases and cue-labelled falls;
they do not replace the separate experimental live fall detector.

Exploration and preprocessing use `storage_resolve_source` to select the archive
in `data/raw/sessions/` through the shared analysis loaders. Derived Parquet caches remain under `data/interim/`.
Cache rebuilds use temporary analysis-only extraction, which is removed after
conversion. Training consumes the windows generated by preprocessing.

Retired experiment notebooks and their generated outputs have been removed.
Historical model results are summarized in
[`docs/reports/fall-model-pilots.md`](../docs/reports/fall-model-pilots.md).
The detector uses an exported model from `data/models/phase_random20_v1/` when
that local, Git-ignored bundle is available.
