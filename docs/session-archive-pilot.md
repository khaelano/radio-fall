# Raw session archive contract, versions 1 and 2

This is the accepted raw format for a closed schema-2 session. One ZIP64 file
contains one complete session and Parquet representations of its receiver
tables. Readers support the original version-1 archives and version-2 archives
with directly recorded Zstandard members.
The collector publishes `<session-id>.zip` after the application exits and
radio, video and buffered writers have closed. During collection it uses a
recoverable schema-2 working directory whose CSI CSVs, radio/clock timing,
session events, transport events, availability and binary envelopes are written
as `.zst` files by the native worker. Each admitted disk batch is compressed
into an independent complete Zstandard frame at level 1 before writing; the
existing bounded RAM queue and configurable flush interval still apply. No
plain copy of those streams is written to disk. Mutable JSON manifests and
the optional video frame index remain plain; MP4 video is already encoded. A failed finalization retains that
directory and reports failure; it never publishes a partially verified archive.
Resuming a working session produces a new numbered archive revision on exit.

## Layout and preservation

- `manifest.json` is UTF-8 JSON with `format` set to
  `fall-detection-session-archive`, `version` set to `1` or `2`, `session_id`, and
  `files` and `tables` arrays.
- `original/<relative path>` contains every regular file from the source
  session, byte-for-byte. Paths use forward slashes, are relative to the
  session root, and cannot contain `.` or `..` components. Symbolic links and
  non-regular files are rejected. Empty directories and filesystem metadata
  are not preserved.
- Each `files` entry has `path`, `size` and lowercase `sha256`, describing the
  original uncompressed bytes. The set of entries must exactly match the
  `original/` members. The manifest is an integrity inventory, not a signature.
- `tables/<relative path>.parquet` contains a Zstandard-compressed Parquet
  representation for each receiver `csi.csv`, `radio_timing.csv` and
  `usb_clock_sync.csv`. Each `tables` entry maps `source` to `path` and records
  `rows`, `size` and `sha256` for the Parquet bytes. Column order and all CSV
  field values are preserved as strings; no numerical types are inferred. The
  original CSV remains in the archive to preserve exact bytes.
- Other files, including frame timing, event journals, transport envelopes,
  manifests, reviews and video, are retained in `original/`. CSV tables outside
  the three receiver names do not receive a Parquet copy in this pilot.
- Original MP4 files are stored without ZIP compression. Other original files
  use ZIP DEFLATE level 1. Parquet files are stored without ZIP compression
  because their contents are already Zstandard-compressed. ZIP64 permits large
  files. Readers use the ZIP central directory for member lookup.

## Version 2: direct Zstandard recording

The archive stores each native `.zst` stream under `original/<relative>.zst`
using ZIP STORED, preserving its compressed bytes without another compression
pass. Its file entry retains physical `size`/`sha256` and adds `encoding: zstd`,
`logical_path` (the relative name without `.zst`), `logical_size` and
`logical_sha256`. Logical names must be safe and unique. Readers expose the
logical names, decode concatenated frames, and verify logical hashes during
full verification. Extraction produces original logical files and verifies the
logical hashes. Parquet tables map to logical CSV names. Finalization builds
Parquet from a streaming decoder without restoring CSV files on disk.

Resume appends complete frames to the compressed session event stream. Legacy
plain-directory sessions retain plain writing when resumed, to avoid mixing
encodings in an existing file. Incomplete final Zstandard frames are rejected;
a crashed recording with such a tail needs explicit recovery before resume.
This change does not promise power-loss durability or change the pending-data
loss window set by the recording flush interval.

## Creation and verification

The exporter accepts only sessions whose manifest status is neither `open`
nor `recording`; do not export a session being modified. It rejects symlinks,
requires a new destination outside the source, writes a temporary archive in
the destination directory, and publishes it only after verification. It checks
that source file identity, size and modification time remain stable during
export and that the source inventory has not changed. On POSIX it also holds
the session event-file lock for the export, rejecting concurrent collectors or
exporters. Arbitrary external programs that ignore that lock can still modify
a session; the inventory checks do not protect against every such mutation.

