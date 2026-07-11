"""Write, compile, and patch MCP tool handlers."""
from __future__ import annotations

from typing import Any, List

import mcp.types as types

import os
from pathlib import Path

from ghostscripter.mcp.tools_pkg._helpers import (
    _err, _load_rm, _normalize_game, _ok, _safe_write_path, _validate_resref, log,
)


async def _write_gff(args: dict) -> List[types.TextContent]:
    import base64
    import re

    document = args.get("document")
    has_legacy_fields = "fields" in args
    if document is not None and has_legacy_fields:
        return _err("writeGFF: provide either 'document' or legacy 'fields', not both.")

    try:
        from ghostscripter.core.services import GFFService

        if document is not None:
            if not isinstance(document, dict):
                return _err("writeGFF: 'document' must be the JSON object returned by readGFF.")
            data = GFFService.write_typed(document)
            file_type = str(document.get("file_type", ""))

            # A redundant fileType is accepted only when it agrees, preventing
            # callers from accidentally relabelling content during a round-trip.
            raw_ft = args.get("fileType") or args.get("file_type")
            if raw_ft is not None:
                requested_type = str(raw_ft).ljust(4)[:4]
                if requested_type != file_type:
                    return _err(
                        "writeGFF: fileType conflicts with the typed document "
                        f"({requested_type!r} != {file_type!r})."
                    )
            fidelity = "lossless_typed"
            result: dict[str, Any] = {
                "schema": document.get("schema"),
                "content": document.get("content"),
            }
        else:
            raw_ft = args.get("fileType") or args.get("file_type") or ""
            if not raw_ft:
                return _err(
                    "writeGFF: pass a typed 'document' from readGFF. "
                    "Legacy 'fields' also requires fileType and allowLossy=true."
                )
            file_type = str(raw_ft).ljust(4)[:4]
            safe_ft = file_type.strip()
            if not safe_ft or not re.fullmatch(r"[A-Za-z0-9_ ]{1,4}", file_type):
                return _err(
                    f"writeGFF: invalid fileType {file_type!r}. Must be 1-4 "
                    "alphanumeric characters (e.g. 'UTC ', 'DLG ')."
                )
            if not has_legacy_fields or not isinstance(args.get("fields"), dict):
                return _err("writeGFF: legacy 'fields' must be a JSON object.")
            allow_lossy = args.get("allowLossy", args.get("allow_lossy", False))
            if allow_lossy is not True:
                return _err(
                    "writeGFF: untyped fields are ambiguous and could corrupt types. "
                    "Use the typed document returned by readGFF, or explicitly set "
                    "allowLossy=true only when creating a new legacy file."
                )
            data = GFFService.write(file_type, args["fields"], allow_lossy=True)
            fidelity = "lossy_legacy"
            result = {
                "warning": (
                    "Legacy fields were written with inferred types: string=String, "
                    "integer=UInt32, float=Single, object=Struct, array=List."
                )
            }

        result.update({
            "file_type": file_type,
            "fidelity": fidelity,
            "size_bytes": len(data),
            "data_base64": base64.b64encode(data).decode("ascii"),
        })
        return _ok(result)
    except Exception as e:
        return _err(f"GFF write error: {e}")


async def _write_dlg(args: dict) -> List[types.TextContent]:
    """Export a dialogue JSON dict to binary KotOR DLG bytes."""
    import base64
    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"writeDLG: {e}")
    dlg_dict = args.get("dialogue", {})
    if not isinstance(dlg_dict, dict):
        return _err("writeDLG: 'dialogue' must be a JSON object.")

    try:
        from ghostscripter.core.services import DialogueService
        dlg = DialogueService.from_dict(dlg_dict)
        data = DialogueService.to_binary(dlg, game_id)
        return _ok({
            "game": game_id,
            "size_bytes": len(data),
            "entry_count": len(dlg.entries),
            "reply_count": len(dlg.replies),
            "data_base64": base64.b64encode(data).decode("ascii"),
        })
    except Exception as e:
        return _err(f"writeDLG error: {e}")


