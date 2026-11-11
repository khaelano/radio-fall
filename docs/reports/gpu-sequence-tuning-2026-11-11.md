# GPU sequence tuning pilot

The local 2-second LSTM pilot used the same saved v2 selection and normalizer
as the larger CPU/GPU comparison: 304 training, 301 validation, and 304 test
windows. Both runs used 32-window effective batches, seed 42, full-sequence
backpropagation, and the 4 GB no-swap worker limit. The only changed setting in
the successful comparison was recurrent chunk length: 32 versus 64 steps.
Operating-system caches were not cleared between the sequential runs.

| Setting | First epoch | Median of epochs 2–3 | Three epochs | Worker peak |
| --- | ---: | ---: | ---: | ---: |
| 32-step chunks | 44.21 s | 14.72 s | 73.65 s | 1.17 GB |
| 64-step chunks | 72.32 s | 12.30 s | 96.93 s | 1.30 GB |

The longer chunks reduced repeat-epoch time by about 16%, while increasing
initial setup by about 28 seconds. On this pilot's observed epoch rates, the
longer setup would be recovered only after about 13 epochs; a complete-data run
may amortize setup differently. The 64-step LSTM completed within the memory
limit with zero recorded OOM events. Its 304 test targets matched the baseline,
and the maximum absolute difference between saved test probabilities was
0.00000763. Existing gradient tests compare recomputed chunks against full
backpropagation across chunk boundaries.

A 64-step, eight-window microbatch LSTM candidate was stopped after its first
repeat epoch took 30.7 s, slower than the 32-step/32-window baseline. A
64-step/32-window GRU candidate was stopped when its cgroup reached 3.74 GB
during setup; it did not record an OOM before the stop. Neither candidate is
recommended as a default. A brief GPU-busy sample was not a controlled comparison
and does not establish a utilization improvement.

The tinygrad notebook now selects 64-step chunks for **2-second full-data LSTM
runs**; `LSTM_2S_CHUNK_STEPS = 32` restores the earlier setting. GRU and other
durations retain 32-step chunks. Full-data performance and the 4- and 6-second
settings remain unmeasured. Pilot artifacts and worker logs are in
`data/processed/sequence_gpu_tuning_64_32/` and
`data/processed/sequence_gpu_tuning_64_8/`.
