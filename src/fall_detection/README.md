# Python package layout

`apps/` contains application entry points and presentation code:

- `collector/`: operator and performer interfaces and collection presenter.
- `csi_viewer/`: live CSI viewer entry point.
- `session_inspector/`: offline inspector interface and video panel.
- `detector/`: live detector interface and command.

`presentation/` contains dashboard widgets shared by multiple applications.
The other packages contain reusable functionality: `radio/` provides acquisition
and configuration; `collection/`
provides collection protocols and session orchestration; `session_inspector/`
provides session reading and review; `detection/` provides scoring and replay;
`storage/`, `analysis/`, and `contracts/` provide shared data access, validation,
and signal primitives. Experimental preprocessing, labels, plots, model definitions,
and training procedures live in `notebooks/latest/`.

The installed commands are defined in `pyproject.toml`. Each application can
also be run as a module, for example `python -m fall_detection.apps.collector`.

The processing architecture has three layers:

1. `src/native/radio_core/` handles USB ingestion, framing, packet decoding,
   and recording. Its `radio_signal` and `radio_preprocessing` workspace
   crates provide numeric kernels and signal preprocessing.
2. The Python domain packages validate settings, manage collection and session
   state, query recordings, and coordinate analysis and inference.
3. `presentation/` provides shared widgets, and `apps/` presents those
   capabilities through the desktop applications.

The Rust extension is built with the Python package; it is required by live
acquisition and native stream decoding.

The native crate layout follows the component-workspace approach used by
[Ruff](https://github.com/astral-sh/ruff/blob/main/Cargo.toml): reusable
components declare their dependencies, while the extension composes them.
