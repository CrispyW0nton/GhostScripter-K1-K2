"""Read-only MCP tool handlers (detect, load, list, read, search)."""
from __future__ import annotations

from typing import Any, List

import mcp.types as types

import os
from pathlib import Path

from ghostscripter.mcp.tools_pkg._helpers import (
    _2DA_CACHE, _DEFAULT_PATHS, _INSTALLS, _err, _load_rm, _normalize_game,
    _ok, _prune, _validate_resref, log,
    gff_scalar, gff_locstr, gff_resref, gff_int, gff_float, gff_list,
    gff_struct_fields, read_module_resource,
)


async def _detect_installations(args: dict) -> List[types.TextContent]:
    result = {}
    for gid in ("K1", "K2"):
        found = []
        env_keys = {
            "K1": [("K1_PATH", "env"), ("KOTOR_PATH", "env"), ("KOTOR1_PATH", "env")],
            "K2": [("K2_PATH", "env"), ("TSL_PATH", "env"), ("KOTOR2_PATH", "env")],
        }
        for key, label in env_keys[gid]:
            p = os.environ.get(key, "").strip()
            if p:
                found.append({"path": p, "exists": Path(p).is_dir(), "label": key})
        for p_str in _DEFAULT_PATHS[gid]:
            p = Path(p_str)
            if p.is_dir():
                found.append({"path": str(p), "exists": True, "label": "default"})
        result[gid] = {
            "candidates": found,
            "loaded": gid in _INSTALLS,
        }
    return _ok(result)


async def _load_installation(args: dict) -> List[types.TextContent]:
    raw_game = args.get("game") or ""
    if not raw_game:
        return _err("gsLoadInstallation: 'game' is required ('K1' or 'K2').")
    try:
        game_id = _normalize_game(raw_game)
    except ValueError as e:
        return _err(f"gsLoadInstallation: {e}")
    path = args.get("path")
    rm = _load_rm(game_id, path)
    game_path = _find_game_path(game_id) if not path else Path(path)
    return _ok({
        "game": game_id,
        "path": str(game_path or "unknown"),
        "resources_indexed": len(rm._key_entries) if hasattr(rm, "_key_entries") else "?",
        "override_files": len(getattr(rm, "_override_files", {})),
    })


async def _list_resources(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"gsListResources: {e}")
    rm = _load_rm(game_id)
    res_type = args.get("resourceType", "").strip().lstrip(".")
    location = args.get("location", "all").lower()
    query = args.get("query", "").lower()
    limit = min(int(args.get("limit", 50)), 500)

    if res_type:
        entries = rm.list_by_type(res_type)
    else:
        # Collect all entries from all types
        from ghostscripter.core.resource_manager import RESTYPE_EXT
        entries = []
        seen_types = set()
        for eid, ext in RESTYPE_EXT.items():
            if ext not in seen_types:
                seen_types.add(ext)
                entries.extend(rm.list_by_type(ext))

    # Location filter
    if location == "override":
        entries = [e for e in entries if "override" in e.source_file.lower()]
    elif location == "chitin":
        entries = [e for e in entries if "override" not in e.source_file.lower()]

    # Query filter
    if query:
        entries = [e for e in entries if query in e.resref.lower()]

    truncated = len(entries) > limit
    entries = entries[:limit]

    items = [
        {
            "resref": e.resref,
            "restype": e.restype_str or f"type{e.restype}",
            "source": e.source_file,
            "size": e.size,
        }
        for e in entries
    ]
    return _ok({"count": len(items), "truncated": truncated, "items": items})


async def _describe_resource(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"gsDescribeResource: {e}")
    resref = (args.get("resref") or "").lower()
    restype = (args.get("restype") or "").lower().lstrip(".")
    if not resref:
        return _err("gsDescribeResource: 'resref' is required.")
    if not restype:
        return _err("gsDescribeResource: 'restype' is required.")
    rm = _load_rm(game_id)

    data = rm.read(f"{resref}.{restype}")
    if data is None:
        return _err(f"Resource not found: {resref}.{restype} in {game_id}")

    summary = {
        "resref": resref,
        "restype": restype.upper(),
        "size_bytes": len(data),
    }

    # Type-specific summaries
    if restype in ("gff", "dlg", "utc", "utp", "uts", "utt", "utw", "ute", "utm",
                   "are", "git", "jrl", "bic", "ifo", "fac", "pth"):
        try:
            from ghostscripter.core.services import GFFService
            parsed = GFFService.parse_bytes(data)
            top_keys = list(parsed.keys())[:20]
            summary["type"] = "GFF"
            summary["file_type"] = parsed.get("__file_type", restype.upper())
            summary["top_level_fields"] = top_keys
            summary["field_count"] = len(parsed)
        except Exception as e:
            summary["parse_error"] = str(e)

    elif restype == "2da":
        try:
            from ghostscripter.core.services import TwoDAService
            tda = TwoDAService.parse_bytes(data, resref)
            summary["type"] = "2DA"
            summary["columns"] = tda.columns
            summary["row_count"] = len(tda.rows)
            summary["first_5_labels"] = [r.label for r in tda.rows[:5]]
        except Exception as e:
            summary["parse_error"] = str(e)

    elif restype == "tlk":
        try:
            from ghostscripter.core.services import TLKService
            tlk = TLKService.parse_bytes(data, f"{resref}.tlk")
            summary.update(TLKService.summary(tlk))
        except Exception as e:
            summary["parse_error"] = str(e)

    elif restype == "jrl":
        try:
            from ghostscripter.core.services import JournalService
            jrl = JournalService.parse_bytes(data)
            summary["type"] = "JRL"
            summary["category_count"] = len(jrl.categories)
            summary["categories"] = [
                {
                    "tag": c.tag,
                    "name": c.name,
                    "entry_count": len(c.entries),
                }
                for c in jrl.categories[:10]
            ]
        except Exception as e:
            summary["parse_error"] = str(e)

    elif restype in ("nss", "ncs"):
        summary["type"] = restype.upper()
        if restype == "nss":
            summary["source_lines"] = data.count(b"\n")
            summary["preview"] = data[:200].decode("latin-1", errors="replace")

    return _ok(summary)


