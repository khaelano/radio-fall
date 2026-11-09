"""Check deterministic explicit augmentation and the absence of fitted scaling."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

path = Path(__file__).resolve().parents[2] / "notebooks/trash/06_phase_shifted/run.py"
spec = importlib.util.spec_from_file_location("phase_random20_experiment", path)
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def test_random_shifts_are_reproducible_distinct_and_cover_both_sides():
    config = experiment.read_json(path.with_name("config.json"))
    first = experiment.random_offsets("001/02", config)
    assert first == experiment.random_offsets("001/02", config)
    assert first != experiment.random_offsets("002/01", config)
    assert len(first) == len(set(first)) == 20
    assert all(-0.5 <= value <= 0.5 and value != 0 for value in first)
    assert sum(value < 0 for value in first) == 10


def test_phase_inputs_keep_values_unchanged_and_zero_only_missing_samples():
    values = np.array([[[0.7, -0.2, np.nan]], [[1.0, 0.3, np.nan]]], dtype="float32")
    result = experiment.encode(values)
    np.testing.assert_array_equal(result[:2], np.nan_to_num(values))
    np.testing.assert_array_equal(result[2:], np.isfinite(values))


def test_dataset_exposes_every_shift_with_its_original_label():
    raw = np.random.default_rng(42).uniform(-1, 1, (42, 8, 2, 3)).astype("float32")
    table = pd.DataFrame(dict(window_index=range(42), target=[0] * 21 + [1] * 21))
    dataset = experiment.PhaseDataset(raw, table)
    assert len(dataset) == 42
    for i in range(len(dataset)):
        values, target = dataset[i]
        np.testing.assert_array_equal(values[:8], raw[i])
        assert target.item() == int(i >= 21)


def test_preparation_replaces_failed_shifts_without_reducing_training_quota(
    monkeypatch,
):
    config = experiment.read_json(path.with_name("config.json"))
    calls = []

    def fake(job):
        offsets = job[2]["offsets_seconds"]
        calls.append(offsets)
        q = [
            dict(
                offset_seconds=offset,
                phase_change_coverage=0.1 if len(calls) == 1 and i == 1 else 0.9,
            )
            for i, offset in enumerate(offsets)
            for _ in range(4)
        ]
        return q, dict(phase_change=np.zeros((len(offsets), 8, 2, 3), dtype="float32"))

    monkeypatch.setattr(experiment, "prepare_one", fake)
    rows, values, audit = experiment.prepare_attempt(
        ("unused", dict(attempt_id="001/02", split="train"), config)
    )
    assert len(rows) == len(values) == 21
    assert len(calls) == 2
    assert sum(row["central"] for row in rows) == 1
    assert len({row["offset_seconds"] for row in rows}) == 21
    assert any(not row["qualified"] for row in audit)
    rows, _, _ = experiment.prepare_attempt(
        ("unused", dict(attempt_id="002/01", split="test"), config)
    )
    assert len(rows) == 1 and rows[0]["offset_seconds"] == 0


def test_phase_native_matches_independent_integer_clock_reference(native_record):
    from fall_detection import _radio_native as core

    start = 10_000_000_000
    rows = []
    for i in range(110):
        record, _ = native_record(i + 1, weak=i % 3 == 0, bad=i % 17 == 0)
        rows.extend(
            (record, rx, start - 150_000_000 + i * 40_000_000) for rx in range(4)
        )
    reference = experiment.reference_phase_windows(rows, [start, start + 13_791_235])
    for kernel in ["scalar", "auto"]:
        native = core.CnnPreprocessor(
            [0.0] * 968, [1.0] * 968, kernel=kernel, representation="phase_change"
        )
        try:
            for wi, offset in enumerate([0, 13_791_235]):
                window = native.build(list(reversed(rows)), start + offset)
                raw = np.frombuffer(window.raw_bytes(), dtype="=f4").reshape(
                    8, 100, 242
                )
                np.testing.assert_allclose(
                    raw, reference[wi], atol=1e-6, equal_nan=True
                )
                tensor = np.frombuffer(window.tensor_bytes(), dtype="=f4").reshape(
                    16, 100, 242
                )
                np.testing.assert_array_equal(tensor, experiment.encode(raw))
        finally:
            native.close()


def test_phase_maximum_lag_accepts_exact_150_ms_and_rejects_one_ns_more(native_record):
    from fall_detection import _radio_native as core

    record, _ = native_record()
    start = 10_000_000_123
    native = core.CnnPreprocessor(
        [0.0] * 968, [1.0] * 968, representation="phase_change"
    )
    try:
        for extra in [0, 1]:
            rows = [
                (record, rx, time)
                for rx in range(4)
                for time in [start - 150_000_000 - extra, start]
            ]
            window = native.build(rows, start)
            tensor = np.frombuffer(window.tensor_bytes(), dtype="=f4").reshape(
                16, 100, 242
            )
            assert np.all(tensor[8:, 0] == (1 if extra == 0 else 0))
    finally:
        native.close()


def test_phase_native_constructor_rejects_fitted_scaling():
    from fall_detection import _radio_native as core

    with pytest.raises(ValueError, match="identity parameters"):
        core.CnnPreprocessor([1.0] * 968, [2.0] * 968, representation="phase_change")


def test_training_visits_every_materialized_window_and_saves_unscaled_checkpoints(
    tmp_path,
):
    config = experiment.read_json(path.with_name("config.json"))
    config.update(max_epochs=2, patience=2, threads=1)
    rows = []
    for split in ["train", "validation", "test"]:
        for target in [0, 1]:
            offsets = (
                [0.0] + list(np.linspace(-0.49, 0.49, 20))
                if split == "train"
                else [0.0]
            )
            rows.extend(
                dict(
                    attempt_id=f"{split}/{target}",
                    scenario_id=f"{split}_{target}",
                    split=split,
                    target=target,
                    offset_seconds=offset,
                    central=offset == 0,
                )
                for offset in offsets
            )
    table = pd.DataFrame(rows)
    table.insert(0, "window_index", range(len(table)))
    table.to_csv(tmp_path / "windows.csv", index=False)
    table.drop_duplicates("attempt_id").to_csv(tmp_path / "trials.csv", index=False)
    raw = (
        np.random.default_rng(42).uniform(-1, 1, (len(rows), 8, 8, 8)).astype("float32")
    )
    np.save(tmp_path / "phase_change.npy", raw)
    experiment.write_json(
        tmp_path / "manifest.json",
        dict(
            config=config,
            windows_sha256=experiment.sha256(tmp_path / "windows.csv"),
            trials_sha256=experiment.sha256(tmp_path / "trials.csv"),
            arrays_sha256={
                "phase_change": experiment.sha256(tmp_path / "phase_change.npy")
            },
        ),
    )
    experiment.train(config, tmp_path)
    history = pd.read_csv(tmp_path / "training_history.csv")
    assert history.windows_per_epoch.eq(42).all()
    assert history.updates_per_epoch.eq(3).all()
    assert set(history.seed) == {17, 29, 43}
    assert len(list((tmp_path / "models").glob("*.pt"))) == 3
    assert not list((tmp_path / "models").glob("*.npz"))
    selection = experiment.read_json(tmp_path / "selection.json")
    assert selection["normalization"] == "none"
