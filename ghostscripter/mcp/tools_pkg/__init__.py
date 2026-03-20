"""GhostScripter MCP tools package.

Public API:
  TOOLS        list[types.Tool]   — tool schemas for list_tools()
  handle_tool  async callable     — dispatch by name for call_tool()
  _HANDLERS    dict               — name → handler mapping

Import this package instead of the legacy tools.py shim whenever
adding new functionality.
"""
from __future__ import annotations

from typing import List

import mcp.types as types

from ghostscripter.mcp.tools_pkg.tool_defs import TOOLS
from ghostscripter.mcp.tools_pkg._helpers import (
    _INSTALLS, _2DA_CACHE, _err, _load_rm, _normalize_game,
    _ok, _safe_write_path, log,
)
from ghostscripter.mcp.tools_pkg.handlers_read import (
    _detect_installations, _load_installation, _list_resources,
    _describe_resource, _read_gff, _read_dlg, _read_twoda,
    _read_tlk, _read_journal, _search_nwscript, _nwscript_signature,
    _read_pth, _read_ltr, _read_gui, _read_save,
    _read_ncs, _read_vis, _read_ifo, _read_wav, _read_txi, _pathfind_route,
    _get_nwscript_db,
)
from ghostscripter.mcp.tools_pkg.handlers_write import (
    _write_gff, _write_dlg, _write_twoda, _write_erf,
    _compile_script, _decompile_script, _write_override, _write_lip, _write_ssf, _write_pth,
)
from ghostscripter.mcp.tools_pkg.handlers_query import (
    _compile_summary, _search_resources, _module_overview,
    _twoda_lookup, _nwscript_categories, _twoda_changes_ini,
    _search_all, _read_ssf, _read_lip,
)
from ghostscripter.mcp.tools_pkg.handlers_composite import (
    _get_resource, _get_quest, _get_npc, _get_script, _list_res_type,
    _get_area, _get_door, _get_placeable, _get_item,
    _get_module, _get_encounter, _get_trigger, _get_waypoint,
    _get_store, _get_sound, _get_creature, _get_faction,
    _get_blueprint,
)


async def handle_tool(name: str, arguments: dict) -> List[types.TextContent]:
    """Dispatch a tool call by name."""
    try:
        handler = _HANDLERS.get(name)
        if handler is None:
            return _err(f"Unknown tool: {name!r}")
        return await handler(arguments)
    except FileNotFoundError as e:
        return _err(str(e))
    except Exception as e:
        log.exception(f"Tool {name} failed")
        return _err(f"Internal error in {name}: {e}")


# ─── Handlers ─────────────────────────────────────────────────────────────────



_HANDLERS = {
    # Prefixed names (canonical — avoids KotorMCP collisions, see SYSTEMS_DESIGN §Tool Namespace Policy)
    "gsDetectInstallations": _detect_installations,
    "gsLoadInstallation": _load_installation,
    "gsListResources": _list_resources,
    "gsDescribeResource": _describe_resource,
    # Legacy aliases kept for backward compatibility (deprecated — will be removed in v3.1)
    "detectInstallations": _detect_installations,
    "loadInstallation": _load_installation,
    "listResources": _list_resources,
    "describeResource": _describe_resource,
    "readGFF": _read_gff,
    "readDLG": _read_dlg,
    "readTwoDA": _read_twoda,
    "readTLK": _read_tlk,
    "readJournal": _read_journal,
    "journalOverview": _read_journal,  # alias
    "searchNWScript": _search_nwscript,
    "nwscriptSignature": _nwscript_signature,
    "writeGFF": _write_gff,
    "writeDLG": _write_dlg,
    "writeTwoDA": _write_twoda,
    "writeERF": _write_erf,
    "compileScript": _compile_script,
    "decompileScript": _decompile_script,
    "writeOverride": _write_override,
    "compileSummary": _compile_summary,
    "searchResources": _search_resources,
    "moduleOverview": _module_overview,
    "twoDALookup": _twoda_lookup,
    "nwscriptCategories": _nwscript_categories,
    "twoDAChangesINI": _twoda_changes_ini,
    # Ghostworks Pipeline composite tools
    "getResource": _get_resource,
    "getQuest": _get_quest,
    "getNpc": _get_npc,
    "getScript": _get_script,
    "listResType": _list_res_type,
    "getArea": _get_area,
    "getDoor": _get_door,
    "getPlaceable": _get_placeable,
    "getItem": _get_item,
    "searchAll": _search_all,
    "getModule": _get_module,
    "getEncounter": _get_encounter,
    "getTrigger": _get_trigger,
    "getWaypoint": _get_waypoint,
    "getStore": _get_store,
    "getSound": _get_sound,
    "readSSF": _read_ssf,
    # v2.9 additions
    "readLIP": _read_lip,
    "writeLIP": _write_lip,
    "getCreature": _get_creature,
    # v3.0 additions
    "getFaction": _get_faction,
    # v3.2 additions
    "readPTH": _read_pth,
    "readLTR": _read_ltr,
    "writeSSF": _write_ssf,
    "writePTH": _write_pth,
    "getBlueprint": _get_blueprint,
    "readGUI": _read_gui,
    "readSave": _read_save,
    # v3.3 additions
    "readNCS": _read_ncs,
    "readVIS": _read_vis,
    "readIFO": _read_ifo,
    "readWAV": _read_wav,
    "readTXI": _read_txi,
    "pathfindRoute": _pathfind_route,
    # v3.6 additions
    "getNWScriptDB": _get_nwscript_db,
}
