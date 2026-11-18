# Storage layout specification (schema 3, draft)

**Status:** living draft. The Rust `radio_storage` crate, its Python bindings,
the version-3 archive writer, and the analysis loaders are implemented and were
verified on real sessions ([section 11.8](#118-implementation-gates)). The
collector stopped writing the legacy CSV sidecars on 18 November 2026, after a
hardware session matched them frame for frame; the inspector and
integrity-analysis migrations are tracked in [section 12](#12-consumers-and-migration).
The document is finalized only after those remaining steps are verified.
[Dataset format](dataset-format.md) remains the authority for data that exists
today.

Every statement carries one of these markers:

- **[implemented]** built, tested, and in the repository.
- **[verified]** read directly from current code or data, with a source link.
- **[proposed]** a design choice that has not been built or measured.
- **[open]** an undecided question; see [Open questions](#13-open-questions).
- **[pending]** a number to be filled in from a measurement.

## 1. Goals and scope

1. Keep one lossless, crash-safe raw record per session.
2. Provide one read-optimized, typed table per session that notebooks and apps
   load without parsing or joining sidecars.
3. Move all storage code into one low-level Rust library shared by the
   collector, the detector, notebooks, and tools.
4. Keep stored size close to today's compressed archives and make reads faster.

Non-goals: choosing a signal representation (amplitude, phase), windowing, or
sequence building. Those stay in analysis code and read the table through the
library. Video recording is unchanged except for how it is aligned
([section 12](#12-consumers-and-migration)).

## 2. Decisions so far

| # | Decision | Source |
| --- | --- | --- |
| D1 | Replace `session_parquet.py` and the Python storage handler with a Rust implementation. | Owner |
| D2 | Raw record is an append-only log; Parquet is a derived copy. The log stays in the archive. | Owner |
| D3 | One Parquet file per session, not per attempt. Attempts are annotations over time ranges. | Owner |
| D4 | Compress the log as zstd inside the session archive; do not recompress Parquet. | Owner |
| D5 | Old CSV-era sessions must remain convertible, through a second input path. All four archives in `data/raw` contain journals, so the path may be unnecessary for them ([section 8](#8-legacy-sources)). | Owner |
| D6 | Integrity verification and crash recovery are in scope. | Owner |
| D7 | Notebooks and apps use one shared library, with Python bindings over the Rust core. | Owner |
| D8 | Store the firmware payload verbatim and decode to I/Q at read time. | Proposed, accepted for now |
| D9 | The journal writer stays in `radio_transport`. The storage crate depends on it for wire decoding and `read_entry`. No move, no dependency cycle. | Owner-approved plan |
| D10 | Derived exports under `data/interim/parquet` and `data/processed` are invalidated once and regenerated. No legacy-fingerprint compatibility. | Owner |
| D11 | The derived tables live under `data/interim/frames/<session-id>/`, in the existing `data/interim` DVC output. | Owner |
| D12 | Python receives Arrow data through the Arrow C stream capsule, not through an Arrow crate pyo3 feature, to avoid a pyo3 version clash. | Owner-approved plan |
| D13 | `frames.parquet` holds frames captured inside an attempt window by default, which is exactly what the CSV sidecars held; `scope = all` keeps every journal frame ([section 7.2](#72-membership-rule-and-frame-scope)). | Measurement |
| D14 | Physical order is run-major journal order, not capture time, because capture time can step backwards ([section 6.2](#62-order-row-groups-encodings)). | Measurement |
| D15 | Reviews live in `data/annotations/<session-id>/session_review.json`, tracked in Git; the library resolves them with the recording and applies them at read time. | Owner |

## 3. Terminology

- **Session**, **trial**, **attempt**: as in [dataset format](dataset-format.md#1-where-the-data-lives).
- **Run**: one continuous transport connection, identified by `run_id`. A
  session can contain several runs after reconnects. An attempt is a time slice
  of one or more runs. **[verified]** the journal is created per run
  ([journal.rs](../src/native/radio_core/crates/radio_transport/src/journal.rs#L36-L39)).
- **Frame**: one CSI measurement from one receiver. The same transmitted frame
  appears once per receiver that heard it.
- **Envelope**: one gateway datagram holding one batch of one to four frames.

## 4. Layout

### 4.1 Current archive layout

**[verified]** by member listing of the four archives in `data/raw/sessions/`
and by reading `20261109T161519702956Z.zip`:

```text
<session-id>.zip
├── original/                                the collector's session directory
│   ├── session.json  protocol.json  events.jsonl
│   ├── transport/gateway/<run-id>/          manifest.json, envelopes.bin,
│   │                                        events.jsonl, availability.jsonl
│   └── trials/<NNN>_<scenario>/attempt_<NN>/
│       ├── attempt.json, camera.mp4 (optional)
│       └── receivers/<rx>/                  csi.csv, radio_timing.csv,
│                                            gateway_timing.jsonl
└── tables/trials/.../receivers/<rx>/        csi.parquet, radio_timing.parquet
```

- Members are Deflate-compressed (text, journals) or stored (video, Parquet).
  The container does not use Zstandard.
- `tables/*.parquet` are plain copies of the CSVs with every column typed as
  string, including the I/Q array. They add size and no typing.
- The same frames therefore exist in the CSV, the string Parquet, the journal,
  and, as `record` events, in the run `events.jsonl`. Sizes are in
  [section 11](#11-measurements).
- Every non-empty archive holds journals: 7 runs in the newest, 31 and 17 in the
  two older ones. The fourth archive (11 KB) is an empty session.

### 4.2 Layout of schema 3

**[implemented]** The derived layer lives under `data/interim/frames/` (decision
D11). Version-3 archives live in `data/raw/sessions/`; the older archives moved
unchanged to `data/old_raw/sessions/` (13 November 2026).

```text
data/old_raw/sessions/<session-id>.zip       pre-schema-3 source archive (unchanged)

data/raw/sessions/<session-id>.zip           version-3 archive (section 5.5)
  ├── original/...                           the session tree without the per-receiver
  │                                          CSV, radio_timing and gateway_timing files
  │                                          and without tables/; journals and logs
  │                                          stored as <name>.zst
  └── manifest.json                          member list with logical SHA-256 hashes

data/interim/frames/<session-id>/            regenerable, versioned with DVC (data/interim)
  ├── frames.parquet                         frames inside attempt windows, all receivers
  ├── attempts.parquet                       one row per attempt
  ├── phases.parquet                         one row per attempt phase
  └── conversion.json                        source fingerprint, counts, output hashes
```

The review overlay (`session_review.json`) is the only mutable file. It lives
outside the archive, at `data/annotations/<session-id>/session_review.json`, and
is tracked in Git (D15). **[implemented]** The `radio_storage` crate resolves
the immutable recording and its review together; see section 4.3.

### 4.3 Resolving a recording and its review

**[implemented]** `radio_storage::open_session(root, id)` returns the recording
with its review applied. Python reaches it as
`_radio_native.storage_open_session`; `storage_open_source(path,
annotations_dir)` does the same for a path outside the repository layout.

1. **Source.** `data/raw/sessions/<id>.zip`, or a directory with that name. A
   version-3 archive must carry the same session id and, when
   `data/old_raw/sessions/<id>.zip` exists, the fingerprint of that
   predecessor recorded in its manifest.
2. **Review.** `data/annotations/<id>/session_review.json` is preferred. A
   `session_review.json` stored inside the source is used only when no
   annotation exists, which keeps directory sessions reviewed before this
   change readable. The applied file's origin is reported as `annotations` or
   `embedded`.
3. **Validation.** The review must match the session id and protocol hash and
   may name only recorded attempts. Unknown fields, bad values and a wrong
   schema version are errors. The same rules apply in the inspector's writer
   (`ReviewDocument`); a parametrised test feeds the same invalid documents to
   both so they cannot drift.
4. **Effective attempts.** Each attempt gets its reviewed label (the recorded
   label is kept as `original_activity_label`), `inclusion`, `quality`, `notes`
   and `review_revision` (`0` without a review). Frames and phases are not
   changed by a review.
5. **Identity.** The recording's fingerprint ignores reviews, so editing one
   never invalidates `frames.parquet`. Derived exports include the review's
   SHA-256, so any edit invalidates exactly the exports that used it.

Writing stays in the inspector (`ReviewStore`): it saves to
`data/annotations/<id>/session_review.json`, reads a review inside the session
directory when none is saved there yet (so the first save migrates it), and
keeps the optimistic-concurrency check and revision history. Moving the writer
into the library is deferred until a second writer exists.

## 5. Raw layer: the journal

### 5.1 Entry framing

**[verified]** [journal.rs](../src/native/radio_core/crates/radio_transport/src/journal.rs#L90-L95)
and [`read_entry`](../src/native/radio_core/crates/radio_transport/src/journal.rs#L158-L176):

| Bytes | Field |
| --- | --- |
| 8 | `arrival_ns`, big-endian: host monotonic time when the envelope was accepted |
| 4 | envelope length `L`, big-endian, at most 1400 |
| `L` | gateway envelope |

A flush precedes every acknowledgement. The reader rejects partial headers and
partial payloads, which is what makes the log crash-tolerant: a torn final entry
is detectable and everything before it is intact.

### 5.2 Envelope, batch and record

**[verified]** [wire.rs](../src/native/radio_core/crates/radio_transport/src/wire.rs#L144-L229).

- **Envelope** (`CGWY`, version 1): 40-byte header holding `run_id` (u64),
  `tx_boot`, `rx_boot`, batch `id` (u32 each), receiver MAC, and payload length;
  then the batch; then a CRC-32 over everything before it. The decoder rejects a
  CRC mismatch.
- **Batch** (`CSIB`, version 1): 60-byte header with record count (1 to 4) and
  ten u32 statistics counters, then each record prefixed by a u16 length.
- **Record** (`CSI1`, version 3): 87-byte header then `n` payload bytes, with
  `n` even and at most 612.

Record header fields **[verified]** from
[`Record::decode`](../src/native/radio_core/crates/radio_transport/src/wire.rs#L44-L104):

| Offset | Size | Field |
| --- | --- | --- |
| 5 | 1 | flags; bit 0 is `first_word_invalid` |
| 10 | 6 | receiver MAC |
| 16 | 6 | transmitter MAC |
| 22 | 4 | `transport_sequence` |
| 26 | 4 | `sequence` |
| 30 | 4 | receiver radio timestamp, microseconds |
| 34 | 1 | `rssi` (i8) |
| 35 | 1 | `noise_floor` (i8) |
| 36 | 15 | `rate`, `sig_mode`, `mcs`, `bandwidth`, `smoothing`, `not_sounding`, `aggregation`, `stbc`, `fec_coding`, `sgi`, `ampdu_cnt`, `channel`, `secondary_channel`, `ant`, `rx_state` (u8 each, in this order) |
| 51 | 2 | `sig_len` |
| 55 | 8 | transmitter enqueue timestamp |
| 63 | 8 | receiver callback timestamp |
| 71 | 16 | radio profile fingerprint (ASCII hex) |
| 87 | `n` | CSI payload |

### 5.3 I/Q convention

**[verified]** The payload is `n` signed bytes in pairs. In each pair the first
byte is the imaginary part and the second is the real part
([radio_signal `iq_scalar`](../src/native/radio_core/crates/radio_signal/src/lib.rs#L12-L23):
`q = p[0]`, `i = p[1]`). The CSV writer emits the bytes unchanged
([`format_csv`](../src/native/radio_core/crates/radio_transport/src/wire.rs#L105-L141)).
The Parquet layer stores the same bytes unchanged and exposes the pairing only
through one documented decode function.

### 5.4 Capture time lives in the run events

**[verified]** on `20261109T161519702956Z`. The journal holds one host arrival
time per envelope (the envelopes there carry two frames each), not a per-frame
capture time. Capture time is written to the run's `events.jsonl` as one
`record` event per frame, with these fields:
`receiver_id`, `receiver_boot_id`, `transmitter_boot_id`, `sequence`,
`capture_host_ns`, `clock_uncertainty_us`, `arrival_ns`, `available_ns`,
`timely`, `rx_radio_us`, `rx_callback_us`, `tx_enqueue_us`,
`native_processing_completed_ns`, and `host_monotonic_ns`.

- Across all 7 runs there are 1,765,508 `record` events and 1,765,508 journal
  frames, and the counts match in every run.
- `capture_host_ns` is unique per receiver within each run. It is an estimate
  and is not always monotone: one run in another archive steps backwards by up
  to about 57 ms after a gap ([section 11.6](#116-other-archives)). Treat it as
  a column, not as an ordering key.
- Conversion can therefore take capture time from these events and does not need
  to replay the clock model. The record counts matched in all three non-empty
  archives (section 11.6).
- `record` events are about 30 percent of the event log by bytes in a 400,000-line
  sample. The rest (`radio_event` with hex payloads, `queue_event`, `round`,
  and so on) is diagnostic. The full event log is 366 MB stored in this
  archive. Which event kinds the raw archive must keep is
  [OQ-12](#13-open-questions).

### 5.4.1 Rust-era journals

**[verified]** in the source and in
[dataset-format.md](dataset-format.md#7-versioning); no Rust-era session exists
locally yet. From 12 November 2026 the Rust session writes every journal. The
directory layout, envelope encoding, and `availability.jsonl` format are
unchanged, but the per-frame `record` events are no longer written. Capture time
is carried by `batch_acceptance` events instead
([acquisition.rs](../src/native/radio_core/crates/radio_transport/src/acquisition.rs#L366-L382)):

| Field | Level | Meaning |
| --- | --- | --- |
| `run`, `transmitter_boot`, `receiver_boot`, `receiver`, `batch` | batch | identity of the envelope |
| `arrival_ns`, `available_ns` | batch | host arrival and acceptance times |
| `clock_uncertainty_us` | batch | clock-mapping uncertainty; added 2026-11-13, null if no reference estimate existed; absent in earlier Rust-era journals |
| `records[].receiver`, `sequence`, `tx_enqueue_us`, `capture_ns` | frame | per-frame capture time |

Each `batch_acceptance` event is written in the same order as its envelope in
`envelopes.bin`, so a reader pairs them one to one (the pattern used by
[feed.rs](../src/native/radio_core/crates/radio_detection/src/feed.rs#L210-L237)).
The Rust era has no `timely`, `native_processing_completed_ns`, or
`rx_callback_us` values in the events. The radio and callback timestamps are
still in the envelope payload. The transport `events.jsonl` also holds
`reference_frame` events (raw relayed frames as hex), `round`, `clock_request`,
`gateway_status`, `round_availability`, `run_resuming`, and `run_interrupted`.

The converter therefore has two event sources, selected per run by the kinds
present: **Python era** (`record` events) and **Rust era** (`batch_acceptance`
events). Frame columns that only one era provides are null in the other
([section 6.1](#61-columns)).

### 5.5 Archive container

**[implemented]** Version-3 archives are ZIP64 files written by
`migrate_archive` ([archive.rs](../src/native/radio_core/crates/radio_storage/src/archive.rs)).

- **Dropped members:** per-receiver `csi.csv`, `radio_timing.csv`,
  `usb_clock_sync.csv`, `gateway_timing.jsonl`, and everything under `tables/`.
  The journals and events determine all of them.
- **Re-encoded members:** `envelopes.bin`, `events.jsonl` and
  `availability.jsonl` under `transport/gateway/<run>/` become stored
  Zstandard frames in members named `<path>.zst`, the convention of the
  collector's compressed streams. The library hides the suffix.
- **Copied members:** everything else (manifests, attempt files, video) is
  copied without recompression.
- **`manifest.json`:** `format`, `version = 3`, `session_id`, the source
  archive's fingerprint, and for every member its stored bytes, logical bytes
  and the SHA-256 of its logical content.
- **Gate:** the destination is renamed into place only after tables converted
  from it equal the tables converted from the source, row for row.
- `verify_archive` re-hashes every member against the manifest and reports
  members missing from either side.

Journal compression level is a parameter (default 9); Deflate against
Zstandard sizes are in [section 11.8](#118-implementation-gates)
([OQ-8](#13-open-questions)).

## 6. Derived layer: `frames.parquet`

### 6.1 Columns

**[implemented]** One row per frame per receiver. Rows are never merged,
interpolated, or deduplicated across receivers.

| Column | Type | Null | Meaning |
| --- | --- | --- | --- |
| `run_index` | uint16 | no | order of the run within the session, by first journal arrival |
| `receiver_id` | string | no | session receiver id (`rx-1`) |
| `transmitter_mac` | string | no | MAC of the frame's transmitter; `is_sensing` compares it with the session's transmitter |
| `run_id` | uint64 | legacy | transport run |
| `tx_boot_id` | uint32 | legacy | transmitter boot |
| `rx_boot_id` | uint32 | legacy | receiver boot |
| `sequence` | uint32 | no | transmitter frame sequence |
| `transport_sequence` | uint32 | no | receiver transfer sequence |
| `capture_time_ns` | int64 | legacy | capture time on the host monotonic clock |
| `capture_uncertainty_us` | float32 | era | clock-mapping uncertainty; Python era per frame, Rust era per batch from 2026-11-13, otherwise null |
| `host_arrival_ns` | int64 | no | envelope arrival; legacy `host_receive_monotonic_ns` |
| `rx_radio_us` | uint32 | no | receiver radio timestamp (32-bit, wraps) |
| `tx_enqueue_us` | uint64 | yes | transmitter enqueue timestamp |
| `rx_callback_us` | uint64 | yes | receiver callback timestamp |
| `rssi`, `noise_floor` | int8 | no | |
| `rate`, `sig_mode`, `mcs`, `bandwidth`, `smoothing`, `not_sounding`, `aggregation`, `stbc`, `fec_coding`, `sgi`, `ampdu_cnt`, `channel`, `secondary_channel`, `ant`, `rx_state` | uint8 | no | verbatim header bytes |
| `sig_len` | uint16 | no | |
| `first_word_invalid` | bool | no | flags bit 0 |
| `csi` | fixed-size binary | no | payload bytes, unchanged (section 5.3); variable-length binary when the length differs within a session. The length was 490 bytes in all measured sessions |
| `timely` | bool | era | Python-era `record` events only; null in the Rust era ([OQ-13](#13-open-questions)) |

"legacy" means the column is null for sessions converted without a journal
(section 8); "era" means it is null when the run's journal era does not provide it
(section 5.4.1). `driver_valid` is `rx_state == 0` and is derived at read time, not
stored. Capture-time columns come from the `record` events (section 5.4).
Fields that are constant within a session (`profile_fingerprint`, bandwidth
settings) are not stored per row; they live in the file metadata and in
`manifest.json` ([OQ-9](#13-open-questions)).

There is no `attempt_index` column. Attempts are annotations joined by time
range (section 7.2), so changing a window never requires rewriting frames.

### 6.2 Order, row groups, encodings

**[implemented]**:

- **Order:** run-major journal order. Runs are ordered by their first journal
  arrival (`run_index`); within a run, frames are grouped by receiver in
  receiver-id order, each group in journal order. This equals
  `(run_index, receiver_id, host_arrival_ns, sequence)`, and `verify` checks it.
  `capture_time_ns` is deliberately not an ordering key: it can step backwards
  when the clock reference is re-fitted (section 11.6).
- **Row groups:** at most 10,000 rows, and a group never spans two
  `(run, receiver)` blocks. Statistics are kept per row group, so
  `read_frames` prunes by `receiver_id` and `capture_time_ns`; because capture
  time is only nearly monotone the row filter is always applied as well.
- **Compression:** Zstandard level 3 on every column.
- **Payload as binary, not a list of int8.** Parquet stores int8 as 32-bit
  integers on disk, so the list form relies on dictionary encoding to stay
  small. Binary stores the firmware bytes directly and decodes with one
  `frombuffer`.
- **Encodings:** no dictionary encoding anywhere (measured smaller on this
  data); delta encoding for `sequence`, `transport_sequence`,
  `capture_time_ns`, `host_arrival_ns`, `rx_radio_us`, `tx_enqueue_us` and
  `rx_callback_us`.

### 6.3 File metadata

**[implemented]** Parquet key-value metadata on `frames.parquet`:

| Key | Value |
| --- | --- |
| `storage_schema_version` | `3` |
| `session_id`, `protocol_hash` | copied from `session.json` |
| `source_kind` | `journal_python_era`, `journal_rust_era`, `journal_no_capture`, `journal_mixed` or `journal_empty` |
| `frame_scope` | `attempts` or `all` |
| `source_fingerprint` | archives: SHA-256 of the central directory (member names, sizes, CRC-32); directories: SHA-256 of the manifests, attempt files and transport files, so a review overlay or a video does not invalidate the tables |
| `converter_version` | semantic version of the converting code |
| `row_count` | rows per `receiver_id` |
| `iq_order` | `imag_real` (section 5.3) |

## 7. Annotations

### 7.1 Tables

**[implemented]** `attempts.parquet`: `attempt_index` (the row number),
`trial_ordinal`, `attempt`, `repetition`, `scenario_id`, `activity_label`,
`status`, `start_ns`, `end_ns`, `action_confirmed`, `action_confirmed_ns` and
`directory`, from `attempt.json`. `phases.parquet`: `attempt_index`,
`trial_ordinal`, `attempt`, `phase` (`countdown`, `action`, `recovery`),
`start_ns` and `end_ns`, from `phase_changed` events by the interval rule of the
analysis timeline: a phase ends where the next one starts, and the last ends at
the attempt's end. Review state (inclusion, quality, corrected labels) stays in
the review overlay. The analysis layer
([session_frames.py](../src/fall_detection/analysis/session_frames.py)) joins the
overlay and the protocol's trial attributes onto these tables and keeps the
validation of phase order and bounds that the old exporter performed.

### 7.2 Membership rule and frame scope

**[implemented]** A frame belongs to an attempt when
`start_ns <= capture_time_ns < end_ns`, evaluated on capture time only. An attempt
without an end time extends to the end of the session. This differs from the old
collector, which also applied a receive-time deadline to late frames
([controller.py](../src/fall_detection/collection/controller.py#L438-L455)); on
the measured sessions the two rules select exactly the same frames
([section 11.8](#118-implementation-gates)).

**Scope.** By default `frames.parquet` holds only frames inside an attempt window
(`scope = attempts`). That is what the CSV sidecars held, so analysis inputs do
not change, and it keeps the table lean: the journal of the 17-run session has
3,012,186 frames but only 1,342,362 (45 percent) lie inside attempts, and the
31-run session keeps 1,428,868 of 4,404,837 (32 percent). The earlier estimate of
0.5 percent gaps came from one session whose recording was almost continuous
([section 11.6](#116-other-archives)). `scope = all` keeps every journal frame, and
the journal itself always keeps them. A session without attempts keeps all
frames. Frames without a capture time cannot be placed in a window and are
excluded from the attempts scope.

## 8. Legacy sources

### 8.1 Legacy CSV adapter

**[verified]** Every non-empty archive in `data/raw/sessions/` today contains
journals, so none of the current raw sessions needs a CSV-only path.
**[proposed]** Keep the adapter as an optional second source implementation, to
be built only if CSV-only sessions turn up (version-1 originals are not in
`data/raw`, and `data/normalized` holds version-2 copies of the same four
sessions). It would read `csi.csv`, `radio_timing.csv`, and
`gateway_timing.jsonl`, write the same schema with the nullable columns, and
record `source_kind = legacy_csv`.

### 8.2 Sort key without capture time

**[open]** [OQ-2](#13-open-questions), reduced in scope. Applies only to
CSV-only sessions that lack `gateway_timing.jsonl`. Proposed fallback: sort by
`(receiver_id, host_arrival_ns, sequence)`. Within one envelope two frames
share an arrival time, so `sequence` must break the tie.

## 9. Identity and ordering

| Purpose | Key |
| --- | --- |
| Physical order | `(receiver_id, host_arrival_ns, sequence)` |
| Time-range filters | predicate on `capture_time_ns`, helped by row-group statistics |
| Row identity | `(run_id, tx_boot_id, rx_boot_id, sequence)` |
| Cross-receiver join | `(run_id, tx_boot_id, sequence)` |

`sequence` alone is not unique across boots or runs. **[verified]** the journal
already deduplicates on `(run, tx_boot, receiver mac, rx_boot, batch id)`
([journal.rs](../src/native/radio_core/crates/radio_transport/src/journal.rs#L77-L89)).
**[verified]** on the measured session (4 receivers, 7 runs, 1,765,508 frames):
all identity keys are unique (0 duplicates); `sequence` is a u32 on the wire
and reached 277,895, so no wraparound; it never decreases within a
`(receiver, run, tx_boot, rx_boot)` group in arrival order; `capture_time_ns`
is unique per receiver within a run. `host_arrival_ns` is not unique per frame,
because frames in one envelope share it, so `sequence` breaks the tie.
Unique `capture_time_ns` per receiver within every run also held on the other two
non-empty archives, but `capture_time_ns` is not monotone in one run
([section 11.6](#116-other-archives)). Uniqueness across runs, and the
sequence-order property on the other archives, are **[pending]**.

## 10. Integrity, recovery and conversion

1. **[implemented] Torn tails.** Journal entries are CRC-checked. A truncated
   final journal entry or an unterminated final event line is counted in the
   conversion report and skipped; a corrupt envelope is an error.
2. **[implemented] Conversion.** A pure function of the source and the options:
   the same input and `converter_version` give byte-identical tables, checked
   by `verify_against_source`. Runs are ordered by first arrival and merged;
   empty runs are reported and skipped. Each file is written to a temporary name,
   synced, and renamed; the source is never written.
3. **[implemented] `conversion.json`.** Source fingerprint, per-run counts (frames,
   frames excluded by the scope, torn tails, frames without capture time,
   backward capture-time steps, arrival decreases and non-increasing
   sequences) and the SHA-256 of each output.
4. **[implemented] Verification.** `verify_dir` re-hashes the outputs, checks the
   schema version, the source fingerprint, per-receiver row counts, that each
   `(run, receiver)` block is contiguous, that `host_arrival_ns` does not
   decrease and `sequence` increases within it. It reports, but does not fail
   on, backward steps in `capture_time_ns`.
5. **[proposed] Crash recovery.** A startup step that finds a session whose
   collector stopped without closing and finalizes it from the journal. The
   converter already accepts a torn journal; the collector-side step is not
   built ([section 12](#12-consumers-and-migration)).
6. **[open]** A collector resume after a host reboot starts a new monotonic
   epoch ([OQ-15](#13-open-questions)).

## 11. Measurements

**[verified]** on one session, `20261109T161519702956Z`: 4 receivers, 7 runs,
883,224 envelopes of 2 frames each, 1,765,508 frames, 490-byte payloads. The
other archives were only listed, not decoded. Scripts and logs are in the
working scratchpad and are not part of the repository; the repeatable version
belongs in the converter's tests.

### 11.1 What the archive stores today

Stored sizes inside the 2,345 MB archive:

| Member group | Stored | Share |
| --- | --- | --- |
| `csi.csv` (attempt frames, Deflate) | 733 MB | 31% |
| `csi.parquet`, string-typed copy (stored as-is) | 585 MB | 25% |
| `envelopes.bin` journals (Deflate; 1,125 MB raw, 637 B/frame) | 525 MB | 22% |
| transport `events.jsonl` (2,546 MB raw) | 366 MB | 16% |
| `gateway_timing.jsonl`, `radio_timing.csv` and `.parquet`, `availability.jsonl` | about 137 MB | 6% |

### 11.2 Typed Parquet from the journal

All 1,765,508 frames, 4 receivers, 10,000-row groups, sorted by
`(receiver, arrival, sequence)`. Capture-time columns were not included in this
test, so add roughly 5 to 10 MB for them.

| Variant | Size |
| --- | --- |
| payload as list of int8, zstd 1 / 3 / 9 | 567 / 443 / 393 MB |
| payload as binary(490), zstd 3 / 9 | 439 / 382 MB |
| binary, no dictionary, zstd 3 | 420 MB |
| binary, no dictionary, delta timestamps, zstd 3 | 406 MB |
| all non-payload columns only, zstd 3, defaults | 45.5 MB |

The payload is the bulk: about 215 to 250 bytes per frame after compression from
490 raw. The list-of-int8 variant with delta encoding and no dictionary came out
at 571 MB because Parquet then stores each int8 as 32 bits.

### 11.3 Comparison

| Representation of the same frames | Size |
| --- | --- |
| `csi.csv` + `radio_timing.csv` + `gateway_timing.jsonl` (attempt frames) | about 810 MB |
| string-typed `csi.parquet` | 585 MB |
| journal, Deflate | 525 MB |
| typed Parquet, best variant | 406 MB |

If the raw archive keeps the journal and the needed events and drops the CSVs
and `tables/`, the 2,345 MB archive would shrink by roughly the CSV, Parquet, and
timing members, which is about 1,500 MB. The derived Parquet then adds about
410 MB locally. These are estimates from one session. The journal's
Zstandard size and the minimum event set are not measured.

### 11.4 Read speed

| Operation | Result |
| --- | --- |
| Load the full typed Parquet (1.77 million frames) | 0.97 s, about 1.8 million frames/s |
| Parse one `csi.csv` with `csv` and `json.loads` into an int8 matrix | about 12,400 frames/s |

The Parquet load is roughly 150 times faster. The CSV figure uses a minimal
parser, so the repository's loaders, which build `CsiRecord` objects, are
slower. A pruned time-range read was not measured meaningfully, because the test
file lacked capture-time sort keys.

### 11.5 Journal and CSV equivalence

**[verified]** Six attempt-receiver `csi.csv` files, chosen at random with a
fixed seed, hold 127,540 rows. Each row was looked up in the decoded journal by
`(receiver, sequence, rx_radio_us)`. All 127,540 were found, with identical
payload bytes and identical `rssi`, `rate`, `sig_mode`, `mcs`, `bandwidth`,
`noise_floor`, `channel`, `sig_len` and `rx_state`. There were no key
collisions across the 1,765,508 journal frames. The CSV is therefore derivable
from the journal for this session. The other columns, the other archives, and
the timing sidecars were not compared.

### 11.6 Other archives

**[verified]** The same per-run check (journal frames against `record` events,
uniqueness and ordering of `capture_host_ns` per receiver) was run on the other
two non-empty archives by a delegated agent. I confirmed the anomaly below
directly, and recounted runs from the raw output because the agent's summary
miscounted them.

| Archive | Runs | Journal frames | `record` events | Frames equal in every run |
| --- | --- | --- | --- | --- |
| `20261109T161519702956Z` | 7 | 1,765,508 | 1,765,508 | yes |
| `20261109T131546367822Z` | 17 | 3,012,186 | 3,012,186 | yes |
| `20261104T081805521126Z` | 31 | 4,404,837 | 4,404,837 | yes |

- Two runs in the 17-run archive contain no frames, and several runs contain only
  4 to 25. The converter must accept empty and tiny runs.
- `capture_host_ns` is unique per receiver within every run in all archives.
- **Run `40d687efd94a27db` (31-run archive) has backward capture-time steps**:
  5 or 6 per receiver, 21 in total over the run's 102,496 frames. Each step is
  between 0.1 and 57 ms, occurs at the same sequence numbers on all four
  receivers, follows a gap of about 490 ms in arrival, and coincides with a clock
  uncertainty of 37 to 178 ms. Sequence never decreases. This is a re-fit of the
  clock reference, not frame reordering.
- The `record` event fields differ slightly between archives: the 31-run archive
  has no `native_processing_completed_ns`.
- Torn journal tails were not found by the script, which decodes whole entries
  and would have stopped on one; this was not tested separately.

### 11.7 Still pending

| Quantity | Status |
| --- | --- |
| Minimum event set the raw archive must keep | pending |
| Pruned read by `capture_time_ns` on the arrival-ordered file | pending |
| Whether `capture_time_ns` is unique across runs | pending |

### 11.8 Implementation gates

**[verified]** Results of the converter on the three non-empty archives, using
the final schema and the default attempts scope.

| Archive | Journal frames | Frames in table | CSV rows compared | Mismatches |
| --- | --- | --- | --- | --- |
| `20261109T161519702956Z` (7 runs) | 1,765,508 | 1,756,649 | 1,756,649 | 0 |
| `20261109T131546367822Z` (17 runs) | 3,012,186 | 1,342,362 | 1,342,362 | 0 |
| `20261104T081805521126Z` (31 runs) | 4,404,837 | 1,428,868 | 1,428,868 | 0 |

- The comparison covers payload bytes, the header fields, `rssi`, `noise_floor`,
  `sig_len`, `rx_state`, the transmitter MAC, radio and enqueue timestamps,
  capture time, clock uncertainty and run and boot ids, for every CSV row of
  every attempt and receiver (`tools/processing/check_storage_equivalence.py`,
  retired on 18 November 2026; last present at commit `af07916`).
  The 31-run archive was compared in four slices that add up to the full table.
- The table holds no frame that a CSV did not hold, so the capture-time
  membership rule reproduces the old per-attempt sets exactly.
- Re-converting the newest archive reproduced all three tables byte for byte.
- Conversion takes 22 s, 37 s and 40 s for the three archives in release mode.
- Version-3 archives: 2,345 MB to 627 MB, 2,740 MB to 1,106 MB and 6,810 MB to
  4,897 MB (the last holds 3.3 GB of unchanged video), 11.9 GB to 6.63 GB over
  the three archives, each proven table-identical before publication and then
  re-hashed by `verify_archive`. The derived tables add 409, 336 and 358 MB.
  Details and the ZIP64 defect found on the way are in the
  [report](reports/storage-layout-migration-2026-11-13.md).
- The new analysis loader matches the old CSV loader on attempts (19) and phases
  (50) tables exactly and, for two sampled recordings of 29,184 and 26,613
  packets, on about 35 columns including the I/Q payload, `is_sensing`, capture
  times and row order.

## 12. Consumers and migration

**[implemented]** The shared library is the pure-Rust crate `radio_storage`
(no Python dependency) plus a thin PyO3 layer in `radio-core` that returns
Arrow data to Polars and pandas without copying.

| Area | Operations |
| --- | --- |
| Read | `read_frames` by receiver and capture-time range with column projection, `session_files`, `read_session_file`, `source_fingerprint` |
| Convert | `convert_session` (scope `attempts` or `all`) |
| Check | `verify_dir`, `verify_against_source`, `verify_archive` |
| Archive | `migrate_archive`, `archive_manifest` |

There is no Python storage package: Python calls the crate through
`fall_detection._radio_native` (`storage_*` functions, `FrameStore`, `ArrowTable`,
`StorageError`). The analysis view is `fall_detection.analysis.session_frames`.

| Consumer | Status |
| --- | --- |
| `analysis/session_parquet.py` | removed; replaced by `session_frames.py` |
| `amplitude_pipeline`, `sequence_preprocessing`, benchmark tools | migrated and tested |
| Notebooks `01_exploration`, `01_01`, `01_02`, `02_preprocess` (`02_preprocess_old` later removed) | edited in the editor buffers through the notebook bridge; they must be saved |
| `phase_signals`, `phase_motion`, `integrity` | see the change log for the current state |
| `session_inspector` | see the change log for the current state |
| Collector (`collection/capture.py`) | writes no CSV sidecars since 18 November 2026; the journal is the raw record |

**Preprocessing checkpoints and exports.** Source fingerprints changed, so
exports under `data/interim/parquet` and `data/processed` are invalidated once
(decision D10). Regenerating them requires running the preprocessing notebook.

**DVC.** Only `data/raw.dvc` (the version-3 archives) is tracked for session
data, since 13 November 2026. Untracked on purpose: `data/interim/frames` and the
version-2 copies, which are rebuilt from raw (`interim.dvc` and `normalized.dvc`
removed); `data/old_raw` (`old_raw.dvc` removed; the directory is git-ignored and
kept locally, and its content stays in the remote under the earlier `raw.dvc`
hash `c9cbc27e...`); and `data/processed` (`processed.dvc` removed; the 44 GB of
exports have obsolete fingerprints and are regenerated by the preprocessing
notebook, and the earlier ones stay in the remote under earlier commits).
Reviews in `data/annotations` are tracked in Git, not DVC. Nothing has been
pushed: the remote still holds the earlier `raw` content, and the version-3
archives need a `dvc push`.

## 13. Open questions

| ID | Question | Status |
| --- | --- | --- |
| OQ-1 | Is capture time stored per frame, or must it be recomputed? | **Resolved** for the measured session: `record` events (section 5.4). Confirm on the other archives. |
| OQ-2 | Sort key for CSV-only sessions without capture time | Reduced: no such session in `data/raw` today |
| OQ-3 | Is `sequence` non-wrapping and are keys unique? | **Resolved** for the measured session (section 9) |
| OQ-4 | Do row-group statistics on `capture_time_ns` prune an attempt's time range when the file is sorted by arrival? | Open |
| OQ-5 | Cached `attempt_index` column | **Resolved**: dropped (section 6.1) |
| OQ-6 | Where does the derived layer live? | **Resolved**: `data/interim/frames/` (D11) |
| OQ-7 | Where does the mutable review overlay live relative to the immutable archive? | **Resolved**: `data/annotations/<session-id>/` (D15, section 4.3) |
| OQ-8 | Journal compression: Zstandard vs Deflate, per run vs per block | Open |
| OQ-9 | Which session-constant header fields move to `manifest.json` and file metadata? | Open |
| OQ-10 | Does the journal move from `radio_transport` into the storage crate? | **Resolved**: no (D9) |
| OQ-11 | One `attempts` and one `phases` file, or a single intervals table? | Open |
| OQ-12 | Which transport event kinds must the raw archive keep? Events are 16% of the archive; `record` events carry capture time, the rest is diagnostic or replay data | Open |
| OQ-13 | Meaning of `timely` and `available_ns` in `record` events, and whether they belong in `frames.parquet` | Open |
| OQ-14 | Do the 31-run and 17-run archives show the same properties? | **Resolved** for record counts and capture-time uniqueness; capture time is not monotone in one run (section 11.6). Key uniqueness and sequence order are still pending on those archives. |
| OQ-15 | How are resumes after a host reboot represented, given that monotonic time restarts? | Open; needs an epoch rule for ordering and for attempt windows |

## 14. Change log

| Date | Change |
| --- | --- |
| 2026-11-13 | Initial draft from design discussion. Journal, record, and I/Q formats verified against current code. Measurements pending. |
| 2026-11-13 | Measured one real session. Added current archive layout (4.1); capture time found in `record` events (5.4); payload changed to binary; `attempt_index` dropped; gaps between trials are 0.5 percent so all frames are stored; legacy CSV path made optional; measurements and open questions updated. Earlier size estimates used a wrong baseline and are replaced by section 11. |
| 2026-11-13 | Checked the other two non-empty archives. Record counts match in all three. Found backward capture-time steps in one run, so the sort key changed from capture time to journal order `(receiver_id, host_arrival_ns, sequence)` and `verify` no longer requires monotone capture time. Added OQ-15. |
| 2026-11-13 | Added Rust-era journals (5.4.1), decisions D9 to D12, derived path `data/interim/frames/`, per-era nullable columns, and `source_kind` values. Added `clock_uncertainty_us` to `batch_acceptance` events in `acquisition.rs` (one value per batch). |
| 2026-11-13 | Implemented the crate, bindings, analysis loaders, inspector and integrity migrations, and version-3 archives. Default scope changed to frames inside attempts (D13) after the 17-run and 31-run archives showed 55 and 68 percent of frames outside attempts. Added `run_index` and `transmitter_mac`, the run-major order (D14), the directory fingerprint rule, and the real-data gates (section 11.8). Fixed a ZIP64 read-back defect in archive migration. |
| 2026-11-13 | Moved the version-3 archives to `data/raw/sessions` and the older ones to `data/old_raw/sessions`. Added the review resolver (section 4.3, D15): `radio_storage::review` and `resolve`, bindings, the `fall_detection.storage` facade, and `data/annotations`. OQ-7 resolved. |
| 2026-11-13 | Retired the Python `fall_detection.storage` package. The crate gained `write_archive` (version-3 archives from session directories, used by the collector; sidecars kept until the Rust-era journal is validated), `extract_archive`, `read_file` (logical reads of the collector's Zstandard streams), `FrameStore` and `ensure_frames`, and the PyO3 module exposes them directly with `StorageError` and Arrow PyCapsule tables. The archive gate found that `attempts.parquet` recorded the `original/` prefix for archives, so directory and archive sources gave different tables; the column is now relative to the session. |
| 2026-11-18 | A hardware collector session (two 60 s segments, four receivers) passed `check_storage_equivalence.py`: 45,824 frames, no mismatch. The collector stopped writing CSV sidecars; they made up 47% of that session's archive. |
| 2026-11-18 | Retired `check_storage_equivalence.py` (last present at `af07916`): new sessions have no CSV sidecars to compare against. |
