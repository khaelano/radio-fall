"""Installation calibration of the live decision threshold.

The detector's scores shift with how a person moves, so a threshold chosen on
the training sessions misses its target on a new one. At installation the
person performs a few ordinary movements, known non-falls, and the threshold is
set so that at most a target share of them would alarm. Scoring stays in Rust:
this module only reads the published rows of ``predictions.jsonl``.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The evaluated setting, not an optimum: see docs/reports/live-calibration-2026-11-24.md.
TARGET_FALSE_POSITIVE_RATE = 0.2
# One calibration. Each movement starts where the previous one ended, beginning
# and ending standing. The mix matters: a single kind misses the target.
PROMPTS = (
    "stand to walk",
    "walk to sit",
    "sit to stand",
    "stand to sit",
    "sit to walk",
    "walk to stand",
    "stand to sit",
    "sit to walk",
    "walk to sit",
    "sit to stand",
)
# Future filter context of the Rust preprocessing contract.
FUTURE_CONTEXT_MS = 250
MINIMUM_MOVEMENT_NS = 1_000_000_000
# Slack for the last rows to reach the log after their publication deadline.
SETTLE_MARGIN_NS = 250_000_000
SCHEMA_VERSION = 1
SETTINGS = ("source", "hop_ms", "delivery_grace_ms", "minimum_coverage")


def maximum_age_ns(hop_ms: int, grace_ms: int) -> int:
    """Return the age at which the detector stops publishing a window's score."""
    return (FUTURE_CONTEXT_MS + grace_ms + 2 * hop_ms) * 1_000_000


def window_ns(model: str) -> int:
    """Return the window length of a ``<family>-<seconds>s`` model ID."""
    return int(model.rsplit("-", 1)[1].removesuffix("s")) * 1_000_000_000


def install_threshold(scores: Sequence[float], target: float) -> float:
    """Set the threshold from the scores of known non-fall movements.

    The threshold is the midpoint between the highest score that must not alarm
    and the next score above it, so at most ``floor(target * len(scores))``
    movements alarm (score at or above the threshold).

    Args:
        scores: Highest window score of each movement.
        target: Highest acceptable share of movements that alarm, from zero to
            below one.

    Returns:
        Threshold in ``(0, 1]``.

    Raises:
        ValueError: No scores, a target outside its range, a score outside zero
            to one, or a score of one that must not alarm.
    """
    if not scores or not 0 <= target < 1:
        raise ValueError("Calibration needs scores and a target in [0, 1)")
    if any(not 0 <= score <= 1 for score in scores):
        raise ValueError("Calibration scores must lie in [0, 1]")
    ordered = sorted(scores, reverse=True)
    excluded = ordered[math.floor(target * len(ordered) + 1e-9)]
    if excluded >= 1:
        raise ValueError("The model scores ordinary movements at 1; no threshold fits")
    above = [score for score in ordered if score > excluded]
    return (excluded + (min(above) if above else 1.0)) / 2


@dataclass(frozen=True)
class Movement:
    """One recorded non-fall movement and its highest window score per model."""

    prompt: str
    begin_ns: int
    end_ns: int
    scores: dict[str, float]
    scored_windows: dict[str, int]
    published_windows: dict[str, int]