async def _write_twoda(args: dict) -> List[types.TextContent]:
    """Serialise a 2DA table (columns + rows) to text or binary KotOR format."""
    import base64
    resref  = args.get("resref", "output").lower().strip()
    columns = args.get("columns", [])
    rows    = args.get("rows", [])
    fmt     = args.get("format", "text").lower()
    edits   = args.get("edits", [])

    err = _validate_resref(resref, "writeTwoDA")
    if err:
        return _err(err)

    if not columns:
        return _err("writeTwoDA: 'columns' is required and must be non-empty.")

    try:
        from ghostscripter.core.services import TwoDAService

        # Build TwoDAFile via the service layer (contract coupling)
        tda = TwoDAService.build_from_dicts(resref, columns, rows)

        # Apply optional cell edits
        warnings: list[str] = []
        for edit in edits:
            row_key = edit.get("row")
            col     = edit.get("column", "")
            val     = str(edit.get("value", "****"))
            if isinstance(row_key, int):
                if 0 <= row_key < len(tda.rows):
                    TwoDAService.set_cell(tda, row_key, col, val)
                else:
                    warnings.append(f"Row index {row_key} out of range.")
            else:
                # string label lookup
                found = False
                for row in tda.rows:
                    if row.label == str(row_key):
                        row.data[col] = val
                        found = True
                        break
                if not found:
                    warnings.append(f"Row label '{row_key}' not found; edit skipped.")

        # Serialise via the service layer
        if fmt == "binary":
            data = TwoDAService.to_binary(tda)
        else:
            data = TwoDAService.to_text(tda).encode("latin-1")

        result: dict = {
            "resref":       resref,
            "format":       fmt,
            "row_count":    len(tda.rows),
            "column_count": len(tda.columns),
            "size_bytes":   len(data),
            "data_base64":  base64.b64encode(data).decode("ascii"),
        }
        if warnings:
            result["warnings"] = warnings
        return _ok(result)

    except Exception as e:
        return _err(f"writeTwoDA error: {e}")


async def _write_erf(args: dict) -> List[types.TextContent]:
    """Pack resource files into a KotOR ERF v1.0 binary archive (MOD/ERF/SAV)."""
    import base64
    files        = args.get("files", [])
    archive_type = args.get("archive_type", "MOD ").upper().ljust(4)[:4]

    if not files:
        return _err("writeERF: 'files' list is required and must be non-empty.")

    try:
        from ghostscripter.core.services import ERFService

        added: list[str] = []
        valid_files: list[dict] = []

        for index, entry in enumerate(files):
            resref   = str(entry.get("resref", "")).strip()
            ext      = str(entry.get("type", "")).strip().lstrip(".")
            data_b64 = str(entry.get("data_b64", ""))
            if not resref or not ext or not data_b64:
                return _err(
                    f"writeERF: files[{index}] requires resref, type, and data_b64."
                )
            resref_error = _validate_resref(resref, f"writeERF files[{index}]")
            if resref_error:
                return _err(resref_error)
            valid_files.append({"resref": resref, "restype": ext, "data_b64": data_b64})

        if not valid_files:
            return _err("writeERF: no valid files to pack.")

        erf_bytes, svc_warnings = ERFService.build(valid_files, archive_type)
        # Count only files that were actually packed (not skipped due to bad base64)
        packed = [f"{v['resref']}.{v['restype']}" for v in valid_files
                  if not any(v['resref'] in w for w in svc_warnings)]
        result: dict = {
            "archive_type": archive_type.strip(),
            "file_count":   len(packed),
            "size_bytes":   len(erf_bytes),
            "files":        packed,
            "data_base64":  base64.b64encode(erf_bytes).decode("ascii"),
        }
        if svc_warnings:
            result["warnings"] = svc_warnings
        return _ok(result)

    except Exception as e:
        log.debug("writeERF error: %s", e)
        return _err(f"writeERF error: {e}")


