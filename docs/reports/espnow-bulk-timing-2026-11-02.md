# Larger bursts and four-receiver timing model, 2 November 2026

The timing-only model represents four fixed receiver lanes. A separate hardware
experiment uses the one powered receiver, rx-1 (`44:bd:8d:d0:b1:4c`), paced to
nominal four-receiver revisit intervals. It produces real CSI for rx-1 only.
No CSI or device readiness is fabricated for the other three receivers, and the
model is never substituted into hardware acquisition journals.

## Timing model

`src/fall_detection/radio/experiments/timing.py` models one authorized receiver
at a time and requires its return confirmation before any successor departure.
It assumes all receivers initially ready, 80 Hz sensing, two sensing rounds of
announcement lead, and confirmation processed on the first sensing tick at or
after slot expiry. Under that conservative assumption, 50, 80, 100 and 125 ms
slots produce nominal per-receiver revisit intervals of 300, 450, 500 and 600 ms.
Actual firmware can process control between sensing ticks, return early, skip a
grant or defer a successor; these modeled intervals are not measured guarantees.

The timeline splits each authorization illustratively into a 5 ms departure
guard, a 5 ms outward switch, a 2.4 GHz authorization interval, and a 10 ms
return/confirmation reserve. This phase split does not reproduce the receiver's
sensing-witness-aligned send cutoff or establish actual switching time. The
upload phase does not mean continuous transmission. It omits RF contention,
MAC retry timing, clock uncertainty, power behavior and CSI generation.

A lost-return case stops new authorizations after rx-2 and keeps its channel
state unknown. At most one receiver is off-channel or unconfirmed in this model;
at least three remain potential sensing receivers. This is a consequence of the
modeled interlock, not independent proof of physical receiver coverage or
available model-input data. The C/Python regression cross-checks nominal grant
start/end/owner sequences against the actual shared firmware scheduling helpers.
Other tests check all four durations and missing-return behavior.

## Hardware experiment

The user clarified that only rx-1 was powered. Initial attempts expecting four
receivers failed preflight and are retained under
`data/experiments/gateway/bulk-windows-20261102T052739Z/`. One initial attempt
also overlapped USB discovery with acquisition startup and is invalid. After a
transmitter USB reset, the links worked but only rx-1 reported readiness. Those
failed attempts are not included in rate comparisons.

The valid single-receiver experiment is under
`data/experiments/gateway/bulk-single-20261102T062506Z/`. The transmitter was
temporarily provisioned with the one real receiver, keeping 5 GHz channel 44,
HE20 MCS0 and 80 Hz sensing. The gateway stayed at 2.4 GHz channel 6, HT20 MCS0.
No receiver firmware was reflashed. All runs use four outstanding batches,
64 record slots, 750 ms retention, two retries, a 150 ms ACK timeout, 5 ms
departure guard, 10 ms send guard, 10 ms return reserve and 900 ms availability
grace. The per-turn record allowance and window/revisit duration are varied
explicitly at the user's request; normal defaults remain unchanged.

The receiver is held on 5 GHz between its authorized turns using the existing
minimum-revisit setting. This controls its own capture/upload cadence but does
not reproduce the other three receivers' RF traffic, gateway load, sensing
unicast workload, clock behavior or power draw. Different observation windows
and sequential radio conditions limit attribution.

Each initial screen uses 5 s warm-up and 30 s measurement. The strongest screen
is repeated with 30 s warm-up and 60 s measurement. Results below count unique
valid records accepted within one second, including clock uncertainty.

| Run | Window / revisit (ms) | Record allowance | Timely records/s | Delay p99 / max (ms) | Queue growth |
| --- | --- | --- | --- | --- | --- |
| window50 | 50 / 300 | 16 | 18.27 | 770.16 / 778.46 | 0.0 |
| window80 | 80 / 450 | 32 | 31.33 | 766.28 / 775.70 | 0.0 |
| window100 | 100 / 500 | 40 | 43.60 | 767.77 / 770.59 | 2.0 |
| window125 | 125 / 600 | 48 | 49.53 | 765.47 / 775.25 | -2.0 |
| best-repeat | 125 / 600 | 48 | 49.33 | 766.15 / 772.83 | -4.0 |

All delivered records were subsecond. Larger, less frequent visits improved
this receiver's delivered rate from 18.27 to 49.53 records/s in screens and
49.33 records/s in the repeat. The repeat remains below the unchanged
50-record/s target. The 100 ms screen failed the existing queue-growth check
(growth 2.0); other paced screens passed it. These results do not qualify four
receivers or justify changing the acceptance threshold.

All observed recovery intervals were before deadline except one uncertain
classification in the 50 ms screen. Complete channel evidence remained false
for the paced runs; unproven grants are listed in their original reports. The
100/125 ms screens and repeat flagged lost queue diagnostic events. Their
submission-event counts therefore cannot be treated as complete burst totals.
Accepted envelopes/records remain validated independently. Longer bursts expose
the bounded diagnostic queue's capacity as a separate instrumentation limit.

The single-receiver availability masks, per-second distributions, longest gaps,
clock/grant evidence and queue checks remain in the raw journals and derived
`comparison.json`. They contain only rx-1. Modeled four-receiver coverage is
stored separately in `four-receiver-timing-model.json`; it is not a measured
four-receiver availability mask.

## Restoration and verification

After the paced tests, a 1 s warm-up/10 s original-default single-receiver smoke
delivered 40.2 records/s, with 198.15 ms p99 and 255.09 ms maximum delay. It used
unrestricted single-receiver revisit timing, so it is not a matched comparison
with the paced 300–600 ms cases. Its queue-growth check failed (growth 1.5);
this short smoke establishes restoration/start/stop, not sustained stability.

The transmitter's four-peer roster was restored and verified by a configuration-only
handshake against the full inventory. Sensing was not started in that check;
the three unpowered receivers were not falsely marked ready. Original transport
defaults and the 80 Hz sensing profile are retained. The full suite passed
371 tests, including six new timing-model checks. The interactive model's
JavaScript syntax, control logic and 320/736 px layout bounds were checked
without a browser. Browser file preview was blocked by its URL policy; no
alternative browser path was used.

Generic four-receiver policies for future hardware tests are available as
`configs/radio/espnow_transport_bulk_80ms.json`, `..._100ms.json` and
`..._125ms.json`. Those files do not impose a per-receiver revisit override,
because a real four-board scheduler determines the cadence. The actual single
receiver overrides are preserved in the experiment directory. Neither the
four-radio bulk configuration nor all-four supply behavior has been measured.
