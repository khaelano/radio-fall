"""Synchronized live state shared by the CSI dashboard applications."""

from __future__ import annotations

from threading import Lock

from ..acquisition.buffer import DEFAULT_NOMINAL_RATE_HZ, RollingCsiBuffer


HISTORY_SECONDS = 10.0


class LiveState:
    """Small synchronized state object shared by the reader and GUI threads."""

    def __init__(self, nominal_rate_hz: int = DEFAULT_NOMINAL_RATE_HZ) -> None:
        self.buffer = RollingCsiBuffer(
            nominal_rate=nominal_rate_hz,
            seconds=int(HISTORY_SECONDS),
            max_records=10_000,
        )
        self._lock = Lock()
        self.status = "starting"
        self.connected = False
        self.receiver_buffers: dict[str, RollingCsiBuffer] = {}
        self.selected_receiver_id: str | None = None

    def set_status(self, message: str, connected: bool) -> None:
        with self._lock:
            self.status = message
            self.connected = connected

    def get_status(self) -> tuple[str, bool]:
        with self._lock:
            return self.status, self.connected

    def attach_buffer(self, buffer: RollingCsiBuffer) -> None:
        """Use a single stream that has no receiver switching."""

        with self._lock:
            self.buffer = buffer
            self.receiver_buffers = {}
            self.selected_receiver_id = None

    def configure_receivers(
        self,
        buffers: dict[str, RollingCsiBuffer],
        selected_receiver_id: str | None = None,
    ) -> None:
        """Register receiver buffers and select the preview stream.

        A USB hub can expose several configured receivers at once.  The
        acquisition manager keeps an independent rolling buffer per receiver;
        the dashboard renders one selected stream so phase and amplitude traces
        never mix sequence or timestamp domains from different boards.
        """

        if not buffers:
            raise ValueError("at least one receiver buffer is required")
        receiver_ids = tuple(sorted(buffers))
        if selected_receiver_id is None:
            selected_receiver_id = receiver_ids[0]
        if selected_receiver_id not in buffers:
            raise ValueError(f"unknown receiver: {selected_receiver_id}")
        with self._lock:
            self.receiver_buffers = dict(buffers)
            self.selected_receiver_id = selected_receiver_id
            self.buffer = self.receiver_buffers[selected_receiver_id]

    def select_receiver(self, receiver_id: str) -> None:
        """Switch the stream rendered by the dashboard."""

        with self._lock:
            try:
                self.buffer = self.receiver_buffers[receiver_id]
            except KeyError as exc:
                raise ValueError(f"unknown receiver: {receiver_id}") from exc
            self.selected_receiver_id = receiver_id
