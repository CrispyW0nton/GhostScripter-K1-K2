"""Query, search, and analysis MCP tool handlers."""
from __future__ import annotations

from typing import Any, List

import mcp.types as types

import os
import re as _re

from ghostscripter.mcp.tools_pkg._helpers import (
    _2DA_CACHE, _err, _load_rm, _normalize_game, _ok, _validate_resref, log,
    gff_locstr, gff_scalar, read_module_resource,
)


async def _compile_summary(args: dict) -> List[types.TextContent]:
    """Static analysis of NWScript source — extract functions, includes, issues."""
    import re
    source: str = args.get("source", "")
    filename: str = args.get("filename", "<source>")

    if not source.strip():
        return _err("compileSummary: 'source' must not be empty.")

    lines = source.splitlines()
    issues: list[str] = []

    # Extract #include directives
    includes = [m.group(1) for line in lines
                for m in [re.match(r'\s*#include\s+"([^"]+)"', line)] if m]

    # Extract top-level void/int/float/string/object/location/effect/talent functions
    func_pattern = re.compile(
        r'^(?:void|int|float|string|object|location|effect|talent|action|'
        r'vector|struct\s+\w+)\s+(\w+)\s*\((.*?)\)',
        re.MULTILINE | re.DOTALL,
    )
    functions = []
    for m in func_pattern.finditer(source):
        sig_raw = source[m.start():m.end()]
        # Collapse whitespace for readability
        sig = " ".join(sig_raw.split())
        functions.append(sig)

    # Extract constant declarations: const <type> <NAME> = <value>;
    const_pattern = re.compile(
        r'^\s*const\s+\w+\s+(\w+)\s*=\s*([^;]+);',
        re.MULTILINE,
    )
    constants = [
        {"name": m.group(1), "value": m.group(2).strip()}
        for m in const_pattern.finditer(source)
    ]

    # Brace balance check
    open_b = source.count("{")
    close_b = source.count("}")
    if open_b != close_b:
        issues.append(
            f"Brace mismatch: {open_b} '{{' vs {close_b} '}}' — possible unclosed block."
        )

    # Missing semicolons after top-level declarations (heuristic)
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip()
        if stripped.endswith(")") and not stripped.lstrip().startswith("//"):
            next_line = lines[i].lstrip() if i < len(lines) else ""
            if next_line and next_line[0] not in ("{", "/", "#", ""):
                issues.append(f"Line {i}: possible missing '{{' or ';' after '{stripped.strip()}'")

    # Parameter type-mismatch heuristic:
    # KotOR NWScript uses 'object' for creature/item/placeable handles.
    # A very common beginner mistake is writing 'int oXxx' instead of 'object oXxx'.
    param_type_pattern = re.compile(r'\bint\s+(o[A-Z]\w*)\b')
    for i, line in enumerate(lines, 1):
        for m in param_type_pattern.finditer(line):
            issues.append(
                f"Line {i}: parameter '{m.group(1)}' uses 'int' but the 'o' prefix "
                f"conventionally indicates an object handle — did you mean 'object {m.group(1)}'?"
            )

    # Script ResRef length check (KotOR limit: 16 chars, no extension).  Only
    # inspect arguments whose engine signatures actually take a ResRef; an
    # arbitrary long string literal may be ordinary text and must not be
    # reported as if the engine would truncate it.
    resref_patterns = (
        re.compile(
            r'\b(?:ExecuteScript|BeginConversation|StartNewModule|PlayMovie)'
            r'\s*\(\s*"([A-Za-z_][A-Za-z0-9_]{16,})"'
        ),
        re.compile(
            r'\bActionStartConversation\s*\([^,]+,\s*'
            r'"([A-Za-z_][A-Za-z0-9_]{16,})"'
        ),
        re.compile(
            r'\bCreateObject\s*\([^,]+,\s*'
            r'"([A-Za-z_][A-Za-z0-9_]{16,})"'
        ),
    )
    for i, line in enumerate(lines, 1):
        # Skip pure comment lines
        stripped_line = line.lstrip()
        if stripped_line.startswith("//"):
            continue
        for pattern in resref_patterns:
            for m in pattern.finditer(line):
                cand = m.group(1)
                issues.append(
                    f"Line {i}: ResRef argument \"{cand}\" is {len(cand)} chars — "
                    "KotOR's limit is 16 characters."
                )

    return _ok({
        "filename": filename,
        "total_lines": len(lines),
        "includes": includes,
        "function_count": len(functions),
        "functions": functions[:50],  # cap output
        "constant_count": len(constants),
        "constants": constants[:50],
        "issues": issues,
    })


