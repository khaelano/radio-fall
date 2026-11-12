"""Device selection, model bundles, and evaluation for sequence training."""

import json

import numpy as np
import polars as pl
import pytest

torch = pytest.importorskip("torch")

from fall_detection.analysis.sequence_training_data import Normalizer


@pytest.mark.parametrize("device_name", ["cpu", "cuda"])
def test_evaluate_moves_inputs_and_returns_host_metrics(device_name, training_notebook):
    _evaluate = training_notebook["_evaluate"]
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


def test_requested_cuda_fails_when_unavailable(
    tmp_path, monkeypatch, training_notebook
):
    run_cpu_training = training_notebook["train_models"]
    CpuPilotConfig = training_notebook["SequenceTrainingConfig"]
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    frame = pl.DataFrame(
        [
            {"duration": 2, "split": split, "dataset": "synthetic"}
            for split in ("train", "validation", "test")
        ]
    )
    frame_path = tmp_path / "split.parquet"
    frame.write_parquet(frame_path)
    normalizer = tmp_path / "normalizer.npz"
    Normalizer(np.zeros(980), np.ones(980), np.ones(980)).save(normalizer)
    with pytest.raises(RuntimeError, match="CUDA was requested"):
        run_cpu_training(
            frame_path, normalizer, tmp_path / "out", CpuPilotConfig(device="cuda")
        )


def test_notebook_trainer_saves_and_reloads_checkpoint(tmp_path, training_notebook):
    signal_path = tmp_path / "signal.npy"
    signal = np.zeros((6 * 192, 4, 245), dtype=np.float32)
    signal[192:384] = signal[576:768] = signal[960:] = 1
    np.save(signal_path, signal)
    frame = pl.DataFrame(
        [
            {
                "path": str(signal_path),
                "dataset": "synthetic",
                "duration": 2,
                "rate_hz": 96,
                "start": i * 192,
                "stop": (i + 1) * 192,
                "target": i % 2,
                "split": split,
            }
            for i, split in enumerate(
                ("train", "train", "validation", "validation", "test", "test")
            )
        ]
    )
    frame_path = tmp_path / "split.parquet"
    frame.write_parquet(frame_path)
    normalizer_path = tmp_path / "normalizer.npz"
    Normalizer(np.zeros(980), np.ones(980), np.ones(980)).save(normalizer_path)
    config = training_notebook["SequenceTrainingConfig"](
        device="cpu", epochs=1, batch_size=2, hidden_size=2, cpu_threads=1
    )
    output = tmp_path / "model"
    model_output = tmp_path / "models" / "sequence"
    result = training_notebook["train_models"](
        frame_path,
        normalizer_path,
        output,
        config,
        model_kind="cnn",
        model_output=model_output,
    )
    assert result["models"]["cnn"]["test_windows"] == 2
    model = training_notebook["TorchCNN"](1960, 2)
    model.load_state_dict(torch.load(model_output / "cnn-2s.pt", weights_only=True))
    assert not (output / "cnn-2s.pt").exists()
    metadata = json.loads((model_output / "cnn-2s.json").read_text())
    assert metadata["features"] == 1960
    assert metadata["sample_rate_hz"] == 96
    assert (model_output / metadata["normalizer"]).resolve() == normalizer_path
    assert (output / "metrics.json").is_file()
    assert result["runtime"]["device"] == "cpu"
