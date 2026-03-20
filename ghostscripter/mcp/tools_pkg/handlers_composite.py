"""Composite game-object MCP tool handlers (getResource, getQuest, getNpc, getScript)."""
from __future__ import annotations

from typing import Any, List

import mcp.types as types

import os
from pathlib import Path

from ghostscripter.mcp.tools_pkg._helpers import (
    _err, _load_rm, _normalize_game, _ok, _prune, _validate_resref, log,
    gff_scalar, gff_locstr, gff_resref, gff_int, gff_float, gff_list,
    gff_struct_fields, HARDCODED_MODULE_NAMES,
)


async def _get_resource(args: dict) -> List[types.TextContent]:
    """Universal resource accessor — returns any KotOR resource in readable form."""
    import base64
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getResource: {e}")
    resref = (args.get("resref") or "").lower().strip()
    restype = (args.get("type") or args.get("restype") or "").lower().lstrip(".")
    if not resref:
        return _err("getResource: 'resref' is required.")
    if not restype:
        return _err("getResource: 'type' is required (e.g. 'utc', 'dlg', '2da').")
    fmt = args.get("format", "auto")

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.{restype}")
    if data is None:
        return _err(f"Resource not found: {resref}.{restype} in {game_id}")

    result: dict = {"game": game_id, "resref": resref, "type": restype, "size_bytes": len(data)}

    try:
        if restype == "2da":
            from ghostscripter.core.services import TwoDAService
            tda = TwoDAService.parse_bytes(data, resref)
            rows = TwoDAService.rows_to_dicts(tda, offset=0, limit=100)
            result["columns"] = tda.columns
            result["row_count"] = len(tda.rows)
            result["rows"] = rows

        elif restype == "dlg":
            from ghostscripter.core.services import DialogueService
            dlg = DialogueService.parse_bytes(data)
            result.update(DialogueService.to_dict(dlg))

        elif restype in ("utc", "utp", "uts", "utt", "utw", "ute", "utm",
                         "are", "git", "jrl", "ifo", "fac", "bic",
                         "gff", "pth"):
            from ghostscripter.core.services import GFFService
            parsed = GFFService.parse_bytes(data)
            result["fields"] = _prune(parsed, depth=4)

        elif restype == "jrl":
            from ghostscripter.core.services import JournalService
            jrl = JournalService.parse_bytes(data)
            result.update(JournalService.to_dict(jrl))

        elif restype == "nss":
            text = data.decode("latin-1", errors="replace")
            result["source"] = text

        elif restype == "ncs":
            # Attempt decompile; fall back to base64 if unavailable
            decompiled = _try_decompile_ncs(data, resref)
            if decompiled:
                result["decompiled_source"] = decompiled
                result["decompiler_used"] = True
            else:
                result["compiled_base64"] = base64.b64encode(data).decode()
                result["note"] = (
                    "NCS decompiler not found. Install NCSDecompCLI.jar in tools/, "
                    "xoreos-tools, or run: pip install pykotor"
                )

        elif restype == "tlk":
            from ghostscripter.core.services import TLKService
            tlk = TLKService.parse_bytes(data, f"{resref}.tlk")
            result.update(TLKService.summary(tlk))

        else:
            # Unknown type — try GFF parse, fall back to raw bytes (b64)
            try:
                from ghostscripter.core.services import GFFService
                parsed = GFFService.parse_bytes(data)
                result["fields"] = _prune(parsed, depth=3)
                result["parsed_as"] = "GFF"
            except Exception as _e:
                log.debug("describeResource: GFF parse failed: %s", _e)
                result["raw_base64"] = base64.b64encode(data[:4096]).decode()
                result["note"] = "Unknown format; first 4KB returned as base64."

    except Exception as e:
        result["parse_error"] = str(e)

    return _ok(result)