class PredictionLog:
    """Complete rows appended to ``predictions.jsonl`` since the last read.

    The detector's poll keeps only the latest row per model, so a stalled
    frontend would miss windows; the log has every one.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._offset = 0
        self._partial = b""

    def read(self) -> list[dict[str, Any]]:
        """Return newly completed rows; none before the detector opens the log."""
        try:
            with self.path.open("rb") as file:
                file.seek(self._offset)
                data = file.read()
        except FileNotFoundError:
            return []
        self._offset += len(data)
        *lines, self._partial = (self._partial + data).split(b"\n")
        return [json.loads(line) for line in lines if line]


class Recorder:
    """Collect movements from operator marks and published rows.

    A movement's score is the highest score among windows that overlap it, as
    any of them can alarm. After a movement the recorder settles until every
    such window has been published, so no window spans two movements.

    Args:
        models: Selected model IDs; each is calibrated on the same movements.
        maximum_age_ns: Age at which the detector stops publishing scores.
    """

    def __init__(self, models: Sequence[str], maximum_age_ns: int) -> None:
        self.models = tuple(models)
        self.settle_ns = (
            max(window_ns(model) for model in self.models)
            + maximum_age_ns
            + SETTLE_MARGIN_NS
        )
        self.movements: list[Movement] = []
        self.state = "idle"
        self.message = ""
        self._begin_ns = self._end_ns = self._generation = 0
        self._discard = False
        self._rows: list[dict[str, Any]] = []
        self._published_generation: dict[str, int] = {}

    @property
    def prompt(self) -> str:
        """Movement to perform next."""
        return PROMPTS[len(self.movements) % len(PROMPTS)]

    @property
    def complete(self) -> bool:
        """Whether enough movements are recorded to set a threshold."""
        return len(self.movements) >= len(PROMPTS)

    def settle_remaining_ns(self, clock_ns: int) -> int:
        """Return how long the person must still stay still."""
        if self.state != "settling":
            return 0
        return max(0, self._end_ns + self.settle_ns - clock_ns)

    def ready(self, generation: int) -> bool:
        """Whether a movement can start in this acquisition segment.

        Until every model has published a window of the segment, windows that
        would overlap the movement's start can be missing.
        """
        return self.state == "idle" and all(
            self._published_generation.get(model) == generation for model in self.models
        )

    def begin(self, clock_ns: int, generation: int) -> None:
        """Mark the start of a movement on the detector clock."""
        if not self.ready(generation):
            raise ValueError("The recorder is not ready for a movement")
        self._begin_ns, self._generation = clock_ns, generation
        self._discard = False
        self._rows = []
        self.state, self.message = "recording", ""

    def end(self, clock_ns: int) -> None:
        """Mark the end of the movement; its windows are still being scored."""
        if self.state != "recording":
            raise ValueError("No movement is being recorded")
        self._end_ns = clock_ns
        self.state = "settling"
        if clock_ns - self._begin_ns < MINIMUM_MOVEMENT_NS:
            self._discard = True
            self.message = "Movement too short; mark its start and end"

    def discard(self, clock_ns: int) -> None:
        """Drop the movement in progress, or the last recorded one when idle."""
        if self.state == "recording":
            self.end(clock_ns)
        if self.state == "settling":
            self._discard = True
            self.message = "Movement discarded"
        elif self.movements:
            self.movements.pop()
            self.message = "Last movement discarded"

    def update(
        self, rows: Sequence[dict[str, Any]], clock_ns: int, generation: int
    ) -> Movement | None:
        """Take newly published rows and finish a settled movement.

        Args:
            rows: New rows of the prediction log.
            clock_ns: Detector clock, in the domain of the row times.
            generation: Current acquisition segment.

        Returns:
            The movement recorded by this call, if any.
        """
        for row in rows:
            self._published_generation[row["model_id"]] = row["generation"]
        if self.state == "idle":
            return None
        if generation != self._generation:
            self.state = "idle"
            self.message = "Acquisition restarted during the movement; repeat it"
            return None
        self._rows.extend(rows)
        if self.state == "recording" or self.settle_remaining_ns(clock_ns):
            return None
        self.state = "idle"
        if self._discard:
            return None
        return self._finish()

    def _finish(self) -> Movement | None:
        scores: dict[str, float] = {}
        scored, published = {}, {}
        for model in self.models:
            windows = [
                row["score"]
                for row in self._rows
                if row["model_id"] == model
                and row["start_ns"] < self._end_ns
                and row["end_ns"] > self._begin_ns
            ]
            present = [score for score in windows if score is not None]
            if not present:
                # An unscored movement is unknown, not a low score.
                self.message = (
                    f"{model} scored none of {len(windows)} windows "
                    "(receiver coverage); repeat the movement"
                )
                return None
            scores[model] = max(present)
            scored[model], published[model] = len(present), len(windows)
        movement = Movement(
            self.prompt, self._begin_ns, self._end_ns, scores, scored, published
        )
        self.movements.append(movement)
        self.message = "Recorded " + ", ".join(
            f"{model} {scores[model]:.3f} ({scored[model]} of {published[model]} windows)"
            for model in self.models
        )
        return movement

    def thresholds(self) -> dict[str, float]:
        """Return each model's threshold, or nothing before enough movements.

        Raises:
            ValueError: A model cannot be calibrated on these movements.
        """
        if not self.complete:
            return {}
        result = {}
        for model in self.models:
            scores = [movement.scores[model] for movement in self.movements]
            try:
                result[model] = install_threshold(scores, TARGET_FALSE_POSITIVE_RATE)
            except ValueError as error:
                raise ValueError(f"{model}: {error}") from error
        return result


def bundle_identities(
    model_root: Path, models: Sequence[str]
) -> dict[str, dict[str, str]]:
    """Read the published hashes of models and normalizers.

    The Rust loader verifies the files against these hashes.

    Args:
        model_root: Directory of the model bundles.
        models: Model IDs.

    Returns:
        ``sha256`` and ``normalizer_sha256`` by model ID.

    Raises:
        OSError: A bundle manifest cannot be read.
        ValueError: A manifest does not list a model.
    """
    result = {}
    for model in models:
        family, duration = model.rsplit("-", 1)
        manifest = json.loads((model_root / family / "manifest.json").read_text())
        rows = [
            row
            for row in manifest["exports"]
            if row["model"] == family and f"{row['duration_seconds']}s" == duration
        ]
        if len(rows) != 1:
            raise ValueError(f"{model} is not in its bundle manifest")
        result[model] = {
            key: str(rows[0][key]) for key in ("sha256", "normalizer_sha256")
        }
    return result


def detector_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Return the settings of a detector configuration that shape its scores."""
    return {
        "source": "replay" if config.get("replay") else "gateway",
        **{key: config[key] for key in SETTINGS if key != "source"},
    }


