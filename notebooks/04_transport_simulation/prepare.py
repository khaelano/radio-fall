"""Read-only source loading, frozen cohort, replay and model-ready arrays."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path

import numpy as np
import pandas as pd

from support import FOLDER, case_path, code_hashes, read_json, sha256, write_json
from data_pipeline import inventory
from vendor.phase_signals import load_phase_signal
from replay import Stream, make_features, simulate, stable_seed


def load_recording(session: Path, row: dict, receivers: list[str]) -> tuple:
    """Load canonical per-packet phases and align original sequence identities."""
    manifest = read_json(session / "session.json")
    transmitter = manifest["environment"]["radio_inventory"]["transmitter"][
        "mac"
    ].lower()
    streams, phases, timing_sources = [], [], []
    for receiver in receivers:
        directory = session / row["attempt_relpath"] / "receivers" / receiver
        signal = load_phase_signal(session, row["attempt_id"], receiver)
        if signal.skipped_layout_rows or not np.array_equal(
            signal.subcarriers, np.arange(-122, 123)
        ):
            raise ValueError(
                "Unexpected/skipped LTF layout; sequence alignment is ambiguous"
            )
        if not signal.time_source.startswith("receiver callback"):
            raise ValueError(
                "Replay requires the recorded USB affine capture-clock fit"
            )
        csi = pd.read_csv(
            directory / "csi.csv",
            usecols=["type", "id", "mac", "sig_mode", "mcs", "bandwidth", "len"],
        )
        selected = (
            csi.type.eq("CSI_DATA")
            & csi.mac.str.lower().eq(transmitter)
            & csi.sig_mode.eq(4)
            & csi.mcs.eq(0)
            & csi.bandwidth.eq(0)
        )
        csi = csi.loc[selected]
        if len(csi) != len(signal.time_seconds):
            raise ValueError("Canonical phases and sensing sequences do not align")
        sequence = csi.id.to_numpy(dtype=np.int64)
        if np.any(np.diff(sequence) <= 0):
            raise ValueError(
                "Sequence restart/wrap/reorder requires explicit segmentation"
            )
        streams.append(
            Stream(sequence, signal.time_seconds, csi.len.to_numpy(dtype=int))
        )
        keep = ~np.isin(signal.subcarriers, [-1, 0, 1])
        common = np.isfinite(signal.raw_phase[:, keep]) & np.isfinite(
            signal.calibrated_phase[:, keep]
        )
        phases.append(
            np.where(common, signal.calibrated_phase[:, keep], np.nan).astype(
                np.float32
            )
        )
        timing_sources.append(
            dict(
                receiver=receiver,
                time_source=signal.time_source,
                uncertainty_us=signal.sync_uncertainty_us,
            )
        )
    return streams, phases, timing_sources


def summarize(
    streams: list[Stream],
    result: dict,
    counts: np.ndarray,
    row: dict,
    condition: dict,
    config: dict,
    seed: int,
) -> list[dict]:
    """Calculate packet-level coverage and distinguish late delivery from loss."""
    records = []
    start, duration = row["action_start_s"], config["window_seconds"]
    end = start + duration
    for rx, stream in enumerate(streams):
        inside = (stream.seconds >= start) & (stream.seconds < end)
        deadlines = (
            start
            + (np.floor((stream.seconds - start) * config["bin_hz"] + 1e-7) + 1)
            / config["bin_hz"]
            + config["prediction_grace_seconds"]
        )
        arrival = result["arrivals"][rx]
        timely = inside & (arrival <= deadlines)
        delivered = inside & np.isfinite(arrival)
        times = stream.seconds[timely]
        gaps = np.diff(np.r_[start, times, end])
        delay = arrival[delivered] - stream.seconds[delivered]
        record = dict(
            attempt_id=row["attempt_id"],
            label=row["label"],
            split=row["split"],
            condition=condition["name"],
            realization=seed,
            receiver=config["receivers"][rx],
            source_records=int(inside.sum()),
            source_hz=float(inside.sum() / duration),
            timely_records=int(timely.sum()),
            timely_hz=float(timely.sum() / duration),
            delivered_late=int((delivered & ~timely).sum()),
            nonempty_bin_fraction=float((counts[rx] > 0).mean()),
            longest_gap_seconds=float(gaps.max()),
            delivery_p95_seconds=float(np.quantile(delay, 0.95)) if len(delay) else 0.0,
            peak_queue=result["counters"][rx]["peak_queue"],
            pending_at_end=result["pending"][rx],
        )
        for reason in (
            "rate_removed",
            "scheduled",
            "radio_independent",
            "radio_burst",
            "overflow",
            "expired",
            "retry_limit",
            "pending",
        ):
            record[reason] = int((inside & (result["reasons"][rx] == reason)).sum())
        records.append(record)
    return records


def _one(job: tuple) -> tuple[list, list, list, list]:
    session, output, row, index, config = job
    streams, phases, timing_sources = load_recording(
        Path(session), row, config["receivers"]
    )
    diagnostics, joint, traces = [], [], []
    for condition in config["conditions"]:
        for realization in config["realization_seeds"]:
            result = simulate(
                streams,
                condition,
                config,
                stable_seed(realization, row["attempt_id"]),
                row["action_start_s"]
                + config["window_seconds"]
                + config["prediction_grace_seconds"],
            )
            values, counts, age = make_features(
                streams, phases, result["arrivals"], row["action_start_s"], config
            )
            directory = case_path(Path(output), condition["name"], realization)
            for name, array in (("values", values), ("counts", counts), ("age", age)):
                target = np.load(directory / f"{name}.npy", mmap_mode="r+")
                target[index] = array
                target.flush()
            diagnostics.extend(
                summarize(streams, result, counts, row, condition, config, realization)
            )
            joint.append(
                dict(
                    attempt_id=row["attempt_id"],
                    condition=condition["name"],
                    realization=realization,
                    split=row["split"],
                    label=row["label"],
                    both_present=float(np.all(counts > 0, axis=0).mean()),
                    neither_present=float(np.all(counts == 0, axis=0).mean()),
                    virtual_completed=sum(
                        c["completed"] for c in result["counters"][2:]
                    ),
                    virtual_expired=sum(c["expired"] for c in result["counters"][2:]),
                    virtual_pending=sum(result["pending"][2:]),
                )
            )
            if index == 0 and realization == config["test_realization"]:
                for rx, stream in enumerate(streams):
                    inside = (stream.seconds >= row["action_start_s"] - 0.2) & (
                        stream.seconds
                        < row["action_start_s"] + config["window_seconds"]
                    )
                    for i in np.flatnonzero(inside):
                        arrival = result["arrivals"][rx][i]
                        traces.append(
                            dict(
                                condition=condition["name"],
                                receiver=config["receivers"][rx],
                                sequence=int(stream.sequence[i]),
                                capture_s=float(
                                    stream.seconds[i] - row["action_start_s"]
                                ),
                                arrival_s=float(arrival - row["action_start_s"])
                                if np.isfinite(arrival)
                                else np.nan,
                                reason=result["reasons"][rx][i],
                            )
                        )
    return (
        diagnostics,
        joint,
        [dict(attempt_id=row["attempt_id"], **x) for x in timing_sources],
        traces,
    )


def prepare(config: dict, output: Path) -> None:
    """Prepare all conditions on the unchanged pilot cohort and partitions."""
    session = (FOLDER / config["session_path"]).resolve()
    if output.is_relative_to(session) or session.is_relative_to(output):
        raise ValueError("Output must be separate from raw recordings")
    if (output / "manifest.json").exists():
        raise ValueError(
            "Prepared output already exists; choose a new --output directory"
        )
    output.mkdir(parents=True, exist_ok=True)
    frozen = (FOLDER / config["frozen_trials"]).resolve()
    table = pd.read_csv(frozen, keep_default_na=False)
    current = inventory(session).set_index("attempt_id")
    for row in table.to_dict("records"):
        original = current.loc[row["attempt_id"]]
        if original["exclusion_reason"] or any(
            original[k] != row[k]
            for k in ("target", "label", "scenario_id", "attempt_relpath")
        ):
            raise ValueError("Frozen cohort differs from current source/review")
        if row["action_start_s"] + config["window_seconds"] > row["ended_s"]:
            raise ValueError("Fixed window is not covered")
    if table.groupby("scenario_id").split.nunique().max() != 1:
        raise ValueError("A scenario crosses partitions")
    table.to_csv(output / "trials.csv", index=False)
    paths = [
        session / p
        for p in (
            "session.json",
            "protocol.json",
            "events.jsonl",
            "session_review.json",
        )
    ]
    for row in table.to_dict("records"):
        directory = session / row["attempt_relpath"]
        paths.append(directory / "attempt.json")
        for receiver in config["receivers"]:
            paths.extend((directory / "receivers" / receiver).glob("*.csv"))
    print(f"Hashing {len(paths)} immutable source files", flush=True)
    sources = {str(p.relative_to(session)): sha256(p) for p in sorted(set(paths))}
    bins = round(config["window_seconds"] * config["bin_hz"])
    for condition in config["conditions"]:
        for seed in config["realization_seeds"]:
            directory = case_path(output, condition["name"], seed)
            directory.mkdir(parents=True, exist_ok=True)
            for name, shape in (
                ("values", (len(table), 4, bins, 242)),
                ("counts", (len(table), 2, bins)),
                ("age", (len(table), 2, bins)),
            ):
                array = np.lib.format.open_memmap(
                    directory / f"{name}.npy", mode="w+", dtype="float32", shape=shape
                )
                del array
    jobs = [
        (str(session), str(output), row, i, config)
        for i, row in enumerate(table.to_dict("records"))
    ]
    diagnostics, joint, clocks, traces = [], [], [], []
    with ProcessPoolExecutor(
        max_workers=config["workers"], mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        for i, (d, j, c, t) in enumerate(pool.map(_one, jobs)):
            diagnostics.extend(d)
            joint.extend(j)
            clocks.extend(c)
            traces.extend(t)
            if (i + 1) % 10 == 0 or i == len(jobs) - 1:
                print(f"Replayed {i + 1}/{len(jobs)} attempts", flush=True)
    pd.DataFrame(diagnostics).to_csv(output / "packet_diagnostics.csv", index=False)
    pd.DataFrame(joint).to_csv(output / "joint_coverage.csv", index=False)
    pd.DataFrame(clocks).to_csv(output / "clock_diagnostics.csv", index=False)
    pd.DataFrame(traces).to_csv(output / "example_packet_trace.csv", index=False)
    arrays = {
        str(p.relative_to(output)): sha256(p)
        for p in sorted((output / "arrays").rglob("*.npy"))
    }
    write_json(
        output / "manifest.json",
        dict(
            config=config,
            source_session=str(session),
            source_sha256=sources,
            frozen_trials_sha256=sha256(frozen),
            trials_sha256=sha256(output / "trials.csv"),
            code_sha256=code_hashes(),
            arrays_sha256=arrays,
            attempts=len(table),
            scope="Two real CSI views; four-slot cases add two virtual traffic sources only. Reused within-session pilot split; prior test set already inspected. All transport/loss parameters are assumptions.",
        ),
    )
    print("Prepared and fingerprinted all replay arrays", flush=True)


def verify(config: dict, output: Path, full: bool = False) -> dict:
    """Reject stale config/code/split and optionally rehash every derived array."""
    manifest = read_json(output / "manifest.json")
    if manifest["config"] != config or manifest["code_sha256"] != code_hashes():
        raise ValueError("Config or experiment code changed; prepare into a new output")
    if manifest["trials_sha256"] != sha256(output / "trials.csv"):
        raise ValueError("Frozen trial membership changed")
    if full:
        for name, digest in manifest["arrays_sha256"].items():
            if sha256(output / name) != digest:
                raise ValueError(f"Changed prepared array: {name}")
    return manifest
