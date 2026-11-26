"""Installation calibration: threshold rule, movement recording and files."""

import itertools
import json
from pathlib import Path

import pytest

from fall_detection.apps.live import app, calibration

MODEL = "tonepool_tcn-4s"
SECOND = 1_000_000_000
MAXIMUM_AGE = calibration.maximum_age_ns(250, 900)
SETTLE = 4 * SECOND + MAXIMUM_AGE + calibration.SETTLE_MARGIN_NS


def _row(start_s, score, model=MODEL, generation=1):
    start = int(start_s * SECOND)
    return {
        "model_id": model,
        "generation": generation,
        "start_ns": start,
        "end_ns": start + calibration.window_ns(model),
        "score": score,
    }


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        # Two of ten may alarm: midpoint of the third and second highest.
        ([0.9, 0.7, 0.5, 0.4, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1], 0.6),
        # A tie with the excluded score cannot be split; step above the tie.
        ([0.9, 0.5, 0.5, 0.4, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1], 0.7),
        ([0.8] * 10, 0.9),
        # Fewer than five movements allow none to alarm.
        ([0.2, 0.6, 0.4], 0.8),
    ],
)
def test_install_threshold_matches_offline_rule(scores, expected):
    threshold = calibration.install_threshold(scores, 0.2)
    assert threshold == pytest.approx(expected)
    assert sum(score >= threshold for score in scores) <= 0.2 * len(scores)


@pytest.mark.parametrize("scores", [[], [0.5, 1.2], [1.0] * 10, [float("nan")]])
def test_install_threshold_rejects_unusable_scores(scores):
    with pytest.raises(ValueError):
        calibration.install_threshold(scores, 0.2)


def test_recorder_scores_windows_overlapping_the_movement():
    recorder = calibration.Recorder([MODEL], MAXIMUM_AGE)
    # Without a published window, windows around the start could be missing.
    with pytest.raises(ValueError, match="not ready"):
        recorder.begin(10 * SECOND, generation=1)
    recorder.update([_row(4, 0.97)], 9 * SECOND, generation=1)
    recorder.begin(10 * SECOND, generation=1)
    recorder.end(15 * SECOND)
    rows = [
        _row(6.0, 0.99),  # ends as the movement begins
        _row(6.25, 0.30),
        _row(12.0, None),  # unknown, never counted as a low score
        _row(14.75, 0.40),
        _row(15.0, 0.98),  # begins as the movement ends
    ]
    assert recorder.update(rows, 15 * SECOND + SETTLE - 1, generation=1) is None
    movement = recorder.update([], 15 * SECOND + SETTLE, generation=1)
    assert movement.scores == {MODEL: 0.40}
    assert movement.scored_windows == {MODEL: 2}
    assert movement.published_windows == {MODEL: 3}
    assert movement.prompt == calibration.PROMPTS[0]
    assert recorder.prompt == calibration.PROMPTS[1]


def test_recorder_rejects_movements_it_cannot_score():
    recorder = calibration.Recorder([MODEL, "cnn-4s"], MAXIMUM_AGE)
    recorder.update([_row(1, 0.4), _row(1, 0.4, "cnn-4s")], 0, generation=1)
    # One of two models scored no window.
    recorder.begin(50 * SECOND, generation=1)
    recorder.end(55 * SECOND)
    rows = [_row(51, 0.4), _row(51, None, "cnn-4s")]
    assert recorder.update(rows, 55 * SECOND + SETTLE, generation=1) is None
    assert "cnn-4s scored none of 1" in recorder.message
    # A restarted acquisition drops the windows of the movement.
    recorder.begin(100 * SECOND, generation=1)
    assert recorder.update([], 101 * SECOND, generation=2) is None
    assert recorder.state == "idle" and "restarted" in recorder.message
    # A too-short mark still settles, so its motion reaches no later movement.
    assert not recorder.ready(2)
    rows = [_row(190, 0.4, model, generation=2) for model in recorder.models]
    recorder.update(rows, 199 * SECOND, generation=2)
    recorder.begin(200 * SECOND, generation=2)
    recorder.end(200 * SECOND + 1)
    assert not recorder.ready(2)
    rows = [_row(199, 0.4, model, generation=2) for model in recorder.models]
    assert recorder.update(rows, 201 * SECOND + SETTLE, generation=2) is None
    assert recorder.state == "idle" and recorder.movements == []


def test_prompts_form_a_closed_chain_of_movements():
    pairs = [prompt.split(" to ") for prompt in calibration.PROMPTS]
    assert all(end == begin for (_, end), (begin, _) in itertools.pairwise(pairs))
    assert pairs[0][0] == pairs[-1][1] == "stand"


