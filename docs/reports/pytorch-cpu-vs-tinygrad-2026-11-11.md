# CPU PyTorch and tinygrad/OpenCL training pilot (11 November 2026)

The comparison uses the saved `akmal` v2 pilot: 36 training, 36 validation,
and 36 test windows of 2 seconds each. Inputs have 192 time steps and 1,960
channels after validity masks are appended. Both runs use the same attempt
selection (SHA-256 `d24298904143addb5cd1d955d733505f75aa3d3003f06397be8f19e2720de4e6`),
the same saved normalizer (SHA-256 `164faa7e904c33c2ca204ef94354d32da21515bd61122620bd7b11ea5b5c333c`),
seed 42, three epochs, 32-window batches, 64 hidden units, weighted binary
cross-entropy, Adam at 0.001, and gradient clipping at 1. Training times include
loading, validation, and checkpoint selection. The CPU runner and tinygrad
worker were executed sequentially without dropping the operating-system cache.

The CPU is an AMD Ryzen 7 PRO 4750U. PyTorch 2.14.1+cpu used affinity to four
logical CPUs, four intra-operation threads, one inter-operation thread, and its
enabled oneDNN backend. Tinygrad 0.14.0 ran on the integrated Radeon OpenCL
device with Mesa 26.2.6, a four-core CPU quota, and a 4 GB no-swap memory limit.
The CNNs have the same two convolution/pooling/head layout. The recurrent
models are single-layer full-sequence LSTM and reset-after GRU models in both
frameworks; PyTorch uses its native CPU kernels while tinygrad uses 32-step
recomputation with full backpropagation through time. Their initialized weights
and execution graphs are not identical.

| Model | PyTorch CPU 3 epochs | tinygrad GPU 3 epochs | tinygrad / PyTorch | PyTorch repeat epoch | tinygrad repeat epoch |
| --- | ---: | ---: | ---: | ---: | ---: |
| CNN | 1.204 s | 10.406 s | 8.64× | 0.393 s | 1.709 s |
| LSTM | 1.350 s | 28.725 s | 21.27× | 0.440 s | 1.896 s |
| GRU | 1.170 s | 27.011 s | 23.08× | 0.392 s | 1.636 s |

PyTorch CPU was faster for every model in this small pilot. First-epoch
tinygrad times were 6.983 s for CNN, 24.929 s for LSTM, and 23.735 s for GRU;
the CPU times were 0.417, 0.471, and 0.386 s. The GPU first epochs include
tinygrad schedule construction and compilation. Comparing the median of epochs
two and three still gives a 4.17–4.34× tinygrad/PyTorch ratio. These timings
describe this local pilot; they do not predict full-dataset throughput or model
quality. The PyTorch process high-water resident memory reached 0.71 GiB after
CNN and 1.00 GiB after the recurrent models, while the tinygrad workers peaked
at 0.81–1.12 GB in their cgroups. The memory measures have different scopes.

The executed notebook is
[`notebooks/latest/03_training_pytorch_cpu.ipynb`](../../notebooks/latest/03_training_pytorch_cpu.ipynb).
CPU metrics and checkpoints are under
`data/processed/pytorch_cpu_segment_pilot/notebook/20261111T105709133687Z/`;
the paired tinygrad metrics and worker records are under
`data/processed/tinygrad_segment_pilot/akmal_v2_cpu_comparison/`.
The notebook also contains an opt-in complete-data CPU training section for
2, 4, and 6 second windows. That section has not been run.

## Larger stratified pilot

A second 2-second pilot sampled up to 16 windows per existing
dataset/activity/target/split stratum from all three datasets. It used 304
training, 301 validation, and 304 test windows, approximately 8.4 times as
many training windows as the first pilot. The CPU and GPU runs used the same
saved selection and training-only normalizer, with the same three-epoch model
and optimization settings. The CPU ran first; the GPU ran afterward without
clearing the operating-system cache. Each measurement is one run.

| Model | PyTorch CPU, 3 epochs | tinygrad GPU, 3 epochs | tinygrad / PyTorch | CPU repeat epoch | GPU repeat epoch |
| --- | ---: | ---: | ---: | ---: | ---: |
| CNN | 12.479 s | 32.699 s | 2.62× | 3.933 s | 6.501 s |
| LSTM | 12.761 s | 73.652 s | 5.77× | 4.106 s | 14.718 s |
| GRU | 8.860 s | 70.343 s | 7.94× | 2.943 s | 13.068 s |

PyTorch CPU remained faster. The CNN repeat-epoch ratio narrowed from 4.34×
in the smaller pilot to 1.65× here; the LSTM ratio was 3.59× and the GRU ratio
was 4.44×. The pilots differ in dataset composition as well as sample size,
so the change is not a controlled scaling curve. GPU workers peaked at
1.17–1.20 GB and recorded no OOM events. Full-data throughput, other durations,
and model quality remain untested in this comparison. The selection, normalizer,
metrics, checkpoints, and resource records are under
`data/processed/sequence_larger_comparison/`.