Before publication the exporter reads every archive member, verifies SHA-256
and sizes against the manifest, and compares every Parquet table's parsed rows
with its source CSV while creating it. Parquet verification preserves parsed
field values, while the original members preserve exact file bytes. The ZIP CRC
provides an additional accidental-corruption check. An archive reader must
reject duplicate names, unsafe paths, unknown versions, missing or extra
members, and mismatched checksums when performing a full verification.

Archives are immutable. Resume uses the retained working directory. Existing
notebook and inspector directory APIs can use a verified extraction; edits to
that extraction do not modify the raw archive. Authentication and live archive
append/recovery are not implemented. Migration retains the old directories.

The shared `fall_detection.storage.Recording` API accepts a directory or archive.
Opening an archive checks the full inventory and every checksum. `open(path)`
returns an original binary stream, `read_json(path)` reads metadata, and
`read_table(path, columns=...)` returns an Arrow table with lossless string
fields. Full verification on open can take time for a large session; reuse the
context across reads. Table reads currently load the selected recording table
into memory. Parquet reads use the stored archive member as a seekable input.

```python
from fall_detection.storage import Recording

with Recording("data/raw/sessions/<session-id>.zip") as recording:
    session = recording.read_json()
    recording.extract("data/interim/extracted/<session-id>")
    recording.compare_source("data/raw/sessions/<session-id>")
```

Extraction writes a new directory, checks extracted hashes, and publishes the
directory only on success. `compare_source` checks the complete original file
inventory and compares every byte through the same member streams used for
extraction. Neither operation modifies the archive or the source directory.

Create or verify an archive with the `radio` or `analysis` extra installed:

```sh
python tools/processing/pilot_session_archive.py create data/raw/sessions/<session-id> data/interim/<session-id>.zip
python tools/processing/pilot_session_archive.py verify data/interim/<session-id>.zip
python tools/processing/migrate_session_archives.py data/raw/sessions
```

## Pilot measurement

The local pilot used the closed session `20261109T161519702956Z`, which has no
video. Its 354 original files total 7,488,795,621 bytes. The verified archive
at `data/raw/sessions/20261109T161519702956Z.zip` is
2,345,485,001 bytes: 31.32% of the source size, a 68.68% reduction. It also
contains 228 Parquet tables with 3,513,298 rows; their uncompressed ZIP-member
sizes total 626,808,084 bytes. This is one session and does not predict the
compression ratio for sessions containing video or different transport data.
The original session remains unchanged.

## Migration of existing sessions

All four local schema-2 session bundles were migrated to sibling raw ZIP files
under `data/raw/sessions/`. Each archive passed full checksum verification and
an independent comparison of its original-member inventory and every file byte
against the old directory. The migration journal is
`data/raw/sessions/archive-migration.jsonl`. Across 9,837 files, source bytes
total 32,264,634,128 (30.049 GiB); archive bytes total 11,895,379,908
(11.078 GiB), a 63.13% reduction in representation size. At the user's later
request, all four original directories were deleted after a fresh full archive
verification and byte comparison. Receipts are recorded in
`data/raw/sessions/legacy-removal.jsonl`. Other recordings were not removed.

The small real session was also physically extracted through `Recording.extract`
and its seven files (106,107 bytes) compared successfully. That temporary
extraction copy has since been removed; the verified source archive remains.
Automated tests
exercise exact CSV and binary extraction, Parquet field equality, changed-byte
detection, lock rejection and collector cleanup ordering. The large-session
comparisons stream every original archive member through the same access API
used by extraction, without requiring another complete uncompressed copy.

The notebook loaders `load_parquet_session` and `load_amplitude_session` accept
raw ZIP paths. A cache rebuild extracts only session metadata and receiver
files into a temporary directory; it excludes transport journals and video and
removes the temporary files afterward. Archive manifest and exporter-code
fingerprints validate subsequent cache reuse. Existing derived windows remain
the inputs to the training notebook.

Fresh loading-cell runs for exploration, preprocessing and amplitude comparison
completed after removing the source directories. For the two selected sessions,
the rebuilt packet tables contain the same 2,771,230 packets, recording counts
and protocol hashes as before. Ordered logical row fingerprints across all
packet columns also match. The validation record is
`data/interim/archive-notebook-validation.json`; no temporary analysis extracts
remain after the run. Existing notebook kernels should be restarted before
rerunning cells so imports use the updated shared loaders.
