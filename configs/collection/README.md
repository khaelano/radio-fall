# Collection configuration

Collection protocols are versioned JSON files. The runner expands blocks and
scenario repetitions in the order written, then records each attempt in its
own session bundle. A protocol may either provide inline `blocks` or reference
`scenario_manifests`; each manifest expands its start and end direction lists
as a deterministic Cartesian product. See [`fall_v1.json`](fall_v1.json) and
the six files under [`scenarios/`](scenarios/) for the directional collection
protocol.

The directional protocol contains 288 generated conditions (64 walk→fall, 24
sit→fall, 64 stand→fall, 64 walk→sit, 64 sit→walk, and 8 sit→stand). With two
repetitions per condition, one participant session contains 576 trials. The
resolved blocks and source manifest contents are embedded in the session's
`protocol.json` for reproducibility.
