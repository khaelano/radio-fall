# Native radio processing

The live POSIX gateway path uses the Rust extension in
`src/native/radio_core`. USB reading, framing, CRC checks, CSI decoding, scalar
statistics, HE20 phase preparation and CSV formatting execute without calling
Python. A separate Rust thread writes buffered recordings. Python retains radio
control, clock estimation, run/profile validation, duplicate tracking, immutable
availability bins, trial state and the Qt interface. Firmware and radio settings
are unchanged.

## Build and run

Install a stable Rust toolchain (Rust 1.85 or newer) and run:

```bash
uv sync --extra radio --extra video
uv run csi-viewer
# Or resume an existing collection with its saved protocol:
uv run fall-collection --resume-session data/raw/sessions/<session>
```

The setuptools build compiles an optimized release extension with thin LTO.
`Cargo.lock` fixes native dependency versions. Source distributions include the
crate and lockfile; neither generated binaries nor Cargo build output are
versioned. Live acquisition reports an actionable error if the extension is
missing. Gateway envelopes are decoded by Rust; an independent current-format
Python reference decoder is kept in the test suite for protocol comparisons. The native serial worker currently targets
POSIX hosts; it does not silently select the previous Python process reader.
The configured [uv build cache keys](https://docs.astral.sh/uv/concepts/cache/)
include Rust sources, manifest and lockfile, so later native edits trigger a
rebuild. For an explicit rebuild, use
`uv sync --extra radio --extra video --reinstall-package radio-fall-detection`.

## Threads, ownership and deadlines

| Stage | Execution | Bound |
| --- | --- | --- |
| USB drain | Native poll/read thread, 5 ms poll | 4 KiB reads; 256 KiB / 256 raw chunks |
| Frame dispatch | Native ordered dispatcher | Up to eight raw chunks per group |
| CSI preparation | Two Rayon workers | Complete envelopes, at most 1,400 bytes each |
| Completed-frame handoff | Native queue consumed by Python | 16 MiB accounted retained data / 8,192 frames |
| Recording | Native writer thread | 32 MiB admitted and in-progress bytes; five-second flush |

The 200 ms limit now measures the native raw queue and native preparation
completion, which are independent of Python's GIL. Completed frames have already
passed framing, CRC and CSI validation and have their numerical/CSV work
prepared. They can wait separately for Python session acceptance. This changes
the stage to which the old fatal age check applies; it does not redefine arrival
or sensing time. Handoff age is measured separately and included in application
latency. Overflow remains an explicit failure. An indefinite Python or storage
stall cannot be absorbed by these finite buffers.

Raw queue accounting excludes the dispatcher's at most eight in-progress
chunks. Handoff accounting includes retained frame bytes, nested payloads,
records, formatted CSV and phase arrays, plus metadata allowances. It is a
queue-data budget rather than a process RSS limit. In-progress decode groups,
Python rolling history and allocator overhead are additional bounded storage.

Workers preserve wire order after parallel preparation. Shared immutable Rust
records avoid copying complex samples for session metadata. NumPy receives
read-only buffers when a view is requested; constructing Python complex tuples
is deferred until an explicit legacy API request. The original envelope is
journaled without re-encoding or repeating its CRC.

USB read completion uses the host monotonic clock. Transmitter enqueue time,
receiver radio/callback times, capture-clock mapping, uncertainty and application
acceptance time remain distinct. Journals additionally retain native processing
completion and separate raw/native/application queue metrics. Late acceptance
does not revise finalized availability bins. The one-second delivery criterion
and radio retention policies remain unchanged.

## Numeric work and compatibility

The signed I/Q kernel dispatches to AVX2 on supporting x86-64 processors, with
a scalar fallback. It widens signed bytes, calculates squared complex magnitude
and square roots in vectors, and uses exact integer reductions for mean I/Q.
Delimiter scanning uses `memchr` runtime acceleration; CRC uses `crc32fast`.
The HE20 compact 245-slot and full 256-slot layouts retain physical masks,
first-word invalidity and the existing amplitude floor. A centered weighted
two-parameter fit replaces the per-record Python/NumPy least-squares setup.
No fast-math flags relax floating-point semantics.

Cross-checks compare raw I/Q and CSV bytes exactly, magnitude and wrapped phase
within explicit numerical tolerances, and invalid masks exactly. The live native phase path
prepares the current HE20 layouts; unsupported layouts provide no calibrated
phase rather than guessing a subcarrier arrangement.

Recording admission copies into bounded native memory and returns without disk
I/O. The writer releases its admission mutex during writes, including blocked
storage. Bytes remain counted until their write completes. Periodic flush,
explicit barriers and shutdown drain release the GIL. A stream reports saved
only after every admitted byte is written and its descriptors close. Disk
errors remain sticky; overflow fails explicitly. Enabled application ACKs still
wait for recorder/journal file-buffer acceptance. Neither the five-second
buffer nor `flush` provides an `fsync`/power-loss durability guarantee.

## Reproduce verification

```bash
uv run pytest
cargo test --manifest-path src/native/radio_core/Cargo.toml --workspace
cargo clippy --manifest-path src/native/radio_core/Cargo.toml --workspace --all-targets -- -D warnings
cargo test --release --manifest-path src/native/radio_core/Cargo.toml -p radio-signal benchmark_iq_kernel -- --ignored --nocapture
uv run python tools/processing/benchmark_radio_pipeline.py <path/to/envelopes.bin>
```

The automated GIL stress test sends 200 distinct envelopes through a real PTY
while Python holds the GIL for 350 ms. It requires native processing to finish
within 200 ms, ordered and complete delivery, truthful application-wait
diagnostics and drained shutdown. Other tests cover nested corruption,
truncation, sequence wrap, cached-envelope invalidation, manager/ACK integration,
explicit handoff overflow, periodic flushing during a GIL stall, blocked
storage ownership and ENOSPC propagation. The exhaustive native numeric test
compares all 65,536 signed I/Q pairs against scalar arithmetic.

CPU benchmarks exclude live radio, session acceptance, storage and rendering;
they cannot establish usable radio throughput or detector accuracy.

## Measurements, 4 November 2026

On this laptop (AMD Ryzen 7 PRO 4750U, Linux x86-64, Rust 1.97.1), the warmed,
alternating Python/Rust preparation benchmark used 256 preserved envelopes from
`data/experiments/gateway/loss-15min-20261104T074025Z/`, four copies per repeat,
seven repeats and 2,040 records per repeat. Median decode/CSV/phase preparation
was 633.77 microseconds per record in Python and 34.87 microseconds in Rust,
about **18.2x** faster for this work. The isolated release I/Q benchmark measured
median 599 ns scalar versus 219 ns AVX2 per 245-tone record, about **2.7x**.
The overall improvement also includes removal of Python sample objects,
repeated formatting and per-record least-squares setup; it is not solely SIMD.

A visible four-receiver collector GUI ran for 361 seconds with receiver/tab
switching and seven deliberate 350 ms GIL holds. Phone video was unavailable;
the user requested completion without it. This first run stayed outside trials
and exercised acquisition, preview and the transport/session journals. In the
fixed 30-second warm-up/300-second measurement window:

| Receiver | Accepted records/s | P99 latency incl. clock uncertainty | Maximum latency | Within one second |
| --- | ---: | ---: | ---: | ---: |
| rx-1 | 98.623 | 601.49 ms | 982.81 ms | 100% |
| rx-2 | 98.703 | 604.50 ms | 905.17 ms | 100% |
| rx-3 | 98.447 | 634.25 ms | 815.43 ms | 100% |
| rx-4 | 96.307 | 706.27 ms | 1,097.91 ms | 99.958% |

These are unique application-accepted records, without filtering driver
`rx_state`; they are not a detector-usable-rate qualification. Twelve rx-4
records remained late under stress. The derived summary also retains one-second
rate distributions, including low individual windows; an average does not
promise a minimum rate in every second. No acceptance timestamp or finalized
bin was revised to hide the injected stalls.

The run had zero native buffer failures, zero malformed frames and zero increase
in gateway USB errors. Maximum native preparation was 4.457 ms, raw queue wait
3.154 ms and Python application wait 352.809 ms. Raw queue peak was 1,396 bytes;
completed-frame peak was 1,743,045 accounted bytes. Recording peak ownership was
4,212,891 bytes. Both queues and recording ownership drained to zero on shutdown.
Raw journals, GUI samples and `derived-summary.json` remain under
`data/experiments/gateway/rust-pipeline-20261104/181714/`.

A second CSI-only collector run lasted 151 seconds and exercised **52 rapid
recording starts and 51 retries**, plus three 350 ms GIL holds. It intentionally
confirmed the validation action immediately to stress file creation, closing
and attempt transitions; these are not participant activity trials. No native
buffer/framing failure occurred. Native preparation peaked at 2.373 ms,
completed data at 1,836,720 accounted bytes and recording ownership at
6,203,722 bytes; all drained to zero. This checks rapid recording transitions,
not long individual trials. All **39,381 saved CSI rows across 208 receiver CSV
files** matched CSV reconstructed from preserved CRC-valid raw envelopes and
had matching radio/gateway timing rows. Independent Python CSV decoding also
accepted every row. The 51 retried attempts remain rejected and the final
stopped attempt incomplete, as expected; no validation trial was accepted into
the participant dataset. Artifacts and `integrity-summary.json` remain under
`data/experiments/gateway/rust-pipeline-20261104/201126/`.

All 571 Python/integration tests pass, as do the exhaustive native numeric test
and strict Clippy. A wheel built from the source distribution imports the native
module successfully. Build, benchmark and integrity-check scripts/logs are in
`.codex-build/rust-pipeline-20261104/`. These observations do not establish
extended camera-enabled endurance or repair the separately unflashed C6 relay
contention fix. No firmware was flashed or radio policy changed for this work.
