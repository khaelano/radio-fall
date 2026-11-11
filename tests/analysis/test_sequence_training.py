"""Leakage, input semantics, and model/checkpoint lifecycle checks."""

from dataclasses import asdict
import json
import os

import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.sequence_training_data import (
    Normalizer,
    SequenceDataset,
    ShardStore,
    SegmentStore,
    fit_normalizer,
    split_sequence_attempts,
    prefetched_batches,
)


def test_split_keeps_attempts_and_durations_together():
    rows = [
        {
            "group": f"{dataset}-{target}-{attempt}",
            "dataset": dataset,
            "activity_label": f"activity-{target}",
            "target": target,
            "duration": duration,
        }
        for dataset in ("a", "b", "continuous_non_fall")
        for target in ((0,) if dataset == "continuous_non_fall" else (0, 1))
        for attempt in range(20)
        for duration in (2, 4, 6)
        for _ in range(2)
    ]
    index = pl.DataFrame(rows)
    split = split_sequence_attempts(index)
    assert split.equals(split_sequence_attempts(index))
    assert split.group_by("group").agg(pl.col("split").n_unique())["split"].max() == 1
    assert split.group_by("split").len().sort("split")["len"].to_list() == [
        120,
        360,
        120,
    ]


def test_streaming_normalization_masks_labels_and_training_isolation(tmp_path):
    path = tmp_path / "shard.npz"
    raw = np.full((3, 192, 1, 2), 3.0)
    raw[0, :96, 0, 0] = 0
    raw[0, 0, 0, 1] = np.nan
    raw[1] = 1e20  # Held-out signals must not affect fitted statistics.
    raw[2] = 99
    valid = np.ones_like(raw, dtype=bool)
    valid[2] = False
    np.savez_compressed(
        path,
        squared_difference=raw,
        difference_valid=valid,
        target=np.array([1, 0, 0]),
        receivers=["rx-1"],
        subcarriers=[-1, 1],
    )
    index = pl.DataFrame(
        [
            {
                "path": str(path),
                "shard_row": i,
                "target": target,
                "duration": 2,
                "window_id": i,
                "split": split,
                "dataset": "synthetic",
            }
            for i, target, split in ((0, 1, "train"), (1, 0, "test"), (2, 0, "train"))
        ]
    )
    store = ShardStore(max_bytes=1)  # Exercise the uncached oversized-shard path.
    normalizer = fit_normalizer(index, store)
    np.testing.assert_allclose(normalizer.mean, [np.log(4) / 2, np.log(4)], rtol=1e-6)
    np.testing.assert_array_equal(normalizer.count, [192, 191])
    normalizer.save(tmp_path / "normalizer.npz")
    normalizer = Normalizer.load(tmp_path / "normalizer.npz")
    dataset = SequenceDataset(index, normalizer, store)
    batches = list(dataset.batches(2, seed=42))
    prefetched = list(prefetched_batches(dataset, 2, seed=42))
    for (expected, metadata), (actual, actual_metadata) in zip(batches, prefetched):
        np.testing.assert_array_equal(actual, expected)
        assert actual_metadata == metadata
    assert sum(len(rows) for _, rows in batches) == 3
    for values, rows in batches:
        assert values.shape[1:] == (192, 4)
        assert np.isfinite(values).all()
        for x, row in zip(values, rows):
            if row["window_id"] == 2:
                np.testing.assert_array_equal(x, 0)
            if row["window_id"] == 0:
                assert x[0, 1] == x[0, 3] == 0
    assert store.bytes == 0
    wrong = index.with_columns(pl.lit(0).alias("target"))
    with pytest.raises(ValueError, match="targets differ"):
        list(SequenceDataset(wrong, normalizer, store).batches(2))


