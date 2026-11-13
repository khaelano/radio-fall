"""Reconstruct collection phases from host-clock events and attempt manifests."""

from collections import defaultdict
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    import pandas as pd

PHASES = ("countdown", "action", "recovery")
_COMPLETED = {"accepted", "rejected", "skipped", "pending_review"}
INTERVAL_SCHEMA = {
    "attempt_id": pl.String,
    "trial_ordinal": pl.Int64,
    "attempt_number": pl.Int64,
    "activity_label": pl.String,
    "status": pl.String,
    "phase": pl.String,
    "phase_start_monotonic_ns": pl.Int64,
    "phase_end_monotonic_ns": pl.Int64,
    "observed_seconds": pl.Float64,
    "planned_seconds": pl.Float64,
    "duration_delta_seconds": pl.Float64,
}
CHECK_SCHEMA = {
    "attempt_id": pl.String,
    "trial_ordinal": pl.Int64,
    "activity_label": pl.String,
    "status": pl.String,
    "phase_sequence": pl.String,
    "phase_order_valid": pl.Boolean,
    "phase_bounds_valid": pl.Boolean,
    "all_phases_present": pl.Boolean,
    "completed_attempt_has_all_phases": pl.Boolean,
    "action_confirmed_manifest": pl.Boolean,
    "action_confirmed_event": pl.Boolean,
    "action_confirmation_matches": pl.Boolean,
    "confirmation_occurs_during_action": pl.Boolean,
    "trial_resolution_matches_status": pl.Boolean,
    **{f"{phase}_seconds": pl.Float64 for phase in PHASES},
}


def as_polars(frame: "pl.DataFrame | pd.DataFrame") -> pl.DataFrame:
    """Return a polars frame, converting a pandas frame at the module boundary.

    Args:
        frame: A polars frame, or a pandas frame such as the one returned by
            ``AnalysisSession.read_packets``.

    Returns:
        ``frame`` unchanged when it is already polars; otherwise its conversion.
    """
    return (
        frame
        if isinstance(frame, pl.DataFrame)
        else pl.from_pandas(frame, nan_to_null=True)
    )


def reconstruct_phases(
    attempts: list[dict[str, Any]], events: list[dict[str, Any]], trials: dict
) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Build interval and validation tables plus intervals keyed by attempt.

    Unavailable durations are null rather than NaN.

    Args:
        attempts: Attempt records with ``key``, ``attempt_id``, ``trial_ordinal``,
            ``attempt_number``, ``activity_label``, ``status`` and ``manifest``.
        events: Host-clock events decoded from ``events.jsonl``.
        trials: Protocol trials keyed by ordinal.

    Returns:
        Phase intervals, per-attempt validation checks, and the
        ``(start_ns, stop_ns)`` intervals of every phase keyed by attempt.
    """
    grouped = defaultdict(list)
    for event in events:
        if event.get("trial_ordinal") is not None and event.get("attempt") is not None:
            grouped[(int(event["trial_ordinal"]), int(event["attempt"]))].append(event)
    interval_rows, checks = [], []
    by_attempt = {}
    for record in attempts:
        manifest = record["manifest"]
        ordered = sorted(grouped[record["key"]], key=lambda item: item["monotonic_ns"])
        transitions = [item for item in ordered if item["kind"] == "phase_changed"]
        confirmations = [item for item in ordered if item["kind"] == "action_confirmed"]
        resolutions = [item for item in ordered if item["kind"] == "trial_resolved"]
        states = [item.get("state") for item in transitions]
        ranks = [PHASES.index(state) if state in PHASES else -1 for state in states]
        valid_order = (
            bool(states) and states[0] == "countdown" and ranks == sorted(set(ranks))
        )
        valid_order = valid_order and all(state in PHASES for state in states)
        end_ns = manifest.get("ended_monotonic_ns")
        if end_ns is None and resolutions:
            end_ns = resolutions[-1]["monotonic_ns"]
        trial = trials.get(record["trial_ordinal"])
        intervals, durations = {}, {}
        bounds_valid = True
        start_ns = manifest.get("started_monotonic_ns")
        for index, event in enumerate(transitions):
            phase = event.get("state")
            if phase not in PHASES:
                continue
            start = int(event["monotonic_ns"])
            stop = (
                transitions[index + 1]["monotonic_ns"]
                if index + 1 < len(transitions)
                else end_ns
            )
            stop = int(stop) if stop is not None else None
            bounded = stop is not None and stop >= start
            bounds_valid &= bounded and (start_ns is None or start >= start_ns)
            observed = (stop - start) / 1e9 if bounded else None
            planned = (
                float(getattr(trial.scenario, f"{phase}_seconds")) if trial else None
            )
            intervals[phase] = (start, stop)
            durations[phase] = observed
            interval_rows.append(
                {
                    "attempt_id": record["attempt_id"],
                    "trial_ordinal": record["trial_ordinal"],
                    "attempt_number": record["attempt_number"],
                    "activity_label": record["activity_label"],
                    "status": record["status"],
                    "phase": phase,
                    "phase_start_monotonic_ns": start,
                    "phase_end_monotonic_ns": stop,
                    "observed_seconds": observed,
                    "planned_seconds": planned,
                    "duration_delta_seconds": None
                    if observed is None or planned is None
                    else observed - planned,
                }
            )
        by_attempt[record["key"]] = intervals
        action = intervals.get("action")
        confirmation_in_action = None
        if confirmations:
            confirmation_in_action = bool(action) and all(
                action[0] <= event["monotonic_ns"]
                and (action[1] is None or event["monotonic_ns"] <= action[1])
                for event in confirmations
            )
        complete = states == list(PHASES)
        checks.append(
            {
                "attempt_id": record["attempt_id"],
                "trial_ordinal": record["trial_ordinal"],
                "activity_label": record["activity_label"],
                "status": record["status"],
                "phase_sequence": " → ".join(str(state) for state in states),
                "phase_order_valid": valid_order,
                "phase_bounds_valid": bounds_valid,
                "all_phases_present": complete,
                "completed_attempt_has_all_phases": complete
                if record["status"] in _COMPLETED
                else None,
                "action_confirmed_manifest": bool(
                    manifest.get("action_confirmed", False)
                ),
                "action_confirmed_event": bool(confirmations),
                "action_confirmation_matches": bool(
                    manifest.get("action_confirmed", False)
                )
                == bool(confirmations),
                "confirmation_occurs_during_action": confirmation_in_action,
                "trial_resolution_matches_status": resolutions[-1].get("disposition")
                == record["status"]
                if resolutions
                else None,
                **{f"{phase}_seconds": durations.get(phase) for phase in PHASES},
            }
        )
    return (
        pl.DataFrame(interval_rows, schema=INTERVAL_SCHEMA),
        pl.DataFrame(checks, schema=CHECK_SCHEMA),
        by_attempt,
    )