async def _compile_script(args: dict) -> List[types.TextContent]:
    """Compile NWScript source to .ncs binary.

    Compilation priority:
      1. PyKotor InbuiltNCSCompiler (Python-native, no Wine, no external binary)
      2. user-installed nwnnsscomp on PATH

    The InbuiltNCSCompiler path is always tried first because it works on all platforms
    (Windows/Linux/macOS) without Wine.  It requires PyKotor to be installed.
    nwnnsscomp is only a fallback when a user has installed it independently.
    """
    import base64
    import subprocess
    import sys
    import tempfile

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"compileScript: {e}")
    source: str = args.get("source", "")
    resref: str = (args.get("resref") or "script").strip() or "script"

    if not source.strip():
        return _err("compileScript: 'source' must not be empty.")
    resref_error = _validate_resref(resref, "compileScript")
    if resref_error:
        return _err(resref_error)

    # ── Strategy 1: PyKotor InbuiltNCSCompiler (cross-platform, no Wine) ─────
    # Uses pykotor.resource.formats.ncs.compilers.InbuiltNCSCompiler which wraps
    # the pure-Python NssParser/NssLexer from PyKotor's native implementation.
    # Equivalent to HolocronToolset's use of InbuiltNCSCompiler without the need
    # for SpoofKotorRegistry (registry spoofing only needed for external compilers).
    try:
        from pykotor.resource.formats.ncs.compilers import InbuiltNCSCompiler  # type: ignore[import]
        from pykotor.resource.formats.ncs.ncs_auto import write_ncs  # type: ignore[import]
        from pykotor.common.misc import Game  # type: ignore[import]
        from io import BytesIO
        from ghostscripter.core.nwscript.compiler_defs import install_pykotor_definitions

        install_pykotor_definitions(game_id)

        # Locate nwscript.nss include file bundled with GhostScripter
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        else:
            base = Path(__file__).parent.parent.parent.parent
        game_lower = game_id.lower()
        nwscript_path = base / "resources" / "scripts" / game_lower / "nwscript.nss"

        game_enum = Game.K1 if game_id == "K1" else Game.K2

        with tempfile.TemporaryDirectory() as tmp:
            nss_path = Path(tmp) / f"{resref}.nss"
            ncs_path = Path(tmp) / f"{resref}.ncs"

            # Copy nwscript.nss into temp dir so #include "nwscript" resolves
            if nwscript_path.exists():
                import shutil
                shutil.copy(nwscript_path, Path(tmp) / "nwscript.nss")

            nss_path.write_text(source, encoding="utf-8", errors="replace")

            compiler = InbuiltNCSCompiler()
            stdout, stderr = compiler.compile_script(
                source_file=nss_path,
                output_file=ncs_path,
                game=game_enum,
            )
            compiler_output = ((stdout or "") + (stderr or "")).strip()

            if ncs_path.exists():
                ncs_bytes = ncs_path.read_bytes()
                return _ok({
                    "game": game_id,
                    "resref": resref,
                    "success": True,
                    "size_bytes": len(ncs_bytes),
                    "data_base64": base64.b64encode(ncs_bytes).decode("ascii"),
                    "compiler_output": compiler_output or "OK",
                    "compiler": "InbuiltNCSCompiler (PyKotor native)",
                })
            # InbuiltNCSCompiler raises on error, so we'd only get here if it silently failed
            log.debug("compileScript: InbuiltNCSCompiler produced no output for %s", resref)
    except ImportError:
        log.debug("compileScript: PyKotor not available, falling back to nwnnsscomp")
    except Exception as pykotor_exc:
        # Syntax or semantic error from PyKotor's compiler — return immediately
        # (no point trying nwnnsscomp for a real compilation error)
        err_str = str(pykotor_exc)
        log.debug("compileScript PyKotor error: %s", err_str)
        return _ok({
            "game": game_id,
            "resref": resref,
            "success": False,
            "compiler_output": err_str,
            "compiler": "InbuiltNCSCompiler (PyKotor native)",
            "error": err_str,
        })

    # ── Strategy 2: nwnnsscomp (bundled .exe, native binary, or Wine) ────────
    def _candidates() -> list[list[str]]:
        native = [["nwnnsscomp"], ["nwnnsscomp.exe"]]
        return native

    compiler_cmd: list[str] | None = None
    for cmd in _candidates():
        try:
            subprocess.run(cmd, capture_output=True, timeout=3)
            compiler_cmd = cmd
            break
        except (FileNotFoundError, PermissionError, OSError):
            pass
        except subprocess.TimeoutExpired:
            compiler_cmd = cmd
            break

    if compiler_cmd is None:
        searched = [" ".join(c) for c in _candidates()]
        return _err(
            f"compileScript: no compiler available. "
            f"Install PyKotor (`pip install pykotor`) for cross-platform native compilation, "
            f"or on Linux/macOS install Wine. "
            f"Searched for nwnnsscomp at: {searched}"
        )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            nss_path = Path(tmp) / f"{resref}.nss"
            ncs_path = Path(tmp) / f"{resref}.ncs"
            nss_path.write_text(source, encoding="latin-1", errors="replace")

            invoke = compiler_cmd + ["-c", str(nss_path)]
            result = subprocess.run(
                invoke,
                capture_output=True, text=True, timeout=30,
                cwd=tmp,
            )
            compiler_output = (result.stdout + result.stderr).strip()
            compiler_name = " ".join(Path(p).name for p in compiler_cmd if p != "wine")

            if ncs_path.exists():
                ncs_bytes = ncs_path.read_bytes()
                return _ok({
                    "game": game_id,
                    "resref": resref,
                    "success": True,
                    "size_bytes": len(ncs_bytes),
                    "data_base64": base64.b64encode(ncs_bytes).decode("ascii"),
                    "compiler_output": compiler_output or "OK",
                    "compiler": compiler_name,
                })
            else:
                return _ok({
                    "game": game_id,
                    "resref": resref,
                    "success": False,
                    "compiler_output": compiler_output or "(no output)",
                    "compiler": compiler_name,
                    "error": "Compiler ran but produced no .ncs output. Check compiler_output for details.",
                })

    except subprocess.TimeoutExpired:
        return _err("compileScript: compiler timed out after 30 seconds.")
    except Exception as e:
        log.debug("compileScript error: %s", e)
        return _err(f"compileScript error: {e}")


