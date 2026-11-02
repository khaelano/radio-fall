"""Deep session-orchestration module for synchronized collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import time
from threading import RLock
from typing import Any, Callable, Protocol

from ..radio.acquisition.clock_sync import ClockSyncEstimate, ClockSyncSample
from ..radio.acquisition.protocol import CsiRecord
from ..radio.acquisition.telemetry import (
    BackhaulTelemetrySnapshot,
    telemetry_delta,
)
from .capture import SessionArtifactStore, SessionMetadata, TrialCapture
from .protocol import CollectionProtocol, Trial


class SessionState(str, Enum):
    """Externally visible collection states."""

    SETUP = "setup"
    READY = "ready"
    COUNTDOWN = "countdown"
    ACTION = "action"
    RECOVERY = "recovery"
    REVIEW = "review"
    COMPLETE = "complete"


class OperatorCommand(str, Enum):
    """Commands accepted by :class:`SessionController`."""

    START_TRIAL = "start_trial"
    CONFIRM_ACTION = "confirm_action"
    ABORT = "abort"
    ACCEPT = "accept"
    RETRY = "retry"
    SKIP = "skip"
    END_SESSION = "end_session"


@dataclass(frozen=True)
class HealthSnapshot:
    """Current input and storage readiness reported by adapters."""

    radio_live: bool = False
    storage_ready: bool = True
    clock_sync_ready: bool = True
    radio_detail: str = "waiting for radio"
    storage_detail: str = "ready"

    @property
    def ready(self) -> bool:
        """Return whether a new trial can safely be started."""

        return self.radio_live and self.storage_ready and self.clock_sync_ready


@dataclass(frozen=True)
class SessionSnapshot:
    """Immutable view model shared by both GUI windows."""

    state: SessionState
    session_id: str | None
    trial: Trial | None
    trial_index: int
    total_trials: int
    attempt_number: int
    phase_remaining_seconds: float
    health: HealthSnapshot
    message: str
    attempt_status: str | None
    action_confirmed: bool = False

    @property
    def progress_text(self) -> str:
        """Return a compact human-readable queue position."""

        if self.trial is None:
            return "complete"
        return f"{self.trial.ordinal}/{self.total_trials}"


class CaptureSink(Protocol):
    """Callback seam used by the radio adapter."""

    def write_radio(
        self, record: CsiRecord, host_receive_monotonic_ns: int
    ) -> None: ...

    def write_clock_sync(
        self,
        sample: ClockSyncSample,
        estimate: ClockSyncEstimate,
        host_receive_monotonic_ns: int,
    ) -> None: ...


class SessionController:
    """Own protocol progression, quality gates, and trial artifact lifecycle.

    Adapters only call the three ``write_*`` methods and ``update_health``;
    windows only dispatch commands and render snapshots. The controller's
    implementation hides file naming, phase timing, retries, and interruption
    semantics behind that small interface.
    """

    def __init__(
        self,
        protocol: CollectionProtocol,
        output_dir: Path,
        *,
        clock: Callable[[], float] = time.monotonic,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        session_id_factory: Callable[[], str] | None = None,
        environment: dict[str, Any] | None = None,
        telemetry_provider: Callable[[], BackhaulTelemetrySnapshot | None]
        | None = None,
        manual_confirmation_required: bool = False,
    ) -> None:
        self.protocol = protocol
        self.output_dir = output_dir
        self._clock = clock
        self._monotonic_ns = monotonic_ns
        self._session_id_factory = session_id_factory or self._default_session_id
        self._environment = environment or {}
        self._telemetry_provider = telemetry_provider
        self._manual_confirmation_required = manual_confirmation_required
        self._lock = RLock()
        self._subscribers: list[Callable[[SessionSnapshot], None]] = []
        self._store: SessionArtifactStore | None = None
        self._capture: TrialCapture | None = None
        self._last_capture: TrialCapture | None = None
        self._capture_start_ns = 0
        self._draining_captures: list[tuple[TrialCapture, int, int, int]] = []
        self._state = SessionState.SETUP
        self._session_id: str | None = None
        self._trial_index = 0
        self._attempt_numbers: dict[int, int] = {}
        self._attempt_number = 0
        self._phase_deadline = 0.0
        self._health = HealthSnapshot()
        self._message = "enter session metadata"
        self._attempt_status: str | None = None
        self._action_confirmed = False
        self._action_confirmed_monotonic_ns: int | None = None
        self._attempt_telemetry_start: BackhaulTelemetrySnapshot | None = None

    @staticmethod
    def _default_session_id() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    @property
    def state(self) -> SessionState:
        """Return the current state."""

        with self._lock:
            return self._state

    @property
    def capture_sink(self) -> CaptureSink:
        """Return the adapter callback seam."""

        return self

    @property
    def session_root(self) -> Path:
        """Return the active session directory for additive transport journals."""
        if self._store is None:
            raise RuntimeError("session has not started")
        return self._store.root

    def flush_radio(self) -> None:
        """Close deferred writers after the transport has finished draining."""
        with self._lock:
            self._expire_draining_locked(self._monotonic_ns(), force=True)

    def _expire_draining_locked(self, now_ns: int, *, force: bool = False) -> None:
        remaining = []
        for capture, start, end, deadline in self._draining_captures:
            if force or now_ns >= deadline:
                capture.close_streams()
            else:
                remaining.append((capture, start, end, deadline))
        self._draining_captures = remaining

    def update_environment(self, values: dict[str, Any]) -> None:
        """Add runtime bindings before the session manifest is created."""

        with self._lock:
            if self._state is not SessionState.SETUP:
                raise RuntimeError("session environment is already published")
            self._environment.update(values)

    def record_event(self, kind: str, **data: Any) -> None:
        """Append an adapter event to the session log when one is open."""

        with self._lock:
            if self._store is not None:
                self._store.event(kind, self._monotonic_ns(), **data)

    def subscribe(self, callback: Callable[[SessionSnapshot], None]) -> None:
        """Subscribe to snapshots; callbacks are invoked after transitions."""

        with self._lock:
            self._subscribers.append(callback)
            snapshot = self._snapshot_locked()
        callback(snapshot)

    def start_session(self, metadata: SessionMetadata) -> SessionSnapshot:
        """Create a session manifest and move into ``READY``."""

        if not metadata.participant_id.strip():
            raise ValueError("participant_id is required")
        with self._lock:
            if self._state is not SessionState.SETUP:
                raise RuntimeError("session has already started")
            base_session_id = self._session_id_factory()
            session_id = base_session_id
            for suffix in range(100):
                try:
                    self._store = SessionArtifactStore(
                        self.output_dir,
                        self.protocol,
                        metadata,
                        session_id,
                        self._environment,
                    )
                    break
                except FileExistsError:
                    session_id = f"{base_session_id}-{suffix + 1}"
            else:
                raise RuntimeError("unable to create a unique session directory")
            self._session_id = session_id
            self._state = SessionState.READY
            self._message = "ready to start the first trial"
            self._store.event("session_started", self._monotonic_ns())
            return self._notify_locked()

    def dispatch(self, command: OperatorCommand) -> SessionSnapshot:
        """Apply one operator command and return the resulting snapshot."""

        with self._lock:
            if command is OperatorCommand.START_TRIAL:
                self._start_trial_locked()
            elif command is OperatorCommand.CONFIRM_ACTION:
                self._confirm_action_locked()
            elif command is OperatorCommand.ABORT:
                self._abort_locked("operator aborted attempt")
            elif command is OperatorCommand.ACCEPT:
                self._accept_locked()
            elif command is OperatorCommand.RETRY:
                self._retry_locked()
            elif command is OperatorCommand.SKIP:
                self._skip_locked()
            elif command is OperatorCommand.END_SESSION:
                self._end_session_locked("operator ended session")
            else:
                raise ValueError(f"unsupported command: {command}")
            return self._notify_locked()

    def tick(self, now: float | None = None) -> SessionSnapshot:
        """Advance timed phases using an injected monotonic clock."""

        with self._lock:
            self._expire_draining_locked(self._monotonic_ns())
            current = self._clock() if now is None else now
            if (
                self._state is SessionState.COUNTDOWN
                and current >= self._phase_deadline
            ):
                self._change_phase_locked(SessionState.ACTION, current)
                self._phase_deadline = current + self._current_scenario.action_seconds
            if self._state is SessionState.ACTION and current >= self._phase_deadline:
                if self._manual_confirmation_required and not self._action_confirmed:
                    self._finish_capture_locked(
                        "invalid",
                        current,
                        invalid_reason="action was not confirmed before timeout",
                    )
                    self._state = SessionState.REVIEW
                    self._attempt_status = "invalid"
                    self._phase_deadline = current
                    self._message = (
                        "action was not confirmed; retry or skip this attempt"
                    )
                    return self._notify_locked()
                self._change_phase_locked(SessionState.RECOVERY, current)
                self._phase_deadline = current + self._current_scenario.recovery_seconds
            if self._state is SessionState.RECOVERY and current >= self._phase_deadline:
                self._enter_review_locked(current)
            return self._notify_locked()

    def update_health(self, health: HealthSnapshot) -> SessionSnapshot:
        """Publish adapter health and interrupt active trials on failure."""

        with self._lock:
            self._health = health
            if self._state in (
                SessionState.COUNTDOWN,
                SessionState.ACTION,
                SessionState.RECOVERY,
            ) and not self._health_ready_locked(health):
                self._abort_locked("input health lost: " + self._health_detail(health))
        return self._notify_locked()

    def _health_ready_locked(self, health: HealthSnapshot | None = None) -> bool:
        """Return whether radio, storage, and clock are all ready."""

        value = health or self._health
        return value.radio_live and value.storage_ready and value.clock_sync_ready

    @staticmethod
    def _health_detail(health: HealthSnapshot) -> str:
        for ready, detail in (
            (health.radio_live, health.radio_detail),
            (health.storage_ready, health.storage_detail),
        ):
            if not ready:
                return detail
        if not health.clock_sync_ready:
            return "clock synchronization is not ready"
        return "unknown readiness failure"

    def write_radio(self, record: CsiRecord, host_receive_monotonic_ns: int) -> None:
        """Receive radio data from an adapter and write it if a trial is active."""

        with self._lock:
            if record.run_id is None:
                if self._capture is not None:
                    self._capture.write_radio(record, host_receive_monotonic_ns)
                return
            # BLE attribution uses capture time. Unaligned or very late data
            # remains in the session journal rather than another attempt.
            captured = record.capture_host_monotonic_ns
            if captured is None:
                return
            self._expire_draining_locked(host_receive_monotonic_ns)
            if self._capture is not None and captured >= self._capture_start_ns:
                self._capture.write_radio(record, host_receive_monotonic_ns)
                return
            for capture, start, end, deadline in self._draining_captures:
                if start <= captured < end and host_receive_monotonic_ns < deadline:
                    capture.write_radio(record, host_receive_monotonic_ns)
                    return

    def write_clock_sync(
        self,
        sample: ClockSyncSample,
        estimate: ClockSyncEstimate,
        host_receive_monotonic_ns: int,
    ) -> None:
        """Receive clock samples from an ESP-NOW adapter."""

        with self._lock:
            if self._capture is not None:
                self._capture.write_clock_sync(
                    sample, estimate, host_receive_monotonic_ns
                )

    @property
    def _current_trial(self) -> Trial | None:
        if 0 <= self._trial_index < len(self.protocol.trials):
            return self.protocol.trials[self._trial_index]
        return None

    @property
    def _current_scenario(self):
        trial = self._current_trial
        if trial is None:
            raise RuntimeError("no current trial")
        return trial.scenario

    def _start_trial_locked(self) -> None:
        if self._state is not SessionState.READY:
            raise RuntimeError(f"cannot start a trial from {self._state.value}")
        if self._current_trial is None:
            self._complete_locked("all protocol trials are complete")
            return
        if not self._health_ready_locked():
            raise RuntimeError("radio, storage, and clock health must be ready")
        assert self._store is not None
        now = self._clock()
        trial = self._current_trial
        attempt = self._attempt_numbers.get(trial.ordinal, 0) + 1
        self._attempt_numbers[trial.ordinal] = attempt
        self._attempt_number = attempt
        telemetry_start = (
            self._telemetry_provider() if self._telemetry_provider is not None else None
        )
        self._capture_start_ns = self._monotonic_ns()
        self._capture = self._store.begin_attempt(
            trial,
            attempt,
            self._capture_start_ns,
            extra_metadata={
                "radio_telemetry_start": (
                    telemetry_start.to_dict() if telemetry_start is not None else None
                )
            },
        )
        self._attempt_telemetry_start = telemetry_start
        self._attempt_status = "recording"
        self._action_confirmed = False
        self._action_confirmed_monotonic_ns = None
        self._state = SessionState.COUNTDOWN
        self._phase_deadline = now + trial.scenario.countdown_seconds
        self._message = trial.scenario.instruction
        self._store.event(
            "phase_changed",
            self._monotonic_ns(),
            state=self._state.value,
            trial_ordinal=trial.ordinal,
            attempt=attempt,
        )

    def _change_phase_locked(
        self,
        state: SessionState,
        now: float,
        *,
        message: str | None = None,
    ) -> None:
        self._state = state
        self._message = message or self._current_scenario.instruction
        if self._store is not None:
            self._store.event(
                "phase_changed",
                self._monotonic_ns(),
                state=state.value,
                trial_ordinal=self._current_trial.ordinal
                if self._current_trial
                else None,
                attempt=self._attempt_number,
            )

    def _enter_review_locked(self, now: float) -> None:
        self._state = SessionState.REVIEW
        self._phase_deadline = now
        self._message = "trial complete; choose accept, retry, or skip"
        self._finish_capture_locked("pending_review", now)

    def _confirm_action_locked(self) -> None:
        """Record operator confirmation and begin the recovery interval."""

        if self._state is not SessionState.ACTION:
            raise RuntimeError("action confirmation is only available during ACTION")
        if self._action_confirmed:
            raise RuntimeError("action has already been confirmed")
        self._action_confirmed = True
        now = self._clock()
        self._action_confirmed_monotonic_ns = self._monotonic_ns()
        if self._store is not None and self._current_trial is not None:
            self._store.event(
                "action_confirmed",
                self._monotonic_ns(),
                trial_ordinal=self._current_trial.ordinal,
                attempt=self._attempt_number,
                activity_label=self._current_trial.scenario.activity_label,
            )
        self._change_phase_locked(
            SessionState.RECOVERY,
            now,
            message="action confirmed; remain still for recovery",
        )
        self._phase_deadline = now + self._current_scenario.recovery_seconds

    def _abort_locked(self, reason: str) -> None:
        if self._state in (
            SessionState.COUNTDOWN,
            SessionState.ACTION,
            SessionState.RECOVERY,
        ):
            now = self._clock()
            self._finish_capture_locked("invalid", now, interruption_reason=reason)
            self._state = SessionState.REVIEW
            self._attempt_status = "invalid"
            self._phase_deadline = now
            self._message = reason + "; retry or skip this attempt"
            return
        if self._state is SessionState.REVIEW:
            self._message = reason
            return
        raise RuntimeError(f"cannot abort from {self._state.value}")

    def _accept_locked(self) -> None:
        if self._state is not SessionState.REVIEW:
            raise RuntimeError("accept is only available during review")
        if self._attempt_status == "invalid":
            raise RuntimeError("an invalid attempt cannot be accepted")
        self._finish_capture_locked("accepted", self._clock())
        self._advance_locked("accepted")

    def _retry_locked(self) -> None:
        if self._state is not SessionState.REVIEW:
            raise RuntimeError("retry is only available during review")
        if self._attempt_status not in ("invalid", "pending_review"):
            raise RuntimeError("there is no retryable attempt")
        if self._attempt_status == "pending_review":
            self._finish_capture_locked("rejected", self._clock())
        self._state = SessionState.READY
        self._message = "ready to retry the current trial"
        self._attempt_status = None
        self._action_confirmed = False
        self._action_confirmed_monotonic_ns = None

    def _skip_locked(self) -> None:
        if self._state not in (SessionState.READY, SessionState.REVIEW):
            raise RuntimeError("skip is only available before or after a trial")
        if (
            self._state is SessionState.REVIEW
            and self._attempt_status == "pending_review"
        ):
            self._finish_capture_locked("skipped", self._clock())
        self._advance_locked("skipped")

    def _advance_locked(self, disposition: str) -> None:
        if self._store is not None and self._current_trial is not None:
            self._store.event(
                "trial_resolved",
                self._monotonic_ns(),
                trial_ordinal=self._current_trial.ordinal,
                attempt=self._attempt_number,
                disposition=disposition,
            )
        self._trial_index += 1
        self._attempt_number = 0
        self._attempt_status = None
        self._action_confirmed = False
        self._action_confirmed_monotonic_ns = None
        if self._trial_index >= len(self.protocol.trials):
            self._complete_locked("protocol complete")
        else:
            self._state = SessionState.READY
            self._message = "ready for the next trial"

    def _complete_locked(self, message: str) -> None:
        self._state = SessionState.COMPLETE
        self._message = message
        if self._store is not None:
            self._store.finish(
                "complete",
                self._monotonic_ns(),
                completed_trials=min(self._trial_index, len(self.protocol.trials)),
            )

    def _end_session_locked(self, reason: str) -> None:
        if self._state is SessionState.COMPLETE:
            return
        if self._state in (
            SessionState.COUNTDOWN,
            SessionState.ACTION,
            SessionState.RECOVERY,
        ):
            self._finish_capture_locked(
                "incomplete", self._clock(), interruption_reason=reason
            )
        elif (
            self._state is SessionState.REVIEW
            and self._attempt_status == "pending_review"
        ):
            self._finish_capture_locked(
                "incomplete", self._clock(), interruption_reason=reason
            )
        self._state = SessionState.COMPLETE
        self._message = reason
        if self._store is not None:
            self._store.finish(
                "ended",
                self._monotonic_ns(),
                completed_trials=self._trial_index,
            )

    def _finish_capture_locked(self, status: str, now: float, **updates: Any) -> None:
        updates.setdefault("action_confirmed", self._action_confirmed)
        updates.setdefault(
            "action_confirmed_monotonic_ns", self._action_confirmed_monotonic_ns
        )
        if self._current_trial is not None:
            updates.setdefault(
                "planned_reference_label",
                self._current_trial.scenario.activity_label,
            )
        if status == "accepted" and self._manual_confirmation_required:
            updates["reference_truth"] = (
                self._action_confirmed
                and self._action_confirmed_monotonic_ns is not None
            )
            updates["reference_truth_label"] = (
                self._current_trial.scenario.activity_label
                if updates["reference_truth"] and self._current_trial is not None
                else None
            )
        if self._capture is None:
            if (
                self._last_capture is not None
                and self._attempt_status == "pending_review"
            ):
                if self._environment.get("transport") not in {"ble", "espnow_gateway"}:
                    updates["ended_monotonic_ns"] = self._monotonic_ns()
                self._last_capture.update_status(status, **updates)
            self._attempt_status = status
            return
        capture = self._capture
        telemetry_end = (
            self._telemetry_provider() if self._telemetry_provider is not None else None
        )
        if self._telemetry_provider is not None:
            updates.setdefault(
                "radio_telemetry_end",
                telemetry_end.to_dict() if telemetry_end is not None else None,
            )
            updates.setdefault(
                "radio_telemetry_delta",
                telemetry_delta(self._attempt_telemetry_start, telemetry_end),
            )
        ended_ns = self._monotonic_ns()
        deferred = self._environment.get("transport") in {"ble", "espnow_gateway"}
        capture.finish(
            status, defer_close=deferred, ended_monotonic_ns=ended_ns, **updates
        )
        if deferred:
            drain_ms = self._environment.get("gateway_transport" if self._environment.get("transport") == "espnow_gateway" else "ble_transport", {}).get("drain_ms", 1000)
            self._draining_captures.append(
                (
                    capture,
                    self._capture_start_ns,
                    ended_ns,
                    ended_ns + drain_ms * 1_000_000,
                )
            )
        self._last_capture = capture
        self._capture = None
        self._attempt_telemetry_start = None
        self._attempt_status = status

    def _notify_locked(self) -> SessionSnapshot:
        snapshot = self._snapshot_locked()
        for callback in tuple(self._subscribers):
            callback(snapshot)
        return snapshot

    def _snapshot_locked(self) -> SessionSnapshot:
        remaining = 0.0
        if self._state in (
            SessionState.COUNTDOWN,
            SessionState.ACTION,
            SessionState.RECOVERY,
        ):
            remaining = max(0.0, self._phase_deadline - self._clock())
        return SessionSnapshot(
            state=self._state,
            session_id=self._session_id,
            trial=self._current_trial,
            trial_index=self._trial_index,
            total_trials=len(self.protocol.trials),
            attempt_number=self._attempt_number,
            phase_remaining_seconds=remaining,
            health=self._health,
            message=self._message,
            attempt_status=self._attempt_status,
            action_confirmed=self._action_confirmed,
        )
