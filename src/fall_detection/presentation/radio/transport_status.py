"""Shared gateway status text and receiver table for both live applications."""

from __future__ import annotations

from dataclasses import dataclass

from fall_detection.radio.acquisition.gateway_diagnostics import (
    GatewayDiagnostics,
    ReceiverDiagnostics,
)


def _value(value: int | None) -> str:
    return "pending" if value is None else str(value)


def _age(value: float | None) -> str:
    return "pending" if value is None else f"{value:.1f}s"


@dataclass(frozen=True)
class TransportStatusText:
    """Labels and tooltips built from the same immutable status snapshot."""

    connection: str
    configuration: str
    compact: str
    detail: str


def receiver_cells(receiver: ReceiverDiagnostics, capacity: int) -> tuple[str, ...]:
    """Format last reports without replacing missing firmware counters with zero."""
    link = (
        "online"
        if receiver.online
        else ("waiting" if receiver.status_age_s is None else "stale")
    )
    return (
        receiver.receiver_id,
        link,
        receiver.state_name,
        f"{receiver.records_s:.0f}",
        _age(receiver.delivery_age_s),
        "pending" if receiver.queued is None else f"{receiver.queued}/{capacity}",
        _value(receiver.expired),
        _value(receiver.dropped),
        _value(receiver.send_errors),
    )


def format_transport_status(
    snapshot: GatewayDiagnostics,
    *,
    selected_receiver_id: str | None,
    plot_refresh_fps: float,
    ui_fps: int,
) -> TransportStatusText:
    """Separate sensing rate, host delivery rate and plotting/GUI refresh rates."""
    online = sum(r.online for r in snapshot.receivers)
    reference = (
        "ready"
        if snapshot.reference_ready
        else (
            "waiting"
            if not snapshot.reference_present
            else ("warming" if snapshot.clock_uncertainty_us is None else "stale")
        )
    )
    gateway = (
        "waiting"
        if snapshot.gateway_age_s is None
        else ("online" if snapshot.gateway_age_s < 2.5 else "stale")
    )
    reference_link = {"usb": "USB", "espnow_uart": "C6 relay"}.get(
        snapshot.transmitter_link, snapshot.transmitter_link.upper()
    )
    connection = f"Reference {reference_link}: {reference} | gateway {gateway} | receivers {online}/{len(snapshot.receivers)} online"
    if snapshot.failure:
        connection = "Error: " + snapshot.failure
    mode = "host ACK" if snapshot.application_acknowledgements else "ACK-less"
    setup = "Configured" if snapshot.gateway_configured else "Requested"
    if gateway == "online" and snapshot.gateway_configured is False:
        connection += " | gateway not configured"
    configuration = (
        f"{setup} sensing {snapshot.nominal_rate_hz} Hz/receiver · 5 GHz ch {snapshot.sensing_channel}"
        f" | backhaul 2.4 GHz ch {snapshot.backhaul_channel} {snapshot.backhaul_phy.replace('_', ' ').upper()}"
        f" | slot {snapshot.slot_ms} ms | queue {snapshot.queue_capacity} records | {mode}"
    )
    selected = next(
        (r for r in snapshot.receivers if r.receiver_id == selected_receiver_id), None
    )
    compact = f"All receivers: {snapshot.records_s:.0f} records/s"
    if selected:
        compact += f" | {selected.receiver_id}: {selected.records_s:.0f}/s · {selected.records} records"
    compact += f" | plot {plot_refresh_fps:.0f} FPS | UI {ui_fps} FPS"
    uncertainty = (
        "pending"
        if snapshot.clock_uncertainty_us is None
        else f"{snapshot.clock_uncertainty_us / 1000:.3f} ms"
    )
    lines = [
        connection,
        configuration,
        "Delivered rates count unique validated host records in the preceding 1 s; they are not a qualification result.",
        f"Last clock fit uncertainty: {uncertainty}.",
        f"Gateway envelopes: received {_value(snapshot.received_envelopes)}, forwarded {_value(snapshot.forwarded_envelopes)}, rejected/dropped {_value(snapshot.rejected_or_dropped)}; USB errors {_value(snapshot.usb_errors)}; queued messages {_value(snapshot.gateway_queued)}; status age {_age(snapshot.gateway_age_s)}.",
    ]
    for r in snapshot.receivers:
        lines.append(
            f"{r.receiver_id}: last reported {r.state_name} ({_age(r.status_age_s)} ago); "
            f"captured {_value(r.captured)}, delivered {r.records}; queue {_value(r.queued)}/{snapshot.queue_capacity}, peak {_value(r.queue_peak)}; "
            f"expired {_value(r.expired)}, dropped {_value(r.dropped)}, send errors {_value(r.send_errors)}; "
            f"sequence gaps {r.sequence_gaps}, transport gaps {r.transport_gaps}, batch gaps {r.batch_gaps}, malformed packets {r.malformed_packets}; "
            f"diagnostic event loss {'pending' if r.diagnostic_loss is None else ('yes' if r.diagnostic_loss else 'no')}."
        )
    lines.extend(
        (
            "Reported state is the last 5 GHz control report, not a live channel indicator.",
            "Dropped combines receiver evictions/rejections and ingress losses. Expiry is separate. Send errors include firmware submission errors and MAC failures.",
            "Sequence gaps do not identify scheduled upload gaps versus radio/transport loss. Last data age is host delivery age, not sensing-to-host latency.",
        )
    )
    return TransportStatusText(connection, configuration, compact, "\n".join(lines))


