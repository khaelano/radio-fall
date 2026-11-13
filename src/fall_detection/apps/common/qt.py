"""Qt application bootstrap shared by the desktop applications."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


class QtUnavailableError(ImportError):
    """The optional Qt dependency group is not installed."""


def qt_application(name: str) -> QApplication:
    """Return the running ``QApplication`` or create one.

    Args:
        name: Application label used in the installation hint, e.g. ``"viewer"``.

    Returns:
        The existing application instance, or a new one built from ``sys.argv``.

    Raises:
        QtUnavailableError: PySide6 cannot be imported. The message names the
            ``uv sync --extra radio`` fix and the underlying import failure.
    """
    try:
        from PySide6 import QtWidgets
    except ImportError as exc:
        raise QtUnavailableError(
            f"Install {name} dependencies with: uv sync --extra radio "
            f"(missing GUI dependency: {exc})"
        ) from exc
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication(list(sys.argv))
