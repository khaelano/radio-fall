"""Main window of ``csi-sessions``: browse, review and record sessions.

The window is the session inspector with a toolbar for recording. **New
session** opens one setup form and starts the collection console; **Resume
recording** continues the selected unfinished session folder. While a session
records, the browser hides so the operator works in one console. When the
operator closes the console, the raw archive is published and the browser
returns with the new session selected.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from fall_detection.collection.resume import load_session_resume
from fall_detection.collection.video import VideoConfig
from fall_detection.session.models import SessionBundle

from .collector.plan import SessionPlan, resume_plan
from .collector.run import (
    DEFAULT_PROTOCOL,
    CollectionOutcome,
    CollectionRun,
    run_with_progress,
)
from .collector.views.dialogs import NewSessionDialog
from .inspector.ui.window import SessionInspectorWindow

WINDOW_TITLE = "CSI sessions"


def is_single_session(path: Path) -> bool:
    """Whether ``path`` is one session folder or archive, not a sessions folder."""
    return (path / "session.json").is_file() or (
        path.is_file() and path.suffix == ".zip"
    )


def resume_blocker(session: SessionBundle | None) -> str | None:
    """Explain why ``session`` cannot be resumed, or return None if it may be.

    This is a quick manifest check for the toolbar; resuming validates the
    saved progress in full.
    """
    if session is None:
        return "Select a session to resume"
    if not session.path.is_dir():
        return "Archives are read-only; resume the session folder instead"
    if session.status.lower() == "complete":
        return "This session is complete"
    return None


class SessionsWindow(SessionInspectorWindow):
    """Session inspector plus the collection workflow.

    Args:
        source_path: Sessions folder, or one session folder or archive, to list.
        annotations_dir: Directory receiving review overlays.
        options: Parsed ``csi-sessions`` arguments (collection defaults, radio
            configuration and display pacing).
        sessions_dir: Directory receiving new sessions.
        radio_factory: Builds the live radio for a collection run.
        radio_text: Description of the radio setup shown in the setup form.
    """

    def __init__(
        self,
        source_path: Path,
        annotations_dir: Path | None,
        *,
        options: Any,
        sessions_dir: Path,
        radio_factory: Callable[..., Any],
        radio_text: str = "",
    ) -> None:
        self.options = options
        self.sessions_dir = sessions_dir
        self._radio_factory = radio_factory
        self._radio_text = radio_text
        self.collection: CollectionRun | None = None
        self.last_outcome: CollectionOutcome | None = None
        self._quit_on_last_window: bool | None = None
        self._shutting_down = False
        super().__init__(source_path, annotations_dir)
        self.setWindowTitle(WINDOW_TITLE)
        self._build_toolbar()
        self._update_resume_action()
        self._show_empty_hint()

    # -- construction --------------------------------------------------

    def _build_toolbar(self) -> None:
        toolbar = QtWidgets.QToolBar("Sessions")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        self.new_action = QtGui.QAction("● New session…", self)
        self.new_action.setShortcut(QtGui.QKeySequence.StandardKey.New)
        self.new_action.setToolTip(
            "Set up and record a new collection session (Ctrl+N)"
        )
        self.new_action.triggered.connect(self.new_session)
        toolbar.addAction(self.new_action)
        button = toolbar.widgetForAction(self.new_action)
        if button is not None:
            button.setStyleSheet("font-weight: 700; color: #b91c1c;")
        self.resume_action = QtGui.QAction("▶ Resume recording", self)
        self.resume_action.triggered.connect(self.resume_selected)
        toolbar.addAction(self.resume_action)
        toolbar.addSeparator()
        open_action = QtGui.QAction("Open folder…", self)
        open_action.setToolTip("Browse sessions in another folder")
        open_action.triggered.connect(self._choose_folder)
        toolbar.addAction(open_action)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        toolbar.addWidget(spacer)
        self.folder_label = QtWidgets.QLabel()
        self.folder_label.setStyleSheet("color: palette(mid);")
        toolbar.addWidget(self.folder_label)
        self._update_folder_label()

    def _update_folder_label(self) -> None:
        self.folder_label.setText(f"Browsing {self.source_path}  ")
        self.folder_label.setToolTip(f"New sessions are saved to {self.sessions_dir}")

    # -- inspector hooks -----------------------------------------------

    @QtCore.Slot()
    def refresh_sessions(self) -> None:
        if self.source_path.exists():
            super().refresh_sessions()
        elif self._leave_review():
            # A missing sessions folder is empty; the first recording creates it.
            self.sessions = ()
            self._populate_session_list()
            self.statusBar().showMessage(
                f"{self.source_path} does not exist yet; recording creates it", 8000
            )
        if hasattr(self, "resume_action"):
            self._show_empty_hint()
            self._update_resume_action()

    def _open_session(self, session: SessionBundle) -> None:
        super()._open_session(session)
        self._update_resume_action()

    def _show_empty_hint(self) -> None:
        if not self.sessions and self.session is None:
            self.session_title.setText(
                "No sessions yet — press “New session” to record one"
            )

    def _update_resume_action(self) -> None:
        if not hasattr(self, "resume_action"):
            return  # The inspector opens its first session before the toolbar exists.
        blocker = resume_blocker(self.session)
        self.resume_action.setEnabled(blocker is None and self.collection is None)
        self.resume_action.setToolTip(
            blocker or "Continue this session at its first unresolved trial"
        )

    def _leave_review(self) -> bool:
        """Settle unsaved review edits; return False when the operator cancels."""
        if not self.is_dirty():
            return True
        if not self._confirm_leave():
            return False
        if self.is_dirty():  # "Discard": drop the edits so nobody asks again.
            self.discard_review()
        return True

    def _choose_folder(self) -> None:
        if not self._leave_review():
            return
        start = (
            self.sessions_dir
            if is_single_session(self.source_path)
            else self.source_path
        )
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Browse sessions in", str(start)
        )
        if not folder:
            return
        self.source_path = Path(folder)
        self.session = None
        self._update_folder_label()
        self.refresh_sessions()

    # -- recording -----------------------------------------------------

    @QtCore.Slot()
    def new_session(self) -> None:
        """Ask for the session setup and start recording it."""
        if self.collection is not None or not self._leave_review():
            return
        options = self.options
        dialog = NewSessionDialog(
            QtWidgets,
            protocol_path=options.protocol or DEFAULT_PROTOCOL,
            output_dir=self.sessions_dir,
            continuous=options.continuous,
            segment_seconds=options.segment_seconds,
            segments=options.segments,
            video_device=options.video_device,
            video_size=(options.video_width, options.video_height, options.video_fps),
            radio_text=self._radio_text,
            parent=self,
        )
        plan = dialog.get()
        if plan is not None:
            self.start_collection(plan)

    @QtCore.Slot()
    def resume_selected(self) -> None:
        """Continue the selected session folder at its first unresolved trial."""
        if self.session is None or self.collection is not None:
            return
        if not self._leave_review():
            return
        self.resume_session(self.session.path, confirm=True)

    def resume_session(self, path: Path, *, confirm: bool = False) -> None:
        """Validate saved progress in ``path`` and resume recording it.

        Args:
            path: Session folder written by an earlier collection.
            confirm: Ask the operator before starting.
        """
        try:
            saved = load_session_resume(path)
            options = self.options
            video = (
                VideoConfig(
                    options.video_device,
                    options.video_width,
                    options.video_height,
                    options.video_fps,
                )
                if options.video_device
                else None
            )
            plan = resume_plan(saved, video)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QtWidgets.QMessageBox.warning(
                self, "This session cannot be resumed", str(exc)
            )
            return
        if confirm:
            total = len(saved.protocol.trials)
            trial = saved.protocol.trials[saved.trial_index]
            answer = QtWidgets.QMessageBox.question(
                self,
                "Resume recording",
                f"Resume session {saved.root.name} for participant "
                f"{saved.metadata.participant_id}?\n\n"
                f"{saved.trial_index} of {total} trials are resolved. Recording "
                f"continues at trial {trial.ordinal}: {trial.scenario.title}.",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.Cancel,
                QtWidgets.QMessageBox.StandardButton.Yes,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self.start_collection(plan)

    def start_collection(self, plan: SessionPlan) -> bool:
        """Open the collection console for ``plan`` and hide the browser.

        Returns:
            Whether recording started; failures are reported in a dialog.
        """
        if self.collection is not None:
            return False
        app = QtWidgets.QApplication.instance()
        run = CollectionRun(
            plan,
            self.options,
            on_finished=self._collection_finished,
            radio_factory=self._radio_factory,
            run_blocking=lambda label, function: run_with_progress(
                None, label, function
            ),
        )
        # Closing the console must return here, not quit the application.
        self._quit_on_last_window = app.quitOnLastWindowClosed()
        app.setQuitOnLastWindowClosed(False)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            run.start()
        except Exception as exc:  # noqa: BLE001 — report and stay in the browser
            QtWidgets.QApplication.restoreOverrideCursor()
            self._restore_quit_policy()
            self.show()
            notes = "\n".join(getattr(exc, "__notes__", ()))
            QtWidgets.QMessageBox.critical(
                self,
                "Recording could not start",
                f"{exc}\n{notes}".strip()
                + "\n\nCheck the radio with `csi-radio`, then try again.",
            )
            self.refresh_sessions()
            return False
        QtWidgets.QApplication.restoreOverrideCursor()
        self.collection = run
        self._update_resume_action()
        self.hide()
        return True

    def _restore_quit_policy(self) -> None:
        if self._quit_on_last_window is not None:
            QtWidgets.QApplication.instance().setQuitOnLastWindowClosed(
                self._quit_on_last_window
            )
            self._quit_on_last_window = None

    def _collection_finished(self, outcome: CollectionOutcome) -> None:
        run, self.collection = self.collection, None
        self.last_outcome = outcome
        if self._shutting_down:
            self._restore_quit_policy()
            if outcome.error:
                print(f"csi-sessions: {outcome.error}", file=sys.stderr)
            return
        if run is not None and is_single_session(self.source_path):
            # A single opened session would hide the new one.
            self.source_path = run.plan.output_dir
            self._update_folder_label()
        self.show()
        self.raise_()
        self.activateWindow()
        self.refresh_sessions()
        target = outcome.archive or outcome.session_root
        if target is not None:
            self.select_session(target)
        self._restore_quit_policy()
        self._update_resume_action()
        if outcome.error:
            QtWidgets.QMessageBox.warning(
                self, "Session saved with problems", outcome.error
            )
        elif outcome.archive is not None:
            self.statusBar().showMessage(f"Saved raw recording {outcome.archive}")

    def select_session(self, path: Path) -> bool:
        """Select the listed session at ``path``; return whether it was found."""
        wanted = Path(path).resolve().as_posix()
        for row in range(self.session_list.count()):
            item = self.session_list.item(row)
            if item.data(QtCore.Qt.ItemDataRole.UserRole) == wanted:
                self.session_list.setCurrentItem(item)
                return True
        return False

    def finish_collection(self) -> None:
        """End a running collection because the application is quitting."""
        if self.collection is not None:
            self._shutting_down = True
            self.collection.finish()

    def closeEvent(self, event: Any) -> None:
        self.finish_collection()
        super().closeEvent(event)
