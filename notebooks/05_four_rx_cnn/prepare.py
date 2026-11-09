"""Read-only four-receiver inventory, capture-time diagnostics and shifted inputs."""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
import time

import numpy as np
import pandas as pd

from support import (
    FOLDER,
    LABELS,
    bin_values,
    code_hashes,
    load_phase_signal,
    phase_change_matrix,
    read_json,
    sha256,
    smooth_valid,
    write_json,
)


def inventory(session: Path) -> pd.DataFrame:
    """Resolve accepted attempts and review overlays on the host cue timeline."""
    manifest = read_json(session / "session.json")
    if manifest.get("status") != "complete":
        raise ValueError("Require a completed immutable session")
    review_file = session / "session_review.json"
    review = read_json(review_file) if review_file.exists() else {}
    if review and (
        review.get("session_id") != manifest["session_id"]
        or review.get("protocol_hash") != manifest["protocol_hash"]
    ):
        raise ValueError("Review identity/hash mismatch")
    protocol = read_json(session / "protocol.json")
    attrs = {
        s["id"]: s.get("attributes", {})
        for b in protocol["blocks"]
        for s in b["scenarios"]
    }
    events = pd.read_json(session / "events.jsonl", lines=True).to_dict("records")
    rows = []
    for path in sorted(session.glob("trials/*/attempt_*/attempt.json")):
        a = read_json(path)
        relative = path.parent.relative_to(session).as_posix()
        overlay = review.get("attempts", {}).get(relative, {})
        label = (
            overlay.get("activity_label")
            or a.get("reference_truth_label")
            or a["activity_label"]
        )
        number = int(path.parent.name.split("_")[-1])
        phases = sorted(
            [
                e
                for e in events
                if e["kind"] == "phase_changed"
                and e.get("trial_ordinal") == a["trial_ordinal"]
                and e.get("attempt") == number
            ],
            key=lambda e: e["monotonic_ns"],
        )
        reason = ""
        if a["status"] != "accepted":
            reason = "not accepted"
        elif overlay.get("inclusion") == "exclude" or overlay.get("quality") == "bad":
            reason = "review excludes attempt"
        elif label not in LABELS:
            reason = "unknown label"
        elif [e["state"] for e in phases] != ["countdown", "action", "recovery"]:
            reason = "incomplete or duplicate phase events"
        start = a["started_monotonic_ns"]
        end = a.get("ended_monotonic_ns", start)
        times = [(e["monotonic_ns"] - start) / 1e9 for e in phases]
        duration = (end - start) / 1e9
        if not reason and not (0 <= times[0] < times[1] < times[2] < duration):
            reason = "invalid phase ordering"
        rows.append(
            dict(
                attempt_id=f"{a['trial_ordinal']:03d}/{number:02d}",
                attempt_relpath=relative,
                trial_ordinal=a["trial_ordinal"],
                repetition=a["repetition"],
                session_id=manifest["session_id"],
                participant_id=review.get("metadata", {}).get("participant_id")
                or manifest.get("participant_id"),
                scenario_id=a["scenario_id"],
                label=label,
                target=int(label.endswith("_to_fall")),
                start_direction=attrs.get(a["scenario_id"], {}).get("start_direction"),
                end_direction=attrs.get(a["scenario_id"], {}).get("end_direction"),
                status=a["status"],
                action_start_s=times[1] if len(times) == 3 else np.nan,
                action_duration_s=times[2] - times[1] if len(times) == 3 else np.nan,
                ended_s=duration,
                exclusion_reason=reason,
            )
        )
    return pd.DataFrame(rows)


