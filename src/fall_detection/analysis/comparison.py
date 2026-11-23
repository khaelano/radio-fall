"""Put the sequence models and the baselines on the same held-out attempts.

``03_training`` splits attempts once; the baseline notebooks reuse that split
through :func:`split_assignment`, and the comparison notebook scores every
approach with :func:`summarize`. Each approach decides on its own unit (a
sequence window, a WiFall window or a FallDeFi trace), so the common unit is
the attempt: an attempt is a fall when any of its units is, and it is
predicted as a fall when any of its units is predicted as one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from .baselines._grouped_holdout import binary_metrics

DEFAULT_REPRESENTATION = "log1p_squared_difference"
"""Sequence signal the live detector computes; ``03_training`` runs default to it."""

DEFAULT_KEEP_SPLIT = ("continuous_non_fall",)
"""Datasets that keep their random split in a ``03_training`` session holdout."""

SEQUENCE_GROUP_SEPARATOR = "::"
"""Separator between session and attempt in the sequence export's ``group``."""


def baseline_group(group: str) -> str:
    """Return an attempt identity in the baselines' ``<session>/<attempt>`` form.

    Args:
        group: Sequence ``<session>::<attempt>`` or baseline identity.

    Returns:
        The identity with ``/`` between session and attempt key.

    Raises:
        ValueError: An identity without a session part.
    """
    session, separator, attempt = group.partition(SEQUENCE_GROUP_SEPARATOR)
    if separator:
        if not session or not attempt:
            raise ValueError(f"Malformed sequence group: {group!r}")
        return f"{session}/{attempt}"
    if "/" not in group:
        raise ValueError(f"Group has no session part: {group!r}")
    return group


def split_assignment(split: pl.DataFrame) -> dict[str, str]:
    """Return each attempt's split from a ``03_training`` window split.

    Args:
        split: ``window_split.parquet`` with ``group`` and ``split`` columns.

    Returns:
        Baseline attempt identity to ``train``, ``validation`` or ``test``.

    Raises:
        ValueError: An attempt assigned to more than one split.
    """
    pairs = split.select("group", "split").unique()
    if pairs["group"].n_unique() != len(pairs):
        raise ValueError("An attempt appears in more than one split")
    return {baseline_group(group): name for group, name in pairs.iter_rows()}


