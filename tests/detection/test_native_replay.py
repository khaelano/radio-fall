"""Replay a recorded native capture through the Rust detector and check inputs."""

import json
import time
from pathlib import Path

import numpy as np
import pytest

from fall_detection.apps.detector import gui

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "data/experiments/detector/native-capture-20261112-c"
MODELS = ROOT / "artifacts/model"


def _offline_inputs(capture: Path) -> tuple[int, int, np.ndarray, np.ndarray]:
    """Recompute aligned log1p squared differences with the offline functions."""
    from fall_detection._radio_native import prepare_magnitude, read_envelopes

    from fall_detection.analysis.preprocessing.amplitude import hampel_subcarriers
    from fall_detection.analysis.preprocessing.sequence_preprocessing import (
        align_samples,
        sequence_offsets,
        squared_difference,
    )

    config = (capture / "radio.cgcf").read_bytes()
    receivers = [
        ":".join(f"{b:02x}" for b in config[44 + i * 6 : 50 + i * 6]) for i in range(4)
    ]
    (journal,) = (capture / "transport/gateway").iterdir()
    columns = {
        mac: {"seq": [], "i": [], "q": [], "fw": [], "dv": []} for mac in receivers
    }
    anchor = None
    for _, batch in read_envelopes(journal / "envelopes.bin"):
        for record in batch.records:
            if record.channel != config[6] or batch.receiver_mac not in columns:
                continue
            anchor = record.sequence if anchor is None else anchor
            column = columns[batch.receiver_mac]
            column["seq"].append(record.sequence)
            column["i"].append(
                np.array([int(c.real) for c in record.raw_csi], np.int16)
            )
            column["q"].append(
                np.array([int(c.imag) for c in record.raw_csi], np.int16)
            )
            column["fw"].append(bool(record.first_word_invalid))
            column["dv"].append(record.rx_state == 0)
    offsets, magnitudes = {}, {}
    for mac, column in columns.items():
        offsets[mac], _ = sequence_offsets(np.asarray(column["seq"], np.int64), anchor)
        raw = prepare_magnitude(
            np.concatenate(column["i"]).tobytes(),
            np.concatenate(column["q"]).tobytes(),
            np.cumsum([0] + [len(v) for v in column["i"]]).tolist(),
            column["fw"],
            column["dv"],
        )
        magnitudes[mac] = np.frombuffer(raw, np.float64).reshape(-1, 245)
    lowest = min(int(o.min()) for o in offsets.values())
    rounds = np.arange(lowest, max(int(o.max()) for o in offsets.values()) + 1)
    amplitude = np.full((len(rounds), 4, 245), np.nan)
    presence = np.zeros((len(rounds), 4), dtype=bool)
    for slot, mac in enumerate(receivers):
        amplitude[:, slot], _ = align_samples(offsets[mac], magnitudes[mac], rounds)
        found, _ = align_samples(offsets[mac], np.ones((len(offsets[mac]), 1)), rounds)
        presence[:, slot] = np.isfinite(found[:, 0])
    # The native history places round offsets on a grid with a 12000-round margin.
    filtered, _ = hampel_subcarriers(
        amplitude.reshape(len(rounds), 980),
        (rounds + 12_000) / 120,
        window_seconds=0.5,
        min_periods=5,
        threshold=3.0,
    )
    signal = np.log1p(squared_difference(filtered)).astype(np.float32)
    # Live windows may extend past the last recorded sample.
    signal = np.concatenate((signal, np.full((1000, 980), np.nan, np.float32)))
    presence = np.concatenate((presence, np.zeros((1000, 4), dtype=bool)))
    return anchor, lowest, signal, presence


@pytest.mark.skipif(
    not CAPTURE.is_dir() or gui.runtime_library() is None,
    reason="needs the DVC capture and the detect extra",
)
def test_native_replay_matches_offline_preprocessing(tmp_path):
    from fall_detection._radio_native import NativeDetector

    from fall_detection.analysis.training.sequence_training_data import Normalizer

    output = tmp_path / "run"
    config = {
        "replay": {"captures": [str(CAPTURE)], "speed": 2.0},
        "model_root": str(MODELS),
        "core_library": str(gui.runtime_library()),
        "backend": "cpu",
        "models": ["cnn-4s"],
        "output_dir": str(output),
        "save_inputs": True,
        "preview": True,
    }
    detector = NativeDetector(json.dumps(config))
    detector.start()
    try:
        deadline = time.monotonic() + 60
        while json.loads(detector.health())["running"] and time.monotonic() < deadline:
            time.sleep(0.05)
        health = json.loads(detector.health())
        preview = detector.preview("cnn-4s")
    finally:
        detector.stop()
    assert health["state"] == "finished", health
    assert health["error"] is None
    rows = [json.loads(line) for line in (output / "predictions.jsonl").open()]
    # How many windows score depends on host load (late results become
    # unknown); every published row must still be well formed.
    assert rows
    for row in rows:
        if row["state"] == "score":
            assert 0 <= row["score"] <= 1
        else:
            assert row["state"] == "unknown" and row["score"] is None
            assert row["error"] in {
                "stale",
                "coverage",
                "preprocessing deadline exceeded",
            }

    anchor, lowest, signal, presence = _offline_inputs(CAPTURE)
    normalizer = Normalizer.load(MODELS / "cnn/normalizer-4s.npz")
    index = [json.loads(line) for line in (output / "inputs.jsonl").open()]
    tensors = np.fromfile(output / "inputs.f32", dtype="<f4").reshape(-1, 480, 1964)
    # Under load a newer window can replace a pending one before inference.
    assert len(index) == len(tensors) >= len(rows)
    for entry, native in zip(index, tensors):
        start = (entry["first_sequence"] - anchor) % 2**32 - lowest
        values = signal[start : start + 480]
        mask = np.isfinite(values)
        reference = np.concatenate(
            (
                normalizer.transform(np.where(mask, values, 0), mask),
                presence[start : start + 480].astype(np.float32),
            ),
            axis=-1,
        )
        np.testing.assert_array_equal(native, reference)

    metadata, raw, model_input = preview
    metadata = json.loads(metadata)
    assert metadata["frames"] == 480
    assert metadata["end_ns"] == index[-1]["end_ns"]
    magnitudes, signals = gui.preview_images(raw, model_input, 480)
    assert magnitudes.shape == signals.shape == (480, 980)
    np.testing.assert_array_equal(
        np.frombuffer(model_input, dtype="<f4").reshape(480, 1964), tensors[-1]
    )
