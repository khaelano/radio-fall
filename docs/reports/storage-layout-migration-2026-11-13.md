# Typed frame storage and version-3 archives, 2026-11-13

The Rust `radio_storage` crate converts raw gateway journals into typed Parquet
tables and rewrites session archives without the data the journals determine.
This report records what was measured on the three non-empty archives in
`data/old_raw/sessions/` (now moved there; the version-3 results live in `data/raw/sessions/`). The design is in the
[storage layout specification](../storage-layout-spec.md). All sessions predate
12 November 2026, so the Rust-era event path was tested only on synthetic
journals.

## Equivalence with the CSV sidecars

Every CSV row of every attempt and receiver was compared with the converted
frame table ([check_storage_equivalence.py](../../tools/processing/check_storage_equivalence.py)).
Compared fields: payload bytes, the header fields, `rssi`, `noise_floor`,
`sig_len`, `rx_state`, transmitter MAC, radio and enqueue timestamps, capture
time, clock uncertainty, run and boot identifiers.

| Archive | Runs | Journal frames | Frames in table | CSV rows | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: |
| `20261109T161519702956Z` | 7 | 1,765,508 | 1,756,649 | 1,756,649 | 0 |
| `20261109T131546367822Z` | 17 | 3,012,186 | 1,342,362 | 1,342,362 | 0 |
| `20261104T081805521126Z` | 31 | 4,404,837 | 1,428,868 | 1,428,868 | 0 |

The tables contain exactly the frames the CSV files held. Re-converting the
newest archive reproduced all three tables byte for byte. The newest session
is almost continuous (99.5 percent of its frames lie inside attempts); the other
two are not (45 and 32 percent), so the default table keeps only frames inside
attempt windows.

## Analysis loader

On the newest session the attempts (19) and phases (50) tables equal those of the
old exporter. Two recordings of 29,184 and 26,613 packets matched the old CSV
loader on about 35 columns, including the I/Q payload, `is_sensing`, capture
times and row order. Reading one 29,184-frame recording takes about 60 ms.
Loading all 1.77 million frames of the session into Arrow takes about 1 s;
a minimal CSV parser manages about 12,400 frames/s.

## Archives

| Archive | Version 2 | Version 3 | Change |
| --- | ---: | ---: | ---: |
| `20261109T161519702956Z` | 2,345,485,001 B | 626,892,070 B | -73% |
| `20261109T131546367822Z` | 2,740,043,006 B | 1,106,160,952 B | -60% |
| `20261104T081805521126Z` | 6,809,840,364 B | 4,896,874,058 B | -28% |
| `20261104T014829774880Z` (empty) | 11,537 B | 9,132 B | -21% |
| Three non-empty archives | 11,895,368,371 B | 6,629,927,080 B | -44% |

The 31-run archive contains 3.3 GB of video that is copied unchanged, so its
saving is smaller; its non-video content shrank from about 3.5 GB to 1.6 GB.
The derived frame tables add 409, 336 and 358 MB on the project volume. Each
migration converted both the source and the result and compared the tables row
for row before publishing; all four passed, and `verify-archive` re-hashed every
member of every result with no problems. The sources were not modified.

Migration takes 2.3, 3.7 and 5.2 minutes for the three non-empty archives.

## Defect found and fixed

The first migration of the 31-run archive wrote a valid file (Python read every
member and CRC) that the `zip` crate could not read back past 4 GiB. Members
copied without recompression were the trigger. The writer now rewrites every kept
member with explicit ZIP64 headers, which removed the problem.

## Limits

- Rust-era sessions (from 12 November) were not available; their conversion is
  covered by synthetic journals only. Run the equivalence tool on a fresh session
  directory before the collector stops writing CSV sidecars.
- The minimum event set that archives must keep, pruning efficiency on real
  data, and uniqueness of capture time across runs are unmeasured.
- Notebook edits made through the notebook bridge are unsaved until the
  notebooks are saved in the editor. Regenerating `data/processed` was not run.