def split_labels(split: pl.DataFrame) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the activity labels the sequence export mapped to fall and non-fall.

    Args:
        split: Window split with ``activity_label`` and ``target`` columns.

    Returns:
        Sorted fall labels and sorted non-fall labels.

    Raises:
        ValueError: A label with windows of both targets.
    """
    targets = split.group_by("activity_label").agg(pl.col("target").unique())
    fall, non_fall = [], []
    for label, values in targets.iter_rows():
        if set(values) == {1}:
            fall.append(label)
        elif set(values) == {0}:
            non_fall.append(label)
        else:
            raise ValueError(f"Label {label!r} has windows of both targets")
    return tuple(sorted(fall)), tuple(sorted(non_fall))


def split_sessions(split: pl.DataFrame) -> list[str]:
    """Return the sorted session identities that a window split covers."""
    return sorted(
        {baseline_group(group).split("/", 1)[0] for group in split["group"].unique()}
    )


def latest_run(directory: Path, required: str) -> Path:
    """Return the newest run directory that contains a required file.

    Run directories are named by UTC timestamp, so the newest sorts last.

    Args:
        directory: Notebook run directory such as ``artifacts/notebooks/03_training``.
        required: Relative path that a usable run must contain.

    Returns:
        The newest qualifying run directory.

    Raises:
        FileNotFoundError: No run contains the required file.
    """
    runs = sorted(
        path
        for path in directory.glob("*")
        if path.is_dir() and (path / required).exists()
    )
    if not runs:
        raise FileNotFoundError(f"No run under {directory} contains {required}")
    return runs[-1]


def latest_training_run(
    directory: Path,
    required: str,
    *,
    representation: str = DEFAULT_REPRESENTATION,
    held_out_session: str | Sequence[str] | None = None,
    keep_split: Sequence[str] = DEFAULT_KEEP_SPLIT,
) -> Path:
    """Return the newest ``03_training`` run of one representation and split.

    Runs recorded before ``03_training`` stored these settings lack them in
    their manifest; they count as the default representation, a random
    attempt split and, for a holdout, :data:`DEFAULT_KEEP_SPLIT`.

    Args:
        directory: ``artifacts/notebooks/03_training``.
        required: Relative path that a usable run must contain.
        representation: Sequence signal the run must have been trained on.
        held_out_session: Dataset or datasets held out entirely (order
            ignored), or None for the random attempt split.
        keep_split: Datasets that kept their random split in a holdout; held-out
            datasets are dropped from it, and it is ignored without a holdout.

    Returns:
        The newest qualifying run directory.

    Raises:
        FileNotFoundError: No run has the file, representation and split.
    """

    def matches(path: Path) -> bool:
        manifest_path = path / "manifest.json"
        if not (path / required).exists() or not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text())
        held_out = _held_out_key(manifest.get("held_out_session"))
        kept = manifest.get("keep_split")
        return (
            manifest.get("representation", DEFAULT_REPRESENTATION) == representation
            and held_out == wanted_held_out
            and _kept_key(held_out, DEFAULT_KEEP_SPLIT if kept is None else kept)
            == wanted_kept
        )

    wanted_held_out = _held_out_key(held_out_session)
    wanted_kept = _kept_key(wanted_held_out, keep_split)

    runs = sorted(
        path for path in directory.glob("*") if path.is_dir() and matches(path)
    )
    if not runs:
        split = "+".join(wanted_held_out) if wanted_held_out else "random-split"
        if wanted_kept:
            split += f" (keeping {'+'.join(wanted_kept)})"
        raise FileNotFoundError(
            f"No {representation} {split} run under {directory} contains {required}"
        )
    return runs[-1]


def _held_out_key(value: str | Sequence[str] | None) -> tuple[str, ...]:
    """Normalize a held-out setting: None, one dataset, or several in any order."""
    if value is None:
        return ()
    return (value,) if isinstance(value, str) else tuple(sorted(value))


def _kept_key(held_out: tuple[str, ...], keep_split: Sequence[str]) -> tuple[str, ...]:
    """Return the datasets that effectively kept their split in a holdout."""
    if not held_out:
        return ()
    return tuple(sorted(name for name in keep_split if name not in held_out))


def latest_split_run(directory: Path, split_sha256: str) -> Path:
    """Return the newest baseline run fitted on one ``03_training`` split.

    Args:
        directory: Baseline notebook run directory such as
            ``artifacts/notebooks/05_falldefi``.
        split_sha256: SHA-256 of the split file the run must have used, as
            recorded in its ``manifest.json``.

    Returns:
        The newest run directory with that split.

    Raises:
        FileNotFoundError: No run used the split.
    """
    runs = sorted(
        path
        for path in directory.glob("*")
        if (path / "manifest.json").is_file()
        and json.loads((path / "manifest.json").read_text()).get("split_sha256")
        == split_sha256
    )
    if not runs:
        raise FileNotFoundError(
            f"No run under {directory} used split {split_sha256[:12]}; "
            "run the baseline notebook on that 03_training run first"
        )
    return runs[-1]


def attempt_outcomes(rows: Iterable[dict[str, Any]]) -> pl.DataFrame:
    """Reduce unit predictions to one target and prediction per attempt.

    Args:
        rows: Units with ``group``, binary ``target`` and binary ``prediction``.

    Returns:
        One row per attempt (baseline identity), with the any-unit target and
        prediction and the number of units scored.
    """
    frame = pl.DataFrame(
        [
            {
                "group": baseline_group(str(row["group"])),
                "target": int(row["target"]),
                "prediction": int(row["prediction"]),
            }
            for row in rows
        ],
        schema={"group": pl.String, "target": pl.Int64, "prediction": pl.Int64},
    )
    return (
        frame.group_by("group")
        .agg(
            pl.col("target").max(),
            pl.col("prediction").max(),
            pl.len().alias("units"),
        )
        .sort("group")
    )


def summarize(
    approach: str, unit: str, rows: list[dict[str, Any]], test_attempts: set[str]
) -> dict[str, Any]:
    """Score one approach on its own unit and on the shared attempt level.

    Args:
        approach: Display name, such as ``CNN 2s`` or ``WiFall random forest``.
        unit: What one prediction covers, such as ``2 s window`` or ``trace``.
        rows: Held-out units with ``group``, ``target`` and ``prediction``.
        test_attempts: Baseline identities of the split's test attempts.

    Returns:
        Unit and attempt metrics with their denominators, and the test
        attempts this approach could not score.

    Raises:
        ValueError: Units from attempts outside the test split.
    """
    attempts = attempt_outcomes(rows)
    outside = set(attempts["group"]) - test_attempts
    if outside:
        raise ValueError(f"{approach} scored attempts outside the test split")
    target = np.array([int(row["target"]) for row in rows])
    prediction = np.array([int(row["prediction"]) for row in rows])
    return {
        "approach": approach,
        "unit": unit,
        "units": len(rows),
        "unit_metrics": binary_metrics(target, prediction),
        "attempts": len(attempts),
        "attempt_metrics": binary_metrics(
            attempts["target"].to_numpy(), attempts["prediction"].to_numpy()
        ),
        "unscored_test_attempts": sorted(test_attempts - set(attempts["group"])),
    }
