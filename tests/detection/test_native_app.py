"""Native frontend configuration, isolation and lifecycle contracts."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from fall_detection.apps.detector import app, native_app


def test_parser_selects_current_four_second_models_on_webgpu():
    args = app.parser().parse_args([])
    assert args.backend == "webgpu"
    assert args.models == ["cnn-4s"]


def test_native_headless_polls_results_and_stops_on_failure(monkeypatch, capsys):
    calls = []

    class Backend:
        def start(self):
            calls.append("start")

        def poll(self, maximum):
            assert maximum == 64
            return json.dumps([{"model_id": "cnn-4s", "score": 0.4}])

        def health(self):
            return json.dumps({"error": "device lost"})

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(native_app, "build_config", lambda args: {})
    monkeypatch.setattr(native_app, "_new_backend", lambda config: Backend())
    with pytest.raises(RuntimeError, match="device lost"):
        native_app.run(SimpleNamespace(headless=True, duration=None))
    assert calls == ["start", "stop"]
    assert '"model_id": "cnn-4s"' in capsys.readouterr().out


def test_native_config_uses_model_files_and_wire_configuration_only(
    tmp_path, monkeypatch
):
    core = tmp_path / "libonnxruntime.so"
    plugin = tmp_path / "webgpu.so"
    core.touch()
    plugin.touch()
    args = app.parser().parse_args(
        ["--ort-library", str(core), "--webgpu-plugin", str(plugin)]
    )
    configuration = native_app.build_config(args)
    assert len(configuration["radio_config"]) == 108
    assert configuration["models"] == list(native_app.DEFAULT_MODELS)
    assert configuration["core_library"] == str(core.resolve())
    assert configuration["model_root"] == str(Path("artifacts/model").resolve())
    assert not any("dataset" in key for key in configuration)
    assert not Path(configuration["output_dir"]).exists()


def test_native_config_replay_needs_no_radio_settings(tmp_path):
    core = tmp_path / "libonnxruntime.so"
    core.touch()
    args = app.parser().parse_args(
        [
            "--backend",
            "cpu",
            "--ort-library",
            str(core),
            "--replay-capture",
            str(tmp_path / "capture"),
            "--replay-speed",
            "2",
        ]
    )
    configuration = native_app.build_config(args)
    assert configuration["replay"] == {
        "captures": [str((tmp_path / "capture").resolve())],
        "speed": 2.0,
        "repeat": False,
    }
    assert "radio_config" not in configuration
    assert configuration["adapter_id"] is None


def test_main_dispatches_to_native_frontend(monkeypatch):
    monkeypatch.setattr(native_app, "run", lambda args: 17)
    assert app.main(["--headless"]) == 17


def test_native_import_does_not_load_python_inference_libraries():
    code = """
import sys
from fall_detection.apps.detector import app
app.parser()
for name in ('torch', 'onnxruntime', 'sklearn'):
    assert name not in sys.modules, name
"""
    subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )


def test_preview_images_mask_missing_samples():
    raw = np.arange(2 * 980, dtype="<f4")
    raw[5] = np.nan
    model_input = np.zeros((2, 1964), dtype="<f4")
    model_input[:, :980] = 1.5
    model_input[0, 980:1960] = 1
    magnitudes, signals = native_app.preview_images(
        raw.tobytes(), model_input.tobytes(), 2
    )
    assert np.isnan(magnitudes[0, 5]) and magnitudes[1, 0] == 980
    assert np.all(signals[0] == 1.5)
    assert np.all(np.isnan(signals[1]))
    with pytest.raises(ValueError):
        native_app.preview_images(raw.tobytes(), model_input.tobytes(), 3)


def _magnitudes(values):
    """Return little-endian float32 rows of 245 samples, one value per row."""
    rows = np.repeat(np.asarray(list(values), dtype="<f4")[:, None], 245, axis=1)
    return rows.astype("<f4").tobytes()


def test_add_places_rows_by_round_and_receiver():
    buffer = native_app.StreamBuffer(rounds=8)
    assert buffer.add([1, 1], [5, 6], [0, 3], _magnitudes([1, 2]))
    assert buffer.latest == 6
    assert np.all(buffer.data[5, :245] == 1)
    assert np.all(buffer.data[6, 735:980] == 2)
    assert np.isnan(buffer.data[5, 245:]).all()
    assert np.isnan(buffer.data[6, :735]).all()
    image = buffer.image()
    assert np.all(image[-1, 735:980] == 2)
    assert np.all(image[-2, :245] == 1)


def test_add_out_of_order_round_lands_in_its_row():
    buffer = native_app.StreamBuffer(rounds=8)
    buffer.add([1], [10], [0], _magnitudes([1]))
    assert buffer.add([1], [8], [1], _magnitudes([2]))
    assert buffer.latest == 10
    assert np.all(buffer.data[8 % 8, 245:490] == 2)
    assert np.all(buffer.data[10 % 8, :245] == 1)
    assert np.isnan(buffer.data[8 % 8, :245]).all()


def test_add_advance_clears_exposed_rows_only():
    buffer = native_app.StreamBuffer(rounds=8)
    buffer.add([1] * 8, list(range(8)), [0] * 8, _magnitudes(range(1, 9)))
    buffer.add([1], [9], [1], _magnitudes([50]))
    assert buffer.latest == 9
    # Rounds 8 and 9 reuse rows 0 and 1; their old contents must not reappear.
    assert np.isnan(buffer.data[0]).all()
    assert np.isnan(buffer.data[1, :245]).all()
    assert np.all(buffer.data[1, 245:490] == 50)
    assert np.all(buffer.data[2, :245] == 3)

    buffer.add([1], [17], [0], _magnitudes([99]))
    assert buffer.latest == 17
    assert np.all(buffer.data[1, :245] == 99)
    assert np.isnan(np.delete(buffer.data, 1, axis=0)).all()


def test_add_stale_round_is_ignored():
    buffer = native_app.StreamBuffer(rounds=8)
    buffer.add([1], [20], [0], _magnitudes([1]))
    assert not buffer.add([1], [12], [1], _magnitudes([2]))  # latest - rounds
    assert buffer.latest == 20
    assert np.isnan(buffer.data[12 % 8, 245:490]).all()
    assert buffer.add([1], [13], [1], _magnitudes([3]))  # oldest row in window
    assert np.all(buffer.data[13 % 8, 245:490] == 3)
    assert np.all(buffer.data[20 % 8, :245] == 1)


def test_add_generation_change_resets_buffer_and_validates_input():
    buffer = native_app.StreamBuffer(rounds=8)
    buffer.add([1], [4], [0], _magnitudes([1]))
    buffer.add([2], [1], [2], _magnitudes([7]))
    assert buffer.generation == 2
    assert buffer.latest == 1
    assert np.all(buffer.data[1, 490:735] == 7)
    assert np.count_nonzero(~np.isnan(buffer.data)) == 245

    with pytest.raises(ValueError):
        buffer.add([2], [3, 4], [0, 1], _magnitudes([1, 2]))
    with pytest.raises(ValueError):
        buffer.add([2, 2], [3, 4], [0, 1], _magnitudes([1]))
    assert buffer.generation == 2
    assert buffer.latest == 1
    assert buffer.add([], [], [], b"") is False
