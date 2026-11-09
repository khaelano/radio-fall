# Collection configuration

The default protocol is [`fall_simple.json`](fall_simple.json), protocol id
`fall-collection-simple-v2`. It uses Walk (`w`), Stand (`d`), Sit (`s`), and
Fall (`f`) with four directions in the order front, right, back, left.
The first letter identifies the starting activity and the second the ending
activity. Each direction pair has two consecutive repetitions.

| Transition | Start directions × end directions | Conditions | Trials |
| --- | --- | --- | --- |
| `wd` — walk → stand | 4 × 1 | 4 | 8 |
| `ws` — walk → sit | 4 × 4 | 16 | 32 |
| `wf` — walk → fall | 4 × 4 | 16 | 32 |
| `dw` — stand → walk | 1 × 4 | 4 | 8 |
| `ds` — stand → sit | 4 × 4 | 16 | 32 |
| `df` — stand → fall | 4 × 4 | 16 | 32 |
| `sw` — sit → walk | 4 × 4 | 16 | 32 |
| `sd` — sit → stand | 4 × 4 | 16 | 32 |
| `sf` — sit → fall | 4 × 3; no back fall | 12 | 24 |
| **Total** | | **116** | **232** |

For `wd`, standing has no requested end direction (`null`). For `dw`, standing
has no requested start direction (`null`). The other standing transitions
retain all four requested orientations, including the end orientation in `sd`.
Directions retain the existing `participant_relative` frame; changing the
collection order does not reinterpret historical directions. Establish the
reference orientation before recording and keep it consistent throughout the
session.

## Collection order and equipment

The runner uses `trial_order: "equipment"` to group the actual trial queue
across activity blocks. The block checkboxes still select individual transition
families. Selecting a subset retains the same ordering policy.

| Stage | Equipment | Transitions | Conditions | Trials |
| --- | --- | --- | --- | --- |
| 1 | Clear floor | `wd`, `dw` | 8 | 16 |
| 2 | Chair only | `ws`, `ds`, `sw`, `sd` | 64 | 128 |
| 3 | Chair and mattress | `sf` | 12 | 24 |
| 4 | Mattress only | `wf`, `df` | 32 | 64 |

Start with a clear collection area. Add the chair for stage 2, add the mattress
for stage 3, then remove the chair for stage 4. The mattress stays in use through
the final stage. This groups all chair use and all mattress use into consecutive
stages, avoiding repeated removal and reintroduction of either item.

Within stage 2, finish every transition for one chair orientation before
rotating it: front → right → back → left. The chair orientation is the end
direction for `ws` and `ds`, and the start direction for `sw`, `sd`, and `sf`.
Stage 3 visits left → back → right → front, continuing from the last chair
orientation of stage 2. Stage 4 places `wf` and `df` with the same start/fall
direction pair together. Both repetitions of a condition remain adjacent.

The operator's current-scenario card and detail card show equipment and chair
orientation. Place the mattress for the requested fall before starting a trial;
matching direction pairs share a setup, but this ordering does not calculate a
shortest path for moving a mattress in a particular room. The fixed setup order
also groups activities in time; account for session and setup effects in later
evaluation.

## Files, timing, and reproducibility

The nine manifests under [`scenarios/simple/`](scenarios/simple/) define the
four-direction matrix. `equipment` selects `none`, `chair`,
`chair_and_mattress`, or `mattress`; `chair_direction` selects which direction
list (`start` or `end`) determines the chair orientation. The loader expands
these into scenario attributes before ordering the queue. Timing remains
5 s countdown, 8 s action, and 5 s recovery per trial.

The resolved blocks, source manifests, and ordering policy are embedded in the
session's `protocol.json` and covered by its hash. Loading that snapshot
recreates the execution order without reading the external manifests. Use
`protocol.trials` for execution order; block order alone does not describe the
equipment-grouped queue.

[`fall_v1.json`](fall_v1.json) retains the earlier eight-direction protocol:
288 conditions and 576 trials across six families. It remains selectable with
`--protocol configs/collection/fall_v1.json`. The old four-direction protocol
had 80 conditions and 160 trials; its recordings keep their pinned snapshots.
The revised four-direction protocol has a new protocol id. Existing condition
ids are reused where the activity and direction pair are unchanged.
