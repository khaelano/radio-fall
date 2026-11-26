# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

The rules above apply in full. This file only adds commands and architecture
that AGENTS.md does not cover.

## Commands

- Single test: `uv run --no-sync pytest tests/radio/test_native_session.py::test_name -q`
  (`-k <expr>` to filter by name).
- Rust workspace (`src/native/radio_core/`):
  - `cargo test --manifest-path src/native/radio_core/Cargo.toml --workspace`
  - `cargo clippy --manifest-path src/native/radio_core/Cargo.toml --workspace --all-targets -- -D warnings`
- The Rust code is compiled into the Python extension `fall_detection._radio_native`
  (setuptools-rust, PyO3). A plain `uv run` rebuilds it when Rust sources change,
  but `--no-sync` skips that step. After editing Rust, rebuild once with
  `uv sync --extra analysis --extra radio --extra cuda --reinstall-package radio-fall-detection`.
- Apps (entry points in `pyproject.toml`): `csi-live` (live view; model
  inference needs the `detect` extra), `csi-sessions` (record and review
  sessions) and `csi-radio` (board status, provisioning, pairing). Without
  hardware, use `csi-live --replay-capture <dir>`, `csi-sessions` (browsing
  works without a gateway) or `csi-radio check`.
- Firmware in `src/firmware/radio/` needs ESP-IDF 6.1+; see `docs/espnow-gateway.md`.

## Architecture

- Data path: C5 transmitter → 5 GHz CSI sensing → four C5 receivers → 2.4 GHz
  ESP-NOW → C6 gateway → USB → laptop. All operational radio settings live in
  `configs/radio.json` (`docs/radio-configuration.md`). Changing `sensing`
  means the boards must be reprovisioned.
- Rust owns live acquisition, gateway transport, CSI decoding, signal kernels,
  session storage/archives and live ONNX inference. The crates are
  `radio_transport`, `radio_signal`, `radio_storage` and `radio_detection`, all
  composed into the PyO3 extension. Python has no fallback for live
  acquisition. Python handles settings, collection workflow, session state,
  offline analysis and the Qt apps. See `docs/rust-radio-pipeline.md`.
- Python package import order is enforced by `tests/test_architecture.py`
  (`ALLOWED_DEPENDENCIES`): `protocol` and `radio` import no project package,
  `session` imports `protocol`, `collection` and `analysis` import
  `protocol`/`radio`/`session`, and only `apps` imports everything. A new
  top-level package must be registered there. Details are in `src/fall_detection/README.md`.
- `analysis/` holds `preprocessing/` (shared amplitude kernels), `sequence/`
  (our approach, driven by notebooks), `baselines/` (WiFall, FallDeFi
  adaptations) and `diagnostics/`. Model definitions, labels and training
  procedures live in `notebooks/latest/` (02 preprocess → 03 training → 04/05
  baselines → 06 comparison). They are not in `src/`.
- Recordings: the gateway journal under
  `data/raw/sessions/<id>/transport/gateway/<run-id>/` is the only raw radio
  record. Attempts are assigned frames by capture time at conversion. The same
  frame appears once per receiver that heard it, so do not merge those rows.
  Review edits go to `data/annotations/`, never into raw manifests. Schemas are
  in `docs/dataset-format.md`.
- Outputs: notebook run history goes to `artifacts/notebooks/<notebook>/<run-id>/`
  and published ONNX bundles go to `artifacts/model/<model>/`. Each directory is
  tracked by its own `.dvc` file. For comparisons, prefer `HELD_OUT_SESSION`
  splits over random attempt splits, which the equipment-ordered protocol
  confounds (`docs/reports/generalization-2026-11-22.md`).
