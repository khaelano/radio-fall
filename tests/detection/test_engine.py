import json
from types import SimpleNamespace

from fall_detection.detection.engine import DetectorEngine


class Frame:
    def __init__(self, valid=True, end=100):
        self.value = dict(
            generation=1,
            end_ns=end,
            valid=valid,
            reason="coverage",
            phase_change_coverage=[0.8] * 4,
        )

    def metadata_json(self):
        return json.dumps(self.value)

    def tensor_bytes(self):
        return b"input"


class Native:
    def __init__(self):
        self.frame = None
        self.generation = 1

    def poll(self):
        frame, self.frame = self.frame, None
        return frame

    def stats_json(self):
        return json.dumps(dict(generation=self.generation))

    def reset(self):
        self.generation += 1

    def close(self):
        pass


class Scorer:
    dropped = 0

    def __init__(self):
        self.result = None
        self.jobs = []

    def submit(self, encoded, meta):
        self.jobs.append((encoded, meta))

    def poll(self):
        result, self.result = self.result, None
        return result

    def close(self):
        pass


def engine():
    obj = DetectorEngine.__new__(DetectorEngine)
    obj.native = Native()
    obj.scorer = Scorer()
    obj.last = None
    obj.last_quality = None
    obj.failure = ""
    obj.invalid_end_ns = 0
    obj.maximum_result_age_ns = 1000
    obj.bundle = SimpleNamespace(metadata=dict(threshold=0.5))
    return obj


def test_invalid_quality_does_not_become_nonfall_or_accept_older_inflight_score():
    detector = engine()
    detector.native.frame = Frame(valid=False, end=200)
    detector.scorer.result = dict(
        kind="prediction", generation=1, end_ns=100, probability=0.9
    )
    events = detector.tick(now_ns=300)
    assert events[0]["kind"] == "insufficient_data"
    assert events[0]["probability"] is None
    assert detector.last is None
    assert detector.scorer.jobs == []


def test_old_generation_late_and_offline_results_are_suppressed():
    for generation, end, ready in [(0, 100, True), (1, 1, True), (1, 2000, False)]:
        detector = engine()
        detector.scorer.result = dict(
            kind="prediction", generation=generation, end_ns=end, probability=0.9
        )
        assert detector.tick(now_ns=2000, radio_ready=ready) == []
        assert detector.last is None


def test_valid_score_is_experimental_candidate_and_interruption_clears_it():
    detector = engine()
    detector.native.frame = Frame()
    detector.scorer.result = dict(
        kind="prediction", generation=1, end_ns=100, probability=0.9
    )
    events = detector.tick(now_ns=300)
    assert events[0]["candidate"] is True
    assert len(detector.scorer.jobs) == 1
    detector.interrupt("reference disconnected")
    assert detector.last is None and detector.native.generation == 2
