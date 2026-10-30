"""Training-only signal EDA and saved, reviewable experiment results."""

from pathlib import Path
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay, RocCurveDisplay

from data_pipeline import LABELS, read_json


DISPLAY = {label: label.replace("_to_", " → ") for label in LABELS}


def eda(config: dict, output: Path) -> None:
    """Plot inventory and inspect signals only from the training partition."""
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    table = pd.read_csv(output / "trials.csv")
    quality = pd.read_csv(output / "quality.csv")
    counts = pd.crosstab(table.label, table.split).reindex(LABELS)
    counts.to_csv(output / "split_counts.csv")
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)
    counts.plot.barh(ax=axes[0], stacked=True)
    axes[0].set(title="Attempts per activity and split", xlabel="Attempts", ylabel="")
    train = table.loc[table.split.eq("train")]
    axes[1].boxplot(
        [train.loc[train.label.eq(label), "action_duration_s"] for label in LABELS],
        orientation="horizontal",
        tick_labels=[DISPLAY[label] for label in LABELS],
    )
    axes[1].set(title="Training action-cue to recovery-cue duration", xlabel="Seconds")
    for receiver in config["receivers"]:
        merged = train.merge(quality, on="attempt_id")
        axes[2].plot(
            np.arange(len(merged)), merged[f"{receiver}_coverage"], ".", label=receiver
        )
    axes[2].axhline(config["minimum_coverage"], color="black", linestyle="--")
    axes[2].set(
        title="Training input coverage",
        xlabel="Training attempt order",
        ylabel="Finite time × tone fraction",
        ylim=(0, 1.02),
    )
    axes[2].legend()
    fig.savefig(figures / "eda_inventory.png", dpi=150)
    plt.close(fig)
    # Deterministic first training example per activity, never signal-ranked.
    examples = [
        table.index[table.split.eq("train") & table.label.eq(label)][0]
        for label in LABELS
    ]
    fig, axes = plt.subplots(6, 4, figsize=(16, 17), constrained_layout=True)
    summary = []
    with np.load(output / "dataset.npz") as data:
        for row_index, index in enumerate(examples):
            for column, receiver in enumerate(config["receivers"]):
                for offset, (name, component, limit) in enumerate(
                    [("amplitude", column, None), ("phase_change", 2 * column, 1)]
                ):
                    ax = axes[row_index, 2 * column + offset]
                    matrix = data[name][index, component]
                    image = ax.imshow(
                        matrix.T,
                        origin="lower",
                        aspect="auto",
                        extent=[0, config["window_seconds"], -122, 122],
                        cmap="viridis" if limit is None else "RdBu_r",
                        vmin=None if limit is None else -limit,
                        vmax=limit,
                    )
                    ax.set_title(
                        f"{table.iloc[index].attempt_id} {receiver}: {'log amplitude' if offset == 0 else 'sin(100 ms change)'}",
                        fontsize=9,
                    )
                    if column == 0 and offset == 0:
                        ax.set_ylabel(
                            DISPLAY[table.iloc[index].label]
                            + "\nPhysical tone (DC omitted)"
                        )
                    if row_index == 5:
                        ax.set_xlabel("Seconds after action cue")
                    fig.colorbar(image, ax=ax, fraction=0.03)
        for name in config["representations"]:
            values = data[name]
            for index in np.flatnonzero(table.split.eq("train")):
                summary.append(
                    {
                        "attempt_id": table.iloc[index].attempt_id,
                        "label": table.iloc[index].label,
                        "representation": name,
                        "finite_fraction": float(np.isfinite(values[index]).mean()),
                        "mean_absolute_component": float(
                            np.nanmean(np.abs(values[index]))
                        ),
                        "component_std": float(np.nanstd(values[index])),
                    }
                )
    pd.DataFrame(summary).to_csv(output / "training_signal_summary.csv", index=False)
    fig.savefig(figures / "eda_training_examples.png", dpi=130)
    plt.close(fig)
    # The same predetermined training examples expose the calibrated input too.
    fig, axes = plt.subplots(6, 4, figsize=(16, 17), constrained_layout=True)
    with np.load(output / "dataset.npz") as data:
        for row_index, index in enumerate(examples):
            for receiver_index, receiver in enumerate(config["receivers"]):
                for component, component_name in enumerate(["sine", "cosine"]):
                    ax = axes[row_index, 2 * receiver_index + component]
                    matrix = data["calibrated_phase"][
                        index, 2 * receiver_index + component
                    ]
                    image = ax.imshow(
                        matrix.T,
                        origin="lower",
                        aspect="auto",
                        extent=[0, config["window_seconds"], -122, 122],
                        cmap="RdBu_r",
                        vmin=-1,
                        vmax=1,
                    )
                    ax.set_title(
                        f"{table.iloc[index].attempt_id} {receiver}: calibrated {component_name}",
                        fontsize=9,
                    )
                    if receiver_index == component == 0:
                        ax.set_ylabel(
                            DISPLAY[table.iloc[index].label]
                            + "\nPhysical tone (DC omitted)"
                        )
                    if row_index == 5:
                        ax.set_xlabel("Seconds after action cue")
                    fig.colorbar(image, ax=ax, fraction=0.03)
    fig.savefig(figures / "eda_calibrated_training_examples.png", dpi=130)
    plt.close(fig)


