# Architecture rehaul: status on 13 November 2026

This report records the state of the host-side simplification and
reorganization on branch `refactor/simplify-architecture` (34 commits on top of
`main` at `0dfe4aa`, not merged and not pushed) at the end of 13 November.
Firmware was out of scope, and hardware validation was explicitly excluded.

## Completed

| Item | Commit |
| --- | --- |
| Missing string attempt values (e.g. walk-to-stand directions) no longer break `read_packets` | `d5e23e7` |
| Session scanning and `materialize` handle `.zst` files; resume rejects stray attempt entries; unused `has_trials` removed | `6123017` |
| Inspector window split into concern mixins (35 methods verified unchanged); CSI detail pane explains stale frame tables | `48ea04f` |
| Retired per-recording export (`preprocess_dataset`, `save_recording`) and its benchmark removed; grant-timing model moved to `tools/radio/grant_timing.py` | `03ced05` |
| pandas and zstandard moved from core dependencies to the `analysis` extra | `6094b60` |
| CSI viewer journals default to `data/experiments/viewer/`, outside DVC-tracked `data/raw/` | `2f965bf` |
| 12 November detector runs tracked with DVC as `data/experiments/detector/runs-20261112`; new runs ignored by Git | `5a669c6`, `ca797f2` |
| `FrameStore.ensure` holds an advisory lock on `<frames_dir>.lock`; reviewed and brought in from the agent worktree, with a four-thread Rust test and a two-process Python test | `0f79b06` |
| `CsiRecord` is the only Python record type, backed by a Rust record with a new constructor; `NativeRecord` and `AnyCsiRecord` removed from Python | `308726b` |
| Video failure handlers in the collection controller marked as deliberate error boundaries (Ruff `BLE001` had failed since `b6f8eaf`) | `a2ec972` |
| `docs/project-knowledge.md` records this round's changes | `f5120be` |
| `01_01_amplitude_exp` and `01_exploration` import the reorganized modules and were rerun from fresh kernels (see below) | `90cae19` |
| Inconsistent frame cache of session `20261104T081805521126Z` rebuilt (see below) | derived data, not in Git |
| Agent worktrees `agent-a557b97a8c6920505` and `agent-a77881277c0cb9c97` removed with their branches | none needed |

The record-type agent had stopped with its tests passing but two defects
untested: `copy.copy` of a record recursed without bound, and records could not
be pickled. Both were fixed by rebuilding records from their fields, and a test
covers pickle, copy and deepcopy. Nothing pickles records today; the inspector
drops them before its worker process returns. The change also fixes an existing
inspector bug: the CSI detail pane read a non-existent `block.values` attribute
whenever a frame had an LTF block, which a new test now covers. Four GUI tests
moved from HE20 to HT fixtures because HE20 records are now phase-ready at
construction; with HE20 they no longer reach the cold-preview path they test.

## Checks

- **Python tests:** 612 passed, 2 skipped (torch not installed) at `f5120be`.
- **Rust:** all workspace tests passed, `cargo clippy` reported no warnings and
  `cargo fmt` was clean at the record-type commit.
- **Ruff:** clean on every file changed today. The repository still has 36
  errors in 13 other files; `main` has 187 with the same Ruff version.
- **Inspector smoke run:** on the archive of session `20261104T081805521126Z`,
  receivers resolved for 255 attempts in 1.3 s. An accepted attempt loaded
  through a spawned worker process (1536 records for `rx-1`), signal
  preparation returned 800 plotted times, and three table rows were rebuilt into
  245-sample HE20 records, each with 245 calibrated value rows. The script uses
  the window's load functions without opening a window. The earlier stop after
  session loading did not recur; its cause remains undetermined.
- **Detector replay:** `fall-detect --headless --backend cpu` replayed captures
  `native-capture-20261112-b` and `-c` through all nine models (exit 0, 427
  published rows). Every score lay in [0, 1]. Unknown windows were `stale`
  (late inference with nine models sharing the CPU) or `coverage` (receiver
  coverage below 0.7); `lstm-6s` scored no window on capture C. Capture A was
  rejected because it predates reference-event logging, as the
  [capture report](native-capture-2026-11-12.md) records. These are unlabelled
  ten-second probe captures, so the scores say nothing about accuracy. The test
  suite's replay test separately confirmed bit-exact model inputs on capture C.
- **Frame caches:** `storage_verify` passed for sessions
  `20261109T131546367822Z` and `20261109T161519702956Z`. For
  `20261104T081805521126Z`, `frames.parquet` (written 12:53) did not match the
  hash in `conversion.json` (written 12:52), the pattern expected when two
  unlocked conversions overlap; the saved output of `01_01_amplitude_exp` cell 1
  shows such a conversion failing with a corrupt Parquet read. Two fresh
  conversions produced byte-identical tables, and both matched the
  `frames.parquet` that had been in place. The data read from that cache was
  therefore correct; only its manifest was stale. The cache was rebuilt and now
  verifies.
- **Notebooks:** the bridge could not restart the `01_01_amplitude_exp` kernel
  (it stayed in `restarting` for more than seven minutes), so both notebooks
  were run by hand in VS Code from fresh kernels. `01_01` finished with no error
  cells and six image cells; cell 11 has its output again. `01_exploration` ran
  cells 1–56 in order (08:00–08:05 UTC) with no error cells and 20 image cells.
  Ruff, using the repository configuration on copies of the cell code read
  through the bridge, found only an import-order issue in each first code cell;
  it was fixed through the bridge before the notebooks were saved.

## Update, 18 November

The data laptop (`laptop-fd`) is the source of truth; the other device is used
only for training. `laptop-remote` is on a separate host, so pushes from the
laptop are off-machine backups.

