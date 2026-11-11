# Amplitude sequence v1: executed 11 November 2026

All three archives completed at 96 Hz. Every shard was reloaded and checked byte-for-byte; independent checks reconciled labels, attempt bounds, masks, tensor shapes, file sizes, and sampled shard hashes. Raw archives and older derived datasets were preserved.

| Dataset | Selected attempts | Receiver recordings | Segments | Candidate windows | Boundary omissions | Cue omissions | Exported windows | Shards |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| akmal | 231 | 924 | 231 | 5231 | 38 | 1213 | 3980 | 828 |
| continuous_non_fall | 12 | 48 | 12 | 6564 | 24 | 0 | 6540 | 564 |
| khaelano | 232 | 928 | 232 | 5275 | 35 | 1217 | 4023 | 809 |

| Dataset | Duration (s) | Non-fall | Fall |
| --- | ---: | ---: | ---: |
| akmal | 2 | 2007 | 280 |
| akmal | 4 | 888 | 167 |
| akmal | 6 | 530 | 108 |
| continuous_non_fall | 2 | 3580 | 0 |
| continuous_non_fall | 4 | 1780 | 0 |
| continuous_non_fall | 6 | 1180 | 0 |
| khaelano | 2 | 1947 | 366 |
| khaelano | 4 | 860 | 201 |
| khaelano | 6 | 494 | 155 |

The exports contain 14,543 overlapping windows, including 1,277 cue-centered fall windows. These are not independent trials. No training or split assignment was performed. Action cues are approximate activity intervals, not impact annotations. Centered Hampel uses future samples; nearest-round selection has no interpolation or anti-alias filter.

The continuous archive records participant_id `khaelnao`, while the first archive records `khaelano`. Both identifiers were preserved literally. Confirm whether they refer to the same participant before participant-level splitting.

Export encountered the local disk limit. Atomic writes preserved completed shards; exact verified shards were reused on resumption. Selected completed shards were losslessly repacked with NumPy-compatible ZIP_LZMA, with SHA256 equality of every uncompressed NPY member. Manifests and Parquet shard tables record current sizes, hashes, compression methods, and compaction provenance. Only this run’s disposable segment caches were reclaimed.

Stage timers include resumed checks and exclude interrupted attempts; they are not cold-run benchmarks. Per-dataset manifests contain timings and parameters. Figures and reconciliation JSON are under each dataset’s reports directory.

Validation: 697 Python tests passed; nine Rust tests passed, one optional timing test was ignored; strict Clippy and focused Ruff checks passed. The executed notebook retains all six stages for each dataset.

See [preprocessing contract](../amplitude-preprocessing.md) and [executed notebook](../../notebooks/latest/02_preprocess.ipynb).
