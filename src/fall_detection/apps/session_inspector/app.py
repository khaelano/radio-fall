"""Standalone PySide6 application for offline session review and curation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from fall_detection.apps.common.qt import QtUnavailableError, qt_application

from .formatting import REVIEW_FILE  # noqa: F401 - re-exported for callers

DEFAULT_SESSIONS_DIR = Path("data/raw/sessions")
DEFAULT_ANNOTATIONS_DIR = Path("data/annotations")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and curate recorded fall-detection sessions."
    )
    parser.add_argument(
        "session",
        nargs="?",
        type=Path,
        help="optional individual session directory or archive to open",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=DEFAULT_SESSIONS_DIR,
        help="directory containing session directories and archives",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=DEFAULT_ANNOTATIONS_DIR,
        help="directory where reviews are saved, one folder per session id",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the offline collection session inspector."""

    args = _parser().parse_args(argv)
    try:
        # The GUI modules import Qt at module level, so import them only after
        # confirming that the optional dependencies are present.
        import pyqtgraph as pg

        application = qt_application("session inspector")
    except (ImportError, QtUnavailableError):
        print(
            "PySide6 and pyqtgraph are required; install with: uv sync --extra radio",
            file=sys.stderr,
        )
        return 2
    from .ui.window import SessionInspectorWindow

    source = args.session if args.session is not None else args.sessions_dir
    pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")
    window = SessionInspectorWindow(source, args.annotations_dir)
    window.show()
    return application.exec()
