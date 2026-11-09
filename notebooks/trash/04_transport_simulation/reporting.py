"""Training-cohort EDA and measured replay/classification reports."""

from __future__ import annotations

from pathlib import Path
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from support import case_path, read_json
from prepare import verify


def markdown_table(frame: pd.DataFrame) -> str:
    """Render compact Markdown without an optional tabulation dependency."""
    rows = [
        "| " + " | ".join(map(str, frame.columns)) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        rows.append(
            "| "
            + " | ".join(
                f"{v:.3f}" if isinstance(v, (float, np.floating)) else str(v)
                for v in row
            )
            + " |"
        )
    return "\n".join(rows)


def eda(config: dict, output: Path) -> None:
    """Plot packet coverage and model inputs using training attempts only."""
    verify(config, output)
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    table = pd.read_csv(output / "trials.csv")
    data = pd.read_csv(output / "packet_diagnostics.csv")
    train = data.loc[
        data.split.eq("train") & data.realization.eq(config["training_realizations"][0])
    ]
    order = [c["name"] for c in config["conditions"]]
    summary = (
        train.groupby(["condition", "receiver"])
        .agg(
            attempts=("attempt_id", "nunique"),
            median_timely_hz=("timely_hz", "median"),
            p10_timely_hz=("timely_hz", lambda s: s.quantile(0.1)),
            p90_longest_gap_s=("longest_gap_seconds", lambda s: s.quantile(0.9)),
            median_p95_delay_s=("delivery_p95_seconds", "median"),
            median_peak_queue=("peak_queue", "median"),
        )
        .reset_index()
    )
    summary.to_csv(output / "eda_training_summary.csv", index=False)
    table.groupby(["split", "label"]).size().rename("attempts").reset_index().to_csv(
        output / "split_counts.csv", index=False
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for receiver, offset, color in (
        ("rx-1", -0.17, "#2563eb"),
        ("rx-2", 0.17, "#d97706"),
    ):
        subset = train.loc[train.receiver.eq(receiver)]
        for ax, column, ylabel in (
            (axes[0], "timely_hz", "Timely records / second"),
            (axes[1], "longest_gap_seconds", "Longest gap incl. window edges (s)"),
        ):
            series = [
                subset.loc[subset.condition.eq(name), column].to_numpy()
                for name in order
            ]
            box = ax.boxplot(
                series,
                positions=np.arange(len(order)) + offset,
                widths=0.28,
                patch_artist=True,
                manage_ticks=False,
                showfliers=False,
            )
            for patch in box["boxes"]:
                patch.set_facecolor(color)
                patch.set_alpha(0.6)
            ax.set_ylabel(ylabel)
            ax.set_xticks(np.arange(len(order)), order, rotation=45, ha="right")
            ax.grid(axis="y", alpha=0.2)
        axes[0].plot([], [], color=color, label=receiver)
    axes[0].legend()
    fig.suptitle(
        "Replay EDA: training attempts, one fixed realization; assumed transport"
    )
    fig.tight_layout()
    fig.savefig(figures / "packet_coverage.png", dpi=150)
    plt.close(fig)
    joint = pd.read_csv(output / "joint_coverage.csv")
    joint = joint.loc[
        joint.split.eq("train")
        & joint.realization.eq(config["training_realizations"][0])
    ]
    coverage = (
        joint.groupby("condition")[["both_present", "neither_present"]]
        .mean()
        .reindex(order)
    )
    coverage.to_csv(output / "eda_joint_coverage.csv")
    fig, ax = plt.subplots(figsize=(9, 4))
    coverage.plot.bar(ax=ax, color=["#0f766e", "#be123c"])
    ax.set_ylabel("Fraction of 20 ms input bins")
    ax.set_title("Availability of the TWO recorded views; virtual slots supply no CSI")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(figures / "joint_coverage.png", dpi=150)
    plt.close(fig)
    index = int(np.flatnonzero(table.split.eq("train"))[0])
    fig, axes = plt.subplots(len(order), 2, figsize=(12, 2 * len(order)), sharex=True)
    for row, name in enumerate(order):
        directory = case_path(output, name, config["training_realizations"][0])
        values = np.load(directory / "values.npy", mmap_mode="r")[index]
        counts = np.load(directory / "counts.npy", mmap_mode="r")[index]
        for rx in range(2):
            phase = np.arctan2(values[2 * rx], values[2 * rx + 1])
            axes[row, rx].imshow(
                phase.T,
                origin="lower",
                aspect="auto",
                vmin=-np.pi,
                vmax=np.pi,
                cmap="twilight",
                extent=[0, config["window_seconds"], -122, 122],
            )
            axes[row, rx].set_title(
                f"{name}, rx-{rx + 1}; {np.mean(counts[rx] > 0):.0%} nonempty bins",
                fontsize=9,
            )
            axes[row, rx].set_ylabel("Tone order")
    for ax in axes[-1]:
        ax.set_xlabel("Seconds after action cue")
    fig.suptitle(
        f"Calibrated phase inputs, training attempt {table.iloc[index].attempt_id}; gaps stay missing"
    )
    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(figures / "phase_inputs.png", dpi=120)
    plt.close(fig)


def report(config: dict, output: Path, destination: Path) -> None:
    """Export small, shareable results with limitations next to measured numbers."""
    verify(config, output)
    eda(config, output)
    metrics = pd.read_csv(output / "test_metrics.csv")
    histories = pd.read_csv(output / "training_history.csv")
    figures = output / "figures"
    order = [c["name"] for c in config["conditions"]]
    cnn = metrics.loc[metrics.model.eq("cnn")]
    pivot = cnn.pivot(
        index="condition", columns="regime", values="balanced_accuracy"
    ).reindex(order)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    pivot.plot.bar(ax=ax, color=["#475569", "#2563eb"])
    ax.set_ylim(0, 1.05)
    ax.axhline(0.5, color="black", ls=":", lw=1)
    ax.set_ylabel("Balanced accuracy, threshold 0.5")
    ax.set_title("Exploratory reused scenario test split; unseen replay seed 404")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(figures / "test_comparison.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, regime in zip(axes, ("clean_trained", "missingness_trained")):
        for seed in config["training_seeds"]:
            group = histories.loc[histories.regime.eq(regime) & histories.seed.eq(seed)]
            ax.plot(group.epoch, group.train_loss, label=f"train {seed}", alpha=0.7)
            ax.plot(
                group.epoch,
                group.validation_loss,
                ls="--",
                label=f"val {seed}",
                alpha=0.7,
            )
        ax.set_title(regime)
        ax.set_xlabel("Epoch")
        ax.legend(fontsize=7, ncol=2)
    axes[0].set_ylabel("Weighted binary cross entropy")
    fig.tight_layout()
    fig.savefig(figures / "training_curves.png", dpi=150)
    plt.close(fig)
    trace = pd.read_csv(output / "example_packet_trace.csv")
    timeline_cases = ["original_100", "loss4_80", "ble4_1400k", "ble4_1000k"]
    edges = np.arange(0, config["window_seconds"] + 0.125, 0.25)
    fig, axes = plt.subplots(len(timeline_cases), 2, figsize=(12, 10), sharex=True)
    for row, name in enumerate(timeline_cases):
        for receiver, color in (("rx-1", "#2563eb"), ("rx-2", "#d97706")):
            group = trace.loc[
                trace.condition.eq(name)
                & trace.receiver.eq(receiver)
                & trace.capture_s.ge(0)
            ]
            deadline = (
                np.floor(group.capture_s * config["bin_hz"] + 1e-7) + 1
            ) / config["bin_hz"] + config["prediction_grace_seconds"]
            timely = group.arrival_s.le(deadline)
            rate, _ = np.histogram(group.loc[timely, "capture_s"], bins=edges)
            axes[row, 0].step(
                edges[:-1], rate / 0.25, where="post", color=color, label=receiver
            )
            delivered = group.loc[group.arrival_s.notna()]
            axes[row, 1].scatter(
                delivered.capture_s,
                delivered.arrival_s - delivered.capture_s,
                s=5,
                alpha=0.6,
                color=color,
                label=receiver,
            )
        axes[row, 0].set_ylabel(f"{name}\nTimely records/s")
        axes[row, 0].set_ylim(0, 115)
        axes[row, 1].axhspan(
            config["prediction_grace_seconds"],
            config["prediction_grace_seconds"] + 1 / config["bin_hz"],
            color="gray",
            alpha=0.2,
        )
        axes[row, 1].set_ylabel("Delivery delay (s)")
        axes[row, 1].set_ylim(0, config["maximum_age_seconds"] + 0.01)
    axes[0, 0].legend()
    axes[0, 1].legend()
    for ax in axes[-1]:
        ax.set_xlabel("Seconds after action cue")
    fig.suptitle(
        "One recorded attempt: timely rate in 250 ms blocks and delivery delays\nGray band is the range of per-packet prediction deadlines"
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(figures / "delivery_timeline.png", dpi=150)
    plt.close(fig)
    trials = pd.read_csv(output / "trials.csv")
    manifest = read_json(output / "manifest.json")
    selected = read_json(output / "selection.json")
    summary = pd.read_csv(output / "eda_training_summary.csv")
    missing = metrics.loc[
        metrics.model.eq("missingness_only"),
        ["regime", "condition", "balanced_accuracy", "roc_auc"],
    ]
    text = f"""# CSI transport replay pilot

Executed on {len(trials)} recorded attempts from session `20261026T174653764289Z`,
using two real receivers and the existing frozen pilot scenario split
({trials.split.value_counts().to_dict()}). This is a synthetic transport stress
test and cue-aligned attempt classifier. It does not measure BLE hardware or
establish performance on new sessions, participants, or continuous activity.
The reused test partition was already inspected in the previous pilot; these
scores are exploratory and must not become a new tuning target.

## Measured classifier comparison

Three training seeds form each ensemble. Every row uses the same test attempts
and an unseen replay realization ({config["test_realization"]}). Threshold is
fixed at 0.5. Conditions were prespecified, with no post-loss cohort exclusion.

{markdown_table(cnn[["regime", "condition", "balanced_accuracy", "fall_recall", "specificity", "roc_auc", "tp", "fn", "fp", "tn"]])}

Scenario-cluster bootstrap intervals are in `test_intervals.json`; they condition
on this one reused split/session. Seed results and attempt-level probabilities
are included. They do not represent uncertainty across people or hardware.

![Classifier comparison](figures/test_comparison.png)

## Training-cohort packet EDA

The following measurements use training attempts and realization 101 only.
Timely means delivered by the capture bin's end plus the fixed 100 ms grace.
Longest gaps include unsupported intervals at the edges of the four-second window.

{markdown_table(summary)}

![Packet coverage](figures/packet_coverage.png)
![Joint coverage](figures/joint_coverage.png)
![Phase inputs](figures/phase_inputs.png)

The next figure uses the first cohort attempt and test replay seed, after model
freezing, to illustrate time-varying availability and queue delay. It is an
example rather than an aggregate result. Deadline bands vary with each
packet's position inside its 20 ms capture bin.

![Delivery timeline](figures/delivery_timeline.png)

## Replay assumptions

- `original_100` preserves original packet values, timing and natural losses,
  with ideal replacement transport. `rate_80` retains four of every five source
  rounds, preserving 10/20 ms spacing; it is not a uniform 12.5 ms hardware trace.
- `rr2_80` makes one of the two actual views blind per retained round. Four-slot
  cases make each actual view blind on its assigned turns and add two virtual
  traffic sources. Virtual sources contain byte workloads only, never CSI.
- A grant owner is unavailable for its retained round. A separate uniform
  target-rate clock supplies equal-length grants after a 1 ms sensing guard;
  grants are assumed announced ahead of time. Source capture times retain
  their original thinning jitter. This avoids assigning the repeated 20 ms
  thinning gap to the same receiver on every round-robin cycle.
  Schedule phases/seeds are label-independent. Actual BLE controller events,
  maintenance traffic, ACK latency, RF interference, and stack behavior are
  not reproduced. On-time transfer completion is the application receipt proxy.
- Additional losses: 5% independent loss, a per-round burst-entry probability
  0.015, and burst-exit probability 0.25. These are assumed stresses, not
  estimated ESP32 loss rates. Separate RNG streams keep capture losses paired
  when changing only the transport capacity.
- Constrained cases assume 1.4 or 1.0 Mbit/s shared application service, 32-record
  queues, 250 ms age expiry, oldest-record overflow eviction, 3% whole-transfer
  failure and one retry. A record costs CSI bytes + 119 metadata bytes, plus
  12 assumed header bytes per 232-byte fragment. Partial service carries into
  that receiver's later grants. Unused capacity never accumulates or spills
  into another receiver's grant. Virtual traffic is idealized before injected
  losses; it does not duplicate the original real receivers' natural loss.
- Source losses stay missing. The source sequence grid and USB affine clock
  mapping are reconstructed retrospectively. The replay cannot recover missing
  source observations or emulate changed AGC/phase behavior under real BLE.

## Preprocessing and training

The unchanged pinned HE-LTF decoder performs packet-local phase masking and
weighted linear phase calibration. All 242 usable physical tones remain.
There is no temporal denoising or interpolation. Four-second action-cue windows
use 50 bins/s; circular phases are averaged through sine/cosine only after
simulated capture loss and per-bin delivery deadlines are applied.

The CNN receives four phase channels, four finite-value masks, two packet-count
channels (scaled by two source packets/bin), and two bounded age channels.
Age uses only packets captured before that bin ends and received before its
deadline. A placeholder is zero only after train-only normalization. Those
additional channels expose losses even when a bin still contains one sample.
The prediction uses the complete four-second window plus delivery grace;
this is not a measured fall-alarm latency or streaming detector.

Both regimes use the same original attempts and maximum optimizer steps.
Clean training sees the original condition; missingness training draws one
condition/realization per attempt per epoch. Training replay seeds are 101/202,
validation uses 303, and test uses 404. All variants of a source attempt remain
in its frozen scenario partition. Both regimes share a normalizer fitted only
to original training attempts. Architecture is the pilot's small three-layer
CNN, AdamW, class-weighted BCE and validation early stopping. Clean checkpoints
minimize original-condition validation BCE; augmented checkpoints minimize
equal-condition validation BCE. Both regimes are reported without test-based
selection. Training took {selected["training_seconds"]:.1f} seconds.

![Training curves](figures/training_curves.png)

## Missingness-only diagnostic

This baseline sees availability, packet-count and age summaries, without signal
values. Nonchance performance can reflect acquisition/cohort confounding and
must be considered when interpreting CNN results. Signal-summary logistic and
majority comparisons are also in `test_metrics.csv`.

{markdown_table(missing)}

## Reproducibility and limits

`manifest.json` pins {len(manifest["source_sha256"])} source hashes, all prepared
array hashes, reused decoder/model code, config and split. `selection.json`
pins checkpoints and package versions. Raw data is read-only. Large arrays
and checkpoints stay in ignored `artifacts/`; this folder contains small
reports, plots, diagnostics and predictions. Rerun commands are in the README.

This pilot can assess robustness to the stated missingness/service model for
two measured CSI views. Four-receiver model performance, actual BLE feasibility,
true uniform 80 Hz sampling, independent-session generalization and alarm
latency require new measurements. No simulated throughput is a hardware result.
"""
    (output / "REPORT.md").write_text(text)
    destination.mkdir(parents=True, exist_ok=True)
    for path in output.iterdir():
        if path.is_file() and path.suffix in (".csv", ".json", ".md"):
            shutil.copy2(path, destination / path.name)
    shutil.copytree(figures, destination / "figures", dirs_exist_ok=True)
    print(f"Shareable report: {destination / 'REPORT.md'}", flush=True)