async def _decompile_script(args: dict) -> List[types.TextContent]:
    """Decompile a KotOR NCS binary back to NWScript (.nss) source.

    Decompilation strategies (in priority order):
      1. PyKotor decompile_ncs  (pure-Python, cross-platform, returns NSS source)
      2. PyKotor disassemble_ncs (pure-Python, returns human-readable disassembly)
      3. xoreos ncsdecomp CLI   (external binary, optional)

    The input NCS can be provided in three ways (in priority order):
      a. data_base64 — raw NCS bytes encoded as base64
      b. resref      — resource reference looked up from a loaded installation
      c. (future)    path — absolute path on disk

    The response always contains:
      - nss_source   (str)  full decompiled/disassembled text
      - method       (str)  which strategy produced the output
      - game         (str)  K1 or K2
      - resref       (str)  the resref used (or 'inline' for base64 input)
      - disassembly  (str)  low-level disassembly (from readNCS) if available
    """
    import base64
    import tempfile

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"decompileScript: {e}")

    resref: str = (args.get("resref") or "").strip()
    data_b64: str = args.get("data_base64") or args.get("data_b64") or ""
    if resref:
        resref_error = _validate_resref(resref, "decompileScript")
        if resref_error:
            return _err(resref_error)

    # ── Resolve NCS bytes ───────────────────────────────────────────────────
    ncs_bytes: bytes | None = None

    if data_b64:
        try:
            ncs_bytes = base64.b64decode(data_b64, validate=True)
        except Exception as decode_err:
            return _err(f"decompileScript: invalid base64 data: {decode_err}")
        used_resref = resref or "inline"
    elif resref:
        try:
            rm = _load_rm(game_id)
        except Exception as e:
            return _err(f"decompileScript: could not load installation for {game_id}: {e}")
        ncs_bytes = rm.read(f"{resref}.ncs")
        if ncs_bytes is None:
            return _err(f"decompileScript: NCS resource '{resref}' not found in {game_id} installation.")
        used_resref = resref
    else:
        return _err("decompileScript: provide either 'data_base64' (raw NCS bytes) or 'resref' to look up.")

    if not ncs_bytes:
        return _err("decompileScript: NCS data is empty.")

    # ── Strategy 1 & 2: PyKotor native decompiler / disassembler ───────────
    nss_source: str | None = None
    disassembly: str | None = None
    method: str = "unknown"

    try:
        from pykotor.common.misc import Game as PyGame  # type: ignore[import]
        from pykotor.resource.formats.ncs.ncs_auto import read_ncs  # type: ignore[import]
        from pykotor.resource.formats.ncs.decompiler import NCSDecompiler  # type: ignore[import]

        game_enum = PyGame.K1 if game_id == "K1" else PyGame.K2
        ncs_obj = read_ncs(ncs_bytes)

        # Disassembly is the lossless, authoritative representation.  Produce
        # it even when a higher-level source reconstruction is available.
        lines = []
        for index, instr in enumerate(ncs_obj.instructions):
            args = " ".join(str(arg) for arg in instr.args)
            jump = ""
            if instr.jump is not None:
                target = instr.jump.offset
                jump = f" -> {target}" if target >= 0 else " -> <target>"
            lines.append(
                f"{index:4d}  {instr.ins_type.name:<20} {args}{jump}".rstrip()
            )
        disassembly = "\n".join(lines)

        # Strategy 1: NCSDecompiler.decompile() — returns NSS source via PyKotor's
        # built-in decompiler (available in pykotor >= 2.3.x, no external deps).
        try:
            dec = NCSDecompiler(ncs_obj, game_enum)
            nss_source = dec.decompile()
            method = "PyKotor NCSDecompiler"
        except Exception as decompile_err:
            log.debug("decompileScript: NCSDecompiler.decompile() failed (%s), trying disassembly", decompile_err)

        # Strategy 2: return the always-generated instruction listing when
        # source reconstruction is unavailable.
        if nss_source is None:
            nss_source = disassembly
            method = "PyKotor NCS disassembly"

    except ImportError:
        log.debug("decompileScript: PyKotor not available, trying xoreos ncsdecomp")
    except Exception as pykotor_err:
        log.debug("decompileScript: PyKotor error: %s", pykotor_err)

    # ── Strategy 3: xoreos ncsdecomp CLI ────────────────────────────────────
    if nss_source is None:
        import subprocess
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ncs_path = Path(tmp) / f"{used_resref}.ncs"
                nss_path = Path(tmp) / f"{used_resref}.nss"
                ncs_path.write_bytes(ncs_bytes)
                result = subprocess.run(
                    ["ncsdecomp", str(ncs_path), str(nss_path)],
                    capture_output=True, text=True, timeout=15,
                )
                if nss_path.exists():
                    nss_source = nss_path.read_text(encoding="utf-8", errors="replace")
                    method = "ncsdecomp (xoreos)"
                else:
                    cli_out = (result.stdout + result.stderr).strip()
                    return _err(f"decompileScript: ncsdecomp produced no output. {cli_out}")
        except FileNotFoundError:
            return _err(
                "decompileScript: no decompiler available. "
                "Install PyKotor (`pip install pykotor`) for native cross-platform decompilation, "
                "or install xoreos-tools for the ncsdecomp CLI."
            )
        except subprocess.TimeoutExpired:
            return _err("decompileScript: ncsdecomp timed out after 15 seconds.")
        except Exception as cli_err:
            return _err(f"decompileScript: external decompiler error: {cli_err}")

    if nss_source is None:
        return _err("decompileScript: all decompilation strategies failed.")

    source_verified = False
    source_status = "disassembly_only"
    warning: str | None = None
    if method != "PyKotor NCS disassembly":
        try:
            from pykotor.common.misc import Game as PyGame
            from pykotor.resource.formats.ncs.ncs_auto import bytes_ncs, compile_nss
            from ghostscripter.core.nwscript.compiler_defs import install_pykotor_definitions

            install_pykotor_definitions(game_id)
            game_enum = PyGame.K1 if game_id == "K1" else PyGame.K2
            rebuilt = bytes(bytes_ncs(compile_nss(nss_source, game_enum)))
            source_verified = rebuilt == ncs_bytes
            source_status = "byte_exact_roundtrip" if source_verified else "unverified_reconstruction"
        except Exception as verify_error:
            source_status = "unverified_reconstruction"
            log.debug("decompileScript: candidate verification failed: %s", verify_error)
        if not source_verified:
            warning = (
                "The reconstructed NWScript did not reproduce the original NCS bytes. "
                "Treat it as a reading aid; use disassembly for authoritative behavior."
            )

    result_dict: dict = {
        "game":        game_id,
        "resref":      used_resref,
        "method":      method,
        "nss_source":  nss_source,
        "size_bytes":  len(ncs_bytes),
        "source_verified": source_verified,
        "source_status": source_status,
        "disassembly": disassembly or "",
    }
    if warning:
        result_dict["warning"] = warning

    return _ok(result_dict)


