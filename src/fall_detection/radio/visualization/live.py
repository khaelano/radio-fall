"""The shared plotting and diagnostics surface of both live applications."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from ..acquisition.availability import AvailabilitySnapshot
from .dashboard import CsiDashboardPanel, DEFAULT_VIEW_SECONDS
from .rendering import DEFAULT_DASHBOARD_SUBCARRIERS, DEFAULT_INSPECT_SUBCARRIER
from .pacing import STATUS_INTERVAL_SECONDS
from .transport_status import GatewayStatusPanel, TransportStatusText

if TYPE_CHECKING:
    from ..live import LiveRadio


class LiveDashboard:
    """Refresh plots at display pace and diagnostics at a bounded lower rate."""

    def __init__(
        self,
        radio: LiveRadio,
        *,
        fps: int,
        dashboard_subcarriers: int = DEFAULT_DASHBOARD_SUBCARRIERS,
        inspect_subcarrier: int = DEFAULT_INSPECT_SUBCARRIER,
        window_seconds: float = DEFAULT_VIEW_SECONDS,
    ) -> None:
        self.radio = radio
        self.fps = fps
        self.panel = CsiDashboardPanel(
            radio.state,
            fps=fps,
            receivers=[binding.receiver_id for binding in radio.bindings],
            can_render=lambda: radio.manager.preview_ready,
            dashboard_subcarriers=dashboard_subcarriers,
            inspect_subcarrier=inspect_subcarrier,
            window_seconds=window_seconds,
            gap_snapshot=self._gap_snapshot,
        )
        self.transport_panel = GatewayStatusPanel()
        self.panel.widget.layout().insertWidget(1, self.transport_panel.widget)
        self._status: TransportStatusText | None = None
        self._status_at = float("-inf")
        self._selected: str | None = None

    def _gap_snapshot(self, seconds: float, now_ns: int) -> AvailabilitySnapshot | None:
        grid = self.radio.manager.grid
        return grid.snapshot(seconds=seconds, now_ns=now_ns) if grid else None

    def refresh(self, *, now: float | None = None) -> TransportStatusText:
        """Draw new preview data and return the current receiver status text."""
        now = time.monotonic() if now is None else now
        self.panel.refresh()
        selected = self.radio.state.selected_receiver_id
        if (
            now - self._status_at >= STATUS_INTERVAL_SECONDS
            or selected != self._selected
        ):
            self._status = self.transport_panel.apply(
                self.radio.manager.diagnostics(),
                selected_receiver_id=selected,
                plot_refresh_fps=self.panel.measured_fps,
                ui_fps=self.fps,
            )
            self._selected = selected
            self._status_at = now
        assert self._status is not None
        return self._status
