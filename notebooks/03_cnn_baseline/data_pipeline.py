"""Independent, traceable trial preparation for the CSI CNN pilot."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path

import numpy as np
import pandas as pd

from vendor.phase_motion import phase_change_matrix
from vendor.phase_signals import load_phase_signal

LABELS = (
    "walk_to_fall",
    "sit_to_fall",
    "stand_to_fall",
    "walk_to_sit",
    "sit_to_walk",
    "sit_to_stand",
)
REPRESENTATIONS = (
    "amplitude",
    "raw_phase",
    "calibrated_phase",
    "phase_change",
    "phase_change_smoothed",
)


def read_json(path: Path) -> dict:
    """Read a UTF-8 JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    """Write portable JSON and reject non-finite numeric values."""
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    """Hash a file without loading it fully into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(session: Path) -> pd.DataFrame:
    """Resolve reviewed labels and reconstruct cue times with exclusion reasons."""
    manifest = read_json(session / "session.json")
    if manifest.get("status") == "open":
        raise ValueError("Refusing an active session")
    review_path = session / "session_review.json"
    review = read_json(review_path) if review_path.exists() else {}
    protocol = read_json(session / "protocol.json")
    scenarios = {
        scenario["id"]: scenario.get("attributes", {})
        for block in protocol["blocks"]
        for scenario in block["scenarios"]
    }
    events = [
        json.loads(line)
        for line in (session / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    records = []
    for path in sorted(session.glob("trials/*/attempt_*/attempt.json")):
        meta = read_json(path)
        relpath = path.parent.relative_to(session).as_posix()
        reviewed = review.get("attempts", {}).get(relpath, {})
        label = (
            meta.get("reference_truth_label")
            or reviewed.get("activity_label")
            or meta["activity_label"]
        )
        number = int(path.parent.name.removeprefix("attempt_"))
        phases = sorted(
            [
                event
                for event in events
                if event.get("kind") == "phase_changed"
                and event.get("trial_ordinal") == meta["trial_ordinal"]
                and event.get("attempt") == number
            ],
            key=lambda event: event["monotonic_ns"],
        )
        reason = ""
        if meta.get("status") != "accepted":
            reason = "not accepted"
        elif reviewed.get("inclusion") == "exclude" or reviewed.get("quality") == "bad":
            reason = "review excludes attempt"
        elif label not in LABELS:
            reason = "unknown label"
        elif [event["state"] for event in phases] != [
            "countdown",
            "action",
            "recovery",
        ]:
            reason = "incomplete or duplicate phase events"
        times = [event["monotonic_ns"] for event in phases]
        ended = meta.get("ended_monotonic_ns", 0)
        if not reason and (not all(a < b for a, b in zip(times, times[1:] + [ended]))):
            reason = "invalid phase ordering"
        attrs = scenarios.get(meta.get("scenario_id"), {})
        action = (
            (times[1] - meta["started_monotonic_ns"]) / 1e9
            if len(times) == 3
            else np.nan
        )
        recovery = (
            (times[2] - meta["started_monotonic_ns"]) / 1e9
            if len(times) == 3
            else np.nan
        )
        records.append(
            {
                "attempt_id": f"{meta['trial_ordinal']:03d}/{number:02d}",
                "attempt_relpath": relpath,
                "trial_ordinal": meta["trial_ordinal"],
                "session_id": manifest["session_id"],
                "participant_id": review.get("metadata", {}).get("participant_id")
                or manifest.get("participant_id"),
                "label": label,
                "target": int(label in LABELS[:3]),
                "scenario_id": meta["scenario_id"],
                "start_direction": attrs.get("start_direction"),
                "end_direction": attrs.get("end_direction"),
                "action_start_s": action,
                "action_duration_s": recovery - action,
                "ended_s": (ended - meta["started_monotonic_ns"]) / 1e9,
                "exclusion_reason": reason,
            }
        )
    return pd.DataFrame(records)


def assign_splits(table: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Stratify scenarios by activity, keeping all repetitions in one partition."""
    result = table.copy()
    result["split"] = ""
    rng = np.random.default_rng(seed)
    if result.groupby("scenario_id")["label"].nunique().max() != 1:
        raise ValueError("A scenario has inconsistent reviewed activity labels")
    for label in LABELS:
        groups = np.array(
            sorted(result.loc[result.label.eq(label), "scenario_id"].unique())
        )
        if len(groups) < 3:
            raise ValueError(f"Need at least three scenarios for {label}")
        rng.shuffle(groups)
        n_test = max(1, round(len(groups) * 0.2))
        n_val = max(1, round(len(groups) * 0.2))
        for split, values in (
            ("test", groups[:n_test]),
            ("validation", groups[n_test : n_test + n_val]),
            ("train", groups[n_test + n_val :]),
        ):
            result.loc[result.scenario_id.isin(values), "split"] = split
    if (
        result.split.eq("").any()
        or result.groupby("scenario_id").split.nunique().max() != 1
    ):
        raise AssertionError("Split assignment failed")
    # Retakes of a trial must stay with the original scenario as well.
    if result.groupby("trial_ordinal").split.nunique().max() != 1:
        raise AssertionError("A trial crosses partitions")
    return result