async def _write_override(args: dict) -> List[types.TextContent]:
    """Write a resource file directly into the game's Override folder."""
    import base64

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"writeOverride: {e}")

    resref  = str(args.get("resref", "")).strip()
    restype = str(args.get("restype", "")).strip().lstrip(".")
    data_b64 = str(args.get("data_b64", ""))

    err = _validate_resref(resref, "writeOverride")
    if err:
        return _err(err)
    # Path-safety: validate extension against allow-list and check for
    # path-traversal characters in both resref and restype.
    path_err = _safe_write_path(resref, restype, "writeOverride")
    if path_err:
        return _err(path_err)
    if not data_b64:
        return _err("writeOverride: 'data_b64' is required.")

    try:
        data = base64.b64decode(data_b64, validate=True)
    except Exception as e:
        return _err(f"writeOverride: invalid base64 data: {e}")

    try:
        rm = _load_rm(game_id)
    except (FileNotFoundError, ValueError) as e:
        return _err(
            f"writeOverride: {e} "
            "Call loadInstallation first with a valid game path."
        )
    override_path: Path | None = None

    # Derive Override path via the ResourceManager's public accessor.
    # ResourceManager.get_game_dir() returns the game root set by load_game().
    game_dir = rm.get_game_dir() if callable(getattr(rm, "get_game_dir", None)) else None
    if game_dir is not None:
        candidate = Path(game_dir) / "Override"
        # Create the Override folder if the game root exists but Override doesn't yet
        if candidate.parent.exists():
            candidate.mkdir(exist_ok=True)
            override_path = candidate

    if override_path is None:
        # Fallback: infer from already-indexed override files
        for fpath in list(getattr(rm, "_override_files", {}).values())[:5]:
            p = Path(fpath).parent
            if p.name.lower() == "override" and p.exists():
                override_path = p
                break

    if override_path is None:
        return _err(
            f"writeOverride: Override folder not found for {game_id}. "
            "Call loadInstallation with a valid game path first, "
            "or set the K1_PATH / K2_PATH environment variable."
        )

    dest = override_path / f"{resref}.{restype}"
    try:
        dest.write_bytes(data)
    except OSError as e:
        return _err(f"writeOverride: could not write {dest}: {e}")

    # Register the new file in the ResourceManager's override index so that
    # subsequent reads in the same session (readGFF, getScript, etc.) see it.
    try:
        override_key = f"{resref}.{restype}".lower()
        rm._override_files[override_key] = dest
        # Invalidate any cached read for this key so the new bytes are returned
        cache = getattr(rm, "_read_cache", None)
        if cache is not None and override_key in cache:
            del cache[override_key]
    except Exception as _e:
        log.debug("writeOverride: could not update override index: %s", _e)

    return _ok({
        "game": game_id,
        "resref": resref,
        "restype": restype,
        "path": str(dest),
        "size_bytes": len(data),
        "written": True,
    })


