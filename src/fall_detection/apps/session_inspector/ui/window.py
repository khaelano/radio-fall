"""Main window of the offline session inspector."""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from threading import Event
from typing import Any

from PySide6 import QtCore, QtWidgets

from fall_detection.session.models import RecordedAttempt, RecordedTrial, SessionBundle

from ..data import AttemptData
from ..review import LoadedReview, ReviewDocument, ReviewStore
from .window_attempt import AttemptMixin
from .window_export import ExportMixin
from .window_layout import LayoutMixin
from .window_loading import LoadingMixin
from .window_review import ReviewMixin
from .window_sessions import SessionsMixin


class SessionInspectorWindow(
    LayoutMixin,
    SessionsMixin,
    AttemptMixin,
    ReviewMixin,
    LoadingMixin,
    ExportMixin,
    QtWidgets.QMainWindow,
):
    """Main offline session browser and review editor.

    The behavior is split by concern into the ``window_*`` mixins; this class
    owns the shared state, the constructor, and shutdown.
    """

    def __init__(self, source_path: Path, annotations_dir: Path | None = None) -> None:
        super().__init__()
        self.source_path = source_path
        self.annotations_dir = annotations_dir
        self.sessions: tuple[SessionBundle, ...] = ()
        self.session: SessionBundle | None = None
        self.store: ReviewStore | None = None
        self.loaded_review: LoadedReview | None = None
        self.review: ReviewDocument | None = None
        self.review_writable = False
        self.baseline_state: dict[str, Any] | None = None
        self.current_attempt: RecordedAttempt | None = None
        self.current_trial: RecordedTrial | None = None
        self._loading_forms = False
        self._load_token = 0
        self._load_cancel: Event | None = None
        self._pending_receiver = ""
        self._current_data: AttemptData | None = None
        self._preparing_key: tuple[str, str, str] | None = None
        self._data_cache: OrderedDict[tuple[str, str, str], AttemptData] = OrderedDict()
        self._cache_limit = 4
        self._load_timer = QtCore.QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(140)
        self._load_timer.timeout.connect(self._dispatch_attempt_load)
        self.thread_pool = QtCore.QThreadPool(self)
        self.thread_pool.setMaxThreadCount(2)
        # Python's frame-to-record decoding is CPU-bound and can starve the
        # GUI event loop even from a QThread. A spawned process pool keeps
        # the interpreter work isolated without forking Qt state.
        self.process_pool = ProcessPoolExecutor(
            max_workers=2,
            mp_context=get_context("spawn"),
        )
        self._process_pool_closed = False

        self.setWindowTitle("Collection session inspector")
        self.resize(1480, 900)
        self._build_ui()
        self.refresh_sessions()

    def closeEvent(self, event: Any) -> None:
        if self.is_dirty() and not self._confirm_leave():
            event.ignore()
            return
        self._cancel_load()
        self.signals_tab.shutdown()
        if not self._process_pool_closed:
            self.process_pool.shutdown(wait=False, cancel_futures=True)
            self._process_pool_closed = True
        event.accept()
