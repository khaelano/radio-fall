from types import SimpleNamespace

from fall_detection.apps.detector import app


def test_help_does_not_open_hardware(capsys):
    try:
        app.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "--replay-session" in capsys.readouterr().out


def test_headless_program_owns_startup_logging_and_cleanup(tmp_path, monkeypatch):
    calls = []
    bundle = SimpleNamespace(metadata={}, validate_radio=lambda settings: None)
    monkeypatch.setattr(app.ModelBundle, "load", lambda path: bundle)

    class Engine:
        failure = ""

        def __init__(self, *a, **kw):
            calls.append("engine-created")

        def on_record(self, *a):
            pass

        def interrupt(self, *a):
            pass

        def start(self):
            calls.append("model-loaded")

        def close(self):
            calls.append("engine-closed")

        def tick(self, **kw):
            return [{"kind": "prediction", "probability": 0.4}]

        def status(self):
            return {"prediction": None}

    class Radio:
        def __init__(self, *a, **kw):
            self.settings = SimpleNamespace(
                transport=SimpleNamespace(delivery_grace_ms=900)
            )
            self.manager = SimpleNamespace(preflight_ready=True, failure=None)

        def environment(self):
            return {}

        def start(self):
            calls.append("radio-started")

        def stop(self):
            calls.append("radio-stopped")

    monkeypatch.setattr(app, "DetectorEngine", Engine)
    monkeypatch.setattr(app, "LiveRadio", Radio)
    assert (
        app.main(
            [
                "--no-phase-models",
                "--headless",
                "--duration",
                "0.01",
                "--output-dir",
                str(tmp_path / "run"),
            ]
        )
        == 0
    )
    assert calls.index("model-loaded") < calls.index("radio-started")
    assert calls[-2:] == ["radio-stopped", "engine-closed"]
    assert (tmp_path / "run/predictions.jsonl").read_text()


def test_failed_radio_setup_cleans_preprocessing_without_starting_scorer(
    tmp_path, monkeypatch, capsys
):
    calls = []
    monkeypatch.setattr(app.ModelBundle, "load", lambda path: SimpleNamespace())

    class Engine:
        def __init__(self, *a, **kw):
            pass

        def close(self):
            calls.append("closed")

        def on_record(self, *a):
            pass

        def interrupt(self, *a):
            pass

    monkeypatch.setattr(app, "DetectorEngine", Engine)

    def fail(*a, **kw):
        raise RuntimeError("missing gateway")

    monkeypatch.setattr(app, "LiveRadio", fail)
    assert (
        app.main(
            ["--no-phase-models", "--headless", "--output-dir", str(tmp_path / "run")]
        )
        == 2
    )
    assert calls == ["closed"]
    assert "missing gateway" in capsys.readouterr().err


def test_invalid_cli_requires_replay_attempt():
    try:
        app.main(["--replay-session", "missing"])
    except SystemExit as exc:
        assert exc.code == 2


def test_headless_phase_models_start_before_radio_and_log_each_score_once(
    tmp_path, monkeypatch
):
    import json

    from fall_detection.detection import phase_models

    calls = []
    bundle = SimpleNamespace(
        metadata={"radio": {}, "receivers": ["rx-1"]},
        validate_radio=lambda settings: None,
    )
    monkeypatch.setattr(app.ModelBundle, "load", lambda path: bundle)

    class Engine:
        failure = ""

        def __init__(self, *args, **kwargs):
            pass

        def on_record(self, *args):
            calls.append("legacy-record")

        def interrupt(self, *args):
            calls.append("legacy-interrupt")

        def start(self):
            calls.append("legacy-start")

        def close(self):
            calls.append("legacy-close")

        def tick(self, **kwargs):
            return []

        def status(self):
            return {"prediction": None}

    class Phase:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            calls.append("phase-start")

        def close(self):
            calls.append("phase-close")

        def on_record(self, *args):
            calls.append("phase-record")

        def interrupt(self, *args):
            calls.append("phase-interrupt")

        def status(self, *args, **kwargs):
            return {
                "models": [
                    {
                        "receiver": "rx-1",
                        "duration_seconds": 2,
                        "model": "cnn",
                        "generation": 1,
                        "end_ns": 100,
                        "center_ns": 0,
                        "coverage": 1.0,
                        "probabilities": {
                            "preparation": 0.2,
                            "action": 0.5,
                            "resting": 0.3,
                        },
                    }
                ],
                "failure": "",
                "dropped": 0,
                "generation": 1,
            }

    class Radio:
        def __init__(self, *args, **kwargs):
            self.record_sink = kwargs["record_sink"]
            self.settings = SimpleNamespace(
                transport=SimpleNamespace(delivery_grace_ms=900)
            )
            self.manager = SimpleNamespace(preflight_ready=True, failure=None)

        def environment(self):
            return {}

        def start(self):
            calls.append("radio-start")
            self.record_sink(object(), 0)

        def stop(self):
            calls.append("radio-stop")

    monkeypatch.setattr(app, "DetectorEngine", Engine)
    monkeypatch.setattr(phase_models, "PhaseModelEngine", Phase)
    monkeypatch.setattr(app, "LiveRadio", Radio)
    output = tmp_path / "run"
    assert (
        app.main(
            [
                "--headless",
                "--duration",
                "0.06",
                "--phase-models",
                str(tmp_path),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert calls.index("phase-start") < calls.index("radio-start")
    assert "legacy-record" in calls and "phase-record" in calls
    assert "phase-close" in calls and "legacy-close" in calls
    events = [
        json.loads(line)
        for line in (output / "predictions.jsonl").read_text().splitlines()
    ]
    assert len(events) == 1 and events[0]["kind"] == "phase_prediction"
    assert events[0]["probabilities"]["action"] == 0.5