async def _write_lip(args: dict) -> List[types.TextContent]:
    """Encode a KotOR lip-sync animation file (LIP V1.0) from a keyframe list.

    Produces a base64-encoded LIP binary ready for writeOverride.

    Args:
        duration  (float): total audio duration in seconds
        keyframes (list):  ordered list of {time: float, shape: int|str}
                           shape may be an integer 0-15, a verified semantic
                           group name, or an ARPAbet phoneme

    Returns a dict with:
        size_bytes, keyframe_count, data (base64 LIP binary)
    """
    import base64
    import struct

    from ghostscripter.core.lip import LIP_SHAPES, shape_index

    duration = args.get("duration")
    if duration is None:
        return _err("writeLIP: 'duration' is required.")
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        return _err("writeLIP: 'duration' must be a number.")
    if duration < 0:
        return _err("writeLIP: 'duration' must be >= 0.")

    raw_kf = args.get("keyframes")
    if not isinstance(raw_kf, list):
        return _err("writeLIP: 'keyframes' must be an array.")

    parsed: list[tuple[float, int]] = []
    for idx, kf in enumerate(raw_kf):
        if not isinstance(kf, dict):
            return _err(f"writeLIP: keyframe[{idx}] must be an object with 'time' and 'shape'.")
        try:
            t = float(kf["time"])
        except (KeyError, TypeError, ValueError):
            return _err(f"writeLIP: keyframe[{idx}] missing or invalid 'time'.")
        if t < 0:
            return _err(f"writeLIP: keyframe[{idx}] time {t} is negative.")

        shape_raw = kf.get("shape", 0)
        if isinstance(shape_raw, str):
            shape_int = shape_index(shape_raw)
            if shape_int is None:
                valid = ", ".join(LIP_SHAPES)
                return _err(
                    f"writeLIP: keyframe[{idx}] shape '{shape_raw}' not recognised. "
                    f"Valid names: {valid}."
                )
        else:
            try:
                shape_int = int(shape_raw)
            except (TypeError, ValueError):
                return _err(f"writeLIP: keyframe[{idx}] 'shape' must be int 0-15 or string name.")
            if not (0 <= shape_int <= 15):
                return _err(f"writeLIP: keyframe[{idx}] shape index {shape_int} out of range 0-15.")

        parsed.append((t, shape_int))

    # Validate ascending order
    for i in range(1, len(parsed)):
        if parsed[i][0] < parsed[i - 1][0]:
            return _err(
                f"writeLIP: keyframe[{i}] time {parsed[i][0]} is before "
                f"keyframe[{i-1}] time {parsed[i-1][0]}. Keyframes must be in ascending order."
            )

    # Build binary
    buf = bytearray()
    buf += b"LIP V1.0"
    buf += struct.pack("<f", duration)
    buf += struct.pack("<I", len(parsed))
    for t, s in parsed:
        buf += struct.pack("<f", t)
        buf += struct.pack("<B", s)

    return _ok({
        "size_bytes":     len(buf),
        "keyframe_count": len(parsed),
        "data":           base64.b64encode(bytes(buf)).decode(),
    })

