# Amplitude preprocessing with Polars and Rust

## Synchronized raw magnitude at 96 Hz

`notebooks/latest/02_preprocess.ipynb` uses
`analysis/sequence_preprocessing.py` to process Khaelano
(`20261104T081805521126Z`), Akmal (`20261109T131546367822Z`), and continuous
non-fall (`20261109T161519702956Z`). It selects accepted attempts unless review
metadata excludes them. The existing archive-aware loader verifies source
checksums and reuses the canonical Parquet cache. Raw archives and previous
derived datasets remain unchanged.

Projected Parquet reads and Polars handle metadata. The magnitude-only Rust
entry point keeps the existing HE20 masks without min–max scaling. Rayon defaults
to all available logical CPUs (16 on this laptop). Restart an existing notebook
kernel before changing its already initialized Rayon pool.

Intermediate arrays are uncompressed NPY files, loaded through read-only memory
maps. Hampel and squared differences add only their new arrays; existing arrays
are not rewritten. Stage checkpoints bind source fingerprints, parameters, code,
and output file identities. A completed dataset reuses its audit tables and index
without opening signal arrays. Source-cache hits check file identities and the
previously verified archive/Parquet manifest; changed source files return to the
canonical validation path. Normal cache reads are not forensic integrity audits.

All receivers share one sequence anchor per segment. Nearest-round selection
converts nominal 120 Hz to 96 Hz, with ties upward, without interpolation or an
anti-alias filter. Missing selected rounds remain NaN. The first duplicate wins;
duplicate and rollover counts are reported. Legitimate uint32 rollover unwraps;
unresolved backward jumps fail. Attempts, run changes, transmitter boots, and
receiver reboots remain separate. A recording gap is defined here as at least
one second without any sensing packet in the union of receiver streams. Shorter
losses remain explicit holes; this boundary rule does not impose a coverage
cutoff. The gap duration is recorded in the manifest.

Grid times use nominal 96 Hz ticks anchored by the median of observed capture
time minus sequence offset/120. Retained source sequence numbers and actual
per-receiver capture times are also stored; capture time −1 means no selected
packet. Grid time is a nominal coordinate, not an interpolation of signal values.

Centered Hampel uses a 0.5 s inclusive neighborhood, threshold 3, at least five
finite samples, and the existing scaled-MAD factor 1.4826. Zero MAD leaves the
center unchanged. Missing values remain missing. Squared consecutive differences
follow filtering and propagate missing values from either endpoint. Each
segment starts with an invalid difference; no difference crosses a boundary.

Window start plus duration must fit inside the recorded attempt interval,
even when nominal grid timing drifts slightly beyond an edge. Boundary omissions
and cue-label omissions are reported separately. Complete 2/4/6 s windows contain
192/384/576 samples with 50% overlap. All four
receivers share each boundary. Fall windows receive target 1 only when their
center lies in the recorded action cue [start, end); other windows from fall
attempts are omitted. Non-fall activities, including continuous non-fall,
receive target 0. Action cues approximate an activity interval and are not
impact annotations. Coverage never causes an exclusion, and missing values
are never filled. Centered filtering uses future samples and may extend beyond
an interior window boundary within the same segment. This is an offline
representation; causal live preprocessing needs a separate design.

Training outputs live in `data/processed/amplitude_sequence_v2/<dataset>/`.
Each `signals/<segment_id>.npy` contains one float32
`log1p(squared_difference)` matrix in `[time, receiver, subcarrier]` order.
Invalid samples are NaN. The memory-mapped loader derives validity from finite
values, then zero fills and standardizes valid values before appending mask
channels. `window_index.parquet` stores the 2/4/6-second slice boundaries,
targets, coverage, grouping IDs, and recording provenance. `signals.parquet`
records each file's logical length, byte size, and SHA-256; `manifest.json`
records the schema version, source, parameters, coordinates, counts, and table
hashes. Btrfs compression is disabled on newly written signal files; other
filesystems use the same NPY format. Copy-on-write and checksums remain enabled.