def test_segment_slices_keep_nan_mask_and_deterministic_batches(tmp_path):
    signal = np.full((288, 4, 245), 3, dtype=np.float32)
    signal[0, 0, 0] = np.nan
    path = tmp_path / "segment.npy"
    np.save(path, signal)
    frame = pl.DataFrame([
        dict(path=str(path), start=start, stop=start + 192, duration=2,
             target=0, split="train", window_id=i)
        for i, start in enumerate((0, 96))
    ])
    store = SegmentStore()
    normalizer = fit_normalizer(frame, store)
    np.testing.assert_array_equal(normalizer.count[:1], [383])
    dataset = SequenceDataset(frame, normalizer, store)
    first = list(dataset.batches(2, seed=7))
    again = list(dataset.batches(2, seed=7))
    np.testing.assert_array_equal(first[0][0], again[0][0])
    assert first[0][1] == again[0][1]
    assert first[0][0].shape == (2, 192, 1960)
    assert np.isfinite(first[0][0]).all()


@pytest.mark.parametrize("kind", ["cnn", "lstm", "gru"])
def test_model_update_and_checkpoint_round_trip(kind, tmp_path):
    pytest.importorskip("tinygrad")
    from tinygrad import Tensor
    from tinygrad.helpers import Context
    from tinygrad.nn.optim import Adam
    from tinygrad.nn.state import get_parameters
    from fall_detection.analysis.tinygrad_training import (
        MODEL_CLASSES,
        make_training_step,
        TrainingConfig,
        classification_metrics,
        load_checkpoint,
        save_checkpoint,
        ModelPredictor,
    )

    # The interpreter keeps this small regression independent of GPU drivers
    # and external C/LLVM compiler installations.
    with Context(DEV="PYTHON", CACHELEVEL=0):
        Tensor.manual_seed(42)
        x = np.random.default_rng(42).normal(size=(4, 4, 4)).astype(np.float32)
        targets = np.array([0, 1, 0, 1])
        model = MODEL_CLASSES[kind](4, 4)
        parameters = get_parameters(model)
        before = [p.numpy().copy() for p in parameters]
        optimizer = Adam(parameters, lr=0.001)
        step = make_training_step(
            model,
            optimizer,
            1.0,
            TrainingConfig(hidden_size=4, recurrent_chunk_steps=2, micro_batch_size=1),
        )
        # Warm-up, capture, and replay must all update live model parameters.
        for _ in range(4):
            head_before = parameters[-1].numpy().copy()
            loss = step(x, targets)
            assert np.isfinite(loss) and loss >= 0
            assert not np.array_equal(head_before, parameters[-1].numpy())
        assert all(
            p.grad is not None and np.isfinite(p.grad.numpy()).all() for p in parameters
        )
        assert any(
            not np.array_equal(old, p.numpy()) for old, p in zip(before, parameters)
        )
        expected = model(Tensor(x)).sigmoid().numpy()
        assert expected.shape == (4,)
        predictor = ModelPredictor(model, chunk_steps=3)
        # Different inputs exercise warm-up, capture, and replay. The last input
        # follows a weight update, catching accidentally frozen JIT parameters.
        for offset in (0.0, 0.1, 0.2, 0.3):
            if offset == 0.3:
                step(x, targets)
            values = x + offset
            np.testing.assert_allclose(
                predictor(Tensor(values)).numpy(), model(Tensor(values)).numpy(),
                rtol=1e-5, atol=1e-6,
            )
        expected = model(Tensor(x)).sigmoid().numpy()
        save_checkpoint(model, tmp_path / "model.safetensors")
        config = TrainingConfig(hidden_size=4)
        (tmp_path / "config.json").write_text(
            json.dumps(
                {
                    "model": kind,
                    "features": 4,
                    "config": asdict(config),
                }
            )
        )
        Normalizer(np.zeros(2), np.ones(2), np.ones(2)).save(
            tmp_path / "normalizer.npz"
        )
        loaded, _, _ = load_checkpoint(tmp_path)
        actual = loaded(Tensor(x)).sigmoid().numpy()
        np.testing.assert_allclose(actual, expected, atol=1e-6)
        report = classification_metrics(targets, actual)
        assert sum(map(sum, report["confusion_matrix"])) == 4
        empty_positive = classification_metrics(targets, np.zeros(4))
        assert (
            empty_positive["precision"]
            == empty_positive["recall"]
            == empty_positive["f1"]
            == 0
        )


