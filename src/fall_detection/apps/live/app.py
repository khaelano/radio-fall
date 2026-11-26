"""Command line of ``csi-live``: live CSI data with optional fall detection.

Without ``--models`` the window opens on the live CSI dashboard. Selecting one
or more models, on the command line or in the window, hands the gateway to the
native detector, which scores windows in Rust. ``--headless`` prints detector
results as JSON lines instead of opening a window.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack
from pathlib import Path

from fall_detection.apps.common.dashboard import (
    DASHBOARD_TRACE_COUNTS,
    DEFAULT_DASHBOARD_SUBCARRIERS,
    DEFAULT_INSPECT_SUBCARRIER,
    VALID_SUBCARRIERS,
)
from fall_detection.apps.common.pacing import (
    FPS_DEFAULT,
    add_fps_argument,
    frame_interval_ms,
)
from fall_detection.apps.common.qt import QtUnavailableError, qt_application
from fall_detection.radio.live import LiveRadio
from fall_detection.radio.settings import add_live_arguments, resolve_settings

from .detection import (
    DEFAULT_MODELS,
    MODELS,
    build_config,
    inference_problem,
    new_backend,
    run_headless,
)

GUI_INTERVAL_MS = frame_interval_ms(FPS_DEFAULT)
EXAMPLES = """\
examples:
  csi-live                                 live CSI dashboard from the gateway
  csi-live --models tonepool_tcn-4s        start with fall detection
  csi-live --replay-capture DIR --backend cpu
                                           replay a recorded capture through a model
  csi-live --headless --models cnn-4s --duration 30
                                           print scores as JSON lines, no window

In the window, the Model menu switches between the live view (no model) and
detection with any combination of models; press the toolbar button to apply.
"""


def parser() -> argparse.ArgumentParser:
    """Return the ``csi-live`` argument parser."""
    result = argparse.ArgumentParser(
        prog="csi-live",
        description="Show live CSI from the radio gateway and, optionally, "
        "detect falls with exported sequence models.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_live_arguments(result)
    result.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "root of everything this run writes: live-view transport journals "
            "(transport/gateway/<run>) and one native-<time>/ folder per "
            "detector start. Default: data/experiments/viewer for the live "
            "view and data/experiments/detector for detection, both outside "
            "the DVC-tracked data/raw"
        ),
    )

    view = result.add_argument_group("live view (no model)")
    view.add_argument(
        "--receiver-id",
        help="receiver inventory ID shown first, e.g. rx-2",
    )
    add_fps_argument(view)
    view.add_argument(
        "--dashboard-subcarriers",
        type=int,
        choices=DASHBOARD_TRACE_COUNTS,
        default=DEFAULT_DASHBOARD_SUBCARRIERS,
        help="number of representative physical subcarriers on the dashboard",
    )
    view.add_argument(
        "--inspect-subcarrier",
        type=int,
        choices=VALID_SUBCARRIERS,
        default=DEFAULT_INSPECT_SUBCARRIER,
        metavar="K",
        help=(
            "physical subcarrier shown in the detail trace, "
            f"{VALID_SUBCARRIERS[0]}…{VALID_SUBCARRIERS[-1]} "
            f"(default: {DEFAULT_INSPECT_SUBCARRIER})"
        ),
    )

    detect = result.add_argument_group("fall detection")
    detect.add_argument(
        "--models",
        nargs="+",
        choices=MODELS,
        default=[],
        metavar="MODEL",
        help=(
            "start with these models instead of the live view "
            f"(recommended: {', '.join(DEFAULT_MODELS)}). "
            f"Choices: {', '.join(MODELS)}"
        ),
    )
    detect.add_argument("--model-root", type=Path, default=Path("artifacts/model"))
    detect.add_argument("--backend", choices=["webgpu", "cpu"], default="webgpu")
    detect.add_argument("--ort-library", type=Path)
    detect.add_argument("--webgpu-plugin", type=Path)
    detect.add_argument(
        "--adapter-id",
        type=lambda value: int(value, 0),
        help="PCI device ID of the AMD GPU; default selects the only one",
    )
    detect.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="decision threshold of models without a calibration",
    )
    detect.add_argument(
        "--calibration",
        type=Path,
        metavar="FILE",
        help="calibration.json of an earlier run; the window also records a new one",
    )
    detect.add_argument("--minimum-coverage", type=float, default=0.7)
    detect.add_argument("--packet-capacity", type=int, default=2048)
    detect.add_argument("--hop-ms", type=int, default=250)
    detect.add_argument("--grace-ms", type=int, default=900)

    replay = result.add_argument_group("replay (needs a model)")
    replay.add_argument(
        "--replay-capture",
        nargs="+",
        type=Path,
        metavar="CAPTURE_DIR",
        help="stream recorded native captures in real time instead of the gateway",
    )
    replay.add_argument("--replay-speed", type=float, default=1.0)
    replay.add_argument(
        "--replay-repeat", action="store_true", help="loop the replayed captures"
    )

    run = result.add_argument_group("run")
    run.add_argument(
        "--headless",
        action="store_true",
        help="print detector results as JSON lines; needs --models",
    )
    run.add_argument("--duration", type=float, help="stop after this many seconds")
    return result


def _source_text(args: argparse.Namespace) -> str:
    if args.replay_capture:
        count = len(args.replay_capture)
        return f"replay of {count} capture{'s' if count > 1 else ''} at {args.replay_speed:g}×"
    settings = resolve_settings(args)
    profile = settings.profile
    return f"gateway · {profile.profile_id} · {profile.band} ch {profile.channel}"


def main(argv: list[str] | None = None) -> int:
    """Run the live window, or the headless detector.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        Process exit status.
    """
    cli = parser()
    args = cli.parse_args(argv)
    if args.duration is not None and args.duration <= 0:
        cli.error("--duration must be positive")
    if not 0 <= args.threshold <= 1:
        cli.error("--threshold must be between 0 and 1")
    if args.headless:
        if args.calibration:
            cli.error(
                "--calibration needs the window; headless output has no decisions"
            )
        if not args.models:
            cli.error("--headless prints detector results; select --models")
        try:
            return run_headless(args)
        except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
            print(f"csi-live: {exc}", file=sys.stderr)
            return 2
    if args.models or args.replay_capture:
        problem = inference_problem(args)
        if problem:
            cli.error(problem)
    try:
        source = _source_text(args)
        if not args.replay_capture and not args.gateway_port:
            raise ValueError("a gateway USB port is required (--gateway-port)")
    except (OSError, ValueError) as exc:
        cli.error(str(exc))
    try:
        app = qt_application("csi-live")
    except QtUnavailableError as exc:
        print(exc, file=sys.stderr)
        return 2
    from .window import LiveWindow

    window = LiveWindow(
        args,
        radio_factory=LiveRadio,
        backend_factory=new_backend,
        build_config=build_config,
        inference_problem=inference_problem(args),
        source_text=source,
    )
    with ExitStack() as resources:
        resources.callback(window.shutdown)
        app.aboutToQuit.connect(window.timer.stop)
        window.start()
        window.window.show()
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
