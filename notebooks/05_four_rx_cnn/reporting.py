"""Training-only signal EDA and an empirical four-receiver experiment report."""

from pathlib import Path
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay, RocCurveDisplay

from support import FOLDER, LABELS, read_json, sha256, write_json


def eda(config: dict, output: Path) -> None:
    """Inspect metadata for all splits and CSI values only for training attempts."""
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    table = pd.read_csv(output / "trials.csv")
    inventory = pd.read_csv(output / "inventory.csv")
    quality = pd.read_csv(output / "quality.csv")
    before = pd.read_csv(output / "split_before_quality.csv")
    before["retained"] = before.attempt_id.isin(table.attempt_id)
    errors = quality.loc[quality.read_error.notna(), ["attempt_id", "read_error"]]
    before.merge(errors, on="attempt_id", how="left").to_csv(
        output / "quality_selection.csv", index=False
    )
    attrition = (
        before.groupby(["split", "label", "target"])
        .agg(eligible=("attempt_id", "size"), retained=("retained", "sum"))
        .reset_index()
    )
    attrition["excluded"] = attrition.eligible - attrition.retained
    attrition.to_csv(output / "quality_attrition.csv", index=False)
    full_quality = quality.merge(
        before[["attempt_id", "split", "label", "retained"]], on="attempt_id"
    )
    full_quality.loc[full_quality.receiver.isin(config["receivers"])].groupby(
        ["split", "receiver", "offset_seconds"]
    ).phase_change_coverage.agg(["count", "min", "median", "max"]).to_csv(
        output / "coverage_before_quality_filter.csv"
    )
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    by_label = (
        attrition.groupby("label")[["retained", "excluded"]].sum().reindex(LABELS)
    )
    by_label.plot.barh(stacked=True, ax=axes[0])
    axes[0].set(
        title="Accepted attempts retained/excluded by fixed quality rule",
        ylabel="",
        xlabel="Attempts",
    )
    for receiver in config["receivers"]:
        q = full_quality.loc[
            full_quality.split.eq("train")
            & full_quality.receiver.eq(receiver)
            & full_quality.offset_seconds.eq(0)
        ]
        axes[1].scatter(
            q.attempt_id.map(dict(zip(before.attempt_id, before.trial_ordinal))),
            q.phase_change_coverage,
            label=receiver,
            s=13,
        )
    axes[1].axhline(config["minimum_coverage"], color="black", ls="--")
    axes[1].set(
        title="Training coverage before quality exclusions",
        xlabel="Collection trial ordinal",
        ylabel="Finite time × tone fraction",
        ylim=(0, 1.02),
    )
    axes[1].legend()
    fig.savefig(figures / "eda_quality_attrition.png", dpi=150)
    plt.close(fig)
    center = config["offsets_seconds"].index(0)
    train = table.loc[table.split.eq("train")]
    train_indices = np.flatnonzero(table.split.eq("train"))
    counts = pd.crosstab(table.label, table.split).reindex(LABELS)
    counts.to_csv(output / "split_counts.csv")
    table.groupby(["split", "target"]).size().rename("attempts").to_csv(
        output / "binary_counts.csv"
    )
    table.groupby(["split", "label"]).scenario_id.nunique().rename("scenarios").to_csv(
        output / "scenario_counts.csv"
    )
    quality = quality.merge(
        table[["attempt_id", "split", "label", "trial_ordinal"]], on="attempt_id"
    )
    train_quality = quality.loc[
        quality.split.eq("train") & quality.receiver.isin(config["receivers"])
    ]
    train_quality.groupby(["label", "receiver", "offset_seconds"]).agg(
        attempts=("attempt_id", "nunique"),
        median_records_s=("records_per_second", "median"),
        median_coverage=("phase_change_coverage", "median"),
        min_coverage=("phase_change_coverage", "min"),
        median_rssi=("rssi_median", "median"),
        median_latency_ms=("latency_median_ms", "median"),
        max_gap_ms=("max_gap_ms", "max"),
        bad_driver_packets=("driver_bad_packets", "sum"),
    ).to_csv(output / "eda_training_quality.csv")
    fig, axes = plt.subplots(1, 3, figsize=(18, 5), constrained_layout=True)
    counts.plot.barh(stacked=True, ax=axes[0])
    axes[0].set(
        title="Accepted attempts and frozen splits", xlabel="Attempts", ylabel=""
    )
    axes[1].boxplot(
        [train.loc[train.label.eq(label), "action_duration_s"] for label in LABELS],
        orientation="horizontal",
        tick_labels=LABELS,
    )
    axes[1].set(title="Training action-cue to recovery-cue", xlabel="Seconds")
    for i, rx in enumerate(config["receivers"]):
        q = train_quality.loc[
            train_quality.receiver.eq(rx) & train_quality.offset_seconds.eq(0)
        ]
        axes[2].scatter(q.trial_ordinal, q.phase_change_coverage, s=12, label=rx)
    axes[2].axhline(config["minimum_coverage"], color="black", ls="--")
    axes[2].set(
        title="Training center-window coverage",
        xlabel="Collection trial ordinal",
        ylabel="Finite time × tone fraction",
        ylim=(0, 1.02),
    )
    axes[2].legend()
    fig.savefig(figures / "eda_inventory.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    center_q = train_quality.loc[train_quality.offset_seconds.eq(0)]
    for rx in config["receivers"]:
        q = center_q.loc[center_q.receiver.eq(rx)]
        for ax, column in zip(
            axes.flat,
            ["records_per_second", "rssi_median", "latency_median_ms", "max_gap_ms"],
        ):
            ax.plot(q.trial_ordinal, q[column], ".", label=rx, alpha=0.75)
            ax.set(xlabel="Training collection trial ordinal", ylabel=column)
    axes[0, 0].set_title("Delivered sensing records per 4-second window")
    axes[0, 1].set_title("RSSI per window (dBm)")
    axes[1, 0].set_title("Host receive minus mapped capture (ms)")
    axes[1, 1].set_title("Largest adjacent received capture gap (ms)")
    axes[0, 0].legend()
    fig.savefig(figures / "eda_transport.png", dpi=150)
    plt.close(fig)
    # Explicitly display chronological activity blocks as a confounding diagnostic.
    fig, ax = plt.subplots(figsize=(13, 4), constrained_layout=True)
    for split, marker in [("train", "o"), ("validation", "^"), ("test", "s")]:
        subset = table.loc[table.split.eq(split)]
        ax.scatter(
            subset.trial_ordinal,
            [LABELS.index(x) for x in subset.label],
            marker=marker,
            s=25,
            label=split,
        )
    ax.set(
        yticks=range(len(LABELS)),
        yticklabels=LABELS,
        xlabel="Collection trial ordinal",
        title="Metadata audit: activities and partition membership over collection order",
    )
    ax.legend()
    fig.savefig(figures / "eda_collection_order.png", dpi=150)
    plt.close(fig)
    examples = [
        table.index[table.split.eq("train") & table.label.eq(label)][0]
        for label in LABELS
    ]
    summary = []
    for rep in config["representations"]:
        data = np.load(output / f"{rep}.npy", mmap_mode="r")
        if rep in {"amplitude", "raw_phase", "calibrated_phase", "phase_change"}:
            fig, axes = plt.subplots(
                len(LABELS),
                len(config["receivers"]),
                figsize=(17, 23),
                constrained_layout=True,
            )
            for li, index in enumerate(examples):
                for ri, rx in enumerate(config["receivers"]):
                    matrix = (
                        data[index, center, ri]
                        if rep == "amplitude"
                        else np.arctan2(
                            data[index, center, 2 * ri], data[index, center, 2 * ri + 1]
                        )
                    )
                    axes[li, ri].imshow(
                        matrix.T,
                        origin="lower",
                        aspect="auto",
                        extent=[0, 4, -122, 122],
                        cmap="viridis" if rep == "amplitude" else "RdBu_r",
                        vmin=None if rep == "amplitude" else -np.pi,
                        vmax=None if rep == "amplitude" else np.pi,
                    )
                    axes[li, ri].set_title(
                        f"{LABELS[li]} {rx} {table.iloc[index].attempt_id}", fontsize=8
                    )
                    if li == len(LABELS) - 1:
                        axes[li, ri].set_xlabel("Seconds after action cue")
                    if ri == 0:
                        axes[li, ri].set_ylabel("HE20 tone")
            fig.suptitle(
                f"First training repetition per activity: {rep}; phase scale ±π radians"
            )
            fig.savefig(figures / f"eda_{rep}_examples.png", dpi=120)
            plt.close(fig)
        for index in train_indices:
            for ri, rx in enumerate(config["receivers"]):
                matrix = (
                    data[index, center, ri]
                    if rep == "amplitude"
                    else np.arctan2(
                        data[index, center, 2 * ri], data[index, center, 2 * ri + 1]
                    )
                )
                finite = matrix[np.isfinite(matrix)]
                summary.append(
                    dict(
                        attempt_id=table.iloc[index].attempt_id,
                        label=table.iloc[index].label,
                        receiver=rx,
                        representation=rep,
                        coverage=float(np.isfinite(matrix).mean()),
                        mean=float(finite.mean()) if len(finite) else None,
                        std=float(finite.std()) if len(finite) else None,
                        median_absolute=float(np.median(np.abs(finite)))
                        if len(finite)
                        else None,
                        p90_absolute=float(np.quantile(np.abs(finite), 0.9))
                        if len(finite)
                        else None,
                    )
                )
        del data
    summary = pd.DataFrame(summary)
    summary.to_csv(output / "eda_training_signal_summary.csv", index=False)
    correlations = []
    for representation in config["representations"]:
        sub = summary.loc[summary.representation.eq(representation)]
        matrix = sub.pivot(
            index="attempt_id", columns="receiver", values="median_absolute"
        )
        correlation = matrix.corr(method="spearman")
        for left in config["receivers"]:
            for right in config["receivers"]:
                correlations.append(
                    dict(
                        representation=representation,
                        receiver_left=left,
                        receiver_right=right,
                        spearman=float(correlation.loc[left, right]),
                    )
                )
    pd.DataFrame(correlations).to_csv(
        output / "eda_training_receiver_correlations.csv", index=False
    )
    window_support = []
    for label, group in train.groupby("label"):
        for offset in config["offsets_seconds"]:
            window_support.append(
                dict(
                    label=label,
                    offset_seconds=offset,
                    attempts=len(group),
                    median_action_duration_s=float(group.action_duration_s.median()),
                    fraction_recovery_cue_after_window=float(
                        (
                            group.action_duration_s > offset + config["window_seconds"]
                        ).mean()
                    ),
                )
            )
    pd.DataFrame(window_support).to_csv(
        output / "eda_training_window_support.csv", index=False
    )
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), constrained_layout=True)
    for ax, rep in zip(axes, ["amplitude", "phase_change"]):
        sub = summary.loc[summary.representation.eq(rep)]
        sub.pivot_table(
            index="label", columns="receiver", values="median_absolute"
        ).reindex(LABELS).plot.barh(ax=ax)
        ax.set(
            title=f"Training per-attempt median |{rep}|, averaged by activity",
            ylabel="",
        )
    fig.savefig(figures / "eda_signal_summary.png", dpi=150)
    plt.close(fig)
    write_json(
        output / "eda_summary.json",
        dict(
            total_attempts=len(inventory),
            status_counts={
                str(k): int(v) for k, v in inventory.status.value_counts().items()
            },
            retained_attempts=len(table),
            scenarios=int(table.scenario_id.nunique()),
            participants=[str(p) for p in table.participant_id.unique()],
            offset_count=len(config["offsets_seconds"]),
            receivers=config["receivers"],
            center_quality={
                rx: dict(
                    median_records_s=float(
                        center_q.loc[
                            center_q.receiver.eq(rx), "records_per_second"
                        ].median()
                    ),
                    minimum_coverage=float(
                        center_q.loc[
                            center_q.receiver.eq(rx), "phase_change_coverage"
                        ].min()
                    ),
                    median_latency_ms=float(
                        center_q.loc[
                            center_q.receiver.eq(rx), "latency_median_ms"
                        ].median()
                    ),
                )
                for rx in config["receivers"]
            },
            policy="Signal plots/statistics restricted to training; full inventory/split metadata and label-independent quality are audited separately. Missing bins remain missing.",
        ),
    )
    print("Saved training-only EDA, diagnostics and figures", flush=True)