@pytest.mark.skipif(
    os.environ.get("RADIO_TEST_OPENCL") != "1", reason="Opt-in OpenCL driver regression"
)
def test_opencl_cnn_loss_matches_numpy():
    """Catch the large CNN/loss fusion fault seen with Mesa 26.2.6 on Renoir."""
    from tinygrad import Tensor
    from fall_detection.analysis.tinygrad_training import CNNModel, binary_loss

    Tensor.manual_seed(42)
    model = CNNModel(1960, 64)
    x = np.random.default_rng(42).normal(size=(8, 576, 1960)).astype(np.float32)
    targets = (np.arange(8) % 2).astype(np.float32)
    logits = model(Tensor(x))
    actual = float(binary_loss(logits, Tensor(targets), 1.0).item())
    host_logits = logits.numpy()
    expected = float((np.logaddexp(0, host_logits) - targets * host_logits).mean())
    print("OpenCL CNN BCE:", actual, "NumPy:", expected)
    np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-5)


@pytest.mark.skipif(
    os.environ.get("RADIO_TEST_OPENCL") != "1", reason="Opt-in OpenCL JIT regression"
)
@pytest.mark.parametrize("kind", ["lstm", "gru"])
def test_opencl_predictor_replays_across_new_window_boundaries(kind):
    """Catch initial-state versus carried-state JIT signatures on a real device."""
    from tinygrad import Tensor
    from fall_detection.analysis.tinygrad_training import MODEL_CLASSES, ModelPredictor

    Tensor.manual_seed(42)
    model = MODEL_CLASSES[kind](4, 4)
    predictor = ModelPredictor(model, chunk_steps=3)
    rng = np.random.default_rng(42)
    for _ in range(4):
        x = rng.normal(size=(2, 19, 4)).astype(np.float32)
        np.testing.assert_allclose(
            predictor(Tensor(x.copy())).numpy(), model(Tensor(x.copy())).numpy(),
            rtol=1e-4, atol=1e-5,
        )


@pytest.mark.parametrize("kind", ["lstm", "gru"])
def test_recomputed_chunks_match_full_sequence_gradients(kind):
    """Compare every parameter gradient, including across uneven chunk edges."""
    pytest.importorskip("tinygrad")
    from tinygrad import Tensor
    from tinygrad.helpers import Context
    from tinygrad.nn.optim import Adam
    from tinygrad.nn.state import get_parameters
    from fall_detection.analysis.tinygrad_training import (
        MODEL_CLASSES,
        RecurrentStep,
        binary_loss,
    )

    with Context(DEV="PYTHON", CACHELEVEL=0):
        Tensor.manual_seed(17)
        model = MODEL_CLASSES[kind](2, 2)
        parameters = get_parameters(model)
        Tensor.realize(*parameters)
        x = np.random.default_rng(7).normal(size=(2, 19, 2)).astype(np.float32)
        targets = np.array([0, 1], dtype=np.float32)
        inputs = Tensor(x.copy())
        final = model.encode(inputs, model.initial_state(2, "PYTHON"))
        reference_loss = binary_loss(
            model.head(final[0]).reshape(-1), Tensor(targets), 2.5
        )
        reference_gradients = reference_loss.gradient(*parameters)
        Tensor.realize(reference_loss, *reference_gradients)
        expected = [g.numpy().copy() for g in reference_gradients]
        expected_loss = float(reference_loss.item())
        np.testing.assert_allclose(
            model(Tensor(x.copy())).numpy(),
            model.head(final[0]).reshape(-1).numpy(),
            atol=1e-6,
        )
        for micro_batch_size in (1, 2, 3):
            step = RecurrentStep(
                model,
                Adam(parameters),
                2.5,
                1.0,
                chunk_steps=3,
                micro_batch_size=micro_batch_size,
            )
            loss, actual = step.gradients(x, targets)
            np.testing.assert_allclose(loss, expected_loss, rtol=2e-5, atol=2e-6)
            for reference, gradient in zip(expected, actual):
                np.testing.assert_allclose(gradient, reference, rtol=2e-4, atol=2e-5)