def test_prediction_log_returns_complete_rows_once(tmp_path):
    path = tmp_path / "predictions.jsonl"
    log = calibration.PredictionLog(path)
    assert log.read() == []
    path.write_text('{"a": 1}\n{"a"')
    assert log.read() == [{"a": 1}]
    with path.open("a") as file:
        file.write(": 2}\n")
    assert log.read() == [{"a": 2}]
    assert log.read() == []


def _config(tmp_path, run, sha="m1", **changes):
    bundle = tmp_path / "models/tonepool_tcn"
    bundle.mkdir(parents=True, exist_ok=True)
    export = {
        "model": "tonepool_tcn",
        "duration_seconds": 4,
        "sha256": sha,
        "normalizer_sha256": "n1",
    }
    (bundle / "manifest.json").write_text(json.dumps({"exports": [export]}))
    output = tmp_path / run
    output.mkdir(exist_ok=True)
    return {
        "model_root": str(tmp_path / "models"),
        "models": [MODEL],
        "output_dir": str(output),
        "hop_ms": 250,
        "delivery_grace_ms": 900,
        "minimum_coverage": 0.7,
        **changes,
    }


def _perform(calibrator, config, index, score):
    """Record one movement through the prediction log."""
    begin = (index + 1) * 100 * SECOND
    health = {"ready": True, "generation": 1, "clock_ns": begin}
    log = Path(config["output_dir"]) / "predictions.jsonl"
    with log.open("a") as file:
        file.write(json.dumps(_row(begin / SECOND - 50, 0.95)) + "\n")
    calibrator.update(health)
    calibrator.mark(health)
    with log.open("a") as file:
        file.write(json.dumps(_row(begin / SECOND + 1, score)) + "\n")
    calibrator.mark({**health, "clock_ns": begin + 5 * SECOND})
    done = {**health, "clock_ns": begin + 5 * SECOND + SETTLE}
    calibrator.update(done)
    return done


def _calibrator(file=None):
    return calibration.Calibrator(fallback=0.5, maximum_age_ns=MAXIMUM_AGE, file=file)


def test_calibrator_applies_withdraws_and_reloads_thresholds(tmp_path):
    config = _config(tmp_path, "run")
    path = tmp_path / "run/calibration.json"
    calibrator = _calibrator()
    calibrator.start(config)
    scores = [0.9, 0.7, 0.5, 0.4, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1]
    for index, score in enumerate(scores):
        assert calibrator.threshold(MODEL) == (0.5, False)
        assert not path.exists()
        health = _perform(calibrator, config, index, score)
    assert calibrator.threshold(MODEL) == (pytest.approx(0.6), True)
    saved = json.loads(path.read_text())
    assert [movement["scores"][MODEL] for movement in saved["movements"]] == scores
    assert saved["settings"]["source"] == "gateway"

    # A restart with the same bundle keeps the threshold; another bundle does not.
    calibrator.start(_config(tmp_path, "restart"))
    assert calibrator.threshold(MODEL) == (pytest.approx(0.6), True)
    calibrator.start(_config(tmp_path, "replaced", sha="m2"))
    assert calibrator.threshold(MODEL) == (0.5, False)

    reloaded = _calibrator(path)
    reloaded.start(_config(tmp_path, "later"))
    assert reloaded.threshold(MODEL) == (pytest.approx(0.6), True)
    for changes, message in [
        ({"hop_ms": 500}, "hop_ms"),
        ({"minimum_coverage": 0.5}, "minimum_coverage"),
        ({"replay": {"captures": ["x"]}}, "source"),
        ({"sha": "m2"}, "another tonepool_tcn-4s bundle"),
    ]:
        with pytest.raises(ValueError, match=message):
            _calibrator(path).start(_config(tmp_path, "other", **changes))

    # Discarding a movement of a finished calibration withdraws it.
    calibrator = _calibrator()
    calibrator.start(_config(tmp_path, "run"))
    (tmp_path / "run/predictions.jsonl").unlink()
    for index, score in enumerate(scores):
        health = _perform(calibrator, config, index, score)
    assert calibrator.threshold(MODEL)[1]
    calibrator.discard(health)
    assert calibrator.threshold(MODEL) == (0.5, False)
    assert not path.exists()


def test_load_thresholds_rejects_other_files(tmp_path):
    path = tmp_path / "calibration.json"
    for content in ("[]", "{}", "not json", '{"schema_version": 2}'):
        path.write_text(content)
        with pytest.raises(ValueError, match="not a detector calibration"):
            calibration.load_thresholds(path, settings={}, identities={})


def test_main_rejects_calibration_without_window(capsys):
    with pytest.raises(SystemExit):
        app.main(["--headless", "--calibration", "calibration.json"])
    assert "--calibration needs the window" in capsys.readouterr().err
