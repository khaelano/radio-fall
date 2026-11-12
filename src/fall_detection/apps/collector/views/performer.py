"""Performer cues rendered from the same snapshot as the operator view."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fall_detection.collection.controller import SessionSnapshot, SessionState
from fall_detection.collection.protocol import CollectionProtocol


class PerformerWindow:
    """Full-screen performer guidance shown on the second display."""

    def __init__(
        self, QtCore: Any, QtWidgets: Any, protocol: CollectionProtocol
    ) -> None:
        self.QtCore = QtCore
        self.QtWidgets = QtWidgets
        self.window = QtWidgets.QMainWindow()
        self.window.setWindowTitle("Performer guidance")
        central = QtWidgets.QWidget()
        self.window.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(48, 48, 48, 48)
        self.state_label = QtWidgets.QLabel("WAITING")
        self.state_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("font-size: 34px; font-weight: bold;")
        self.title_label = QtWidgets.QLabel(protocol.title)
        self.title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-size: 24px;")
        self.instruction_label = QtWidgets.QLabel("Wait for the operator")
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.instruction_label.setStyleSheet("font-size: 32px;")
        self.timer_label = QtWidgets.QLabel("")
        self.timer_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("font-size: 96px; font-weight: bold;")
        layout.addStretch()
        layout.addWidget(self.state_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self.timer_label)
        layout.addStretch()

    def place(self, screens: Sequence[Any]) -> bool:
        """Place the guidance window and report whether a second display exists."""

        if len(screens) > 1:
            self.window.setGeometry(screens[1].geometry())
            self.window.showFullScreen()
            return True
        self.window.show()
        return False

    def apply(self, snapshot: SessionSnapshot) -> None:
        """Render one controller snapshot into the performer guidance."""

        trial = snapshot.trial
        if trial is None:
            self.state_label.setText("COMPLETE")
            self.instruction_label.setText(snapshot.message)
            self.timer_label.setText("")
        elif snapshot.state is SessionState.COUNTDOWN:
            self.state_label.setText("GET READY")
            self.instruction_label.setText(trial.scenario.instruction)
            self.timer_label.setText(
                str(max(1, int(snapshot.phase_remaining_seconds + 0.999)))
            )
        elif snapshot.state is SessionState.ACTION:
            self.state_label.setText("PERFORM")
            self.instruction_label.setText(trial.scenario.title)
            self.timer_label.setText(
                str(max(1, int(snapshot.phase_remaining_seconds + 0.999)))
            )
        elif snapshot.state is SessionState.RECOVERY:
            self.state_label.setText("RECOVER")
            self.instruction_label.setText("Remain still until the operator continues.")
            self.timer_label.setText(
                str(max(1, int(snapshot.phase_remaining_seconds + 0.999)))
            )
        elif snapshot.state is SessionState.REVIEW:
            self.state_label.setText("WAIT")
            self.instruction_label.setText("The operator is reviewing this attempt.")
            self.timer_label.setText("")
        else:
            self.state_label.setText("WAITING")
            self.instruction_label.setText("Wait for the operator.")
            self.timer_label.setText("")
