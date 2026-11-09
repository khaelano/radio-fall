"""Deterministic checks for shift direction, partition leakage and fitted transforms."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare import assign_splits, inventory, shifted_bin
from support import LABELS, read_json, sha256, write_json
from training import WindowDataset, epoch_offsets, fit_scaler, transform


def test_split_keeps_every_repetition_retake_receiver_and_offset_in_scenario():
    records = [
        dict(
            label=label,
            scenario_id=f"{label}_{direction}",
            trial_ordinal=li * 100 + direction * 10 + rep,
            attempt_id=f"{li}/{direction}/{rep}/{retake}",
            receiver=rx,
            offset=offset,
        )
        for li, label in enumerate(LABELS)
        for direction in range(4)
        for rep in range(2)
        for retake in range(2)
        for rx in ["rx-1", "rx-2", "rx-3", "rx-4"]
        for offset in [-0.5, 0.0, 0.5]
    ]
    table = pd.DataFrame(records)
    result = assign_splits(table, 17)
    assert result.groupby("scenario_id").split.nunique().eq(1).all()
    assert result.groupby("trial_ordinal").split.nunique().eq(1).all()
    assert result.groupby("label").split.nunique().eq(3).all()
    pd.testing.assert_frame_equal(result, assign_splits(table, 17))


def test_shift_sign_and_half_open_boundaries_leave_gaps_missing():
    times = np.array([0.5, 1.0, 1.5, 2.0, 2.5])
    values = np.array(
        [[5.0, 50.0], [10.0, 100.0], [15.0, 150.0], [20.0, 200.0], [25.0, 250.0]]
    )
    cfg = dict(window_seconds=1.0, bin_hz=4)
    early = shifted_bin(times, values, cue=1.0, offset=-0.5, config=cfg)
    center = shifted_bin(times, values, cue=1.0, offset=0.0, config=cfg)
    late = shifted_bin(times, values, cue=1.0, offset=0.5, config=cfg)
    np.testing.assert_equal(early[[0, 2], 0], [5.0, 10.0])
    np.testing.assert_equal(center[[0, 2], 0], [10.0, 15.0])
    np.testing.assert_equal(late[[0, 2], 0], [15.0, 20.0])
    assert np.isnan(early[[1, 3]]).all()
    np.testing.assert_equal(values[:, 0], [5.0, 10.0, 15.0, 20.0, 25.0])


def test_scaler_uses_only_training_and_scheme_permitted_offsets():
    raw = np.array(
        [
            [[[[1.0], [3.0]]], [[[5.0], [7.0]]]],
            [[[[1001.0], [np.nan]]], [[[9999.0], [9999.0]]]],
        ],
        dtype="float32",
    )
    train = np.array([0])
    fixed = fit_scaler(raw, train, [0])
    augmented = fit_scaler(raw, train, [0, 1])
    np.testing.assert_allclose(fixed["mean"], 2)
    np.testing.assert_allclose(fixed["scale"], 1)
    np.testing.assert_allclose(augmented["mean"], 4)
    changed = raw.copy()
    changed[1] *= 100
    np.testing.assert_equal(fixed["mean"], fit_scaler(changed, train, [0])["mean"])
    values = transform(raw[:, 0], fixed)
    assert values.shape == (2, 2, 2, 1)
    assert values[1, 0, 1, 0] == values[1, 1, 1, 0] == 0
    assert values[1, 0, 0, 0] == 999


def test_augmentation_uses_one_reproducible_shift_per_attempt_and_epoch():
    fixed = epoch_offsets(100, 5, 2, "fixed", 17, 1)
    np.testing.assert_equal(fixed, np.full(100, 2))
    first = epoch_offsets(100, 5, 2, "shift_augmented", 17, 1)
    np.testing.assert_equal(first, epoch_offsets(100, 5, 2, "shift_augmented", 17, 1))
    assert set(first) == set(range(5))
    assert not np.array_equal(first, epoch_offsets(100, 5, 2, "shift_augmented", 17, 2))
    with pytest.raises(ValueError):
        epoch_offsets(100, 5, 2, "typo", 17, 1)


def test_window_dataset_preserves_attempt_target_and_uses_selected_offset():
    raw = np.arange(3 * 5 * 4 * 2 * 3, dtype="float32").reshape(3, 5, 4, 2, 3)
    scaler = dict(mean=np.zeros((1, 4, 1, 3)), scale=np.ones((1, 4, 1, 3)))
    data = WindowDataset(raw, np.array([2, 0]), np.array([0.0, 1.0, 1.0]), scaler)
    data.offsets = np.array([4, 1])
    x, y = data[0]
    assert len(data) == 2
    assert y.item() == 1.0
    np.testing.assert_equal(x[:4].numpy(), raw[2, 4])
    np.testing.assert_equal(x[4:].numpy(), 1)


def test_inventory_rejects_active_or_mismatched_review(tmp_path):
    write_json(tmp_path / "session.json", dict(status="open"))
    with pytest.raises(ValueError, match="completed"):
        inventory(tmp_path)
    write_json(
        tmp_path / "session.json",
        dict(status="complete", session_id="abc", protocol_hash="p"),
    )
    write_json(
        tmp_path / "session_review.json", dict(session_id="wrong", protocol_hash="p")
    )
    with pytest.raises(ValueError, match="Review identity"):
        inventory(tmp_path)


def test_training_evaluation_freezes_selection_and_detects_changed_inputs(
    tmp_path, monkeypatch
):
    import training

    cfg = read_json(Path(__file__).resolve().parents[1] / "config.json")
    cfg.update(
        representations=["amplitude"],
        training_seeds=[17],
        max_epochs=2,
        patience=2,
        threads=1,
        batch_size=4,
    )
    table = pd.DataFrame(
        [
            dict(
                attempt_id=f"{split}/{i}",
                scenario_id=f"{split}_{i}",
                split=split,
                target=i % 2,
                label="fall" if i % 2 else "nonfall",
                trial_ordinal=j * 4 + i,
            )
            for j, split in enumerate(["train", "validation", "test"])
            for i in range(4)
        ]
    )
    raw = np.random.default_rng(42).normal(size=(12, 5, 4, 8, 8)).astype("float32")
    np.save(tmp_path / "amplitude.npy", raw)
    table.to_csv(tmp_path / "trials.csv", index=False)
    table.to_csv(tmp_path / "split_before_quality.csv", index=False)
    pd.DataFrame(
        [
            dict(
                attempt_id=row.attempt_id,
                receiver=rx,
                offset_seconds=off,
                amplitude_coverage=0.9,
                packets=300,
                max_gap_ms=30,
                driver_bad_packets=0,
            )
            for row in table.itertuples()
            for rx in cfg["receivers"]
            for off in cfg["offsets_seconds"]
        ]
    ).to_csv(tmp_path / "quality.csv", index=False)
    write_json(
        tmp_path / "manifest.json",
        dict(
            config=cfg,
            arrays_sha256={"amplitude": sha256(tmp_path / "amplitude.npy")},
            trials_sha256=sha256(tmp_path / "trials.csv"),
            split_sha256=sha256(tmp_path / "split_before_quality.csv"),
        ),
    )
    monkeypatch.setattr(training, "cluster_intervals", lambda *a, **k: {})
    training.train(cfg, tmp_path)
    selection_digest = sha256(tmp_path / "selection.json")
    training.evaluate(cfg, tmp_path)
    assert sha256(tmp_path / "selection.json") == selection_digest
    predictions = pd.read_csv(tmp_path / "test_predictions.csv")
    assert len(predictions) == 2 * 5 * 4
    assert (
        predictions.groupby(["scheme", "offset_seconds"])
        .attempt_id.nunique()
        .eq(4)
        .all()
    )
    assert set(predictions.attempt_id) == set(
        table.loc[table.split.eq("test"), "attempt_id"]
    )
    history = pd.read_csv(tmp_path / "training_history.csv")
    assert (
        history.groupby("scheme")
        .updates_per_epoch.unique()
        .apply(lambda x: list(x) == [1])
        .all()
    )
    raw[0, 0, 0, 0, 0] += 1
    np.save(tmp_path / "amplitude.npy", raw)
    with pytest.raises(ValueError, match="Array changed"):
        training.evaluate(cfg, tmp_path)
