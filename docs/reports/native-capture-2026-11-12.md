# Native acquisition observations, 2026-11-12

The Rust `capture_probe` executed operational configuration, sensing startup,
relay demultiplexing, continuous reference checks, receiver boot verification,
raw journaling and stop writes without Python acquisition or inference. It used
CGCF bytes encoded from `configs/radio.json` by the existing validated settings
layer. No firmware changed. Each capture ran for approximately ten seconds;
these are short integration observations, not throughput or soak qualification.

| Capture | Accepted batches | Journaled records | Peak waiting batches | Error |
| --- | ---: | ---: | ---: | --- |
| native-capture-20261112-a | 1911 | 3820 | 3 | none |
| native-capture-20261112-b | 1880 | 3757 | 3 | none |
| native-capture-20261112-c | 1912 | 3822 | 3 | none |

All four configured receivers contributed. Capture B recorded 955, 972, 884,
and 946 records in configured receiver order. Application ACKs were disabled in
the supplied configuration, so both probes correctly wrote zero ACKs. This does
not exercise enabled application-ACK hardware behavior. Both completed stop
writes; post-A discovery confirmed gateway `configured=false` and transmitter
`radio_active=false`.

The existing Python reader replayed A's 1911 batches and 3820 records. A predates
reference-event logging and cannot reproduce its live clock estimates. B retains
initial clock samples, 26 gateway-status events, 7934 reference frames and nine
periodic clock requests, plus the operational wire config and health summary.
The native `mapped_replay` tool (now `cargo run -p radio-detection --example mapped_replay -- RUN_JOURNAL_DIR`) reconstructs B's
initial fit, periodic requests, responses and authoritative round validation,
using bounded JSONL reads. It mapped all 3757 record timestamps twice with digest
`35d20eedf8b1aad741b543adca3b173d1e78cbe8bfa0350641bd857afbc00800`.
Mapping uses reference evidence through original USB arrival. Exact live batch
acceptance times were not logged in B, so this does not establish equality with
the delayed live acceptance path. Signal/input parity remains outstanding.

The probes use a 256-envelope pending bound, 750 ms receiver-evidence wait,
2.5-second heartbeat/reference freshness limits and one-second clock-request
interval. These are explicit probe policies. The reference drift baseline is
ten seconds. Read/processing isolation under inference load remains unqualified.
Shutdown sends stop writes but does not drain every remaining forwarded batch;
gateway post-A counters exceeded journaled batches by six. Preserve that limit
when comparing delivery or end-of-segment behavior.

Data is retained through existing DVC configuration without changing remotes:

- `data/experiments/detector/native-capture-20261112-a.dvc`
- `data/experiments/detector/native-capture-20261112-b.dvc`
- `data/experiments/detector/native-capture-20261112-c.dvc`

Capture C adds batch-acceptance events containing original arrival, availability,
run/boot/batch identity and mapped capture timestamps for every record. Native
`cargo run -p radio-detection --example accepted_replay -- RUN_JOURNAL_DIR` reconstructs reference state at acceptance,
checks each event against the raw envelope and requires exact timestamp equality.
All 1912 batches and 3822 records passed, producing digest
`c9a71cae6c7fbc18b5e13e74eb5ba3e3dc2aeef4bf4d1b13dd044715d9311995`.
A temporary event copy with a one-nanosecond capture-time change was rejected;
the original capture was unchanged. This establishes reference-clock replay
equality on C, not offline signal preprocessing or model-input parity.

No model scores were produced. Exact preprocessing contracts, recorded-input
parity, window publication, recovery, frontend integration, performance/thermal
measurements, 30-minute soaks and independently annotated continuous detection
evaluation remain incomplete.