def save_calibration(
    path: Path,
    *,
    created_at: str,
    settings: dict[str, Any],
    movements: Sequence[Movement],
    thresholds: dict[str, float],
    identities: dict[str, dict[str, str]],
) -> None:
    """Write a calibration atomically, replacing an earlier one.

    Args:
        path: Output JSON file.
        created_at: ISO 8601 time.
        settings: Result of :func:`detector_settings`.
        movements: Recorded movements.
        thresholds: Threshold by model ID.
        identities: Result of :func:`bundle_identities` for those models.
    """
    content = {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at,
        "settings": settings,
        "target_false_positive_rate": TARGET_FALSE_POSITIVE_RATE,
        "models": {
            model: {"threshold": threshold, **identities[model]}
            for model, threshold in thresholds.items()
        },
        "movements": [asdict(movement) for movement in movements],
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def load_thresholds(
    path: Path,
    *,
    settings: dict[str, Any],
    identities: dict[str, dict[str, str]],
) -> tuple[dict[str, float], str]:
    """Read the thresholds that apply to the current detector.

    Scores depend on the bundle, the hop and the coverage gate, so a calibration
    made under other settings is refused rather than applied.

    Args:
        path: File written by :func:`save_calibration`.
        settings: Settings of the current detector.
        identities: Hashes of the selected models.

    Returns:
        Threshold by selected model ID (models missing from the file are left
        out) and the calibration's creation time.

    Raises:
        OSError: The file cannot be read.
        ValueError: The file is not a calibration, or it was made for other
            settings or another bundle of a selected model.
    """
    try:
        content = json.loads(path.read_text())
        if content["schema_version"] != SCHEMA_VERSION:
            raise ValueError("unsupported schema version")
        recorded, models = content["settings"], content["models"]
        created_at = str(content["created_at"])
        thresholds = {name: float(row["threshold"]) for name, row in models.items()}
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"{path} is not a detector calibration: {error}") from error
    if any(not 0 < value <= 1 for value in thresholds.values()):
        raise ValueError(f"{path} holds a threshold outside (0, 1]")
    for key in SETTINGS:
        if recorded.get(key) != settings[key]:
            raise ValueError(
                f"{path} was made with {key} {recorded.get(key)}, "
                f"the detector uses {settings[key]}"
            )
    for model, identity in identities.items():
        if model in models and any(
            models[model].get(key) != value for key, value in identity.items()
        ):
            raise ValueError(f"{path} was made for another {model} bundle")
    return (
        {model: thresholds[model] for model in identities if model in thresholds},
        created_at,
    )


@dataclass(frozen=True)
class _Calibrated:
    threshold: float
    created_at: str
    identity: dict[str, str]


