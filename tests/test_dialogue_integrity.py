"""P0 dialogue integrity regressions: END links, typed deletion, K2 fidelity."""

from __future__ import annotations

import pytest

from ghostscripter.core.export.dlg_reader import DLGImporter, GFF3Reader
from ghostscripter.core.export.dlg_writer import DLGExporter, DLGFidelityError
from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct
from ghostscripter.core.models.dialogue import (
    DialogueBranch,
    DialogueFile,
    DialogueNode,
    END_NODE_ID,
    create_simple_dialogue,
)


def test_starter_dialogue_end_link_roundtrips_as_dword_sentinel() -> None:
    """The factory dialogue's Reply→END must never turn into Reply→Entry 0."""
    dialogue = create_simple_dialogue("end_sentinel", "npc_test")
    assert dialogue.replies[0].branches[0].target_node_id == END_NODE_ID

    first_bytes = DLGExporter().export(dialogue, "K1")
    first_gff = GFF3Reader(first_bytes).parse()
    assert (
        first_gff["ReplyList"][0]["EntriesList"][0]["Index"]
        == 0xFFFFFFFF
    )

    imported = DLGImporter().import_from_bytes(first_bytes)
    end_branch = imported.replies[0].branches[0]
    assert end_branch.target_node_id == END_NODE_ID
    assert end_branch.is_end

    second_bytes = DLGExporter().export(imported, "K1")
    second_gff = GFF3Reader(second_bytes).parse()
    assert (
        second_gff["ReplyList"][0]["EntriesList"][0]["Index"]
        == 0xFFFFFFFF
    )


def _typed_deletion_fixture() -> DialogueFile:
    dialogue = DialogueFile(name="typed_delete")
    dialogue.entries = [
        DialogueNode(node_id=0, node_type="entry", text="entry zero"),
        DialogueNode(node_id=1, node_type="entry", text="entry one"),
    ]
    dialogue.replies = [
        DialogueNode(node_id=0, node_type="reply", text="reply zero"),
        DialogueNode(node_id=1, node_type="reply", text="reply one"),
    ]
    dialogue.entries[0].branches = [DialogueBranch(target_node_id=0)]
    dialogue.entries[1].branches = [DialogueBranch(target_node_id=1)]
    dialogue.replies[0].branches = [DialogueBranch(target_node_id=0)]
    dialogue.replies[1].branches = [DialogueBranch(target_node_id=1)]
    dialogue.starters = [
        DialogueBranch(branch_id=0, target_node_id=0),
        DialogueBranch(branch_id=1, target_node_id=1),
    ]
    return dialogue


def test_remove_entry_zero_keeps_reply_zero_and_repairs_only_entry_targets() -> None:
    dialogue = _typed_deletion_fixture()

    dialogue.remove_node(0, "entry")

    assert [node.text for node in dialogue.entries] == ["entry one"]
    assert [node.node_id for node in dialogue.entries] == [0]
    assert [node.text for node in dialogue.replies] == ["reply zero", "reply one"]
    assert [node.node_id for node in dialogue.replies] == [0, 1]

    # Entry branches target replies, so their IDs do not shift.
    assert dialogue.entries[0].branches[0].target_node_id == 1
    # Reply branches and starters target entries: deleted refs disappear and
    # refs above the removed list index shift down.
    assert dialogue.replies[0].branches == []
    assert dialogue.replies[1].branches[0].target_node_id == 0
    assert [branch.target_node_id for branch in dialogue.starters] == [0]


def test_remove_node_without_type_refuses_ambiguous_entry_reply_id() -> None:
    dialogue = _typed_deletion_fixture()

    with pytest.raises(ValueError, match="ambiguous"):
        dialogue.remove_node(0)

    assert len(dialogue.entries) == 2
    assert len(dialogue.replies) == 2


def _synthetic_k2_conditional_stunt_dlg() -> bytes:
    writer = GFF3Writer("DLG ")
    root = writer.root

    root.add_resref("EndConversation", "k_end")
    root.add_resref("EndConverAbort", "k_abort")
    root.add_byte("Skippable", 1)
    root.add_dword("DelayEntry", 0)
    root.add_dword("DelayReply", 0)
    root.add_dword("NumWords", 37)
    root.add_cexo("VO_ID", "k2_voice_set")
    root.add_int("AlienRaceOwner", 2)
    root.add_int("PostProcOwner", 3)
    root.add_int("RecordNoVO", 1)
    root.add_int("NextNodeID", 91)
    root.add_cexo("FutureRootData", "must survive")

    stunt = GFFStruct(6)
    stunt.add_cexo("Participant", "KREIA")
    stunt.add_resref("StuntModel", "stunt_01")
    stunt.add_int("FutureStuntData", 42)
    root.add_list("StuntList", [stunt])

    entry_to_reply = GFFStruct(0)
    entry_to_reply.add_dword("Index", 0)
    entry_to_reply.add_resref("Active", "c_active_one")
    entry_to_reply.add_resref("Active2", "c_active_two")
    entry_to_reply.add_int("Logic", 1)
    entry_to_reply.add_byte("Not", 1)
    entry_to_reply.add_byte("Not2", 0)
    entry_to_reply.add_int("Param1", 123)
    entry_to_reply.add_int("Param5b", 987)
    entry_to_reply.add_cexo("ParamStrA", "alpha")
    entry_to_reply.add_cexo("ParamStrB", "beta")
    entry_to_reply.add_byte("DisplayInactive", 1)
    entry_to_reply.add_byte("IsChild", 0)

    entry = GFFStruct(0)
    entry.add_locstring("Text", -1, "A synthetic TSL entry")
    entry.add_cexo("Speaker", "KREIA")
    entry.add_list("AnimList", [])
    entry.add_list("RepliesList", [entry_to_reply])

    reply_to_end = GFFStruct(0)
    reply_to_end.add_dword("Index", 0xFFFFFFFF)
    reply_to_end.add_resref("Active", "c_end")
    reply_to_end.add_int("Param2", 456)

    reply = GFFStruct(0)
    reply.add_locstring("Text", -1, "End it")
    reply.add_list("AnimList", [])
    reply.add_list("EntriesList", [reply_to_end])

    starter = GFFStruct(0)
    starter.add_dword("Index", 0)
    starter.add_resref("Active", "c_starter")
    starter.add_resref("Active2", "c_starter_two")
    starter.add_int("Param3", 99)

    root.add_list("EntryList", [entry])
    root.add_list("ReplyList", [reply])
    root.add_list("StartingList", [starter])
    return writer.build()


