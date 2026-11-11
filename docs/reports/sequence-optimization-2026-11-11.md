# Sequence pipeline optimization: 11 November 2026

Completed-data reuse across all three datasets took 0.638 s,
returning the same 14,543 indexed windows. The benchmark replaced NumPy tensor
loading, raw archive validation, and NPZ writing with functions that raise if
called; none ran on completed cache hits. Only metadata and file identities were
read. This is a warm-cache measurement on this laptop, not a cold preprocessing
benchmark.

A deterministic synthetic sample (seed 42; 32 shards, each containing one
192 × 4 × 245 float64 amplitude window) took
1.085 s with one export worker and
0.223 s with sixteen (4.87× faster in this
single local run). All sixteen worker threads executed tasks. Reusing those
shards took 0.008 s with tensor loading and NPZ writing
blocked. The sample was stored in a temporary directory and removed afterward;
existing recordings and exported tensors were not rewritten.

Native Rayon and the export pool default to all logical CPUs. The export pool
bounds outstanding allocations by `memory_budget_mb` before constructing window
tensors; large jobs may therefore use fewer simultaneous workers. Intermediates
are uncompressed NPY memory maps. A stage adds only new arrays and preserves
unchanged mapped files. This trades additional cold-run scratch space for avoiding
repeated compression; completed-cache reuse requires no scratch arrays.

Source, stage, and shard receipts bind source identity, processing parameters,
code, and output identity. Completed shard receipts are checked before opening
segments or constructing windows. Changed source identities, parameters, or
outputs invalidate the affected cache. Cache metadata assumes ordinary local
file identity semantics; explicit checksum audits remain available for forensic
integrity checks.

Normal export compresses only new final NPZ shards, at deflate level 1. It does
not reload every tensor or rescan every completed checksum. Exact new-shard
reloads require `verify_new_shards=True`; full completed-file checksums require
`load_exported(verify_hashes=True)`. Plots default off in the notebook. No existing
dataset or tensor shard was regenerated. The continuous window overview below
was rendered once to measure the plotting changes.

## Figure rendering

The continuous non-fall representative contains 28,805 samples. Its window
overview used a 1,200-point display preview and at most 24 overlays per duration.
The cold render took 1.361 s and produced one 133,355-byte PNG. Cached redisplay
read and embedded that PNG in 0.0030 s with tensor loading and figure rendering
blocked. This measured the updated bounded overview; no comparable cold timing
was collected for the old dense plot path.