class Calibrator:
    """Thresholds of a detector window, across restarts with other models.

    Args:
        fallback: Threshold of models without a calibration.
        maximum_age_ns: Age at which the detector stops publishing scores.
        file: Calibration of an earlier run to apply.
    """

    def __init__(
        self, *, fallback: float, maximum_age_ns: int, file: Path | None = None
    ) -> None:
        self._fallback = fallback
        self._maximum_age_ns = maximum_age_ns
        self._file = file
        # From the file or an earlier selection, and from the current recorder.
        self._kept: dict[str, _Calibrated] = {}
        self._fitted: dict[str, _Calibrated] = {}

    def start(self, config: dict[str, Any]) -> None:
        """Prepare for a new detector run.

        Args:
            config: Native detector configuration.

        Raises:
            OSError: A bundle manifest or the calibration file cannot be read.
            ValueError: The calibration file does not fit this configuration.
        """
        models = config["models"]
        settings = detector_settings(config)
        identities = bundle_identities(Path(config["model_root"]), models)
        loaded = {}
        if self._file:
            values, created_at = load_thresholds(
                self._file, settings=settings, identities=identities
            )
            loaded = {
                model: _Calibrated(value, created_at, identities[model])
                for model, value in values.items()
            }
        self._kept = {
            model: entry
            for model, entry in {**loaded, **self._kept, **self._fitted}.items()
            # A bundle replaced on disk invalidates its threshold.
            if entry.identity == identities.get(model, entry.identity)
        }
        self._fitted = {}
        self._settings, self._identities = settings, identities
        output = Path(config["output_dir"])
        self._path = output / "calibration.json"
        self._log = PredictionLog(output / "predictions.jsonl")
        self.recorder = Recorder(models, self._maximum_age_ns)

    def threshold(self, model: str) -> tuple[float, bool]:
        """Return a model's threshold and whether it is calibrated."""
        entry = self._fitted.get(model) or self._kept.get(model)
        return (entry.threshold, True) if entry else (self._fallback, False)

    def can_mark(self, health: dict[str, Any]) -> bool:
        """Whether :meth:`mark` would start or end a movement now."""
        return self.recorder.state == "recording" or (
            bool(health.get("ready"))
            and not health.get("error")
            and self.recorder.ready(health["generation"])
        )

    def mark(self, health: dict[str, Any]) -> None:
        """Start a movement, or end the one being recorded."""
        if self.recorder.state == "recording":
            self.recorder.end(health["clock_ns"])
        elif self.can_mark(health):
            self.recorder.begin(health["clock_ns"], health["generation"])

    def discard(self, health: dict[str, Any]) -> None:
        """Drop the movement in progress or the last one, and refit without it."""
        recorded = len(self.recorder.movements)
        self.recorder.discard(health["clock_ns"])
        if len(self.recorder.movements) < recorded:
            self._fit()

    def update(self, health: dict[str, Any]) -> None:
        """Read new rows and fit the thresholds when a movement is added."""
        if self.recorder.update(
            self._log.read(), health["clock_ns"], health["generation"]
        ):
            self._fit()

    def _fit(self) -> None:
        self._fitted = {}
        try:
            thresholds = self.recorder.thresholds()
        except ValueError as error:
            self.recorder.message = str(error)
            thresholds = {}
        if not thresholds:
            # A file from before the last change would hold a dropped movement.
            self._path.unlink(missing_ok=True)
            return
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        save_calibration(
            self._path,
            created_at=created_at,
            settings=self._settings,
            movements=self.recorder.movements,
            thresholds=thresholds,
            identities=self._identities,
        )
        self._fitted = {
            model: _Calibrated(value, created_at, self._identities[model])
            for model, value in thresholds.items()
        }
        self.recorder.message += f" · calibrated, saved to {self._path}"

    def status(self, clock_ns: int) -> str:
        """Describe the calibration and what to do next."""
        recorder = self.recorder
        count = len(recorder.movements)
        if recorder.state == "recording":
            text = f"recording “{recorder.prompt}”: stop when it ends, then stay still"
        elif recorder.state == "settling":
            left = recorder.settle_remaining_ns(clock_ns) / 1e9
            text = f"stay still for {math.ceil(left)} s"
        elif recorder.complete:
            text = f"{count} movements recorded"
        else:
            text = f"next movement {count + 1} of {len(PROMPTS)}: “{recorder.prompt}”"
        if recorder.message:
            return f"{text} · {recorder.message}"
        dates = sorted(
            {
                self._kept[model].created_at
                for model in recorder.models
                if model in self._kept
            }
        )
        if dates and not self._fitted:
            text += f" · using the calibration of {', '.join(dates)}"
        return text
