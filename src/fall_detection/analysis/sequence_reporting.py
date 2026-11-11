"""Dataset-wide summaries and deterministic figures for the sequence notebook."""

import json
import os
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.colors import Normalize, SymLogNorm

from .sequence_cache import array_directory, file_hash, fingerprint, read_segment, stamp
from .sequence_preprocessing import DURATIONS, RECEIVERS, SequenceDataset, atomic_json


def representative(workflow: SequenceDataset) -> dict:
    """Choose the longest fall segment (otherwise longest), breaking ties by ID."""
    rows = workflow.segments.to_dicts()
    falls = [r for r in rows if r["activity_label"].endswith("_to_fall")]
    return sorted(falls or rows, key=lambda r: (-r["samples"], r["segment_id"]))[0]


_RENDERER = file_hash(Path(__file__))
_STAGE_ARRAYS = {
    "align": ("time_ns", "subcarriers", "amplitude", "availability"),
    "hampel": (
        "time_ns",
        "subcarriers",
        "amplitude",
        "filtered_amplitude",
        "hampel_replaced",
    ),
    "difference": (
        "time_ns",
        "subcarriers",
        "filtered_amplitude",
        "squared_difference",
    ),
    "windows": ("time_ns", "subcarriers", "filtered_amplitude"),
}


def _array_identity(path: str, key: str) -> dict:
    source = Path(path)
    directory = array_directory(source)
    stored_key = "valid" if key == "availability" else key
    file = directory / f"{stored_key}.npy" if directory.is_dir() else source
    return dict(path=str(file.resolve()), **stamp(file))


@lru_cache(maxsize=24)
def _preview_array(path: str, key: str, max_points: int, identity: str) -> np.ndarray:
    """Copy a bounded display sample; never retain the full decoded recording."""
    with read_segment(path) as data:
        values = data["valid" if key == "availability" else key]
        if key in {"subcarriers", "receivers"}:
            preview = np.array(values, copy=True)
        elif key == "availability":
            available = values.any(axis=2).astype(np.float32)
            edges = np.linspace(
                0, len(values), min(max_points, len(values)) + 1, dtype=int
            )
            preview = (
                np.add.reduceat(available, edges[:-1], axis=0) / np.diff(edges)[:, None]
            )
        else:
            indices = np.linspace(
                0, len(values) - 1, min(max_points, len(values)), dtype=int
            )
            preview = np.array(values[indices], copy=True)
    preview.setflags(write=False)
    return preview


def _preview(path: str, key: str, max_points: int) -> np.ndarray:
    return _preview_array(
        path, key, max_points, fingerprint(_array_identity(path, key))
    )


def comparison_scales(
    workflows: list[SequenceDataset], *, max_points: int = 1200
) -> tuple[float, float]:
    """Cache common robust scales from bounded display samples, not full tensors."""
    if max_points < 2:
        raise ValueError("max_points must be at least two")
    sources = [representative(w)["path"] for w in workflows]
    key = fingerprint(
        [_RENDERER, max_points, [_array_identity(p, "amplitude") for p in sources]]
    )
    cache = workflows[0].output / "reports/figures" / f".scales-{key}.json"
    if cache.is_file():
        return tuple(json.loads(cache.read_text())["scales"])
    values = []
    for path in sources:
        sample = _preview(path, "amplitude", max_points)
        values.append(sample[np.isfinite(sample)])
    finite = np.concatenate(values)
    scales = (0.0, float(np.quantile(finite, 0.99))) if len(finite) else (0.0, 1.0)
    atomic_json({"scales": scales}, cache)
    return scales


def _frame_identity(frame: pl.DataFrame) -> dict:
    return dict(
        shape=frame.shape,
        columns=frame.columns,
        rows=fingerprint(frame.hash_rows(seed=0).to_list()),
    )