Intermediate preprocessing arrays retain amplitude, filtering, masks, phase,
and timing needed for audit figures while the workflow runs. After a direct v2
export, only the representative segment cache remains. Migrated datasets also
retain their review tables, figures, and representative cache. The raw archives
remain authoritative for regenerating other audit arrays. Full signal checksum
scans require `load_exported(verify_hashes=True)`. The migration tool verifies
overlap consistency while writing and compares every saved window with v1 in a
separate pass. No training split is assigned here. The earlier v1 NPZ contract
and run measurements remain in the dated v1 report.
Stage figures show deterministic representative
segments, while summary tables cover the complete datasets; figures are saved
beside the derived reports in `reports/figures/`.

Figure previews sample at most 1,200 time points and overlay at most 24 windows
per duration. Availability is shown as the fraction of available source samples
inside each display bin; preview thinning can omit short signal transients, but
does not affect exported tensors or full-dataset summaries. Each stage reads
only arrays needed for its figure. Saved PNGs and robust shared color scales are
reused when their inputs and display settings match; `plot_stage(...,
refresh=True)` forces a redraw. A new figure is rendered once and that PNG is
embedded in the notebook, avoiding a second inline render. The notebook uses
`ENABLE_PLOTS = True`; set it to `False` to skip rendering.

Reproduce with:

```bash
uv sync --inexact --extra analysis --extra notebook --reinstall-package radio-fall-detection
uv run --no-sync jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 notebooks/latest/02_preprocess.ipynb
```

## Earlier per-recording workflow

The earlier notebook, now `notebooks/latest/02_preprocess_old.ipynb`, used
`analysis/amplitude_pipeline.py`. Polars selects accepted recordings and handles
packet metadata. PyArrow's native Parquet reader reuses file metadata, projects
17 required columns, and reads only candidate row groups. Rust decodes the
batched signed-int16 I/Q arrays, aligns compact 245-slot or full 256-slot HE20
layouts to physical indices −122…122, applies validity masks, fits per-subcarrier
min–max scaling, and runs the centered Hampel filter.

The workflow no longer constructs per-packet Python complex tuples, calculates
unused phase/calibration arrays, or performs repeated pandas packet-table
materialization. Existing valid Parquet exports load their selection table
directly into Polars. The shared CSV-to-Parquet exporter remains the canonical
cache builder and still uses pandas when a cache must be created or rebuilt;
other analysis notebooks keep their existing interfaces. Cache validity still
uses the shared source fingerprint and schema contract.

## Numeric behavior and parallel work

The native CSI kernel preserves the amplitude floor of four, driver validity,
first-word invalidity, null tones, signed physical order and missing samples.
All selected sensing rows must use a supported layout; corrupt lengths, null
samples, mixed identities and invalid or backwards timestamps fail explicitly.
The output retains the original masks and does not synthesize missing packets.

Runtime AVX2/FMA dispatch computes four magnitudes together using a scaled
ratio and fused multiply-add. This explicit evaluation matches NumPy's complex
SIMD magnitude rounding on the verified machine. Using libc hypot instead
introduced tiny rounding differences that changed a few nearly constant
Hampel windows; that version was discarded. The portable scalar kernel uses
the same explicit fused formula and is tested against dispatched results,
including all 65,536 signed-byte I/Q pairs and signed-int16 extremes. Exact
agreement with a different NumPy version or CPU dispatch must be checked with
the supplied comparison tool; it is not inferred from an approximate tolerance.

Rayon parallelizes physical decoding, scaling and subcarrier filtering while
PyO3 releases the GIL. The Hampel filter keeps inclusive timestamp windows,
minimum finite counts, median, scaled MAD threshold and zero-MAD behavior.
Replacements always read the original normalized recording. Each filter task
reuses one window-sized scratch vector; it does not build three-dimensional
window arrays. Absolute deviations use runtime AVX2 dispatch with a scalar
fallback. No compiler fast-math flags are enabled.

Python exchanges immutable byte buffers with Rust, preventing alias mutation
while the GIL is released. Working memory is bounded by the current recording,
one previous recording being saved, and native scratch buffers. A single
background writer overlaps compression with the next read and computation;
there is no unbounded future queue.

