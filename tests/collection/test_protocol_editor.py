"""The operator's editor of the remaining protocol, with real offscreen widgets."""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtWidgets
from test_controller import FakeClock
from test_protocol_revision import controller, record_and_accept, source

from fall_detection.apps.common.dashboard import CsiDashboardPanel
from fall_detection.apps.sessions.collector.views.operator import OperatorWindow
from fall_detection.apps.sessions.collector.views.protocol_editor import (
    MIXED,
    ProtocolEditorDialog,
)
from fall_detection.apps.sessions.collector.views.protocol_sources import (
    AddScenariosDialog,
    NewScenarioDialog,
    SaveProtocolDialog,
)
from fall_detection.collection.capture import SessionMetadata
from fall_detection.collection.controller import HealthSnapshot, OperatorCommand
from fall_detection.protocol.loader import load_protocol, protocol_from_mapping
from fall_detection.protocol.model import ProtocolError
from fall_detection.protocol.revision import DraftTrial
from fall_detection.radio.state import LiveState


@pytest.fixture(scope="module")
def qt_app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def editor(locked=1):
    return ProtocolEditorDialog(
        QtCore,
        QtWidgets,
        protocol_from_mapping(source()),  # walk 1, walk 2, sit, fall
        locked=locked,
        revision=1,
    )


def select(dialog, rows):
    dialog.table.clearSelection()
    model = dialog.table.selectionModel()
    flags = QtCore.QItemSelectionModel.SelectionFlag
    for row in rows:
        model.select(dialog.table.model().index(row, 0), flags.Select | flags.Rows)


def order(dialog):
    return [dialog.table.item(row, 1).text() for row in range(dialog.table.rowCount())]


def test_fixed_trials_cannot_be_selected(qt_app):
    dialog = editor(locked=2)
    select(dialog, [0, 1, 2])
    assert dialog.selected_rows() == [2]
    assert dialog.table.item(0, 5).text() == "fixed"
    assert not dialog.save_button.isEnabled()


def test_queue_operations_reorder_duplicate_and_remove(qt_app):
    dialog = editor()
    select(dialog, [3])
    dialog.buttons["next"].click()
    assert order(dialog) == ["Walk", "Fall", "Walk", "Sit"]
    assert dialog.selected_rows() == [1]
    dialog.buttons["duplicate"].click()
    assert order(dialog) == ["Walk", "Fall", "Fall", "Walk", "Sit"]
    assert dialog.table.item(2, 5).text() == "new"
    select(dialog, [4])
    dialog.buttons["remove"].click()
    select(dialog, [3])
    dialog.buttons["up"].click()
    dialog.buttons["up"].click()
    # The first editable place is a hard stop.
    dialog.buttons["up"].click()
    assert order(dialog) == ["Walk", "Walk", "Fall", "Fall"]
    assert "removed 1 trial(s): 3" in dialog.summary.text()
    assert dialog.save_button.isEnabled()

    edit = dialog.build()

    assert [t.scenario.id for t in edit.protocol.trials] == [
        "walk",
        "walk",
        "fall",
        "fall",
    ]
    assert "added 1 more trial(s) of scenarios already in the protocol" in edit.changes


def test_field_edits_apply_to_every_selected_trial(qt_app):
    dialog = editor()
    select(dialog, [1, 3])
    label = dialog.editors["activity_label"].lineEdit()
    assert label.text() == "" and label.placeholderText() == MIXED
    label.setText("transition")
    label.textEdited.emit("transition")
    dialog.editors["action_seconds"].setText("3.5")
    dialog.editors["action_seconds"].textEdited.emit("3.5")
    dialog.note.setText("participant tires quickly")
    select(dialog, [2])  # changing the selection commits the fields first

    assert dialog.table.item(1, 2).text() == "transition"
    assert dialog.table.item(3, 4).text() == "1 / 3.5 / 1 s"
    assert dialog.table.item(2, 2).text() == "sit"
    edit = dialog.build()
    trials = edit.protocol.trials
    # Walk 2 forks because walk 1 is recorded; fall is edited in place.
    assert trials[1].scenario.id == "walk__rev1"
    assert (trials[3].scenario.id, trials[3].scenario.activity_label) == (
        "fall",
        "transition",
    )
    assert edit.note == "participant tires quickly"


