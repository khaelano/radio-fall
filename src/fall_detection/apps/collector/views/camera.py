"""Camera viewfinder with aspect-preserving display and explicit health state."""

from __future__ import annotations

from typing import Any

from fall_detection.collection.video import VideoPreviewFrame


class CameraPreview:
    """Display the latest camera image without owning or reading a camera device."""

    def __init__(self, QtCore: Any, QtWidgets: Any) -> None:
        from PySide6 import QtGui

        self.QtCore, self.QtGui = QtCore, QtGui
        self._pixmap = None
        preview = self

        class ImageLabel(QtWidgets.QLabel):
            def resizeEvent(self, event: Any) -> None:
                super().resizeEvent(event)
                preview._draw()

        self.widget = QtWidgets.QFrame()
        self.widget.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        self.status = QtWidgets.QLabel("Camera · waiting for camera frames")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.image = ImageLabel("Waiting for camera frames")
        self.image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(160, 90)
        self.image.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Ignored,
        )
        self.image.setStyleSheet("background: #101010; color: #dddddd;")
        layout.addWidget(self.image, 1)

    def apply(
        self, frame: VideoPreviewFrame | None, *, ready: bool, detail: str
    ) -> None:
        """Show new RGB data; clear the last image when camera health is lost."""
        self.status.setText(f"Camera · {detail}")
        self.status.setToolTip(detail)
        if not ready:
            self._pixmap = None
            self.image.clear()
            self.image.setText(
                "Waiting for camera frames"
                if detail == "waiting for camera frames"
                else "Camera unavailable"
            )
        elif frame is not None:
            image = self.QtGui.QImage(
                frame.rgb,
                frame.width,
                frame.height,
                frame.width * 3,
                self.QtGui.QImage.Format.Format_RGB888,
            ).copy()
            self._pixmap = self.QtGui.QPixmap.fromImage(image)
            self._draw()

    def _draw(self) -> None:
        if self._pixmap is not None:
            self.image.setPixmap(
                self._pixmap.scaled(
                    self.image.size(),
                    self.QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    self.QtCore.Qt.TransformationMode.FastTransformation,
                )
            )
