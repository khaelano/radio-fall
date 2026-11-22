"""WiFall window loading from recorded sessions without changing them."""

import json

import numpy as np
import pytest
from recorded_sources import four_receiver_source

from fall_detection.analysis.wifall.dataset import WIFALL_SUBCARRIERS, load_windows

SHORT = {"window_seconds": 0.5, "hop_seconds": 0.5}


def test_load_windows_reads_native_journals_and_separates_cues(
    session_factory, monkeypatch, tmp_path
):
    source = four_receiver_source(session_factory, monkeypatch)
    original = (source / "session.json").read_bytes()
    dataset = load_windows(
        [source],
        root=tmp_path,
        fall_labels=("stand_to_fall",),
        non_fall_labels=("walk",),
        **SHORT,
    )
    assert dataset.windows.statistics.shape == (2, 4, 6)
    assert dataset.windows.streams.shape == (2, 60, 4)
    assert dataset.resting_streams.shape == (1, 60, 4)
    # Constant amplitude has no principal-component motion on any receiver.
    np.testing.assert_allclose(dataset.windows.streams, 0, atol=1e-6)
    np.testing.assert_array_equal(dataset.targets, [0, 0])
    assert dataset.resting_groups[0] == dataset.groups[0]
    assert dataset.provenance["center_frequency_hz"] == 5.22e9
    assert dataset.provenance["coordinates"]["subcarriers"] == list(WIFALL_SUBCARRIERS)
    assert (source / "session.json").read_bytes() == original


def test_load_windows_drops_failing_receivers_per_window(
    session_factory, monkeypatch, tmp_path
):
    source = four_receiver_source(session_factory, monkeypatch, skip=("rx-2",))
    settings = {
        "root": tmp_path,
        "fall_labels": ("fall",),
        "non_fall_labels": ("walk",),
    }
    dataset = load_windows([source], **settings, **SHORT)
    assert np.isnan(dataset.windows.statistics[:, 1]).all()
    assert dataset.metadata[0]["receivers_used"] == ["rx-1", "rx-3", "rx-4"]
    with pytest.raises(ValueError, match="action_too_few_receivers.*2"):
        load_windows([source], minimum_receivers=4, **settings, **SHORT)


def test_load_windows_counts_unknown_labels_without_guessing(
    session_factory, monkeypatch, tmp_path
):
    source = four_receiver_source(session_factory, monkeypatch)
    with pytest.raises(ValueError, match="attempts_unmapped_label.*1"):
        load_windows(
            [source],
            root=tmp_path,
            fall_labels=("fall",),
            non_fall_labels=("sit",),
            **SHORT,
        )


def test_load_windows_rejects_unrecorded_rate(session_factory, monkeypatch, tmp_path):
    source = four_receiver_source(session_factory, monkeypatch)
    manifest_path = source / "session.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["environment"]["nominal_rate_hz"] = 100
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="120 Hz"):
        load_windows(
            [source], root=tmp_path, fall_labels=("fall",), non_fall_labels=("walk",)
        )


def test_load_windows_honors_excluded_review(session_factory, monkeypatch, tmp_path):
    source = four_receiver_source(session_factory, monkeypatch)
    review_path = tmp_path / "data/annotations/session-1/session_review.json"
    review_path.parent.mkdir(parents=True)
    review_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": "session-1",
                "protocol_hash": "test-hash",
                "revision": 1,
                "attempts": {
                    "trials/001_walk/attempt_01": {
                        "inclusion": "exclude",
                        "quality": "bad",
                    }
                },
            }
        )
    )
    with pytest.raises(ValueError, match="attempts_excluded.*1"):
        load_windows(
            [source],
            root=tmp_path,
            fall_labels=("fall",),
            non_fall_labels=("walk",),
            **SHORT,
        )
