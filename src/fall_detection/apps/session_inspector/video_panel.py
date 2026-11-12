"""Video transport controls sharing an attempt-relative cursor with CSI plots."""

from __future__ import annotations

import time
from bisect import bisect_right

from PySide6 import QtCore, QtGui, QtWidgets

from fall_detection.session_inspector.models import RecordedAttempt
from fall_detection.session_inspector.video import VideoTimeline, VideoWorker


class VideoPanel(QtWidgets.QWidget):
    """Play, scrub and frame-step without decoding media on the GUI thread."""

    position_changed = QtCore.Signal(float)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.worker = VideoWorker()
        self.generation = 0
        self.attempt = None
        self.timeline: VideoTimeline | None = None
        self.position = 0.0
        self.playing = False
        self._anchor = 0.0
        self._pixmap = None
        self._frame_index = None
        self.setMinimumWidth(260)
        layout = QtWidgets.QVBoxLayout(self)
        self.image = QtWidgets.QLabel("No video selected")
        self.image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.image.setWordWrap(True)
        self.image.setMinimumSize(240, 135)
        self.image.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.image.setStyleSheet("background: #111827; color: #e5e7eb;")
        layout.addWidget(self.image, 1)
        self.caption = QtWidgets.QLabel("Video · select an attempt")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(self.slider)
        controls = QtWidgets.QHBoxLayout()
        self.previous = QtWidgets.QPushButton("◀ Frame")
        self.play = QtWidgets.QPushButton("Play")
        self.next = QtWidgets.QPushButton("Frame ▶")
        for button in [self.previous, self.play, self.next]:
            controls.addWidget(button)
        layout.addLayout(controls)
        note = QtWidgets.QLabel(
            "Host observation time · camera exposure latency is unknown"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.previous.clicked.connect(lambda: self.step(-1))
        self.next.clicked.connect(lambda: self.step(1))
        self.play.clicked.connect(self.toggle_play)
        self.slider.sliderPressed.connect(self.pause)
        self.slider.valueChanged.connect(lambda value: self.seek(value / 1000))
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._enable(False)

    def _enable(self, enabled: bool) -> None:
        for widget in [self.play, self.previous, self.next, self.slider]:
            widget.setEnabled(enabled)

    def set_attempt(self, attempt: RecordedAttempt | None) -> None:
        """Invalidate previous media immediately when changing attempts."""
        if (
            attempt is not None
            and self.attempt is not None
            and attempt.path == self.attempt.path
        ):
            return
        self.pause()
        self.generation += 1
        self.attempt, self.timeline = attempt, None
        self.position, self._frame_index = 0.0, None
        self._pixmap = None
        self.image.clear()
        self.image.setText(
            "Loading recorded video…" if attempt else "No video selected"
        )
        self.caption.setText(
            "Video · loading" if attempt else "Video · select an attempt"
        )
        self._enable(False)
        with QtCore.QSignalBlocker(self.slider):
            self.slider.setValue(0)
        self.position_changed.emit(0.0)
        self.worker.request(self.generation, attempt, 0.0)

    def pause(self) -> None:
        """Stop playback while retaining the selected observation time."""
        self.playing = False
        self.play.setText("Play")

    def toggle_play(self) -> None:
        """Use elapsed host time as the playback clock, including saved gaps."""
        if self.playing:
            self.pause()
        elif self.timeline is not None:
            if self.position >= self.timeline.duration:
                self.seek(0)
            self._anchor = time.monotonic() - self.position
            self.playing = True
            self.play.setText("Pause")

    def seek(self, seconds: float) -> None:
        """Move the shared cursor and request the corresponding recorded frame."""
        if self.timeline is None:
            return
        self.position = min(max(0.0, seconds), self.timeline.duration)
        if self.playing:
            self._anchor = time.monotonic() - self.position
        with QtCore.QSignalBlocker(self.slider):
            self.slider.setValue(round(self.position * 1000))
        self.position_changed.emit(self.position)
        self.worker.request(self.generation, self.attempt, self.position)
        self._update_caption()

    def step(self, direction: int) -> None:
        """Step between actual frame observations, not assumed FPS intervals."""
        if self.timeline is None:
            return
        self.pause()
        instant = self.timeline.origin_ns + round(self.position * 1e9)
        if direction > 0:
            index = min(
                len(self.timeline.observations) - 1,
                bisect_right(self.timeline.observations, instant),
            )
        else:
            current = self.timeline.frame_at(self.position)
            index = max(0, (current if current is not None else 0) - 1)
        self.seek(self.timeline.frame_seconds(index))

    def _tick(self) -> None:
        if self.playing and self.timeline is not None:
            anchor = self._anchor
            self.seek(time.monotonic() - anchor)
            self._anchor = anchor
            if self.position >= self.timeline.duration:
                self.pause()
        result = self.worker.poll()
        if result is None:
            return
        token, seconds, timeline, index, pixels, error = result
        if token != self.generation:
            return
        if error:
            self.pause()
            self.timeline = None
            self._pixmap = None
            self._enable(False)
            self.image.clear()
            self.image.setText(error)
            self.caption.setText("Video unavailable")
            self.position_changed.emit(self.position)
            return
        first_result = self.timeline is None
        self.timeline = timeline
        if first_result:
            self.position_changed.emit(self.position)
        self._enable(True)
        with QtCore.QSignalBlocker(self.slider):
            self.slider.setRange(0, round(timeline.duration * 1000))
        if not self.playing and abs(seconds - self.position) > 1e-6:
            return
        self._frame_index = index
        if pixels is None:
            self._pixmap = None
            self.image.clear()
            self.image.setText("No frame observed yet at this time")
        else:
            width, height, rgb = pixels
            image = QtGui.QImage(
                rgb, width, height, width * 3, QtGui.QImage.Format.Format_RGB888
            ).copy()
            self._pixmap = QtGui.QPixmap.fromImage(image)
            self._draw()
        self._update_caption()

    def _update_caption(self) -> None:
        if self.timeline is None:
            return
        text = f"Attempt {self.position:.3f} / {self.timeline.duration:.3f} s"
        if self._frame_index is not None:
            observed = self.timeline.frame_seconds(self._frame_index)
            text += f" · frame {self._frame_index + 1} at {observed:.3f} s (age {(self.position - observed) * 1000:.0f} ms)"
        if self.timeline.status == "failed":
            text += " · incomplete recording"
        self.caption.setText(text)

    def _draw(self) -> None:
        if self._pixmap is not None:
            self.image.setPixmap(
                self._pixmap.scaled(
                    self.image.size(),
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._draw()

    def shutdown(self) -> None:
        """Stop playback and release worker resources when the window closes."""
        self.pause()
        self.timer.stop()
        self.worker.close()
