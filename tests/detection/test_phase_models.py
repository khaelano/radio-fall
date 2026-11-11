"""Check experimental multi-model phase inference and stale-score protection."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fall_detection.analysis.amplitude import hampel_subcarriers, normalize_subcarriers
from fall_detection.analysis.windows import resample_amplitude
from fall_detection.detection.phase_models import (
    PhaseModelEngine,
    load_phase_models,
    prepare_live_phase_window,
    score_phase_models,
)


def test_live_phase_window_uses_shared_processing_and_keeps_gaps():
    times = np.arange(0, 201, dtype=np.int64) * 10_000_000
    amp = np.column_stack([np.sin(times / 1e9), np.cos(times / 1e9)]).repeat(
        123, axis=1
    )[:, :245]
    amp[(times > 800_000_000) & (times < 900_000_000)] = np.nan
    actual, valid = prepare_live_phase_window(times, amp, 2_000_000_000, 2)
    normalized, _, _ = normalize_subcarriers(amp)
    filtered, _ = hampel_subcarriers(normalized, times / 1e9)
    filtered = filtered.astype(np.float32)
    expected, mask, _, _ = resample_amplitude(
        times / 1e9, filtered, np.isfinite(filtered), np.arange(160) / 80
    )
    np.testing.assert_allclose(actual, expected.astype(np.float32), equal_nan=True)
    np.testing.assert_array_equal(valid, mask)
    assert not valid[68].any()


def test_resampling_does_not_extrapolate():
    values, valid, _, _ = resample_amplitude(
        np.array([1.0, 1.01]),
        np.array([[1.0], [2.0]]),
        np.ones((2, 1), bool),
        np.array([0.99, 1.0, 1.02]),
    )
    np.testing.assert_array_equal(valid[:, 0], [False, True, False])
    assert np.isnan(values[0, 0]) and np.isnan(values[-1, 0])


def test_forest_missing_class_probabilities_are_mapped_correctly():
    class Forest:
        classes_ = np.array([1, 2])

        def predict_proba(self, values):
            return np.array([[0.75, 0.25]])

    models = {(6, "random_forest"): (Forest(), 4)}
    result = score_phase_models(
        models, 6, np.ones((480, 245)), np.ones((480, 245), bool)
    )
    assert result["random_forest"] == {
        "preparation": 0.0,
        "action": 0.75,
        "resting": 0.25,
    }


def test_radio_loss_and_interruption_invalidate_phase_scores():
    radio = {"receiver_macs": ["a"], "transmitter_mac": "b", "profile_fingerprint": "p"}
    engine = PhaseModelEngine(Path("/unused"), radio, ["rx-1"])
    engine.status(True)
    with engine.lock:
        engine.results[("rx-1", 2, "cnn")] = {
            "receiver": "rx-1",
            "duration_seconds": 2,
            "model": "cnn",
            "end_ns": time.monotonic_ns(),
            "generation": 0,
            "coverage": 1.0,
            "probabilities": {"preparation": 0.0, "action": 1.0, "resting": 0.0},
        }
    assert len(engine.status(True)["models"]) == 1
    assert not engine.status(False)["models"]
    assert not engine.status(True)["models"]
    assert engine.generation == 1
    engine.interrupt("reconnect")
    assert engine.generation == 2


def test_input_rejects_wrong_radio_or_unavailable_clock():
    radio = {"receiver_macs": ["a"], "transmitter_mac": "b", "profile_fingerprint": "p"}
    engine = PhaseModelEngine(Path("/unused"), radio, ["rx-1"])
    engine.status(True)
    record = SimpleNamespace(
        mac="b",
        profile_fingerprint="p",
        receiver_mac="a",
        rx_state=0,
        capture_host_monotonic_ns=None,
        capture_clock_uncertainty_us=None,
    )
    engine.on_record(record, time.monotonic_ns())
    assert engine.queue.empty()


def test_load_twelve_model_files_and_score_all_four_types(tmp_path):
    import json

    import joblib
    import torch
    from sklearn.ensemble import RandomForestClassifier
    from torch import nn

    for duration in (2, 4, 6):
        for kind in ("cnn", "lstm", "gru", "random_forest"):
            path = tmp_path / f"{duration}s" / kind
            path.mkdir(parents=True)
            config = {"temporal_bins": 4}
            info = {
                "model": kind,
                "duration_seconds": duration,
                "config": config,
            }
            (path / "metrics.json").write_text(json.dumps(info))
            if kind == "random_forest":
                model = RandomForestClassifier(n_estimators=1, random_state=1).fit(
                    np.zeros((2, 4 * 490)), [1, 2]
                )
                joblib.dump(model, path / "model.joblib")
            else:
                if kind == "cnn":
                    encoder = nn.Sequential(
                        nn.Conv1d(490, 4, 5, padding=2),
                        nn.ReLU(),
                        nn.Conv1d(4, 4, 3, padding=1),
                        nn.ReLU(),
                        nn.AdaptiveAvgPool1d(1),
                        nn.Flatten(),
                    )
                else:
                    encoder = {"lstm": nn.LSTM, "gru": nn.GRU}[kind](
                        490, 4, batch_first=True
                    )
                model = nn.Module()
                model.add_module("encoder", encoder)
                model.add_module("head", nn.Linear(4, 3))
                torch.save(
                    {
                        "kind": kind,
                        "features": 490,
                        "hidden_size": 4,
                        "labels": ("preparation", "action", "resting"),
                        "config": config,
                        "state_dict": model.state_dict(),
                    },
                    path / "model.pt",
                )
    models = load_phase_models(tmp_path, threads=1)
    assert len(models) == 12
    for duration in (2, 4, 6):
        scores = score_phase_models(
            models,
            duration,
            np.ones((duration * 80, 245)),
            np.ones((duration * 80, 245), dtype=bool),
        )
        assert set(scores) == {"cnn", "lstm", "gru", "random_forest"}
        for probabilities in scores.values():
            assert sum(probabilities.values()) == pytest.approx(1)
        assert scores["random_forest"]["preparation"] == 0


def test_interrupt_during_inference_discards_completed_scores(monkeypatch):
    from fall_detection.detection import phase_models

    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(phase_models, "load_phase_models", lambda *args: {})
    monkeypatch.setattr(
        phase_models,
        "prepare_live_phase_window",
        lambda *args: (
            np.ones((160, 245), dtype=np.float32),
            np.ones((160, 245), dtype=bool),
        ),
    )

    def slow_score(*args):
        entered.set()
        assert release.wait(3)
        return {
            kind: {"preparation": 0.2, "action": 0.5, "resting": 0.3}
            for kind in ("cnn", "lstm", "gru", "random_forest")
        }

    monkeypatch.setattr(phase_models, "score_phase_models", slow_score)
    radio = {"receiver_macs": ["a"], "transmitter_mac": "b", "profile_fingerprint": "p"}
    engine = PhaseModelEngine(Path("/unused"), radio, ["rx-1"], grace_ms=0, hop_ms=100)
    engine.start()
    engine.status(True)
    try:
        now = time.monotonic_ns()
        block = SimpleNamespace(
            subcarrier_indices=np.arange(-122, 123),
            amplitudes=np.ones(245),
            raw_phases=np.ones(245),
        )
        for i in range(3):
            stamp = now - 3_000_000_000 + i * 10_000_000
            record = SimpleNamespace(
                mac="b",
                profile_fingerprint="p",
                receiver_mac="a",
                rx_state=0,
                capture_host_monotonic_ns=stamp,
                capture_clock_uncertainty_us=0,
                run_id=1,
                transmitter_boot_id=1,
                receiver_boot_id=1,
                channel_estimate_block=block,
            )
            engine.on_record(record, now)
        assert entered.wait(3)
        engine.interrupt("disconnect")
        release.set()
        time.sleep(0.1)
        assert engine.status(True)["models"] == []
    finally:
        release.set()
        engine.close()
