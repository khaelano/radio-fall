"""WiFall session adaptation without changing source recordings."""

import json

import inspector_sessions
import numpy as np
import pytest
from inspector_sessions import FrameSpec, attempt_origin
from journal_builder import TX, mac_text

from fall_detection.analysis.wifall.dataset import (
    DEFAULT_SUBCARRIERS,
    fill_short_gaps,
    load_dataset,
)


def test_fill_short_gaps_brackets_bounds_and_preserves_source():
    values = np.array(
        [[np.nan, 1], [2, np.nan], [np.nan, 3], [4, np.nan], [np.nan, np.nan]]
    )
    original = values.copy()
    result = fill_short_gaps(values, sample_rate_hz=10, max_gap_seconds=0.2)
    np.testing.assert_array_equal(values, original)
    np.testing.assert_array_equal(
        result, [[np.nan, 1], [2, 2], [3, 3], [4, np.nan], [np.nan, np.nan]]
    )
    np.testing.assert_array_equal(
        fill_short_gaps(values, sample_rate_hz=10, max_gap_seconds=0.19), original
    )


@pytest.mark.parametrize(
    "values,settings",
    [
        (np.ones((4, 1)), {"sample_rate_hz": 0}),
        (np.ones((4, 1)), {"max_gap_seconds": float("nan")}),
        (np.array([[-1.0], [2]]), {}),
        (np.array([[np.inf], [2]]), {}),
    ],
)
def test_fill_short_gaps_rejects_invalid_inputs(values, settings):
    with pytest.raises(ValueError, match="amplitudes"):
        fill_short_gaps(values, **settings)


def _recorded_source(session_factory, monkeypatch):
    receivers = {
        **inspector_sessions.RECEIVERS,
        "rx-3": bytes.fromhex("44bd8dd0be9c"),
        "rx-4": bytes.fromhex("44bd8dd0b66c"),
    }
    for receiver, mac in receivers.items():
        monkeypatch.setitem(inspector_sessions.RECEIVERS, receiver, mac)
    origin = attempt_origin(0)
    frames = [
        FrameSpec(
            sequence=sequence,
            capture_ns=origin + round(sequence / 120 * 1e9),
            receiver_id=receiver,
            # Compact HE20 slot 122 is the positive edge tone. Inspected C5
            # recordings contain zeros here; the default interior schema must
            # still produce windows without inventing amplitudes for that tone.
            values=(10 + 5j,) * 122 + (0j,) + (10 + 5j,) * 122,
        )
        for sequence in range(240)
        for receiver in receivers
    ]
    source = session_factory(attempts=((1, 1, "accepted"),), frames=frames)
    manifest_path = source / "session.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["environment"].update(
        {
            "radio_inventory": {"transmitter": {"mac": mac_text(TX)}},
            "receiver_ids": {mac_text(mac): rx for rx, mac in receivers.items()},
            "nominal_rate_hz": 120,
            "radio_profile": {
                "band": "5ghz",
                "bandwidth_mhz": 20,
                "channel": 44,
                "nominal_rate_hz": 120,
            },
        }
    )
    manifest_path.write_text(json.dumps(manifest))
    events = [
        {
            "kind": "phase_changed",
            "trial_ordinal": 1,
            "attempt": 1,
            "state": state,
            "monotonic_ns": origin + offset,
        }
        for state, offset in (
            ("countdown", 0),
            ("action", 500_000_000),
            ("recovery", 1_500_000_000),
        )
    ]
    (source / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    return source


def test_load_dataset_reads_native_journals_and_separates_cues(
    session_factory, monkeypatch, tmp_path
):
    source = _recorded_source(session_factory, monkeypatch)
    original = (source / "session.json").read_bytes()
    dataset = load_dataset(
        [source],
        root=tmp_path,
        fall_labels=("stand_to_fall",),
        non_fall_labels=("walk",),
        window_seconds=0.5,
        hop_seconds=0.5,
    )
    assert dataset.windows.shape == (2, 60, 4, 30)
    assert dataset.windows.dtype == np.float32
    assert dataset.stable_windows.shape == (1, 60, 4, 30)
    np.testing.assert_array_equal(dataset.targets, [0, 0])
    np.testing.assert_allclose(dataset.windows, abs(10 + 5j), rtol=1e-6)
    assert len(set(dataset.groups)) == 1
    assert dataset.stable_groups[0] == dataset.groups[0]
    assert all(row["annotation_source"] == "collection_cue" for row in dataset.metadata)
    assert dataset.provenance["sources"][0]["source_fingerprint"]
    assert dataset.provenance["center_frequency_hz"] == 5.22e9
    assert dataset.provenance["coordinates"]["subcarriers"] == list(DEFAULT_SUBCARRIERS)
    assert (source / "session.json").read_bytes() == original


def test_load_dataset_counts_unknown_labels_without_guessing(
    session_factory, monkeypatch, tmp_path
):
    source = _recorded_source(session_factory, monkeypatch)
    with pytest.raises(ValueError, match="attempts_unmapped_label.*1"):
        load_dataset(
            [source],
            root=tmp_path,
            fall_labels=("fall",),
            non_fall_labels=("sit",),
            window_seconds=0.5,
            hop_seconds=0.5,
        )


def test_load_dataset_rejects_unrecorded_rate(session_factory, monkeypatch, tmp_path):
    source = _recorded_source(session_factory, monkeypatch)
    manifest_path = source / "session.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["environment"]["nominal_rate_hz"] = 100
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="120 Hz"):
        load_dataset(
            [source], root=tmp_path, fall_labels=("fall",), non_fall_labels=("walk",)
        )


def test_load_dataset_honors_excluded_review(session_factory, monkeypatch, tmp_path):
    source = _recorded_source(session_factory, monkeypatch)
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
        load_dataset(
            [source],
            root=tmp_path,
            fall_labels=("fall",),
            non_fall_labels=("walk",),
            window_seconds=0.5,
            hop_seconds=0.5,
        )
