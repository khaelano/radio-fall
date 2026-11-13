# Native WebGPU smoke observation, 2026-11-12

Rust `qualify` loaded ONNX Runtime 1.31.1 through ort 2.0.0-rc.15 and
registered WebGPU plugin 0.5.0. Device 5686 matched DRM AMD vendor 0x1002,
device 0x1636. Sessions explicitly requested Vulkan. Driver/capability capture
and direct Dawn adapter identity verification remain outstanding.

The input was a synthetic all-zero float32 tensor `[1,480,1964]`, not a
recorded prepared window. Each model used three warmups and 20 measured calls,
with profiling enabled and a debug Rust executable. Sessions ran separately.
Submission timing includes a CPU input clone and runtime upload/readback; stage
costs were not separated. These observations do not qualify latency or accuracy.

| Four-second model | WebGPU logit | Absolute CPU difference | Observed submission time |
| --- | ---: | ---: | --- |
| CNN | 0.0010996722 | 1.12e-8 | 8.66–13.20 ms |
| LSTM | -0.0407321416 | 7.45e-9 | 1.125–1.215 s |
| GRU | -6.4299225807 | 4.77e-7 | 1.223–1.293 s |

All three satisfy atol=1e-4, rtol=1e-4 on this one fixture. Profiles assigned
Conv/ReduceMean/Gemm to WebGPU for CNN and LSTM or GRU plus Gemm to WebGPU
for recurrent models. Recurrent CPU operations were Slice, Concat, Gather, Mul
and Reshape. Inspected CPU tensor shapes were small int64 shape/control values;
every event still requires auditing before qualification. The auditor now
requires integer/bool tensor-type evidence for explicitly allowed CPU operations.

The profiled recurrent path exceeds the 250 ms target. Measure without profiling,
then investigate synchronization and transfer costs before making a performance
claim. Recorded-input parity, all-nine operator placement, sustained operation,
soaks, and continuous detection evaluation remain incomplete. Logs and profiles
are disposable smoke artifacts under `/tmp/radio-detection-gpu-*`.

An additional unprofiled four-second LSTM run still took 1.126–1.329 s over
20 submissions on the same synthetic input. Profiling overhead therefore does
not explain the observed slowdown. The `qualify` example (`cargo run -p radio-detection --example qualify`) accepts `-` as its
profile argument to disable profiling. `qualify_all` loads verified bundles,
keeps all nine CPU and GPU sessions resident in one native environment, and
compares caller-supplied inputs. It does not verify those inputs' provenance or
operator placement when profiling is disabled.

The all-nine unprofiled synthetic run completed successfully with all sessions
resident and sequential submissions. Every model passed the requested logit
tolerance against explicit CPU diagnostic sessions. Each used three warmups and
20 measured submissions; these are small-sample timing observations, not p99 or
soak qualification. Debug builds and concurrent test-suite activity limit timing
interpretation.

| Model | Median submission (ms) | Maximum absolute logit error |
| --- | ---: | ---: |
| CNN 2 s | 7.251 | 1.19e-7 |
| CNN 4 s | 8.944 | 1.12e-8 |
| CNN 6 s | 9.671 | 1.49e-8 |
| LSTM 2 s | 566.973 | 9.54e-7 |
| LSTM 4 s | 1135.398 | 7.45e-9 |
| LSTM 6 s | 1696.114 | 1.12e-8 |
| GRU 2 s | 616.164 | 0 |
| GRU 4 s | 1236.126 | 4.77e-7 |
| GRU 6 s | 1843.039 | 4.77e-7 |

Observed shared-library SHA-256 values (not distribution-package pins):

- Core: `fc44112fbe06d7d689c57e11d3862031f64711007e4ee020f8eed5185fd2c1d3`
- WebGPU: `fc98b10c7d03537694ff4ea6ebca79ed3b41ca71e316dac3292257ee5f85c95d`