async def _search_resources(args: dict) -> List[types.TextContent]:
    """Search 2DA tables and TLK strings for a given query."""
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"searchResources: {e}")
    query = args.get("query", "").lower().strip()
    scope = args.get("scope", "all").lower()
    limit = min(int(args.get("limit", 30)), 200)

    if not query:
        return _err("searchResources: 'query' must not be empty.")

    rm = _load_rm(game_id)
    results: List[dict] = []

    # ── 2DA search ────────────────────────────────────────────────────────────
    if scope in ("2da", "all"):
        from ghostscripter.core.services import TwoDAService

        # Per-session parse cache: avoids re-parsing every 2DA on each call.
        # Keyed game_id → {resref: TwoDAFile}.  Invalidated when
        # loadInstallation re-registers the game (see _load_rm / _2DA_CACHE).
        session_cache: dict = _2DA_CACHE.setdefault(game_id, {})

        twoda_entries = rm.list_by_type("2da")
        for entry in twoda_entries:
            if len(results) >= limit:
                break
            try:
                resref = entry.resref
                if resref not in session_cache:
                    data = rm.read(f"{resref}.2da")
                    if data is None:
                        continue
                    session_cache[resref] = TwoDAService.parse_bytes(data, resref)
                tda = session_cache[resref]
                for row in tda.rows:
                    for col, val in row.data.items():
                        if query in str(val).lower():
                            results.append({
                                "scope": "2da",
                                "file": resref,
                                "row": row.label,
                                "column": col,
                                "value": val,
                            })
                            if len(results) >= limit:
                                break
                    if len(results) >= limit:
                        break
            except Exception as _e:
                log.debug("searchResources: 2DA scan error: %s", _e)
                continue

    # ── TLK search ────────────────────────────────────────────────────────────
    if scope in ("tlk", "all") and len(results) < limit:
        tlk_data = rm.read("dialog.tlk")
        if tlk_data:
            try:
                from ghostscripter.core.services import TLKService
                tlk = TLKService.parse_bytes(tlk_data, "dialog.tlk")
                for hit in TLKService.search(tlk, query, limit=limit - len(results)):
                    results.append({"scope": "tlk", **hit})
            except Exception as _e:
                log.debug("searchResources: TLK parse error: %s", _e)

    return _ok({
        "game": game_id,
        "query": query,
        "scope": scope,
        "count": len(results),
        "results": results,
    })


