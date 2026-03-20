"""GhostScripter MCP tools — backward-compatibility shim.

This module previously contained all 2,500+ lines of tool handlers.
As of v2.6.0 the code has been reorganised into the ``tools_pkg`` sub-package:

    ghostscripter/mcp/tools_pkg/
        _helpers.py           — shared state, utilities (_ok, _err, _load_rm …)
        tool_defs.py          — TOOLS list (34 MCP tool schemas)
        handlers_read.py      — read-only handlers
        handlers_write.py     — write / compile handlers
        handlers_query.py     — search, lookup, analysis handlers
        handlers_composite.py — composite game-object handlers (getQuest, …)
        __init__.py           — re-exports + handle_tool + _HANDLERS

This shim re-exports every name that external code (tests, server.py) needs
so that all existing ``from ghostscripter.mcp.tools import X`` calls continue
to work without modification.
"""
from __future__ import annotations

# ── Re-export the full public API from the new package ────────────────────────
from ghostscripter.mcp.tools_pkg import (       # noqa: F401
    TOOLS,
    handle_tool,
    _HANDLERS,
)
from ghostscripter.mcp.tools_pkg._helpers import (   # noqa: F401
    _INSTALLS,
    _2DA_CACHE,
    _DEFAULT_PATHS,
    _normalize_game,
    _validate_resref,
    _safe_write_path,
    _find_game_path,
    _load_rm,
    _ok,
    _err,
    _prune,
    log,
)
from ghostscripter.mcp.tools_pkg.handlers_read import (   # noqa: F401
    _detect_installations,
    _load_installation,
    _list_resources,
    _describe_resource,
    _read_gff,
    _prune,            # also lives in read module
    _read_dlg,
    _read_twoda,
    _read_tlk,
    _read_journal,
    _search_nwscript,
    _nwscript_signature,
)
from ghostscripter.mcp.tools_pkg.handlers_write import (  # noqa: F401
    _write_gff,
    _write_dlg,
    _write_twoda,
    _write_erf,
    _compile_script,
    _write_override,
)
from ghostscripter.mcp.tools_pkg.handlers_query import (  # noqa: F401
    _compile_summary,
    _search_resources,
    _module_overview,
    _twoda_lookup,
    _nwscript_categories,
    _twoda_changes_ini,
    _search_all,
    _read_ssf,
)
from ghostscripter.mcp.tools_pkg.handlers_composite import (  # noqa: F401
    _get_resource,
    _get_quest,
    _get_npc,
    _get_script,
    _list_res_type,
    _get_area,
    _get_door,
    _get_placeable,
    _get_item,
    _get_module,
    _get_encounter,
    _get_trigger,
    _get_waypoint,
    _get_store,
    _get_sound,
    _try_decompile_ncs,
)
