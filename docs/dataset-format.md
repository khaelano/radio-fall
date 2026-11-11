# Dataset format

This document describes the on-disk structure of a recorded collection session:
where each file lives, what it contains, and how to read it without guessing.
It is the reference for anyone building datasets, annotations, or models from
`data/raw/sessions/`.

**Raw container:** version-1 and version-2 ZIP64
[session archives](session-archive-pilot.md) are supported. New collector
streams use version 2 with direct Zstandard recording.
The collector publishes one verified `<session-id>.zip` on application exit.
The layout below describes its exact original members, working directories,
and verified extractions. Use `fall_detection.storage.Recording` to open raw
archives and legacy directories. Migration retains both representations.

**Inner artifact schema:** `2` (receiver-split). The obsolete schema 1 is
described in [Legacy format](#8-legacy-format-and-cleanup) and is no longer
written or read.

## Contents

1. [Where the data lives](#1-where-the-data-lives)
2. [Session bundle](#2-session-bundle)
   - [2.1 `session.json`](#21-sessionjson)
   - [2.2 `protocol.json`](#22-protocoljson)
   - [2.3 `events.jsonl`](#23-eventsjsonl)
   - [2.4 `session_review.json`](#24-session_reviewjson)
   - [2.5 Curated exports](#25-curated-exports)
3. [Trials and attempts](#3-trials-and-attempts)
   - [3.1 Naming and ordering](#31-naming-and-ordering)
   - [3.2 `attempt.json`](#32-attemptjson)
   - [3.3 Receiver directories](#33-receiver-directories)
   - [3.4 Optional video recording](#34-optional-video-recording)
4. [CSV formats](#4-csv-formats)
   - [4.1 `csi.csv`](#41-csicsv)
   - [4.2 `radio_timing.csv`](#42-radio_timingcsv)
   - [4.3 `usb_clock_sync.csv`](#43-usb_clock_synccsv)
5. [How to read the dataset](#5-how-to-read-the-dataset)
   - [5.1 Session inspector](#51-session-inspector-recommended-for-browsing-and-review)
   - [5.2 Python API](#52-python-api)
   - [5.3 Building a flat manifest](#53-building-a-flat-manifest)
   - [5.4 Direct CSV access](#54-direct-csv-access)
6. [Invariants and gotchas](#6-invariants-and-gotchas)
7. [Versioning](#7-versioning)
8. [Legacy format and cleanup](#8-legacy-format-and-cleanup)
   - [8.1 Schema 1](#81-schema-1-obsolete)
   - [8.2 Cleanup performed on 2026-10-27](#82-cleanup-performed-on-2026-10-27)
   - [8.3 Pruning](#83-pruning)
9. [Quick reference](#9-quick-reference)
10. [Derived amplitude sequence v2 export](#derived-amplitude-sequence-v2-export)

## 1. Where the data lives

Dataset contents under `data/` are git-ignored; only the directory README files
are versioned. Raw recordings are
immutable: analysis code may read them, but must not rewrite or re-label them in
place. Review decisions belong in the sidecar described in
[2.4](#24-session_reviewjson).

```text
data/
├── raw/
│   ├── sessions/
│   │   └── <session-id>/                    one collection session
│   │       ├── session.json                 session manifest
│   │       ├── protocol.json                pinned protocol snapshot
│   │       ├── events.jsonl                 append-only event log
│   │       ├── session_review.json          optional review overlay
│   │       └── trials/
│   │           └── <NNN>_<scenario-id>/
│   │               └── attempt_<NN>/
│   │                   ├── attempt.json
│   │                   ├── camera.mp4                 optional synchronized video
│   │                   ├── camera_frames.csv          optional frame timing
│   │                   ├── video.json                 optional video status/settings
│   │                   └── receivers/
│   │                       └── <receiver-id>/
│   │                           ├── csi.csv
│   │                           ├── radio_timing.csv
│   │                           └── usb_clock_sync.csv
│   └── receivers/<receiver-id>/             ad-hoc captures, not sessions
├── archive/                                 compressed obsolete bundles (local)
├── interim/                                 extracted windows and features
├── annotations/                             reviewed labels
├── processed/                               model-ready dataset versions
├── splits/                                  train/validation/test assignments
├── experiments/                             engineering experiment outputs
└── models/                                  local model weights
```

Rules of thumb:

- A **session** is one operator-led collection run. Its directory name is the
  session id, a UTC timestamp such as `20261026T174653764289Z`
  (`%Y%m%dT%H%M%S%fZ`).
- A **trial** is one planned activity from the protocol, addressed by its
  ordinal and scenario id.
- An **attempt** is one recording of a trial. Retries create `attempt_02`,
  `attempt_03`, and so on.
- A **receiver directory** is one ESP32 receiver. The same transmitted frame
  appears once under every receiver that heard it; never merge those rows.
- `data/raw/receivers/` contains standalone `csi_<timestamp>.csv` and
  `radio_timing_<timestamp>.csv` captures. They use the schemas in
  [section 4](#4-csv-formats) but have no session manifest, trial metadata, or
  review sidecar, and generally no clock-sync file. Treat them as scratch data,
  not as a substitute for a session bundle.
- `data/archive/` holds compressed legacy material. It is a local safety net,
  not an input to the current pipeline.

## 2. Session bundle

A session directory is self-describing: the manifests pin the protocol, the
radio setup, the receiver mapping, and every attempt disposition. A reader
should be able to reconstruct the experimental conditions from the bundle
alone.

| File | Required | Written by | Purpose |
| --- | --- | --- | --- |
| `session.json` | yes | collector | Session identity, protocol hash, environment, lifecycle status |
| `protocol.json` | yes | collector | Exact expanded protocol snapshot used for the trial queue |
| `events.jsonl` | yes | collector | Append-only operator/phase/attempt event stream |
| `session_review.json` | no | session inspector | Reviewed labels, inclusion, quality, notes, revision history |
| `trials/` | when trials ran | collector | One directory per trial and attempt |

All manifests and the review sidecar are UTF-8 JSON, sorted by key, indented by
two spaces, and terminated by a newline. They are replaced atomically through a
temporary `.tmp` file. `events.jsonl` is compact JSON Lines instead: one
sorted-key object per line, appended and flushed in event order.

### 2.1 `session.json`

The session manifest is created when the session starts and rewritten when it
finishes. A trimmed example:

```json
{
  "artifact_schema_version": 2,
  "completed_trials": 160,
  "ended_monotonic_ns": 33615215680036,
  "environment": {
    "nominal_rate_hz": 100,
    "radio_profile": {
      "band": "5ghz",
      "bandwidth_mhz": 20,
      "channel": 44,
      "country_code": "ID",
      "nominal_rate_hz": 100,
      "profile_id": "indonesia-5g-ch44-100hz",
      "schema_version": 1
    },
    "radio_profile_fingerprint": "38b0022110bb30ac",
    "receiver_bindings": {
      "rx-1": {
        "mac": "44:bd:8d:d0:b1:4c",
        "port": "/dev/ttyACM2",
        "profile_fingerprint": "38b0022110bb30ac",
        "target": "esp32c5"
      },
      "rx-2": {
        "mac": "44:bd:8d:d0:b3:50",
        "port": "/dev/ttyACM1",
        "profile_fingerprint": "38b0022110bb30ac",
        "target": "esp32c5"
      }
    },
    "receiver_ids": {
      "44:bd:8d:d0:b1:4c": "rx-1",
      "44:bd:8d:d0:b3:50": "rx-2"
    }
  },
  "location": "lab",
  "notes": "",
  "operator": "operator-01",
  "participant_id": "participant-01",
  "protocol_hash": "18f14ea48c7fffb835e0888bbd0a917b659e23ccb427404b9fa901fb0cc5cda0",
  "protocol_id": "fall-collection-simple-v1",
  "session_id": "20261026T174653764289Z",
  "started_at_utc": "2026-10-26T17:46:53.764289+00:00",
  "status": "complete"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `artifact_schema_version` | integer | Must be `2` for the layout in this document |
| `session_id` | string | Directory name; UTC `%Y%m%dT%H%M%S%fZ` |
| `participant_id` | string | Operator-supplied participant identifier |
| `operator` | string | Operator name or initials; may be empty |
| `location` | string | Free text; may be empty |
| `notes` | string | Free text; may be empty |
| `protocol_id` | string | `protocol_id` from the pinned protocol |
| `protocol_hash` | string | SHA-256 of the resolved protocol source; joins a session to its review sidecar |
| `started_at_utc` | string | ISO 8601 wall-clock start time |
| `status` | string | `open` while recording, `complete` when the queue finished, `ended` when the operator stopped early |
| `ended_monotonic_ns` | integer | Host monotonic clock at session finish |
| `completed_trials` | integer | Trials resolved when the session closed |
| `environment` | object | Runtime bindings; see below |
| `curation` | object | Present only in curated exports; see [2.5](#25-curated-exports) |

`environment` is an extensible snapshot. These keys are the ones that matter for
reading the data:

| Key | Meaning |
| --- | --- |
| `receiver_ids` | Map of lowercase receiver MAC to receiver id. This map determines the `receivers/<receiver-id>/` directory names |
| `radio_inventory` | Snapshot of the inventory (schema 1 historically; schema 2 includes the C6 gateway) |
| `radio_profile` | Snapshot of the active radio profile: band, channel, bandwidth, nominal rate, profile id |
| `radio_profile_fingerprint` | Short fingerprint of the profile applied to the firmware |
| `receiver_bindings` | Per receiver id: MAC, firmware target, USB port, applied profile fingerprint |
| `radio_config` | Path of the unified radio settings file; resolved snapshots above remain authoritative |
| `receiver_config` | Historical split inventory input path; null for unified configuration |
| `transport`, `nominal_rate_hz`, `port`, `listen_host`, `listen_port` | Acquisition settings |

`environment.video` is null for CSI-only sessions, or contains requested device,
size/rate, codec, host observation timing policy and unknown phone pipeline
latency. Actual source dimensions/rate and PyAV version are saved in each
attempt's `video.json`. This optional schema-2 recording is separate from the
removed camera comparator; older `camera_*` and `scenario_*` environment keys
remain historical metadata.

`ended_monotonic_ns` and the event log use the host monotonic clock, so they are
only meaningful relative to the start of the same machine boot. To map an event
to wall time, anchor it to `started_at_utc` with the `session_started` event's
`monotonic_ns` (see [2.3](#23-eventsjsonl)).

### 2.2 `protocol.json`

`protocol.json` is written once at session start. It is the resolved source
after block selection: if the operator ran only some blocks, the snapshot
contains only those blocks and the trial ordinals are renumbered from 1.

Top-level fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Protocol schema, currently `1` |
| `protocol_id` | Stable protocol identifier |
| `title` | Human-readable protocol title |
| `defaults` | Default `countdown_seconds`, `action_seconds`, `recovery_seconds` |
| `blocks` | Ordered blocks, each with `id`, `title`, and `scenarios` |
| `trial_order` | Optional `declared` (default) or `equipment` execution order |
| `scenario_manifests` | Optional relative paths of the source manifests |
| `resolved_manifest_sources` | Optional array of `{path, source}` for reproducibility |

Each scenario contains:

| Field | Meaning |
| --- | --- |
| `id` | Unique scenario id, e.g. `walk-to-fall__start_front__end_front` |
| `activity_label` | Planned label, e.g. `walk_to_fall`; this is also written to attempts |
| `title` | Display title |
| `instruction` | Performer instruction |
| `repetitions` | Number of repetitions expanded into trials |
| `countdown_seconds`, `action_seconds`, `recovery_seconds` | Per-scenario timing, if it overrides the defaults |
| `attributes` | Free-form metadata; typically `family_id`, `start_direction`, `end_direction`, `direction_frame`, `manifest_path`, `safety_note` |

The protocol is expanded deterministically. With the default `declared` order,
blocks and scenarios follow written order, then repetitions `1..n`. With
`equipment` order, scenarios are grouped across blocks by equipment stage,
chair orientation, and start/end direction, then repetitions `1..n`. Equipment
and resolved chair orientation are stored in scenario `attributes`. See the
[collection configuration](../configs/collection/README.md) for the setup order.
The expansion produces the
`trial_ordinal` used by attempt directories and `attempt.json`. Use
`fall_detection.collection.protocol.load_protocol()` to get the expanded
`protocol.trials` rather than reimplementing the loop.

`protocol_hash` is computed over the canonical JSON of the resolved source. Two
sessions with the same protocol id but a different block selection have
different hashes, which is deliberate: they represent different trial queues.

### 2.3 `events.jsonl`

One JSON object per line, appended in event order. The live collector can batch
physical writes through its recording service (currently five seconds); event
timestamps retain their original observation time. Every event has:

| Field | Meaning |
| --- | --- |
| `kind` | Event type |
| `monotonic_ns` | Host monotonic timestamp at emission |

Known event kinds in current sessions:

| `kind` | Extra fields | Emitted when |
| --- | --- | --- |
| `session_started` | none | Session directory and manifest created |
| `attempt_started` | `trial_ordinal`, `scenario_id`, `attempt` | A trial attempt begins recording |
| `phase_changed` | `state`, `trial_ordinal`, `attempt` | The operator state changes (`countdown`, `action`, `recovery`) |
| `action_confirmed` | `trial_ordinal`, `attempt`, `activity_label` | Operator confirms the planned action |
| `trial_resolved` | `trial_ordinal`, `attempt`, `disposition` | Trial advances after accept or skip |
| `receiver_status` | `message`, `connected` | Acquisition adapter reports a receiver connection change |

The log is append-only and can be longer than the current state: use the last
event for each attempt when reconstructing a timeline. Do not assume that every
event kind appears in every session; aborted sessions may stop early, and
`receiver_status` is diagnostic noise for most analyses.

### 2.4 `session_review.json`

This optional sidecar is created by `fall-session-inspector` when the operator
saves a review. It never modifies `session.json`, `attempt.json`, or the CSV
data. Schema:

```json
{
  "schema_version": 1,
  "session_id": "20261026T174653764289Z",
  "protocol_hash": "18f14ea48c7fffb835e0888bbd0a917b659e23ccb427404b9fa901fb0cc5cda0",
  "revision": 2,
  "updated_at_utc": "2026-10-27T01:40:00+00:00",
  "metadata": {
    "participant_id": "participant-01",
    "notes": "reviewed after session"
  },
  "attempts": {
    "trials/001_walk-to-fall__start_front__end_front/attempt_01": {
      "activity_label": "walk_to_fall",
      "inclusion": "include",
      "quality": "good",
      "notes": "clean signal"
    }
  },
  "history": [
    {
      "revision": 2,
      "saved_at_utc": "2026-10-27T01:40:00+00:00",
      "changes": [
        {"path": "attempts.trials/.../notes", "old": "", "new": "clean signal"}
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `schema_version` | Review schema, currently `1` |
| `session_id`, `protocol_hash` | Must match the session manifest; prevents applying a review to the wrong bundle |
| `revision` | Starts at `0`; increments on every saved change |
| `updated_at_utc` | ISO 8601 time of the last save |
| `metadata` | Optional overrides for `participant_id`, `operator`, `location`, `notes` |
| `attempts` | Map from the attempt's relative path to its review |
| `history` | Array of revisions, each with `revision`, `saved_at_utc`, and flattened `changes` (`path`, `old`, `new`) |

Attempt review values:

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `activity_label` | non-empty string or `null` | Correction; `null` means “use the acquisition label” |
| `inclusion` | `unreviewed`, `include`, `exclude` | Whether the attempt belongs in a curated dataset |
| `quality` | `unreviewed`, `good`, `questionable`, `bad` | Signal/recording quality judgment |
| `notes` | string | Free text |

Saving is optimistic: the inspector reads the sidecar's current bytes, rejects a
save if another process changed them, and writes through a `.tmp` file. Active
sessions (`status: open`, or any attempt still `recording`) are read-only.

### 2.5 Curated exports

`fall-session-inspector` can export a session plus its review to a new directory.
The export keeps the same schema-2 layout and raw CSV bytes, and adds:

- `session.json` → `curation`: `exported_at_utc`, `source_session_id`,
  `source_protocol_hash`, `review_revision`, `excluded_attempts_retained: true`.
- `session.json` metadata fields overridden by review metadata.
- `session_review.json`: the full review document.
- Each reviewed `attempt.json` → `review` block (`inclusion`, `quality`,
  `notes`, `reviewed_at_utc`, `source_review_revision`), and
  `original_activity_label` when the reviewer corrected the label.

Excluded attempts are retained in the export and marked with
`inclusion: "exclude"`. Downstream code must filter on review state rather than
assuming every exported attempt is usable.

## 3. Trials and attempts

### 3.1 Naming and ordering

```text
trials/001_walk-to-fall__start_front__end_front/attempt_01/
trials/001_walk-to-fall__start_front__end_front/attempt_02/
trials/002_walk-to-fall__start_front__end_left/attempt_01/
```

- The trial prefix is `<ordinal:03d>_<scenario-id>`. The scenario id is
  slugified for the filesystem (`[A-Za-z0-9_.-]` preserved, other runs replaced
  with `-`), but `attempt.json.scenario_id` keeps the original id. Read the
  manifest, not the directory suffix, when exact ids matter.
- The attempt suffix is `attempt_<NN>`, two digits. Retries increment it; a
  retried trial leaves earlier attempts in place.
- Trial directories normally cover the selected protocol queue. A trial with no
  attempts was planned but never started.
- `attempt.json.trial_ordinal` is authoritative if a directory name and manifest
  ever disagree.

### 3.2 `attempt.json`

Written when the attempt starts (`status: recording`) and rewritten atomically
when it ends. Core fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `artifact_schema_version` | integer | `2` |
| `session_id` | string | Parent session |
| `trial_ordinal` | integer | Expanded protocol ordinal, starting at 1 |
| `repetition` | integer | Repetition number of the scenario, starting at 1 |
| `scenario_id` | string | Exact protocol scenario id |
| `activity_label` | string | Planned activity label from the protocol |
| `planned_reference_label` | string | Same planned label, recorded at finish |
| `started_monotonic_ns` | integer | Host monotonic time at attempt start |
| `ended_monotonic_ns` | integer | Host monotonic time at attempt finish |
| `status` | string | Attempt disposition; see below |
| `action_confirmed` | boolean | Operator confirmed the action during the action phase |
| `action_confirmed_monotonic_ns` | integer or null | Host monotonic time of confirmation |
| `reference_truth` | boolean | Present on accepted attempts that require manual confirmation |
| `reference_truth_label` | string or null | Label accepted as ground truth when `reference_truth` is true |
| `invalid_reason` | string | Present when the attempt was invalidated by a timeout or missing confirmation |
| `interruption_reason` | string | Present when an operator or health failure interrupted the attempt |
| `radio_telemetry_start`, `radio_telemetry_end`, `radio_telemetry_delta` | objects | Acquisition counters for engineering diagnostics |

Attempt status lifecycle:

```text
recording ──► pending_review ──► accepted
                    │
                    ├──────────► rejected      (operator retries)
                    └──────────► skipped       (operator skips)

recording ──► invalid        (timeout, abort, or health loss)
recording ──► incomplete     (operator ended the session mid-attempt)
```

`accepted`, `rejected`, `skipped`, `invalid`, and `incomplete` are terminal.
`pending_review` means the capture finished but the operator has not decided yet.
An `invalid` attempt cannot be accepted.

The `activity_label` is the **planned** label. Use `reference_truth_label` when
it exists and is non-null for the operator-confirmed label; otherwise use the
review sidecar's `activity_label` correction, and fall back to
`activity_label`. Do not infer a label from `radio_telemetry_*`.

`radio_telemetry_*` is an opaque diagnostic snapshot. It contains counters such
as `records`, `batches`, `transport_missing`, `batch_missing`, `malformed`,
`foreign`, and `receiver_restarts`, plus `values`, `warnings`, and `complete` in
the delta. It is useful for quality screening but is not part of the CSI format.

In curated exports, an attempt can additionally contain `original_activity_label`
and a `review` object (see [2.5](#25-curated-exports)).

### 3.3 Receiver directories

```text
attempt_01/receivers/rx-1/
├── csi.csv
├── radio_timing.csv
└── usb_clock_sync.csv
```

- One directory per receiver id, using the id from
  `session.json.environment.receiver_ids` (filesystem-slugified).
- `csi.csv` and `radio_timing.csv` are written in the same order: row `n` of the
  timing file describes row `n` of the CSI file. `radio_timing.sequence` should
  equal `csi.id`.
- `usb_clock_sync.csv` is independent: it has one row per synchronization
  exchange, not one row per CSI frame.
- Files are created with headers even when no frames arrive, so a header-only
  CSV is valid and usually means the receiver heard nothing during that attempt.
- The receiver MAC is in `radio_timing.csv` and `usb_clock_sync.csv`; the CSI
  `mac` column is the **transmitter/source** MAC, not the receiver.

### 3.4 Optional video recording

Enabled-video attempts add three files at the attempt root. This is an
additive extension of artifact schema 2; existing CSI-only sessions are valid.
`attempt.json.video` names the three relative paths. No schema-1 camera
comparator data or inference output is reintroduced.

| File | Contents |
| --- | --- |
| `camera.mp4` | H.264 video with variable presentation timestamps; no audio |
| `camera_frames.csv` | One row per submitted video frame, indexed in presentation order |
| `video.json` | Video schema version 1, lifecycle status, requested/negotiated settings and timestamp coverage |

Frame timing columns are:

| Column | Meaning |
| --- | --- |
| `frame_index` | Zero-based index within this clip |
| `presentation_pts` | Microseconds from attempt start to host read completion, rounded down |
| `time_base_num`, `time_base_den` | Encoder time base, `1/1000000` |
| `host_read_started_monotonic_ns` | Host time immediately before obtaining the decoded frame |
| `host_read_completed_monotonic_ns` | Host observation time used for presentation alignment |
| `source_pts` | Original decoder PTS; empty when unavailable |
| `source_time_base_num`, `source_time_base_den` | Original decoder time base; empty when unavailable |

`video.json.status` progresses through `queued`, `recording` and `complete`,
or becomes `failed`. `frames` counts submitted frames. The sidecar stores
`attempt_started_monotonic_ns`, `ended_monotonic_ns`, and the first/last frame
observation timestamps. `configuration` contains requested output/device
settings, timing policy and an unknown `phone_pipeline_latency_ns` (null).
`source` records the camera's negotiated dimensions/rate and PyAV version.
A complete clip must be finalized, nonempty, and have no observations at or
after the attempt end. `complete` does not guarantee uninterrupted camera
exposure or power-loss durability. Failure metadata and partial files remain
available for diagnosis and cannot satisfy video acceptance.

Match video to CSI using host monotonic timestamps from this CSV and each
receiver's mapped capture times in `gateway_timing.jsonl`. Do not align by
video frame number, assumed frame rate or USB arrival. Source PTS are evidence,
not an established exposure clock. DroidCam buffering is unmeasured; see
[video recording](video-recording.md) for synchronization limits and validation.

## 4. CSV formats

All CSVs are UTF-8, comma-separated, with a header row and `\n` line endings.
Columns are positional in the ESP-IDF `CSI_DATA` sense; keep the header to avoid
off-by-one errors.

### 4.1 `csi.csv`

One row per CSI callback. The header is exactly:

```text
type,id,mac,rssi,rate,sig_mode,mcs,bandwidth,smoothing,not_sounding,aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,secondary_channel,local_timestamp,ant,sig_len,rx_state,len,first_word,data
```

| # | Column | Meaning |
| --- | --- | --- |
| 1 | `type` | Always `CSI_DATA` for a valid row |
| 2 | `id` | Transmitter frame sequence; matches `radio_timing.sequence` |
| 3 | `mac` | Lowercase source/transmitter MAC that elicited the CSI |
| 4 | `rssi` | Received signal strength in dBm |
| 5 | `rate` | ESP-IDF rate index; `11` in the current sensing setup |
| 6 | `sig_mode` | Baseband format: `4` = HE, `1` = HT, other values can appear from non-sensing traffic |
| 7 | `mcs` | Modulation and coding scheme; `0` for the HE20/MCS0 sensing link |
| 8 | `bandwidth` | Bandwidth code; `0` for the fixed 20 MHz setup |
| 9 | `smoothing` | ESP-IDF smoothing flag |
| 10 | `not_sounding` | ESP-IDF non-sounding flag |
| 11 | `aggregation` | A-MPDU aggregation flag |
| 12 | `stbc` | Space-time block coding flag |
| 13 | `fec_coding` | FEC coding flag |
| 14 | `sgi` | Short guard interval flag |
| 15 | `noise_floor` | Noise floor in dBm |
| 16 | `ampdu_cnt` | A-MPDU counter |
| 17 | `channel` | Primary channel of the capture |
| 18 | `secondary_channel` | Secondary channel code |
| 19 | `local_timestamp` | Receiver 32-bit microsecond timer at the callback; wraps every ~71.6 minutes |
| 20 | `ant` | Antenna index |
| 21 | `sig_len` | Signal length reported by the firmware |
| 22 | `rx_state` | Receiver state flags |
| 23 | `len` | Number of integers in `data`; always `2 × number_of_complex_slots` |
| 24 | `first_word` | `1` when the first four CSI bytes (two complex values) are invalid |
| 25 | `data` | Quoted JSON array of interleaved integers: `[imag, real, imag, real, ...]` |

Parsing `data`:

- The array alternates imaginary and real parts. A pair `[i, r]` is
  `complex(r, i)`; this is the convention used by
  `fall_detection.radio.acquisition.protocol.parse_csi_line`.
- `len` counts integers, not subcarriers. For the current HE20 compact layout,
  `len` is typically `490` (245 complex slots). Do not hard-code the width; use
  `len`, or derive the layout from `sig_mode`, `bandwidth`, and `stbc` with the
  helpers in `fall_detection.radio.preprocessing.phase`.
- When `first_word` is `1`, `parse_csi_line` preserves the raw values but sets
  the first two parsed complex values to `NaN` for plotting. `raw_csi` keeps the
  original values; `csi` is the masked view.
- Rows with `sig_mode == 1` are commonly non-HE frames (control/ESP-NOW or
  ambient traffic) captured by the same receiver. For the standard HE20 sensing
  dataset, filter on `sig_mode == 4`, `mcs == 0`, and the expected transmitter
  MAC. The exact filter should be recorded with the dataset version.
- `channel` is the channel the receiver was tuned to. A session can contain
  more than one channel only if the profile changed between attempts; the
  `radio_profile` snapshot is authoritative for the session.

A minimal parse in Python:

```python
import json
import numpy as np
import pandas as pd

frame = pd.read_csv("csi.csv")
frame["csi"] = frame["data"].map(
    lambda text: (
        np.array(json.loads(text)[1::2]) + 1j * np.array(json.loads(text)[0::2])
    )
)
```

This produces one `numpy` complex vector per row. For validated parsing,
including the `first_word` mask and declared-length checks, use
`parse_csi_line(row_text)` from the package instead of the one-liner.

### 4.2 `radio_timing.csv`

One row per CSI row, in the same order:

```text
sequence,receiver_mac,transport_sequence,tx_enqueue_timestamp_us,rx_radio_timestamp_us,rx_callback_timestamp_us,host_receive_monotonic_ns
```

| Column | Meaning |
| --- | --- |
| `sequence` | Transmitter frame sequence; equals `csi.id` |
| `receiver_mac` | MAC of the receiver that wrote this directory |
| `transport_sequence` | Per-transfer/batch sequence from the receiver; not a frame id |
| `tx_enqueue_timestamp_us` | Transmitter `esp_timer` at frame enqueue (may be blank) |
| `rx_radio_timestamp_us` | Receiver 32-bit radio timestamp; equals `csi.local_timestamp` |
| `rx_callback_timestamp_us` | Receiver `esp_timer` at callback (may be blank) |
| `host_receive_monotonic_ns` | Host monotonic clock when the host received the record |

`tx_enqueue_timestamp_us` and `rx_callback_timestamp_us` can be empty when the
transport does not provide them. The radio timestamps are device-local 32-bit
values; use `usb_clock_sync.csv` before comparing them to host or transmitter
time. Align CSI and timing rows by row index, and verify `csi.id ==
radio_timing.sequence`; a mismatch indicates a truncated or partially written
attempt.

### 4.3 `usb_clock_sync.csv`

One row per clock exchange. In the USB collection path the exchange is between
the **host and receiver**. The historical column names `tx_*` and
`receiver_minus_transmitter_us` are retained, so read “transmitter” in those
names as “reference clock”: the host for USB sessions, the transmitter for the
legacy ESP-NOW gateway exchange.

```text
host_receive_monotonic_ns,receiver_mac,sync_id,sensing_sequence,receiver_boot_id,tx_t1_us,rx_t2_us,rx_t3_us,tx_t4_us,rx_radio_t2_us,tx_radio_t4_us,round_trip_us,receiver_minus_transmitter_us,drift_ppm,uncertainty_us
```

| Column | Meaning |
| --- | --- |
| `host_receive_monotonic_ns` | Host monotonic time when the host received the exchange result |
| `receiver_mac` | Receiver MAC |
| `sync_id` | Exchange counter |
| `sensing_sequence` | Transmitter sensing sequence current at the exchange |
| `receiver_boot_id` | Receiver boot identifier; changes on reboot and resets the clock fit |
| `tx_t1_us` | Reference-clock `t1`: host monotonic microseconds in USB collection, transmitter `esp_timer` in the legacy gateway exchange |
| `rx_t2_us` | Receiver `esp_timer` when the request arrived |
| `rx_t3_us` | Receiver `esp_timer` when the reply left |
| `tx_t4_us` | Reference-clock `t4`; for USB exchanges the receiver synthesizes `t1 + (t3 - t2)` because the true host receipt time is recorded separately in `host_receive_monotonic_ns` |
| `rx_radio_t2_us` | Receiver radio timestamp for `t2`; `0` in USB exchanges |
| `tx_radio_t4_us` | Reference radio timestamp for `t4`; `0` in USB exchanges |
| `round_trip_us` | `(t4 - t1) - (t3 - t2)`; `0` in USB exchanges because `t4` is synthesized |
| `receiver_minus_transmitter_us` | Offset estimate (receiver minus reference); receiver minus host in USB sessions |
| `drift_ppm` | Current affine clock-fit drift estimate (receiver versus reference) |
| `uncertainty_us` | Current fit uncertainty estimate |

A header-only file means no exchange was recorded for that receiver. To map
receiver time to the reference timeline, use the clock-fit code in
`fall_detection.radio.acquisition.clock_sync` rather than a single offset row;
the fit accounts for drift and boot changes.

Reading caveats for USB sessions:

- `t1` is the host's `time.monotonic_ns() // 1000`; `t2`/`t3` are receiver
  `esp_timer` microseconds. `t4` is synthetic, and the real host receipt time is
  the first CSV column (later than `t4`). The resulting offset therefore absorbs
  the one-way USB latency, and `round_trip_us` is `0`. Treat the offset as a
  host-timeline alignment, not an exact transmitter-receiver synchronization.
- `radio_timing.csv` carries a third clock domain:
  `tx_enqueue_timestamp_us` is the transmitter's own `esp_timer` from the
  sensing header. This file does not fit transmitter time to host time. If a
  workflow needs transmitter↔receiver alignment, use the frame sequence and
  sensing header, and treat the result as approximate.
- `receiver_boot_id` changing means the receiver rebooted; start a new clock fit
  rather than mixing rows from before and after the reboot.

## 5. How to read the dataset

### 5.1 Session inspector (recommended for browsing and review)

```sh
uv run fall-session-inspector --sessions-dir data/raw/sessions
# or open one session directly
uv run fall-session-inspector data/raw/sessions/20261026T174653764289Z
```

The inspector reads manifests first and loads CSI/timing only when an attempt is
selected. It shows the session and trial tables, exact CSV rows, signal plots,
review fields, and the curated-export action. It requires the `radio` extra
(PySide6 and pyqtgraph):

```sh
uv sync --extra radio
```

For attempts with recorded camera artifacts, add the `video` extra and use the
**Signals** tab to play video alongside CSI. Playback, scrubbing, frame stepping
and plot cursors share seconds from attempt start, using saved host-clock frame
observations and capture timing. Missing or invalid video timing is shown
explicitly; raw files remain unchanged. See
[recorded-session playback](video-recording.md#recorded-session-playback).

### 5.2 Python API

```python
from pathlib import Path

from fall_detection.session_inspector.data import load_attempt_data
from fall_detection.session_inspector.models import scan_sessions

sessions = scan_sessions(Path("data/raw/sessions"))
for session in sessions:
    print(session.session_id, session.status, session.protocol.protocol_id)
    for attempt in session.attempts:
        print(
            attempt.key,
            attempt.trial_ordinal,
            attempt.scenario_id,
            attempt.status,
            attempt.receiver_ids,
        )
        data = load_attempt_data(attempt, attempt.receiver_ids[0])
        print("  csi rows:", data.csi.row_count, "parsed:", len(data.records))
```

Useful entry points:

| Function / object | Use |
| --- | --- |
| `scan_sessions(path)` | Load every session below a directory; invalid children are skipped |
| `load_session(path)` | Load one session; raises `SessionReadError` for an unsupported artifact schema |
| `session.attempts` | All attempts with their relative `key`, status, and receiver files |
| `session.trials` | Planned protocol trials joined with their recorded attempts |
| `attempt.files_for(receiver_id)` | Exact `csi.csv`, `radio_timing.csv`, `usb_clock_sync.csv` paths |
| `load_attempt_data(attempt, receiver_id)` | Parsed CSI records plus exact CSV tables |
| `csi_value_rows(record)` | Per-subcarrier real, imaginary, amplitude, and phase values |
| `prepare_attempt_signals(data)` | Plotting matrices with phase calibration |
| `ReviewStore(session)` | Load/save the review sidecar with optimistic concurrency |
| `export_curated_bundle(session, review, destination)` | Write a reviewed export |

`load_attempt_data` deliberately keeps malformed rows as warnings instead of
raising. Check `data.warnings`, `data.csi.row_count`, and `len(data.records)` if
you need strict validation. Use `parse_csi_line()` directly when a bad row
should be an error.

### 5.3 Building a flat manifest

A manifest is usually the first derived artifact. Keep it derived and
regenerable; do not edit session files to add labels.

```python
from pathlib import Path
import json

from fall_detection.session_inspector.models import scan_sessions

rows = []
for session in scan_sessions(Path("data/raw/sessions")):
    for attempt in session.attempts:
        rows.append(
            {
                "session_id": session.session_id,
                "participant_id": session.manifest.get("participant_id"),
                "protocol_hash": session.protocol_hash,
                "attempt_key": attempt.key,
                "trial_ordinal": attempt.trial_ordinal,
                "scenario_id": attempt.scenario_id,
                "planned_label": attempt.activity_label,
                "status": attempt.status,
                "receivers": ",".join(attempt.receiver_ids),
            }
        )
```

If a review sidecar exists, join it on `attempt_key` (the dictionary key under
`review.attempts`) and prefer the review's `activity_label` when it is not
`null`. Filter out `status != "accepted"` and `inclusion == "exclude"` only when
the experiment protocol says so; keep the excluded attempts in the manifest so
the filtering decision is reproducible.

### 5.4 Direct CSV access

If a job only needs one receiver's frames, bypass the session API but preserve
the directory semantics:

```python
from pathlib import Path
import pandas as pd

attempt = Path("data/raw/sessions/<session-id>/trials/001_.../attempt_01")
receiver = "rx-1"
csi = pd.read_csv(attempt / "receivers" / receiver / "csi.csv")
timing = pd.read_csv(attempt / "receivers" / receiver / "radio_timing.csv")

assert len(csi) == len(timing)
assert (csi["id"].to_numpy() == timing["sequence"].to_numpy()).all()
```

Do not read every receiver into one table and drop the receiver column: the
per-receiver files are the spatial-diversity axis. If you concatenate, add a
`receiver_id` column and keep `attempt_key` + receiver as the unique row key.

## 6. Invariants and gotchas

- **Raw is immutable.** Reviews and corrections go in `session_review.json` or
  a curated export. Never edit `attempt.json` or CSV files in place.
- **One row is one frame for one receiver.** The same transmitted frame appears
  once under every receiver that heard it. Do not de-duplicate across receiver
  directories; that would destroy the spatial diversity.
- **Receiver identity is the directory.** The CSI `mac` is the source
  transmitter. Use `radio_timing.receiver_mac` or the directory name for the
  receiver.
- **Filter the sensing link.** `sig_mode == 4`, `mcs == 0`, and the expected
  transmitter MAC identify the HE20 sensing frames. HT/VHT rows can be present
  from control traffic or other networks.
- **`first_word == 1` means a masked prefix.** Keep the raw values for
  alignment, but do not treat the first two complex values as valid.
- **Timestamps wrap.** `local_timestamp`, `rx_radio_timestamp_us`, and other
  radio timestamps are 32-bit. Use sequence numbers and clock sync; do not
  subtract raw values across a wrap.
- **Rows can be missing.** About 2% frame loss is expected, plus USB batch gaps.
  Align by sequence, not by assuming equal row counts across receivers.
- **Files can be header-only.** An attempt directory is created before frames
  arrive. Check `status` and row counts before treating it as a failed
  experiment.
- **Active sessions are incomplete.** `status: open` or an attempt still in
  `recording` means another process may be writing. Do not review or move the
  directory.
- **Protocol hash binds the review.** Do not copy `session_review.json` between
  sessions; `load_session`/`ReviewStore` will reject the hash mismatch.
- **JSON is canonical-ish.** Keys are sorted and indented, but do not rely on
  byte-for-byte formatting for equality; use the parsed values.
- **Schema mismatch is an error.** A session without
  `artifact_schema_version: 2` is rejected by the reader. Archived schema-1
  sessions must be restored as historical material, not fed to the current
  pipeline.

## 7. Versioning

The repository uses several independent schema versions. Do not confuse them:

| Artifact | Field | Current value |
| --- | --- | --- |
| Session/attempt layout | `artifact_schema_version` in `session.json` and `attempt.json` | `2` |
| Collection protocol | `schema_version` in `protocol.json` | `1` |
| Scenario manifest | `schema_version` in a manifest file | `1` |
| Radio inventory/profile | `schema_version` in the config snapshots | `1` |
| Review sidecar | `schema_version` in `session_review.json` | `1` |
| USB wire envelope | `VERSION` in the firmware/host framing | `1` |

A layout change requires a new `artifact_schema_version`; readers should reject
unknown versions with a clear message rather than guessing. Additive metadata
(such as a new optional `attempt.json` key or a new `environment` key) does not
need a schema bump, but consumers must ignore unknown keys. Removing or renaming
a file, changing a CSV column, or changing the meaning of an existing field does
need a bump.

## 8. Legacy format and cleanup

### 8.1 Schema 1 (obsolete)

Schema 1 was the pre-receiver-split layout. Its attempts kept the streams at the
attempt root and often included camera artifacts:

```text
attempt_01/
├── attempt.json                 # artifact_schema_version 1 (or missing)
├── csi.csv
├── radio_timing.csv
├── clock_sync.csv
├── camera.mp4
├── camera_frames.csv
└── poses.jsonl
```

It had no `receivers/<receiver-id>/` directory, so a file could mix streams that
belong to different receivers. The current collector never writes it; the
session inspector rejects it (`unsupported artifact schema`), and
`tools/processing/prune_data.py --legacy-sessions` reports it.

Pre-session flat captures are also obsolete: `data/raw/csi_<timestamp>.csv`,
`data/raw/radio_timing_<timestamp>.csv`, and
`data/raw/clock_sync_<timestamp>.csv` have no session or trial context. The
current pipeline does not produce or read them.

### 8.2 Cleanup performed on 2026-10-27

Obsolete material was archived (not deleted) before the originals were removed.
The archives are local, git-ignored, and not part of the active dataset:

| Archive | Contents | Size | SHA-256 |
| --- | --- | --- | --- |
| `data/archive/legacy-20261027T123855Z.tar.zst` | 114 flat pre-session captures, 13 empty sessions, 1 camera-era schema-1 session, 1 stale YOLO model directory | 255 MiB | `f83fedd17534f324fd890a240103b2e04ee88acdde41c00f26797b3c3ab69717` |
| `data/archive/legacy-flat-timing-20261027T124235Z.tar.zst` | 3 flat `radio_timing_*.csv` captures | 1.1 MiB | `d3e49867e231f29ef79ae8e7696f0530112c651a7f3b2a47f4d20c62db979eba` |

Each archive has a sibling `.manifest.tsv` recording the category, byte size,
SHA-256 (for files), and original path of every entry. Verify and restore from
the repository root:

```sh
sha256sum -c data/archive/legacy-20261027T123855Z.tar.zst.sha256
tar --zstd -xf data/archive/legacy-20261027T123855Z.tar.zst

sha256sum -c data/archive/legacy-flat-timing-20261027T124235Z.tar.zst.sha256
tar --zstd -xf data/archive/legacy-flat-timing-20261027T124235Z.tar.zst
```

Restoring an archive recreates the old paths under `data/raw/` (and the YOLO
model under `data/models/`). Those files are historical; the current reader will
still reject schema-1 sessions. Use `data/raw/receivers/` only for ad-hoc
captures that follow the current CSV schemas; it is not reviewed or versioned
as a session.

### 8.3 Pruning

`tools/processing/prune_data.py` reports, and with `--apply` removes, data the current
pipeline no longer uses:

```sh
python3 tools/processing/prune_data.py                 # dry run: safe defaults
python3 tools/processing/prune_data.py --verbose       # list every path
python3 tools/processing/prune_data.py --apply         # remove the reported entries
python3 tools/processing/prune_data.py --viewer-captures --keep-days 0 --apply
```

Categories:

- `empty-session` — session directories with zero CSI rows.
- `legacy-session` — sessions whose artifact schema is not 2.
- `viewer-capture` — ad-hoc `data/raw/receivers/` captures (opt-in only).

Paths modified within `--keep-days` (default 7) are never touched, including
empty and legacy sessions.

## 9. Quick reference

```text
session.json                 identity, protocol hash, environment, status
protocol.json                pinned expanded protocol
events.jsonl                 append-only kind/monotonic_ns events
session_review.json          optional review overlay (schema 1)
trials/<NNN>_<scenario>/attempt_<NN>/
  attempt.json               disposition + telemetry
  receivers/<rx>/csi.csv             one row per CSI frame
  receivers/<rx>/radio_timing.csv    one row per CSI row, same order
  receivers/<rx>/usb_clock_sync.csv  one row per clock exchange
```

Most useful commands:

```sh
# Browse and review
uv run fall-session-inspector --sessions-dir data/raw/sessions

# Find sessions
find data/raw/sessions -maxdepth 2 -name session.json -print

# Check the obsolete-data archive
sha256sum -c data/archive/legacy-20261027T123855Z.tar.zst.sha256

# Report removable data
python3 tools/processing/prune_data.py --verbose
```

Related documentation:

- [`data/README.md`](../data/README.md) — directory roles and pruning
- [`configs/collection/README.md`](../configs/collection/README.md) — protocol and scenario selection
- [`src/fall_detection/collection/README.md`](../src/fall_detection/collection/README.md) — collector operation and schema-2 writer
- [`src/fall_detection/session_inspector/`](../src/fall_detection/session_inspector/) — manifest reader, CSV loader, review sidecar, exporter
- [`src/fall_detection/radio/acquisition/protocol.py`](../src/fall_detection/radio/acquisition/protocol.py) — exact `CSI_DATA` parser and formatter

## Derived session Parquet export

`fall_detection.analysis.session_parquet.load_parquet_session(raw, destination)`
builds a versioned analysis export outside the raw data tree. The exploration
notebook uses `data/interim/parquet/<session-id>/`. Install the Parquet reader
with `uv sync --extra analysis`.

| File | Rows and purpose |
| --- | --- |
| `session.json` | Export schema, source manifest/protocol hash, source fingerprint, packet counts, and representation settings |
| `attempts.parquet` | One row per attempt, including retries, status, effective/original labels, review revision, directions, timestamps, and receiver IDs |
| `phases.parquet` | One row per observed collection-cue interval, including intervals containing no CSI |
| `packets.parquet` | One row per CSI record, with scenario/attempt/receiver/review fields, phase, raw metadata, timing, and typed I/Q arrays |

`phase` is `preparation`, `action`, or `resting`, mapped respectively from the
original `collection_phase` values `countdown`, `action`, and `recovery`.
`annotation_source = collection_cue` distinguishes these instructions from
manually annotated movement boundaries. Assignment uses half-open host-clock
intervals `[start_ns, end_ns)` and mapped capture times; rows outside intervals
remain `unassigned`. Missing phases are not fabricated. Invalid phase ordering
or bounds reject the export. These groups do not average, resample, interpolate,
or combine receivers' packets.

`csi_i` and `csi_q` are numeric lists in original raw slot order, corresponding
to the real and imaginary components. They preserve invalid slots and raw
values. Interpret them using the recorded layout fields (`sig_mode`,
`bandwidth`, `stbc`, `first_word`, and `len`); raw slot positions are not a
physical-subcarrier axis. `phase_signal_from_packets()` uses the same physical
layout decoding and masks as `load_phase_signal()` for plotting.

The packet table retains non-sensing and driver-invalid records for auditing;
`is_sensing` marks the standard transmitter/HE20/MCS0 filter, while
`driver_valid` records `rx_state == 0`. `source_row`, sequence, receiver, and
run/boot identities preserve attribution through capture-time sorting.
`capture_time_ns`, `time_source`, `clock_uncertainty_us`, and host-receive timing
remain distinct. Wireless recordings require validated capture sidecars; USB
fallbacks retain their explicit time-source description.

The export streams one receiver recording at a time into Zstandard-compressed
packet row groups. `ParquetSession.read_packets(filters=..., columns=...)`
supports filtering and column selection before loading. Its optional
`arrow_backed=True` keeps a full-session pandas DataFrame in Arrow-backed
columns. Frequent label/review fields are already on packets, so ordinary
scenario/phase queries require no joins. Attempt distributions should use the
attempt table so empty recordings still count once.

All attempts are retained; analysis selects accepted attempts without an
explicit review exclusion. Source file paths, sizes, modification times, and
exporter code form a cache fingerprint. Changes to review, phase events, or
recording inputs rebuild the export. The manifest is published only after a
successful build; this cache check is not a cryptographic raw-data integrity
audit. Active sessions are rejected. Video files and full transport journals
are excluded, so this derived export does not replace the raw session bundle.

## Optional BLE transport sidecars

BLE sessions retain schema-2 attempt CSVs and add independently versioned
`transport/ble/<run-id>/` journals plus per-receiver `ble_timing.jsonl`.
Capture, notification arrival, and processing availability are separate times.
Packets are assigned to attempts by capture time; late delivery cannot backfill
finalized availability bins. See [BLE transport files and wire contract](ble-transport.md).
USB-only sessions do not require these sidecars.

## Scheduled ESP-NOW gateway sidecars

The transmitter reference may use `usb`, the older experimental `ble` path, or
the dedicated `espnow_uart` companion path. The transport manifest records
`transmitter_link`; collection also snapshots it in the session environment.
All three retain the original C5 round timestamps and the same CSI row schema.
Relay mode adds `relay_*` diagnostics to gateway status events, and records a
ten-second minimum baseline for reference-clock drift fitting. See the
[UART relay procedure](uart-transmitter-relay.md) for failure handling and
qualification limits. Gateway USB arrival is never a sensing timestamp.

Gateway sessions use `environment.transport = espnow_gateway` and snapshot the
ordered inventory, sensing profile and gateway policy. Attempt CSV formats are
unchanged; `gateway_timing.jsonl` records run/boot identities, transmitter enqueue
reference, mapped host capture time and clock uncertainty alongside each CSI row.
Readers require that sidecar for capture-time alignment and do not fall back to
USB arrival times. Historical `ble_timing.jsonl` remains supported.

Session journals under `transport/gateway/<run-id>/` contain versioned manifests,
CRC-protected complete envelopes, acceptance events, raw grants/clock/status
messages, conservative channel intervals and immutable 50 Hz availability bins.
See [gateway contracts and qualification](espnow-gateway.md). Host acceptance is
file-buffer acceptance; it does not guarantee persistence through power failure.

Automatic live recovery adds another `transport/gateway/<run-id>/` segment;
it does not append a reboot to the old clock/run domain. The previous journal
records `run_interrupted`; the new manifest's optional `recovery` object and
`run_resuming`/`run_recovered` events link `previous_run_id` and the interruption
`reason`. Collection records `radio_interrupted` and marks an active attempt
invalid. Raw partial files remain available, and no synthetic CSI fills the gap.
See [automatic recovery](automatic-radio-recovery.md).

Buffered gateway acquisition records `host_usb_buffer` limits in the manifest
and periodic/final `gateway_host_buffer` occupancy, queue-wait and group counters
in `events.jsonl`. USB arrival times retain the host read-completion timestamp
for the read completing each frame; they are not replaced by later processing
times. Record `available_ns` still follows validation and recorder acceptance,
so delivery latency includes buffer residence. Gateway status events also retain
`usb_read_ns`. Historical direct-reader timestamps are preserved as recorded.
These optional fields do not change CSI rows or finalized availability masks.

Native processing runs additionally snapshot `host_processing` in session and
gateway manifests: backend/version, selected I/Q kernel and phase algorithm.
Record events may include `native_processing_completed_ns` alongside the
original USB `arrival_ns` and application `available_ns`. Rust buffer diagnostics
separate raw queue/preparation time from completed-frame application wait;
their 200 ms guard applies to native preparation. Recording writer ownership
and the separate handoff bounds are documented in
[native processing](rust-radio-pipeline.md). All fields are additive; historical
recordings remain readable without them.

Optional CGCF-v2 policies add an eight-batch window and early-return grace to the
manifest/fingerprint without changing CSI rows. `CGQE` events 9/10 distinguish
early-return decisions from return-channel API completion; `CGPR` identifies
resumed sensing probes. First sensing-frame recovery remains in receiver status.
See [window/return protocol details](reports/espnow-window-return-2026-11-02.md).

CGCF-v3 manifests also pin minimum revisit time, send-completion guard, bitmap
ACK polling and MAC timing collection. Raw `CGPQ`/`CGPB` requests/replies stay
on the receiver/gateway radio path; host `CGAK` submissions retain their existing
journal format. `CGMT` radio events and decoded `mac_completion_summary` entries
report per-grant MAC durations, failures, late completions and sender ownership
at return. They do not establish host acceptance or capture recovery. The
original CSI/envelope encoding and immutable availability-bin rules are unchanged.
See [transport details](espnow-gateway.md) and
[cadence trial report](reports/espnow-cadence-2026-11-02.md).

CGCF-v4 retains the v3 wire layout and fingerprints its bounded application retry
budget (0–3). Existing v1–v3 budgets remain limited to one retry. Retention trials
can use 750 ms record lifetime and 900 ms availability grace; the one-second
transport metric is unchanged. Preserve each manifest's grace when interpreting
mask counts, because masks from different grace settings are not a controlled
comparison of transport delivery. Fault-injection experiments additionally
journal ACK hold/release events; host acceptance can precede transmission of its
ACK to the gateway. See [retention trials](reports/espnow-retention-2026-11-02.md).

CGCF-v5 adds `application_acknowledgements` to the manifest and fingerprint.
When false, byte 103 bit 2 is set, application retries must be zero, and bitmap
ACKs are forbidden. CSI/envelope bytes and capture-time attribution are unchanged.
`host_acceptance` events record successful validation and recorder acceptance
without sending `CGAK`; `host_acceptance_ack` remains specific to acknowledged
runs. `CGQE` code 11 records local buffer release after MAC send completion,
including failed MAC sends. It does not establish gateway or host receipt.
Lost diagnostic events remain flagged in receiver status; absence of an event
is not evidence of delivery or loss. See [ACK-less trials](reports/espnow-ackless-2026-11-02.md).

Timing-only four-receiver simulations stay separate from acquisition journals.
Their authorization phases and potential sensing coverage do not count as real
receiver records, readiness, clock evidence or missingness masks. A hardware
probe with only one powered receiver records only that receiver even when its
revisit interval approximates a four-receiver cycle. See
[bulk/timing experiment boundaries](reports/espnow-bulk-timing-2026-11-02.md).

CGCF-v6 retains complete CSI/envelope encoding and fingerprints the negotiated
HT20 long-GI MCS0–3 backhaul PHY. Byte 103 bits 3–4 carry its MCS index. Extended
5 GHz profile schema v2 permits up to 120 Hz; historical schema-v1 profiles keep
their original rate limit and fingerprints. Manifests retain the actual profile,
transport policy and radio identities. Firmware hashes, build settings and USB
status distinguish event-worker and CPU-policy treatments; CPU policy is not a
CGCF field. Benchmark reports include `target_records_s` (default 50, explicit
80 for throughput trials). The availability grid remains 50 Hz and its finalized
bins are never revised by late records. See
[higher-throughput experiments](reports/espnow-throughput-2026-11-02.md).

CGCF-v7 additionally permits an explicit record capacity up to 96; older versions
retain their 64-slot limit. Queue occupancy/peak fields retain their existing
meaning and widths. Peak occupancy is a boot-level counter, so high-rate
comparisons reset the identified receiver before each run and retain reset logs.
The experimental 96-slot pool is fingerprinted separately and does not increase
the 64-record submission allowance, 750 ms retention or one-second target.
Role-specific control ingress storage does not truncate any CSI bytes or alter
the gateway's full-envelope journal format.

## Radio configuration input

Live commands load `configs/radio.json` (or `--config <file>`). The session
`environment.radio_config` field records its source path; the resolved
`radio_inventory`, `radio_profile`, `gateway_transport` and their fingerprints
remain the authoritative snapshots. Connection paths are host metadata and do
not alter on-air fingerprints. Historical sessions may instead identify split
inputs in `receiver_config`; their contents and schemas remain unchanged.
# Derived amplitude sequence exports

## Full-rate amplitude sequence export

`data/processed/amplitude_sequence/120hz/<dataset>/` retains every nominal 120 Hz
transmitter sequence position on a shared four-receiver grid. The signal has
the same float32 `[time, receiver, subcarrier]` log1p squared-difference layout
as the 96 Hz export; invalid values remain NaN. Two masks describe different causes:
`isfinite(signal)` is the transformed-signal validity mask, while the adjacent
`signals/<segment_id>.presence.npy` Boolean `[time, receiver]` array records
whether a receiver packet was observed, including packets with invalid CSI.
The `signals.parquet` ledger includes each presence file and its SHA-256 hash.
Segment sequence metadata retains the uint32 sequence coordinate across rollover.
Two-, four-, and six-second windows contain 240, 480, and 720 samples.

Training selects 96 or 120 Hz through `SAMPLE_RATE` in the preprocessing and
training notebooks. Full-rate batches append four receiver-presence channels after
the normalized values and signal-validity channels. Missing values are set to
zero only in the model batch; the export retains NaN. Each run records source
manifest hashes and uses an attempt-level split with training-only normalization.

## 96 Hz amplitude sequence export

The training export is under
`data/processed/amplitude_sequence/96hz/<dataset>/`. It does not alter the raw
session archive. Each `signals/<segment_id>.npy` is a C-order float32 array
with axes `[time, receiver, subcarrier]`. Receiver order is `rx-1` through
`rx-4`; the 245 subcarriers run from -122 through 122. A finite value is the
current `log1p(squared_difference)` training value. NaN marks an invalid
sample; the loader derives the mask from `isfinite` and replaces invalid values
with zero only when constructing a batch. No separate mask tensor is stored.

`window_index.parquet` has one row per 2, 4, or 6 second window. `segment_id`
and relative `signal` select the NPY file; integer `start` is inclusive and
`stop` is exclusive on its 96 Hz time axis. The row also retains target,
coverage, session, participant, run, trial, attempt, and grouping identifiers.
`segments.parquet` keeps segment provenance. `signals.parquet` records one row
per NPY file with `samples`, `bytes`, and `sha256`. `manifest.json` declares
`amplitude_sequence`, preprocessing provenance, coordinates, counts, and
metadata hashes. Validate the file sizes before loading and compare hashes for
a full integrity audit. The Btrfs `compression=none` property applies only to
new signal files; NPY loading does not depend on Btrfs.

To migrate a verified v1 export, run
`uv run python tools/processing/migrate_sequence_segments.py <dataset>`. The converter
reconstructs each segment from indexed windows, requires overlapping values
and validity to agree, and publishes each NPY atomically. It preserves review
tables, figures, and the representative audit segment. The full verification
routine compares every indexed window with its v1 source, including values,
validity, target, and row metadata. Raw recordings are never modified.
