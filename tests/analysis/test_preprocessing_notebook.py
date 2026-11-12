"""Execute the actual preprocessing stages on a small synthetic recording."""

# These tests execute only trusted, repository-owned notebook cells.
# ruff: noqa: S102

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import numpy as np
import polars as pl
import pytest

from fall_detection.analysis.sequence_preprocessing import SequenceArtifacts
from fall_detection.analysis.sequence_training_data import load_sequence_index

NOTEBOOK = Path(__file__).resolve().parents[2] / "notebooks/latest/02_preprocess.ipynb"


def synthetic_session(path):
    # Eight seconds contains complete 2/4/6-second windows at both grid rates.
    n = 961
    rows = []
    for receiver in range(1, 5):
        for i in range(n):
            if receiver == 2 and i == 120:
                continue
            rows.append(
                {
                    "attempt_key": "trial/attempt",
                    "attempt_id": "001/01",
                    "receiver_id": f"rx-{receiver}",
                    "is_sensing": True,
                    "time_source": "test",
                    "time_seconds": i / 120,
                    "capture_time_ns": 1_000_000_000 + round(i / 120 * 1e9),
                    "phase": "action",
                    "driver_valid": True,
                    "sig_mode": 4,
                    "bandwidth": 0,
                    "stbc": 0,
                    "first_word": 0,
                    "len": 490,
                    "csi_i": [10 + i % 5] * 245,
                    "csi_q": [5] * 245,
                    "attempt_started_monotonic_ns": 1_000_000_000,
                    "attempt_ended_monotonic_ns": 9_000_000_001,
                    "sequence": i,
                    "run_id": "run",
                    "transmitter_boot_id": "tx",
                    "receiver_boot_id": f"rx-{receiver}",
                    "nominal_rate_hz": 120.0,
                    "source_row": i,
                    "clock_uncertainty_us": 0.0,
                }
            )
    path.mkdir()
    pl.DataFrame(rows).with_columns(
        pl.col("csi_i", "csi_q").cast(pl.List(pl.Int16))
    ).write_parquet(path / "packets.parquet")
    attempts = pl.DataFrame(
        [
            {
                "attempt_key": "trial/attempt",
                "participant_id": "synthetic",
                "session_id": "session",
                "attempt_id": "001/01",
                "trial_ordinal": 1,
                "attempt": 1,
                "activity_label": "stand_to_fall",
                "scenario_id": "fall",
                "review_revision": 0,
                "started_monotonic_ns": 1_000_000_000,
                "ended_monotonic_ns": 9_000_000_001,
                "status": "accepted",
                "inclusion": "include",
            }
        ]
    )
    pl.DataFrame(
        {
            "attempt_key": ["trial/attempt"],
            "phase": ["action"],
            "start_ns": [2_000_000_000],
            "end_ns": [8_000_000_000],
        }
    ).write_parquet(path / "phases.parquet")
    return SimpleNamespace(
        path=path,
        attempts=attempts,
        manifest={"source_fingerprint": "synthetic-source"},
    )


@pytest.mark.parametrize("rate", [96, 120])
def test_preprocessing_notebook_stages_and_cache(tmp_path, monkeypatch, rate):
    session = synthetic_session(tmp_path / "source")
    monkeypatch.setattr(SequenceArtifacts, "load_source", lambda self: session)
    original = SequenceArtifacts.output.fget
    monkeypatch.setattr(
        SequenceArtifacts,
        "output",
        property(lambda self: tmp_path / original(self).relative_to(self.root)),
    )
    notebook = json.loads(NOTEBOOK.read_text())
    cells = [
        "".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"
    ]
    # Override experiment configuration in the copy, never the real notebook/data.
    tree = ast.parse(cells[0])
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        values = {
            "DATASETS": {"synthetic": "session"},
            "SAMPLE_RATE": rate,
            "CPU_WORKERS": 1,
            "ENABLE_PLOTS": True,
            "MAX_PLOT_POINTS": 16,
        }
        if target.id in values:
            node.value = ast.parse(repr(values[target.id]), mode="eval").body
    namespace = {}
    exec(compile(ast.fix_missing_locations(tree), str(NOTEBOOK), "exec"), namespace)
    for cell in cells[1:]:
        exec(compile(cell, str(NOTEBOOK), "exec"), namespace)
    dataset = namespace["datasets"][0]
    assert set(dataset.index["duration"]) == {2, 4, 6}
    assert set(dataset.index["target"]) == {1}
    assert set(dataset.index["center_phase"]) == {"action"}
    assert dataset.index["receiver_coverage"].list.get(1).min() < 1
    index, _ = load_sequence_index(
        dataset.output.parent, datasets=("synthetic",), durations=(2, 4, 6)
    )
    assert len(index) == len(dataset.index)
    signal_path = dataset.output / dataset.signals["signal"][0]
    signal = np.load(signal_path, mmap_mode="r")
    assert signal.dtype == np.float32
    assert np.isnan(signal[0]).all()
    assert np.isnan(signal[rate, 1]).all()
    assert np.isnan(signal[rate + 1, 1]).all()
    stamp = (Path(dataset.segments["path"][0]) / "amplitude.npy").stat().st_mtime_ns
    cached_stages = [
        cell
        for cell in cells[1:]
        if any(
            f'checkpoint_stage(dataset.output, "{stage}"' in cell
            for stage in ("align_decode", "hampel", "difference")
        )
    ]
    assert len(cached_stages) == 3
    for cell in cached_stages:
        exec(compile(cell, str(NOTEBOOK), "exec"), namespace)
    assert (
        Path(dataset.segments["path"][0]) / "amplitude.npy"
    ).stat().st_mtime_ns == stamp
    namespace["PARAMETERS"]["threshold"] = 99
    with pytest.raises(ValueError, match="preprocessing parameters"):
        dataset.load_exported()
