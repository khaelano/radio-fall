"""Deterministic checks for split leakage, masking, and fitted transforms."""

import numpy as np
import pandas as pd
import pytest
import torch

from data_pipeline import (
    LABELS,
    assign_splits,
    bin_values,
    normalize_inputs,
    smooth_valid,
)
from modeling import SmallCNN, metrics
from vendor.phase_motion import phase_change_matrix


def test_split_keeps_scenarios_repetitions_and_receivers_together():
    records = []
    for label in LABELS:
        for group in range(5):
            for repetition in range(2):
                records.append(
                    {
                        "label": label,
                        "scenario_id": f"{label}_{group}",
                        "trial_ordinal": len(records),
                        "attempt_id": f"{label}_{group}_{repetition}",
                    }
                )
    table = pd.DataFrame(records)
    result = assign_splits(table, 4)
    assert result.groupby("scenario_id").split.nunique().eq(1).all()
    assert set(result.split) == {"train", "validation", "test"}
    assert result.groupby(["label", "split"]).size().gt(0).all()
    pd.testing.assert_frame_equal(result, assign_splits(table, 4))


def test_bin_does_not_interpolate_gaps_or_mix_tones():
    values = np.array([[1.0, 10.0], [3.0, np.nan], [7.0, 70.0]])
    output = bin_values(np.array([0.01, 0.03, 0.13]), values, bins=4, hz=25)
    np.testing.assert_allclose(output[0], [2, 10])
    assert np.isnan(output[1:3]).all()
    np.testing.assert_allclose(output[3], [7, 70])


def test_circular_binning_preserves_pi_wrap():
    phases = np.array([[np.pi - 0.01], [-np.pi + 0.01]])
    cosine = bin_values(np.array([0.01, 0.02]), np.cos(phases), 1, 25)
    sine = bin_values(np.array([0.01, 0.02]), np.sin(phases), 1, 25)
    assert cosine[0, 0] < -0.99
    assert abs(sine[0, 0]) < 1e-5


def test_normalization_never_fits_held_out_values_and_retains_masks():
    values = np.array([[[[1.0], [3.0]]], [[[1001.0], [np.nan]]]], dtype=np.float32)
    result, statistics = normalize_inputs(values, np.array([0]))
    np.testing.assert_allclose(statistics["mean"], 2)
    np.testing.assert_allclose(statistics["scale"], 1)
    assert result.shape == (2, 2, 2, 1)
    assert result[1, 0, 0, 0] == 999
    assert result[1, 0, 1, 0] == 0
    assert result[1, 1, 1, 0] == 0
    changed = values.copy()
    changed[1] *= 10
    _, second_statistics = normalize_inputs(changed, np.array([0]))
    np.testing.assert_equal(statistics["mean"], second_statistics["mean"])


def test_smoothing_preserves_missing_center_and_never_mixes_tones():
    values = np.array([[[1.0, 10.0], [np.nan, np.nan], [5.0, 50.0]]])
    result = smooth_valid(values, 3)
    assert np.isnan(result[:, 1]).all()
    np.testing.assert_allclose(result[:, 0], [[1.0, 10.0]])
    np.testing.assert_allclose(result[:, 2], [[5.0, 50.0]])
    with pytest.raises(ValueError):
        smooth_valid(values, 2)


def test_signed_change_wrap_and_unsupported_lag():
    values = np.array([[np.pi - 0.05, 0], [-np.pi + 0.05, 0.4], [0, 0]])
    result = phase_change_matrix(values, np.array([0, 0.1, 0.5]), 0.1)
    np.testing.assert_allclose(result[1], [0.1, 0.4])
    assert np.isnan(result[2]).all()


def test_cnn_has_one_output_per_attempt_and_finite_gradients():
    torch.manual_seed(7)
    model = SmallCNN(8)
    values = torch.randn(3, 8, 100, 242)
    output = model(values)
    assert output.shape == (3,)
    torch.nn.functional.binary_cross_entropy_with_logits(
        output, torch.tensor([0.0, 1.0, 0.0])
    ).backward()
    assert all(torch.isfinite(parameter.grad).all() for parameter in model.parameters())


def test_metrics_use_fall_as_positive_and_fixed_threshold():
    result = metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.8, 0.5, 0.2]))
    assert result["tp"] == result["tn"] == result["fp"] == result["fn"] == 1
    assert result["fall_recall"] == result["specificity"] == 0.5
