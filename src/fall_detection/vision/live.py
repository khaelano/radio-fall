"""Live YOLO-pose viewer with rule-based fall proposals."""

from __future__ import annotations

import argparse
from pathlib import Path
import time
from typing import Sequence

from .rules import (
    DetectorState,
    DetectorTransition,
    FallRulesConfig,
    RuleBasedFallDetector,
)
from .yolo import largest_person_index, observation_from_yolo


DEFAULT_MODEL = Path("data/models/yolo/yolo26n-pose_ncnn_model")
DEFAULT_CONFIG = Path("configs/vision/rule_based_fall.toml")


def _source(value: str) -> int | str:
    return int(value) if value.isdecimal() else value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Propose falls from live YOLO pose landmarks."
    )
    parser.add_argument("--source", default="0", help="Camera index, path, or URL")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--device", default="vulkan:0")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--headless", action="store_true")
    return parser


def _state_color(state: DetectorState) -> tuple[int, int, int]:
    return {
        DetectorState.MONITORING: (40, 200, 40),
        DetectorState.DESCENDING: (0, 190, 255),
        DetectorState.POSSIBLE_FALL: (0, 120, 255),
        DetectorState.FALLEN: (0, 0, 255),
    }[state]


def main(argv: Sequence[str] | None = None) -> int:
    """Run live pose inference and display proposed fall states."""

    args = _parser().parse_args(argv)
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "Install vision dependencies with: uv sync --extra vision"
        ) from exc

    config = FallRulesConfig.from_toml(args.config)
    detector = RuleBasedFallDetector(config)
    model = YOLO(str(args.model))
    source = _source(args.source)

    try:
        results = model.predict(
            source=source,
            stream=True,
            stream_buffer=False,
            imgsz=args.imgsz,
            device=args.device,
            save=False,
            verbose=False,
        )
        for result in results:
            timestamp_s = time.monotonic()
            person_index = largest_person_index(result)
            if person_index is None:
                output = detector.update_missing(timestamp_s)
            else:
                observation = observation_from_yolo(
                    result, timestamp_s, person_index
                )
                output = detector.update(observation)

            if output.transition is not DetectorTransition.NONE:
                print(
                    f"{timestamp_s:.3f} {output.transition.value} "
                    f"state={output.state.value}",
                    flush=True,
                )

            if args.headless:
                continue
            frame = result.plot()
            color = _state_color(output.state)
            cv2.putText(
                frame,
                f"Fall state: {output.state.value}",
                (16, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )
            if output.features is not None:
                features = output.features
                detail = (
                    f"drop={features.hip_drop_torso_lengths:.2f} "
                    f"angle={features.torso_angle_degrees:.0f} "
                    f"ratio={features.box_aspect_ratio:.2f}"
                )
                cv2.putText(
                    frame,
                    detail,
                    (16, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    color,
                    1,
                    cv2.LINE_AA,
                )
            cv2.imshow("Rule-based fall proposals", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if not args.headless:
            cv2.destroyAllWindows()
    return 0
