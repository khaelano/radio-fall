"""Curated bundle export for the session inspector window."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from fall_detection.session import (
    SessionSource,
)

from ..exporter import ExportCancelled, export_curated_bundle, session_size
from ..formatting import _human_size


class ExportMixin:
    """Exports the reviewed session as a curated bundle.

    Mixin of :class:`SessionInspectorWindow`; it relies on the attributes
    the window initializes in its constructor.
    """

    @QtCore.Slot()
    def export_session(self) -> None:
        if self.session is None or self.review is None:
            return
        if self.is_dirty() and not self.save_review():
            return
        parent_text = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose export parent directory", str(self.session.path.parent)
        )
        if not parent_text:
            return
        default_name = f"{SessionSource(self.session.path).name}-curated"
        name, accepted = QtWidgets.QInputDialog.getText(
            self,
            "Curated bundle name",
            "New directory name:",
            text=default_name,
        )
        if not accepted or not name.strip():
            return
        if Path(name).name != name or name in {".", ".."}:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid name",
                "Enter one new directory name without separators.",
            )
            return
        destination = Path(parent_text) / name
        if destination.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Destination exists",
                f"The destination already exists:\n{destination}",
            )
            return
        total = session_size(self.session)
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Export curated bundle",
            f"Copy {_human_size(total)} to:\n{destination}\n\n"
            "All attempts, including excluded attempts, will be retained and flagged.",
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        progress_dialog = QtWidgets.QProgressDialog(
            "Preparing export…", "Cancel", 0, 1000, self
        )
        progress_dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)

        def update(copied: int, expected: int, relative: str) -> None:
            value = 1000 if expected == 0 else min(1000, int(copied * 1000 / expected))
            progress_dialog.setValue(value)
            progress_dialog.setLabelText(
                f"Copying {relative}\n{_human_size(copied)} / {_human_size(expected)}"
            )
            QtWidgets.QApplication.processEvents()

        try:
            export_curated_bundle(
                self.session,
                self.review,
                destination,
                progress=update,
                cancelled=progress_dialog.wasCanceled,
            )
        except ExportCancelled:
            self.statusBar().showMessage("Export cancelled", 5000)
            return
        except Exception as exc:  # noqa: BLE001 — application error boundary
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))
            return
        finally:
            progress_dialog.close()
        QtWidgets.QMessageBox.information(
            self, "Export complete", f"Curated bundle created at:\n{destination}"
        )