async def _module_overview(args: dict) -> List[types.TextContent]:
    """Give a high-level overview of a KotOR module area."""
    game_id = _normalize_game(args.get("game", "K1"))
    module_id = (args.get("moduleId") or args.get("module_id") or args.get("module") or args.get("resref") or "").lower().strip()
    if not module_id:
        return _err("moduleOverview: 'moduleId' is required.")
    validation_error = _validate_resref(module_id, "moduleOverview")
    if validation_error:
        return _err(validation_error)

    rm = _load_rm(game_id)
    source_getter = getattr(type(rm), "module_sources", None)
    if callable(source_getter) and not rm.module_sources(module_id):
        return _err(
            f"moduleOverview: no live .mod/.rim/.erf capsule found for '{module_id}'"
        )

    # Resolve the area from this module's own IFO.  A flat read of
    # ``module.ifo`` would select an arbitrary capsule because every module
    # uses that same internal filename.
    area_resref = module_id
    ifo_data = read_module_resource(rm, module_id, "module.ifo")
    if ifo_data:
        try:
            from ghostscripter.core.services import GFFService
            ifo = GFFService.parse_bytes(ifo_data)
            entry_area = (
                gff_scalar(ifo, "Mod_Entry_Area")
                or gff_scalar(ifo, "EntryArea")
            )
            if entry_area:
                area_resref = str(entry_area).casefold()
            else:
                area_list = ifo.get("Mod_Area_list", [])
                if isinstance(area_list, list) and area_list:
                    first = area_list[0]
                    if isinstance(first, dict):
                        listed = first.get("Area_Name") or first.get("AreaName")
                        if listed:
                            area_resref = str(listed).casefold()
        except Exception as exc:
            log.debug("moduleOverview: IFO parse error: %s", exc)

    git_data = read_module_resource(rm, module_id, f"{area_resref}.git")
    are_data = read_module_resource(rm, module_id, f"{area_resref}.are")

    overview: dict = {
        "game": game_id,
        "module_id": module_id,
        "area_resref": area_resref,
        "area_name": None,
        "creatures": [],
        "doors": [],
        "placeables": [],
        "waypoints": [],
        "triggers": [],
        "sounds": [],
        "encounters": [],
        "stores": [],
    }

    if are_data:
        try:
            from ghostscripter.core.services import GFFService
            are = GFFService.parse_bytes(are_data)
            overview["area_name"] = (
                gff_locstr(are, "Name", rm=rm)
                or gff_locstr(are, "AreaName", rm=rm)
            )
        except Exception as _e:
            log.debug("moduleOverview: ARE parse error: %s", _e)

    if git_data is None:
        return _ok(dict(
            overview,
            error=f"No {area_resref}.git found in module '{module_id}'",
        ))

    try:
        from ghostscripter.core.services import GFFService
        git = GFFService.parse_bytes(git_data)

        # ── Authoritative GIT GFF field names (verified against PyKotor git.py) ──
        # List keys:  "Creature List", "Door List", "Encounter List",
        #             "Placeable List", "SoundList", "StoreList",
        #             "TriggerList", "WaypointList"   ← NB: no space
        # Template field: "TemplateResRef" for all types EXCEPT stores ("ResRef")
        # Position fields: "XPosition"/"YPosition"/"ZPosition" for creatures,
        #                  encounters, sounds, waypoints;
        #                  "X"/"Y"/"Z" for doors, placeables, triggers, stores.
        # Tag field present on: doors, triggers, waypoints (not creatures/placeables/sounds/stores).

        def _extract_list(list_key: str,
                          template_field: str = "TemplateResRef",
                          tag_field: str | None = None,
                          use_xyz_pos: bool = True) -> List[dict]:
            """Extract and normalise a GIT object list into plain dicts.

            Args:
                list_key:        GFF field name for the list (exact KotOR string).
                template_field:  Field holding the resref/template ("TemplateResRef" or "ResRef").
                tag_field:       Field holding the tag string, or None if this type has no tag.
                use_xyz_pos:     True  → position is in X/Y/Z fields (doors, placeables, …)
                                 False → position is in XPosition/YPosition/ZPosition (creatures, …)
            """
            items = git.get(list_key, [])
            out = []
            for obj in (items if isinstance(items, list) else []):
                if not isinstance(obj, dict):
                    continue
                if use_xyz_pos:
                    x = round(float(obj.get("X", 0)), 2)
                    y = round(float(obj.get("Y", 0)), 2)
                else:
                    x = round(float(obj.get("XPosition", 0)), 2)
                    y = round(float(obj.get("YPosition", 0)), 2)
                entry: dict = {
                    "template": str(obj.get(template_field, obj.get("ResRef", ""))),
                    "x": x,
                    "y": y,
                }
                if tag_field:
                    entry["tag"] = str(obj.get(tag_field, ""))
                out.append(entry)
            return out

        # Creatures: XPosition/YPosition, TemplateResRef, no Tag in GFF
        overview["creatures"] = _extract_list(
            "Creature List", "TemplateResRef", tag_field=None, use_xyz_pos=False)
        # Doors: X/Y/Z, TemplateResRef, Tag
        overview["doors"] = _extract_list(
            "Door List", "TemplateResRef", tag_field="Tag", use_xyz_pos=True)
        # Placeables: X/Y/Z, TemplateResRef, no Tag in GFF list
        overview["placeables"] = _extract_list(
            "Placeable List", "TemplateResRef", tag_field=None, use_xyz_pos=True)
        # Waypoints: XPosition/YPosition, TemplateResRef, Tag  ← "WaypointList" (no space)
        overview["waypoints"] = _extract_list(
            "WaypointList", "TemplateResRef", tag_field="Tag", use_xyz_pos=False)
        # Triggers: X/Y/Z (geometry centroid), TemplateResRef, Tag
        overview["triggers"] = _extract_list(
            "TriggerList", "TemplateResRef", tag_field="Tag", use_xyz_pos=True)
        # Sounds: XPosition/YPosition, TemplateResRef, no Tag
        overview["sounds"] = _extract_list(
            "SoundList", "TemplateResRef", tag_field=None, use_xyz_pos=False)
        # Encounters: XPosition/YPosition, TemplateResRef, no Tag
        overview["encounters"] = _extract_list(
            "Encounter List", "TemplateResRef", tag_field=None, use_xyz_pos=False)
        # Stores: X/Y, ResRef (not TemplateResRef), no Tag
        overview["stores"] = _extract_list(
            "StoreList", "ResRef", tag_field=None, use_xyz_pos=True)

        # Summary counts
        for key in ("creatures", "doors", "placeables", "waypoints",
                    "triggers", "sounds", "encounters", "stores"):
            overview[f"{key}_count"] = len(overview[key])

    except Exception as e:
        overview["parse_error"] = str(e)
        log.debug("_module_overview GIT parse error for %s: %s", module_id, e)

    return _ok(overview)


