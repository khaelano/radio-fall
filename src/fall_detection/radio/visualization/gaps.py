"""Receiver-by-time heatmap of CSI availability at the delivery deadline."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import time
from typing import Any

import numpy as np

from ..acquisition.availability import AvailabilitySnapshot


UNKNOWN, GAP, RECEIVED, PENDING = range(4)
GAP_REFRESH_NS = 250_000_000
GAP_COLORS = ("#56606a", "#d55e00", "#009e73", "#e5b64b")


def gap_values(snapshot: AvailabilitySnapshot, now_ns: int) -> np.ndarray:
    """Classify bins without interpolation or revising deadline availability."""
    counts = np.asarray(snapshot.packet_counts, dtype=np.float64)
    if counts.size == 0:
        return np.empty((len(snapshot.receivers), 0), dtype=np.uint8)
    ends = (
        snapshot.first_bin_start_ns
        + (np.arange(counts.shape[1], dtype=np.int64) + 1) * snapshot.width_ns
    )
    values = np.where(ends + snapshot.grace_ns <= now_ns, GAP, PENDING)
    values = np.broadcast_to(values, counts.shape).copy()
    values[counts > 0] = RECEIVED
    values[~np.isfinite(counts)] = UNKNOWN
    return values.astype(np.uint8)


class CsiGapPanel:
    """Render all receivers at four Hz without preparing any CSI/phase matrices."""

    def __init__(
        self,
        QtCore: Any,
        QtWidgets: Any,
        pg: Any,
        *,
        receivers: Sequence[str],
        snapshot: Callable[[float, int], AvailabilitySnapshot | None] | None = None,
    ) -> None:
        self._QtCore = QtCore
        self._snapshot = snapshot
        self._receivers = tuple(receivers)
        self._rendered_ns: int | None = None
        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.caption = QtWidgets.QLabel("Waiting for acquisition timing")
        self.caption.setWordWrap(True)
        layout.addWidget(self.caption)
        self.canvas = pg.GraphicsLayoutWidget()
        self.plot = self.canvas.addPlot()
        self.plot.setTitle("CSI gaps — all receivers")
        self.plot.setLabel("left", "receiver")
        self.plot.setLabel("bottom", "capture time relative to now", units="s")
        self.plot.getViewBox().setMouseEnabled(x=False, y=False)
        self.plot.getViewBox().invertY(True)
        self.plot.enableAutoRange(False)
        self.image = pg.ImageItem(axisOrder="row-major")
        self.image.setLookupTable(
            np.array(
                [pg.mkColor(color).getRgb() for color in GAP_COLORS], dtype=np.uint8
            )
        )
        self.plot.addItem(self.image)
        layout.addWidget(self.canvas, 1)
        legend = QtWidgets.QLabel(
            " &nbsp; ".join(
                f'<span style="color:{color}">■</span> {label}'
                for color, label in zip(
                    GAP_COLORS,
                    (
                        "No timing / before run",
                        "Empty after deadline",
                        "CSI received by deadline",
                        "Awaiting delivery deadline",
                    ),
                )
            )
        )
        legend.setWordWrap(True)
        layout.addWidget(legend)

    def refresh(
        self, seconds: float, *, force: bool = False, now_ns: int | None = None
    ) -> bool:
        """Update a bounded snapshot, including advancing time during silence."""
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        if (
            not force
            and self._rendered_ns is not None
            and now_ns - self._rendered_ns < GAP_REFRESH_NS
        ):
            return False
        snapshot = self._snapshot(seconds, now_ns) if self._snapshot else None
        if snapshot is None:
            receivers = self._receivers
            values = np.zeros((max(1, len(receivers)), 1), dtype=np.uint8)
            left, width = -seconds, seconds
            self.caption.setText("Waiting for acquisition timing")
        else:
            receivers = snapshot.receivers
            values = gap_values(snapshot, now_ns)
            left = (snapshot.first_bin_start_ns - now_ns) / 1e9
            width = values.shape[1] * snapshot.width_ns / 1e9
            self.caption.setText(
                f"{snapshot.width_ns / 1e6:g} ms bins · delivery deadline "
                f"{snapshot.grace_ns / 1e6:g} ms after each bin. "
                "Empty bins can include scheduled sensing/upload pauses."
            )
        self.image.setImage(values, autoLevels=False, levels=(0, 3))
        self.image.setRect(
            self._QtCore.QRectF(left, -0.5, width, max(1, len(receivers)))
        )
        self.plot.getAxis("left").setTicks(
            [[(index, receiver) for index, receiver in enumerate(receivers)]]
        )
        self.plot.setXRange(-seconds, 0, padding=0)
        self.plot.setYRange(-0.5, max(1, len(receivers)) - 0.5, padding=0)
        self._rendered_ns = now_ns
        return True