def _try_decompile_ncs(ncs_bytes: bytes, resref: str) -> str | None:
    """Attempt to decompile compiled NWScript via available tools.

    Tries in order:
    1. NCSDecompCLI.jar (tools/ directory, requires Java)
    2. xoreos-tools ncsdecomp (if on PATH)
    3. pykotor (if installed)

    Returns decompiled source text, or None if no decompiler found.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ncs_path = Path(tmp) / f"{resref}.ncs"
        nss_path = Path(tmp) / f"{resref}.nss"
        ncs_path.write_bytes(ncs_bytes)

        # 1. Try NCSDecompCLI.jar
        jar_candidates = [
            Path("tools") / "NCSDecompCLI.jar",
            Path(__file__).parent.parent.parent / "tools" / "NCSDecompCLI.jar",
        ]
        for jar in jar_candidates:
            if jar.exists():
                try:
                    result = subprocess.run(
                        ["java", "-jar", str(jar), str(ncs_path), str(nss_path)],
                        capture_output=True, timeout=15,
                    )
                    if nss_path.exists():
                        return nss_path.read_text("latin-1", errors="replace")
                except Exception as _e:
                    log.debug("_try_decompile_ncs: NCSDecompCLI failed: %s", _e)

        # 2. Try xoreos-tools ncsdecomp
        try:
            result = subprocess.run(
                ["ncsdecomp", "-o", str(nss_path), str(ncs_path)],
                capture_output=True, timeout=15,
            )
            if nss_path.exists():
                return nss_path.read_text("latin-1", errors="replace")
        except Exception as _e:
            log.debug("_try_decompile_ncs: xoreos ncsdecomp failed: %s", _e)

        # 3. Try pykotor
        try:
            from pykotor.resource.formats.ncs import NCS, compile_nss  # noqa
            from pykotor.resource.formats.ncs.compiler.classes import EntryPointError  # noqa
            # pykotor decompiler
            ncs_obj = NCS.from_data(ncs_bytes)
            src = ncs_obj.to_nss()
            if src:
                return src
        except Exception as _e:
            log.debug("_try_decompile_ncs: pykotor decompile failed: %s", _e)

    return None


async def _get_quest(args: dict) -> List[types.TextContent]:
    """Composite quest view: JRL states + TLK text + scripts + DLG references."""
    game_id = _normalize_game(args.get("game", "K1"))
    quest_id = (args.get("questId") or args.get("quest_id") or args.get("tag") or "").strip()
    if not quest_id:
        return _err("getQuest: 'questId' is required.")
    include_scripts = args.get("includeScripts", True)
    include_dialogues = args.get("includeDialogues", False)

    rm = _load_rm(game_id)

    # 1. Load journal
    jrl_data = rm.read("global.jrl")
    if jrl_data is None:
        return _err(f"global.jrl not found in {game_id}")

    from ghostscripter.core.services import JournalService, TLKService
    jrl = JournalService.parse_bytes(jrl_data)

    # Find the quest category
    quest_cat = None
    for cat in jrl.categories:
        if cat.tag.lower() == quest_id.lower():
            quest_cat = cat
            break
    if quest_cat is None:
        return _err(
            f"Quest '{quest_id}' not found in global.jrl. "
            f"Available: {[c.tag for c in jrl.categories[:10]]}"
        )

    # 2. Load TLK for string resolution
    tlk = None
    tlk_data = rm.read("dialog.tlk")
    if tlk_data:
        try:
            tlk = TLKService.parse_bytes(tlk_data, "dialog.tlk")
        except Exception as _e:
            log.debug("_get_quest: TLK parse error: %s", _e)

    def resolve_strref(strref: int) -> str:
        if strref < 0 or tlk is None:
            return ""
        try:
            entries = TLKService.lookup(tlk, [strref])
            # lookup returns a list of dicts, not a dict keyed by strref
            return (entries[0].get("text", "") if entries else "") or ""
        except Exception as _e:
            log.debug("resolve_strref(%s) error: %s", strref, _e)
            return ""

    # 3. Build states with human-readable text
    states = []
    script_resrefs: list[str] = []
    for entry in quest_cat.entries:
        state: dict = {
            "id": entry.id,
            "text": resolve_strref(getattr(entry, "strref", -1)) or entry.text or "",
            "end": getattr(entry, "end", False),
        }
        # Collect script references from entry
        for field in ("script", "script1", "script2", "scriptAbort",
                      "scriptToRun", "runScript"):
            val = getattr(entry, field, None) or ""
            if val:
                state[field] = val
                script_resrefs.append(val.lower())
        states.append(state)

    result: dict = {
        "game": game_id,
        "quest_id": quest_cat.tag,
        "name": quest_cat.name or resolve_strref(getattr(quest_cat, "name_strref", -1)),
        "state_count": len(states),
        "states": states,
    }

    # 4. Optionally load scripts
    if include_scripts and script_resrefs:
        scripts = {}
        seen = set()
        for sref in script_resrefs:
            if sref in seen:
                continue
            seen.add(sref)
            # Try .nss first, then .ncs
            src = None
            for ext in ("nss", "ncs"):
                raw = rm.read(f"{sref}.{ext}")
                if raw:
                    if ext == "nss":
                        src = raw.decode("latin-1", errors="replace")
                    else:
                        src = _try_decompile_ncs(raw, sref) or f"[compiled NCS — {len(raw)} bytes]"
                    break
            scripts[sref] = src or "[not found]"
        result["scripts"] = scripts

    # 5. Optionally find DLG files referencing quest scripts
    if include_dialogues and script_resrefs:
        referenced_dlgs: List[dict] = []
        dlg_list = rm.list_by_type(".dlg")
        for dlg_entry in (dlg_list or [])[:50]:  # cap scan at 50 DLGs to stay responsive
            dlg_resref = dlg_entry.resref if hasattr(dlg_entry, 'resref') else str(dlg_entry)
            dlg_data = rm.read(f"{dlg_resref}.dlg")
            if not dlg_data:
                continue
            try:
                from ghostscripter.core.services import DialogueService
                dlg = DialogueService.parse_bytes(dlg_data)
                d = DialogueService.to_dict(dlg)
                # Check if any entry/reply references our scripts
                refs: list[str] = []
                for entry in d.get("entries", []) + d.get("replies", []):
                    for field in ("script1", "script2", "actionParam1",
                                  "condScript"):
                        v = entry.get(field, "")
                        if v and v.lower() in script_resrefs:
                            refs.append(
                                f"entry #{entry.get('id', '?')}: {v!r}"
                            )
                if refs:
                    referenced_dlgs.append({
                        "dlg_resref": dlg_resref,
                        "references": refs[:5],
                    })
                    if len(referenced_dlgs) >= 20:
                        break
            except Exception as _e:
                log.debug("_get_quest: DLG scan error: %s", _e)
                continue
        result["dialogues_referencing_quest"] = referenced_dlgs

    return _ok(result)


async def _get_npc(args: dict) -> List[types.TextContent]:
    """Composite NPC view: UTC stats + appearance.2da + repute.2da + DLG summary."""
    game_id = _normalize_game(args.get("game", "K1"))
    resref = (args.get("resref") or args.get("npc_resref") or "").lower().strip()
    if not resref:
        return _err("getNpc: 'resref' is required.")
    include_dialogue = args.get("includeDialogue", True)

    rm = _load_rm(game_id)

    # 1. Load UTC
    utc_data = rm.read(f"{resref}.utc")
    if utc_data is None:
        return _err(
            f"NPC UTC not found: {resref}.utc in {game_id}. "
            "Try listResType(type='utc') to find NPC resrefs."
        )

    from ghostscripter.core.services import GFFService, TwoDAService
    utc_fields = GFFService.parse_bytes(utc_data)

    result: dict = {
        "game": game_id,
        "resref": resref,
        "utc_fields": _prune(utc_fields, depth=2),
    }

    # 2. Resolve appearance.2da row
    appearance_id = utc_fields.get("Appearance_Type", utc_fields.get("AppearanceType", -1))
    if isinstance(appearance_id, dict):
        appearance_id = appearance_id.get("value", -1)
    if appearance_id >= 0:
        app_data = rm.read("appearance.2da")
        if app_data:
            try:
                tda = TwoDAService.parse_bytes(app_data, "appearance")
                cell = TwoDAService.get_cell(tda, row=appearance_id, column="label")
                result["appearance_label"] = cell or f"row {appearance_id}"
                result["appearance_row"] = appearance_id
            except Exception as e:
                result["appearance_note"] = str(e)

    # 3. Resolve faction/repute
    faction_id = utc_fields.get("FactionID", -1)
    if isinstance(faction_id, dict):
        faction_id = faction_id.get("value", -1)
    if faction_id >= 0:
        repute_data = rm.read("repute.2da")
        if repute_data:
            try:
                tda = TwoDAService.parse_bytes(repute_data, "repute")
                faction_name = TwoDAService.get_cell(tda, row=faction_id, column="label")
                result["faction"] = faction_name or f"faction {faction_id}"
                result["faction_row"] = faction_id
            except Exception as _e:
                log.debug("_get_npc: repute.2da faction lookup error: %s", _e)

    # 4. Extract key script fields
    script_fields = {}
    for field in ("ScriptHeartbeat", "ScriptOnNotice", "ScriptSpellAt",
                  "ScriptAttacked", "ScriptDamaged", "ScriptDisturbed",
                  "ScriptEndRound", "ScriptEndDialogue", "ScriptDialogue",
                  "ScriptSpawn", "ScriptDeath", "ScriptUserDefined"):
        v = utc_fields.get(field, "")
        if isinstance(v, dict):
            v = v.get("value", "")
        if v:
            script_fields[field] = v
    result["scripts"] = script_fields

    # 5. Get DLG reference and summarize
    dlg_resref = utc_fields.get("Conversation", "")
    if isinstance(dlg_resref, dict):
        dlg_resref = dlg_resref.get("value", "")
    if dlg_resref:
        result["dialogue_resref"] = dlg_resref
        if include_dialogue:
            dlg_data = rm.read(f"{dlg_resref}.dlg")
            if dlg_data:
                try:
                    from ghostscripter.core.services import DialogueService, TLKService
                    dlg = DialogueService.parse_bytes(dlg_data)
                    d = DialogueService.to_dict(dlg)
                    # Resolve TLK for first entry
                    opening_text = ""
                    if d.get("starters") and d.get("entries"):
                        first_idx = d["starters"][0].get("index", 0)
                        entries = d.get("entries", [])
                        if first_idx < len(entries):
                            strref = entries[first_idx].get("strref", -1)
                            opening_text = entries[first_idx].get("text", "")
                            if not opening_text and strref >= 0:
                                tlk_data = rm.read("dialog.tlk")
                                if tlk_data:
                                    tlk = TLKService.parse_bytes(tlk_data, "dialog.tlk")
                                    opening_text = TLKService.lookup(
                                        tlk, [strref]
                                    ).get(strref, {}).get("text", "")
                    result["dialogue_summary"] = {
                        "entry_count": len(d.get("entries", [])),
                        "reply_count": len(d.get("replies", [])),
                        "opening_line": opening_text[:200] if opening_text else "",
                    }
                except Exception as e:
                    result["dialogue_error"] = str(e)

    return _ok(result)


async def _get_script(args: dict) -> List[types.TextContent]:
    """Return a KotOR script in readable form with optional static analysis."""
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getScript: {e}")
    # Use removesuffix to strip extension correctly (rstrip strips characters, not suffixes)
    resref = (args.get("resref") or "").lower().strip()
    if not resref:
        return _err("getScript: 'resref' is required.")
    for _ext in (".nss", ".ncs"):
        if resref.endswith(_ext):
            resref = resref[: -len(_ext)]
            break
    do_analyze = args.get("analyze", True)

    rm = _load_rm(game_id)

    source: str | None = None
    source_type: str = "not_found"

    # Try .nss source first
    nss_data = rm.read(f"{resref}.nss")
    if nss_data:
        source = nss_data.decode("latin-1", errors="replace")
        source_type = "nss_source"
    else:
        # Try compiled .ncs and decompile
        ncs_data = rm.read(f"{resref}.ncs")
        if ncs_data:
            decompiled = _try_decompile_ncs(ncs_data, resref)
            if decompiled:
                source = decompiled
                source_type = "ncs_decompiled"
            else:
                source_type = "ncs_binary_only"

    result: dict = {
        "game": game_id,
        "resref": resref,
        "source_type": source_type,
    }

    if source:
        result["source"] = source

        if do_analyze:
            # Reuse the existing compileSummary static analysis logic
            try:
                analysis_result = await _compile_summary({"source": source})
                import json as _json
                if analysis_result:
                    analysis_data = _json.loads(analysis_result[0].text)
                    result["analysis"] = analysis_data
            except Exception as e:
                result["analysis_error"] = str(e)
    elif source_type == "ncs_binary_only":
        result["note"] = (
            "Script compiled (.ncs only) and no decompiler found. "
            "Install NCSDecompCLI.jar in tools/, xoreos-tools, or run: pip install pykotor"
        )
    else:
        result["note"] = f"Script {resref}.nss/.ncs not found in {game_id}"

    return _ok(result)


async def _list_res_type(args: dict) -> List[types.TextContent]:
    """List all resources of a given type with optional name filter."""
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"listResType: {e}")
    restype = (args.get("type") or args.get("restype") or "").lower().lstrip(".")
    if not restype:
        return _err("listResType: 'type' is required (e.g. 'utc', 'dlg', '2da').")
    pattern = args.get("pattern", "").lower()
    offset = int(args.get("offset", 0))
    limit = min(int(args.get("limit", 50)), 200)

    rm = _load_rm(game_id)
    all_refs = rm.list_by_type(f".{restype}") or []

    # Filter by pattern
    if pattern:
        all_refs = [r for r in all_refs if pattern in (r.resref if hasattr(r, 'resref') else str(r)).lower()]

    total = len(all_refs)
    page = all_refs[offset: offset + limit]

    # Serialize ResourceEntry objects to plain dicts for JSON transport
    def _entry_to_dict(e: Any) -> dict:
        if hasattr(e, "resref"):
            return {
                "resref": e.resref,
                "type": e.restype_str or restype,
                "source": e.source_file,
                "size": e.size,
            }
        return {"resref": str(e)}

    return _ok({
        "game": game_id,
        "type": restype,
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [_entry_to_dict(e) for e in page],
        "has_more": (offset + limit) < total,
    })


async def _get_area(args: dict) -> List[types.TextContent]:
    """Return a rich view of a KotOR area: properties (ARE), instances (GIT), and room layout (LYT).

    Combines data from three binary files:
      <resref>.are  — area properties (name, tileset, flags, fog, grass, weather, scripts)
      <resref>.git  — game instance table (creatures, doors, placeables, waypoints, triggers,
                       stores, sounds, encounters, cameras; plus ambient audio + weather IDs)
      <resref>.lyt  — room layout (room names + X/Y/Z positions)

    Args:
        game   (str): "K1" or "K2"
        resref (str): area resref, e.g. "danm13", "tar_m02aa"

    Returns a dict with keys:
        game, resref, area_name, tag, tileset, flags, camera_style, default_envmap,
        ambient_sound, ambient_volume, ambient_battle_sound,
        music_standard, music_battle, music_delay,
        fog_enabled, fog_near, fog_far, fog_color,
        sun_ambient_color, sun_diffuse_color, dynamic_light_color, shadows,
        grass_texture, grass_density, grass_size,
        wind_power, unescapable, disable_transit,
        weather, chance_rain, chance_snow, chance_lightning (K2 only),
        stealth_xp_enabled, stealth_xp_loss, stealth_xp_max, no_rest,
        use_templates, current_weather, weather_started (GIT runtime state),
        scripts (dict of non-empty OnXxx script resrefs),
        rooms (list of {room, x, y, z}),
        creatures, doors, placeables, waypoints, triggers,
        stores, sounds, encounters, cameras,
        parse_errors (list of strings, empty on clean parse)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getArea: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getArea")
    if err:
        return _err(err)

    rm = _load_rm(game_id)

    result: dict = {
        "game": game_id,
        "resref": resref,
        "area_name": None,
        "tag": None,
        "tileset": None,
        "flags": None,
        "camera_style": None,
        "default_envmap": None,
        # Ambient audio / music (from ARE + GIT AreaProperties)
        "ambient_sound": None,
        "ambient_volume": None,
        "ambient_battle_sound": None,
        "music_standard": None,
        "music_battle": None,
        "music_delay": None,
        # Fog / lighting
        "fog_enabled": None,
        "fog_near": None,
        "fog_far": None,
        "fog_color": None,
        "sun_ambient_color": None,
        "sun_diffuse_color": None,
        "dynamic_light_color": None,
        "shadows": None,
        # Grass (KotOR exterior areas)
        "grass_texture": None,
        "grass_density": None,
        "grass_size": None,
        # Weather / environment
        "wind_power": None,
        "unescapable": None,
        "disable_transit": None,
        "weather": None,
        "chance_rain": None,
        "chance_snow": None,
        "chance_lightning": None,
        # Gameplay flags
        "stealth_xp_enabled": None,
        "stealth_xp_loss": None,
        "stealth_xp_max": None,
        "no_rest": None,
        # GIT runtime state
        "use_templates": None,
        "current_weather": None,
        "weather_started": None,
        "scripts": {},
        "rooms": [],
        "creatures": [],
        "doors": [],
        "placeables": [],
        "waypoints": [],
        "triggers": [],
        "stores": [],
        "sounds": [],
        "encounters": [],
        "cameras": [],
        "parse_errors": [],
    }

    # ── ARE (area properties) ────────────────────────────────────────────────
    are_data = rm.read(f"{resref}.are")
    if are_data is None:
        return _err(f"getArea: area '{resref}' not found in {game_id} installation.")

    try:
        from ghostscripter.core.services import GFFService
        are = GFFService.parse_bytes(are_data)
        fields = are if isinstance(are, dict) else (are.get("fields") or are)
        result["area_name"]     = fields.get("Name", {}).get("value") or fields.get("Name")
        result["tag"]           = fields.get("Tag")
        result["tileset"]       = fields.get("Tileset")
        result["flags"]         = fields.get("Flags")
        result["camera_style"]  = fields.get("CameraStyle")
        result["default_envmap"] = fields.get("DefaultEnvMap")
        result["ambient_sound"] = (
            fields.get("AmbientSndDay") or fields.get("AmbientSnd")
        )
        result["ambient_volume"]        = fields.get("AmbientSndDayVol") or fields.get("AmbientSndVol")
        result["ambient_battle_sound"]  = fields.get("AmbientSndBat") or fields.get("EnvAudio")
        result["music_standard"]        = fields.get("MusicDay") or fields.get("MusicStandard")
        result["music_battle"]          = fields.get("MusicBattle")
        result["music_delay"]           = fields.get("MusicDelay")
        result["fog_enabled"]           = fields.get("SunFogOn") or fields.get("FogOn")
        result["fog_near"]              = _safe_float(fields.get("SunFogNear") or fields.get("FogNear"))
        result["fog_far"]               = _safe_float(fields.get("SunFogFar") or fields.get("FogFar"))
        result["fog_color"]             = fields.get("SunFogColor")
        result["sun_ambient_color"]     = fields.get("SunAmbientColor")
        result["sun_diffuse_color"]     = fields.get("SunDiffuseColor")
        result["dynamic_light_color"]   = fields.get("DynAmbientColor")
        result["shadows"]               = fields.get("SunShadows")
        result["grass_texture"]         = fields.get("Grass_TexName")
        result["grass_density"]         = _safe_float(fields.get("Grass_Density"))
        result["grass_size"]            = _safe_float(fields.get("Grass_QuadSize"))
        result["wind_power"]            = fields.get("WindPower")
        result["unescapable"]           = fields.get("Unescapable")
        result["disable_transit"]       = fields.get("DisableTransit")
        result["weather"]               = fields.get("WeatherID")
        # K2-only weather fields
        result["chance_rain"]           = fields.get("ChanceRain")
        result["chance_snow"]           = fields.get("ChanceSnow")
        result["chance_lightning"]      = fields.get("ChanceLightning")
        # Stealth / gameplay flags
        result["stealth_xp_enabled"]    = fields.get("StealthXPEnabled")
        result["stealth_xp_loss"]       = fields.get("StealthXPLoss")
        result["stealth_xp_max"]        = fields.get("StealthXPMax")
        result["no_rest"]               = fields.get("NoRest")
        # Area scripts
        scripts = {}
        for sf in ("OnEnter", "OnExit", "OnHeartbeat", "OnUserDefined"):
            v = fields.get(sf)
            if v:
                scripts[sf] = v
        result["scripts"] = scripts
    except Exception as e:
        result["parse_errors"].append(f"ARE parse error: {e}")

    # Fallback: use HARDCODED_MODULE_NAMES when .are has no readable name
    if not result.get("area_name"):
        result["area_name"] = HARDCODED_MODULE_NAMES.get(resref.lower(), None)

    # ── LYT (room layout) ────────────────────────────────────────────────────
    lyt_data = rm.read(f"{resref}.lyt")
    if lyt_data:
        try:
            text = lyt_data.decode("latin-1", errors="replace")
            rooms = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("beginlayout") or line.startswith("donelayout"):
                    continue
                if line.startswith("roomcount") or line.startswith("trackcount"):
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    rooms.append({
                        "room": parts[0],
                        "x": _safe_float(parts[1]),
                        "y": _safe_float(parts[2]),
                        "z": _safe_float(parts[3]),
                    })
            result["rooms"] = rooms
        except Exception as e:
            result["parse_errors"].append(f"LYT parse error: {e}")

    # ── GIT (game instance table) ─────────────────────────────────────────────
    git_data = rm.read(f"{resref}.git")
    if git_data:
        try:
            from ghostscripter.core.services import GFFService
            git = GFFService.parse_bytes(git_data)
            fields = git if isinstance(git, dict) else (git.get("fields") or git)

            def _extract_list(key: str, tag_field: str = "Tag", ref_field: str = "TemplateResRef") -> list:
                entries = fields.get(key, [])
                if not isinstance(entries, list):
                    return []
                out = []
                for item in entries:
                    if not isinstance(item, dict):
                        continue
                    sub = item.get("fields") or item
                    entry: dict = {}
                    tag = sub.get(tag_field) or sub.get("Tag") or sub.get("tag")
                    ref = sub.get(ref_field) or sub.get("TemplateResRef") or sub.get("resref")
                    pos = sub.get("XPosition"), sub.get("YPosition"), sub.get("ZPosition")
                    if tag: entry["tag"] = tag
                    if ref: entry["resref"] = ref
                    if any(v is not None for v in pos):
                        entry["x"] = _safe_float(pos[0])
                        entry["y"] = _safe_float(pos[1])
                        entry["z"] = _safe_float(pos[2])
                    out.append(entry)
                return out

            result["creatures"]  = _extract_list("Creature List")
            result["doors"]      = _extract_list("Door List")
            result["placeables"] = _extract_list("Placeable List")
            result["waypoints"]  = _extract_list("Waypoint List")
            result["triggers"]   = _extract_list("TriggerList")
            result["stores"]     = _extract_list("StoreList")
            result["sounds"]     = _extract_list("SoundList")
            result["encounters"] = _extract_list("EncounterList")

            # GIT runtime state flags
            result["use_templates"]    = fields.get("UseTemplates")
            result["current_weather"]  = fields.get("CurrentWeather")
            result["weather_started"]  = fields.get("WeatherStarted")

            # AreaProperties sub-struct (ambient audio / music overrides)
            area_props = fields.get("AreaProperties")
            if isinstance(area_props, dict):
                ap = area_props.get("fields") or area_props
                def _ap(key):
                    v = ap.get(key)
                    return v if v is not None and v != 0 else None
                if result["ambient_sound"] is None:
                    result["ambient_sound"] = _ap("AmbientSndDay")
                if result["ambient_volume"] is None:
                    result["ambient_volume"] = _ap("AmbientSndDayVol")
                if result["ambient_battle_sound"] is None:
                    result["ambient_battle_sound"] = _ap("EnvAudio")
                if result["music_standard"] is None:
                    result["music_standard"] = _ap("MusicDay")
                if result["music_battle"] is None:
                    result["music_battle"] = _ap("MusicBattle")
                if result["music_delay"] is None:
                    result["music_delay"] = _ap("MusicDelay")

            # Cameras (GITCamera has CameraID + Position + Orientation)
            cam_list = fields.get("CameraList", [])
            if isinstance(cam_list, list):
                cameras = []
                for item in cam_list:
                    sub = item.get("fields") or item if isinstance(item, dict) else {}
                    cam: dict = {}
                    cid = sub.get("CameraID")
                    if cid is not None:
                        cam["camera_id"] = cid
                    pos = sub.get("XPosition"), sub.get("YPosition"), sub.get("ZPosition")
                    if any(v is not None for v in pos):
                        cam["x"] = _safe_float(pos[0])
                        cam["y"] = _safe_float(pos[1])
                        cam["z"] = _safe_float(pos[2])
                    pitch = sub.get("Pitch")
                    if pitch is not None:
                        cam["pitch"] = _safe_float(pitch)
                    cameras.append(cam)
                result["cameras"] = cameras

            # GIT ambient audio overrides (override ARE values when present in top-level fields)
            for git_key, result_key in (
                ("AmbientSndDay",    "ambient_sound"),
                ("AmbientSndDayVol", "ambient_volume"),
                ("MusicDay",         "music_standard"),
                ("MusicBattle",      "music_battle"),
                ("MusicDelay",       "music_delay"),
            ):
                v = fields.get(git_key)
                if v is not None and result[result_key] is None:
                    result[result_key] = v
        except Exception as e:
            result["parse_errors"].append(f"GIT parse error: {e}")

    return _ok(result)


