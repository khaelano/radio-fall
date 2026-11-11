# Amplitude sequence v2 migration and pilot (11 November 2026)

## Representation and integrity

The v2 export stores one float32 `log1p(squared_difference)` NPY signal for
each segment. NaN denotes an invalid sample. The Parquet window index supplies
the 2/4/6-second slice bounds, target, grouping IDs, coverage, and provenance.
The signal ledger records byte sizes and SHA-256 hashes. The loader maps NPY
files, groups nearby windows, and prefetches one batch without a second signal
cache. New signal files receive the per-inode `compression=none` Btrfs property
before data is written; [Btrfs documents this value and its inode scope](https://btrfs.readthedocs.io/en/latest/btrfs-property.html).

The migration reconstructed each segment from v1 shards and rejected any
conflicting overlap. An independent second pass compared every indexed window's
values, validity, target, and row metadata with v1. All 14,543 windows matched.
With the saved 2-second pilot normalizer, all five windows in `akmal`'s retained
representative segment also produced byte-identical float32 training batch rows
from the saved audit arrays and the v2 loader. The all-window comparison checks
the underlying values and masks; batch order depends on grouping and seed.
The raw session archives were not modified. Review tables and each dataset's
representative audit segment were copied into v2. Existing v1 reports were
preserved byte-for-byte under each v2 `reports/v1/` directory before retirement.
After all gates passed, the derived `amplitude_sequence_v1` directory,
including its NPZ shards and obsolete manifest, was removed. The v2 index and
full signal-hash audit still open all 14,543 windows after removal.

| Dataset | Segments | Windows | Conversion | Independent verification |
| --- | ---: | ---: | ---: | ---: |
| `akmal` | 231 | 3,980 | 68.69 s | 63.76 s |
| `khaelano` | 232 | 4,023 | 66.06 s | 62.51 s |
| `continuous_non_fall` | 12 | 6,540 | 126.86 s | 126.06 s |

The three v2 directories occupy **4,153,126,912 allocated bytes (3.868 GiB)**,
including audit material and reports. Signal lengths projected 3.667 GiB
before migration. The measured complete store is below the 5 GiB gate. All
475 signal ledger entries record the disabled Btrfs compression property;
`btrfs property get` returned `compression=none` on a saved file.

## Loader gate

The `akmal` loader benchmark used one process, a 32-window batch, seed 45,
the same identity normalizer, and sequential v1/v2/v2/v1 passes for each
duration. The operating-system cache was retained; no cache drop was attempted.
The table reports the second pass of each format, so these are warm-cache
comparisons rather than controlled cold-cache measurements. Detailed pass
records are under `data/processed/amplitude_sequence_v2/akmal/reports/`.

| Window | v1 repeat | v2 repeat | v2 / v1 |
| --- | ---: | ---: | ---: |
| 2 s | 29.74 s | 4.07 s | 0.137 |
| 4 s | 26.93 s | 5.05 s | 0.187 |
| 6 s | 26.72 s | 6.69 s | 0.250 |

All three repeated-pass ratios satisfy the gate of at most 1.05. First-pass
times were 29.30/4.64 s (v1/v2) at 2 s, 27.20/5.39 s at 4 s, and 27.68/6.73 s
at 6 s. Their order is fixed by the ABBA design and should not be interpreted
as an independent cold-cache estimate.

## Guarded training pilot

An `akmal`-only seed-42 attempt split selected 36 training, 36 validation,
and 36 test windows at 2 seconds for a three-epoch CNN, LSTM, and GRU pilot.
All three completed training, validation, checkpoint restoration, testing, and
inference in a systemd scope capped at **4,000,000,000 bytes**, with zero swap
and four CPU cores. A separate probe verified the new no-swap enforcement.

| Model | Three-epoch training | Peak worker memory | OOM events |
| --- | ---: | ---: | ---: |
| CNN | 11.23 s | 1,154,801,664 bytes | 0 |
| LSTM | 29.26 s | 1,105,027,072 bytes | 0 |
| GRU | 28.13 s | 1,074,372,608 bytes | 0 |

The pilot artifacts and cgroup resource records are under
`data/processed/tinygrad_segment_pilot/akmal_v2/`. This small subset checks the
loader and guarded execution path; it does not establish model accuracy or a
full-data training time. Earlier v1 model results remain in their original
reports. Raw archives and existing reports remain available.

The full Python suite passed **719 tests with 3 optional tests skipped** after
the reporting fix. The full preprocessing notebook executed against v2 and
saved outputs for all three datasets. The training notebook's setup, combined
index, attempt split, and pilot-normalizer cells executed in a fresh kernel;
its saved model outputs may still reflect the earlier v1 run.