async def _write_ssf(args: dict) -> List[types.TextContent]:
    """Encode a KotOR SSF (Sound Set File) from a slot→StrRef mapping.

    The first 28 SSF entries map named sound-event slots to TLK StrRef
    integers. New files also contain the 12 undocumented compatibility entries
    used by PyKotor and most retail resources. An ``unknown_slots`` value from
    readSSF can be supplied when preserving a longer retail table.

    SSF V1.1 binary layout (from PyKotor ssf/io_ssf.py):
        Header  : "SSF V1.1" (8 bytes)
        Offset  : uint32 = 12  (offset to sound table)
        Table   : at least 28 × uint32 StrRefs (0xFFFFFFFF = no sound)

    Canonical slot names (0-27):
        BATTLE_CRY_1..6, SELECT_1..3, ATTACK_GRUNT_1..3, PAIN_GRUNT_1..2,
        LOW_HEALTH, DEAD, CRITICAL_HIT, TARGET_IMMUNE, LAY_MINE, DISARM_MINE,
        BEGIN_STEALTH, BEGIN_SEARCH, BEGIN_UNLOCK, UNLOCK_FAILED,
        UNLOCK_SUCCESS, SEPARATED_FROM_PARTY, REJOINED_PARTY, POISONED

    Args:
        game    (str):  "K1" or "K2"
        resref  (str):  target resref for writeOverride (e.g. "n_bastila")
        slots   (dict): {slot_name_or_index: strref_int, ...}
                        Missing slots default to -1 (no sound).
        unknown_slots (dict|list): optional readSSF-compatible trailing entries
                        to preserve. New files default to 12 unset tail entries.
        write_override (bool): if true, also call writeOverride. Default false.

    Returns:
        size_bytes, slot_count, entry_count, data (base64 SSF binary)
    """
    import base64
    import json

    from ghostscripter.core.ssf import (
        SSF_DEFAULT_ENTRY_COUNT,
        SSF_SLOT_COUNT,
        SSF_SLOT_NAMES,
        encode_ssf,
        validate_strref,
    )

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"writeSSF: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "writeSSF")
    if err:
        return _err(err)

    slots_raw = args.get("slots", {})
    if not isinstance(slots_raw, dict):
        return _err("writeSSF: 'slots' must be a dict of {slot_name_or_index: strref}.")

    slot_indices = {name: index for index, name in enumerate(SSF_SLOT_NAMES)}
    strrefs: list[int] = [-1] * SSF_DEFAULT_ENTRY_COUNT

    def _coerce_strref(value: Any, label: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{label} value must be an integer StrRef")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{label} value must be an integer StrRef")
        try:
            parsed = int(value)
            validate_strref(parsed)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} value must be a valid 32-bit StrRef: {exc}") from exc
        return parsed

    for key, val in slots_raw.items():
        try:
            strref = _coerce_strref(val, f"slot '{key}'")
        except ValueError as exc:
            return _err(f"writeSSF: {exc}.")

        if isinstance(key, bool):
            return _err("writeSSF: boolean slot keys are not valid indices.")
        if isinstance(key, int) or (isinstance(key, str) and key.strip().isdigit()):
            idx = int(key)
        elif isinstance(key, str):
            key_upper = key.strip().upper()
            if key_upper in slot_indices:
                idx = slot_indices[key_upper]
            else:
                return _err(f"writeSSF: unknown slot name '{key}'. Use 0-27 or canonical name.")
        else:
            return _err(f"writeSSF: slot key must be int or string, got {type(key).__name__}.")

        if not (0 <= idx < SSF_SLOT_COUNT):
            return _err(f"writeSSF: slot index {idx} out of range 0-27.")
        strrefs[idx] = strref

    unknown_raw = args.get("unknown_slots")
    if unknown_raw is not None:
        if isinstance(unknown_raw, dict):
            unknown_items = list(unknown_raw.items())
        elif isinstance(unknown_raw, list):
            unknown_items = []
            for position, item in enumerate(unknown_raw):
                if not isinstance(item, dict) or "index" not in item or "strref" not in item:
                    return _err(
                        "writeSSF: unknown_slots list entries must contain "
                        f"'index' and 'strref' (invalid entry {position})."
                    )
                unknown_items.append((item["index"], item["strref"]))
        else:
            return _err("writeSSF: 'unknown_slots' must be an object or readSSF slot list.")

        for raw_index, raw_strref in unknown_items:
            if isinstance(raw_index, bool):
                return _err("writeSSF: boolean unknown-slot indices are invalid.")
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                return _err(f"writeSSF: unknown-slot index '{raw_index}' is not an integer.")
            if index < SSF_SLOT_COUNT:
                return _err(
                    f"writeSSF: unknown-slot index {index} overlaps canonical slots 0-27."
                )
            if index > 4095:
                return _err(f"writeSSF: unknown-slot index {index} exceeds safety limit 4095.")
            try:
                strref = _coerce_strref(raw_strref, f"unknown slot {index}")
            except ValueError as exc:
                return _err(f"writeSSF: {exc}.")
            if index >= len(strrefs):
                strrefs.extend([-1] * (index + 1 - len(strrefs)))
            strrefs[index] = strref

    encoded = encode_ssf(strrefs)
    data_b64 = base64.b64encode(encoded).decode()

    result: dict = {
        "game": game_id,
        "resref": resref,
        "size_bytes": len(encoded),
        "slot_count": SSF_SLOT_COUNT,
        "assigned_slot_count": sum(1 for s in strrefs[:SSF_SLOT_COUNT] if s != -1),
        "entry_count": len(strrefs),
        "data": data_b64,
    }

    if args.get("write_override", False):
        ov_result = await _write_override({
            "game": game_id,
            "resref": resref,
            "restype": "ssf",
            "data_b64": data_b64,
        })
        try:
            result["write_override"] = json.loads(ov_result[0].text)
        except (AttributeError, IndexError, json.JSONDecodeError):
            result["write_override"] = {"error": "writeOverride returned an invalid response"}

    return _ok(result)


