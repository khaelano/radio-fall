# Shared CNN experiment helpers

`shared.py` contains preprocessing, model and evaluation helpers extracted from
the archived two-receiver pilot. The four-receiver and phase-shifted experiments
import them through `05_four_rx_cnn/support.py`. The pinned CPU environment
and lockfile also come from the pilot; create it with:

```sh
uv sync --project notebooks/shared_cnn --frozen --extra notebook
```

Old experiment selections fingerprinted the original code paths. Prepare and
train a new run before evaluating with these relocated helpers. The archived
pilot retains its original code and recorded results under `notebooks/trash/`.
