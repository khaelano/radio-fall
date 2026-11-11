"""Segmented unattended collection using the ordinary attempt artifact format."""

from __future__ import annotations

from typing import Any

from .controller import OperatorCommand, SessionController, SessionState
from .protocol import protocol_from_mapping


def continuous_protocol(segment_seconds: float, segments: int):
    """Create a bounded queue of non-fall activity segments."""
    return protocol_from_mapping(
        {
            "schema_version": 1,
            "protocol_id": "continuous-activity-v1",
            "title": "Continuous activity recording",
            "defaults": {
                "countdown_seconds": 0,
                "action_seconds": segment_seconds,
                "recovery_seconds": 0,
            },
            "blocks": [
                {
                    "id": "continuous",
                    "title": "Continuous activity",
                    "scenarios": [
                        {
                            "id": "activity",
                            "activity_label": "non_fall",
                            "title": "Non-fall segment",
                            "instruction": "Continue normal non-fall activities.",
                            "repetitions": segments,
                        }
                    ],
                }
            ],
        }
    )


class ContinuousController(SessionController):
    """Automatically record, finalize, and restart timed segments.

    Pauses between capture intervals are journaled. Interrupted partial attempts
    remain invalid and are retried under a new attempt number.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._gap_start: int | None = None

    def dispatch(self, command: OperatorCommand):
        if command is not OperatorCommand.END_SESSION:
            raise RuntimeError(
                "continuous recording is automatic; use End Session to stop"
            )
        return super().dispatch(command)

    def _open_gap(self, reason: str) -> None:
        if self._gap_start is None and self._store is not None:
            self._gap_start = self._monotonic_ns()
            self._store.event("continuous_gap_started", self._gap_start, reason=reason)

    def _finish_capture_locked(self, status: str, now: float, **updates: Any) -> None:
        was_recording = self._capture is not None
        super()._finish_capture_locked(status, now, **updates)
        if was_recording and status in {"pending_review", "invalid"}:
            self._open_gap("segment ended or input interrupted")

    def tick(self, now: float | None = None):
        super().tick(now)
        with self._lock:
            if self._state is SessionState.REVIEW:
                self._open_gap("segment ended or input interrupted")
                if self._attempt_status == "invalid":
                    self._retry_locked()
                elif self._attempt_status == "pending_review":
                    if (
                        self._last_capture is not None
                        and self._last_capture.writes_complete
                    ):
                        self._accept_locked()
            if self._state is SessionState.READY:
                self._open_gap("waiting for ready inputs or next segment")
                if self._health_ready_locked():
                    self._start_trial_locked()
                    if self._state is SessionState.COUNTDOWN:
                        start = self._capture_start_ns
                        self._store.event(
                            "continuous_gap_ended",
                            start,
                            started_monotonic_ns=self._gap_start,
                        )
                        self._gap_start = None
                        current = self._clock() if now is None else now
                        self._change_phase_locked(SessionState.ACTION, current)
                        self._phase_deadline = (
                            current + self._current_scenario.action_seconds
                        )
            return self._notify_locked()
