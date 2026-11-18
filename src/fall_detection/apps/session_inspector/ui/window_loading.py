"""Asynchronous attempt loading for the session inspector window."""

from __future__ import annotations

from threading import Event

from PySide6 import QtCore

from fall_detection.session.models import RecordedAttempt

from ..data import AttemptData
from .workers import AttemptLoadWorker, SignalPrepareWorker


class LoadingMixin:
    """Debounces, dispatches, caches, and applies background attempt loads.

    Mixin of :class:`SessionInspectorWindow`; it relies on the attributes
    the window initializes in its constructor.
    """

    @QtCore.Slot(str)
    def _receiver_changed(self, receiver_id: str) -> None:
        if not self._loading_forms and receiver_id:
            self._schedule_attempt_load(receiver_id)

    def _cancel_load(self) -> None:
        # A completed worker signal may already be queued when cancellation
        # is requested. Advancing the token also makes that queued result
        # stale, preventing an old scenario from replacing the new one.
        self._load_token += 1
        self._load_timer.stop()
        if self._load_cancel is not None:
            self._load_cancel.set()
        self._load_cancel = None
        self._preparing_key = None

    def _cache_key(
        self,
        attempt: RecordedAttempt,
        receiver_id: str,
    ) -> tuple[str, str, str]:
        session_path = self.session.path.as_posix() if self.session else ""
        return session_path, attempt.key, receiver_id

    def _cache_put(
        self,
        key: tuple[str, str, str],
        data: AttemptData,
    ) -> None:
        self._data_cache[key] = data
        self._data_cache.move_to_end(key)
        while len(self._data_cache) > self._cache_limit:
            self._data_cache.popitem(last=False)

    def _schedule_attempt_load(self, receiver_id: str) -> None:
        if self.current_attempt is None or not receiver_id:
            return
        self._cancel_load()
        self._pending_receiver = receiver_id
        self._current_data = None
        if self.detail_tabs.currentWidget() is self.signals_tab:
            self.signals_tab.clear(f"Waiting to load {receiver_id}…")
        if self.detail_tabs.currentWidget() is self.values_tab:
            self.values_tab.clear(f"Waiting to load {receiver_id}…")
        self._load_timer.start()

    @QtCore.Slot()
    def _dispatch_attempt_load(self) -> None:
        if self.current_attempt is None or not self._pending_receiver:
            return
        receiver_id = self._pending_receiver
        key = self._cache_key(self.current_attempt, receiver_id)
        cached = self._data_cache.get(key)
        if cached is not None:
            self._data_cache.move_to_end(key)
            self._current_data = cached
            self._apply_visible_data()
            return
        token = self._load_token
        cancellation = Event()
        self._load_cancel = cancellation
        if self.detail_tabs.currentWidget() is self.signals_tab:
            self.signals_tab.clear(f"Loading {receiver_id}…")
        if self.detail_tabs.currentWidget() is self.values_tab:
            self.values_tab.clear(f"Loading {receiver_id}…")
        worker = AttemptLoadWorker(
            token,
            self.current_attempt,
            receiver_id,
            cancellation,
            self.process_pool,
            prepare_signals=(self.detail_tabs.currentWidget() is self.signals_tab),
        )
        worker.signals.completed.connect(self._attempt_data_loaded)
        worker.signals.failed.connect(self._attempt_data_failed)
        self.thread_pool.start(worker)

    def _ensure_signals(self) -> None:
        data = self._current_data
        if data is None or data.prepared_frame is not None:
            if data is not None:
                self.signals_tab.set_data(data)
            return
        key = (
            self.session.path.as_posix() if self.session else "",
            data.attempt_key,
            data.receiver_id,
        )
        if self._preparing_key == key:
            return
        if self._load_cancel is not None:
            self._load_cancel.set()
        cancellation = Event()
        self._load_cancel = cancellation
        self._preparing_key = key
        self.signals_tab.clear("Preparing downsampled signal plots…")
        worker = SignalPrepareWorker(
            self._load_token,
            self.current_attempt,
            data.receiver_id,
            cancellation,
            self.process_pool,
        )
        worker.signals.completed.connect(self._attempt_data_loaded)
        worker.signals.failed.connect(self._attempt_data_failed)
        self.thread_pool.start(worker, -1)

    def _apply_visible_data(self) -> None:
        data = self._current_data
        if data is None:
            return
        current_tab = self.detail_tabs.currentWidget()
        if current_tab is self.values_tab:
            current = self.values_tab.data
            if (
                current is None
                or current.attempt_key != data.attempt_key
                or current.receiver_id != data.receiver_id
            ):
                self.values_tab.set_data(data)
        elif current_tab is self.signals_tab:
            if data.prepared_frame is None:
                self._ensure_signals()
            elif self.signals_tab.data is not data:
                self.signals_tab.set_data(data)

    @QtCore.Slot(int)
    def _detail_tab_changed(self, _index: int) -> None:
        self._apply_visible_data()

    @QtCore.Slot(int, object)
    def _attempt_data_loaded(self, token: int, data: AttemptData) -> None:
        if token != self._load_token:
            return
        self._load_cancel = None
        self._preparing_key = None
        key = (
            self.session.path.as_posix() if self.session else "",
            data.attempt_key,
            data.receiver_id,
        )
        self._cache_put(key, data)
        self._current_data = data
        self._apply_visible_data()
        self.statusBar().showMessage(
            f"Loaded {data.record_count} CSI records for {data.receiver_id}", 5000
        )

    @QtCore.Slot(int, str)
    def _attempt_data_failed(self, token: int, message: str) -> None:
        if token != self._load_token:
            return
        self._load_cancel = None
        self._preparing_key = None
        self.signals_tab.clear("Unable to load signal")
        self.values_tab.clear(message)
        self.statusBar().showMessage(message)