class GatewayStatusPanel:
    """A shared, read-only transport summary with one stable row per receiver."""

    def __init__(self) -> None:
        from PySide6 import QtWidgets

        self._QtWidgets = QtWidgets
        self.widget = QtWidgets.QGroupBox("Gateway transport")
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(6, 4, 6, 4)
        self.connection_label = QtWidgets.QLabel(
            "Waiting for gateway and transmitter reference"
        )
        self.connection_label.setWordWrap(True)
        self.configuration_label = QtWidgets.QLabel("")
        self.configuration_label.setWordWrap(True)
        layout.addWidget(self.connection_label)
        layout.addWidget(self.configuration_label)
        self.table = QtWidgets.QTableWidget(0, 9)
        headers = (
            "Receiver",
            "Link",
            "Last report",
            "Delivered/s",
            "Data age",
            "Queue",
            "Expired",
            "Dropped",
            "Send errors",
        )
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.NoSelection
        )
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        tips = (
            "Fixed inventory identity; bold row is the plotted receiver.",
            "Fresh receiver control report, independent of short planned upload gaps.",
            "Last reported state, not the current radio channel. Reports may be delayed by uploads.",
            "Unique valid records accepted by the host in the preceding 1 second. Configured sensing Hz is separate.",
            "Time since the last host-delivered record; this is not transport latency.",
            "Last reported queued records / configured receiver record capacity.",
            "Cumulative receiver record lifetime expiry counter.",
            "Cumulative receiver evictions/rejections and ingress losses, separate from expiry.",
            "Cumulative receiver submission errors plus MAC failures; not host acceptance failures.",
        )
        for index, tip in enumerate(tips):
            self.table.horizontalHeaderItem(index).setToolTip(tip)
        layout.addWidget(self.table)
        self._receiver_order: tuple[str, ...] = ()

    def apply(
        self,
        snapshot: GatewayDiagnostics,
        *,
        selected_receiver_id: str | None,
        plot_refresh_fps: float,
        ui_fps: int,
    ) -> TransportStatusText:
        """Refresh labels and cells; neither polling nor rendering touches hardware."""
        text = format_transport_status(
            snapshot,
            selected_receiver_id=selected_receiver_id,
            plot_refresh_fps=plot_refresh_fps,
            ui_fps=ui_fps,
        )
        self.connection_label.setText(text.connection)
        self.configuration_label.setText(text.configuration)
        self.widget.setToolTip(text.detail)
        order = tuple(r.receiver_id for r in snapshot.receivers)
        if order != self._receiver_order:
            self.table.setRowCount(len(order))
            self._receiver_order = order
            self.table.setFixedHeight(
                self.table.horizontalHeader().sizeHint().height()
                + 24 * len(order)
                + 2 * self.table.frameWidth()
                + self.table.horizontalScrollBar().sizeHint().height()
            )
            for index in range(len(order)):
                self.table.setRowHeight(index, 24)
        for row, receiver in enumerate(snapshot.receivers):
            for column, value in enumerate(
                receiver_cells(receiver, snapshot.queue_capacity)
            ):
                cell = self.table.item(row, column)
                if cell is None:
                    cell = self._QtWidgets.QTableWidgetItem()
                    self.table.setItem(row, column, cell)
                if cell.text() != value:
                    cell.setText(value)
                font = cell.font()
                font.setBold(receiver.receiver_id == selected_receiver_id)
                cell.setFont(font)
                cell.setToolTip(
                    f"Control status age: {_age(receiver.status_age_s)}. "
                    + self.table.horizontalHeaderItem(column).toolTip()
                )
        return text