def bin_values(
    seconds: np.ndarray, values: np.ndarray, bins: int, hz: int
) -> np.ndarray:
    """Average each tone inside fixed time bins; leave empty bins missing.

    Does not interpolate across gaps or mix physical subcarriers. Sine/cosine
    components must be supplied for circular values.
    """
    indices = np.floor(seconds * hz).astype(int)
    selected = (indices >= 0) & (indices < bins)
    indices, values = indices[selected], values[selected]
    finite = np.isfinite(values)
    totals = np.zeros((bins, values.shape[1]), dtype=np.float64)
    counts = np.zeros_like(totals)
    np.add.at(totals, indices, np.where(finite, values, 0))
    np.add.at(counts, indices, finite)
    return np.divide(
        totals, counts, out=np.full_like(totals, np.nan), where=counts > 0
    ).astype(np.float32)


def smooth_valid(values: np.ndarray, width: int) -> np.ndarray:
    """Average adjacent supported bins without filling a missing center bin."""
    if width < 1 or width % 2 != 1:
        raise ValueError("Smoothing width must be positive and odd")
    pad = width // 2
    padded = np.pad(values, ((0, 0), (pad, pad), (0, 0)), constant_values=np.nan)
    stack = np.stack(
        [padded[:, offset : offset + values.shape[1]] for offset in range(width)]
    )
    finite = np.isfinite(stack)
    count = finite.sum(axis=0)
    total = np.where(finite, stack, 0).sum(axis=0)
    result = np.divide(total, count, out=np.full_like(total, np.nan), where=count > 0)
    result[~np.isfinite(values)] = np.nan
    return result.astype(np.float32)


def _prepare_one(job: tuple) -> tuple[dict, dict | None]:
    session, row, config = job
    diagnostics = {"attempt_id": row["attempt_id"], "read_error": ""}
    outputs = {name: [] for name in REPRESENTATIONS}
    bins = round(config["window_seconds"] * config["bin_hz"])
    try:
        if row["action_start_s"] + config["window_seconds"] > row["ended_s"]:
            raise ValueError("Recording does not cover fixed window")
        for receiver in config["receivers"]:
            signal = load_phase_signal(session, row["attempt_id"], receiver)
            if not np.array_equal(signal.subcarriers, np.arange(-122, 123)):
                raise ValueError("Unexpected physical tone layout")
            # Drop only the three structurally invalid DC slots, for every trial.
            keep = ~np.isin(signal.subcarriers, [-1, 0, 1])
            times = signal.time_seconds - row["action_start_s"]
            common = np.isfinite(signal.raw_phase[:, keep]) & np.isfinite(
                signal.calibrated_phase[:, keep]
            )
            amplitude = np.where(
                common, np.log1p(np.abs(signal.complex_csi[:, keep])), np.nan
            )
            raw = np.where(common, signal.raw_phase[:, keep], np.nan)
            calibrated = np.where(common, signal.calibrated_phase[:, keep], np.nan)
            changes = phase_change_matrix(
                calibrated, signal.time_seconds, config["lag_seconds"]
            )
            arrays = {"amplitude": amplitude[None]}
            for name, matrix in [
                ("raw_phase", raw),
                ("calibrated_phase", calibrated),
                ("phase_change", changes),
            ]:
                arrays[name] = np.stack([np.sin(matrix), np.cos(matrix)])
            for name, matrix in arrays.items():
                outputs[name].append(
                    np.stack(
                        [
                            bin_values(times, component, bins, config["bin_hz"])
                            for component in matrix
                        ]
                    )
                )
            outputs["phase_change_smoothed"].append(
                smooth_valid(outputs["phase_change"][-1], config["smoothing_bins"])
            )
            coverage = float(np.isfinite(outputs["phase_change"][-1][0]).mean())
            diagnostics[f"{receiver}_coverage"] = coverage
            diagnostics[f"{receiver}_time_source"] = signal.time_source
            diagnostics[f"{receiver}_packets"] = int(
                ((times >= 0) & (times < config["window_seconds"])).sum()
            )
            diagnostics[f"{receiver}_sync_uncertainty_us"] = signal.sync_uncertainty_us
            if coverage < config["minimum_coverage"]:
                raise ValueError(
                    f"{receiver} phase-change coverage below fixed minimum"
                )
        return diagnostics, {
            name: np.concatenate(parts, axis=0) for name, parts in outputs.items()
        }
    except (ValueError, OSError, KeyError) as exc:
        diagnostics["read_error"] = str(exc)
        return diagnostics, None


