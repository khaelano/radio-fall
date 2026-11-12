"""Compose the collection command, radio, controller and Qt windows."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

from fall_detection.apps.collector.runtime import (
    CollectionPresenter,
    running_collection,
)
from fall_detection.apps.collector.views.dialogs import MetadataDialog, choose_protocol
from fall_detection.apps.collector.views.operator import OperatorWindow
from fall_detection.apps.collector.views.performer import PerformerWindow
from fall_detection.collection.continuous import (
    ContinuousController,
    continuous_protocol,
)
from fall_detection.collection.controller import OperatorCommand, SessionController
from fall_detection.collection.protocol import (
    ProtocolError,
    load_protocol,
    select_blocks,
)
from fall_detection.collection.resume import load_session_resume
from fall_detection.presentation.radio.dashboard import DEFAULT_VIEW_SECONDS
from fall_detection.presentation.radio.live import LiveDashboard
from fall_detection.presentation.radio.pacing import (
    FPS_CHOICES as COLLECTOR_FPS_CHOICES,
)
from fall_detection.presentation.radio.pacing import (
    FPS_DEFAULT as COLLECTOR_FPS_DEFAULT,
)
from fall_detection.presentation.radio.pacing import (
    frame_interval_ms,
)
from fall_detection.radio.acquisition.recording_io import RecordingIO
from fall_detection.radio.live import LiveRadio, add_live_arguments
from fall_detection.radio.settings import DEFAULT_CONFIG

DEFAULT_PROTOCOL = DEFAULT_CONFIG.parent / "collection/fall_simple.json"
COLLECTOR_VIEW_SECONDS = DEFAULT_VIEW_SECONDS
COLLECTOR_UI_INTERVAL_MS = frame_interval_ms(COLLECTOR_FPS_DEFAULT)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guide and record operator-confirmed ESP-NOW gateway radio collection trials."
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        help="scenario protocol JSON; omit to choose a file at startup",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="automatically record activity in segments",
    )
    parser.add_argument(
        "--segment-seconds",
        type=float,
        default=300,
        help="continuous segment duration (default: 300 s)",
    )
    parser.add_argument(
        "--segments",
        type=int,
        default=288,
        help="maximum number of segments (default: 288)",
    )
    add_live_arguments(parser)
    parser.add_argument(
        "--manual-confirmation",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="require operator confirmation during ACTION before recovery",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw/sessions"))
    parser.add_argument(
        "--recording-flush-seconds",
        type=float,
        default=5,
        help="interval between background recording writes (default: 5 s)",
    )
    parser.add_argument(
        "--resume-session",
        type=Path,
        help="resume a saved session directory using its protocol and remaining trials",
    )
    parser.add_argument(
        "--video-device",
        help="DroidCam USB virtual webcam, e.g. /dev/video2; omit for CSI only",
    )
    parser.add_argument("--video-width", type=int, default=1280)
    parser.add_argument("--video-height", type=int, default=720)
    parser.add_argument(
        "--video-fps",
        type=int,
        default=30,
        help="requested camera/encoder frame rate, independent of UI refresh",
    )
    parser.add_argument(
        "--fps",
        type=int,
        choices=COLLECTOR_FPS_CHOICES,
        default=COLLECTOR_FPS_DEFAULT,
        help="constant UI refresh rate in frames per second",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the collection console with guaranteed input cleanup on exit."""
    parser = _parser()
    args = parser.parse_args(argv)
    with ExitStack() as resources:
        result = _run(args, parser, resources)
    controller = getattr(args, "_archive_controller", None)
    if controller is not None and controller._store is not None:
        from fall_detection.collection.archive import finalize_recording

        print(f"Saving raw recording from {controller.session_root}...", flush=True)
        try:
            archive = finalize_recording(controller.session_root)
        except Exception as exc:  # noqa: BLE001 — application error boundary
            print(
                f"Raw archive finalization failed; working session retained: {exc}",
                file=sys.stderr,
            )
            return 1
        print(f"Saved raw recording: {archive}")
    return result