- **Notebook run history.** The 179 files (113 MB, directory hash `65fd3c14…`)
  that `artifacts/notebooks.dvc` recorded on 12 November were in neither
  machine's cache nor on `laptop-remote`; a push from the training device
  reported nothing to send. The pointer was re-recorded to the seven figures on
  disk (`25b492a1…`, 4.4 MB). The old record remains in commit `7ad7d7c` and can
  be checked out if the data turns up.
- **Model bundles.** `dvc commit artifacts/model.dvc` stored the 21 files in
  the cache without changing the `.dvc` file.
- **Hardware storage check.** A collector session recorded on radio hardware
  (`20261118T061506921397Z`: continuous mode, two 60 s segments, CSV sidecars
  on) finished with both attempts accepted. All four receivers delivered for
  the whole 121 s, at 91.7–98.0 frames/s each. The archive verified, its
  45,824 converted frames re-verified against the source, and
  `check_storage_equivalence.py` on the session directory matched every CSV row
  to exactly one frame with no mismatch in payload, PHY header, MAC, signal,
  radio timestamps, capture time or clock uncertainty. The sidecars made up
  13.3 MB (47%) of the 28.1 MB archive. The archive is tracked with DVC under
  `data/experiments/storage-check-20261118/`; Git ignores the 96 MB working
  directory, which duplicates its contents.
- **Sidecars removed.** The collector no longer writes CSV sidecars (`771abf2`).
  The full suite passed (637 passed, 2 skipped). A 60 s session with the updated
  collector (`20261118T090516246988Z`, tracked under
  `data/experiments/collector-check-20261118/`) finished with the attempt
  accepted, only `attempt.json` in the attempt directory, `csv_sidecars: false`
  in the manifest and a 6.5 MB archive that verified; its 18,036 frames
  re-verified against the source. rx-1 and rx-2 delivered at their usual median
  of 95–96 frames/s, but rx-3 and rx-4 fell to medians of 54 and 69 frames/s
  with eight to nine gaps over 0.5 s each, against 96 frames/s in the earlier
  session. Python no longer touches records before they are journaled, so the
  change cannot reduce delivery; the cause, probably placement or interference,
  was not investigated.
- **Backup.** `dvc push` uploaded the four version-3 session archives (about
  6.6 GB), the 12 November detector captures and runs, and both 18 November
  hardware sessions. The original pre-migration archives (11.9 GB) were already
  complete on `laptop-remote`; they were then removed from the local cache with
  `dvc gc --workspace` (local cache 18 GB to 6.3 GB) and can be restored with
  `dvc pull` at `5ab3758`. The working directories of the two test sessions were
  deleted after their archives verified.
- **Artifacts were skipped by DVC.** That push did not include the model bundles
  or the figures, and `dvc status -c` without targets did not check them. DVC
  skips any `.dvc` file or directory that its Git library (`dulwich`) reports as
  ignored, and it treated the root rule `/artifacts/*`, despite its
  `!/artifacts/*.dvc` negation, as ignoring `artifacts/model.dvc` and
  `artifacts/notebooks.dvc`; it also treats `/artifacts/*/` as ignoring the
  `artifacts/` directory. `dvc gc --workspace` therefore removed their cache
  objects as unused. The files were still on disk; `dvc commit` restored the
  cache, and pushing both `.dvc` files by name uploaded all 21 model files and 7
  figures, confirmed on the remote. `.gitignore` now names `/artifacts/model/`
  and `/artifacts/notebooks/`, so commands without targets include both outputs.
  New artifact directories need their own line.
- **Merge.** `main` was fast-forwarded to the branch locally; nothing was pushed
  to `origin`.
- **Storage.** The working tree is on btrfs, and DVC's cache shares extents with
  the tracked files, so the cache does not duplicate them on disk.

## Not done

### Follow-ups found

1. **Equivalence checker gaps.** Given an archive, the checker does not decode
   `.zst` members, so a Rust-era archive reports "no CSV sidecars"; the session
   directory works. It also skips, without counting a mismatch, any receiver
   whose three sidecar files differ in row count. Neither affected the result
   above, where every frame was matched.
2. **Currency check ignores output hashes.** `tables_current` accepts a table set
   whose `conversion.json` hashes do not match the files, which is how the stale
   manifest above went unnoticed; `storage_verify` detects it in about 0.5 s on
   a 358 MB table. The lock prevents the race through `FrameStore.ensure`, but
   direct `convert_session` calls are not locked. Adding a hash or size check is
   a proposal, not implemented.
3. **Pre-existing Ruff errors** (36), mostly in `tools/papers/`, the video
   modules and `protocol/loader.py`.

### Deliberately not done

4. **Cache warm-up.** Notebook stage caches and the integrity and phase-motion
   caches rebuild once because their keys hash moved source files. Forcing it
   would rerun the long preprocessing and rewrite derived datasets.
5. **Historical references left as they are.** `docs/reports/ble-c6-timing-2026-11-01.md`
   and `docs/archive/ble-delivery-policy.md` cite `radio.experiments.ble_timing`,
   which was removed before this work. The "648 Python tests" count in
   `docs/amplitude-preprocessing.md` is a dated record.

## Verification limits

- Apart from the collector session above, the GUI applications have been
  exercised only by offscreen tests and the window-free inspector script.
- On radio hardware, this work has been run only in that two-minute collector
  session; sustained operation and radio-failure recovery are unverified.

## Suggested order

1. Check rx-3 and rx-4 placement and delivery before the next participant
   session.
2. Decide whether `tables_current` should check output hashes.
