"""What the operator chose for one collection run, without Qt or hardware."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.resume import SessionResume
from fall_detection.collection.video import VideoConfig
from fall_detection.protocol.model import CollectionProtocol

CONTINUOUS_PROTOCOL_ID = "continuous-activity-v1"


@dataclass(frozen=True)
class SessionPlan:
    """Inputs of one new or resumed collection session.

    Attributes:
        protocol: Trials to collect, already reduced to the selected blocks.
        metadata: Participant and operator details saved in the manifest.
        output_dir: Directory that receives the session folder and archive.
        continuous: Record bounded activity segments instead of guided trials.
        video: Camera to record beside CSI, or None for CSI only.
        resume: Saved progress when continuing an earlier session.
        protocol_path: Protocol file the session was set up from, offered as a
            source of scenarios when editing the protocol while recording.
    """

    protocol: CollectionProtocol
    metadata: SessionMetadata
    output_dir: Path
    continuous: bool = False
    video: VideoConfig | None = None
    resume: SessionResume | None = None
    protocol_path: Path | None = None

    def __post_init__(self) -> None:
        if self.continuous and self.video is not None:
            raise ValueError("continuous mode currently supports CSI only")


def resume_plan(saved: SessionResume, video: VideoConfig | None = None) -> SessionPlan:
    """Continue ``saved`` with its own protocol, metadata and camera.

    Args:
        saved: Validated progress from :func:`load_session_resume`.
        video: Camera override; by default the camera recorded in the saved
            manifest is reused, so a session keeps one video setup.

    Returns:
        A plan writing beside the saved session folder.

    Raises:
        ValueError: A continuous session would be resumed with a camera.
    """
    continuous = saved.protocol.protocol_id == CONTINUOUS_PROTOCOL_ID
    if video is None and not continuous:
        previous: dict[str, Any] | None = saved.manifest.get("environment", {}).get(
            "video"
        )
        if previous:
            video = VideoConfig(
                previous["device"],
                previous["width"],
                previous["height"],
                previous["fps"],
            )
    return SessionPlan(
        protocol=saved.protocol,
        metadata=saved.metadata,
        output_dir=saved.root.parent,
        continuous=continuous,
        video=video,
        resume=saved,
    )