def test_invalid_field_values_are_explained_and_block_saving(qt_app):
    dialog = editor()
    select(dialog, [2])
    dialog.editors["action_seconds"].setText("0")
    dialog.editors["action_seconds"].textEdited.emit("0")
    with pytest.raises(ProtocolError, match="greater than zero"):
        dialog.build()
    assert dialog.error.isVisibleTo(dialog.dialog)
    dialog._reset()
    assert dialog.build() is None  # nothing changed


def test_operator_window_edits_only_between_trials_and_shows_revisions(
    qt_app, tmp_path
):
    from fall_detection.protocol.revision import draft_queue, revise_protocol

    clock = FakeClock()
    c = controller(tmp_path, clock)
    c.start_session(SessionMetadata("p01"))
    snapshot = c.update_health(
        HealthSnapshot(radio_live=True, storage_ready=True, clock_sync_ready=True)
    )
    edits = []
    window = OperatorWindow(
        QtCore,
        QtWidgets,
        protocol=c.protocol,
        profile_text="profile test",
        panel=CsiDashboardPanel(LiveState(50), fps=24),
        on_command=lambda command: None,
        on_edit_protocol=lambda: edits.append(True),
    )
    try:

        def show(snapshot):
            window.apply(
                snapshot,
                health_text="",
                metrics_text="",
                metrics_tooltip="",
                radio_detail="",
            )

        show(snapshot)
        assert window.edit_protocol_button.isEnabled()
        window.edit_protocol_button.click()
        assert edits == [True]
        record_and_accept(c, clock)
        queue = draft_queue(c.protocol)
        revised = revise_protocol(
            c.protocol, [queue[0], queue[3], queue[1], queue[2]], locked=1, revision=1
        )
        snapshot = c.revise_protocol(revised)
        window.set_protocol(c.protocol)
        show(snapshot)
        assert window.trial_list.item(1).text().startswith("▶ 002  Fall")
        snapshot = c.dispatch(OperatorCommand.START_TRIAL)
        show(snapshot)
        assert not window.edit_protocol_button.isEnabled()
    finally:
        window.window.close()
        c.dispatch(OperatorCommand.END_SESSION)


def write_other(path):
    from test_protocol_revision import other_protocol

    path.write_text(json.dumps(other_protocol().source))
    return path


def test_add_from_protocol_lists_sources_and_inserts_after_the_selection(
    qt_app, tmp_path
):
    folder = tmp_path / "protocols"
    folder.mkdir()
    other = write_other(folder / "other.json")
    starting = tmp_path / "protocol.json"
    starting.write_text(json.dumps(protocol_from_mapping(source()).source))
    dialog = editor()
    picker = AddScenariosDialog(
        QtCore,
        QtWidgets,
        sources=[("This session's starting protocol", starting)],
        protocol_dir=folder,
        known=dialog.known_scenarios(),
    )
    items = [
        picker.source_combo.itemText(i) for i in range(picker.source_combo.count())
    ]
    assert len(items) == 2 and items[0].startswith("This session's starting protocol")
    # Scenarios of the starting protocol are already in the session.
    sit = picker.tree.topLevelItem(0).child(1)
    assert (sit.text(0), sit.text(3)) == ("Sit", "already in session")

    picker.source_combo.setCurrentIndex(picker.source_combo.findData(str(other)))
    block = picker.tree.topLevelItem(0)
    block.setCheckState(0, QtCore.Qt.CheckState.Checked)  # checks both children
    picker.count.setValue(2)
    chosen = picker.chosen()
    assert [(scenario.id, count) for scenario, count in chosen] == [
        ("walk", 2),
        ("kneel", 2),
    ]
    assert "adds 4 trial(s)" in picker.summary.text()

    select(dialog, [1])
    dialog.add_scenarios(picker.protocol, chosen)

    assert order(dialog) == [
        "Walk",
        "Walk",
        "Fast walk",
        "Fast walk",
        "Kneel",
        "Kneel",
        "Sit",
        "Fall",
    ]
    assert dialog.table.item(2, 5).text() == "new"
    assert dialog.selected_rows() == [2, 3, 4, 5]
    assert "added 4 trial(s) of 2 new scenario(s)" in dialog.summary.text()
    edit = dialog.build()
    assert edit.protocol.trials[2].scenario.id == "walk__other"