def markdown_table(frame: pd.DataFrame) -> str:
    """Render compact Markdown without an optional tabulate dependency."""

    def display(value: object) -> str:
        return f"{value:.3f}" if isinstance(value, (float, np.floating)) else str(value)

    return "\n".join(
        [
            "| " + " | ".join(map(str, frame.columns)) + " |",
            "| " + " | ".join(["---"] * len(frame.columns)) + " |",
            *[
                "| " + " | ".join(display(x) for x in row) + " |"
                for row in frame.itertuples(index=False, name=None)
            ],
        ]
    )


def report(config: dict, output: Path) -> None:
    """Write measured methods/results and copy small artifacts for review."""
    table = pd.read_csv(output / "trials.csv")
    manifest = read_json(output / "manifest.json")
    selection = read_json(output / "selection.json")
    evaluation = read_json(output / "evaluation.json")
    eda_summary = read_json(output / "eda_summary.json")
    results = pd.read_csv(output / "test_metrics.csv")
    predictions = pd.read_csv(output / "test_predictions.csv")
    history = pd.read_csv(output / "training_history.csv")
    candidates = pd.read_csv(output / "validation_candidates.csv")
    figures = output / "figures"
    center_results = results.loc[results.offset_seconds.eq(0)]
    winner = selection["winner"]
    winning_metrics = center_results.loc[
        center_results.scheme.eq(winner["scheme"]) & center_results.model.eq("cnn")
    ].iloc[0]
    order_metrics = center_results.loc[
        center_results.scheme.eq(winner["scheme"])
        & center_results.model.eq("collection_order")
    ].iloc[0]
    quality_metrics = center_results.loc[
        center_results.scheme.eq(winner["scheme"])
        & center_results.model.eq("quality_only")
    ].iloc[0]
    winning = predictions.loc[
        predictions.scheme.eq(winner["scheme"]) & predictions.offset_seconds.eq(0)
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.7), constrained_layout=True)
    ConfusionMatrixDisplay.from_predictions(
        winning.target,
        winning.cnn_prediction,
        display_labels=["Non-fall", "Fall"],
        ax=axes[0],
        colorbar=False,
    )
    RocCurveDisplay.from_predictions(
        winning.target,
        winning.cnn_probability,
        ax=axes[1],
        name="Validation-selected CNN",
    )
    axes[1].plot([0, 1], [0, 1], "--", c="gray")
    for scheme, group in results.loc[results.model.eq("cnn")].groupby("scheme"):
        axes[2].plot(group.offset_seconds, group.balanced_accuracy, "o-", label=scheme)
    axes[2].set(
        xlabel="Window shift from cue (s)",
        ylabel="Test balanced accuracy",
        ylim=(0, 1.03),
        title="Correlated timing-sensitivity measurements",
    )
    axes[2].legend()
    fig.savefig(figures / "test_evaluation.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(17, 5), constrained_layout=True)
    for scheme in config["schemes"]:
        c = candidates.loc[candidates.scheme.eq(scheme)]
        axes[0].plot(c.balanced_accuracy, c.representation, "o-", label=scheme)
        rep = selection["selected_by_scheme"][scheme]
        sub = history.loc[history.scheme.eq(scheme) & history.representation.eq(rep)]
        for seed, group in sub.groupby("seed"):
            axes[1].plot(
                group.epoch, group.train_loss, label=f"{scheme} {seed}", alpha=0.7
            )
            axes[2].plot(
                group.epoch, group.validation_loss, label=f"{scheme} {seed}", alpha=0.7
            )
    axes[0].set(
        xlabel="Central validation balanced accuracy",
        title="Predefined representation comparison",
    )
    axes[0].legend(fontsize=8)
    axes[1].set(
        xlabel="Epoch",
        ylabel="Weighted BCE",
        title="Training losses, selected representations",
    )
    axes[2].set(
        xlabel="Epoch",
        ylabel="Weighted BCE",
        title="Validation losses, selected representations",
    )
    axes[2].legend(fontsize=7)
    fig.savefig(figures / "training_curves.png", dpi=150)
    plt.close(fig)
    stability = predictions.groupby(["scheme", "attempt_id"]).cnn_prediction.nunique()
    changed = {s: int(stability.loc[s].gt(1).sum()) for s in config["schemes"]}
    splits = table.groupby("split").size().to_dict()
    counts = pd.read_csv(output / "split_counts.csv")
    attrition = pd.read_csv(output / "quality_attrition.csv")
    class_attrition = (
        attrition.groupby("target")[["eligible", "retained", "excluded"]]
        .sum()
        .reset_index()
    )
    quality_table = pd.DataFrame(eda_summary["center_quality"]).T.reset_index(
        names="receiver"
    )
    metrics_columns = [
        "scheme",
        "model",
        "n",
        "balanced_accuracy",
        "fall_recall",
        "specificity",
        "roc_auc",
        "tp",
        "fn",
        "fp",
        "tn",
    ]
    sensitivity_columns = [
        "scheme",
        "offset_seconds",
        "balanced_accuracy",
        "fall_recall",
        "specificity",
        "tp",
        "fn",
        "fp",
        "tn",
    ]
    intervals = "\n".join(
        f"- {scheme}: {values}"
        for scheme, values in evaluation[
            "center_scenario_bootstrap_95_percent_intervals"
        ].items()
    )
    text = f"""# Four-receiver CSI EDA and CNN experiment

The completed session `20261104T081805521126Z` contains {eda_summary["total_attempts"]} attempts: {eda_summary["status_counts"]}. The experiment retains {len(table)} accepted attempts across {table.scenario_id.nunique()} activity/direction scenarios and nine activity families, with {manifest["excluded_after_scope"]} additional signal-quality exclusions. One ESP32-C5 transmitter supplies four real receiver views. All recordings belong to participant `{table.participant_id.iloc[0]}` in one session; this is exploratory binary attempt classification.

## Inventory and EDA

Whole scenarios, including every repetition, retake and receiver, stay within one seeded partition. Membership was frozen before signal-quality reads: {splits}. CSI values in the EDA come exclusively from training attempts. Inventory and split metadata describe all partitions.

{markdown_table(counts)}

![Inventory and training coverage](figures/eda_inventory.png)

Quality filtering uses no labels, but its observed exclusions can still differ by class. The class totals below describe attrition before any model fitting. Scores apply to the retained subset and do not measure performance on excluded low-coverage attempts.

{markdown_table(class_attrition)}

![Quality attrition and training coverage before filtering](figures/eda_quality_attrition.png)

The following training center-window summaries count delivered sensing records per four-second window. A received timestamp gap includes scheduling and delivery effects; it is not a direct RF-loss probability. Latency is host receipt minus mapped transmitter enqueue time, rather than a measurement of ADC acquisition time.

{markdown_table(quality_table)}

![Training transport diagnostics](figures/eda_transport.png)

![Collection order and split membership](figures/eda_collection_order.png)

Activity labels are blocked in collection order. Scenario separation prevents repeated-window leakage, but does not remove shared participant, room, time, equipment or recording-condition effects. The collection-order and quality-only controls below help expose these associations; they do not establish the causal signal used by a CNN.

![Training signal summaries](figures/eda_signal_summary.png)

Full receiver-by-activity galleries show [log amplitude](figures/eda_amplitude_examples.png), [raw phase](figures/eda_raw_phase_examples.png), [calibrated phase](figures/eda_calibrated_phase_examples.png), and [100 ms phase change](figures/eda_phase_change_examples.png). Each uses the first training attempt per activity, selected without ranking its signal. Phase heatmaps use ±π radians. Summary phase values are reconstructed with atan2 from binned sine/cosine components; they are descriptive, not original unbinned phase statistics.

`eda_training_receiver_correlations.csv` gives Spearman correlations between receivers' per-attempt median absolute values, separately for each representation. These aggregate associations are not waveform synchronization measures. `eda_training_window_support.csv` reports how often the recovery cue falls after each four-second training window. A cue window ending before recovery does not establish whether impact is present or absent; verified impact annotations are unavailable.

## Preprocessing and window schema

The canonical repository loader verifies CSI/timing sequence and receiver-timestamp alignment, validates the gateway capture sidecar and its epoch identities, filters the recorded transmitter's HE20 MCS0/20 MHz sensing link, and sorts only derived views by mapped transmitter enqueue time. Missing gateway alignment is an error; host arrival time is never substituted. The inherited loader calls this time source BLE in its string, but these inputs use the actual `gateway_timing.jsonl` sidecar. The experiment records an explicit gateway label.

Driver `rx_state != 0` packets are masked. Canonical physical-slot, weak-amplitude and finite-value masks remain in force. All 242 valid physical HE20 tones are retained; only the three structural DC tones −1, 0, +1 are removed. There is no frequency reduction, gap interpolation or synthetic receiver data.

Every attempt has five four-second windows: `[cue + δ, cue + δ + 4)`, where δ is −0.50, −0.25, 0, +0.25 or +0.50 seconds. Signals are averaged inside 25 Hz bins (100 time bins); sine/cosine components preserve circular phase during averaging. Windows can include countdown/recovery or omit part of a longer action. The operator action cue is not a verified fall-impact timestamp.

Representations are log1p amplitude, raw-phase sine/cosine, calibrated-phase sine/cosine, 100 ms calibrated circular-change sine/cosine, and a three-bin smoothing ablation of that change. The 100 ms lag rejects support beyond 150 ms. It may use pre-window packets, including across operator phase cues; it is a fixed-lag signal feature, not a phase-segment duration measure. Smoothing is centered/offline, does not fill missing center bins, and does not establish causal live performance. Each receiver in each offset must meet the predefined {config["minimum_coverage"]:.0%} phase-change coverage threshold. An attempt failing any offset is removed from every scheme without redrawing the split.

Per-channel/tone means and scales use training inputs only (scale floor 0.05). The fixed scheme fits its zero-offset training windows; augmentation fits all configured training offsets. Missing normalized values become zero and each channel gets an explicit finite-value mask. Thus amplitude has eight model channels and phase representations have sixteen, combining all four receiver views.

## CNN training and validation

The reused small CNN has three convolution layers (8, 16 and 32 outputs), ReLU, global average pooling, dropout 0.25 and one fall logit. Class-weighted BCE and AdamW use learning rate {config["learning_rate"]}, weight decay {config["weight_decay"]}, batch size {config["batch_size"]}, at most {config["max_epochs"]} epochs and patience {config["patience"]}. Seeds {config["training_seeds"]} produce a three-model probability ensemble. CPU deterministic algorithms are enabled.

The fixed scheme sees offset zero. The augmented scheme chooses one seeded uniform offset per training attempt each epoch. Both have the same attempts and maximum optimizer-update budget; augmentation does not multiply training examples or update counts. Early stopping can yield different actual epoch counts. Validation always uses one central window per attempt. Normalization differs consistently with each scheme's training distribution.

The selection rule is highest central validation ensemble balanced accuracy, then ROC AUC, then predefined configuration order, with a fixed 0.5 decision threshold. The selected representations are `{selection["selected_by_scheme"]}`. The overall frozen winner is `{winner}`. All selections were saved before test scoring. Comparing separately selected representations is a pipeline comparison, not an isolated causal estimate of shift augmentation.

{markdown_table(candidates[["scheme", "representation", "balanced_accuracy", "roc_auc", "fall_recall", "specificity"]])}

Training took {selection["training_seconds"] / 60:.2f} minutes. Each epoch has {int(history.updates_per_epoch.iloc[0])} optimizer updates. Dependency versions: `{selection["versions"]}`. The CPU environment/lock and common model helpers are maintained in `../shared_cnn`.

![Validation selection and learning curves](figures/training_curves.png)

## Held-out attempt evaluation

There are {evaluation["test_attempts"]} test attempts across {evaluation["test_scenarios"]} scenarios. Each row below uses one center window per attempt. Fall is the positive class. Summary logistic uses standardized global channel means/standard deviations of the selected input and masks. Quality-only logistic sees coverage of each representation, packet counts, maximum capture gaps and driver-error counts per receiver. Collection-order logistic sees only trial ordinal. Baseline transforms and classifiers fit central training attempts only, with no test fitting.

{markdown_table(center_results[metrics_columns])}

The validation-selected CNN obtains center-window balanced accuracy {winning_metrics.balanced_accuracy:.3f} on {int(winning_metrics.n)} attempts ({int(winning_metrics.tp)} detected falls, {int(winning_metrics.fn)} missed falls, {int(winning_metrics.fp)} false-positive non-falls). Collection order alone obtains {order_metrics.balanced_accuracy:.3f}, and the quality-only control obtains {quality_metrics.balanced_accuracy:.3f}. These controls quantify associations in this recording; the CNN score does not isolate a motion-specific fall signal.

![Held-out confusion matrix, ROC and offset sensitivity](figures/test_evaluation.png)

Scenario-cluster 95% bootstrap intervals (2,000 draws, seed 812), conditional on this split and session:

{intervals}

## Backward/forward timing sensitivity

All offsets use the already frozen per-scheme representation, scaler, checkpoints and threshold. The same held-out attempts appear at every offset; these are correlated robustness measurements, not independent samples or a larger test cohort. No offset or model was selected using these test scores.

{markdown_table(results.loc[results.model.eq("cnn"), sensitivity_columns])}

Predictions change across offsets for {changed} test attempts. These counts measure timing sensitivity on this cohort; they are not continuous detector false-alarm rates. Per-attempt/seed probabilities, activity errors and stability ranges are saved in the accompanying CSVs.

## Limits and reproducibility

One participant and one session cannot establish generalization to new people, sessions, rooms, device positions, natural falls or continuous daily activity. The action cue is operator generated, video exposure/pipeline delay is unknown, and this experiment does not infer impact timing from video. Collection order and receiver-quality associations can inflate within-session discrimination. A high CSI score therefore requires interpretation alongside the controls rather than attribution to a fall mechanism. The test set has now been inspected and must not be reused as an untouched selection set in later tuning.

Raw recordings were read without modification. `manifest.json` records raw-input SHA-256 hashes, code, configuration, derived arrays and frozen splits; `selection.json` hashes checkpoints and records model selection. Large arrays and CPU checkpoints remain ignored in `artifacts/four_rx_v1/`; small tables, plots and this report are copied to `results/four_rx_v1/`. The executed notebook reads these results by default. Reruns should use a fresh output directory.
"""
    (output / "REPORT.md").write_text(text, encoding="utf-8")
    destination = FOLDER / "results" / output.name
    destination.mkdir(parents=True, exist_ok=True)
    for p in output.iterdir():
        if p.is_file() and p.suffix in {".json", ".csv", ".md"}:
            shutil.copy2(p, destination / p.name)
    shutil.copytree(figures, destination / "figures", dirs_exist_ok=True)
    write_json(
        destination / "result_hashes.json",
        {
            str(p.relative_to(destination)): sha256(p)
            for p in sorted(destination.rglob("*"))
            if p.is_file() and p.name != "result_hashes.json"
        },
    )
    print(f"Saved report and small artifacts to {destination}", flush=True)