def test_k2_stunts_root_metadata_and_link_conditionals_are_lossless() -> None:
    source = _synthetic_k2_conditional_stunt_dlg()
    source_tree = GFF3Reader(source).parse()

    dialogue = DLGImporter().import_from_bytes(source, name="synthetic_k2")
    assert dialogue.source_game == "K2"
    assert dialogue.replies[0].branches[0].target_node_id == END_NODE_ID

    # Deliberately ask for K1, matching the editor's historical stale default.
    # Imported K2 provenance must win rather than silently downgrading it.
    output = DLGExporter().export(dialogue, "K1")
    output_tree = GFF3Reader(output).parse()

    assert output_tree == source_tree
    assert output_tree["StuntList"][0]["StuntModel"] == "stunt_01"
    assert output_tree["FutureRootData"] == "must survive"
    conditional = output_tree["EntryList"][0]["RepliesList"][0]
    assert conditional["Active2"] == "c_active_two"
    assert conditional["Logic"] == 1
    assert conditional["Param1"] == 123
    assert conditional["Param5b"] == 987
    assert conditional["ParamStrA"] == "alpha"
    assert conditional["ParamStrB"] == "beta"


def test_editing_modeled_k2_link_keeps_unmodeled_conditional_parameters() -> None:
    dialogue = DLGImporter().import_from_bytes(
        _synthetic_k2_conditional_stunt_dlg(), name="synthetic_k2_edit"
    )
    dialogue.entries[0].branches[0].active_script2 = "c_changed"

    output_tree = GFF3Reader(DLGExporter().export(dialogue, "K2")).parse()
    conditional = output_tree["EntryList"][0]["RepliesList"][0]

    assert conditional["Active2"] == "c_changed"
    assert conditional["Logic"] == 1
    assert conditional["Param1"] == 123
    assert conditional["Param5b"] == 987
    assert output_tree["StuntList"][0]["FutureStuntData"] == 42


def test_save_refuses_when_import_fidelity_state_is_unavailable() -> None:
    dialogue = create_simple_dialogue("unsafe_import", "npc_test")
    dialogue._unsupported_fidelity_fields = ["typed source GFF unavailable"]

    with pytest.raises(DLGFidelityError, match="Cannot safely save"):
        DLGExporter().export(dialogue, "K2")


def test_mcp_read_json_write_roundtrip_preserves_k2_fidelity() -> None:
    """Public readDLG output must be safe to feed directly to writeDLG."""
    import asyncio
    import base64
    import json
    from unittest.mock import MagicMock, patch

    from ghostscripter.mcp.tools_pkg.handlers_read import _read_dlg
    from ghostscripter.mcp.tools_pkg.handlers_write import _write_dlg

    source = _synthetic_k2_conditional_stunt_dlg()
    resource_manager = MagicMock()
    resource_manager.read.return_value = source

    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        return_value=resource_manager,
    ):
        read_content = asyncio.run(_read_dlg({"game": "K2", "resref": "k2_fidelity"}))
    read_dto = json.loads(read_content[0].text)

    fidelity = read_dto["source_fidelity"]
    assert fidelity["schema"] == "ghostscripter.dlg.source-gff.v1"
    assert fidelity["required_for_lossless_save"] is True
    assert base64.b64decode(fidelity["binary_base64"]) == source

    write_content = asyncio.run(_write_dlg({"game": "K2", "dialogue": read_dto}))
    write_result = json.loads(write_content[0].text)
    assert "error" not in write_result

    output = base64.b64decode(write_result["data_base64"])
    assert GFF3Reader(output).parse() == GFF3Reader(source).parse()


def test_mcp_write_refuses_marked_import_when_fidelity_payload_is_missing() -> None:
    import asyncio
    import json

    from ghostscripter.core.services import DialogueService
    from ghostscripter.mcp.tools_pkg.handlers_write import _write_dlg

    dialogue = DLGImporter().import_from_bytes(
        _synthetic_k2_conditional_stunt_dlg(), name="missing_payload"
    )
    dto = DialogueService.to_dict(dialogue)
    del dto["source_fidelity"]["binary_base64"]

    content = asyncio.run(_write_dlg({"game": "K2", "dialogue": dto}))
    result = json.loads(content[0].text)

    assert "error" in result
    assert "lossless save" in result["error"]
