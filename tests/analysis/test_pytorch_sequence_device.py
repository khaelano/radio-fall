"""Device selection and evaluation for PyTorch sequence training."""

import numpy as np
import polars as pl
import pytest

torch = pytest.importorskip("torch")

from fall_detection.analysis.pytorch_cpu_training import (
    CpuPilotConfig,
    _evaluate,
    run_cpu_training,
)
from fall_detection.analysis.sequence_training_data import Normalizer


@pytest.mark.parametrize("device_name", ["cpu", "cuda"])
def test_evaluate_moves_inputs_and_returns_host_metrics(device_name):
    if device_name == "cuda" and not torch.cuda.is_available():
        pytest.skip("NVIDIA CUDA device unavailable")
    device = torch.device(device_name)

    class Dataset:
        def batches(self, batch_size, seed=None):
            yield np.ones((2, 4), dtype=np.float32), [{"target": 0}, {"target": 1}]

    model = torch.nn.Sequential(torch.nn.Linear(4, 1), torch.nn.Flatten(0)).to(device)
    result = _evaluate(model, Dataset(), 2, device)
    assert result["windows"] == 2
    assert 0 <= result["fall_f1"] <= 1


def test_requested_cuda_fails_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    frame = pl.DataFrame([
        {"duration": 2, "split": split, "dataset": "synthetic"}
        for split in ("train", "validation", "test")
    ])
    frame_path = tmp_path / "split.parquet"
    frame.write_parquet(frame_path)
    normalizer = tmp_path / "normalizer.npz"
    Normalizer(np.zeros(980), np.ones(980), np.ones(980)).save(normalizer)
    with pytest.raises(RuntimeError, match="CUDA was requested"):
        run_cpu_training(frame_path, normalizer, tmp_path / "out", CpuPilotConfig(device="cuda"))
