"""Device selection, model bundles, and evaluation for sequence training."""

import json

import numpy as np
import polars as pl
import pytest

torch = pytest.importorskip("torch")

from fall_detection.analysis.sequence.training_data import Normalizer


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


def test_evaluate_balanced_log_loss_weights_classes_equally(training_notebook):
    class Dataset:
        def batches(self, batch_size, seed=None):
            rows = [{"target": 0}] * 3 + [{"target": 1}]
            yield np.zeros((4, 1), dtype=np.float32), rows

    class Uncertain(torch.nn.Module):
        def forward(self, x):
            return torch.zeros(len(x))

    result = training_notebook["_evaluate"](
        Uncertain(), Dataset(), 4, torch.device("cpu")
    )
    assert result["balanced_log_loss"] == pytest.approx(np.log(2))


def test_evaluate_action_loss_ignores_quiet_non_fall_windows(training_notebook):
    rows = [
        {"target": 1, "center_phase": "action", "activity_label": "sit_to_fall"},
        {"target": 0, "center_phase": "action", "activity_label": "sit_to_stand"},
        {"target": 0, "center_phase": "preparation", "activity_label": "sit_to_stand"},
    ]

    class Dataset:
        def batches(self, batch_size, seed=None):
            # Logits 0, 0 and -10: the quiet window is confidently non-fall.
            yield np.array([[0.0], [0.0], [-10.0]], dtype=np.float32), rows

    class Identity(torch.nn.Module):
        def forward(self, x):
            return x[:, 0]

    result = training_notebook["_evaluate"](
        Identity(), Dataset(), 3, torch.device("cpu")
    )
    assert result["action_balanced_log_loss"] == pytest.approx(np.log(2))
    assert result["balanced_log_loss"] < result["action_balanced_log_loss"]
    assert training_notebook["_is_hard_negative"](rows[1])
    assert not training_notebook["_is_hard_negative"](rows[2])


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


@pytest.mark.parametrize(
    "name",
    [
        "TorchTonePool",
        "TorchTonePoolGeM",
        "TorchTonePoolTemporal",
        "TorchTonePoolTemporalCentered",
        "TorchTinyTCN1",
        "TorchTinyTCN3",
        "TorchTinyCNN3",
    ],
)
def test_tone_pool_ignores_tone_and_receiver_order(training_notebook, name):
    torch.manual_seed(0)
    model = training_notebook[name](1964, 4).eval()
    values = torch.randn(2, 48, 4, 245)
    valid = (torch.rand(2, 48, 4, 245) > 0.2).float()
    present = (torch.rand(2, 48, 4) > 0.2).float()

    def inputs(tones, receivers):
        return torch.cat(
            (
                values[:, :, receivers][..., tones].flatten(2),
                valid[:, :, receivers][..., tones].flatten(2),
                present[:, :, receivers],
            ),
            dim=-1,
        )

    original = model(inputs(torch.arange(245), torch.arange(4)))
    shuffled = model(inputs(torch.randperm(245), torch.tensor([2, 0, 3, 1])))
    assert original.shape == (2,)
    torch.testing.assert_close(shuffled, original)


def test_tiny_energy_collapse_uses_only_valid_tones(training_notebook):
    model = training_notebook["TorchTinyTCN3"](1964, 4).eval()
    values = torch.randn(2, 24, 980)
    valid = (torch.rand(2, 24, 980) > 0.3).float()
    valid[0, 5] = 0  # a sample without any valid tone
    present = torch.ones(2, 24, 4)
    noisy = values + 100 * (1 - valid)  # invalid values must not matter
    mean, spread, coverage = model.collapse(
        torch.cat((noisy, valid, present), dim=-1)
    ).unbind(1)
    count = valid.sum(-1)
    expected = (values * valid).sum(-1) / count.clamp_min(1)
    torch.testing.assert_close(mean, expected)
    torch.testing.assert_close(coverage, count / 980)
    assert mean[0, 5] == 0 and torch.isfinite(spread).all()
    assert sum(p.numel() for p in model.parameters()) == 5505


def test_tone_pool_gem_gradient_is_finite_when_all_tones_are_dropped(
    training_notebook,
):
    model = training_notebook["TorchTonePoolGeM"](1964, 4)
    encoded = torch.full((2, 980, 16, 5), 0.5, requires_grad=True)
    model.pool_peak(encoded, torch.zeros(2, 980, 1, 1)).sum().backward()
    assert torch.isfinite(encoded.grad).all()


