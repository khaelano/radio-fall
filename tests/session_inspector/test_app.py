from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6 import QtCore, QtWidgets

from fall_detection.apps.session_inspector.app import (
    SessionInspectorWindow,
    SignalsPanel,
    TextTableModel,
    ValuesPanel,
    _parser,
)
from fall_detection.radio.acquisition.protocol import (
    CSI_HEADER,
    CsiRecord,
    format_csi_record,
)
from fall_detection.session_inspector.data import (
    TableData,
    load_attempt_data,
    load_attempt_data_for_ui,
)
from fall_detection.session_inspector.models import load_session


@pytest.fixture
def application():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_parser_accepts_sessions_directory_and_individual_path():
    assert _parser().parse_args([]).sessions_dir == Path("data/raw/sessions")
    assert _parser().parse_args(["one-session"]).session == Path("one-session")


def test_window_lists_attempts_edits_metadata_and_accepts_current_load(
    session_factory, application
):
    root = session_factory(attempts=((1, 1, "accepted"),))
    window = SessionInspectorWindow(root)

    assert window.session is not None
    assert window.attempt_model.rowCount() == 2
    assert window.metadata_widgets["participant_id"].isEnabled()
    window.metadata_widgets["participant_id"].setText("changed")
    window.metadata_widgets["participant_id"].textEdited.emit("changed")
    assert window.is_dirty()

    attempt = window.session.attempts[0]
    data = load_attempt_data(attempt, "rx-1")
    stale_token = window._load_token - 1
    window._attempt_data_loaded(stale_token, data)
    assert window.values_tab.data is None
    window.detail_tabs.setCurrentWidget(window.values_tab)
    window._attempt_data_loaded(window._load_token, data)
    assert window.values_tab.data is data
    window.review = window.loaded_review.document.clone()
    window.baseline_state = {
        "metadata": {},
        "attempts": {},
    }
    window.close()


def test_active_session_disables_review_controls(session_factory, application):
    root = session_factory(status="open", attempts=((1, 1, "recording"),))
    window = SessionInspectorWindow(root)

    assert window.session.active
    assert not window.save_button.isEnabled()
    assert not window.export_button.isEnabled()
    assert not window.metadata_widgets["notes"].isEnabled()
    window.close()


def test_text_table_model_paginates_and_maps_source_rows(application):
    table = TableData(
        name="long",
        path=None,
        headers=("value",),
        rows=tuple((f"row-{index}",) for index in range(505)),
    )
    model = TextTableModel(table, page_size=250)

    assert model.page_count == 3
    assert model.rowCount() == 250
    assert model.data(model.index(249, 0)) == "row-249"

    model.set_page(1)
    assert model.source_row(0) == 250
    assert model.data(model.index(0, 0)) == "row-250"
    assert (
        model.headerData(
            0,
            QtCore.Qt.Orientation.Vertical,
            QtCore.Qt.ItemDataRole.DisplayRole,
        )
        == "251"
    )

    model.set_page(2)
    assert model.rowCount() == 5
    assert model.data(model.index(4, 0)) == "row-504"


def test_signal_panel_reuses_plot_items(application):
    panel = SignalsPanel()
    curve_ids = tuple(
        id(curve)
        for curve in (
            *panel.amplitude_curves,
            panel.phase_curve,
            *panel.iq_curves,
            *panel.radio_curves,
            panel.interval_curve,
        )
    )

    panel.clear()

    assert curve_ids == tuple(
        id(curve)
        for curve in (
            *panel.amplitude_curves,
            panel.phase_curve,
            *panel.iq_curves,
            *panel.radio_curves,
            panel.interval_curve,
        )
    )
    panel.close()


def test_values_panel_parses_compact_csi_row_on_demand(session_factory, application):
    root = session_factory(attempts=((1, 1, "accepted"),))
    csi_path = next(root.glob("trials/*/attempt_*/receivers/rx-1/csi.csv"))
    record = CsiRecord(
        sequence=10,
        mac="00:11:22:33:44:55",
        rssi=-50,
        noise_floor=-95,
        timestamp_us=1_000,
        csi=(complex(3, 4), complex(-2, 1)),
    )
    csi_path.write_text(
        CSI_HEADER + "\n" + format_csi_record(record) + "\n",
        encoding="utf-8",
    )
    session = load_session(root)
    data = load_attempt_data_for_ui(session.attempts[0], "rx-1")
    panel = ValuesPanel()

    panel.set_data(data)
    panel._csi_row_changed(panel.models["csi"].index(0, 0), QtCore.QModelIndex())

    assert data.records == ()
    assert panel.models["detail"].rowCount() == 2
    panel.close()


def test_attempt_load_is_debounced_and_cache_hits_skip_worker(
    session_factory, application, monkeypatch
):
    root = session_factory(attempts=((1, 1, "accepted"), (1, 2, "accepted")))
    window = SessionInspectorWindow(root)
    window._load_timer.stop()
    starts = []
    monkeypatch.setattr(
        window.thread_pool, "start", lambda worker, *args: starts.append(worker)
    )

    window.attempt_table.selectRow(0)
    window.attempt_table.selectRow(1)

    assert window._load_timer.isActive()
    assert starts == []
    window._load_timer.stop()
    window._dispatch_attempt_load()
    assert len(starts) == 1
    assert starts[0].attempt.key == window.current_attempt.key

    data = load_attempt_data(window.current_attempt, "rx-1")
    key = window._cache_key(window.current_attempt, "rx-1")
    window._cache_put(key, data)
    starts.clear()
    window._pending_receiver = "rx-1"
    window._dispatch_attempt_load()

    assert starts == []
    assert window._current_data is data
    window.close()


def test_cancelling_load_invalidates_queued_results(session_factory, application):
    root = session_factory(attempts=((1, 1, "accepted"),))
    window = SessionInspectorWindow(root)
    window._load_timer.stop()
    attempt = window.session.attempts[0]
    data = load_attempt_data(attempt, "rx-1")
    token = window._load_token

    window._clear_attempt()
    window._attempt_data_loaded(token, data)

    assert window._current_data is None
    assert window.values_tab.data is None
    assert window.signals_tab.data is None
    window.close()
