"""Presentation styles for the collection windows."""

from fall_detection.collection.controller import SessionState

_STATE_COLORS = {
    SessionState.SETUP: "#6b7280",
    SessionState.READY: "#2563eb",
    SessionState.COUNTDOWN: "#d97706",
    SessionState.ACTION: "#dc2626",
    SessionState.RECOVERY: "#7c3aed",
    SessionState.REVIEW: "#0d9488",
    SessionState.COMPLETE: "#16a34a",
}

STYLESHEET = """
QFrame#card {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 8px;
}
QLabel#cardTitle {
    color: palette(mid);
    font-size: 11px;
    font-weight: 700;
}
QLabel#scenarioTitle {
    font-size: 16px;
    font-weight: 700;
}
QLabel#instruction {
    font-size: 13px;
}
QLabel#message {
    color: palette(mid);
    font-size: 12px;
    font-style: italic;
}
QLabel#phase {
    font-size: 28px;
    font-weight: 700;
}
QPushButton:disabled {
    color: #9ca3af;
}
"""


def state_badge_style(state: SessionState) -> str:
    """Return the badge stylesheet for one collection state."""

    color = _STATE_COLORS.get(state, "#6b7280")
    return (
        f"background: {color}; color: white; border-radius: 6px;"
        "padding: 4px 12px; font-size: 15px; font-weight: 700;"
    )
