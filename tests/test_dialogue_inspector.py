"""Qt regressions for the dialogue node inspector's model synchronization."""

from __future__ import annotations

import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qtpy.QtCore import Qt
    from qtpy.QtWidgets import QApplication
except Exception as exc:  # pragma: no cover - depends on optional GUI runtime
    pytest.skip(f"Qt unavailable: {exc}", allow_module_level=True)

from ghostscripter.core.export.dlg_reader import DLGImporter
from ghostscripter.core.export.dlg_writer import DLGExporter
from ghostscripter.core.models.dialogue import (
    DLGAnimation,
    DialogueBranch,
    DialogueNode,
    create_simple_dialogue,
)
from ghostscripter.ui.widgets.dialogue_editor_widget import NodeInspector


@pytest.fixture(scope="module")
def qapp():
    """Keep one application alive for every off-screen inspector test."""
    return QApplication.instance() or QApplication([])


def test_controls_connect_once_and_pending_edit_flushes_before_node_switch(qapp) -> None:
    first = DialogueNode(node_id=0, node_type="entry", speaker="old", text="old")
    second = DialogueNode(node_id=1, node_type="entry", speaker="second")
    inspector = NodeInspector()
    inspector.load_node(first)

    # Calling the idempotent helper again must not stack another connection.
    receivers_before = inspector.speaker_input.receivers(
        inspector.speaker_input.textChanged
    )
    inspector._connect_all()
    assert inspector.speaker_input.receivers(
        inspector.speaker_input.textChanged
    ) == receivers_before

    inspector.speaker_input.setText("edited_speaker")
    inspector.text_input.setPlainText("edited text")
    inspector.script1_input.setText("edit_action")
    inspector.quest_entry_spin.setValue(27)
    inspector.record_vo_chk.setChecked(True)

    # This was false before the signal-wiring fix: controls changed visually,
    # but no save was scheduled and the model stayed untouched.
    assert inspector._save_timer.isActive()
    assert first.text == "old"

    # Selecting another node is a common immediate action.  It must commit the
    # old node before load_node changes the inspector's model target.
    inspector.load_node(second)
    assert first.speaker == "edited_speaker"
    assert first.text == "edited text"
    assert first.script1 == "edit_action"
    assert first.quest_entry == 27
    assert first.record_vo is True

    inspector.close()


def test_table_and_link_comment_edits_update_existing_model_objects(qapp) -> None:
    raw_animation = object()
    raw_branch = object()
    animation = DLGAnimation(participant="PLAYER", animation_id=1)
    animation._raw_gff = raw_animation
    branch = DialogueBranch(target_node_id=-1, link_comment="before")
    branch._raw_gff = raw_branch
    node = DialogueNode(
        node_id=0,
        node_type="reply",
        animations=[animation],
        branches=[branch],
    )
    inspector = NodeInspector()
    inspector.load_node(node)

    inspector.anim_table.item(0, 0).setText("NPC_TEST")
    inspector.anim_table.item(0, 1).setText("42")
    inspector.branch_table.item(0, 1).setText("k_cond")
    inspector.branch_table.item(0, 2).setCheckState(Qt.Checked)
    inspector.branch_table.item(0, 3).setText("k_cond2")
    inspector.branch_table.item(0, 4).setCheckState(Qt.Checked)
    inspector.link_comment_input.setText("edited branch")

    assert node.animations[0] is animation
    assert animation._raw_gff is raw_animation
    assert (animation.participant, animation.animation_id) == ("NPC_TEST", 42)
    assert node.branches[0] is branch
    assert branch._raw_gff is raw_branch
    assert branch.target_node_id == -1
    assert branch.active_script == "k_cond"
    assert branch.active_script2 == "k_cond2"
    assert branch.is_child is True
    assert branch.display_inactive is True
    assert branch.link_comment == "edited branch"

    inspector.close()


def test_inspector_edits_survive_k2_binary_save_and_reload(qapp) -> None:
    dialogue = create_simple_dialogue("inspector_rt", "npc_original")
    entry = dialogue.entries[0]
    inspector = NodeInspector()
    inspector.load_node(entry)

    inspector.speaker_input.setText("npc_edited")
    inspector.listener_input.setText("Player")
    inspector.text_input.setPlainText("A real edited line.")
    inspector.script1_input.setText("k_edit_action")
    inspector.s1p1_spin.setValue(11)
    inspector.vo_input.setText("vo_edit_01")
    inspector.sound_input.setText("snd_edit_01")
    inspector.sound_exists_chk.setChecked(True)
    inspector.cam_id_spin.setValue(7)
    inspector.emotion_spin.setValue(3)
    inspector.record_vo_chk.setChecked(True)

    inspector._add_anim_row()
    inspector.anim_table.item(0, 0).setText("NPC_EDITED")
    inspector.anim_table.item(0, 1).setText("123")
    inspector.branch_table.item(0, 1).setText("k_show_reply")
    inspector.branch_table.item(0, 3).setText("k_show_reply2")
    inspector.branch_table.item(0, 4).setCheckState(Qt.Checked)
    inspector.link_comment_input.setText("round-trip link")

    # Save can be clicked within the 80 ms debounce window; force the same
    # synchronous commit used by the editor's Export action.
    assert inspector._save_timer.isActive()
    inspector.flush_pending_changes()

    saved = DLGExporter().export(dialogue, target_game="K2")
    reloaded = DLGImporter().import_from_bytes(saved)
    result = reloaded.entries[0]
    result_branch = result.branches[0]

    assert result.speaker == "npc_edited"
    assert result.listener == "Player"
    assert result.text == "A real edited line."
    assert result.script1 == "k_edit_action"
    assert result.script1_param1 == 11
    assert result.vo_resref == "vo_edit_01"
    assert result.sound == "snd_edit_01"
    assert result.sound_exists == 1
    assert result.camera_id == 7
    assert result.emotion_id == 3
    assert result.record_vo is True
    assert [(a.participant, a.animation_id) for a in result.animations] == [
        ("NPC_EDITED", 123)
    ]
    assert result_branch.active_script == "k_show_reply"
    assert result_branch.active_script2 == "k_show_reply2"
    assert result_branch.display_inactive is True
    assert result_branch.link_comment == "round-trip link"

    inspector.close()