def report(config: dict, output: Path) -> None:
    """Create plots, a factual report, and a small versionable result snapshot."""
    results = read_json(output / "test_metrics.json")
    selection = read_json(output / "selection.json")
    manifest = read_json(output / "manifest.json")
    table = pd.read_csv(output / "trials.csv")
    predictions = pd.read_csv(output / "test_predictions.csv")
    validation = pd.read_csv(output / "validation_candidates.csv")
    history = pd.read_csv(output / "training_history.csv")
    activities = pd.read_csv(output / "test_activity_metrics.csv")
    quality = pd.read_csv(output / "quality.csv")
    figures = output / "figures"
    figures.mkdir(exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), constrained_layout=True)
    ConfusionMatrixDisplay.from_predictions(
        predictions.target,
        predictions.cnn_prediction,
        display_labels=["Non-fall", "Fall"],
        cmap="Blues",
        colorbar=False,
        ax=axes[0],
    )
    axes[0].set_title("Held-out scenarios: CNN ensemble")
    RocCurveDisplay.from_predictions(
        predictions.target, predictions.cnn_probability, ax=axes[1], name="CNN ensemble"
    )
    axes[1].plot([0, 1], [0, 1], "--", color="gray")
    axes[1].set_title("Held-out ROC")
    for target, label, color in [(0, "Non-fall", "#2563eb"), (1, "Fall", "#ea580c")]:
        values = predictions.loc[predictions.target.eq(target), "cnn_probability"]
        axes[2].scatter(
            np.full(len(values), target) + np.linspace(-0.12, 0.12, len(values)),
            values,
            label=label,
            color=color,
        )
    axes[2].axhline(0.5, color="black", linestyle="--")
    axes[2].set(
        xticks=[0, 1],
        xticklabels=["Non-fall", "Fall"],
        ylabel="Predicted fall probability",
        title="Held-out attempt predictions",
        ylim=(-0.02, 1.02),
    )
    fig.savefig(figures / "test_evaluation.png", dpi=160)
    plt.close(fig)
    selected = selection["selected_representation"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), constrained_layout=True)
    axes[0].barh(
        validation.representation,
        validation.balanced_accuracy,
        color=[
            "#ea580c" if name == selected else "#2563eb"
            for name in validation.representation
        ],
    )
    axes[0].axvline(0.5, color="black", linestyle="--")
    axes[0].set(
        xlabel="Validation balanced accuracy",
        xlim=(0, 1),
        title="Representation selection (validation only)",
    )
    for seed in config["training_seeds"]:
        group = history.loc[history.representation.eq(selected) & history.seed.eq(seed)]
        axes[1].plot(group.epoch, group.train_loss, label=f"Train {seed}")
        axes[1].plot(
            group.epoch, group.validation_loss, "--", label=f"Validation {seed}"
        )
    axes[1].set(
        xlabel="Epoch",
        ylabel="Weighted binary cross entropy",
        title=f"Learning curves: {selected}",
    )
    axes[1].legend(fontsize=8, ncol=2)
    fig.savefig(figures / "validation_and_learning.png", dpi=160)
    plt.close(fig)
    score_rows = []
    for name, scores in results["metrics"].items():
        score_rows.append(
            f"| {name} | {scores['accuracy']:.3f} | {scores['balanced_accuracy']:.3f} | {scores['fall_recall']:.3f} | {scores['specificity']:.3f} | {scores['fall_f1']:.3f} | {scores['roc_auc']:.3f} |"
        )
    counts = table.groupby("split").size().to_dict()
    intervals = results["cnn_scenario_bootstrap_95_percent_intervals"]
    confusion = results["metrics"]["cnn"]
    activity_rows = [
        f"| {row.activity} | {row.n} | {row.accuracy:.3f} |"
        for row in activities.itertuples()
    ]
    validation_rows = [
        f"| {row.representation} | {row.balanced_accuracy:.3f} | {row.roc_auc:.3f} |"
        for row in validation.itertuples()
    ]
    report_text = f"""# CSI CNN pilot: executed results

This experiment classifies a fixed, cue-aligned four-second recording as fall or
non-fall. The selected input is **{selected}**. The held-out test set contains
{results["test_attempts"]} attempts in {results["test_scenarios"]} activity/direction scenarios.
The CNN ensemble has balanced accuracy {confusion["balanced_accuracy"]:.3f}, fall
recall {confusion["fall_recall"]:.3f}, and specificity {confusion["specificity"]:.3f}.
These are results from one session and participant, not evidence of performance
on new people, rooms, sessions, or continuous streams.

## Data and EDA

Session: `{table.session_id.iloc[0]}`. Effective participant:
`{table.participant_id.iloc[0]}`. Accepted and reviewed scope is resolved using
reference-truth labels, then review corrections, then planned labels. Bad or
excluded reviews and non-accepted attempts are excluded. Source-file SHA-256
hashes and dataset hashes are in [manifest.json](manifest.json).

{manifest["attempts_retained"]} attempts remain; {manifest["attempts_excluded_after_scope"]}
additional attempts were excluded by preprocessing quality. Read failures:
{int(quality.read_error.fillna("").ne("").sum())}. Counts are train
{counts.get("train", 0)}, validation {counts.get("validation", 0)}, test
{counts.get("test", 0)}. [Inventory](inventory.csv), [quality](quality.csv), and
[split membership](trials.csv) retain the audit trail. Signal examples below use
only training attempts, selected by identity rather than observed disturbance.

![Inventory and training quality](figures/eda_inventory.png)

![First training example per activity](figures/eda_training_examples.png)

![Calibrated sine/cosine for the same training examples](figures/eda_calibrated_training_examples.png)

## Preprocessing

The pinned canonical HE-LTF decoder filters the transmitter MAC and HE20/MCS0
format, masks amplitudes below 4, and calibrates packet-wise phase slope/offset.
Recorded USB affine clock fits align receivers to the host event timeline;
[quality.csv](quality.csv) records fallback timing and uncertainty when applicable.
The experiment keeps 242 physical tones, removing only DC slots -1, 0, 1.
Receiver streams are aligned by the same cue, retained as separate feature
channels, and combined in the CNN. No receiver is a separate training example.

Each input covers [0, 4) seconds after the action cue, with 100 time bins at
25 Hz. Packets are averaged within each bin per tone. Phase is represented by
sine/cosine components before averaging to avoid a false discontinuity at ±pi.
Phase change is the signed calibrated change over 100 ms, with actual lag at
most 150 ms. Lag endpoints can cross a cue: phase-boundary metadata is not
supplied to the model. Empty bins remain missing; there is no interpolation or
activity-duration-dependent cropping/padding. A short action may include its
recovery, while a long action may be truncated. Actual fall-onset times are
unknown. The 25 Hz binning is a fixed pilot choice, not a validated optimum.

The smoothing ablation averages three adjacent bins (120 ms support), preserving
missing center bins. It uses neighboring samples and the whole input window;
this is offline classification. Training-only channel/tone means and standard
deviations scale all partitions, with a 0.05 standard-deviation floor. Missing
values become zero after scaling, accompanied by explicit finite-value masks.
Both receiver phase-change coverages must reach {config["minimum_coverage"]:.0%}.
The threshold and all model settings were fixed before test evaluation.

## Split and model

The seeded split assigns entire scenarios within each of the six activity
families to approximately 60/20/20 percent train/validation/test partitions.
Both repetitions, all retakes, all tones, and both receivers stay together.
Membership is frozen before signal-quality exclusions; exclusions do not redraw
it. This is stricter than splitting individual attempts, but every partition
shares the same participant, session, hardware, room, and acquisition protocol.
Activities were collected in blocks, so recording-order drift is a possible
confound. Scenario holdout does not remove that confound.

The CNN has three convolution/ReLU stages (8, 16, 32 channels; strides 2), global
average pooling, dropout 0.25, and one binary output. Learned convolutions receive
the full time-by-tone grid; there is no PCA or tone average before the CNN.
AdamW uses learning rate {config["learning_rate"]} and weight decay
{config["weight_decay"]}. Training uses class-weighted binary cross entropy,
batches of {config["batch_size"]}, at most {config["max_epochs"]} epochs, and
validation-loss early stopping with patience {config["patience"]}. Seeds are
{config["training_seeds"]}; predictions average the three independently fitted
models. The decision threshold stays at 0.5. No augmentation or architecture
search was performed. Train-only simple logistic and majority baselines provide
reference scores. The quality-only logistic baseline uses missingness summaries
from the four original representations and no signal values.

## Validation selection

Epoch selection minimizes validation loss; representation selection maximizes
ensemble validation balanced accuracy, then ROC AUC, then configured order.
Test predictions are computed only after this selection is saved. The five
candidate scores below are validation results; they do not establish superiority
on an independent session. Code, checkpoint hashes, package versions, and elapsed
training time are in [selection.json](selection.json).

| Input | Validation balanced accuracy | Validation ROC AUC |
| --- | ---: | ---: |
{chr(10).join(validation_rows)}

![Validation selection and learning curves](figures/validation_and_learning.png)

## Held-out evaluation

| Model | Accuracy | Balanced accuracy | Fall recall | Specificity | Fall F1 | ROC AUC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(score_rows)}

The selected CNN identifies {confusion["tp"]} falls and misses {confusion["fn"]};
it correctly rejects {confusion["tn"]} non-falls and flags {confusion["fp"]} as
falls. Scenario-cluster bootstrap 95% intervals (2,000 resamples, fixed seed 812)
are [{intervals["balanced_accuracy"][0]:.3f}, {intervals["balanced_accuracy"][1]:.3f}]
for balanced accuracy and [{intervals["fall_recall"][0]:.3f},
{intervals["fall_recall"][1]:.3f}] for fall recall. These exploratory intervals
condition on this split and do not include participant or selection uncertainty.
If every observed fall is detected, resampling those same successes produces a
degenerate recall interval of [1, 1]. That interval does not establish perfect
population sensitivity or bound the risk of missing a future fall.

![Held-out evaluation](figures/test_evaluation.png)

| Held-out activity | Attempts | Accuracy at fixed threshold |
| --- | ---: | ---: |
{chr(10).join(activity_rows)}

[Per-attempt predictions](test_predictions.csv) retain probabilities for each
seed and the ensemble. [Seed metrics](test_seed_metrics.csv) describe fitting
variability on the same test set; these are not independent test cohorts.

## Interpretation and remaining work

The CNN separates the labels on this within-session holdout, whereas the earlier
descriptive plots did not establish separation. Calibrated phase wins the
validation comparison; its absolute sine/cosine structure may retain static
channel information as well as motion. The 100 ms change inputs have much lower
validation scores in this experiment, so these results do not establish that
short phase-change bursts explain the classification.

The signal-summary logistic baseline reaches balanced accuracy
{results["metrics"]["summary_logistic"]["balanced_accuracy"]:.3f}. The quality-only
baseline reaches balanced accuracy {results["metrics"]["quality_only"]["balanced_accuracy"]:.3f}
and ROC AUC {results["metrics"]["quality_only"]["roc_auc"]:.3f} without seeing
signal values. Missingness therefore carries label information in this test set,
and acquisition artifacts offer a competing explanation for some predictability.
These comparisons do not isolate how much of the CNN score comes from motion,
static channel structure, recording-order drift, or quality differences.

The present data do not support a session- or participant-independent conclusion.
The four-second window is aligned to an operator cue, not an annotated impact.
Continuous detection, false alarms per hour, onset latency, unseen-activity
performance, and calibration under realistic fall prevalence remain untested.
Collect independent sessions and participants, annotate movement/impact timing,
and evaluate a frozen pipeline on those recordings before making a generalization
claim. Further tuning must use training/validation data; this test partition is
already consumed by the reported evaluation.
"""
    (output / "REPORT.md").write_text(report_text)
    # Keep small result artifacts versionable; arrays and model weights stay local.
    snapshot = Path(__file__).parent / "results" / output.name
    snapshot.mkdir(parents=True, exist_ok=True)
    for path in output.iterdir():
        if path.is_file() and path.suffix in {".json", ".csv", ".md"}:
            shutil.copy2(path, snapshot / path.name)
    shutil.copytree(figures, snapshot / "figures", dirs_exist_ok=True)
    print(f"Saved report: {snapshot / 'REPORT.md'}", flush=True)
