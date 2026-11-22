"""FallDeFi trace extraction from recorded sessions without changing them."""

import numpy as np
import pytest
from recorded_sources import four_receiver_source

from fall_detection.analysis.falldefi.dataset import FALLDEFI_SUBCARRIERS, load_traces

TONES = len(FALLDEFI_SUBCARRIERS)


def test_load_traces_widens_action_cues_and_keeps_countdown_rest(
    session_factory, monkeypatch, tmp_path
):
    source = four_receiver_source(session_factory, monkeypatch)
    original = (source / "session.json").read_bytes()
    dataset = load_traces(
        [source],
        root=tmp_path,
        fall_labels=("stand_to_fall",),
        non_fall_labels=("walk",),
        margin_seconds=0.25,
        minimum_seconds=0.25,
    )
    assert [trace.shape for trace in dataset.traces] == [(180, 4, TONES)]
    assert [segment.shape for segment in dataset.resting] == [(60, 4, TONES)]
    assert dataset.traces[0].dtype == np.float32
    np.testing.assert_allclose(dataset.traces[0], abs(10 + 5j), rtol=1e-6)
    np.testing.assert_array_equal(dataset.targets, [0])
    assert dataset.resting_groups[0] == dataset.groups[0]
    row = dataset.metadata[0]
    assert row["kind"] == "cue" and row["duration_seconds"] == 1.5
    assert row["cue_start_ns"] - row["start_ns"] == 250_000_000
    assert (source / "session.json").read_bytes() == original


def test_load_traces_selects_receivers_and_cuts_countdown_to_the_epoch(
    session_factory, monkeypatch, tmp_path
):
    # Packets start 25 ms after the countdown cue, as in the C5 recordings.
    source = four_receiver_source(session_factory, monkeypatch, first=3)
    dataset = load_traces(
        [source],
        root=tmp_path,
        fall_labels=("fall",),
        non_fall_labels=("walk",),
        margin_seconds=0.25,
        minimum_seconds=0.25,
        receivers=("rx-1", "rx-3"),
    )
    assert [trace.shape for trace in dataset.traces] == [(180, 2, TONES)]
    assert [segment.shape for segment in dataset.resting] == [(57, 2, TONES)]
    assert dataset.provenance["coordinates"]["receivers"] == ["rx-1", "rx-3"]


def test_load_traces_drops_failing_receivers_per_trace(
    session_factory, monkeypatch, tmp_path
):
    source = four_receiver_source(session_factory, monkeypatch, skip=("rx-2",))
    settings = {
        "root": tmp_path,
        "fall_labels": ("fall",),
        "non_fall_labels": ("walk",),
        "margin_seconds": 0.25,
        "minimum_seconds": 0.25,
    }
    dataset = load_traces([source], **settings)
    assert dataset.metadata[0]["receivers_used"] == ["rx-1", "rx-3", "rx-4"]
    assert np.isnan(dataset.traces[0][:, 1]).all()
    assert np.isfinite(dataset.traces[0][:, [0, 2, 3]]).all()
    with pytest.raises(ValueError, match="trace_too_few_receivers.*1"):
        load_traces([source], minimum_receivers=4, **settings)


def test_load_traces_tiles_long_non_fall_cues_but_not_long_fall_cues(
    session_factory, monkeypatch, tmp_path
):
    source = four_receiver_source(session_factory, monkeypatch)
    tiled = load_traces(
        [source],
        root=tmp_path,
        fall_labels=("fall",),
        non_fall_labels=("walk",),
        interval_seconds=0.5,
        minimum_seconds=0.25,
    )
    assert [row["kind"] for row in tiled.metadata] == ["interval", "interval"]
    assert [trace.shape[0] for trace in tiled.traces] == [60, 60]
    with pytest.raises(ValueError, match="fall_cues_longer_than_interval.*1"):
        load_traces(
            [source],
            root=tmp_path,
            fall_labels=("walk",),
            non_fall_labels=("sit",),
            interval_seconds=0.5,
            minimum_seconds=0.25,
        )
