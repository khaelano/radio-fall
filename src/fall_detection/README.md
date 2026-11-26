# Python package layout

`apps/` contains application entry points and presentation code:

- `live/` (`csi-live`): live CSI view with optional fall detection.
  `window.py` runs one engine at a time on the gateway: the CSI dashboard when
  no model is selected, the native detector otherwise. `detection.py` encodes
  the detector configuration and runs it headless without Qt;
  `detection_view.py` shows scores and previews; `calibration.py` sets the
  thresholds without Qt or inference.
- `sessions/` (`csi-sessions`): session browser and collection console.
  `window.py` adds recording to the inspector window. `collector/` holds the
  setup form, the run lifecycle (`run.py`), the presenter and the operator and
  performer views; `inspector/` holds the Qt-free frame loading, review, export
  and video modules beside its `ui/` window, panels and workers.
- `common/`: dashboard widgets, display preparation (`rendering.py`), pacing,
  shared `--fps` option and Qt bootstrap used by both applications.

The other packages contain reusable functionality, listed from the bottom of
the dependency order up:

- `protocol/`: planned trials and scenarios (`model.py`, `loader.py`) and
  revisions of the remaining queue during recording (`revision.py`). Imports
  no other project package.
- `radio/`: radio settings, profiles, live delivery, record types, display
  buffers, provisioning, the `csi-radio` command (`cli.py`) and the
  Rust-backed `phase.py`. Imports no other project package.
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
also be run as a module, for example `python -m fall_detection.apps.sessions`.
`csi-radio` is `fall_detection.radio.cli`.

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
