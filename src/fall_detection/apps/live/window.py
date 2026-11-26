"""Main window of ``csi-live``: live CSI data, with model inference on demand.

The gateway serial port admits one reader, so the window runs one engine at a
time. With no model selected, :class:`~fall_detection.radio.live.LiveRadio`
feeds the CSI dashboard (amplitude, phase, I/Q, radio levels, CSI gaps and the
gateway transport panel). With one or more models selected, the native
detector owns the port, scores windows and shows the raw stream, previews and
calibration. Applying a new selection stops the running engine before the
next one starts.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from fall_detection.apps.common.dashboard import DEFAULT_VIEW_SECONDS
from fall_detection.apps.common.live import LiveDashboard
from fall_detection.apps.common.pacing import frame_interval_ms

from .detection import (
    DEFAULT_MODELS,
    MODELS,
    model_bundle_present,
)
from .detection_view import DetectionView

VIEW_OUTPUT_DIR = Path("data/experiments/viewer")
WINDOW_TITLE = "CSI live"
_ENGINE_ERRORS = (RuntimeError, ValueError, OSError, KeyError, TimeoutError)
_BADGE_STYLE = (
    "background: {color}; color: white; border-radius: 6px;"
    "padding: 3px 10px; font-weight: 700;"
)


def view_output_dir(args: Any) -> Path:
    """Directory receiving live-view transport journals (outside ``data/raw``)."""
    return args.output_dir or VIEW_OUTPUT_DIR


def selection_text(models: Sequence[str]) -> str:
    """Summarize a model selection for the toolbar button."""
    if not models:
        return "None — view live data"
    if len(models) == 1:
        return models[0]
    return f"{models[0]} +{len(models) - 1}"


def apply_text(running: tuple[str, ...] | None, pending: tuple[str, ...]) -> str:
    """Name what the Apply button will do for the pending selection."""
    if running is None:
        return "Start detection" if pending else "Start live view"
    if pending == running:
        return "Apply"
    if not pending:
        return "Switch to live view"
    if not running:
        return "Start detection"
    return "Restart with selection"


class LiveWindow:
    """Toolbar, engine lifecycle and the two pages of ``csi-live``.

    Args:
        args: Parsed ``csi-live`` arguments.
        radio_factory: Builds a :class:`LiveRadio` from ``args`` and keyword
            options; called for every live-view start.
        backend_factory: Builds a native detector from a configuration.
        build_config: Encodes a detector configuration for a model selection.
        inference_problem: Why inference cannot start on this machine, or
            None; when set, model choices are disabled with this explanation.
        source_text: Short description of the data source for the toolbar.
    """

    def __init__(
        self,
        args: Any,
        *,
        radio_factory: Callable[..., Any],
        backend_factory: Callable[[dict], Any],
        build_config: Callable[[Any, list[str]], dict],
        inference_problem: str | None,
        source_text: str,
    ) -> None:
        from PySide6 import QtCore, QtWidgets

        self.QtCore, self.QtWidgets = QtCore, QtWidgets
        self.args = args
        self._radio_factory = radio_factory
        self._build_config = build_config
        self._inference_problem = inference_problem
        self._replay = bool(getattr(args, "replay_capture", None))
        self.radio: Any = None
        self.dashboard: LiveDashboard | None = None
        self.running: tuple[str, ...] | None = None
        initial = tuple(args.models or ())
        if self._replay and not initial:
            initial = DEFAULT_MODELS
        self.pending: tuple[str, ...] = initial
        self._dashboard_options = {
            "dashboard_subcarriers": args.dashboard_subcarriers,
            "inspect_subcarrier": args.inspect_subcarrier,
            "window_seconds": DEFAULT_VIEW_SECONDS,
        }
        self._began = time.monotonic()

        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle(WINDOW_TITLE)
        self.window.resize(1400, 950)
        self._build_toolbar(source_text)

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(8, 4, 8, 4)
        self.banner = QtWidgets.QLabel()
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.banner.setStyleSheet(
            "background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;"
            "border-radius: 6px; padding: 6px 10px;"
        )
        self.banner.hide()
        layout.addWidget(self.banner)
        self.pages = QtWidgets.QStackedWidget()
        self.view_page = QtWidgets.QWidget()
        self.view_layout = QtWidgets.QVBoxLayout(self.view_page)
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_placeholder = QtWidgets.QLabel("Live view is not running.")
        self.view_placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.view_placeholder.setStyleSheet("color: palette(mid); font-size: 15px;")
        self.view_layout.addWidget(self.view_placeholder)
        self.detection = DetectionView(args, backend_factory=backend_factory)
        self.pages.addWidget(self.view_page)
        self.pages.addWidget(self.detection.widget)
        layout.addWidget(self.pages, 1)
        self.window.setCentralWidget(central)

        self.status_label = QtWidgets.QLabel("Starting…")
        self.status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.metrics_label = QtWidgets.QLabel("")
        status_bar = QtWidgets.QStatusBar()
        status_bar.addWidget(self.status_label, 1)
        status_bar.addPermanentWidget(self.metrics_label)
        self.window.setStatusBar(status_bar)

        self.timer = QtCore.QTimer(self.window)
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self._sync_menu()
        self._sync_controls()

    # -- construction --------------------------------------------------

    def _build_toolbar(self, source_text: str) -> None:
        QtCore, QtWidgets = self.QtCore, self.QtWidgets
        toolbar = QtWidgets.QToolBar("Live controls")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.window.addToolBar(toolbar)

        source = QtWidgets.QLabel(f"  Source: <b>{source_text}</b>  ")
        source.setToolTip(
            "Recorded captures replayed through the detector"
            if self._replay
            else "USB gateway from configs/radio.json (or --gateway-port)"
        )
        toolbar.addWidget(source)
        toolbar.addSeparator()
        toolbar.addWidget(QtWidgets.QLabel("  Model: "))
        self.model_button = QtWidgets.QToolButton()
        self.model_button.setPopupMode(
            QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.model_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly
        )
        self.model_button.setMinimumWidth(220)
        self.model_menu = _sticky_menu(QtWidgets, self.model_button)
        self.view_only_action = self.model_menu.addAction("None — view live data only")
        self.view_only_action.setCheckable(True)
        self.view_only_action.triggered.connect(self._view_only_triggered)
        if self._replay:
            self.view_only_action.setEnabled(False)
            self.view_only_action.setToolTip(
                "Replay runs through the detector; select at least one model"
            )
        self.model_menu.addSection("Detect falls with")
        self.model_actions: dict[str, Any] = {}
        for model in MODELS:
            label = f"{model}  (default)" if model in DEFAULT_MODELS else model
            action = self.model_menu.addAction(label)
            action.setCheckable(True)
            problem = self._inference_problem
            if problem is None and not model_bundle_present(
                self.args.model_root, model
            ):
                problem = f"no exported bundle under {self.args.model_root}"
            if problem:
                action.setEnabled(False)
                action.setToolTip(problem)
            action.triggered.connect(self._model_triggered)
            self.model_actions[model] = action
        self.model_menu.setToolTipsVisible(True)
        self.model_button.setMenu(self.model_menu)
        toolbar.addWidget(self.model_button)
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.setToolTip(
            "Stop the running engine and start the selected one; the gateway "
            "admits one reader at a time"
        )
        self.apply_button.clicked.connect(self.apply)
        toolbar.addWidget(self.apply_button)
        if self._inference_problem:
            hint = QtWidgets.QLabel("  inference unavailable")
            hint.setStyleSheet("color: #b45309;")
            hint.setToolTip(self._inference_problem)
            toolbar.addWidget(hint)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(spacer)
        self.mode_badge = QtWidgets.QLabel("STOPPED")
        toolbar.addWidget(self.mode_badge)

    # -- selection -----------------------------------------------------

    def _view_only_triggered(self, checked: bool) -> None:
        if checked:
            self.pending = ()
        elif not self.pending:
            # Something must stay selected; "none" is the live view itself.
            self.view_only_action.setChecked(True)
            return
        self._sync_menu()
        self._sync_controls()

    def _model_triggered(self, _checked: bool) -> None:
        self.pending = tuple(
            model for model, action in self.model_actions.items() if action.isChecked()
        )
        if not self.pending and self._replay:
            self.pending = DEFAULT_MODELS
        self._sync_menu()
        self._sync_controls()

    def set_selection(self, models: Sequence[str]) -> None:
        """Select ``models`` (empty for live view) without applying it."""
        self.pending = tuple(model for model in MODELS if model in models)
        self._sync_menu()
        self._sync_controls()

    def _sync_menu(self) -> None:
        for model, action in self.model_actions.items():
            blocked = action.blockSignals(True)
            action.setChecked(model in self.pending)
            action.blockSignals(blocked)
        blocked = self.view_only_action.blockSignals(True)
        self.view_only_action.setChecked(not self.pending)
        self.view_only_action.blockSignals(blocked)
        self.model_button.setText(selection_text(self.pending) + "  ▾")
        self.model_button.setToolTip(
            "Detect falls with: " + ", ".join(self.pending)
            if self.pending
            else "No model: live CSI dashboard only"
        )

    def _sync_controls(self) -> None:
        changed = self.running != self.pending
        self.apply_button.setEnabled(changed)
        self.apply_button.setText(apply_text(self.running, self.pending))
        self.apply_button.setDefault(changed)
        if self.running is None:
            text, color = "STOPPED", "#6b7280"
        elif not self.running:
            text, color = "LIVE VIEW", "#2563eb"
        else:
            count = len(self.running)
            text = f"DETECTING · {count} model{'s' if count > 1 else ''}"
            color = "#16a34a"
        self.mode_badge.setText(text)
        self.mode_badge.setStyleSheet(_BADGE_STYLE.format(color=color))

    # -- engines -------------------------------------------------------

    def start(self) -> None:
        """Start the initially selected engine and the display timer."""
        self.timer.start(frame_interval_ms(self.args.fps))
        self.apply()

    def apply(self) -> None:
        """Stop the running engine and start the one the selection names."""
        QtWidgets = self.QtWidgets
        target = self.pending
        QtWidgets.QApplication.setOverrideCursor(self.QtCore.Qt.CursorShape.WaitCursor)
        try:
            self._show_error(None)
            self._stop_engine()
            if target:
                self._start_detection(target)
            else:
                self._start_view()
        except _ENGINE_ERRORS as exc:
            self._show_error(str(exc))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self._sync_controls()

    def _start_view(self) -> None:
        self.pages.setCurrentWidget(self.view_page)
        self.status_label.setText("Starting radio…")
        radio = self._radio_factory(
            self.args, journal_root=lambda: view_output_dir(self.args)
        )
        dashboard = LiveDashboard(radio, fps=self.args.fps, **self._dashboard_options)
        self.view_placeholder.hide()
        self.view_layout.addWidget(dashboard.panel.widget)
        self.radio, self.dashboard = radio, dashboard
        try:
            radio.start()
        except BaseException:
            self._stop_view()
            raise
        self.running = ()

    def _stop_view(self) -> None:
        radio, dashboard = self.radio, self.dashboard
        self.radio = self.dashboard = None
        if dashboard is not None:
            panel = dashboard.panel
            self._dashboard_options = {
                "dashboard_subcarriers": int(panel.trace_count_combo.currentData()),
                "inspect_subcarrier": int(panel.inspect_combo.currentData()),
                "window_seconds": panel.window_seconds,
            }
            panel.widget.hide()
            self.view_layout.removeWidget(panel.widget)
            panel.widget.deleteLater()
        self.view_placeholder.show()
        if radio is not None:
            radio.stop()

    def _start_detection(self, models: tuple[str, ...]) -> None:
        self.pages.setCurrentWidget(self.detection.widget)
        self.status_label.setText("Starting detector…")
        self.metrics_label.setText("")
        config = self._build_config(self.args, list(models))
        self.detection.start(config)
        self.running = models
        self.metrics_label.setText(f"output {config['output_dir']}")
        self.metrics_label.setToolTip(
            "Detector run directory: predictions, calibration and journal"
        )

    def _stop_engine(self) -> None:
        running, self.running = self.running, None
        if running is None:
            # A failed start may have left partial resources.
            self.detection.stop()
            self._stop_view()
        elif running:
            self.detection.stop()
        else:
            self._stop_view()

    def _show_error(self, message: str | None) -> None:
        if message is None:
            self.banner.hide()
            return
        self.banner.setText(
            f"<b>Could not start:</b> {message}<br>"
            "Fix the cause, then press the button in the toolbar to retry."
        )
        self.banner.show()
        self.status_label.setText(message)

    # -- display -------------------------------------------------------

    def tick(self) -> None:
        """Advance the running engine's display by one frame."""
        try:
            if self.running == () and self.dashboard is not None:
                text = self.dashboard.refresh()
                self.status_label.setText(text.connection)
                self.status_label.setToolTip(text.detail)
                self.metrics_label.setText(text.compact)
                self.metrics_label.setToolTip(text.detail)
            elif self.running:
                self.status_label.setText(self.detection.tick())
        except _ENGINE_ERRORS as exc:
            self.status_label.setText(str(exc))
        duration = self.args.duration
        if duration is not None and time.monotonic() - self._began >= duration:
            self.window.close()

    def shutdown(self) -> None:
        """Stop the timer and the running engine; repeat calls are harmless."""
        self.timer.stop()
        try:
            self._stop_engine()
        finally:
            self.window.close()


def _sticky_menu(QtWidgets: Any, parent: Any) -> Any:
    """Return a menu that stays open while checkable entries are toggled."""

    class StickyMenu(QtWidgets.QMenu):
        def mouseReleaseEvent(self, event: Any) -> None:
            action = self.activeAction()
            if action is not None and action.isEnabled() and action.isCheckable():
                action.trigger()
                return
            super().mouseReleaseEvent(event)

    return StickyMenu(parent)