async def _twoda_lookup(args: dict) -> List[types.TextContent]:
    """Look up a single row or cell in a 2DA table."""
    game_id = _normalize_game(args.get("game", "K1"))
    resref = (args.get("resref") or args.get("table") or "").lower().strip()
    if not resref:
        return _err("twoDALookup: 'resref' (or 'table') is required.")
    row_key = args.get("row")
    if row_key is None:
        return _err("twoDALookup: 'row' is required.")
    column = args.get("column", "").strip()

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.2da")
    if data is None:
        return _err(f"2DA not found: {resref} in {game_id}")

    try:
        from ghostscripter.core.services import TwoDAService
        tda = TwoDAService.parse_bytes(data, resref)

        # Find the row using the service's get_cell, or full row lookup
        # First locate the row object for the label
        row = None
        if isinstance(row_key, int) or (isinstance(row_key, str) and str(row_key).isdigit()):
            idx = int(row_key)
            if 0 <= idx < len(tda.rows):
                row = tda.rows[idx]
        else:
            for r in tda.rows:
                if r.label.lower() == str(row_key).lower():
                    row = r
                    break

        if row is None:
            return _err(f"Row {row_key!r} not found in {resref}.2da")

        if column:
            val = TwoDAService.get_cell(tda, row_key, column)
            if val is None:
                return _err(f"Column {column!r} not found in {resref}.2da (columns: {tda.columns})")
            return _ok({
                "resref": resref,
                "row": row.label,
                "column": column,
                "value": val,
            })
        else:
            return _ok({
                "resref": resref,
                "row": row.label,
                "data": row.data,
            })
    except Exception as e:
        return _err(f"twoDALookup error: {e}")


async def _nwscript_categories(args: dict) -> List[types.TextContent]:
    """List all NWScript function/constant categories with counts."""
    game_id = _normalize_game(args.get("game", "K1"))
    kind = args.get("kind", "functions").lower()

    from ghostscripter.core.services import NWScriptService
    db = NWScriptService.load(game_id)
    result = NWScriptService.categories(db, kind)
    result["game"] = game_id
    return _ok(result)


