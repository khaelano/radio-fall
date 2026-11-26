"""Command line of ``csi-sessions``: record new sessions and review existing ones.

The window lists the sessions in ``--sessions-dir``. **New session** records
one with the collection console; selecting a session opens it for review,
signal inspection and curated export. Collection options on the command line
only preselect values in the setup form, except ``--resume-session``, which
starts recording at once.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

from fall_detection.apps.common.pacing import add_fps_argument
from fall_detection.apps.common.qt import QtUnavailableError, qt_application
from fall_detection.radio.live import LiveRadio
from fall_detection.radio.settings import add_live_arguments, resolve_settings

DEFAULT_SESSIONS_DIR = Path("data/raw/sessions")
DEFAULT_ANNOTATIONS_DIR = Path("data/annotations")
EXAMPLES = """\
examples:
  csi-sessions                          browse data/raw/sessions; record from the toolbar
  csi-sessions --new                    open the New session form right away
  csi-sessions --new --video-device /dev/video2
                                        preselect a DroidCam camera
  csi-sessions --resume-session data/raw/sessions/<id>
                                        continue an unfinished session folder
  csi-sessions data/raw/sessions/<id>.zip
                                        open one session or archive for review
"""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="csi-sessions",
        description="Record new fall-detection sessions and review existing ones.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "session",
        nargs="?",
        type=Path,
        help="optional individual session folder or archive to open",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=DEFAULT_SESSIONS_DIR,
        help="folder listed in the browser and receiving new sessions",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=DEFAULT_ANNOTATIONS_DIR,
        help="folder where reviews are saved, one subfolder per session id",
    )
    record = parser.add_argument_group("recording")
    record.add_argument(
        "--new",
        action="store_true",
        help="open the New session form at startup",
    )
    record.add_argument(
        "--resume-session",
        type=Path,
        metavar="SESSION_DIR",
        help="resume recording this saved session folder at startup",
    )
    record.add_argument(
        "--protocol",
        type=Path,
        help="scenario protocol JSON preselected in the setup form",
    )
    record.add_argument(
        "--continuous",
        action="store_true",
        help="preselect continuous activity recording in segments",
    )
    record.add_argument(
        "--segment-seconds",
        type=float,
        default=300,
        help="continuous segment duration (default: 300 s)",
    )
    record.add_argument(
        "--segments",
        type=int,
        default=288,
        help="maximum number of continuous segments (default: 288)",
    )
    record.add_argument(
        "--video-device",
        help="DroidCam USB virtual webcam preselected, e.g. /dev/video2",
    )
    record.add_argument("--video-width", type=int, default=1280)
    record.add_argument("--video-height", type=int, default=720)
    record.add_argument(
        "--video-fps",
        type=int,
        default=30,
        help="requested camera/encoder frame rate, independent of UI refresh",
    )
    record.add_argument(
        "--recording-flush-seconds",
        type=float,
        default=5,
        help="interval between background recording writes (default: 5 s)",
    )
    add_fps_argument(record)
    add_live_arguments(parser)
    return parser


def _radio_text(args: argparse.Namespace) -> str:
    """Describe the radio setup for the setup form without opening hardware."""
    try:
        settings = resolve_settings(args)
    except (OSError, ValueError) as exc:
        return f"configuration problem: {exc}"
    profile = settings.profile
    port = args.gateway_port or "no gateway port configured"
    return (
        f"{profile.profile_id} · {profile.band} ch {profile.channel} · "
        f"{len(settings.inventory.receivers)} receivers · gateway {port}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the session browser and collection console."""

    parser = _parser()
    args = parser.parse_args(argv)
    if args.continuous and args.protocol is not None:
        parser.error("--continuous cannot be combined with --protocol")
    if args.continuous and args.video_device:
        parser.error("continuous mode currently supports CSI only")
    if args.resume_session is not None and (args.protocol or args.continuous):
        parser.error("--resume-session uses the saved protocol and mode")
    if args.resume_session is not None and args.new:
        parser.error("choose either --new or --resume-session")
    try:
        # The window modules import Qt at module level, so import them only
        # after confirming that the optional dependencies are present.
        import pyqtgraph as pg

        application = qt_application("csi-sessions")
    except (ImportError, QtUnavailableError):
        print(
            "PySide6 and pyqtgraph are required; install with: uv sync --extra radio",
            file=sys.stderr,
        )
        return 2
    from PySide6 import QtCore

    from .window import SessionsWindow

    pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")
    source = args.session if args.session is not None else args.sessions_dir
    window = SessionsWindow(
        source,
        args.annotations_dir,
        options=args,
        sessions_dir=args.sessions_dir,
        radio_factory=LiveRadio,
        radio_text=_radio_text(args),
    )
    with ExitStack() as resources:
        resources.callback(window.finish_collection)
        window.show()
        if args.resume_session is not None:
            QtCore.QTimer.singleShot(
                0, lambda: window.resume_session(args.resume_session)
            )
        elif args.new:
            QtCore.QTimer.singleShot(0, window.new_session)
        return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
