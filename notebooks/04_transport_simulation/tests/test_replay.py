"""Deterministic transport, causality and source-preservation checks."""

import json
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay import Stream, make_features, retain_round, simulate, wire_bits  # noqa: E402


@pytest.fixture
def config():
    return json.loads((Path(__file__).resolve().parents[1] / "config.json").read_text())


def streams(n=100):
    sequence = np.arange(n, dtype=np.int64)
    return [Stream(sequence.copy(), sequence / 100, np.full(n, 490)) for _ in range(2)]


def test_retain_round_80_preserves_four_of_five_original_rounds():
    seq = np.arange(100)
    kept = seq[retain_round(seq, 80)]
    assert len(kept) == 80
    assert set(np.diff(kept)) == {1, 2}
    assert retain_round(seq, 50).sum() == 50
    with pytest.raises(ValueError):
        retain_round(seq, 101)


def test_simulate_original_preserves_natural_source_gaps(config):
    source = streams(20)
    source[0] = Stream(
        np.delete(source[0].sequence, 5),
        np.delete(source[0].seconds, 5),
        np.full(19, 490),
    )
    result = simulate(source, config["conditions"][0], config, 12, 0.2)
    assert len(result["arrivals"][0]) == 19
    np.testing.assert_array_equal(result["arrivals"][0], source[0].seconds)
    assert set(result["reasons"][0]) == {"delivered"}


def test_simulate_round_robin_exact_four_slot_balance(config):
    result = simulate(streams(), config["conditions"][3], config, 12, 1)
    np.testing.assert_array_equal(np.bincount(result["owners"], minlength=4), [20] * 4)
    for reason in result["reasons"]:
        assert np.count_nonzero(reason == "scheduled") == 20
        assert np.count_nonzero(reason == "delivered") == 60


def test_simulate_random_reproducible_without_global_rng(config):
    first = simulate(streams(), config["conditions"][4], config, 77, 1)
    np.random.seed(999)
    second = simulate(streams(), config["conditions"][4], config, 77, 1)
    np.testing.assert_array_equal(first["owners"], second["owners"])
    assert np.any(np.diff(first["owners"]) == 0)


def test_simulate_transfer_failure_does_not_change_capture_loss(config):
    condition = dict(config["conditions"][6])
    first = simulate(streams(200), condition, config, 29, 2)
    condition["transfer_failure"] = 1.0
    condition["service_bps"] = 500000
    second = simulate(streams(200), condition, config, 29, 2)
    for a, b in zip(first["reasons"], second["reasons"]):
        for reason in ("rate_removed", "scheduled", "radio_burst", "radio_independent"):
            np.testing.assert_array_equal(a == reason, b == reason)


def test_simulate_slow_service_expires_without_unbounded_queue(config):
    condition = dict(
        config["conditions"][7], service_bps=1000, independent_loss=0, burst_enter=0
    )
    config = dict(config, queue_capacity=3, maximum_age_seconds=0.05)
    result = simulate(streams(), condition, config, 7, 1)
    assert sum(c["expired"] + c["overflow"] for c in result["counters"]) > 0
    assert all(c["peak_queue"] <= 3 for c in result["counters"])
    assert all(n <= 3 for n in result["pending"])


def test_simulate_delivered_record_cannot_arrive_before_capture(config):
    result = simulate(streams(), config["conditions"][6], config, 17, 1.1)
    for source, arrival in zip(streams(), result["arrivals"]):
        assert np.all(arrival >= source.seconds)
    assert sum(c["completed"] for c in result["counters"]) > 0


def test_simulate_shared_service_never_exceeds_wall_time_capacity(config):
    condition = config["conditions"][6]
    result = simulate(streams(), condition, config, 17, 1)
    assert (
        sum(c["service_bits"] for c in result["counters"]) <= condition["service_bps"]
    )
    assert wire_bits(490, config) == (609 + 36) * 8


def test_simulate_thinning_does_not_give_one_receiver_double_service(config):
    condition = dict(
        config["conditions"][6], independent_loss=0, burst_enter=0, transfer_failure=0
    )
    source = streams(600)
    result = simulate(source, condition, config, 17, 6)
    np.testing.assert_allclose(np.diff(result["times"]), 1 / 80, atol=1e-10)
    for stream, arrival in zip(source, result["arrivals"]):
        last_second = (stream.seconds >= 4) & (stream.seconds < 5)
        assert np.count_nonzero(last_second & (arrival < stream.seconds + 0.1)) >= 50


def test_make_features_late_data_stays_missing_but_age_can_update(config):
    source = [
        Stream(np.array([0, 1]), np.array([0.001, 0.021]), np.full(2, 490))
        for _ in range(2)
    ]
    phases = [np.zeros((2, 3)), np.zeros((2, 3))]
    # First sample misses its own .12 deadline but is known by the next .14.
    arrival = [np.array([0.13, np.inf]), np.array([0.001, np.inf])]
    values, counts, age = make_features(source, phases, arrival, 0, config)
    assert np.isnan(values[0, 0]).all()
    assert counts[0, 0] == 0
    assert counts[1, 0] == 1
    assert age[0, 0] == 1
    assert age[0, 1] < 1
    # An old late arrival updates age, never fills a different capture bin.
    assert np.isnan(values[0, 1]).all()


def test_make_features_never_uses_future_capture_for_earlier_age(config):
    source = [
        Stream(np.array([0]), np.array([0.021]), np.array([490])) for _ in range(2)
    ]
    phases = [np.zeros((1, 3)) for _ in range(2)]
    values, counts, age = make_features(
        source, phases, [s.seconds for s in source], 0, config
    )
    assert np.isnan(values[:, 0]).all()
    assert np.all(counts[:, 0] == 0)
    assert np.all(age[:, 0] == 1)


def test_make_features_circular_average_does_not_cancel_wrap_boundary(config):
    source = [
        Stream(np.array([0, 1]), np.array([0.001, 0.011]), np.full(2, 490))
        for _ in range(2)
    ]
    phase = np.tile(np.array([[np.pi - 0.01], [-np.pi + 0.01]]), (1, 3))
    values, counts, _ = make_features(
        source, [phase, phase], [s.seconds for s in source], 0, config
    )
    assert abs(values[0, 0, 0]) < 0.001
    assert values[1, 0, 0] < -0.99
    assert counts[0, 0] == 2