def assign_splits(table: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Stratify by activity; freeze complete scenario groups before quality reads."""
    result = table.copy()
    result["split"] = ""
    rng = np.random.default_rng(seed)
    if result.groupby("scenario_id").label.nunique().ne(1).any():
        raise ValueError("Reviewed labels disagree within a scenario")
    for label in LABELS:
        groups = np.array(
            sorted(result.loc[result.label.eq(label), "scenario_id"].unique())
        )
        if len(groups) < 3:
            raise ValueError(f"Need three scenarios for {label}")
        rng.shuffle(groups)
        n = max(1, round(len(groups) * 0.2))
        for split, selected in [
            ("test", groups[:n]),
            ("validation", groups[n : 2 * n]),
            ("train", groups[2 * n :]),
        ]:
            result.loc[result.scenario_id.isin(selected), "split"] = split
    if (
        result.split.eq("").any()
        or result.groupby("trial_ordinal").split.nunique().ne(1).any()
    ):
        raise ValueError("Incomplete or leaking split")
    return result


def shifted_bin(
    times: np.ndarray, values: np.ndarray, cue: float, offset: float, config: dict
) -> np.ndarray:
    """Bin [cue + offset, cue + offset + duration) without interpolation."""
    return bin_values(
        times - cue - offset,
        values,
        round(config["window_seconds"] * config["bin_hz"]),
        config["bin_hz"],
    )


def prepare_one(job: tuple) -> tuple[list[dict], dict | None]:
    """Decode each receiver once and create all timing variants on a common axis."""
    session, row, config = job
    session = Path(session)
    results = {
        name: [[] for _ in config["offsets_seconds"]]
        for name in config["representations"]
    }
    quality = []
    try:
        if row["action_start_s"] + min(config["offsets_seconds"]) < 0 or (
            row["action_start_s"]
            + max(config["offsets_seconds"])
            + config["window_seconds"]
            > row["ended_s"]
        ):
            raise ValueError("Recording does not contain every shifted window")
        transmitter = read_json(session / "session.json")["environment"][
            "radio_inventory"
        ]["transmitter"]["mac"]
        for receiver in config["receivers"]:
            directory = session / row["attempt_relpath"] / "receivers" / receiver
            signal = load_phase_signal(session, row["attempt_id"], receiver)
            if not np.array_equal(signal.subcarriers, np.arange(-122, 123)):
                raise ValueError("Unexpected HE20 tone layout")
            # Audit/mask driver errors in the same stable capture order as the loader.
            meta = pd.read_csv(
                directory / "csi.csv",
                usecols=[
                    "type",
                    "mac",
                    "sig_mode",
                    "mcs",
                    "bandwidth",
                    "rx_state",
                    "rssi",
                    "noise_floor",
                ],
            )
            timing = pd.read_json(directory / "gateway_timing.jsonl", lines=True)
            order = timing.capture_host_monotonic_ns.sort_values(kind="stable").index
            meta, timing = meta.loc[order], timing.loc[order]
            selected = (
                meta.type.eq("CSI_DATA")
                & meta.mac.str.lower().eq(transmitter.lower())
                & meta.sig_mode.eq(4)
                & meta.mcs.eq(0)
                & meta.bandwidth.eq(0)
            )
            meta, timing = meta.loc[selected], timing.loc[selected]
            if len(meta) != len(signal.time_seconds) or signal.skipped_layout_rows:
                raise ValueError("Driver metadata does not match decoded packets")
            keep = ~np.isin(signal.subcarriers, [-1, 0, 1])
            common = (
                np.isfinite(signal.raw_phase[:, keep])
                & np.isfinite(signal.calibrated_phase[:, keep])
                & meta.rx_state.eq(0).to_numpy()[:, None]
            )
            amplitude = np.where(
                common, np.log1p(np.abs(signal.complex_csi[:, keep])), np.nan
            )
            raw = np.where(common, signal.raw_phase[:, keep], np.nan)
            calibrated = np.where(common, signal.calibrated_phase[:, keep], np.nan)
            changes = phase_change_matrix(
                calibrated, signal.time_seconds, config["lag_seconds"]
            )
            source = {"amplitude": amplitude[None]}
            for name, matrix in [
                ("raw_phase", raw),
                ("calibrated_phase", calibrated),
                ("phase_change", changes),
            ]:
                source[name] = np.stack([np.sin(matrix), np.cos(matrix)])
            times = signal.time_seconds
            latency = (
                timing.host_receive_monotonic_ns.to_numpy()
                - timing.capture_host_monotonic_ns.to_numpy()
            ) / 1e6
            for oi, offset in enumerate(config["offsets_seconds"]):
                binned = {
                    name: np.stack(
                        [
                            shifted_bin(
                                times, component, row["action_start_s"], offset, config
                            )
                            for component in matrix
                        ]
                    )
                    for name, matrix in source.items()
                }
                binned["phase_change_smoothed"] = smooth_valid(
                    binned["phase_change"], config["smoothing_bins"]
                )
                within = (times >= row["action_start_s"] + offset) & (
                    times < row["action_start_s"] + offset + config["window_seconds"]
                )
                gaps = np.diff(times[within])
                q = dict(
                    attempt_id=row["attempt_id"],
                    receiver=receiver,
                    offset_seconds=offset,
                    packets=int(within.sum()),
                    driver_bad_packets=int(
                        (~meta.rx_state.eq(0).to_numpy() & within).sum()
                    ),
                    records_per_second=float(within.sum() / config["window_seconds"]),
                    rssi_median=float(np.median(meta.rssi.to_numpy()[within]))
                    if within.any()
                    else np.nan,
                    max_gap_ms=float(gaps.max() * 1000) if len(gaps) else np.nan,
                    gaps_over_50ms=int((gaps > 0.05).sum()),
                    latency_median_ms=float(np.median(latency[within]))
                    if within.any()
                    else np.nan,
                    latency_p99_ms=float(np.quantile(latency[within], 0.99))
                    if within.any()
                    else np.nan,
                    sync_uncertainty_us=signal.sync_uncertainty_us,
                    time_source="gateway sidecar: mapped transmitter enqueue time",
                    read_error="",
                )
                for name, matrix in binned.items():
                    q[f"{name}_coverage"] = float(np.isfinite(matrix).mean())
                    results[name][oi].append(matrix)
                quality.append(q)
        if any(
            q["phase_change_coverage"] < config["minimum_coverage"] for q in quality
        ):
            raise ValueError(
                "At least one receiver/offset below fixed coverage threshold"
            )
        arrays = {
            name: np.stack([np.concatenate(parts, axis=0) for parts in offsets])
            for name, offsets in results.items()
        }
        return quality, arrays
    except (ValueError, OSError, KeyError) as exc:
        quality.append(
            dict(attempt_id=row["attempt_id"], receiver="all", read_error=str(exc))
        )
        return quality, None


def prepare(config: dict, output: Path) -> None:
    """Write derived memory-mapped arrays, frozen splits and hashed raw provenance."""
    session = (FOLDER / config["session_path"]).resolve()
    if output.is_relative_to(session) or session.is_relative_to(output):
        raise ValueError("Output overlaps raw session")
    if (
        len(config["offsets_seconds"]) != len(set(config["offsets_seconds"]))
        or 0 not in config["offsets_seconds"]
    ):
        raise ValueError("Offsets must be unique and include zero")
    output.mkdir(parents=True, exist_ok=True)
    table = inventory(session)
    table.to_csv(output / "inventory.csv", index=False)
    table = assign_splits(
        table.loc[table.exclusion_reason.eq("")], config["split_seed"]
    ).reset_index(drop=True)
    table.to_csv(output / "split_before_quality.csv", index=False)
    source_paths = [
        session / n for n in ["session.json", "events.jsonl", "protocol.json"]
    ]
    if (session / "session_review.json").exists():
        source_paths.append(session / "session_review.json")
    for row in table.to_dict("records"):
        attempt = session / row["attempt_relpath"]
        source_paths.append(attempt / "attempt.json")
        for receiver in config["receivers"]:
            source_paths.extend(
                p
                for p in (attempt / "receivers" / receiver).iterdir()
                if p.suffix in {".csv", ".jsonl"}
            )
    print(
        f"Hashing {len(source_paths)} raw inputs, then preparing {len(table)} attempts",
        flush=True,
    )
    source_hashes = {
        str(p.relative_to(session)): sha256(p) for p in sorted(source_paths)
    }
    maps, retained, diagnostics = {}, [], []
    jobs = [(str(session), row, config) for row in table.to_dict("records")]
    started = time.monotonic()
    with ProcessPoolExecutor(
        max_workers=config["workers"], mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        for index, (quality, arrays) in enumerate(pool.map(prepare_one, jobs)):
            diagnostics.extend(quality)
            if arrays is not None:
                if not maps:
                    maps = {
                        name: np.lib.format.open_memmap(
                            output / f"{name}.npy",
                            mode="w+",
                            dtype="float32",
                            shape=(len(table), *a.shape),
                        )
                        for name, a in arrays.items()
                    }
                for name, a in arrays.items():
                    maps[name][len(retained)] = a
                retained.append(index)
            if (index + 1) % 10 == 0:
                print(
                    f"Prepared {index + 1}/{len(table)} ({time.monotonic() - started:.0f}s)",
                    flush=True,
                )
    for mapping in maps.values():
        mapping.flush()
    pd.DataFrame(diagnostics).to_csv(output / "quality.csv", index=False)
    table = table.iloc[retained].reset_index(drop=True)
    if table.empty or any(
        table.loc[table.split.eq(s)].target.nunique() != 2
        for s in ["train", "validation", "test"]
    ):
        raise ValueError("Insufficient class coverage after quality exclusions")
    table.to_csv(output / "trials.csv", index=False)
    write_json(
        output / "manifest.json",
        dict(
            config=config,
            raw_session=str(session),
            source_sha256=source_hashes,
            code_sha256=code_hashes(),
            arrays_sha256={n: sha256(output / f"{n}.npy") for n in maps},
            trials_sha256=sha256(output / "trials.csv"),
            split_sha256=sha256(output / "split_before_quality.csv"),
            attempts_retained=len(table),
            excluded_after_scope=len(jobs) - len(table),
            array_layout="attempt, offset, receiver/component, time, physical HE20 tone; read only first attempts_retained rows",
            tones=list(range(-122, -1)) + list(range(2, 123)),
            scope="Exploratory within one participant/session; scenario-held-out binary attempt classification",
        ),
    )
    print(table.groupby(["split", "label"]).size().to_string(), flush=True)
