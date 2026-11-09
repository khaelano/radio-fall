# Amplitude preprocessing with Polars and Rust

`notebooks/latest/02_preprocess.ipynb` runs the complete amplitude workflow through
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
uv run --no-sync python tools/benchmark_amplitude_pipeline.py data/raw/sessions/20261104T081805521126Z --output-dir data/interim/amplitude_preprocessed_v3/20261104T081805521126Z --verify-dir data/interim/amplitude_preprocessed_v2/20261104T081805521126Z
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
that bottleneck as well. `tools/benchmark_amplitude_preprocessing.py` retains
the original batched NumPy Hampel implementation as an independent reference.

Whole-recording scaling and centered filtering still use future samples.
This optimization does not establish causal model inputs, a training/test
scaling policy, or improved detection accuracy.

The notebook can also generate 80 Hz overlapping windows in separate 2s, 4s,
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
