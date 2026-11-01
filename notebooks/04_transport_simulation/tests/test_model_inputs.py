"""Ensure training normalization cannot see held-out signal values."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiment_models import Attempts, fit_scaler  # noqa: E402


class FakeCases:
    def __init__(self):
        self.config = {
            "training_realizations": [101, 202],
            "conditions": [{"name": "original_100"}, {"name": "rr4_80"}],
        }
        self.values = np.zeros((3, 4, 2, 242), dtype=np.float32)
        self.values[0] = 0.25
        self.values[1] = 100
        self.values[2] = -100

    def raw(self, condition, seed):
        return self.values, None, None

    def input(self, condition, seed, index, scaler):
        # Expose chosen identity/condition, independently of signal content.
        return np.array([index, condition != "original_100", seed], dtype=np.float32)


def test_fit_scaler_ignores_validation_and_test_values():
    cases = FakeCases()
    before = fit_scaler(cases, np.array([0]))
    cases.values[1:] = 1e9
    after = fit_scaler(cases, np.array([0]))
    np.testing.assert_array_equal(before["mean"], after["mean"])
    assert np.all(before["mean"] == 0.25)


def test_reporting_import_resolves_to_current_experiment():
    import reporting

    assert Path(reporting.__file__).resolve().parent.name == "04_transport_simulation"


def test_attempts_only_draws_variants_of_the_selected_training_attempt():
    cases = FakeCases()
    table = pd.DataFrame({"target": [1, 0, 1]})
    dataset = Attempts(cases, table, np.array([0]), {}, "missingness_trained", 17)
    for epoch in range(12):
        dataset.epoch = epoch
        x, target = dataset[0]
        assert x[0] == 0
        assert x[2] in (101, 202)
        assert target == 1
    original = dataset[0][0].clone()
    table.loc[0, "target"] = 0
    np.testing.assert_array_equal(dataset[0][0], original)