async def _read_gff(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readGFF: {e}")
    resref = (args.get("resref") or "").lower()
    restype = (args.get("restype") or "").lower().lstrip(".")
    if not resref:
        return _err("readGFF: 'resref' is required.")
    if not restype:
        return _err("readGFF: 'restype' is required (e.g. 'utc', 'dlg', 'jrl').")
    max_depth_raw = args.get("maxDepth")
    if max_depth_raw is None:
        max_depth = None
    else:
        if isinstance(max_depth_raw, bool):
            return _err("readGFF: 'maxDepth' must be a positive integer when supplied.")
        try:
            max_depth = int(max_depth_raw)
        except (TypeError, ValueError):
            return _err("readGFF: 'maxDepth' must be a positive integer when supplied.")
        if max_depth < 1:
            return _err("readGFF: 'maxDepth' must be at least 1.")

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.{restype}")
    if data is None:
        return _err(f"Resource not found: {resref}.{restype} in {game_id}")

    try:
        import hashlib

        from ghostscripter.core.services import GFFService
        document = GFFService.parse_typed_bytes(data, max_depth=max_depth)
        # Source metadata is intentionally outside the typed root and is
        # ignored by writeGFF, so the entire readGFF response can be passed
        # back as its ``document`` argument.
        document["source"] = {
            "game": game_id,
            "resref": resref,
            "restype": restype.lower(),
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        return _ok(document)
    except Exception as e:
        return _err(f"GFF parse error for {resref}.{restype}: {e}")


def _prune(obj: Any, depth: int) -> Any:
    """Recursively prune deeply nested data to keep output manageable."""
    if depth <= 0:
        return "<truncated>"
    if isinstance(obj, dict):
        return {k: _prune(v, depth - 1) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) > 20:
            return [_prune(v, depth - 1) for v in obj[:20]] + [f"... ({len(obj) - 20} more)"]
        return [_prune(v, depth - 1) for v in obj]
    return obj


async def _read_dlg(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readDLG: {e}")
    resref = (args.get("resref") or "").lower()
    if not resref:
        return _err("readDLG: 'resref' is required.")
    include_branches = bool(args.get("includeBranches", True))

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.dlg")
    if data is None:
        return _err(f"DLG not found: {resref} in {game_id}")

    try:
        from ghostscripter.core.services import DialogueService
        dlg = DialogueService.parse_bytes(data)
        result = DialogueService.to_dict(dlg, include_branches=include_branches)
        result["resref"] = resref
        result["game"] = game_id
        return _ok(result)
    except Exception as e:
        return _err(f"DLG parse error for {resref}: {e}")


async def _read_twoda(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readTwoDA: {e}")
    resref = (args.get("resref") or "").lower()
    if not resref:
        return _err("readTwoDA: 'resref' is required (e.g. 'appearance', 'baseitems').")
    columns_filter = args.get("columns", [])
    row_query = args.get("rowQuery", "").lower()
    limit = int(args.get("limit", 100))
    offset = int(args.get("offset", 0))

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.2da")
    if data is None:
        return _err(f"2DA not found: {resref} in {game_id}")

    try:
        from ghostscripter.core.services import TwoDAService
        tda = TwoDAService.parse_bytes(data, resref)

        # Apply column filter
        cols = columns_filter if columns_filter else tda.columns
        cols = [c for c in cols if c in tda.columns]

        rows = tda.rows
        if row_query:
            rows = [r for r in rows if any(
                row_query in str(v).lower() for v in r.data.values()
            )]

        total = len(rows)
        rows = rows[offset: offset + limit]

        result_rows = []
        for r in rows:
            row_data = {"__label": r.label}
            for c in cols:
                row_data[c] = r.data.get(c, "****")
            result_rows.append(row_data)

        return _ok({
            "resref": resref,
            "columns": cols,
            "total_rows": total,
            "offset": offset,
            "returned": len(result_rows),
            "rows": result_rows,
        })
    except Exception as e:
        return _err(f"2DA parse error for {resref}: {e}")


async def _read_tlk(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readTLK: {e}")
    strrefs = [int(s) for s in args.get("strrefs", [])]

    rm = _load_rm(game_id)
    data = rm.read("dialog.tlk")
    if data is None:
        return _err(f"dialog.tlk not found in {game_id} installation.")

    try:
        from ghostscripter.core.services import TLKService
        tlk = TLKService.parse_bytes(data, "dialog.tlk")
        results = TLKService.lookup(tlk, strrefs)
        return _ok({"game": game_id, "entries": results})
    except Exception as e:
        return _err(f"TLK error: {e}")


async def _read_journal(args: dict) -> List[types.TextContent]:
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readJournal: {e}")
    category_filter = args.get("categoryFilter", "").lower()

    rm = _load_rm(game_id)
    data = rm.read("global.jrl")
    if data is None:
        return _err(f"global.jrl not found in {game_id} installation.")

    try:
        from ghostscripter.core.services import JournalService
        jrl = JournalService.parse_bytes(data)
        journal_dict = JournalService.to_dict(jrl, category_filter=category_filter)
        return _ok({"game": game_id, **journal_dict})
    except Exception as e:
        return _err(f"Journal parse error: {e}")


async def _search_nwscript(args: dict) -> List[types.TextContent]:
    game_id = _normalize_game(args.get("game", "K1"))
    query = args.get("query", "").strip()
    kind = args.get("kind", "functions").lower()
    category_filter = args.get("category", "").strip()
    limit = min(int(args.get("limit", 20)), 100)

    from ghostscripter.core.services import NWScriptService
    db = NWScriptService.load(game_id)
    results = NWScriptService.search(
        db, query, kind=kind, category_filter=category_filter, limit=limit
    )
    return _ok({
        "game": game_id,
        "query": query,
        "count": len(results),
        "results": results,
    })


async def _nwscript_signature(args: dict) -> List[types.TextContent]:
    game_id = _normalize_game(args.get("game", "K1"))
    func_name = args.get("functionName") or args.get("function_name")
    if not func_name:
        return _err("nwscriptSignature: 'functionName' is required.")

    from ghostscripter.core.services import NWScriptService
    db = NWScriptService.load(game_id)
    sig = NWScriptService.signature(db, func_name)
    if sig is None:
        return _err(f"Function not found: {func_name!r} in {game_id} NWScript database.")
    return _ok(sig)



async def _read_pth(args: dict) -> List[types.TextContent]:
    """Read a KotOR PTH (pathfinding) GFF and return the node graph.

    PTH files define the NPC pathfinding graph for an area. Each point has an
    X/Y position plus a list of connected point indices (directed edges).

    Format reference (PyKotor pth.py):
        Path_Points list — each struct:
            X (float), Y (float)
            Conections (DWORD) — edge count from this node
            First_Conection (DWORD) — index into Path_Conections for first edge
        Path_Conections list — each struct:
            Destination (DWORD) — target point index

    Args:
        game   (str): "K1" or "K2"
        resref (str): area resref (same as .are/.git/.lyt), e.g. "danm13"

    Returns:
        point_count (int), connection_count (int),
        points (list of {x, y, connections: [int, ...]})
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readPTH: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "readPTH")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.pth")
    if data is None:
        return _err(f"readPTH: '{resref}.pth' not found in {game_id} installation.")

    try:
        from ghostscripter.core.services import GFFService
        raw = GFFService.parse_bytes(data)
        fields = raw if isinstance(raw, dict) else (raw.get("fields") or raw)

        # Read flat connections list
        conn_list = fields.get("Path_Conections", [])
        if not isinstance(conn_list, list):
            conn_list = []
        flat_connections: list[int] = []
        for c in conn_list:
            sub = c.get("fields") or c if isinstance(c, dict) else {}
            dest = sub.get("Destination")
            flat_connections.append(int(dest) if dest is not None else -1)

        # Read points
        point_list = fields.get("Path_Points", [])
        if not isinstance(point_list, list):
            point_list = []
        points = []
        for p in point_list:
            sub = p.get("fields") or p if isinstance(p, dict) else {}
            x = _safe_float(sub.get("X"))
            y = _safe_float(sub.get("Y"))
            count = int(sub.get("Conections", 0) or 0)
            first = int(sub.get("First_Conection", 0) or 0)
            # Slice the relevant connections
            conns = flat_connections[first: first + count]
            points.append({"x": x, "y": y, "connections": conns})

        return _ok({
            "game":             game_id,
            "resref":           resref,
            "point_count":      len(points),
            "connection_count": len(flat_connections),
            "points":           points,
        })
    except Exception as exc:
        return _err(f"readPTH: parse error — {exc}")


async def _read_ltr(args: dict) -> List[types.TextContent]:
    """Decode a KotOR LTR (Letter/Name Generator) binary and return summary stats.

    LTR files contain 3rd-order Markov chain probability tables used by the
    character-creation name generator. The binary stores float32 probabilities
    for 28 characters at three positions (start, middle, end) for single,
    double, and triple character contexts.

    Format reference (PyKotor ltr_data.py):
        Header   : 8 bytes ("LTR V1.0")
        LetterCnt: 1 byte uint8 (typically 28)
        Single   : LetterCnt * 3 * 4 bytes (float32[start, middle, end])
        Double   : LetterCnt^2 * 3 * 4 bytes
        Triple   : LetterCnt^3 * 3 * 4 bytes  (~258 KB for 28 chars)

    Args:
        game   (str): "K1" or "K2"
        resref (str): LTR resref, e.g. "humanm", "humanf", "alien"

    Returns:
        resref, letter_count, file_size_bytes,
        top_start_letters (top-5 most probable first letters),
        top_end_letters   (top-5 most probable ending letters)
    """
    import struct

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readLTR: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "readLTR")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.ltr")
    if data is None:
        return _err(f"readLTR: '{resref}.ltr' not found in {game_id} installation.")

    try:
        if len(data) < 9 or data[:4] != b"LTR ":
            return _err(f"readLTR: '{resref}.ltr' is not a valid LTR file (bad magic).")
        if data[4:8] != b"V1.0":
            return _err(f"readLTR: unsupported LTR version {data[4:8]!r} (expected V1.0).")

        letter_count = data[8]  # uint8
        # Single-letter probabilities: letter_count * 3 floats
        offset = 9
        n = letter_count
        single_size = n * 3 * 4
        if len(data) < offset + single_size:
            return _err(f"readLTR: file too short for single-letter tables.")

        # Start probabilities (first n floats)
        starts = struct.unpack_from(f"<{n}f", data, offset)
        ends   = struct.unpack_from(f"<{n}f", data, offset + n * 4 * 2)

        # Build alphabet for the 28 chars (a-z + space-like chars)
        ALPHA = "abcdefghijklmnopqrstuvwxyz  "

        def _top5(probs, alpha):
            indexed = sorted(enumerate(probs), key=lambda x: -x[1])[:5]
            return [{"char": alpha[i] if i < len(alpha) else f"[{i}]",
                     "prob": round(p, 4)} for i, p in indexed if p > 0]

        return _ok({
            "game":             game_id,
            "resref":           resref,
            "letter_count":     letter_count,
            "file_size_bytes":  len(data),
            "top_start_letters": _top5(starts, ALPHA),
            "top_end_letters":   _top5(ends,   ALPHA),
        })
    except Exception as exc:
        return _err(f"readLTR: parse error — {exc}")


async def _read_gui(args: dict) -> List[types.TextContent]:
    """Read a KotOR GUI (GFF-based UI definition) file and return its control tree.

    GUI files define the KotOR 2D interface: panels, buttons, labels, list boxes,
    sliders, checkboxes, and scroll bars. Each control has a type (GUIControlType
    0-11), position, extent, border, text, fill style, and optional proto/list items.

    GUI format reference (PyKotor gui.py):
        GUIControlType: Invalid(-1), Control(0), Panel(2), ProtoItem(4), Label(5),
                        Button(6), CheckBox(7), Slider(8), ScrollBar(9),
                        Progress(10), ListBox(11)
        GUIAlignment:   TopLeft(1)..BottomRight(35)

    Args:
        game   (str): "K1" or "K2"
        resref (str): GUI file resref without extension (e.g. "mainmenu16x12")

    Returns:
        resref, control_count, root_type, root_tag, controls (list of
        {tag, type_id, type_name, x, y, width, height, text_label})
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readGUI: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "readGUI")
    if err:
        return _err(err)

    rm = _load_rm(game_id)
    data = rm.read(f"{resref}.gui")
    if data is None:
        return _err(f"readGUI: '{resref}.gui' not found in {game_id} installation.")

    # GUIControlType enum mapping
    _CTRL_TYPE: dict[int, str] = {
        -1: "Invalid", 0: "Control", 2: "Panel", 4: "ProtoItem",
        5: "Label", 6: "Button", 7: "CheckBox", 8: "Slider",
        9: "ScrollBar", 10: "Progress", 11: "ListBox",
    }

    try:
        from ghostscripter.core.services import GFFService
        gui = GFFService.parse_bytes(data)
        root = gui if isinstance(gui, dict) else (gui.get("fields") or gui)

        def _extract_ctrl(node: dict) -> dict:
            f = node.get("fields") or node
            type_id = f.get("CONTROLTYPE", f.get("CONTROL_TYPE", f.get("Obj_Type")))
            extent = f.get("EXTENT") or {}
            if isinstance(extent, dict):
                ef = extent.get("fields") or extent
            else:
                ef = {}
            text_node = f.get("TEXT") or {}
            if isinstance(text_node, dict):
                tf = text_node.get("fields") or text_node
            else:
                tf = {}
            return {
                "tag":        f.get("TAG", ""),
                "type_id":    type_id,
                "type_name":  _CTRL_TYPE.get(int(type_id or 0), "Unknown"),
                "x":          ef.get("LEFT"),
                "y":          ef.get("TOP"),
                "width":      ef.get("WIDTH"),
                "height":     ef.get("HEIGHT"),
                "text_label": tf.get("TEXT", ""),
            }

        controls_raw = root.get("CONTROLS", root.get("Controls", []))
        if not isinstance(controls_raw, list):
            controls_raw = []
        controls = [_extract_ctrl(c) for c in controls_raw if isinstance(c, dict)]

        return _ok({
            "game":          game_id,
            "resref":        resref,
            "control_count": len(controls),
            "root_type":     root.get("CONTROLTYPE"),
            "root_tag":      root.get("TAG", ""),
            "controls":      controls,
        })
    except Exception as exc:
        return _err(f"readGUI: parse error — {exc}")


async def _read_save(args: dict) -> List[types.TextContent]:
    """Read real data from a KotOR save-game folder.

    The four core components are parsed independently so a damaged or partial
    save still produces an honest report.  A missing field/component is
    represented by ``None`` and described by ``completeness``; genuine zeroes,
    false flags, empty strings, and empty lists are preserved as-is.
    """

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"readSave: {e}")

    raw_save_path = str(args.get("save_path") or "").strip()
    if not raw_save_path:
        return _err("readSave: 'save_path' is required.")

    save_path = Path(raw_save_path).expanduser()
    if not save_path.is_absolute():
        # Slot names are resolved below the loaded/detected installation.  The
        # ResourceManager stores this as _game_dir (not the obsolete _path).
        try:
            rm = _load_rm(game_id)
        except (FileNotFoundError, OSError) as exc:
            return _err(
                f"readSave: relative slot '{raw_save_path}' could not be resolved: {exc}"
            )
        install_root = getattr(rm, "_game_dir", None)
        if install_root is None:
            return _err(
                f"readSave: relative slot '{raw_save_path}' could not be resolved because "
                f"the {game_id} installation path is unavailable."
            )
        save_path = Path(install_root) / "saves" / save_path

    if not save_path.is_dir():
        return _err(f"readSave: save folder '{save_path}' does not exist.")

    save_path = save_path.resolve()
    files = {
        child.name.casefold(): child
        for child in save_path.iterdir()
        if child.is_file()
    }
    expected = {
        "save_info": "savenfo.res",
        "party_table": "partytable.res",
        "global_vars": "globalvars.res",
        "save_archive": "savegame.sav",
    }
    component_paths = {
        component: files.get(filename.casefold())
        for component, filename in expected.items()
    }
    if not any(component_paths.values()):
        return _err(
            f"readSave: '{save_path}' contains none of the four KotOR save components "
            "(savenfo.res, partytable.res, globalvars.res, savegame.sav)."
        )

    try:
        from pykotor.extract.capsule import Capsule
        from pykotor.extract.savedata import GlobalVars, PartyTable, SaveInfo
        from pykotor.resource.formats.gff import read_gff
        from pykotor.resource.type import ResourceType
    except (ImportError, ModuleNotFoundError) as exc:
        return _err(f"readSave: PyKotor save support is unavailable: {exc}")

    loaded: list[str] = []
    missing = [name for name, path in component_paths.items() if path is None]
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    # Values intentionally start at None.  That is materially different from
    # a parsed empty string/list or zero and prevents partial saves from being
    # reported as if they contained data they do not have.
    save_name: str | None = None
    last_module: str | None = None
    area_name: str | None = None
    time_played_secs: int | None = None
    timestamp: int | None = None
    cheat_used: bool | None = None
    pc_name: str | None = None
    gameplay_hint: int | None = None
    story_hint: int | None = None
    portraits: list[dict[str, Any]] | None = None

    party_members: list[dict[str, Any]] | None = None
    party: dict[str, Any] | None = None
    globals_summary: dict[str, Any] | None = None
    global_count: int | None = None
    module_snapshots: list[str] | None = None
    nested_resource_count: int | None = None
    nested_resource_types: dict[str, int] | None = None
    character_resources: list[str] | None = None

    nfo_path = component_paths["save_info"]
    if nfo_path is not None:
        try:
            info = SaveInfo(save_path)
            info.load()
            root = read_gff(nfo_path).root

            def _info_value(label: str, attr: str) -> Any:
                return getattr(info, attr) if root.exists(label) else None

            save_name = _info_value("SAVEGAMENAME", "savegame_name")
            last_module = _info_value("LASTMODULE", "last_module")
            area_name = _info_value("AREANAME", "area_name")
            time_played_secs = _info_value("TIMEPLAYED", "time_played")
            timestamp = _info_value("TIMESTAMP", "timestamp")
            cheat_used = _info_value("CHEATUSED", "cheat_used")
            pc_name = _info_value("PCNAME", "pc_name")
            gameplay_hint = _info_value("GAMEPLAYHINT", "gameplay_hint")
            story_hint = _info_value("STORYHINT", "story_hint")
            portrait_attrs = ("portrait0", "portrait1", "portrait2")
            portraits = [
                {"slot": slot, "resref": str(getattr(info, attr))}
                for slot, attr in enumerate(portrait_attrs)
                if root.exists(f"PORTRAIT{slot}")
            ]
            loaded.append("save_info")
        except Exception as exc:
            errors.append({"component": "save_info", "error": f"{type(exc).__name__}: {exc}"})

    party_path = component_paths["party_table"]
    if party_path is not None:
        try:
            table = PartyTable(save_path)
            table.load()
            root = read_gff(party_path).root

            if root.exists("PT_MEMBERS"):
                party_members = [
                    {"index": member.index, "is_leader": member.is_leader}
                    for member in table.pt_members
                ]
            else:
                warnings.append({
                    "component": "party_table",
                    "warning": "PT_MEMBERS is absent; party membership is unavailable.",
                })

            available_npcs = None
            if root.exists("PT_AVAIL_NPCS"):
                available_npcs = [
                    {
                        "index": index,
                        "available": npc.npc_available,
                        "selected": npc.npc_selected,
                    }
                    for index, npc in enumerate(table.pt_avail_npcs)
                ]

            # Retail files use the 16-character PT_CONTROLLED_NP label.  Some
            # older libraries looked for the impossible 17-character
            # PT_CONTROLLED_NPC spelling, so read the retail field directly.
            controlled_npc = (
                root.acquire("PT_CONTROLLED_NP", None)
                if root.exists("PT_CONTROLLED_NP")
                else (
                    root.acquire("PT_CONTROLLED_NPC", None)
                    if root.exists("PT_CONTROLLED_NPC")
                    else None
                )
            )
            party = {
                "member_count": len(party_members) if party_members is not None else None,
                "declared_member_count": (
                    root.acquire("PT_NUM_MEMBERS", None)
                    if root.exists("PT_NUM_MEMBERS")
                    else None
                ),
                "controlled_npc_index": controlled_npc,
                "available_npcs": available_npcs,
                "gold": table.pt_gold if root.exists("PT_GOLD") else None,
                "xp_pool": table.pt_xp_pool if root.exists("PT_XP_POOL") else None,
                "played_seconds": (
                    table.time_played if root.exists("PT_PLAYEDSECONDS") else None
                ),
                "solo_mode": table.pt_solomode if root.exists("PT_SOLOMODE") else None,
                "cheat_used": (
                    table.pt_cheat_used if root.exists("PT_CHEAT_USED") else None
                ),
                "components": (
                    table.pt_item_componen if root.exists("PT_ITEM_COMPONEN") else None
                ),
                "chemicals": (
                    table.pt_item_chemical if root.exists("PT_ITEM_CHEMICAL") else None
                ),
                "influence": (
                    list(table.pt_influence) if root.exists("PT_INFLUENCE") else None
                ),
                "journal_entry_count": (
                    len(table.jnl_entries) if root.exists("JNL_Entries") else None
                ),
            }
            loaded.append("party_table")
        except Exception as exc:
            errors.append({"component": "party_table", "error": f"{type(exc).__name__}: {exc}"})

    globals_path = component_paths["global_vars"]
    if globals_path is not None:
        try:
            save_globals = GlobalVars(save_path)
            save_globals.load()
            root = read_gff(globals_path).root
            category_fields = {
                "booleans": ("CatBoolean", "ValBoolean", save_globals.global_bools),
                "numbers": ("CatNumber", "ValNumber", save_globals.global_numbers),
                "strings": ("CatString", "ValString", save_globals.global_strings),
                "locations": ("CatLocation", "ValLocation", save_globals.global_locs),
            }
            counts: dict[str, int | None] = {}
            for category, (names_field, values_field, values) in category_fields.items():
                if root.exists(names_field) and root.exists(values_field):
                    counts[category] = len(values)
                else:
                    counts[category] = None
                    warnings.append({
                        "component": "global_vars",
                        "warning": (
                            f"{category} are unavailable because {names_field} or "
                            f"{values_field} is absent."
                        ),
                    })
            known_counts = [count for count in counts.values() if count is not None]
            global_count = sum(known_counts) if len(known_counts) == len(counts) else None
            globals_summary = {"counts": counts, "total_count": global_count}
            loaded.append("global_vars")
        except Exception as exc:
            errors.append({"component": "global_vars", "error": f"{type(exc).__name__}: {exc}"})

    archive_path = component_paths["save_archive"]
    if archive_path is not None:
        try:
            resources = Capsule(archive_path).resources()
            module_snapshots = []
            character_resources = []
            nested_resource_types = {}
            for resource in resources:
                restype = resource.restype()
                extension = restype.extension.lower()
                nested_resource_types[extension] = nested_resource_types.get(extension, 0) + 1
                if restype == ResourceType.SAV:
                    module_snapshots.append(resource.resname())
                elif restype == ResourceType.UTC and (
                    resource.resname().casefold() == "pc"
                    or resource.resname().casefold().startswith("availnpc")
                ):
                    character_resources.append(f"{resource.resname()}.{extension}")
            nested_resource_count = len(resources)
            loaded.append("save_archive")
        except Exception as exc:
            errors.append({"component": "save_archive", "error": f"{type(exc).__name__}: {exc}"})

    # A component that exists but did not parse is neither loaded nor missing;
    # its exact failure is retained in errors.
    status = "complete" if len(loaded) == len(expected) and not warnings else "partial"
    return _ok({
        "game": game_id,
        "save_path": str(save_path),
        "save_name": save_name,
        "last_module": last_module,
        "area_name": area_name,
        "time_played_secs": time_played_secs,
        "timestamp": timestamp,
        "cheat_used": cheat_used,
        "pc_name": pc_name,
        "gameplay_hint": gameplay_hint,
        "story_hint": story_hint,
        "portraits": portraits,
        "party_members": party_members,
        "party": party,
        "global_count": global_count,
        "globals": globals_summary,
        "module_snapshots": module_snapshots,
        "nested_resource_count": nested_resource_count,
        "nested_resource_types": nested_resource_types,
        "character_resources": character_resources,
        "completeness": {
            "status": status,
            "loaded_components": loaded,
            "missing_components": missing,
            "errors": errors,
            "warnings": warnings,
        },
    })


# ─────────────────────────────────────────────
# v3.3 NEW TOOLS
# ─────────────────────────────────────────────

async def _read_ncs(args: dict) -> List[types.TextContent]:
    """Disassemble a KotOR NCS (compiled NWScript) binary.

    NCS files begin with an 8-byte header ("NCS V1.0") followed by a magic
    byte (0x42) and a 4-byte script size.  The body is a stream of instructions;
    each instruction has a 1-byte opcode, a 1-byte type qualifier, and
    variable-length arguments.

    Returns instruction_count, byte_size, header info, and a listing of up to
    the first 256 instructions (opcode_hex, qualifier_hex, mnemonic, args_hex).
    """
    try:
        import struct
        game_id = _normalize_game(args.get("game", "K1"))
        resref  = (args.get("resref") or "").strip().lower()
        if not resref:
            return _err("readNCS: 'resref' is required")
        try:
            rm = _load_rm(game_id)
        except FileNotFoundError:
            return _err("readNCS: installation not loaded — call gsLoadInstallation first")

        ncs_data = rm.read(f"{resref}.ncs")
        if ncs_data is None:
            return _err(f"readNCS: '{resref}.ncs' not found in {game_id} installation")

        if len(ncs_data) < 9:
            return _err(f"readNCS: file too short ({len(ncs_data)} bytes) — not a valid NCS")

        file_type    = ncs_data[0:4].decode("ascii", errors="replace")
        file_version = ncs_data[4:8].decode("ascii", errors="replace")
        magic_byte   = ncs_data[8]

        if file_type != "NCS ":
            return _err(f"readNCS: invalid file type '{file_type}' — expected 'NCS '")
        if file_version != "V1.0":
            return _err(f"readNCS: unsupported version '{file_version}'")

        # ── Opportunistic PyKotor delegation ──────────────────────────────────
        # When pykotor is installed, use its NCS reader for richer output
        # (full opcode coverage, string constants decoded, etc.).
        # Fall through to the internal disassembler when unavailable.
        try:
            from pykotor.resource.formats.ncs import read_ncs  # type: ignore
            from pykotor.resource.formats.ncs.ncs_data import NCS  # type: ignore
            ncs_obj: NCS = read_ncs(ncs_data)
            instructions_out = []
            for i, instr in enumerate(ncs_obj.instructions):
                encoded = instr.ins_type.value
                opcode = int(encoded.byte_code)
                qualifier = int(encoded.qualifier)
                start = int(getattr(instr, "offset", 13))
                end = (
                    int(getattr(ncs_obj.instructions[i + 1], "offset", len(ncs_data)))
                    if i + 1 < len(ncs_obj.instructions) else len(ncs_data)
                )
                jump_target = (
                    getattr(instr.jump, "offset", None)
                    if getattr(instr, "jump", None) is not None else None
                )
                instructions_out.append({
                    "offset":    f"{getattr(instr, 'offset', i * 2):#06x}",
                    "opcode":    f"{opcode:#04x}",
                    "qualifier": f"{qualifier:#04x}",
                    "mnemonic":  "CONSTx" if opcode == 0x04 else instr.ins_type.name,
                    "instruction_type": instr.ins_type.name,
                    "args":      [str(a) for a in getattr(instr, "args", [])],
                    "args_hex":  ncs_data[start + 2:end].hex(),
                    "jump_target": jump_target,
                })
            return _ok({
                "game":              game_id,
                "resref":            resref,
                "file_type":         file_type,
                "file_version":      file_version,
                "magic_byte":        f"{magic_byte:#04x}",
                "script_size_bytes": len(ncs_data),
                "byte_size":         len(ncs_data),
                "instruction_count": len(instructions_out),
                "truncated":         False,
                "instructions":      instructions_out,
                "parse_errors":      [],
                "pykotor_used":      True,
            })
        except ImportError:
            pass  # pykotor not installed — fall through to internal disassembler
        except Exception as _pk_err:
            log.debug("readNCS: pykotor delegation failed (%s), using internal disassembler", _pk_err)
        # ─────────────────────────────────────────────────────────────────────

        # Script size field lives at offset 9 (4 bytes BE in some variants — we read it
        # but don't rely on it, since the actual body follows immediately after byte 8).
        script_size_bytes = ncs_data[9:13] if len(ncs_data) >= 13 else b""
        script_size = struct.unpack(">I", script_size_bytes)[0] if len(script_size_bytes) == 4 else 0

        # Opcode mnemonic table (NWSByteCode enum subset — most common opcodes)
        MNEMONICS = {
            0x01: "CPDOWNSP", 0x02: "RSADDx",  0x03: "CPTOPSP",
            0x04: "CONSTx",   0x05: "ACTION",   0x06: "LOGANDxx",
            0x07: "LOGORxx",  0x08: "INCORxx",  0x09: "EXCORxx",
            0x0A: "BOOLANDxx",0x0B: "EQUALxx",  0x0C: "NEQUALxx",
            0x0D: "GEQxx",    0x0E: "GTxx",     0x0F: "LTxx",
            0x10: "LEQxx",    0x11: "SHLEFTxx", 0x12: "SHRIGHTxx",
            0x13: "USHRIGHTxx",0x14:"ADDxx",    0x15: "SUBxx",
            0x16: "MULxx",    0x17: "DIVxx",    0x18: "MODxx",
            0x19: "NEGx",     0x1A: "COMPx",    0x1B: "MOVSP",
            0x1D: "JMP",      0x1E: "JSR",      0x1F: "JZ",
            0x20: "RETN",     0x21: "DESTRUCT", 0x22: "NOTx",
            0x23: "DECxSP",   0x24: "INCxSP",   0x25: "JNZ",
            0x26: "CPDOWNBP", 0x27: "CPTOPBP",  0x28: "DECIBP",
            0x29: "INCIBP",   0x2A: "SAVEBP",   0x2B: "RESTOREBP",
            0x2C: "STORE_STATE",0x2D:"NOP",
        }
        # Arg sizes per opcode (bytes after the 2-byte opcode+qualifier prefix)
        # Sourced from PyKotor ncs_data.py and xoreos-tools ncsdis.cpp.
        # Key: all two-operand stack ops (CPDOWNSP, CPTOPSP, CPDOWNBP, CPTOPBP)
        # take 4+2=6 bytes (int32 offset + uint16 size).  One-operand stack ops
        # (DECxSP, INCxSP, DECIBP, INCIBP) take 4 bytes.
        # Jump/JSR/JZ/JNZ take a 4-byte signed offset.
        # MOVSP takes a 4-byte signed offset.
        # ACTION takes 2 bytes (routine ID) + 1 byte (arg count) = 3.
        # DESTRUCT takes 2+2+2 = 6 bytes (size, offset, dont-destroy-size).
        # STORE_STATE takes 4+4 = 8 bytes (base-pointer, stack-pointer).
        # CONSTx arg size depends on qualifier (handled below).
        # All arithmetic/logic/compare ops (RSADDx, LOGANDxx ... MODxx,
        # NEGx, COMPx, NOTx, EQUALxx, NEQUALxx, GEQxx, GTxx, LTxx, LEQxx,
        # SHLEFTxx, SHRIGHTxx, USHRIGHTxx) have 0 extra args.
        ARG_SIZES = {
            0x01: 6,   # CPDOWNSP  — stack_offset(4) + size(2)
            0x02: 0,   # RSADDx    — no args
            0x03: 6,   # CPTOPSP   — stack_offset(4) + size(2)
            0x04: 4,   # CONSTx    — overridden below by qualifier
            0x05: 3,   # ACTION    — routine_id(2) + arg_count(1)
            0x06: 0,   # LOGANDxx
            0x07: 0,   # LOGORxx
            0x08: 0,   # INCORxx
            0x09: 0,   # EXCORxx
            0x0A: 0,   # BOOLANDxx
            0x0B: 0,   # EQUALxx
            0x0C: 0,   # NEQUALxx
            0x0D: 0,   # GEQxx
            0x0E: 0,   # GTxx
            0x0F: 0,   # LTxx
            0x10: 0,   # LEQxx
            0x11: 0,   # SHLEFTxx
            0x12: 0,   # SHRIGHTxx
            0x13: 0,   # USHRIGHTxx
            0x14: 0,   # ADDxx
            0x15: 0,   # SUBxx
            0x16: 0,   # MULxx
            0x17: 0,   # DIVxx
            0x18: 0,   # MODxx
            0x19: 0,   # NEGx
            0x1A: 0,   # COMPx
            0x1B: 4,   # MOVSP     — stack_offset(4) signed
            0x1D: 4,   # JMP       — jump_offset(4) signed
            0x1E: 4,   # JSR       — jump_offset(4) signed
            0x1F: 4,   # JZ        — jump_offset(4) signed
            0x20: 0,   # RETN
            0x21: 6,   # DESTRUCT  — size(2) + offset(2) + dont_destroy_size(2)
            0x22: 0,   # NOTx
            0x23: 4,   # DECxSP    — stack_offset(4) signed
            0x24: 4,   # INCxSP    — stack_offset(4) signed
            0x25: 4,   # JNZ       — jump_offset(4) signed
            0x26: 6,   # CPDOWNBP  — stack_offset(4) + size(2)
            0x27: 6,   # CPTOPBP   — stack_offset(4) + size(2)
            0x28: 4,   # DECIBP    — stack_offset(4) signed
            0x29: 4,   # INCIBP    — stack_offset(4) signed
            0x2A: 0,   # SAVEBP
            0x2B: 0,   # RESTOREBP
            0x2C: 8,   # STORE_STATE — base_ptr(4) + stack_ptr(4)
            0x2D: 0,   # NOP
        }

        instructions = []
        pos = 13  # after header (8) + magic (1) + size (4)
        MAX_INSTR = 256
        parse_errors = []

        while pos < len(ncs_data) and len(instructions) < MAX_INSTR:
            if pos + 2 > len(ncs_data):
                break
            opcode    = ncs_data[pos]
            qualifier = ncs_data[pos + 1]
            mnemonic  = MNEMONICS.get(opcode, f"UNK_{opcode:02X}")
            arg_size  = ARG_SIZES.get(opcode, 0)
            # For CONSTx the argument size depends on qualifier
            if opcode == 0x04:  # CONSTx
                # qualifier: 03=int(4), 04=float(4), 05=string(2+n), 06=object(4)
                if qualifier == 0x03:
                    arg_size = 4
                elif qualifier == 0x04:
                    arg_size = 4
                elif qualifier == 0x05:
                    # 2-byte length prefix then string data
                    if pos + 4 <= len(ncs_data):
                        str_len = struct.unpack(">H", ncs_data[pos+2:pos+4])[0]
                        arg_size = 2 + str_len
                    else:
                        arg_size = 0
                elif qualifier == 0x06:
                    arg_size = 4
                else:
                    arg_size = 4
            end = pos + 2 + arg_size
            if end > len(ncs_data):
                parse_errors.append(f"truncated at offset {pos:#06x}")
                break
            args_hex = ncs_data[pos+2:end].hex() if arg_size > 0 else ""
            instructions.append({
                "offset":    f"{pos:#06x}",
                "opcode":    f"{opcode:#04x}",
                "qualifier": f"{qualifier:#04x}",
                "mnemonic":  mnemonic,
                "args_hex":  args_hex,
            })
            pos = end

        return _ok({
            "game":              game_id,
            "resref":            resref,
            "file_type":         file_type,
            "file_version":      file_version,
            "magic_byte":        f"{magic_byte:#04x}",
            "script_size_bytes": script_size,
            "byte_size":         len(ncs_data),
            "instruction_count": len(instructions),
            "truncated":         len(instructions) >= MAX_INSTR,
            "instructions":      instructions,
            "parse_errors":      parse_errors,
        })
    except Exception as exc:
        return _err(f"readNCS: {exc}")


async def _read_vis(args: dict) -> List[types.TextContent]:
    """Read a KotOR VIS (visibility/occlusion) ASCII file.

    VIS files define which rooms are visible from each room, used for
    occlusion-culling optimization.  Format: parent room line followed
    by indented child room names (2-space indent).

    Returns room_count and a dict mapping each parent room to the list
    of rooms visible from it.
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
        resref  = (args.get("resref") or "").strip().lower()
        if not resref:
            return _err("readVIS: 'resref' is required")
        try:
            rm = _load_rm(game_id)
        except FileNotFoundError:
            return _err("readVIS: installation not loaded — call gsLoadInstallation first")

        vis_data = rm.read(f"{resref}.vis")
        if vis_data is None:
            return _err(f"readVIS: '{resref}.vis' not found in {game_id} installation")

        # Parse ASCII VIS format
        visibility: dict = {}
        current_parent: str | None = None

        for raw_line in vis_data.decode("ascii", errors="replace").splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            if line.startswith("  "):
                # Child room line (2-space indent)
                child = line.strip().lower()
                if child and current_parent is not None:
                    visibility.setdefault(current_parent, []).append(child)
            else:
                # Parent room line: "room_name [child_count]"
                parts = line.split()
                if parts:
                    current_parent = parts[0].lower()
                    if current_parent not in visibility:
                        visibility[current_parent] = []

        return _ok({
            "game":       game_id,
            "resref":     resref,
            "room_count": len(visibility),
            "rooms":      visibility,
        })
    except Exception as exc:
        return _err(f"readVIS: {exc}")


async def _read_ifo(args: dict) -> List[types.TextContent]:
    """Read a KotOR IFO (module info GFF) file.

    IFO files store module metadata: entry point, area list, all Mod_On*
    script hooks (13 hooks: heartbeat, load, start, enter, leave,
    activate_item, acquire_item, unacquire_item, player_death, player_dying,
    player_levelup, player_respawn, player_rest, user_defined).

    Returns comprehensive module info in a structured JSON object.
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
        resref  = (args.get("resref") or args.get("module") or "").strip().lower()
        if not resref:
            return _err("readIFO: 'resref' (module name without extension) is required")
        try:
            rm = _load_rm(game_id)
        except FileNotFoundError:
            return _err("readIFO: installation not loaded — call gsLoadInstallation first")

        ifo_data = read_module_resource(rm, resref, "module.ifo")
        if ifo_data is None:
            return _err(
                f"readIFO: 'module.ifo' not found inside module '{resref}' "
                f"in the {game_id} installation"
            )

        # ── Opportunistic PyKotor delegation ──────────────────────────────────
        # pykotor.resource.generics.ifo provides a typed IFO dataclass that
        # correctly handles all field aliases between K1 and K2.  When
        # available, we use it for full field coverage; otherwise we fall
        # through to the GFFService-based reader below.
        try:
            from pykotor.resource.formats.gff import read_gff  # type: ignore
            from pykotor.resource.generics.ifo import IFO, construct_ifo  # type: ignore
            gff_obj  = read_gff(ifo_data)
            ifo_obj: IFO = construct_ifo(gff_obj)

            # Map PyKotor IFO fields to our output schema
            entry_pos = getattr(ifo_obj, "entry_position", None)
            ex = float(entry_pos.x) if entry_pos else 0.0
            ey = float(entry_pos.y) if entry_pos else 0.0
            ez = float(entry_pos.z) if entry_pos else 0.0

            # Script hooks: PyKotor IFO uses on_xxx attributes
            scripts_map = {}
            for attr, key in (
                ("on_heartbeat",      "on_heartbeat"),
                ("on_load",           "on_load"),
                ("on_start",          "on_start"),
                ("on_enter",          "on_enter"),
                ("on_leave",          "on_leave"),
                ("on_activate_item",  "on_activate_item"),
                ("on_acquire_item",   "on_acquire_item"),
                ("on_unacquire_item", "on_unacquire_item"),
                ("on_player_death",   "on_player_death"),
                ("on_player_dying",   "on_player_dying"),
                ("on_player_levelup", "on_player_levelup"),
                ("on_player_respawn", "on_player_respawn"),
                ("on_player_rest",    "on_player_rest"),
                ("on_user_defined",   "on_user_defined"),
            ):
                val = getattr(ifo_obj, attr, None)
                if val:
                    scripts_map[key] = str(val)

            area_list = [str(a) for a in getattr(ifo_obj, "area_list", [])]

            return _ok({
                "game":            game_id,
                "resref":          resref,
                "mod_name":        str(getattr(ifo_obj, "mod_name", "") or ""),
                "mod_description": str(getattr(ifo_obj, "mod_description", "") or ""),
                "tag":             str(getattr(ifo_obj, "tag", "") or ""),
                "entry_area":      str(getattr(ifo_obj, "area_name", "") or ""),
                "entry_x":         ex,
                "entry_y":         ey,
                "entry_z":         ez,
                "entry_dir_x":     0.0,
                "entry_dir_y":     0.0,
                "expansion_id":    int(getattr(ifo_obj, "expansion_id", 0) or 0),
                "is_save_game":    bool(getattr(ifo_obj, "is_save_game", False)),
                "creator_id":      int(getattr(ifo_obj, "creator_id", 0) or 0),
                "version":         int(getattr(ifo_obj, "version", 0) or 0),
                "area_list":       area_list,
                "scripts":         scripts_map,
                "pykotor_used":    True,
            })
        except ImportError:
            pass  # pykotor not installed — fall through to GFFService reader
        except Exception as _pk_err:
            log.debug("readIFO: pykotor delegation failed (%s), using GFFService", _pk_err)
        # ─────────────────────────────────────────────────────────────────────

        from ghostscripter.core.services import GFFService
        gff = GFFService.parse_bytes(ifo_data)
        root = gff if isinstance(gff, dict) else (gff.get("fields") or gff)





        # Area list
        area_list_raw = root.get("Mod_Area_list") or []
        area_list = []
        if isinstance(area_list_raw, list):
            for item in area_list_raw:
                if isinstance(item, dict):
                    name = item.get("Area_Name") or item.get("fields", {}).get("Area_Name") or ""
                    area_list.append(str(name))

        scripts = {
            "on_heartbeat":      gff_resref(root, "Mod_OnHeartbeat"),
            "on_load":           gff_resref(root, "Mod_OnModLoad"),
            "on_start":          gff_resref(root, "Mod_OnModStart"),
            "on_enter":          gff_resref(root, "Mod_OnClientEntr"),
            "on_leave":          gff_resref(root, "Mod_OnClientLeav"),
            "on_activate_item":  gff_resref(root, "Mod_OnActvtItem"),
            "on_acquire_item":   gff_resref(root, "Mod_OnAcquirItem"),
            "on_unacquire_item": gff_resref(root, "Mod_OnUnAqreItem"),
            "on_player_death":   gff_resref(root, "Mod_OnPlrDeath"),
            "on_player_dying":   gff_resref(root, "Mod_OnPlrDying"),
            "on_player_levelup": gff_resref(root, "Mod_OnPlrLvlUp"),
            "on_player_respawn": gff_resref(root, "Mod_OnSpawnBtnDn"),
            "on_player_rest":    gff_resref(root, "Mod_OnPlrRest"),
            "on_user_defined":   gff_resref(root, "Mod_OnUsrDefined"),
        }
        # Remove blank scripts
        scripts = {k: v for k, v in scripts.items() if v}

        return _ok({
            "game":            game_id,
            "resref":          resref,
            "mod_name":        (gff_locstr(root, "Mod_Name", rm=rm) or ""),
            "mod_description": (gff_locstr(root, "Mod_Description", rm=rm) or ""),
            "tag":             gff_resref(root, "Mod_Tag"),
            "entry_area":      gff_resref(root, "Mod_Entry_Area"),
            "entry_x":         gff_float(root, "Mod_Entry_X"),
            "entry_y":         gff_float(root, "Mod_Entry_Y"),
            "entry_z":         gff_float(root, "Mod_Entry_Z"),
            "entry_dir_x":     gff_float(root, "Mod_Entry_Dir_X"),
            "entry_dir_y":     gff_float(root, "Mod_Entry_Dir_Y"),
            "expansion_id":    gff_int(root, "Expansion_Pack"),
            "is_save_game":    bool(gff_int(root, "Mod_IsSaveGame")),
            "creator_id":      gff_int(root, "Mod_Creator_ID"),
            "version":         gff_int(root, "Mod_Version"),
            "area_list":       area_list,
            "scripts":         scripts,
        })
    except Exception as exc:
        return _err(f"readIFO: {exc}")


async def _read_wav(args: dict) -> List[types.TextContent]:
    """Read KotOR audio file metadata.

    KotOR uses WAV/MP3/OGG audio in three wrapping modes:
    - Standard RIFF WAV (magic: 'RIFF')
    - SFX-obfuscated (magic: 0xBFBFBFBF LE)
    - VO-obfuscated (has a special VO header)

    Returns format, sample_rate, channels, bits_per_sample, duration_ms,
    byte_size, and obfuscation_type.  Works without an active installation
    if raw bytes are provided via 'data_b64'; otherwise loads from the
    installation by resref.
    """
    try:
        import struct, base64

        game_id = _normalize_game(args.get("game", "K1"))
        resref  = (args.get("resref") or "").strip().lower()
        data_b64 = (args.get("data_b64") or "").strip()

        if data_b64:
            wav_bytes = base64.b64decode(data_b64, validate=True)
        elif resref:
            try:
                rm = _load_rm(game_id)
            except FileNotFoundError:
                return _err("readWAV: installation not loaded — call gsLoadInstallation first")
            wav_bytes = rm.read(f"{resref}.wav")
            if wav_bytes is None:
                wav_bytes = rm.read(f"{resref}.mp3")
            if wav_bytes is None:
                return _err(f"readWAV: '{resref}.wav/.mp3' not found in {game_id} installation")
        else:
            return _err("readWAV: provide 'resref' or 'data_b64'")

        if len(wav_bytes) < 4:
            return _err("readWAV: file too short")

        magic = wav_bytes[:4]
        SFX_MAGIC_LE  = b"\xbf\xbf\xbf\xbf"
        RIFF_MAGIC    = b"RIFF"
        MP3_SYNC      = b"\xff\xfb"
        OGG_MAGIC     = b"OggS"
        VO_HEADER_SIZE = 8  # known VO obfuscation header

        obfuscation_type = "standard"
        audio_format     = "unknown"
        sample_rate      = None
        channels         = None
        bits_per_sample  = None
        duration_ms      = None

        if magic == RIFF_MAGIC:
            audio_format = "wav"
            obfuscation_type = "riff"
            # Parse WAVE fmt chunk
            if len(wav_bytes) >= 44:
                try:
                    audio_format_code, ch, sr, _, _, bps = struct.unpack_from("<HHIIHH", wav_bytes, 20)
                    channels        = ch
                    sample_rate     = sr
                    bits_per_sample = bps
                    # Look for data chunk to compute duration
                    i = 12
                    while i + 8 <= len(wav_bytes):
                        chunk_id   = wav_bytes[i:i+4]
                        chunk_size = struct.unpack_from("<I", wav_bytes, i+4)[0]
                        if chunk_id == b"data":
                            if sr > 0 and ch > 0 and bps > 0:
                                frame_size = ch * (bps // 8)
                                num_frames = chunk_size // frame_size if frame_size else 0
                                duration_ms = int(num_frames * 1000 / sr)
                            break
                        i += 8 + chunk_size
                        if chunk_size % 2 != 0:
                            i += 1
                except Exception:
                    pass
        elif magic == SFX_MAGIC_LE or magic[:2] == b"\xbf\xbf":
            audio_format = "sfx_obfuscated"
            obfuscation_type = "sfx"
        elif magic == OGG_MAGIC:
            audio_format = "ogg"
            obfuscation_type = "standard"
        elif wav_bytes[:2] == MP3_SYNC or wav_bytes[:3] == b"ID3":
            audio_format = "mp3"
            obfuscation_type = "standard"
        elif len(wav_bytes) > VO_HEADER_SIZE and wav_bytes[VO_HEADER_SIZE:VO_HEADER_SIZE+4] == RIFF_MAGIC:
            audio_format = "wav"
            obfuscation_type = "vo"
        else:
            audio_format = f"unknown_magic_{magic[:4].hex()}"

        result = {
            "game":             game_id,
            "resref":           resref or "(from data_b64)",
            "audio_format":     audio_format,
            "obfuscation_type": obfuscation_type,
            "byte_size":        len(wav_bytes),
        }
        if sample_rate is not None:
            result["sample_rate"]     = sample_rate
            result["channels"]        = channels
            result["bits_per_sample"] = bits_per_sample
        if duration_ms is not None:
            result["duration_ms"] = duration_ms
        return _ok(result)
    except Exception as exc:
        return _err(f"readWAV: {exc}")


async def _read_txi(args: dict) -> List[types.TextContent]:
    """Read a KotOR TXI (texture info) ASCII file.

    TXI files accompany TPC textures and provide rendering parameters:
    blending, mipmaps, filtering, envmap, bump map, cube maps,
    procedural texture, font metrics, and flipbook animation settings.

    Returns all key/value pairs from the TXI file as a structured dict.
    """
    try:
        game_id = _normalize_game(args.get("game", "K1"))
        resref  = (args.get("resref") or "").strip().lower()
        if not resref:
            return _err("readTXI: 'resref' is required")
        try:
            rm = _load_rm(game_id)
        except FileNotFoundError:
            return _err("readTXI: installation not loaded — call gsLoadInstallation first")

        txi_data = rm.read(f"{resref}.txi")
        if txi_data is None:
            return _err(f"readTXI: '{resref}.txi' not found in {game_id} installation")

        # Parse ASCII key-value pairs
        attributes: dict = {}
        for raw_line in txi_data.decode("ascii", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) == 1:
                attributes[parts[0].lower()] = True
            elif len(parts) == 2:
                key, val = parts[0].lower(), parts[1].strip()
                # Try numeric conversion
                try:
                    attributes[key] = int(val)
                except ValueError:
                    try:
                        attributes[key] = float(val)
                    except ValueError:
                        attributes[key] = val

        return _ok({
            "game":             game_id,
            "resref":           resref,
            "attribute_count":  len(attributes),
            "attributes":       attributes,
        })
    except Exception as exc:
        return _err(f"readTXI: {exc}")


async def _pathfind_route(args: dict) -> List[types.TextContent]:
    """Find an A* route between two points on a KotOR PTH path-node graph.

    Loads the PTH file for the given area, builds the adjacency graph, and
    runs A* to find the shortest path between the start and end nodes.

    The caller may specify endpoints in two ways — they can be combined freely:

      Mode A – by node index (the caller already knows the graph):
        start_index : integer PTH node index
        end_index   : integer PTH node index

      Mode B – by world XY coordinates (agent-ergonomic; no pre-knowledge needed):
        start_x, start_y : float world-space coordinates of start position
        end_x,   end_y   : float world-space coordinates of destination

      Mixed: start_index with end_x/end_y, or vice versa — also valid.

    When XY coordinates are provided, the nearest PTH node (Euclidean distance)
    is selected automatically.  The ``start_nearest`` / ``end_nearest`` fields
    in the response confirm which node was selected and the snap distance.

    Returns the path as an ordered list of node indices, total Euclidean
    distance, and the world-space coordinates of each waypoint.

    Args:
        game        : "K1" or "K2"
        resref      : area resref (PTH filename without extension)
        start_index : (Mode A) integer index of the starting PTH node
        end_index   : (Mode A) integer index of the destination PTH node
        start_x     : (Mode B) world X of the start position
        start_y     : (Mode B) world Y of the start position
        end_x       : (Mode B) world X of the destination
        end_y       : (Mode B) world Y of the destination
    """
    try:
        import math, heapq

        game_id = _normalize_game(args.get("game", "K1"))
        resref  = (args.get("resref") or "").strip().lower()

        if not resref:
            return _err("pathfindRoute: 'resref' is required")

        try:
            rm = _load_rm(game_id)
        except FileNotFoundError:
            return _err("pathfindRoute: installation not loaded — call gsLoadInstallation first")

        pth_data = rm.read(f"{resref}.pth")
        if pth_data is None:
            return _err(f"pathfindRoute: '{resref}.pth' not found in {game_id} installation")

        # ── Parse PTH GFF to extract points and connections ──────────────────
        from ghostscripter.core.services import GFFService
        gff  = GFFService.parse_bytes(pth_data)
        root = gff if isinstance(gff, dict) else (gff.get("fields") or gff)

        path_list = root.get("Path_Points") or root.get("PathPoints") or []
        if not path_list:
            return _err(f"pathfindRoute: no Path_Points found in {resref}.pth")

        points: list[dict]          = []
        adjacency: dict[int, list[int]] = {}

        for i, pnode in enumerate(path_list):
            fields   = gff_struct_fields(pnode)
            x        = float(gff_float(fields, "X") or gff_float(fields, "x"))
            y        = float(gff_float(fields, "Y") or gff_float(fields, "y"))
            conns_raw = fields.get("Conections") or fields.get("Connections") or []
            conns: list[int] = []
            if isinstance(conns_raw, list):
                for c in conns_raw:
                    cf  = gff_struct_fields(c)
                    dst = gff_scalar(cf, "Destination") or gff_scalar(cf, "destination")
                    if dst is not None:
                        try:
                            conns.append(int(dst))
                        except (TypeError, ValueError):
                            pass
            points.append({"x": x, "y": y})
            adjacency[i] = conns

        n = len(points)

        # ── nearest-node helper ───────────────────────────────────────────────
        def _nearest_node(wx: float, wy: float) -> tuple[int, float]:
            """Return (node_index, euclidean_distance) for the closest PTH node."""
            best_i, best_d = 0, float("inf")
            for idx, pt in enumerate(points):
                dx = pt["x"] - wx
                dy = pt["y"] - wy
                d  = math.sqrt(dx*dx + dy*dy)
                if d < best_d:
                    best_d, best_i = d, idx
            return best_i, round(best_d, 4)

        # ── resolve start / end indices ───────────────────────────────────────
        start_snap: dict | None = None
        end_snap:   dict | None = None

        raw_si = args.get("start_index")
        raw_ei = args.get("end_index")
        raw_sx = args.get("start_x")
        raw_sy = args.get("start_y")
        raw_ex = args.get("end_x")
        raw_ey = args.get("end_y")

        # Determine start
        if raw_si is not None:
            start_index = int(raw_si)
        elif raw_sx is not None and raw_sy is not None:
            start_index, snap_d = _nearest_node(float(raw_sx), float(raw_sy))
            start_snap = {"snapped_to": start_index, "snap_distance": snap_d,
                          "from_x": float(raw_sx), "from_y": float(raw_sy)}
        else:
            return _err(
                "pathfindRoute: provide 'start_index' OR ('start_x' + 'start_y')"
            )

        # Determine end
        if raw_ei is not None:
            end_index = int(raw_ei)
        elif raw_ex is not None and raw_ey is not None:
            end_index, snap_d = _nearest_node(float(raw_ex), float(raw_ey))
            end_snap = {"snapped_to": end_index, "snap_distance": snap_d,
                        "from_x": float(raw_ex), "from_y": float(raw_ey)}
        else:
            return _err(
                "pathfindRoute: provide 'end_index' OR ('end_x' + 'end_y')"
            )

        if start_index < 0 or start_index >= n:
            return _err(f"pathfindRoute: start_index {start_index} out of range [0, {n-1}]")
        if end_index < 0 or end_index >= n:
            return _err(f"pathfindRoute: end_index {end_index} out of range [0, {n-1}]")

        if start_index == end_index:
            result: dict = {
                "game": game_id, "resref": resref,
                "start_index": start_index, "end_index": end_index,
                "path": [start_index], "step_count": 1, "total_distance": 0.0,
                "waypoints": [points[start_index]],
            }
            if start_snap: result["start_nearest"] = start_snap
            if end_snap:   result["end_nearest"]   = end_snap
            return _ok(result)

        # ── A* search ─────────────────────────────────────────────────────────
        def _dist(a: int, b: int) -> float:
            dx = points[a]["x"] - points[b]["x"]
            dy = points[a]["y"] - points[b]["y"]
            return math.sqrt(dx*dx + dy*dy)

        open_set: list = []
        heapq.heappush(open_set, (0.0, start_index))
        came_from: dict[int, int] = {}
        g_score: dict[int, float] = {start_index: 0.0}
        f_score: dict[int, float] = {start_index: _dist(start_index, end_index)}
        visited: set = set()

        found = False
        while open_set:
            _, current = heapq.heappop(open_set)
            if current in visited:
                continue
            visited.add(current)
            if current == end_index:
                found = True
                break
            for neighbor in adjacency.get(current, []):
                if neighbor in visited:
                    continue
                tentative_g = g_score.get(current, float("inf")) + _dist(current, neighbor)
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor]   = tentative_g
                    f_score[neighbor]   = tentative_g + _dist(neighbor, end_index)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))

        if not found:
            return _err(f"pathfindRoute: no path found from {start_index} to {end_index}")

        # Reconstruct path
        path: list[int] = []
        node = end_index
        while node in came_from:
            path.append(node)
            node = came_from[node]
        path.append(start_index)
        path.reverse()

        total_distance = sum(_dist(path[i], path[i+1]) for i in range(len(path)-1))
        waypoints      = [points[idx] for idx in path]

        result = {
            "game":           game_id,
            "resref":         resref,
            "start_index":    start_index,
            "end_index":      end_index,
            "path":           path,
            "step_count":     len(path),
            "total_distance": round(total_distance, 4),
            "waypoints":      waypoints,
        }
        if start_snap: result["start_nearest"] = start_snap
        if end_snap:   result["end_nearest"]   = end_snap
        return _ok(result)
    except Exception as exc:
        return _err(f"pathfindRoute: {exc}")


async def _get_nwscript_db(args: dict) -> List[types.TextContent]:
    """Return the full NWScript function and constant database for K1 or K2.

    Returns all function signatures and all constants from the bundled
    nwscript.nss for the requested game. Useful for agents that need
    to enumerate all available functions or build reference lists.

    Args:
        game (str): "K1" or "K2" (default "K1")

    Returns:
        game, function_count, constant_count,
        functions: [{name, return_type, parameters, category}],
        constants: [{name, value, category}]
    """
    game_id = _normalize_game(args.get("game", "K1"))
    from ghostscripter.core.services import NWScriptService
    db = NWScriptService.load(game_id)

    functions = []
    for func in getattr(db, "functions", []):
        functions.append({
            "name": func.name,
            "return_type": func.return_type,
            "parameters": [
                {"name": p.name, "type": p.type, "default": p.default}
                for p in func.params
            ],
            "signature": func.signature,
            "category": func.category,
            "description": func.comment,
            "source_line": func.line_number,
        })

    constants = []
    for const in getattr(db, "constants", []):
        constants.append({
            "name": const.name,
            "type": const.type,
            "value": const.value,
            "category": const.category,
            "source_line": const.line_number,
        })

    duplicate_declarations = {
        name: [
            {"value": item.value, "source_line": item.line_number}
            for item in declarations
        ]
        for name, declarations in getattr(db, "duplicate_constants", {}).items()
    }

    return _ok({
        "game": game_id,
        "function_count": len(functions),
        "constant_count": len(constants),
        "constant_declaration_count": len(getattr(db, "constant_declarations", constants)),
        "duplicate_constant_declarations": duplicate_declarations,
        "functions": functions,
        "constants": constants,
    })
