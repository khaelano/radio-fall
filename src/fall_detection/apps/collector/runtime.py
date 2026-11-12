"""Collection lifecycle and presentation updates without importing Qt."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import (
    HealthSnapshot,
    OperatorCommand,
    SessionController,
    SessionSnapshot,
    SessionState,
)
from fall_detection.presentation.radio.live import LiveDashboard
from fall_detection.radio.live import LiveRadio


def output_writable(path: Path) -> bool:
    """Check the output directory, or the nearest existing parent before creation."""
    while not path.exists() and path != path.parent:
        path = path.parent
    return path.is_dir() and os.access(path, os.W_OK)


def _end_session(controller: SessionController) -> None:
    if controller.state is not SessionState.COMPLETE:
        controller.dispatch(OperatorCommand.END_SESSION)


@contextmanager
def running_collection(
    controller: SessionController,
    radio: LiveRadio,
    metadata: SessionMetadata,
    *,
    video: Any = None,
    resume_session: Path | None = None,
) -> Iterator[None]:
    """Start inputs and always end and drain the run, even on partial startup.

    Ending the attempt precedes radio shutdown; draining the remaining accepted
    records precedes camera shutdown. The caller owns the optional camera and
    closes it after this context. Every cleanup runs if an earlier one fails.
    """
    with ExitStack() as resources:
        resources.callback(controller.flush_radio)
        resources.callback(radio.stop)
        resources.callback(_end_session, controller)
        if resume_session is None:
            controller.start_session(metadata)
        else:
            controller.resume_session(resume_session)
        if video is not None:
            video.start()
        radio.start()
        yield


class CollectionPresenter:
    """Keep trial health responsive while bounding optional display work.

    Each tick evaluates current radio/video readiness and advances the controller.
    Filesystem probes run once a second; the shared dashboard bounds diagnostics
    separately. The presenter consumes snapshots and never writes CSI itself.
    """

    def __init__(
        self,
        controller: SessionController,
        radio: LiveRadio,
        dashboard: LiveDashboard,
        *,
        operator: Any,
        performer: Any,
        output_dir: Path,
        video: Any = None,
    ) -> None:
        self.controller, self.radio, self.dashboard = controller, radio, dashboard
        self.operator, self.performer = operator, performer
        self.output_dir, self.video = output_dir, video
        self._storage_at = float("-inf")
        self._storage_ready = False

    def refresh(self, *, now: float | None = None) -> SessionSnapshot:
        """Advance one display tick using current health and return its snapshot."""
        now = time.monotonic() if now is None else now
        reader = self.radio.manager
        active = self.controller.state in (
            SessionState.COUNTDOWN,
            SessionState.ACTION,
            SessionState.RECOVERY,
        )
        clock_ready = reader.clock_sync_ready
        radio_live = clock_ready and (
            active or (reader.all_live and reader.any_recent_record)
        )
        if now - self._storage_at >= 1.0:
            self._storage_ready = output_writable(self.output_dir)
            self._storage_at = now
        health = HealthSnapshot(
            radio_live=radio_live,
            storage_ready=self._storage_ready
            and not getattr(
                getattr(self.controller, "_recording_io", None), "failure", None
            ),
            clock_sync_ready=clock_ready,
            radio_detail=self.radio.state.get_status()[0],
            video_ready=self.video.ready if self.video else True,
            video_detail=self.video.detail if self.video else "video disabled",
            storage_detail="ready"
            if self._storage_ready
            else "output directory is not writable",
        )
        if health != self.controller.health:
            self.controller.update_health(health)
        snapshot = self.controller.tick()
        text = self.dashboard.refresh(now=now)
        health = snapshot.health
        health_text = (
            f"radio {'ok' if health.radio_live else 'offline'}"
            f"  |  sync {'ok' if health.clock_sync_ready else 'warming'}"
            f"  |  storage {'ok' if health.storage_ready else 'blocked'}"
        )
        radio_detail = text.connection
        if self.video:
            health_text += f"  |  video {'ok' if health.video_ready else 'blocked'}"
            radio_detail += " | " + self.video.detail
        self.operator.apply(
            snapshot,
            health_text=health_text,
            metrics_text=text.compact,
            metrics_tooltip=text.detail,
            radio_detail=radio_detail,
        )
        if self.video is not None and self.operator.camera_preview is not None:
            self.operator.camera_preview.apply(
                self.video.latest_preview() if health.video_ready else None,
                ready=health.video_ready,
                detail=health.video_detail,
            )
        self.performer.apply(snapshot)
        return snapshot
