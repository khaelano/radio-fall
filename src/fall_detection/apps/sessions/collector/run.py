"""One collection session inside the running ``csi-sessions`` application.

:meth:`CollectionRun.start` composes the recording worker, optional camera,
radio, controller and both collection windows, then starts acquisition.
Closing the operator window calls :meth:`CollectionRun.finish`, which ends the
attempt, drains the radio, flushes recording, closes the camera and windows,
and publishes the verified raw archive. Cleanup runs in reverse order of
construction and continues when an earlier step fails.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fall_detection.apps.common.dashboard import DEFAULT_VIEW_SECONDS
from fall_detection.apps.common.live import LiveDashboard
from fall_detection.apps.common.pacing import FPS_DEFAULT, frame_interval_ms
from fall_detection.collection.continuous import ContinuousController
from fall_detection.collection.controller import OperatorCommand, SessionController
from fall_detection.radio.recording_io import RecordingIO
from fall_detection.radio.settings import DEFAULT_CONFIG

from .plan import SessionPlan
from .runtime import CollectionPresenter, running_collection
from .views.operator import OperatorWindow
from .views.performer import PerformerWindow

DEFAULT_PROTOCOL = DEFAULT_CONFIG.parent / "collection/fall_simple.json"
COLLECTOR_VIEW_SECONDS = DEFAULT_VIEW_SECONDS
COLLECTOR_UI_INTERVAL_MS = frame_interval_ms(FPS_DEFAULT)


@dataclass(frozen=True)
class CollectionOutcome:
    """Result of a finished collection run.

    Attributes:
        session_root: Working session folder, or None when no session started.
        archive: Published raw archive, or None when none was written.
        error: Cleanup or archive failure written for the operator, or None.
    """

    session_root: Path | None
    archive: Path | None
    error: str | None = None


def _video_recorder(config: Any) -> Any:
    from fall_detection.collection.video import VideoRecorder

    return VideoRecorder(config)


def _finalize(root: Path) -> Path:
    from fall_detection.collection.archive import finalize_recording

    return finalize_recording(root)


class CollectionRun:
    """Compose, run and tear down one collection session.

    Args:
        plan: Protocol, metadata, output folder and camera of the session.
        options: Parsed ``csi-sessions`` arguments supplying the radio
            configuration and gateway port, ``recording_flush_seconds`` and
            ``fps``.
        on_finished: Receives the outcome once everything is closed.
        radio_factory: Builds the live radio; offline tests replace it.
        video_factory: Builds the camera recorder from a ``VideoConfig``.
        finalize: Publishes the raw archive of a drained session folder.
        run_blocking: Runs a slow callable while keeping the UI responsive;
            receives a label and the callable and returns its result.
    """

    def __init__(
        self,
        plan: SessionPlan,
        options: Any,
        *,
        on_finished: Callable[[CollectionOutcome], None],
        radio_factory: Callable[..., Any],
        video_factory: Callable[[Any], Any] = _video_recorder,
        finalize: Callable[[Path], Path] = _finalize,
        run_blocking: Callable[[str, Callable[[], Any]], Any] | None = None,
    ) -> None:
        self.plan = plan
        self.options = options
        self._on_finished = on_finished
        self._radio_factory = radio_factory
        self._video_factory = video_factory
        self._finalize = finalize
        self._run_blocking = run_blocking or (lambda _label, function: function())
        self._resources = ExitStack()
        self.controller: Any = None
        self.operator: OperatorWindow | None = None
        self.performer: PerformerWindow | None = None
        self.started = False
        self.finished = False

    # -- startup -------------------------------------------------------

    def start(self) -> None:
        """Open every input and window, then start acquisition.

        Raises:
            Exception: Any construction or startup failure, after everything
                already opened has been closed again.
        """
        try:
            self._compose()
        except BaseException as exc:
            self.finished = True
            try:
                self._resources.close()
            except Exception as cleanup:  # noqa: BLE001 — keep the startup error
                exc.add_note(f"cleanup after the failed start also failed: {cleanup}")
            raise
        self.started = True

    def _compose(self) -> None:
        from PySide6 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        plan, options, resources = self.plan, self.options, self._resources
        recording_io = RecordingIO(
            interval_s=options.recording_flush_seconds, compressed=True
        )
        resources.callback(recording_io.close)
        video = None
        if plan.video is not None:
            video = self._video_factory(plan.video)
            resources.callback(video.stop)
        radio = self._radio_factory(
            options,
            require_four=True,
            on_status=lambda message, connected: self.controller.record_event(
                "receiver_status", message=message, connected=connected
            ),
            journal_root=lambda: self.controller.session_root,
            on_interruption=lambda reason: self.controller.interrupt_radio(reason),
        )
        # Binding is hardware-free; the sinks above are first used after this.
        controller_type = ContinuousController if plan.continuous else SessionController
        self.controller = controller = controller_type(
            plan.protocol,
            plan.output_dir,
            environment={
                **radio.environment(),
                "video": video.config.metadata() if video else None,
                "csv_sidecars": False,
                "recording_io": {
                    "flush_interval_s": options.recording_flush_seconds,
                    "compression": "zstd" if recording_io.compressed else "none",
                    "capacity_bytes": recording_io.capacity_bytes,
                },
            },
            telemetry_provider=lambda: radio.telemetry_snapshot(),
            video_recorder=video,
            recording_io=recording_io,
            manual_confirmation_required=not plan.continuous,
        )
        profile = radio.settings.profile
        dashboard = LiveDashboard(
            radio, fps=options.fps, window_seconds=COLLECTOR_VIEW_SECONDS
        )

        def dispatch(command: OperatorCommand) -> None:
            try:
                controller.dispatch(command)
            except (RuntimeError, ValueError) as exc:
                QtWidgets.QMessageBox.warning(
                    operator.window, "Collection command unavailable", str(exc)
                )

        operator = OperatorWindow(
            QtCore,
            QtWidgets,
            protocol=plan.protocol,
            profile_text=(
                f"profile {profile.profile_id} · {profile.band} ch {profile.channel}"
                f" · fp {radio.settings.profile_fingerprint}"
            ),
            panel=dashboard.panel,
            on_command=dispatch,
            video_enabled=video is not None,
            continuous=plan.continuous,
            on_edit_protocol=None if plan.continuous else self.edit_protocol,
        )
        self.operator = operator
        resources.callback(operator.window.close)
        performer = PerformerWindow(QtCore, QtWidgets, plan.protocol)
        self.performer = performer
        resources.callback(performer.window.close)
        performer.place(app.screens())
        presenter = CollectionPresenter(
            controller,
            radio,
            dashboard,
            operator=operator,
            performer=performer,
            output_dir=plan.output_dir,
            video=video,
        )
        timer = QtCore.QTimer(operator.window)
        timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        timer.setInterval(frame_interval_ms(options.fps))
        timer.timeout.connect(presenter.refresh)
        resources.callback(timer.stop)

        # Closing the operator console ends the session, even while the
        # performer guidance stays open on the second display.
        def close_operator(event: Any) -> None:
            event.accept()
            QtCore.QTimer.singleShot(0, self.finish)

        operator.window.closeEvent = close_operator
        resources.enter_context(
            running_collection(
                controller,
                radio,
                plan.metadata,
                video=video,
                resume_session=plan.resume.root if plan.resume else None,
            )
        )
        timer.start()
        operator.window.show()
        operator.window.raise_()

    # -- protocol revisions --------------------------------------------

    def edit_protocol(self) -> bool:
        """Let the operator revise the trials not recorded yet.

        Returns:
            Whether a revision was saved.
        """
        from PySide6 import QtCore, QtWidgets

        from .views.protocol_editor import ProtocolEditorDialog

        controller, operator = self.controller, self.operator
        if controller is None or operator is None or not controller.can_revise_protocol:
            return False
        sources = [
            ("This session's starting protocol", self.session_root / "protocol.json")
        ]
        if self.plan.protocol_path is not None:
            sources.append(("Set up from", self.plan.protocol_path))
        editor = ProtocolEditorDialog(
            QtCore,
            QtWidgets,
            controller.protocol,
            locked=controller.protocol_locked_trials,
            revision=controller.protocol_revisions + 1,
            protocol_dir=DEFAULT_PROTOCOL.parent,
            sources=sources,
            session_id=controller.session_id,
            parent=operator.window,
        )
        edit = editor.get()
        if edit is None:
            return False
        try:
            controller.revise_protocol(
                edit.protocol, note=edit.note, changes=edit.changes
            )
        except (RuntimeError, ValueError, OSError) as exc:
            QtWidgets.QMessageBox.warning(
                operator.window, "Protocol not changed", str(exc)
            )
            return False
        operator.set_protocol(controller.protocol)
        return True

    # -- shutdown ------------------------------------------------------

    @property
    def session_root(self) -> Path | None:
        """Working session folder once the session has started."""
        controller = self.controller
        if controller is None or getattr(controller, "_store", None) is None:
            return None
        return controller.session_root

    def finish(self) -> CollectionOutcome | None:
        """End the session, close everything and publish the raw archive.

        Repeat calls do nothing and return None.

        Returns:
            The outcome also passed to ``on_finished``.
        """
        if self.finished:
            return None
        self.finished = True
        errors = []
        try:
            self._resources.close()
        except Exception as exc:  # noqa: BLE001 — report and still archive
            errors.append(f"cleanup failed: {exc}")
        root = self.session_root
        archive = None
        if root is not None:
            try:
                archive = self._run_blocking(
                    f"Saving raw recording from {root.name}…",
                    lambda: self._finalize(root),
                )
            except Exception as exc:  # noqa: BLE001 — keep the working session
                errors.append(
                    f"raw archive finalization failed; working session retained: {exc}"
                )
        outcome = CollectionOutcome(
            session_root=root,
            archive=archive,
            error="; ".join(errors) or None,
        )
        self._on_finished(outcome)
        return outcome


def run_with_progress(parent: Any, label: str, function: Callable[[], Any]) -> Any:
    """Run ``function`` on a thread behind a modal busy dialog.

    Args:
        parent: Parent widget of the dialog, or None.
        label: Text shown while waiting.
        function: Work to run; its exception is re-raised here.

    Returns:
        The function's result.
    """
    from PySide6 import QtCore, QtWidgets

    dialog = QtWidgets.QProgressDialog(label, None, 0, 0, parent)
    dialog.setWindowTitle("Please wait")
    dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
    dialog.setMinimumDuration(0)
    dialog.setCancelButton(None)
    dialog.show()
    result: dict[str, Any] = {}

    def work() -> None:
        try:
            result["value"] = function()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the GUI thread
            result["error"] = exc

    thread = threading.Thread(target=work, name="csi-sessions-work", daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50
            )
            thread.join(0.05)
    finally:
        dialog.close()
        dialog.deleteLater()
    if "error" in result:
        raise result["error"]
    return result.get("value")