async def _twoda_changes_ini(args: dict) -> List[types.TextContent]:
    """Generate a TSLPatcher changes.ini section from original vs modified 2DA."""
    original_text = args.get("original", "")
    modified_text = args.get("modified", "")
    twoda_name = args.get("twoDAName", "unnamed")

    try:
        from ghostscripter.core.services import TwoDAService
        orig = TwoDAService.parse_text(original_text)
        mod = TwoDAService.parse_text(modified_text)
        ini_text = TwoDAService.diff_to_ini(orig, mod)
        return _ok({
            "twoDA": twoda_name,
            "original_rows": len(orig.rows),
            "modified_rows": len(mod.rows),
            "changes_ini": ini_text,
        })
    except Exception as e:
        return _err(f"twoDAChangesINI error: {e}")


async def _search_all(args: dict) -> List[types.TextContent]:
    """Unified text search across 2DA tables, TLK strings, NWScript sources, and DLG text.

    Runs the *query* string against every enabled scope and returns all matches
    in a single response, each annotated with its source scope.

    Args:
        game    (str): "K1" or "K2"
        query   (str): substring to search (case-insensitive)
        scopes  (list[str], default all): subset of ["2da", "tlk", "nss", "dlg"]
        limit   (int, default 100, max 500): maximum total hits across all scopes

    Returns a dict with keys:
        game, query, scopes_searched, total, matches
        Each match has: scope, source, detail, value
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"searchAll: {e}")

    query = args.get("query", "").strip()
    if not query:
        return _err("searchAll: 'query' is required")

    all_scopes = {"2da", "tlk", "nss", "dlg"}
    requested = args.get("scopes", list(all_scopes))
    if isinstance(requested, str):
        requested = [requested]
    scopes = {s.lower() for s in requested} & all_scopes
    if not scopes:
        return _err(f"searchAll: no valid scopes in {requested!r}; valid: {sorted(all_scopes)}")

    limit = min(int(args.get("limit", 100)), 500)
    query_lc = query.lower()

    rm = _load_rm(game_id)
    matches: list = []

    # ── 2DA scope ─────────────────────────────────────────────────────────────
    if "2da" in scopes and len(matches) < limit:
        try:
            from ghostscripter.core.services import TwoDAService
            all_res = rm.list_resources()
            tda_names = [r for r in all_res if r.lower().endswith(".2da")]
            for res_name in tda_names:
                if len(matches) >= limit:
                    break
                resref = res_name[:-4]
                try:
                    # Use session cache when available
                    cache_key = (game_id, resref)
                    tda = _2DA_CACHE.get(cache_key)
                    if tda is None:
                        data = rm.read(res_name)
                        if not data:
                            continue
                        tda = TwoDAService.parse_bytes(data, resref)
                        _2DA_CACHE[cache_key] = tda
                    for row_label, row_dict in zip(
                        (r.label for r in tda.rows), TwoDAService.rows_to_dicts(tda)
                    ):
                        if len(matches) >= limit:
                            break
                        for col, cell_val in row_dict.items():
                            if col == "_row_index":
                                continue
                            if cell_val and query_lc in str(cell_val).lower():
                                matches.append({
                                    "scope":  "2da",
                                    "source": res_name,
                                    "detail": f"row={row_label} col={col}",
                                    "value":  str(cell_val),
                                })
                                if len(matches) >= limit:
                                    break
                except Exception as _e:
                    log.debug("searchAll 2da error in %s: %s", res_name, _e)
        except Exception as e:
            log.debug("searchAll 2da scope error: %s", e)

    # ── TLK scope ─────────────────────────────────────────────────────────────
    if "tlk" in scopes and len(matches) < limit:
        try:
            from ghostscripter.core.services import TLKService
            tlk_data = rm.read("dialog.tlk")
            if tlk_data:
                tlk = TLKService.parse_bytes(tlk_data, "dialog.tlk")
                hits = TLKService.search(tlk, query)
                for strref, text in hits:
                    if len(matches) >= limit:
                        break
                    matches.append({
                        "scope":  "tlk",
                        "source": "dialog.tlk",
                        "detail": f"strref={strref}",
                        "value":  str(text)[:300],
                    })
        except Exception as e:
            log.debug("searchAll tlk scope error: %s", e)

    # ── NSS scope ─────────────────────────────────────────────────────────────
    if "nss" in scopes and len(matches) < limit:
        try:
            all_res = rm.list_resources()
            nss_names = [r for r in all_res if r.lower().endswith(".nss")]
            for res_name in nss_names:
                if len(matches) >= limit:
                    break
                try:
                    data = rm.read(res_name)
                    if not data:
                        continue
                    text = data.decode("latin-1", errors="replace")
                    for lineno, line in enumerate(text.splitlines(), 1):
                        if len(matches) >= limit:
                            break
                        if query_lc in line.lower():
                            matches.append({
                                "scope":  "nss",
                                "source": res_name,
                                "detail": f"line={lineno}",
                                "value":  line.strip()[:300],
                            })
                except Exception as _e:
                    log.debug("searchAll nss error in %s: %s", res_name, _e)
        except Exception as e:
            log.debug("searchAll nss scope error: %s", e)

    # ── DLG scope ─────────────────────────────────────────────────────────────
    if "dlg" in scopes and len(matches) < limit:
        try:
            from ghostscripter.core.services import DialogueService
            all_res = rm.list_resources()
            dlg_names = [r for r in all_res if r.lower().endswith(".dlg")]
            for res_name in dlg_names:
                if len(matches) >= limit:
                    break
                try:
                    data = rm.read(res_name)
                    if not data:
                        continue
                    dlg = DialogueService.parse_bytes(data)
                    d = DialogueService.to_dict(dlg, include_fidelity=False)
                    resref = res_name[:-4]
                    for node_type in ("entries", "replies"):
                        for node in d.get(node_type, []):
                            if len(matches) >= limit:
                                break
                            text_val = node.get("text", "") or ""
                            if query_lc in text_val.lower():
                                matches.append({
                                    "scope":  "dlg",
                                    "source": res_name,
                                    "detail": f"{node_type[:-1]}_index={node.get('index', '?')}",
                                    "value":  text_val[:300],
                                })
                except Exception as _e:
                    log.debug("searchAll dlg error in %s: %s", res_name, _e)
        except Exception as e:
            log.debug("searchAll dlg scope error: %s", e)

    return _ok({
        "game":            game_id,
        "query":           query,
        "scopes_searched": sorted(scopes),
        "total":           len(matches),
        "matches":         matches,
    })


async def _read_ssf(args: dict) -> List[types.TextContent]:
    """Read and decode a KotOR Sound Set File (SSF) by resref.

    The first 28 StrRefs map canonical creature sound-event slots to dialog.tlk
    entries. Retail files can contain additional undocumented entries, which are
    returned separately so callers can preserve them. A StrRef of -1
    (0xFFFFFFFF) means no sound is assigned.

    Args:
        game        (str): "K1" or "K2"
        resref      (str): SSF resref without extension, e.g. "c_bantha" or "p_bastila"
        resolve_tlk (bool, default True): look up each StrRef in dialog.tlk and
                    include the TLK text alongside the raw StrRef integer.

    Returns a dict with keys:
        game, resref, slot_count (always 28), entry_count,
        slots: list of {index, name, strref, text (or null)},
        unknown_slots: list of {index, strref}
    """
    from ghostscripter.core.ssf import SSF_SLOT_NAMES, decode_ssf

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readSSF: {e}")

    resref = args.get("resref", "").lower().strip()
    if not resref:
        return _err("readSSF: 'resref' is required")
    if len(resref) > 16:
        return _err(f"readSSF: resref '{resref}' exceeds 16 characters")

    resolve_tlk = args.get("resolve_tlk", True)
    rm = _load_rm(game_id)

    ssf_data = rm.read(f"{resref}.ssf")
    if ssf_data is None:
        return _err(
            f"readSSF: '{resref}.ssf' not found in {game_id}. "
            "Try listResType(type='ssf') to browse available sound sets."
        )

    try:
        strrefs = decode_ssf(ssf_data)
    except (TypeError, ValueError) as e:
        return _err(f"readSSF: invalid SSF V1.1 resource: {e}")

    # Optionally resolve TLK
    tlk = None
    if resolve_tlk:
        try:
            from ghostscripter.core.services import TLKService
            tlk_bytes = rm.read("dialog.tlk")
            if tlk_bytes:
                tlk = TLKService.parse_bytes(tlk_bytes, "dialog.tlk")
        except Exception as _e:
            log.debug("readSSF: TLK load error: %s", _e)

    slots: list = []
    for i, (name, strref) in enumerate(zip(SSF_SLOT_NAMES, strrefs)):
        text = None
        if tlk is not None and strref >= 0:
            try:
                text = TLKService.lookup(tlk, [strref]).get(strref, {}).get("text")
            except Exception:
                pass
        slots.append({
            "index":  i,
            "name":   name,
            "strref": strref,
            "text":   text,
        })

    unknown_slots = [
        {"index": index, "strref": strref}
        for index, strref in enumerate(strrefs[len(SSF_SLOT_NAMES):], len(SSF_SLOT_NAMES))
    ]

    return _ok({
        "game":       game_id,
        "resref":     resref,
        "slot_count": len(slots),
        "entry_count": len(strrefs),
        "slots":      slots,
        "unknown_slots": unknown_slots,
    })


async def _read_lip(args: dict) -> List[types.TextContent]:
    """Read and decode a KotOR lip-sync file (LIP V1.0) by resref.

    LIP is a simple fixed-layout binary: 8-byte magic ("LIP V1.0"), 4-byte float
    duration, 4-byte uint32 keyframe count, then N×5-byte keyframes (float time +
    uint8 shape).

    Numeric mouth-shape indices are decoded with the retail-validated mapping
    shared by the editor and writer.  Index 0 is NEUTRAL/rest.

    Args:
        game   (str): "K1" or "K2"
        resref (str): LIP resref without extension, e.g. "n_bastila001"

    Returns a dict with:
        game, resref, duration_s, keyframe_count, keyframes (list of {time_s, shape_index, shape_name})
    """
    import struct
    from ghostscripter.core.lip import LIP_SHAPES

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readLIP: {e}")

    resref = (args.get("resref") or "").strip().lower()
    if not resref:
        return _err("readLIP: 'resref' is required.")
    if len(resref) > 16:
        return _err(f"readLIP: resref '{resref}' exceeds 16 characters.")

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.lip")
    if data is None:
        return _err(
            f"readLIP: '{resref}.lip' not found in {game_id} installation. "
            "Use listResType(type='lip') to enumerate available resrefs."
        )

    if len(data) < 16:
        return _err(f"readLIP: '{resref}.lip' is too short to be a valid LIP file ({len(data)} bytes).")

    magic = data[:8].decode("ascii", errors="replace")
    if magic != "LIP V1.0":
        return _err(
            f"readLIP: '{resref}.lip' has unexpected magic '{magic}' (expected 'LIP V1.0')."
        )

    duration_s = struct.unpack_from("<f", data, 8)[0]
    entry_count = struct.unpack_from("<I", data, 12)[0]

    expected_size = 16 + entry_count * 5
    if len(data) < expected_size:
        return _err(
            f"readLIP: File too short: expected {expected_size} bytes for "
            f"{entry_count} keyframes, got {len(data)}."
        )

    keyframes: list = []
    offset = 16
    for _ in range(entry_count):
        time_s = struct.unpack_from("<f", data, offset)[0]
        shape_idx = data[offset + 4]
        keyframes.append({
            "time_s":      round(time_s, 6),
            "shape_index": shape_idx,
            "shape_name":  LIP_SHAPES[shape_idx] if shape_idx < len(LIP_SHAPES) else f"SHAPE_{shape_idx}",
        })
        offset += 5

    return _ok({
        "game":           game_id,
        "resref":         resref,
        "duration_s":     round(duration_s, 6),
        "keyframe_count": entry_count,
        "keyframes":      keyframes,
    })


# ─── Composite / high-level tool handlers (Ghostworks Pipeline) ──────────────