NPZ writing uses lossless deflate level 1 by default. Files keep the existing
array names, shapes and dtypes and remain readable with `numpy.load`. A complete
temporary archive replaces its destination atomically; a failed save preserves
the previous destination. Provenance records the backend, compression level
and preprocessing parameters. The default output is
`data/interim/amplitude_preprocessed_v3/<session>/`; previous derived outputs
and raw recordings are preserved.

## Reproduce

Install before starting the notebook kernel, or restart it after rebuilding:

```bash
uv sync --inexact --extra analysis --reinstall-package radio-fall-detection
uv run --no-sync python tools/processing/benchmark_amplitude_pipeline.py data/raw/sessions/20261104T081805521126Z --output-dir data/interim/amplitude_preprocessed_v3/20261104T081805521126Z --verify-dir data/interim/amplitude_preprocessed_v2/20261104T081805521126Z
```

`--inexact` preserves separately installed notebook packages. The benchmark's
`--recordings` option limits a run and `--compression-level` selects deflate
level 0–9. Verification compares every saved array exactly, excluding the
provenance JSON whose backend/compression fields intentionally differ.
Set `RAYON_NUM_THREADS` before starting Python to limit the offline worker pool.
The standalone Hampel API also exposes scalar and serial comparison modes.

## Verification on 8 November 2026

On an AMD Ryzen 7 PRO 4750U, Linux x86-64, Polars 2.1.0:

| Measurement | Original pipeline | Polars/Rust pipeline |
| --- | ---: | ---: |
| Same first 20 recordings, read through compressed save | 30.07 s | 1.07 s |
| All 928 selected receiver recordings | ≈1,186 s, earlier saved notebook execution | 33.00 s |
| Full-run startup/cache validation | — | 0.95 s |

The 20-recording comparison was about 28 times faster end to end. The full
dataset run was about 36 times faster than the earlier notebook execution.
These are individual local runs rather than repeated cross-hardware estimates.
The full run verified all 928 new files against the previous dataset: amplitudes,
validity and replacement masks, timestamps, phase labels, physical subcarrier
indices, and scale extrema were exactly equal. Verification time is excluded
from the processing timings.

Summed full-run stage durations were 9.38 s reading, 6.76 s for preparation
(including Polars validation and native decode/scaling), and 14.22 s filtering.
Serialization/compression runs concurrently, so these figures are not an
independent breakdown of writer CPU time. Derived disk usage rose from about
843 MiB to 875 MiB with faster compression, approximately four percent.
All three inspection plots executed using the native path.

The previous isolated Hampel optimization measured roughly 23–25 times faster
filtering, but left Python decoding dominant. The full pipeline above removes
that bottleneck as well. `tools/processing/benchmark_amplitude_preprocessing.py` retains
the original batched NumPy Hampel implementation as an independent reference.

Whole-recording scaling and centered filtering still use future samples.
This optimization does not establish causal model inputs, a training/test
scaling policy, or improved detection accuracy.

The earlier notebook also generated 80 Hz overlapping windows in separate 2s, 4s,
and 6s directories. The stride is half the duration. Linear interpolation
requires finite valid endpoints at most 25 ms apart; other values remain NaN
with a false validity mask. Windows use the attempt clock and keep per-sample
phase labels, replacement masks, physical subcarriers, and activity provenance.
The single window label is the most recent recorded collection phase at or
before the center; if the center has no timing support it is `unknown`.
Phase transitions are consequently localized only to the packet interval.
These phase labels are collection cues,
not precise movement boundaries. Interpolation is not an anti-alias filter;
the 80 Hz representation has not been validated against held-out data.

## Checks

Tests cover canonical-decoder equivalence, mixed supported layouts, invalid
metadata, projected/mixed row groups, cache reuse without pandas tables,
atomic writer failures, and independent NumPy Hampel comparisons. Native tests
cover SIMD/scalar magnitudes and tails. All 648 Python tests and nine Rust tests
passed (one optional timing test ignored); strict Clippy also passed. Run:

```bash
uv run --no-sync pytest
cargo test --manifest-path src/native/radio_core/Cargo.toml
cargo clippy --manifest-path src/native/radio_core/Cargo.toml --all-targets -- -D warnings
```

Radio integration tests require local socket permissions.