def test_tone_pool_centering_removes_each_tones_window_level(training_notebook):
    model = training_notebook["TorchTonePoolTemporalCentered"](1964, 4)
    values = torch.randn(2, 24, 4, 245)
    valid = (torch.rand(2, 24, 4, 245) > 0.3).float()
    shifted = values + torch.randn(1, 1, 4, 245)  # a per-tone level change
    torch.testing.assert_close(
        model.prepare(shifted, valid), model.prepare(values, valid)
    )
    assert torch.all(model.prepare(values, valid)[valid == 0] == 0)


def test_tone_pool_lags_reads_lags_as_channels_of_each_tone(training_notebook):
    torch.manual_seed(0)
    model = training_notebook["TorchTonePoolLags"](2 * 4 * 980 + 4, 4).eval()
    values = torch.randn(2, 48, 4, 4, 245)  # [batch, time, receiver, lag, tone]
    valid = (torch.rand(2, 48, 4, 4, 245) > 0.2).float()
    present = (torch.rand(2, 48, 4) > 0.2).float()

    def inputs(tones):
        return torch.cat(
            (
                values[..., tones].flatten(2),
                valid[..., tones].flatten(2),
                present,
            ),
            dim=-1,
        )

    original = model(inputs(torch.arange(245)))
    # The same tone permutation in every lag leaves the output unchanged.
    torch.testing.assert_close(model(inputs(torch.randperm(245))), original)
    assert original.shape == (2,)


def _pc_spectrum_window(seed: int = 0) -> torch.Tensor:
    """A 4 s window [1, 480, 1964]: low-rank motion plus noise per receiver,
    staggered 12-in-68 receiver gaps and some invalid tones."""
    generator = np.random.default_rng(seed)
    t = np.arange(480)[:, None]
    tones = np.arange(245)[None, :] / 245
    window = np.zeros((480, 1964), np.float32)
    for r in range(4):
        present = (t[:, 0] + 17 * r) % 68 >= 12
        values = (
            2 * np.sin(2 * np.pi * 3 * t / 120) * tones
            + np.sin(2 * np.pi * 37 * t / 120 + r) * (1 - tones)
            + 0.3 * generator.standard_normal((480, 245))
        )
        valid = present[:, None] & ((np.arange(245)[None, :] * 31 + t * 7) % 101 != 0)
        window[:, r * 245 : (r + 1) * 245] = np.where(valid, values, 0)
        window[:, 980 + r * 245 : 980 + (r + 1) * 245] = valid
        window[:, 1960 + r] = present
    return torch.from_numpy(window[None])


def test_pc_spectrum_export_head_equals_the_model(training_notebook):
    torch.manual_seed(0)
    model = training_notebook["TorchPCSpectrum"](1964, 8)
    # Non-trivial batch norm statistics, as after training.
    model.norm.running_mean.normal_()
    model.norm.running_var.uniform_(0.5, 2.0)
    model.norm.weight.data.uniform_(0.5, 1.5)
    model.norm.bias.data.normal_()
    model.eval()
    window = _pc_spectrum_window()
    with torch.inference_mode():
        head = model.head_module().eval()
        torch.testing.assert_close(
            head(model.frame_features(window)), model(window), rtol=0, atol=1e-5
        )
    # The export holds no batch norm: it is folded into the GRU.
    assert not any(isinstance(m, torch.nn.BatchNorm1d) for m in head.modules())


def test_pc_spectrum_features_match_the_native_front_end(training_notebook):
    from fall_detection._radio_native import PcSpectrumFrontEnd

    model = training_notebook["TorchPCSpectrum"](1964, 8).double().eval()
    window = _pc_spectrum_window(seed=1)
    with torch.inference_mode():
        expected = model.frame_features(window.double())[0].numpy()
    raw, updates, _ = PcSpectrumFrontEnd(480).features(window[0].numpy().tobytes())
    assert updates == ["full"] * 4
    native = np.frombuffer(raw, np.float32).reshape(expected.shape)
    np.testing.assert_allclose(native, expected, rtol=0, atol=1e-3)
    assert model.front_end["components"] == model.components
