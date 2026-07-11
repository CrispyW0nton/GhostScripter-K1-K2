"""Focused tests for the readSave MCP tool.

These fixtures use real PyKotor writers so the handler is exercised against
the same GFF/ERF structures as a retail save without requiring a game install.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pykotor = pytest.importorskip("pykotor")


def _call(save_path: Path | str, game: str = "K1") -> dict:
    from ghostscripter.mcp.tools import handle_tool

    result = asyncio.run(handle_tool("readSave", {
        "game": game,
        "save_path": str(save_path),
    }))
    return json.loads(result[0].text)


def _write_save_info(folder: Path) -> None:
    from pykotor.common.misc import ResRef
    from pykotor.extract.savedata import SaveInfo

    info = SaveInfo(folder)
    info.area_name = ""  # A present, genuinely empty field must remain empty.
    info.last_module = "zero_module"
    info.savegame_name = "Zero Test"
    info.time_played = 0
    info.cheat_used = False
    info.gameplay_hint = 0
    info.story_hint = 0
    info.portrait0 = ResRef("po_zero")
    info.save()


def _write_party_table(folder: Path) -> None:
    from pykotor.resource.formats.gff import GFF, GFFContent, GFFList, write_gff

    gff = GFF(GFFContent.PT)
    root = gff.root
    root.set_uint32("PT_GOLD", 0)
    root.set_int32("PT_XP_POOL", 0)
    root.set_uint32("PT_PLAYEDSECONDS", 0)
    root.set_uint8("PT_NUM_MEMBERS", 1)
    # This is the actual 16-character retail label.  In particular, zero must
    # not be changed to None by truthiness-based fallbacks.
    root.set_int32("PT_CONTROLLED_NP", 0)
    root.set_uint8("PT_SOLOMODE", 0)
    root.set_uint8("PT_CHEAT_USED", 0)

    members = GFFList()
    member = members.add(0)
    member.set_uint8("PT_IS_LEADER", 1)
    member.set_int32("PT_MEMBER_ID", 0)
    root.set_list("PT_MEMBERS", members)

    available = GFFList()
    npc = available.add(0)
    npc.set_uint8("PT_NPC_AVAIL", 1)
    npc.set_uint8("PT_NPC_SELECT", 1)
    root.set_list("PT_AVAIL_NPCS", available)
    write_gff(gff, folder / "PARTYTABLE.res")


def _write_globals(folder: Path) -> None:
    from pykotor.extract.savedata import GlobalVars

    save_globals = GlobalVars(folder)
    save_globals.global_bools = [("BOOL_ZERO", False)]
    save_globals.global_numbers = [("NUMBER_ZERO", 0)]
    save_globals.global_strings = []
    save_globals.global_locs = []
    save_globals.save()


def _write_save_archive(folder: Path) -> None:
    from pykotor.resource.formats.erf import ERF, ERFType, bytes_erf, write_erf
    from pykotor.resource.type import ResourceType

    # PyKotor's current ERF writer expects the unsigned on-disk sentinel.
    cached_module = ERF(ERFType.SAV, description_strref=0xFFFFFFFF)
    outer = ERF(ERFType.SAV, description_strref=0xFFFFFFFF)
    outer.set_data("zero_module", ResourceType.SAV, bytes_erf(cached_module, ResourceType.SAV))
    # readSave inventories this resource but deliberately does not pretend to
    # resolve its TLK-backed character name.
    outer.set_data("availnpc0", ResourceType.UTC, b"synthetic raw utc")
    write_erf(outer, folder / "SAVEGAME.sav", ResourceType.SAV)


def _write_complete_save(folder: Path) -> None:
    folder.mkdir(parents=True)
    _write_save_info(folder)
    _write_party_table(folder)
    _write_globals(folder)
    _write_save_archive(folder)


def test_read_save_parses_components_and_preserves_zero_values(tmp_path: Path) -> None:
    save_folder = tmp_path / "000001 - Zero Test"
    _write_complete_save(save_folder)

    data = _call(save_folder)

    assert "error" not in data
    assert data["completeness"] == {
        "status": "complete",
        "loaded_components": ["save_info", "party_table", "global_vars", "save_archive"],
        "missing_components": [],
        "errors": [],
        "warnings": [],
    }
    assert data["save_name"] == "Zero Test"
    assert data["area_name"] == ""
    assert data["time_played_secs"] == 0
    assert data["cheat_used"] is False
    assert data["gameplay_hint"] == 0
    assert data["story_hint"] == 0
    assert data["party_members"] == [{"index": 0, "is_leader": True}]
    assert data["party"]["controlled_npc_index"] == 0
    assert data["party"]["gold"] == 0
    assert data["party"]["xp_pool"] == 0
    assert data["party"]["solo_mode"] is False
    assert data["global_count"] == 2
    assert data["globals"]["counts"] == {
        "booleans": 1,
        "numbers": 1,
        "strings": 0,
        "locations": 0,
    }
    assert data["module_snapshots"] == ["zero_module"]
    assert data["nested_resource_count"] == 2
    assert data["character_resources"] == ["availnpc0.utc"]


def test_read_save_reports_missing_components_without_fabricated_empties(tmp_path: Path) -> None:
    save_folder = tmp_path / "partial"
    save_folder.mkdir()
    _write_save_info(save_folder)

    data = _call(save_folder)

    assert data["completeness"]["status"] == "partial"
    assert data["completeness"]["loaded_components"] == ["save_info"]
    assert data["completeness"]["missing_components"] == [
        "party_table",
        "global_vars",
        "save_archive",
    ]
    assert data["party_members"] is None
    assert data["party"] is None
    assert data["global_count"] is None
    assert data["globals"] is None
    assert data["module_snapshots"] is None
    assert data["nested_resource_count"] is None
    assert data["character_resources"] is None


def test_read_save_reports_component_parse_errors(tmp_path: Path) -> None:
    save_folder = tmp_path / "damaged"
    save_folder.mkdir()
    _write_save_info(save_folder)
    (save_folder / "GLOBALVARS.res").write_bytes(b"not a gff")

    data = _call(save_folder)

    assert data["completeness"]["status"] == "partial"
    assert data["global_count"] is None
    assert data["globals"] is None
    assert data["completeness"]["errors"][0]["component"] == "global_vars"
    assert "global_vars" not in data["completeness"]["missing_components"]


def test_read_save_resolves_relative_slot_below_loaded_game(tmp_path: Path) -> None:
    install = tmp_path / "game"
    save_folder = install / "saves" / "RELATIVE_SLOT"
    _write_complete_save(save_folder)
    manager = MagicMock()
    manager._game_dir = install

    with patch(
        "ghostscripter.mcp.tools_pkg.handlers_read._load_rm",
        return_value=manager,
    ):
        data = _call("RELATIVE_SLOT")

    assert "error" not in data
    assert data["completeness"]["status"] == "complete"
    assert Path(data["save_path"]) == save_folder.resolve()


def test_read_save_tool_description_has_no_stub_claims() -> None:
    from ghostscripter.mcp.tools import TOOLS

    tool = next(tool for tool in TOOLS if tool.name == "readSave")
    assert "stub" not in tool.description.casefold()
    assert "completeness" in tool.description.casefold()
