"""Background workers that load attempt data outside the GUI thread."""

from __future__ import annotations

from concurrent.futures import Executor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Event

from PySide6 import QtCore

from fall_detection.session import (
    RecordedAttempt,
)

from ..data import (
    load_attempt_data_for_ui,
)


class WorkerSignals(QtCore.QObject):
    completed = QtCore.Signal(int, object)
    failed = QtCore.Signal(int, str)


class AttemptLoadWorker(QtCore.QRunnable):
    """Load one receiver outside the GUI thread."""

    def __init__(
        self,
        token: int,
        attempt: RecordedAttempt,
        receiver_id: str,
        cancelled: Event,
        executor: Executor,
        *,
        prepare_signals: bool,
    ) -> None:
        super().__init__()
        self.token = token
        self.attempt = attempt
        self.receiver_id = receiver_id
        self.cancelled = cancelled
        self.executor = executor
        self.prepare_signals = prepare_signals
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            if self.cancelled.is_set():
                return
            future = self.executor.submit(
                load_attempt_data_for_ui,
                self.attempt,
                self.receiver_id,
                prepare_signals=self.prepare_signals,
            )
            while True:
                if self.cancelled.is_set():
                    future.cancel()
                    return
                try:
                    data = future.result(timeout=0.05)
                    break
                except FutureTimeoutError:
                    continue
        except Exception as exc:  # noqa: BLE001 — keep worker exceptions inside the UI boundary
            self.signals.failed.emit(self.token, str(exc))
            return
        self.signals.completed.emit(self.token, data)


class SignalPrepareWorker(QtCore.QRunnable):
    """Prepare downsampled plot matrices outside the GUI thread."""

    def __init__(
        self,
        token: int,
        attempt: RecordedAttempt,
        receiver_id: str,
        cancelled: Event,
        executor: Executor,
    ) -> None:
        super().__init__()
        self.token = token
        self.attempt = attempt
        self.receiver_id = receiver_id
        self.cancelled = cancelled
        self.executor = executor
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            if self.cancelled.is_set():
                return
            future = self.executor.submit(
                load_attempt_data_for_ui,
                self.attempt,
                self.receiver_id,
                prepare_signals=True,
            )
            while True:
                if self.cancelled.is_set():
                    future.cancel()
                    return
                try:
                    data = future.result(timeout=0.05)
                    break
                except FutureTimeoutError:
                    continue
        except Exception as exc:  # noqa: BLE001 — application error boundary
            self.signals.failed.emit(self.token, str(exc))
            return
        self.signals.completed.emit(self.token, data)
