import json

import numpy as np

from fall_detection.analysis.amplitude_pipeline import save_recording
from fall_detection.analysis.windows import generate_windows


def test_generate_windows_overlap_labels_and_missing_gaps(tmp_path):
    source = tmp_path / "source"
    times = np.arange(0, 8.01, 0.01)
    keep = (times < 3) | (times > 3.1)
    times = times[keep]
    amplitude = np.column_stack((times, times * 2)).astype(np.float32)
    save_recording(source / "trial" / "rx.npz", {
        "time_seconds": times, "amplitude": amplitude,
        "valid": np.ones_like(amplitude, dtype=bool),
        "phase": np.where(times < 4, "preparation", "action"),
        "hampel_replaced": np.zeros_like(amplitude, dtype=bool),
        "subcarriers": np.array([-2, 2]),
        "provenance_json": np.asarray(json.dumps({"activity_label": "walk_to_fall"})),
    })
    output = tmp_path / "windows"
    counts = generate_windows(source, output)
    assert counts == {2: 7, 4: 3, 6: 1}
    with np.load(output / "2s/trial/rx.npz") as data:
        assert data["amplitude"].shape == (7, 160, 2)
        assert data["label"][0] == "preparation"
        assert data["label"][3] == "action"
        np.testing.assert_allclose(data["time_seconds"][1, 0] - data["time_seconds"][0, 0], 1)
        assert not data["valid"][2, 84].any()
        assert np.isnan(data["amplitude"][2, 84]).all()