def _plot_identity(workflow, stage, scales, max_points, max_window_overlays, dpi):
    frames = {
        "load": ("selected", "recordings"),
        "align": ("alignment",),
        "hampel": ("hampel",),
        "difference": (),
        "windows": ("index",),
        "export": ("index", "signals") if getattr(workflow, "format_version", 1) == 2 else ("index", "shards"),
    }[stage]
    inputs = {name: _frame_identity(getattr(workflow, name)) for name in frames}
    if stage in _STAGE_ARRAYS:
        row = representative(workflow)
        inputs["representative"] = row
        inputs["arrays"] = [
            _array_identity(row["path"], key) for key in _STAGE_ARRAYS[stage]
        ]
    elif stage == "export":
        inputs["timings"] = workflow.timings
        if len(workflow.index):
            column = "signal" if getattr(workflow, "format_version", 1) == 2 else "shard"
            path = workflow.output / workflow.index[column][0]
            inputs["example"] = dict(path=str(path), **stamp(path))
    return fingerprint(
        dict(
            renderer=_RENDERER,
            name=workflow.name,
            stage=stage,
            scales=scales,
            max_points=max_points,
            max_window_overlays=max_window_overlays,
            dpi=dpi,
            inputs=inputs,
        )
    )


def _show_saved(path: Path) -> None:
    from IPython.display import Image, display

    display(Image(filename=str(path)))