def _run(
    args: argparse.Namespace, parser: argparse.ArgumentParser, resources: ExitStack
) -> int:
    protocol = None
    saved = None
    if args.continuous and args.protocol is not None:
        parser.error("--continuous cannot be combined with --protocol")
    if args.continuous and args.video_device:
        parser.error("continuous mode currently supports CSI only")
    if args.continuous and args.resume_session is None:
        try:
            protocol = continuous_protocol(args.segment_seconds, args.segments)
        except ProtocolError as exc:
            parser.error(str(exc))
    if args.resume_session is not None:
        if args.protocol is not None:
            parser.error("--resume-session uses the saved protocol; omit --protocol")
        try:
            saved = load_session_resume(args.resume_session)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f"cannot resume session: {exc}")
        protocol = saved.protocol
        is_continuous = protocol.protocol_id == "continuous-activity-v1"
        if args.continuous and not is_continuous:
            parser.error("saved session is not a continuous session")
        args.continuous = is_continuous
        if args.continuous and args.video_device:
            parser.error("continuous mode currently supports CSI only")
        args.output_dir = saved.root.parent
        previous_video = saved.manifest.get("environment", {}).get("video")
        if previous_video and args.video_device is None:
            args.video_device = previous_video["device"]
            args.video_width = previous_video["width"]
            args.video_height = previous_video["height"]
            args.video_fps = previous_video["fps"]
    if args.protocol is not None:
        try:
            protocol = load_protocol(args.protocol)
        except ProtocolError as exc:
            parser.error(str(exc))

    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError as exc:
        print(
            "Install collection dependencies with: uv sync --extra radio",
            file=sys.stderr,
        )
        print(f"Missing GUI dependency: {exc}", file=sys.stderr)
        return 2

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(list(sys.argv))
    if protocol is None:
        protocol = choose_protocol(QtWidgets, DEFAULT_PROTOCOL)
        if protocol is None:
            return 0

    try:
        recording_io = RecordingIO(
            interval_s=args.recording_flush_seconds,
            compressed=True,
        )
    except ValueError as exc:
        parser.error(str(exc))
    resources.callback(recording_io.close)

    video = None
    if args.video_device:
        from fall_detection.collection.video import VideoConfig, VideoRecorder

        try:
            video = VideoRecorder(
                VideoConfig(
                    args.video_device,
                    args.video_width,
                    args.video_height,
                    args.video_fps,
                )
            )
        except (RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        resources.callback(video.stop)
    try:
        radio = LiveRadio(
            args,
            require_four=True,
            on_status=lambda message, connected: controller.record_event(
                "receiver_status",
                message=message,
                connected=connected,
            ),
            record_sink=lambda record, arrival_ns: controller.write_radio(
                record, arrival_ns
            ),
            journal_root=lambda: controller.session_root,
            on_interruption=lambda reason: controller.interrupt_radio(reason),
            recording_io=recording_io,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    if saved is not None:
        metadata = saved.metadata
    else:
        dialog = MetadataDialog(QtWidgets, protocol, continuous=args.continuous)
        metadata = dialog.get()
        if metadata is None:
            return 0
        try:
            protocol = select_blocks(protocol, dialog.block_ids())
        except ProtocolError as exc:
            parser.error(str(exc))
    # Binding is hardware-free; these sinks are first used after controller creation.
    controller = (ContinuousController if args.continuous else SessionController)(
        protocol,
        args.output_dir,
        environment={
            **radio.environment(),
            "video": video.config.metadata() if video else None,
            "recording_io": {
                "flush_interval_s": args.recording_flush_seconds,
                "compression": "zstd" if recording_io.compressed else "none",
                "capacity_bytes": recording_io.capacity_bytes,
            },
        },
        telemetry_provider=lambda: radio.manager.telemetry_snapshot(),
        video_recorder=video,
        recording_io=recording_io,
        manual_confirmation_required=not args.continuous,
    )
    args._archive_controller = controller
    profile = radio.settings.profile
    dashboard = LiveDashboard(
        radio, fps=args.fps, window_seconds=COLLECTOR_VIEW_SECONDS
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
        protocol=protocol,
        profile_text=f"profile {profile.profile_id} · {profile.band} ch {profile.channel}"
        f" · fp {radio.settings.profile_fingerprint}",
        panel=dashboard.panel,
        on_command=dispatch,
        video_enabled=video is not None,
        continuous=args.continuous,
    )
    resources.callback(operator.window.close)
    performer = PerformerWindow(QtCore, QtWidgets, protocol)
    resources.callback(performer.window.close)
    performer.place(app.screens())
    presenter = CollectionPresenter(
        controller,
        radio,
        dashboard,
        operator=operator,
        performer=performer,
        output_dir=args.output_dir,
        video=video,
    )
    timer = QtCore.QTimer(operator.window)
    timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
    timer.setInterval(frame_interval_ms(args.fps))
    timer.timeout.connect(presenter.refresh)
    app.aboutToQuit.connect(timer.stop)
    resources.callback(timer.stop)

    # Closing the operator console must also end collection when guidance is open.
    def close_operator(event: object) -> None:
        event.accept()
        app.quit()

    operator.window.closeEvent = close_operator
    with running_collection(
        controller, radio, metadata, video=video, resume_session=args.resume_session
    ):
        timer.start()
        operator.window.show()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