async def _write_pth(args: dict) -> List[types.TextContent]:
    """Encode a KotOR PTH (pathfinding) GFF V3.2 binary from a path-node graph.

    PTH files are GFF-based and define the NPC pathfinding graph for an area.
    Each point has X/Y coordinates and a list of connection indices
    (destination node indices, 0-based). Returns base64-encoded PTH binary.

    PTH GFF structure (from PyKotor pth.py / BioWare reverse engineering):
        Root struct:
          Path_Points (GFFList):
            Each entry struct:
              X              (FLOAT)
              Y              (FLOAT)
              Conections     (DWORD) — count of outgoing edges from this point
              First_Conection (DWORD) — index into Path_Conections where this
                                        point's edges begin
          Path_Conections (GFFList):  [sic – BioWare typo in original field name]
            Each entry struct:
              Destination    (DWORD) — 0-based index into Path_Points

    Args:
        game    (str):  "K1" or "K2"
        resref  (str):  target area resref (e.g. "danm13")
        points  (list): list of {x: float, y: float, connections: [int, ...]}
        write_override (bool): if true, also write to Override folder. Default false.

    Returns:
        size_bytes, point_count, connection_count, format="PTH-GFF", data (base64)
    """
    import base64

    try:
        game_id = _normalize_game(args.get("game", "K1"))
    except ValueError as e:
        return _err(f"writePTH: {e}")

    resref = args.get("resref", "").lower().strip()
    err = _validate_resref(resref, "writePTH")
    if err:
        return _err(err)

    points_raw = args.get("points", [])
    if not isinstance(points_raw, list):
        return _err("writePTH: 'points' must be a list of {x, y, connections: [int,...]}.")

    point_count = len(points_raw)

    # Validate all points first
    validated_points = []
    for i, p in enumerate(points_raw):
        if not isinstance(p, dict):
            return _err(f"writePTH: point[{i}] must be a dict with x, y, connections.")
        try:
            x = float(p.get("x", 0.0))
            y = float(p.get("y", 0.0))
        except (TypeError, ValueError):
            return _err(f"writePTH: point[{i}] x/y must be floats.")
        conns = p.get("connections", [])
        if not isinstance(conns, list):
            return _err(f"writePTH: point[{i}] connections must be a list of int.")
        conn_list = []
        for ci, c in enumerate(conns):
            try:
                idx = int(c)
            except (TypeError, ValueError):
                return _err(f"writePTH: point[{i}] connection[{ci}] must be int.")
            if idx < 0 or idx >= point_count:
                return _err(
                    f"writePTH: point[{i}] connection[{ci}]={idx} out of range "
                    f"(0..{point_count - 1})."
                )
            conn_list.append(idx)
        validated_points.append({"x": x, "y": y, "connections": conn_list})

    # Build a flat connections list and per-point first_connection offset
    # Each point stores how many connections it has (Conections) and the
    # index in the global Path_Conections list where its edges start (First_Conection).
    all_connections: list[int] = []
    for p in validated_points:
        p["_first"] = len(all_connections)
        all_connections.extend(p["connections"])

    connection_count = len(all_connections)

    # ── Build GFF V3.2 binary using our internal GFF3Writer ──────────────────
    from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct, GFFType

    writer = GFF3Writer("PTH ")

    # Path_Points list
    point_structs: list[GFFStruct] = []
    for p in validated_points:
        ps = GFFStruct(0)
        ps.add_float("X", p["x"])
        ps.add_float("Y", p["y"])
        ps.add_dword("Conections", len(p["connections"]))       # BioWare typo — one 'n'
        ps.add_dword("First_Conection", p["_first"])            # BioWare typo — one 'n'
        point_structs.append(ps)

    writer.root.add_list("Path_Points", point_structs)

    # Path_Conections list (all destinations, flat)
    conn_structs: list[GFFStruct] = []
    for dest in all_connections:
        cs = GFFStruct(0)
        cs.add_dword("Destination", dest)
        conn_structs.append(cs)

    writer.root.add_list("Path_Conections", conn_structs)       # BioWare typo

    pth_bytes = writer.build()
    encoded = base64.b64encode(pth_bytes).decode("ascii")

    result: dict = {
        "game": game_id,
        "resref": resref,
        "point_count": point_count,
        "connection_count": connection_count,
        "size_bytes": len(pth_bytes),
        "format": "PTH-GFF",
        "data": encoded,
    }

    # Optionally write to Override
    if args.get("write_override"):
        try:
            rm = _load_rm(game_id)
            override_path = _safe_write_path(rm, resref, "pth")
            Path(override_path).write_bytes(pth_bytes)
            result["wrote_override"] = str(override_path)
        except Exception as ov_err:
            result["override_warning"] = str(ov_err)

    return _ok(result)