def plot_stage(
    workflow: SequenceDataset,
    stage: str,
    scales: tuple[float, float] = (0, 150),
    *,
    max_points: int = 1200,
    max_window_overlays: int = 24,
    dpi: int = 100,
    refresh: bool = False,
) -> Path:
    """Show a cached PNG or render one bounded overview with complete summaries.

    Signal curves and heatmaps select at most max_points time samples. Availability
    shows the observed fraction in each display bin. Window overlays are bounded;
    label counts and summary distributions still cover the complete dataset.
    """
    from IPython.display import display

    if stage not in {"load", "align", "hampel", "difference", "windows", "export"}:
        raise ValueError(f"Unknown stage: {stage}")
    if max_points < 2 or max_window_overlays < 0 or dpi <= 0:
        raise ValueError("Invalid display limits")
    directory = workflow.output / "reports/figures"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stage}.png"
    receipt = path.with_suffix(".plot.json")
    key = _plot_identity(workflow, stage, scales, max_points, max_window_overlays, dpi)
    if not refresh:
        try:
            cached = json.loads(receipt.read_text())
            if cached["key"] == key and cached["png"] == stamp(path):
                _show_saved(path)
                return path
        except (OSError, ValueError, KeyError):
            pass
    plt.rcParams.update({"figure.dpi": 90, "font.size": 9})
    if stage == "load":
        fig, axes = plt.subplots(1, 3, figsize=(15, 3.5), constrained_layout=True)
        activity = (
            workflow.selected.group_by("activity_label").len().sort("activity_label")
        )
        axes[0].barh(activity["activity_label"], activity["len"])
        axes[0].set_xlabel("Selected attempts")
        duration = (
            workflow.selected["ended_monotonic_ns"]
            - workflow.selected["started_monotonic_ns"]
        ) / 1e9
        axes[1].hist(duration, bins=20)
        axes[1].set(xlabel="Recorded attempt duration (s)", ylabel="Attempts")
        receiver = (
            workflow.recordings.group_by("receiver_id")
            .agg(pl.col("packets", "driver_valid_packets").sum())
            .sort("receiver_id")
        )
        x = np.arange(4)
        axes[2].bar(x - 0.18, receiver["packets"], width=0.36, label="Sensing packets")
        axes[2].bar(
            x + 0.18, receiver["driver_valid_packets"], width=0.36, label="Driver valid"
        )
        axes[2].set_xticks(x, RECEIVERS)
        axes[2].legend()
        display(
            workflow.recordings.group_by("receiver_id")
            .agg(pl.col("packets", "driver_valid_packets").sum())
            .sort("receiver_id")
        )
        print(
            f"{workflow.name}: {len(workflow.selected)}/{len(workflow.attempts)} selected attempts; "
            f"{len(workflow.recordings)} receiver views; {duration.sum():.2f} recorded seconds"
        )
    else:
        segment = representative(workflow) if stage != "export" else None
        if segment is not None:
            data = {
                name: _preview(segment["path"], name, max_points)
                for name in _STAGE_ARRAYS[stage]
            }
            time = (data["time_ns"] - data["time_ns"][0]) / 1e9
            col = int(np.flatnonzero(data["subcarriers"] == 30)[0])
        if stage == "align":
            fig, axes = plt.subplots(3, 2, figsize=(15, 9), constrained_layout=True)
            axes[0, 0].imshow(
                data["availability"].T,
                aspect="auto",
                interpolation="nearest",
                extent=(time[0], time[-1], 4.5, 0.5),
                vmin=0,
                vmax=1,
                cmap="Greys",
            )
            axes[0, 0].set(
                yticks=range(1, 5),
                yticklabels=RECEIVERS,
                xlabel="Grid time (s)",
                title="Receiver availability (fraction per display bin)",
            )
            histogram = {}
            for row in workflow.alignment.iter_rows(named=True):
                for gap, count in zip(row["gap_rounds"], row["gap_counts"]):
                    histogram[gap] = histogram.get(gap, 0) + count
            axes[0, 1].bar(list(histogram), list(histogram.values()))
            axes[0, 1].set(
                xlabel="Consecutive source-round spacing",
                ylabel="Packet pairs (all recordings)",
                yscale="log",
            )
            for r, ax in enumerate(axes[1:].flat):
                image = ax.imshow(
                    np.ma.masked_invalid(data["amplitude"][:, r].T),
                    origin="lower",
                    aspect="auto",
                    extent=(time[0], time[-1], -122, 122),
                    norm=Normalize(*scales),
                    cmap="viridis",
                )
                ax.set(
                    title=RECEIVERS[r],
                    xlabel="Grid time (s)",
                    ylabel="Physical subcarrier",
                )
            fig.colorbar(image, ax=list(axes[1:].flat), label="Raw magnitude")
        elif stage == "hampel":
            fig, axes = plt.subplots(3, 2, figsize=(15, 8), constrained_layout=True)
            for r, ax in enumerate(axes[:2].flat):
                before, after = (
                    data["amplitude"][:, r, col],
                    data["filtered_amplitude"][:, r, col],
                )
                mask = data["hampel_replaced"][:, r, col]
                ax.plot(time, before, lw=0.7, alpha=0.7, label="Raw")
                ax.plot(time, after, lw=0.7, label="Hampel")
                ax.scatter(
                    time[mask],
                    before[mask],
                    marker="x",
                    s=18,
                    color="red",
                    label="Replaced",
                )
                ax.set(
                    title=f"{RECEIVERS[r]}, k=30", xlabel="Grid time (s)", ylim=scales
                )
            axes[0, 0].legend(ncol=3)
            stats = (
                workflow.hampel.group_by("receiver")
                .agg(pl.col("replaced", "valid").sum())
                .sort("receiver")
            )
            axes[2, 0].bar(stats["receiver"], stats["replaced"] / stats["valid"] * 100)
            axes[2, 0].set(
                ylabel="Replacements / finite values (%)", title="Complete dataset"
            )
            rates = workflow.hampel.with_columns(
                (pl.col("replaced") / pl.col("valid")).alias("rate")
            )["rate"].drop_nulls()
            axes[2, 1].hist(rates.to_numpy() * 100, bins=30)
            axes[2, 1].set(
                xlabel="Replacement rate per segment/receiver (%)", ylabel="Views"
            )
        elif stage == "difference":
            fig, axes = plt.subplots(4, 2, figsize=(15, 10), constrained_layout=True)
            for r in range(4):
                ax = axes[r, 0]
                ax.plot(
                    time,
                    data["filtered_amplitude"][:, r, col],
                    lw=0.7,
                    color="tab:blue",
                )
                ax.set(
                    ylabel="Filtered magnitude",
                    title=f"{RECEIVERS[r]}, k=30",
                    ylim=scales,
                )
                twin = ax.twinx()
                twin.plot(
                    time,
                    data["squared_difference"][:, r, col],
                    lw=0.6,
                    color="tab:orange",
                    alpha=0.8,
                )
                twin.set(ylabel="Squared difference", ylim=(0, scales[1] ** 2))
                image = axes[r, 1].imshow(
                    np.ma.masked_invalid(data["squared_difference"][:, r].T),
                    origin="lower",
                    aspect="auto",
                    extent=(time[0], time[-1], -122, 122),
                    norm=SymLogNorm(linthresh=0.01, vmin=0, vmax=scales[1] ** 2),
                    cmap="magma",
                )
                axes[r, 1].set(
                    ylabel="Physical subcarrier",
                    xlabel="Grid time (s)",
                    facecolor="lightgrey",
                )
            fig.colorbar(
                image,
                ax=list(axes[:, 1]),
                label="Squared magnitude difference (grey = missing)",
            )
        elif stage == "windows":
            fig, axes = plt.subplots(3, 3, figsize=(15, 9), constrained_layout=True)
            for i, duration in enumerate(DURATIONS):
                subset = workflow.index.filter(pl.col("duration") == duration)
                local = subset.filter(pl.col("segment_id") == segment["segment_id"])
                axes[i, 0].plot(time, data["filtered_amplitude"][:, 0, col], lw=0.7)
                overlay_indices = np.linspace(
                    0, len(local) - 1, min(len(local), max_window_overlays), dtype=int
                )
                for j, position in enumerate(overlay_indices):
                    row = local.row(int(position), named=True)
                    begin = (row["start_ns"] - data["time_ns"][0]) / 1e9
                    axes[i, 0].plot(
                        [begin, begin + duration],
                        [scales[1] * (0.8 + 0.05 * (j % 3))] * 2,
                        lw=2,
                        alpha=0.7,
                    )
                    axes[i, 0].axvline(begin, lw=0.5, alpha=0.4)
                axes[i, 0].set(
                    title=f"{duration}s; {len(overlay_indices)}/{len(local)} windows overlaid",
                    xlabel="Grid time (s)",
                    ylim=scales,
                )
                counts = [
                    subset.filter(pl.col("target") == target).height
                    for target in (0, 1)
                ]
                axes[i, 1].bar(["non_fall", "fall"], counts)
                axes[i, 1].set(ylabel="Exported windows", title="Complete dataset")
                axes[i, 2].hist(subset["coverage"], bins=np.linspace(0, 1, 31))
                axes[i, 2].set(
                    xlabel="Finite value fraction", ylabel="Windows", xlim=(0, 1)
                )
        elif stage == "export":
            fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
            v2 = getattr(workflow, "format_version", 1) == 2
            files = workflow.signals if v2 else workflow.shards
            axes[0].hist(files["bytes"].to_numpy() / 2**20, bins=25)
            axes[0].set(
                xlabel="Signal file size (MiB)" if v2 else "Compressed shard size (MiB)",
                ylabel="Files",
            )
            axes[1].barh(list(workflow.timings), list(workflow.timings.values()))
            axes[1].set(xlabel="Wall time (s)")
            example = workflow.index.row(0, named=True)
            if v2:
                amplitude = np.load(workflow.output / example["signal"], mmap_mode="r")
                amplitude = amplitude[example["start"]:example["stop"]]
                source_name = example["signal"]
            else:
                with np.load(workflow.output / example["shard"]) as reloaded:
                    amplitude = reloaded["amplitude"][example["shard_row"]]
                source_name = example["shard"]
            positions = np.linspace(
                0, amplitude.shape[0] - 1,
                min(max_points, amplitude.shape[0]),
                dtype=int,
            )
            a = amplitude[positions, 0, :]
            norm = (Normalize(0, max(1e-6, float(np.nanquantile(a, 0.99))))
                    if v2 else Normalize(*scales))
            image = axes[2].imshow(
                np.ma.masked_invalid(a.T),
                aspect="auto",
                origin="lower",
                extent=(0, example["duration"], -122, 122),
                norm=norm,
            )
            print(f"Reloaded {source_name}: signal {amplitude.shape}, target={example['target']}")
            axes[2].set(
                xlabel="Window time (s)",
                ylabel="Physical subcarrier",
                title="Reloaded example, rx-1",
            )
            fig.colorbar(image, ax=axes[2], label="Log difference" if v2 else "Raw magnitude")
            columns = ("segment_id", "samples", "bytes") if v2 else (
                "duration", "shape", "bytes"
            )
            display(files.select(*columns).head(6))
        else:
            raise ValueError(f"Unknown stage: {stage}")
        if segment is not None:
            print(
                f"Representative: {segment['attempt_key']} / {segment['segment_id']}; "
                f"display selects {len(time)}/{segment['samples']} time samples; summaries cover all data"
            )
    subtitle = (
        ""
        if stage in {"load", "export"}
        else f" — display preview ≤{max_points} time samples"
    )
    fig.suptitle(f"{workflow.name} — {stage}{subtitle}")
    with NamedTemporaryFile(dir=directory, suffix=".png", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        fig.savefig(temporary, dpi=dpi)
        plt.close(fig)  # Inline display embeds this PNG rather than redrawing artists.
        os.replace(temporary, path)
        atomic_json(dict(key=key, png=stamp(path)), receipt)
    finally:
        plt.close(fig)
        temporary.unlink(missing_ok=True)
    _show_saved(path)
    return path