def _safe_float(val) -> float | None:
    """Convert a value to float, returning None on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


async def _get_module(args: dict) -> List[types.TextContent]:
    """Composite module view: IFO fields + area list + entry point + scripts + GIT summaries.

    Reads module.ifo from the loaded installation.  A KotOR module.ifo
    (GFF type IFO) stores the master metadata for a single game module —
    the entry area, player spawn position/direction, all module event scripts,
    and the list of area resrefs that belong to the module.

    When ``include_git`` is True (default False to keep response size manageable),
    each area resref in the ``areas`` list is expanded to a GIT instance-count
    summary — useful for building module maps or validating placements.

    Args:
        game        (str):  "K1" or "K2"
        module_id   (str):  module resref / IFO filename without extension
                            (e.g. "danm13", "tar_m02aa").  Pass "module" to
                            read the global module.ifo from the installation root.
        include_git (bool): if True, add per-area GIT instance counts to
                            the ``area_summaries`` key (default False).

    Returns a dict with keys:
        game, module_id,
        mod_name, tag, vo_id,
        entry_area, entry_x, entry_y, entry_z, entry_dir_x, entry_dir_y,
        areas (list of resref strings from Mod_Area_list),
        area_summaries (list of {area, creatures, doors, placeables, waypoints,
                        triggers, stores, sounds, encounters} — only when
                        include_git=True and the area GIT is readable),
        scripts (dict of non-empty Mod_On* resrefs),
        fields (pruned raw IFO GFF data at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getModule: {e}")

    module_id = (args.get("module_id") or args.get("moduleId") or args.get("module") or "module").lower().strip()
    include_git: bool = bool(args.get("include_git", False))

    rm = _load_rm(game_id)

    ifo_data = rm.read(f"{module_id}.ifo")
    if ifo_data is None:
        # Try bare "module.ifo" as fallback
        ifo_data = rm.read("module.ifo")
    if ifo_data is None:
        return _err(
            f"getModule: IFO not found for '{module_id}' in {game_id}. "
            "Ensure the installation is loaded and the module_id is correct."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(ifo_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)



    # Module event scripts  (IFO uses Mod_OnXxx naming per PyKotor IFO reference)
    scripts: dict = {}
    for field_name in (
        "Mod_OnAcquirItem", "Mod_OnActvtItem", "Mod_OnClientEntr",
        "Mod_OnClientLeav", "Mod_OnHeartbeat", "Mod_OnLoad",
        "Mod_OnModStart", "Mod_OnPlrDeath", "Mod_OnPlrDying",
        "Mod_OnPlrLvlUp", "Mod_OnPlrRest", "Mod_OnPlrRespawn",
        "Mod_OnUnAqreItem", "Mod_OnUsrDefined",
        # alternate naming without Mod_ prefix
        "OnAcquireItem", "OnActivateItem", "OnClientEnter", "OnClientLeave",
        "OnHeartbeat", "OnLoad", "OnModuleStart", "OnPlayerDeath",
        "OnPlayerDying", "OnPlayerLevelUp", "OnPlayerRest", "OnPlayerRespawn",
        "OnUnacquireItem", "OnUserDefined",
    ):
        v = gff_scalar(f, field_name)
        if v:
            scripts[field_name] = v

    # Area list  (Mod_Area_list is a GFFList of structs each with Area_Name)
    areas: list = []
    area_list = f.get("Mod_Area_list", f.get("Area_list", []))
    if not isinstance(area_list, list):
        area_list = []
    for area_entry in area_list:
        sub = area_entry.get("fields") or area_entry if isinstance(area_entry, dict) else {}
        area_name = sub.get("Area_Name") or sub.get("AreaName")
        if isinstance(area_name, dict):
            area_name = area_name.get("value", area_name)
        if area_name:
            areas.append(str(area_name))

    # ── Optional per-area GIT summaries ──────────────────────────────────────
    area_summaries: list = []
    if include_git and areas:
        _GIT_LISTS = {
            "creatures":  "Creature List",
            "doors":      "Door List",
            "placeables": "Placeable List",
            "waypoints":  "Waypoint List",
            "triggers":   "TriggerList",
            "stores":     "StoreList",
            "sounds":     "SoundList",
            "encounters": "EncounterList",
        }
        for area_resref in areas:
            git_data = rm.read(f"{area_resref}.git")
            if git_data is None:
                area_summaries.append({"area": area_resref, "error": "GIT not found"})
                continue
            try:
                git_parsed = GFFService.parse_bytes(git_data)
                gf = git_parsed if isinstance(git_parsed, dict) else (
                    git_parsed.get("fields") or git_parsed
                )
                summary: dict = {"area": area_resref}
                for key, git_key in _GIT_LISTS.items():
                    lst = gf.get(git_key, [])
                    summary[key] = len(lst) if isinstance(lst, list) else 0
                area_summaries.append(summary)
            except Exception as git_err:
                area_summaries.append({"area": area_resref, "error": str(git_err)})

    result: dict = {
        "game":            game_id,
        "module_id":       module_id,
        "mod_name":        gff_locstr(f, "Mod_Name") or gff_locstr(f, "ModName"),
        "tag":             gff_scalar(f, "Mod_Tag") or gff_scalar(f, "Tag"),
        "vo_id":           gff_scalar(f, "Mod_VO_ID") or gff_scalar(f, "VO_ID"),
        "entry_area":      gff_scalar(f, "Mod_Entry_Area") or gff_scalar(f, "EntryArea"),
        "entry_x":         _safe_float(gff_scalar(f, "Mod_Entry_X") or gff_scalar(f, "EntryX")),
        "entry_y":         _safe_float(gff_scalar(f, "Mod_Entry_Y") or gff_scalar(f, "EntryY")),
        "entry_z":         _safe_float(gff_scalar(f, "Mod_Entry_Z") or gff_scalar(f, "EntryZ")),
        "entry_dir_x":     _safe_float(gff_scalar(f, "Mod_Entry_Dir_X") or gff_scalar(f, "EntryDirX")),
        "entry_dir_y":     _safe_float(gff_scalar(f, "Mod_Entry_Dir_Y") or gff_scalar(f, "EntryDirY")),
        "areas":           areas,
        "area_summaries":  area_summaries,
        "scripts":         scripts,
        "fields":          _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_encounter(args: dict) -> List[types.TextContent]:
    """Composite encounter view: UTE blueprint — spawn list, difficulty, scripts.

    Args:
        game   (str): "K1" or "K2"
        resref (str): encounter blueprint resref (UTE), e.g. "enc_taris01"

    Returns a dict with keys:
        game, resref, tag, active, difficulty, faction,
        spawn_list (list of {resref, cr, single_spawn}),
        scripts (dict of non-empty script fields),
        fields (pruned raw UTE GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getEncounter: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getEncounter")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    ute_data = rm.read(f"{resref}.ute")
    if ute_data is None:
        return _err(
            f"getEncounter: blueprint '{resref}.ute' not found in {game_id}. "
            "Try listResType(type='ute') to browse encounter resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(ute_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    # Spawn creature list
    spawn_list: list = []
    creature_list = f.get("CreatureList", [])
    if not isinstance(creature_list, list):
        creature_list = []
    for entry in creature_list:
        sub = entry.get("fields") or entry if isinstance(entry, dict) else {}
        cref = sub.get("ResRef") or sub.get("resref")
        if isinstance(cref, dict):
            cref = cref.get("value", cref)
        cr = sub.get("CR")
        if isinstance(cr, dict):
            cr = cr.get("value", cr)
        single = sub.get("SingleSpawn")
        if isinstance(single, dict):
            single = single.get("value", single)
        if cref:
            spawn_list.append({
                "resref": str(cref),
                "cr": _safe_float(cr),
                "single_spawn": bool(single),
            })

    scripts: dict = {}
    for field_name in ("OnEntered", "OnExhausted", "OnExit",
                       "OnHeartbeat", "OnSpawn", "OnUserDefined"):
        v = gff_scalar(f, field_name)
        if v:
            scripts[field_name] = v

    result: dict = {
        "game":       game_id,
        "resref":     resref,
        "tag":        gff_scalar(f, "Tag"),
        "active":     gff_scalar(f, "Active"),
        "difficulty": gff_scalar(f, "DifficultyIndex") or gff_scalar(f, "Difficulty"),
        "faction":    gff_scalar(f, "Faction"),
        "spawn_list": spawn_list,
        "scripts":    scripts,
        "fields":     _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_trigger(args: dict) -> List[types.TextContent]:
    """Composite trigger view: UTT blueprint — trap settings, linked object, scripts.

    Args:
        game   (str): "K1" or "K2"
        resref (str): trigger blueprint resref (UTT), e.g. "trg_exit01"

    Returns a dict with keys:
        game, resref, tag, trap_type, trap_one_shot, linked_to,
        trap (detectable, disarmable, trap_dc, disarm_dc),
        scripts (dict of non-empty script fields),
        fields (pruned raw UTT GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getTrigger: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getTrigger")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    utt_data = rm.read(f"{resref}.utt")
    if utt_data is None:
        return _err(
            f"getTrigger: blueprint '{resref}.utt' not found in {game_id}. "
            "Try listResType(type='utt') to browse trigger resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(utt_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    scripts: dict = {}
    for field_name in ("ScriptHeartbeat", "ScriptOnEnter", "ScriptOnExit",
                       "ScriptUserDefine", "OnTrapTriggered", "OnDisarm", "OnClick"):
        v = gff_scalar(f, field_name)
        if v:
            scripts[field_name] = v

    result: dict = {
        "game":          game_id,
        "resref":        resref,
        "tag":           gff_scalar(f, "Tag"),
        "trap_type":     gff_scalar(f, "TrapType"),
        "trap_one_shot": gff_scalar(f, "TrapOneShot"),
        "linked_to":     gff_scalar(f, "LinkedTo"),
        "trap": {
            "detectable": gff_scalar(f, "TrapDetectable"),
            "disarmable":  gff_scalar(f, "TrapDisarmable"),
            "trap_dc":     gff_scalar(f, "TrapDetectDC"),
            "disarm_dc":   gff_scalar(f, "DisarmDC"),
        },
        "scripts":  scripts,
        "fields":   _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_waypoint(args: dict) -> List[types.TextContent]:
    """Composite waypoint view: UTW blueprint — position, orientation, map note.

    Args:
        game   (str): "K1" or "K2"
        resref (str): waypoint blueprint resref (UTW), e.g. "wp_entry01"

    Returns a dict with keys:
        game, resref, tag, name,
        x, y, z, dir_x, dir_y,
        has_map_note, map_note_enabled, map_note,
        fields (pruned raw UTW GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getWaypoint: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getWaypoint")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    utw_data = rm.read(f"{resref}.utw")
    if utw_data is None:
        return _err(
            f"getWaypoint: blueprint '{resref}.utw' not found in {game_id}. "
            "Try listResType(type='utw') to browse waypoint resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(utw_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)



    result: dict = {
        "game":             game_id,
        "resref":           resref,
        "tag":              gff_scalar(f, "Tag"),
        "name":             gff_locstr(f, "LocalizedName") or gff_locstr(f, "LocName"),
        "x":                _safe_float(gff_scalar(f, "XPosition")),
        "y":                _safe_float(gff_scalar(f, "YPosition")),
        "z":                _safe_float(gff_scalar(f, "ZPosition")),
        "dir_x":            _safe_float(gff_scalar(f, "XOrientation")),
        "dir_y":            _safe_float(gff_scalar(f, "YOrientation")),
        "has_map_note":     gff_scalar(f, "HasMapNote"),
        "map_note_enabled": gff_scalar(f, "MapNoteEnabled"),
        "map_note":         gff_locstr(f, "MapNote"),
        "fields":           _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_store(args: dict) -> List[types.TextContent]:
    """Composite store/merchant view: UTM blueprint — inventory, pricing, scripts.

    Args:
        game   (str): "K1" or "K2"
        resref (str): store blueprint resref (UTM), e.g. "store_taris01"

    Returns a dict with keys:
        game, resref, tag, name,
        mark_up, mark_down, buy_sell_flag,
        inventory (list of {resref, infinite}),
        scripts (dict of non-empty script fields),
        fields (pruned raw UTM GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getStore: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getStore")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    utm_data = rm.read(f"{resref}.utm")
    if utm_data is None:
        return _err(
            f"getStore: blueprint '{resref}.utm' not found in {game_id}. "
            "Try listResType(type='utm') to browse store resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(utm_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)



    # Inventory list
    inventory: list = []
    item_list = f.get("ItemList", [])
    if not isinstance(item_list, list):
        item_list = []
    for item in item_list:
        sub = item.get("fields") or item if isinstance(item, dict) else {}
        iref = sub.get("InventoryRes") or sub.get("ResRef") or sub.get("resref")
        if isinstance(iref, dict):
            iref = iref.get("value", iref)
        infinite = sub.get("Infinite")
        if isinstance(infinite, dict):
            infinite = infinite.get("value", infinite)
        if iref:
            inventory.append({"resref": str(iref), "infinite": bool(infinite)})

    scripts: dict = {}
    for field_name in ("OnOpenStore",):
        v = gff_scalar(f, field_name)
        if v:
            scripts[field_name] = v

    result: dict = {
        "game":          game_id,
        "resref":        resref,
        "tag":           gff_scalar(f, "Tag"),
        "name":          gff_locstr(f, "LocName"),
        "mark_up":       gff_scalar(f, "MarkUp"),
        "mark_down":     gff_scalar(f, "MarkDown"),
        "buy_sell_flag": gff_scalar(f, "BuySellFlag"),
        "inventory":     inventory,
        "scripts":       scripts,
        "fields":        _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_sound(args: dict) -> List[types.TextContent]:
    """Composite sound object view: UTS blueprint — audio settings and position.

    Args:
        game   (str): "K1" or "K2"
        resref (str): sound object blueprint resref (UTS), e.g. "snd_amb_den"

    Returns a dict with keys:
        game, resref, tag,
        active, continuous, looping, positional,
        volume, pitch_variation,
        min_distance, max_distance,
        x, y, z,
        sounds (list of audio ResRef strings),
        fields (pruned raw UTS GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getSound: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getSound")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    uts_data = rm.read(f"{resref}.uts")
    if uts_data is None:
        return _err(
            f"getSound: blueprint '{resref}.uts' not found in {game_id}. "
            "Try listResType(type='uts') to browse sound object resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(uts_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    # Sounds list (list of CResRef structs)
    sounds: list = []
    sounds_list = f.get("Sounds", [])
    if not isinstance(sounds_list, list):
        sounds_list = []
    for snd in sounds_list:
        sub = snd.get("fields") or snd if isinstance(snd, dict) else {}
        sref = sub.get("Sound") or sub.get("ResRef") or sub.get("resref")
        if isinstance(sref, dict):
            sref = sref.get("value", sref)
        if sref:
            sounds.append(str(sref))

    result: dict = {
        "game":              game_id,
        "resref":            resref,
        "tag":               gff_scalar(f, "Tag"),
        "active":            gff_scalar(f, "Active"),
        "continuous":        gff_scalar(f, "Continuous"),
        "looping":           gff_scalar(f, "Looping"),
        "positional":        gff_scalar(f, "Positional"),
        "volume":            gff_scalar(f, "Volume"),
        "pitch_variation":   _safe_float(gff_scalar(f, "PitchVariation")),
        "min_distance":      _safe_float(gff_scalar(f, "MinDistance")),
        "max_distance":      _safe_float(gff_scalar(f, "MaxDistance")),
        "x":                 _safe_float(gff_scalar(f, "XPosition")),
        "y":                 _safe_float(gff_scalar(f, "YPosition")),
        "z":                 _safe_float(gff_scalar(f, "ZPosition")),
        "sounds":            sounds,
        "fields":            _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_door(args: dict) -> List[types.TextContent]:
    """Composite door view: UTD blueprint stats + script fields + linked area.

    Args:
        game   (str): "K1" or "K2"
        resref (str): door blueprint resref (UTD file), e.g. "door_med_01"

    Returns a dict with keys:
        game, resref, tag, local_ident, generic_type, animation_state,
        lock (locked, key_required, key_name, lock_dc, open_lock_dc),
        trap (detectable, disarmable, trap_type, trap_dc, disarm_dc),
        scripts (dict of non-empty script fields),
        conversation (resref if set),
        fields (pruned raw UTD GFF data at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getDoor: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getDoor")
    if err:
        return _err(err)

    rm = _load_rm(game_id)

    utd_data = rm.read(f"{resref}.utd")
    if utd_data is None:
        return _err(
            f"getDoor: blueprint '{resref}.utd' not found in {game_id}. "
            "Try listResType(type='utd') to browse door resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(utd_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    result: dict = {
        "game":            game_id,
        "resref":          resref,
        "tag":             gff_scalar(f, "Tag"),
        "local_ident":     gff_scalar(f, "LocName"),
        "generic_type":    gff_scalar(f, "GenericType"),
        "animation_state": gff_scalar(f, "AnimationState"),
        "lock": {
            "locked":       gff_scalar(f, "Locked"),
            "key_required": gff_scalar(f, "KeyRequired"),
            "key_name":     gff_scalar(f, "KeyName"),
            "lock_dc":      gff_scalar(f, "LockDC"),
            "open_lock_dc": gff_scalar(f, "OpenLockDC"),
        },
        "trap": {
            "detectable":  gff_scalar(f, "TrapDetectable"),
            "disarmable":  gff_scalar(f, "TrapDisarmable"),
            "trap_type":   gff_scalar(f, "TrapType"),
            "trap_dc":     gff_scalar(f, "TrapDetectDC"),
            "disarm_dc":   gff_scalar(f, "DisarmDC"),
        },
    }

    # Script fields
    scripts = {}
    for field in ("OnClick", "OnClosed", "OnDamaged", "OnDeath", "OnDisarm",
                  "OnFailToOpen", "OnHeartbeat", "OnLock", "OnMeleeAttacked",
                  "OnOpen", "OnSpellCastAt", "OnTrapTriggered", "OnUnlock",
                  "OnUserDefined", "LinkedTo", "LinkedToFlags"):
        v = gff_scalar(f, field)
        if v:
            scripts[field] = v
    result["scripts"] = scripts

    conv = gff_scalar(f, "Conversation")
    if conv:
        result["conversation"] = conv

    result["fields"] = _prune(raw, depth=2)
    return _ok(result)


async def _get_placeable(args: dict) -> List[types.TextContent]:
    """Composite placeable view: UTP blueprint stats + script fields + inventory.

    Args:
        game   (str): "K1" or "K2"
        resref (str): placeable blueprint resref (UTP file), e.g. "plc_footlocker"

    Returns a dict with keys:
        game, resref, tag, local_ident, appearance, static, useable,
        lock (locked, key_required, key_name, lock_dc, open_lock_dc),
        trap (detectable, disarmable, trap_type, trap_dc, disarm_dc),
        inventory (list of item resrefs if present),
        scripts (dict of non-empty script fields),
        conversation (resref if set),
        fields (pruned raw UTP GFF data at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getPlaceable: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getPlaceable")
    if err:
        return _err(err)

    rm = _load_rm(game_id)

    utp_data = rm.read(f"{resref}.utp")
    if utp_data is None:
        return _err(
            f"getPlaceable: blueprint '{resref}.utp' not found in {game_id}. "
            "Try listResType(type='utp') to browse placeable resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(utp_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    result: dict = {
        "game":       game_id,
        "resref":     resref,
        "tag":        gff_scalar(f, "Tag"),
        "local_ident": gff_scalar(f, "LocName"),
        "appearance": gff_scalar(f, "Appearance"),
        "static":     gff_scalar(f, "Static"),
        "useable":    gff_scalar(f, "Useable"),
        "lock": {
            "locked":       gff_scalar(f, "Locked"),
            "key_required": gff_scalar(f, "KeyRequired"),
            "key_name":     gff_scalar(f, "KeyName"),
            "lock_dc":      gff_scalar(f, "LockDC"),
            "open_lock_dc": gff_scalar(f, "OpenLockDC"),
        },
        "trap": {
            "detectable":  gff_scalar(f, "TrapDetectable"),
            "disarmable":  gff_scalar(f, "TrapDisarmable"),
            "trap_type":   gff_scalar(f, "TrapType"),
            "trap_dc":     gff_scalar(f, "TrapDetectDC"),
            "disarm_dc":   gff_scalar(f, "DisarmDC"),
        },
    }

    # Inventory items (ItemList in UTP)
    item_list = f.get("ItemList", [])
    if not isinstance(item_list, list):
        item_list = []
    inventory = []
    for item in item_list:
        sub = item.get("fields") or item if isinstance(item, dict) else {}
        iref = sub.get("InventoryRes") or sub.get("resref")
        if isinstance(iref, dict):
            iref = iref.get("value", iref)
        if iref:
            inventory.append(iref)
    result["inventory"] = inventory

    # Script fields
    scripts = {}
    for field in ("OnClick", "OnClosed", "OnDamaged", "OnDeath", "OnDisarm",
                  "OnHeartbeat", "OnInvDisturbed", "OnLock", "OnMeleeAttacked",
                  "OnOpen", "OnSpellCastAt", "OnTrapTriggered", "OnUnlock",
                  "OnUsed", "OnUserDefined"):
        v = gff_scalar(f, field)
        if v:
            scripts[field] = v
    result["scripts"] = scripts

    conv = gff_scalar(f, "Conversation")
    if conv:
        result["conversation"] = conv

    result["fields"] = _prune(raw, depth=2)
    return _ok(result)


async def _get_item(args: dict) -> List[types.TextContent]:
    """Composite item view: UTI blueprint stats + properties + cost.

    Args:
        game   (str): "K1" or "K2"
        resref (str): item blueprint resref (UTI file), e.g. "g_w_lghtsbr01"
        includeTLK (bool, default True): resolve TLK strref to text for name/description

    Returns a dict with keys:
        game, resref, tag, base_item, stack_size, cost, add_cost, stolen,
        name (resolved text if TLK available), description (resolved text),
        identified, charges, upgrade_level,
        properties (list of item property dicts),
        scripts (dict of non-empty script fields),
        fields (pruned raw UTI GFF data at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getItem: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getItem")
    if err:
        return _err(err)

    include_tlk = args.get("includeTLK", True)

    rm = _load_rm(game_id)

    uti_data = rm.read(f"{resref}.uti")
    if uti_data is None:
        return _err(
            f"getItem: blueprint '{resref}.uti' not found in {game_id}. "
            "Try listResType(type='uti') to browse item resrefs."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(uti_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    result: dict = {
        "game":           game_id,
        "resref":         resref,
        "tag":            gff_scalar(f, "Tag"),
        "base_item":      gff_scalar(f, "BaseItem"),
        "stack_size":     gff_scalar(f, "StackSize"),
        "cost":           gff_scalar(f, "Cost"),
        "add_cost":       gff_scalar(f, "AddCost"),
        "stolen":         gff_scalar(f, "Stolen"),
        "identified":     gff_scalar(f, "Identified"),
        "charges":        gff_scalar(f, "Charges"),
        "upgrade_level":  gff_scalar(f, "UpgradeLevel"),
    }

    # Resolve LocalizedString strrefs for Name / Description
    def _resolve_locstring(key: str) -> str | None:
        """Return plain text from a CExoLocString field, optionally via TLK."""
        entry = f.get(key)
        if entry is None:
            return None
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            # Inline substring (language 0)
            for sub_key in ("0", 0, "value"):
                if sub_key in entry:
                    v = entry[sub_key]
                    if isinstance(v, str) and v:
                        return v
            strref = entry.get("strref", -1)
            if isinstance(strref, dict):
                strref = strref.get("value", -1)
            if include_tlk and isinstance(strref, int) and strref >= 0:
                try:
                    from ghostscripter.core.services import TLKService
                    tlk_data = rm.read("dialog.tlk")
                    if tlk_data:
                        tlk = TLKService.parse_bytes(tlk_data, "dialog.tlk")
                        return TLKService.lookup(tlk, [strref]).get(strref, {}).get("text")
                except Exception as _e:
                    log.debug("_get_item TLK lookup error: %s", _e)
        return None

    result["name"] = _resolve_locstring("LocalizedName") or _resolve_locstring("Name")
    result["description"] = _resolve_locstring("DescIdentified") or _resolve_locstring("Description")

    # Item properties list (PropertiesList)
    props_raw = f.get("PropertiesList", [])
    if not isinstance(props_raw, list):
        props_raw = []
    properties = []
    for prop in props_raw:
        sub = prop.get("fields") or prop if isinstance(prop, dict) else {}
        entry = {}
        for pk in ("PropertyName", "Subtype", "CostTable", "CostValue",
                   "Param1", "Param1Value", "ChanceAppear", "UpgradeType"):
            pv = sub.get(pk)
            if isinstance(pv, dict):
                pv = pv.get("value", pv)
            if pv is not None:
                entry[pk] = pv
        if entry:
            properties.append(entry)
    result["properties"] = properties

    # Script fields
    scripts = {}
    for field in ("OnActivated", "OnHeartbeat", "OnUserDefined"):
        v = gff_scalar(f, field)
        if v:
            scripts[field] = v
    result["scripts"] = scripts

    result["fields"] = _prune(raw, depth=2)
    return _ok(result)


async def _get_creature(args: dict) -> List[types.TextContent]:
    """Composite creature view: UTC blueprint — stats, class, appearance, scripts.

    Reads a UTC (creature template) file and returns the key fields an AI agent
    needs to understand a KotOR NPC: tag, name, race/subrace, gender,
    class-level pairs, all six ability scores, HP, AC, appearance row,
    faction, conversation resref, equipment list, feat list, skill ranks,
    and all script fields.

    Args:
        game        (str): "K1" or "K2"
        resref      (str): creature blueprint resref without extension (max 16 chars)
        include_tlk (bool, default True): resolve localized FirstName/LastName via dialog.tlk

    Returns a dict with:
        game, resref, tag, name, race, subrace, gender,
        classes (list of {class_id, level}),
        str, dex, con, int_, wis, cha, hp, max_hp, ac,
        appearance, faction, conversation,
        equipment (dict slot_name → resref),
        feats (list of feat IDs),
        skills (dict skill_name → rank),
        scripts (dict event → resref),
        fields (pruned raw UTC GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getCreature: {e}")

    resref = (args.get("resref") or "").strip().lower()
    if not resref:
        return _err("getCreature: 'resref' is required.")
    if len(resref) > 16:
        return _err(f"getCreature: resref '{resref}' exceeds 16 characters.")

    include_tlk: bool = bool(args.get("include_tlk", True))

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.utc")
    if data is None:
        return _err(
            f"getCreature: '{resref}.utc' not found in {game_id} installation. "
            "Ensure loadInstallation has been called and the resref is correct."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)



    # Build name: FirstName + LastName
    first = gff_locstr(f, "FirstName", rm=rm if include_tlk else None)
    last = gff_locstr(f, "LastName", rm=rm if include_tlk else None)
    name_parts = [p for p in (first, last) if p]
    name = " ".join(name_parts) if name_parts else None

    # Class/level list
    classes: list = []
    cl_raw = f.get("ClassList", f.get("Class_List", []))
    if not isinstance(cl_raw, list):
        cl_raw = []
    for cl_entry in cl_raw:
        sub = gff_struct_fields(cl_entry)
        cls_id = gff_scalar(sub, "Class")
        lvl    = gff_scalar(sub, "ClassLevel")
        if cls_id is not None:
            classes.append({"class_id": cls_id, "level": lvl})

    # Equipment
    _EQUIP_SLOTS = {
        "Equip_ArmorItem": "armor", "Equip_RightHand": "right_hand",
        "Equip_LeftHand": "left_hand", "Equip_RightRing": "right_ring",
        "Equip_LeftRing": "left_ring", "Equip_Head": "head",
        "Equip_Neck": "neck", "Equip_Gloves": "gloves",
        "Equip_Boots": "boots", "Equip_Belt": "belt",
        "Equip_Implant": "implant", "Equip_CreatureItem": "creature_item",
        "Equip_CreatureItem2": "creature_item2", "Equip_CreatureItem3": "creature_item3",
    }
    equipment: dict = {}
    equip_raw = f.get("Equip_ItemList", f.get("ItemList", []))
    # Some IFOs encode equipment as top-level EquipItemList
    for gff_key, slot_name in _EQUIP_SLOTS.items():
        v = gff_scalar(f, gff_key)
        if v:
            equipment[slot_name] = str(v)
    # Also check Equip_ItemList
    if isinstance(equip_raw, list):
        for item_entry in equip_raw:
            sub  = gff_struct_fields(item_entry)
            repo = gff_scalar(sub, "EquipRes") or gff_scalar(sub, "ResRef") or gff_scalar(sub, "Resref")
            slot_idx = gff_scalar(sub, "Repos_Posx") or gff_scalar(sub, "Repos_PosY")
            if repo:
                equipment[f"slot_{slot_idx}"] = str(repo)

    # Feats (FeatList is a GFFList of structs each with a Feat INT16)
    feats: list = []
    feat_raw = f.get("FeatList", [])
    if not isinstance(feat_raw, list):
        feat_raw = []
    for fe in feat_raw:
        sub = fe.get("fields") or fe if isinstance(fe, dict) else {}
        fid = sub.get("Feat")
        if isinstance(fid, dict):
            fid = fid.get("value", fid)
        if fid is not None:
            feats.append(int(fid))

    # Skills (SkillList is a GFFList of structs each with Rank)
    _SKILL_NAMES = [
        "computer_use", "demolitions", "stealth", "awareness",
        "persuade", "repair", "security", "treat_injury",
    ]
    skills: dict = {}
    skill_raw = f.get("SkillList", [])
    if not isinstance(skill_raw, list):
        skill_raw = []
    for i, sk in enumerate(skill_raw):
        sub = sk.get("fields") or sk if isinstance(sk, dict) else {}
        rank = sub.get("Rank")
        if isinstance(rank, dict):
            rank = rank.get("value", rank)
        if rank is not None:
            key = _SKILL_NAMES[i] if i < len(_SKILL_NAMES) else f"skill_{i}"
            skills[key] = int(rank)

    # Script fields
    scripts: dict = {}
    for field in (
        "ScriptSpawn", "ScriptDeath", "ScriptPerceived", "ScriptAttacked",
        "ScriptDamaged", "ScriptEndCombat", "ScriptHeartbeat", "ScriptOnBlocked",
        "ScriptUserDefine", "OnSpawn", "OnDeath", "OnPerception", "OnAttacked",
        "OnDamaged", "OnEndCombatRound", "OnHeartbeat", "OnBlocked", "OnUserDefined",
    ):
        v = gff_scalar(f, field)
        if v:
            scripts[field] = str(v)

    result: dict = {
        "game":         game_id,
        "resref":       resref,
        "tag":          gff_scalar(f, "Tag"),
        "name":         name,
        "race":         gff_scalar(f, "Race"),
        "subrace":      gff_scalar(f, "SubraceIndex") or gff_scalar(f, "Subrace"),
        "gender":       gff_scalar(f, "Gender"),
        "classes":      classes,
        "str":          gff_scalar(f, "Str"),
        "dex":          gff_scalar(f, "Dex"),
        "con":          gff_scalar(f, "Con"),
        "int_":         gff_scalar(f, "Int"),
        "wis":          gff_scalar(f, "Wis"),
        "cha":          gff_scalar(f, "Cha"),
        "hp":           gff_scalar(f, "CurrentHitPoints") or gff_scalar(f, "HitPoints"),
        "max_hp":       gff_scalar(f, "MaxHitPoints"),
        "ac":           gff_scalar(f, "NaturalAC"),
        "appearance":   gff_scalar(f, "Appearance_Type"),
        "faction":      gff_scalar(f, "FactionID") or gff_scalar(f, "Faction"),
        "conversation": gff_scalar(f, "Conversation") or gff_scalar(f, "TemplateResRef"),
        "equipment":    equipment,
        "feats":        feats,
        "skills":       skills,
        "scripts":      scripts,
        "fields":       _prune(raw, depth=2),
    }
    return _ok(result)


async def _get_faction(args: dict) -> List[types.TextContent]:
    """Composite faction view: FAC blueprint — faction names and mutual reputation table.

    Reads the faction GFF (type FAC) for the loaded installation.  KotOR
    stores faction data in a single file called ``repute.fac`` (or similar).
    Each faction entry has a name (CExoString) and a reputation list that
    maps faction index → integer reputation (0-100).

    Args:
        game    (str): "K1" or "K2"
        resref  (str): faction file resref, usually "repute" (default: "repute")

    Returns a dict with keys:
        game, resref,
        factions (list of {index, name, rep_entries: [{target_faction, reputation}]}),
        fields   (pruned raw FAC GFF at depth 2)
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getFaction: {e}")

    resref = args.get("resref", "repute").lower().strip()
    if not resref:
        resref = "repute"

    err = _validate_resref(resref, "getFaction")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    fac_data = rm.read(f"{resref}.fac")
    if fac_data is None:
        return _err(
            f"getFaction: '{resref}.fac' not found in {game_id}. "
            "Use listResType(type='fac') to discover available faction files."
        )

    from ghostscripter.core.services import GFFService
    raw = GFFService.parse_bytes(fac_data)
    f = raw if isinstance(raw, dict) else (raw.get("fields") or raw)


    # Faction list — FactionList is a GFFList of structs
    factions: list[dict] = []
    faction_list = f.get("FactionList", [])
    if not isinstance(faction_list, list):
        faction_list = []

    for idx, entry in enumerate(faction_list):
        sub = entry.get("fields") or entry if isinstance(entry, dict) else {}


        name = gff_scalar(sub, "FactionName") or gff_scalar(sub, "Name") or f"faction_{idx}"

        # Reputation table — RepList is a list of {FactionID, FactionRep}
        rep_list_raw = sub.get("RepList", [])
        if not isinstance(rep_list_raw, list):
            rep_list_raw = []
        rep_entries: list[dict] = []
        for rep_entry in rep_list_raw:
            rsub = rep_entry.get("fields") or rep_entry if isinstance(rep_entry, dict) else {}


            faction_id = gff_scalar(rsub, "FactionID")
            rep_val = gff_scalar(rsub, "FactionRep")
            if faction_id is not None:
                rep_entries.append({
                    "target_faction_index": int(faction_id) if faction_id is not None else None,
                    "reputation": int(rep_val) if rep_val is not None else None,
                })

        factions.append({
            "index": idx,
            "name": str(name),
            "rep_entries": rep_entries,
        })

    result: dict = {
        "game":     game_id,
        "resref":   resref,
        "factions": factions,
        "count":    len(factions),
        "fields":   _prune(raw, depth=2),
    }
    return _ok(result)


# ─── Handler dispatch table ───────────────────────────────────────────────────


async def _get_blueprint(args: dict) -> List[types.TextContent]:
    """Universal KotOR blueprint reader for UTC/UTI/UTP/UTD/UTE/UTM/UTS/UTT/UTW.

    All blueprint types are GFF-based and share common fields (tag, resref, name,
    description, scripts). This tool reads any blueprint resref and returns a rich
    JSON view, auto-detecting the resource type from the file extension.

    Supported resource types:
        utc  – creature blueprint      utd  – door blueprint
        uti  – item blueprint          utm  – merchant store blueprint
        utp  – placeable blueprint     uts  – ambient sound blueprint
        ute  – encounter blueprint     utt  – trigger blueprint
        utw  – waypoint blueprint

    Args:
        game    (str): "K1" or "K2"
        resref  (str): blueprint resref (e.g. "n_bastila", "g_w_lghtsbr01")
        type    (str): resource type extension (utc/uti/utp/utd/ute/utm/uts/utt/utw)

    Returns:
        dict with all GFF fields, a pruned scripts sub-dict, and inventory list.
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"getBlueprint: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "getBlueprint")
    if err:
        return _err(err)

    res_type = args.get("type", "").lower().strip().lstrip(".")
    VALID_BLUEPRINT_TYPES = {
        "utc", "uti", "utp", "utd", "ute", "utm", "uts", "utt", "utw"
    }
    if not res_type:
        return _err("getBlueprint: 'type' is required (utc/uti/utp/utd/ute/utm/uts/utt/utw).")
    if res_type not in VALID_BLUEPRINT_TYPES:
        return _err(
            f"getBlueprint: unsupported type '{res_type}'. "
            f"Supported: {', '.join(sorted(VALID_BLUEPRINT_TYPES))}"
        )

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.{res_type}")
    if data is None:
        return _err(f"getBlueprint: '{resref}.{res_type}' not found in {game_id} installation.")

    try:
        from ghostscripter.core.services import GFFService
        gff = GFFService.parse_bytes(data)
        fields = gff if isinstance(gff, dict) else (gff.get("fields") or gff)
    except Exception as e:
        return _err(f"getBlueprint: GFF parse error — {e}")

    # Common fields present in all blueprint types
    result: dict = {
        "game": game_id,
        "resref": resref,
        "type": res_type,
        "tag":         fields.get("Tag") or fields.get("tag"),
        "template_resref": fields.get("TemplateResRef") or fields.get("ResRef"),
        "comment":     fields.get("Comment"),
    }

    # Name (LocString)
    name_raw = fields.get("LocalizedName") or fields.get("Name") or fields.get("FirstName")
    if isinstance(name_raw, dict):
        result["name"] = name_raw.get("value") or name_raw.get("en") or str(name_raw)
    else:
        result["name"] = name_raw

    # Description (LocString)
    desc_raw = fields.get("Description") or fields.get("DescIdentified")
    if isinstance(desc_raw, dict):
        result["description"] = desc_raw.get("value") or desc_raw.get("en") or str(desc_raw)
    else:
        result["description"] = desc_raw

    # Scripts: collect all ScriptXxx / OnXxx fields
    scripts: dict = {}
    for k, v in fields.items():
        if (k.startswith("Script") or k.startswith("On")) and v and v != "":
            scripts[k] = v
    result["scripts"] = scripts

    # Type-specific fields
    if res_type == "utc":
        result.update({
            "first_name":    fields.get("FirstName", {}).get("value") if isinstance(fields.get("FirstName"), dict) else fields.get("FirstName"),
            "last_name":     fields.get("LastName", {}).get("value") if isinstance(fields.get("LastName"), dict) else fields.get("LastName"),
            "appearance":    fields.get("Appearance_Type"),
            "gender":        fields.get("Gender"),
            "race":          fields.get("Race"),
            "subrace":       fields.get("SubraceIndex"),
            "faction":       fields.get("FactionID"),
            "hp":            fields.get("HitPoints"),
            "hp_current":    fields.get("CurrentHitPoints"),
            "hp_max":        fields.get("MaxHitPoints"),
            "str":           fields.get("Str"),
            "dex":           fields.get("Dex"),
            "con":           fields.get("Con"),
            "int":           fields.get("Int"),
            "wis":           fields.get("Wis"),
            "cha":           fields.get("Cha"),
            "conversation":  fields.get("Conversation"),
            "class_list":    fields.get("ClassList", []),
            "equip_item_list": fields.get("Equip_ItemList", []),
            "item_list":     fields.get("ItemList", []),
        })
    elif res_type == "uti":
        result.update({
            "base_item":     fields.get("BaseItem"),
            "cost":          fields.get("Cost"),
            "add_cost":      fields.get("AddCost"),
            "stolen":        fields.get("Stolen"),
            "identified":    fields.get("Identified"),
            "charges":       fields.get("Charges"),
            "stack_size":    fields.get("StackSize"),
            "model_part1":   fields.get("ModelPart1"),
            "model_part2":   fields.get("ModelPart2"),
            "model_part3":   fields.get("ModelPart3"),
            "texture_var":   fields.get("TextureVar"),
            "upgrade_level": fields.get("UpgradeLevel"),
            "properties":    fields.get("PropertiesList", []),
        })
    elif res_type == "utp":
        result.update({
            "appearance":    fields.get("Appearance"),
            "conversation":  fields.get("Conversation"),
            "faction":       fields.get("Faction"),
            "hp":            fields.get("HP"),
            "hp_current":    fields.get("CurrentHP"),
            "hardness":      fields.get("Hardness"),
            "fort_save":     fields.get("Fort"),
            "locked":        fields.get("Locked"),
            "key_required":  fields.get("KeyRequired"),
            "key_name":      fields.get("KeyName"),
            "has_inventory": fields.get("HasInventory"),
            "item_list":     fields.get("ItemList", []),
            "static":        fields.get("Static"),
        })
    elif res_type == "utd":
        result.update({
            "appearance":    fields.get("AppearanceID"),
            "conversation":  fields.get("Conversation"),
            "faction":       fields.get("Faction"),
            "hp":            fields.get("HP"),
            "hp_current":    fields.get("CurrentHP"),
            "hardness":      fields.get("Hardness"),
            "fort_save":     fields.get("Fort"),
            "locked":        fields.get("Locked"),
            "key_required":  fields.get("KeyRequired"),
            "key_name":      fields.get("KeyName"),
            "generic_type":  fields.get("GenericType"),
            "linked_to":     fields.get("LinkedTo"),
            "linked_to_flags": fields.get("LinkedToFlags"),
        })
    elif res_type == "ute":
        result.update({
            "active":        fields.get("Active"),
            "difficulty":    fields.get("DifficultyIndex"),
            "faction":       fields.get("Faction"),
            "max_creatures": fields.get("MaxCreatures"),
            "reset_time":    fields.get("ResetTime"),
            "spawn_option":  fields.get("SpawnOption"),
            "creature_list": fields.get("CreatureList", []),
        })
    elif res_type == "utm":
        result.update({
            "mark_up":       fields.get("MarkUp"),
            "mark_down":     fields.get("MarkDown"),
            "black_market":  fields.get("BlackMarket"),
            "id":            fields.get("ID"),
            "item_list":     fields.get("ItemList", []),
        })
    elif res_type == "uts":
        result.update({
            "active":        fields.get("Active"),
            "looping":       fields.get("Looping"),
            "positional":    fields.get("Positional"),
            "priority":      fields.get("Priority"),
            "elevation":     fields.get("Elevation"),
            "max_distance":  fields.get("MaxDistance"),
            "min_distance":  fields.get("MinDistance"),
            "random_range":  fields.get("RandomRangeX") or fields.get("RandomRange"),
            "sound_list":    fields.get("Sounds", []),
        })
    elif res_type == "utt":
        result.update({
            "faction":       fields.get("Faction"),
            "type":          fields.get("Type"),
            "cursor":        fields.get("Cursor"),
            "highlight_height": fields.get("HighlightHeight"),
            "linked_to":     fields.get("LinkedTo"),
            "linked_to_flags": fields.get("LinkedToFlags"),
        })
    elif res_type == "utw":
        result.update({
            "appearance":    fields.get("Appearance"),
            "linked_to":     fields.get("LinkedTo"),
            "map_note":      fields.get("MapNote"),
            "map_note_enabled": fields.get("MapNoteEnabled"),
            "has_map_note":  fields.get("HasMapNote"),
        })

    # Prune None values for cleaner output
    result = {k: v for k, v in result.items() if v is not None or k in ("tag", "name", "description")}
    return _ok(result)
