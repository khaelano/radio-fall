# Python package layout

`apps/` contains application entry points and presentation code:

- `collector/`: operator and performer interfaces and collection presenter.
- `csi_viewer/`: live CSI viewer entry point.
- `session_inspector/`: offline inspector; its Qt-free frame loading, review,
  export and video modules sit beside the `ui/` window, panels and workers.
- `detector/`: live detector interface and command; `calibration.py` sets its
  thresholds without Qt or inference.
- `common/`: dashboard widgets, display preparation (`rendering.py`), pacing,
  shared `--fps` option and Qt bootstrap used by several applications.

The other packages contain reusable functionality, listed from the bottom of
the dependency order up:

- `protocol/`: planned trials and scenarios (`model.py`, `loader.py`). Imports
  no other project package.
- `radio/`: radio settings, profiles, live delivery, record types, display
  buffers, provisioning and the Rust-backed `phase.py`. Imports no other
  project package.
- `session/`: the neutral session model (manifests, directory/archive reader,
  schema version). Imports `protocol`.
- `collection/`: collection workflow (controller, capture, resume, video).
  Imports `protocol`, `radio` and `session`.
- `analysis/`: shared data access (`session_frames.py`) and four groups:
  `preprocessing/` (shared amplitude kernels and loading), `sequence/` (our
  sequence approach: alignment, difference transforms, export and training
  inputs, driven by the notebooks), `baselines/` (adaptations of prior
  research: WiFall, FallDeFi) and `diagnostics/`. Imports `protocol`, `radio`
  and `session`.

`tests/test_architecture.py` enforces this order (`ALLOWED_DEPENDENCIES`);
adding a top-level package requires adding it there. Experimental
preprocessing, labels, plots, model definitions, and training procedures live
in `notebooks/latest/`.

The installed commands are defined in `pyproject.toml`. Each application can
also be run as a module, for example `python -m fall_detection.apps.collector`.

The processing architecture has three layers:

1. `src/native/radio_core/` handles USB ingestion, framing, packet decoding,
   and recording. Its `radio_signal` workspace crate provides numeric kernels
   and signal preprocessing.
2. The Python domain packages validate settings, manage collection and session
   state, query recordings, and coordinate analysis and inference.
3. `apps/` presents those capabilities through the desktop applications;
   `apps/common/` holds the widgets they share.

The Rust extension is built with the Python package; it is required by live
acquisition and native stream decoding.

The native crate layout follows the component-workspace approach used by
[Ruff](https://github.com/astral-sh/ruff/blob/main/Cargo.toml): reusable
components declare their dependencies, while the extension composes them.
