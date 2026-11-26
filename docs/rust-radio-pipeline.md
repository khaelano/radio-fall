# Native radio processing

The Rust workspace in `src/native/radio_core` owns every live radio path:
gateway startup and relay recovery, USB framing, CRC and CSI decoding,
journal-before-ACK acceptance, clock fitting and capture mapping, availability
bins, duplicate-capture removal, signal preprocessing and inference. Python
applications receive accepted records and health snapshots; they display data,
run the collection workflow. Neither the collector nor the viewer writes CSV
files; the transport journal is the raw record. Firmware and radio settings are unchanged.

| Crate | Responsibility |
| --- | --- |
| `radio_signal` | Signed I/Q kernels (AVX2/scalar), Espressif LTF layouts, phase calibration, batch amplitude preparation and Hampel filtering for offline analysis; the `pcspec` principal-component spectrum front end (`pc_spectrum`, `symmetric_eigen`; Python class `PcSpectrumFrontEnd`), not yet used by the live detector |
| `radio_transport` | Framing, CSI decoding, serial I/O, startup, clock and reference, acceptance, journals, availability, quality counters, `session` |
| `radio_detection` | Live sequence windows, ONNX Runtime sessions, scheduling, live and replay feeds |
| `radio-core` (extension) | PyO3 bindings: `NativeAcquisition`, `NativeDetector`, recording writer, record views, offline kernels |

## Build and run

Install a stable Rust toolchain (Rust 1.85 or newer; 1.92 for `radio_detection`)
and run:

```bash
uv sync --extra radio
uv run csi-viewer
# Or resume an existing collection with its saved protocol:
uv run fall-collection --resume-session data/raw/sessions/<session>
```

The setuptools build compiles an optimized release extension with thin LTO.
`Cargo.lock` fixes native dependency versions. Source distributions include the
crates and lockfile; neither generated binaries nor Cargo build output are
versioned. Live acquisition reports an actionable error if the extension is
missing; it has no Python fallback. The serial transport targets Linux. The
configured [uv build cache keys](https://docs.astral.sh/uv/concepts/cache/)
include Rust sources, manifests and lockfile, so later native edits trigger a
rebuild. For an explicit rebuild, use
`uv sync --extra radio --reinstall-package radio-fall-detection`.

## Live session, threads and bounds

`radio_transport::session::run` drives one run at a time: prepare the gateway,
discover the gateway and relayed transmitter, fit the clock from eight
exchanges, configure and start sensing, then accept data until stop or failure.
The detector feed and `NativeAcquisition` both use it.

| Stage | Execution | Bound |
| --- | --- | --- |
| USB read and framing | Session thread, raw serial with 200 ms read timeout | 4 KiB reads; frames above the envelope limit are counted and fail the run |
| Receiver evidence wait | Session thread | 256 envelopes, 750 ms for current receiver status |
| Acceptance | Session thread | Journal flush before ACK; 4,096 remembered batch identities |
| Record handoff to Python | `NativeAcquisition` queue, polled by `LiveRadio` | 65,536 records; overflow fails the run |
| Detector handoff | Bounded channel to the detection coordinator | Packet capacity setting; overflow fails the run |
| CSV and session recording | Native writer thread | 32 MiB admitted and in-progress bytes; five-second flush |

Gateway status must arrive within 2.5 s, and clock and authoritative round
evidence must stay fresh within 2.5 s; otherwise the run fails. A failed run
journals `run_interrupted`; recoverable failures start a fresh run after a
linear backoff (see [automatic radio recovery](automatic-radio-recovery.md)).
Python never runs on the session thread, so GIL or GUI stalls delay only record
delivery and display. The ACK certifies the native envelope journal, not the
later CSV write.

USB read completion uses the host monotonic clock. Transmitter enqueue time,
receiver radio/callback times, capture-clock mapping, uncertainty and
application acceptance time remain distinct. Late acceptance does not revise
finalized availability bins.

## Numeric work and compatibility

The signed I/Q kernel dispatches to AVX2 on supporting x86-64 processors, with
a scalar fallback. It widens signed bytes, calculates squared complex magnitude
and square roots in vectors, and uses exact integer reductions for mean I/Q.
Delimiter scanning uses `memchr` runtime acceleration; CRC uses `crc32fast`.
`radio_signal::layouts` selects the HE20 (compact 245-slot and full 256-slot)
and HT20 LLTF/HT-LTF/STBC layouts; `calibrate` applies a centered,
amplitude-weighted two-parameter fit after unwrapping. Live records use exact
integer amplitudes; offline Python callers of `radio/phase.py`
use the same kernels through `phase_block` and `ltf_layouts`. No fast-math
flags relax floating-point semantics.

Python keeps independent references only in the tests:
`tests/radio/wire_reference.py` decodes the wire format (its fixtures come from
the encoder in `tests/radio/wire_encoder.py`) and `tests/radio/phase_reference.py` calibrates phase with NumPy. Cross-checks
compare raw I/Q and CSV bytes exactly, magnitude and wrapped phase within
explicit tolerances, and invalid masks exactly.

Recording admission copies into bounded native memory and returns without disk
I/O. The writer releases its admission mutex during writes, including blocked
storage. Bytes remain counted until their write completes. Periodic flush,
explicit barriers and shutdown drain release the GIL. Disk errors remain sticky;
overflow fails explicitly. Neither the five-second buffer nor `flush` provides
an `fsync`/power-loss durability guarantee.

## Reproduce verification

```bash
uv run pytest
cargo test --manifest-path src/native/radio_core/Cargo.toml --workspace
cargo clippy --manifest-path src/native/radio_core/Cargo.toml --workspace --all-targets -- -D warnings
cargo test --release --manifest-path src/native/radio_core/Cargo.toml -p radio-signal benchmark_iq_kernel -- --ignored --nocapture
cargo test --release --manifest-path src/native/radio_core/Cargo.toml -p radio-signal benchmark_pc_spectrum -- --ignored --nocapture
```

`tests/radio/test_native_session.py` runs the session against a fake gateway on
a pseudo-terminal, covering startup, journal-before-ACK, rounds, availability,
duplicate removal, restart after lost gateway status and a fatal identity
mismatch. Other tests cover nested corruption, truncation, sequence wrap,
framing across every split, layout and calibration parity, blocked storage
ownership and ENOSPC propagation. The exhaustive native numeric test compares
all 65,536 signed I/Q pairs against scalar arithmetic. None of these tests
exercises radio timing, USB hardware or firmware.

## Historical measurements, 4 November 2026

These measurements describe the superseded design, in which Python owned
session acceptance and Rust prepared frames for a Python handoff. They have not
been repeated for the native session. The Python preparation benchmark used
below was removed with the Python decoder.

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