def test_new_scenario_dialog_builds_a_scenario_in_a_chosen_block(qt_app):
    dialog = editor()
    form = NewScenarioDialog(
        QtWidgets,
        known=dialog.known_scenarios(),
        defaults=dialog.protocol.defaults,
    )
    blocks = [form.block.itemData(i) for i in range(form.block.count())]
    assert blocks == [
        ("added", "Added scenarios"),
        ("a", "Block A"),
        ("b", "Block B"),
    ]
    with pytest.raises(ProtocolError, match="title cannot be empty"):
        form.build()
    form.title.setText("Lie down")
    form.label.setCurrentText("lie")
    form.instruction.setText("Lie on the mattress")
    form.timings["action_seconds"].setValue(6)
    form.count.setValue(3)

    scenario, count = form.build()

    assert (scenario.id, scenario.block_id, count) == ("custom__lie_down", "added", 3)
    assert scenario.action_seconds == 6.0
    dialog.table.clearSelection()  # without a selection, trials go to the end
    dialog.insert([DraftTrial(scenario) for _ in range(count)])
    edit = dialog.build()
    assert edit.protocol.blocks[-1][:2] == ("added", "Added scenarios")
    assert [t.scenario.id for t in edit.protocol.trials[-3:]] == [
        "custom__lie_down"
    ] * 3


def test_queue_is_saved_as_a_new_protocol_file(qt_app, tmp_path):
    dialog = editor()
    dialog.session_id = "20261126T101010000000Z"
    select(dialog, [3])
    dialog.buttons["next"].click()
    path = tmp_path / "revisable-short.json"

    saved = dialog.export(protocol_id="revisable-short", title="Short", path=path)

    assert load_protocol(path).source_hash == saved.source_hash
    assert [t.scenario.id for t in saved.trials] == ["walk", "fall", "walk", "sit"]
    derived = saved.source["derived_from"]
    assert derived["protocol_id"] == "revisable"
    assert derived["protocol_hash"] == dialog.protocol.source_hash
    assert derived["session_id"] == "20261126T101010000000Z"
    assert dialog.saved_files == [path.resolve()]
    # Saving a file changes nothing in the session's revision.
    assert dialog.build().protocol.protocol_id == "revisable"


def test_save_protocol_dialog_requires_a_new_id_and_a_json_file(qt_app, tmp_path):
    form = SaveProtocolDialog(
        QtWidgets, protocol_from_mapping(source()), folder=tmp_path, trials=4
    )
    assert form.values() == (
        "Revisable protocol (edited)",
        "revisable-edited",
        tmp_path / "revisable-edited.json",
    )
    form.protocol_id.setText("short")
    form.protocol_id.textEdited.emit("short")
    assert form.path.text() == str(tmp_path / "short.json")
    for field, value, message in (
        (form.protocol_id, "revisable", "new protocol id"),
        (form.protocol_id, "bad id", "may contain"),
        (form.path, str(tmp_path / "short.txt"), "end in .json"),
        (form.path, str(tmp_path / "missing/short.json"), "does not exist"),
    ):
        previous = field.text()
        field.setText(value)
        with pytest.raises(ProtocolError, match=message):
            form.values()
        field.setText(previous)