def prepare(config: dict, folder: Path, output: Path) -> None:
    """Build audited, fixed-window arrays and a frozen scenario-group split."""
    session = (folder / config["session_path"]).resolve()
    if output.resolve().is_relative_to(session):
        raise ValueError("Derived output must be outside raw data")
    output.mkdir(parents=True, exist_ok=True)
    table = inventory(session)
    table.to_csv(output / "inventory.csv", index=False)
    eligible = table.loc[table.exclusion_reason.eq("")].copy()
    if eligible.empty:
        raise ValueError("No accepted usable attempts")
    table = assign_splits(eligible, config["split_seed"])
    # Freeze membership before reading signals; quality exclusions do not redraw it.
    table.to_csv(output / "split_before_quality.csv", index=False)
    source_paths = [
        session / name for name in ("session.json", "protocol.json", "events.jsonl")
    ]
    if (session / "session_review.json").exists():
        source_paths.append(session / "session_review.json")
    for row in table.to_dict("records"):
        attempt = session / row["attempt_relpath"]
        source_paths.append(attempt / "attempt.json")
        for receiver in config["receivers"]:
            source_paths.extend((attempt / "receivers" / receiver).glob("*.csv"))
    print(f"Hashing {len(source_paths)} source files", flush=True)
    source_hashes = {
        str(path.relative_to(session)): sha256(path)
        for path in sorted(set(source_paths))
    }
    jobs = [(str(session), row, config) for row in table.to_dict("records")]
    diagnostics, results, retained = [], {name: [] for name in REPRESENTATIONS}, []
    with ProcessPoolExecutor(
        max_workers=config["workers"], mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        for index, (diagnostic, arrays) in enumerate(pool.map(_prepare_one, jobs)):
            diagnostics.append(diagnostic)
            if arrays is not None:
                retained.append(index)
                for name in results:
                    results[name].append(arrays[name])
            if (index + 1) % 10 == 0:
                print(f"Prepared {index + 1}/{len(jobs)} attempts", flush=True)
    pd.DataFrame(diagnostics).to_csv(output / "quality.csv", index=False)
    table = table.iloc[retained].reset_index(drop=True)
    if table.empty or any(
        table.loc[table.split.eq(split), "target"].nunique() != 2
        for split in ["train", "validation", "test"]
    ):
        raise ValueError("Insufficient class coverage after exclusions")
    table.to_csv(output / "trials.csv", index=False)
    np.savez_compressed(
        output / "dataset.npz",
        **{name: np.stack(arrays) for name, arrays in results.items()},
        subcarriers=np.r_[np.arange(-122, -1), np.arange(2, 123)],
    )
    code_paths = [
        folder / "data_pipeline.py",
        *sorted((folder / "vendor").glob("*.py")),
    ]
    manifest = {
        "config": config,
        "raw_session": str(session),
        "source_sha256": source_hashes,
        "preprocessing_sha256": {
            str(path.relative_to(folder)): sha256(path) for path in code_paths
        },
        "dataset_sha256": sha256(output / "dataset.npz"),
        "trials_sha256": sha256(output / "trials.csv"),
        "split_before_quality_sha256": sha256(output / "split_before_quality.csv"),
        "attempts_retained": len(table),
        "attempts_excluded_after_scope": len(jobs) - len(table),
        "evaluation_scope": "Within one session and participant; held-out activity/direction scenarios, with all repetitions together.",
    }
    write_json(output / "manifest.json", manifest)
    print(table.groupby(["split", "label"]).size().to_string(), flush=True)


def normalize_inputs(
    values: np.ndarray, train_indices: np.ndarray
) -> tuple[np.ndarray, dict]:
    """Fit channel/tone moments on training attempts only and append masks.

    Arrays are N x C x time x tone. Zero imputation occurs after scaling;
    every original feature channel gets its own unscaled finite-value mask.
    """
    train = values[train_indices].astype(np.float64)
    finite = np.isfinite(train)
    count = finite.sum(axis=(0, 2), keepdims=True)
    total = np.where(finite, train, 0).sum(axis=(0, 2), keepdims=True)
    mean = np.divide(total, count, out=np.zeros_like(total), where=count > 0)
    variance = np.divide(
        np.where(finite, (train - mean) ** 2, 0).sum(axis=(0, 2), keepdims=True),
        count,
        out=np.ones_like(total),
        where=count > 0,
    )
    scale = np.maximum(np.sqrt(variance), 0.05)
    normalized = np.where(np.isfinite(values), (values - mean) / scale, 0).astype(
        np.float32
    )
    normalized = np.concatenate(
        [normalized, np.isfinite(values).astype(np.float32)], axis=1
    )
    return normalized, {
        "mean": mean.astype(np.float32),
        "scale": scale.astype(np.float32),
        "training_count": count,
    }
