# Collection configuration

Collection protocols are versioned JSON files. The runner expands blocks and
scenario repetitions in the order written, then records each attempt in its
own session bundle. A protocol may either provide inline `blocks` or reference
`scenario_manifests`; each manifest expands its start and end direction lists
as a deterministic Cartesian product.

| Protocol | Direction grid | Conditions | Trials |
| --- | --- | --- | --- |
| [`fall_v1.json`](fall_v1.json) | 8 — cardinals plus diagonals | 288 | 576 |
| [`fall_simple.json`](fall_simple.json) | 4 — front, left, right, back | 80 | 160 |

`fall_v1.json` with the six files under [`scenarios/`](scenarios/) is the full
eight-direction protocol: 64 walk→fall, 24 sit→fall, 64 stand→fall, 64
walk→sit, 64 sit→walk, and 8 sit→stand conditions.

`fall_simple.json` with [`scenarios/simple/`](scenarios/simple/) is the
four-direction variant: 16 walk→fall, 12 sit→fall, 16 stand→fall, 16 walk→sit,
16 sit→walk, and 4 sit→stand conditions. It keeps the same instruction
templates, timings, repetitions, and family ids, so a cardinal-direction
condition keeps the same scenario id in both protocols; the session's
`protocol_id` and `protocol_hash` record which grid produced a recording.

Two families keep their original asymmetry. Sit→fall only covers forward,
left, and right falls — never backward from a seated position — so it has 12
conditions instead of 16. Sit→stand has no end direction, so it has 4 instead
of 16. That is why the simplified protocol has 160 trials rather than 144.

With two repetitions per condition, one participant session contains 576
trials for the full protocol and 160 for the simplified one. The resolved
blocks and source manifest contents are embedded in the session's
`protocol.json` for reproducibility.
