"""Shared helpers, module-level state, and utility functions for MCP tools.

Imported by all handler sub-modules.  Never import from here back into
tools.py – this module is the *bottom* of the tools-package dependency graph.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, List

import mcp.types as types

log = logging.getLogger("ghostscripter.mcp.tools")

# ─── Installation cache ────────────────────────────────────────────────────────

# Maps "K1" / "K2" -> ResourceManager instance (loaded)
_INSTALLS: dict[str, Any] = {}

# Per-session 2DA parse cache: game_id → {resref: TwoDAFile}
# Populated lazily by _search_resources; invalidated when loadInstallation
# is called with a new path (same game_id).  Cuts searchResources latency
# from O(n×parse) to O(n×dict-lookup) after the first call.
_2DA_CACHE: dict[str, dict[str, Any]] = {}

# ─── Curated default install path candidates ──────────────────────────────────
# Covers common Steam, GOG, disc, Epic, Microsoft Store, and macOS layouts.
# These are discovery candidates, not a claim that every storefront currently
# ships every game at each listed path; chitin.key validation remains mandatory.
# Paths are probed in order; first directory containing chitin.key wins.

_home = os.path.expanduser("~")

_DEFAULT_PATHS: dict[str, list[str]] = {
    "K1": [
        # ── Linux Steam (native + Proton) ──────────────────────────────
        f"{_home}/.local/share/Steam/steamapps/common/swkotor",
        f"{_home}/.steam/steam/steamapps/common/swkotor",
        f"{_home}/.steam/root/steamapps/common/swkotor",
        f"{_home}/.steam/debian-installation/steamapps/common/swkotor",
        "/mnt/sda/SteamLibrary/steamapps/common/swkotor",
        "/mnt/games/SteamLibrary/steamapps/common/swkotor",
        # Flatpak Steam (verified by PyKotor community)
        f"{_home}/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/swkotor",
        # Proton prefix (Wine C:\ drive)
        f"{_home}/.local/share/Steam/steamapps/compatdata/32370/pfx/drive_c/Program Files (x86)/Steam/steamapps/common/swkotor",
        # WSL paths (Windows Subsystem for Linux)
        "/mnt/c/Program Files/Steam/steamapps/common/swkotor",
        "/mnt/c/Program Files (x86)/Steam/steamapps/common/swkotor",
        "/mnt/c/Program Files/LucasArts/SWKotOR",
        "/mnt/c/Program Files (x86)/LucasArts/SWKotOR",
        "/mnt/c/GOG Games/Star Wars - KotOR",
        "/mnt/c/Amazon Games/Library/Star Wars - Knights of the Old",
        # ── macOS Steam ───────────────────────────────────────────────
        f"{_home}/Library/Application Support/Steam/steamapps/common/swkotor",
        f"{_home}/Library/Applications/Steam/steamapps/common/swkotor",
        # macOS .app bundle (Aspyr port — verified path)
        f"{_home}/Library/Application Support/Steam/steamapps/common/swkotor/Knights of the Old Republic.app/Contents/Assets",
        "/Applications/Star Wars- KOTOR.app/Contents/Assets",
        "/Applications/Knights of the Old Republic.app/Contents/Assets",
        # ── Windows Steam ─────────────────────────────────────────────
        "C:/Program Files (x86)/Steam/steamapps/common/swkotor",
        "C:/Program Files/Steam/steamapps/common/swkotor",
        "D:/Steam/steamapps/common/swkotor",
        "D:/SteamLibrary/steamapps/common/swkotor",
        "E:/Steam/steamapps/common/swkotor",
        "E:/SteamLibrary/steamapps/common/swkotor",
        # ── Windows GOG ───────────────────────────────────────────────
        "C:/GOG Games/Star Wars - KotOR",
        "C:/GOG Games/Star Wars KotOR",
        "D:/GOG Games/Star Wars - KotOR",
        # ── Windows LucasArts disc ────────────────────────────────────
        "C:/Program Files/LucasArts/SWKotOR",
        "C:/Program Files (x86)/LucasArts/SWKotOR",
        # ── Windows Amazon Games Store ────────────────────────────────
        "C:/Amazon Games/Library/Star Wars - Knights of the Old",
        # ── Windows Epic Games Store ──────────────────────────────────
        "C:/Program Files/Epic Games/SWKotOR",
        # ── Xbox Game Pass / Microsoft Store ──────────────────────────
        "C:/XboxGames/Star Wars KOTOR/Content",
        f"{os.environ.get('LOCALAPPDATA', 'C:/Users/User/AppData/Local')}/Packages/LucasArtsInc.StarWarsKnightsoftheOldRepub_h7ry3b9x2ndgm/LocalCache/Roaming/SWKotOR",
    ],
    "K2": [
        # ── Linux Steam (native + Proton) ──────────────────────────────
        f"{_home}/.local/share/Steam/steamapps/common/Knights of the Old Republic II",
        f"{_home}/.steam/steam/steamapps/common/Knights of the Old Republic II",
        f"{_home}/.steam/root/steamapps/common/Knights of the Old Republic II",
        f"{_home}/.steam/debian-installation/steamapps/common/Knights of the Old Republic II",
        "/mnt/sda/SteamLibrary/steamapps/common/Knights of the Old Republic II",
        "/mnt/games/SteamLibrary/steamapps/common/Knights of the Old Republic II",
        # Aspyr port saves (K2 has a dedicated Linux-native Aspyr port)
        f"{_home}/.local/share/aspyr-media/kotor2",
        # Flatpak Steam (verified by PyKotor community)
        f"{_home}/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Knights of the Old Republic II/steamassets",
        # Proton prefix
        f"{_home}/.local/share/Steam/steamapps/compatdata/208580/pfx/drive_c/Program Files (x86)/Steam/steamapps/common/Knights of the Old Republic II",
        # WSL paths
        "/mnt/c/Program Files/Steam/steamapps/common/Knights of the Old Republic II",
        "/mnt/c/Program Files (x86)/Steam/steamapps/common/Knights of the Old Republic II",
        "/mnt/c/Program Files/LucasArts/SWKotOR2",
        "/mnt/c/Program Files (x86)/LucasArts/SWKotOR2",
        "/mnt/c/GOG Games/Star Wars - KotOR2",
        # ── macOS Steam ───────────────────────────────────────────────
        f"{_home}/Library/Application Support/Steam/steamapps/common/Knights of the Old Republic II",
        # macOS .app bundle paths (verified by PyKotor community)
        f"{_home}/Library/Application Support/Steam/steamapps/common/Knights of the Old Republic II/Knights of the Old Republic II.app/Contents/Assets",
        f"{_home}/Library/Application Support/Steam/steamapps/common/Knights of the Old Republic II/KOTOR2.app/Contents/GameData",
        f"{_home}/Applications/Knights of the Old Republic 2.app/Contents/Resources/transgaming/c_drive/Program Files/SWKotOR2",
        "/Applications/Knights of the Old Republic 2.app/Contents/Resources/transgaming/c_drive/Program Files/SWKotOR2",
        # ── Windows Steam ─────────────────────────────────────────────
        "C:/Program Files (x86)/Steam/steamapps/common/Knights of the Old Republic II",
        "C:/Program Files/Steam/steamapps/common/Knights of the Old Republic II",
        "D:/Steam/steamapps/common/Knights of the Old Republic II",
        "D:/SteamLibrary/steamapps/common/Knights of the Old Republic II",
        "E:/Steam/steamapps/common/Knights of the Old Republic II",
        "E:/SteamLibrary/steamapps/common/Knights of the Old Republic II",
        # ── Windows GOG ───────────────────────────────────────────────
        "C:/GOG Games/Star Wars - KotOR II",
        "C:/GOG Games/Star Wars KotOR II",
        "D:/GOG Games/Star Wars - KotOR II",
        # ── Windows LucasArts disc ────────────────────────────────────
        "C:/Program Files/LucasArts/SWKotOR2",
        "C:/Program Files (x86)/LucasArts/SWKotOR2",
        # ── Windows Epic Games Store ──────────────────────────────────
        "C:/Program Files/Epic Games/SWKotOR2",
        # ── Xbox Game Pass / Microsoft Store ──────────────────────────
        "C:/XboxGames/Star Wars KOTOR II/Content",
    ],
}

# Area display names must come from the installed module's ARE Name LocString
# and that installation's dialog.tlk.  An absent or blank live name remains
# unknown; GhostScripter intentionally ships no guessed area-name catalogue.
HARDCODED_MODULE_NAMES: dict[str, str] = {
}


def _probe_windows_registry() -> dict[str, str | None]:
    """Read KotOR install paths from the Windows Registry (Windows-only).

    Returns a dict {game_id: path_or_None}.  Called once at startup on win32;
    results are merged into the env-var / default-path lookup chain.

    Registry keys sourced from PyKotor's tools/registry.py KOTOR_REG_PATHS table
    (cross-referenced against Steam App IDs 32370 and 208580, GOG IDs, and retail
    BioWare/LucasArts disc paths for both 32-bit and 64-bit Windows).
    """
    paths: dict[str, str | None] = {"K1": None, "K2": None}
    if sys.platform != "win32":
        return paths
    try:
        import winreg  # type: ignore[import]
        # Each entry: (hive, subkey, value_name)
        # Ordered: Steam (most common) → GOG → BioWare/LucasArts disc retail
        # Both 64-bit WOW6432Node and 32-bit paths covered for maximum compatibility.
        _REG_ENTRIES = {
            "K1": [
                # Steam (App ID 32370)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 32370",
                 "InstallLocation"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 32370",
                 "InstallLocation"),
                # GOG (product ID 1207666283)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\GOG.com\Games\1207666283", "PATH"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\GOG.com\Games\1207666283", "PATH"),
                # BioWare disc retail (32-bit Windows)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\BioWare\SW\KOTOR", "InternalPath"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\BioWare\SW\KOTOR", "Path"),
                # BioWare disc retail (64-bit Windows — WOW6432Node)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\BioWare\SW\KOTOR", "InternalPath"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\BioWare\SW\KOTOR", "Path"),
            ],
            "K2": [
                # Steam (App ID 208580)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 208580",
                 "InstallLocation"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 208580",
                 "InstallLocation"),
                # GOG (product ID 1421404581)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\GOG.com\Games\1421404581", "PATH"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\GOG.com\Games\1421404581", "PATH"),
                # LucasArts disc retail (32-bit)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\LucasArts\KotOR2", "InternalPath"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\LucasArts\KotOR2", "Path"),
                # LucasArts disc retail (64-bit — WOW6432Node)
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\LucasArts\KotOR2", "InternalPath"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"SOFTWARE\WOW6432Node\LucasArts\KotOR2", "Path"),
            ],
        }
        for game_id, entry_list in _REG_ENTRIES.items():
            for hive, subkey, value_name in entry_list:
                try:
                    with winreg.OpenKey(hive, subkey) as k:
                        val, _ = winreg.QueryValueEx(k, value_name)
                        if val and Path(val).exists():
                            paths[game_id] = str(val)
                            break
                except OSError:
                    continue
    except Exception:
        pass
    return paths


def _auto_load_installations() -> dict[str, str]:
    """Probe all known install locations and load any found game installations.

    Called once at server startup.  Silently skips games not found; logs a
    summary of what was (and wasn't) auto-detected.

    Returns a dict {game_id: path_string} for every game that was loaded.
    """
    from ghostscripter.core.resource_manager import ResourceManager  # late import

    loaded: dict[str, str] = {}

    # Windows Registry entries take highest priority after explicit env vars
    reg_paths = _probe_windows_registry()

    for game_id in ("K1", "K2"):
        if game_id in _INSTALLS:
            log.debug("auto-load: %s already loaded, skipping", game_id)
            continue

        # 1. Explicit env var wins
        env_key = f"{game_id}_PATH"
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            candidate = Path(env_val)
            if candidate.exists():
                try:
                    rm = ResourceManager()
                    rm.load_game(candidate)
                    _INSTALLS[game_id] = rm
                    _2DA_CACHE.pop(game_id, None)
                    loaded[game_id] = str(candidate)
                    log.info("auto-load: %s loaded from env %s=%s", game_id, env_key, candidate)
                    continue
                except Exception as exc:
                    log.warning("auto-load: %s env path failed (%s): %s", game_id, candidate, exc)

        # 2. Windows Registry
        reg_path = reg_paths.get(game_id)
        if reg_path:
            candidate = Path(reg_path)
            if candidate.exists():
                try:
                    rm = ResourceManager()
                    rm.load_game(candidate)
                    _INSTALLS[game_id] = rm
                    _2DA_CACHE.pop(game_id, None)
                    loaded[game_id] = str(candidate)
                    log.info("auto-load: %s loaded from registry: %s", game_id, candidate)
                    continue
                except Exception as exc:
                    log.warning("auto-load: %s registry path failed (%s): %s", game_id, candidate, exc)

        # 3. Walk exhaustive default path list
        for raw in _DEFAULT_PATHS.get(game_id, []):
            candidate = Path(raw)
            if not candidate.exists():
                continue
            # Verify it is a real install: must have chitin.key OR swkotor.exe
            has_key  = (candidate / "chitin.key").exists()
            has_exe  = (candidate / "swkotor.exe").exists() or (candidate / "swkotor2.exe").exists()
            if not (has_key or has_exe):
                continue
            try:
                rm = ResourceManager()
                rm.load_game(candidate)
                _INSTALLS[game_id] = rm
                _2DA_CACHE.pop(game_id, None)
                loaded[game_id] = str(candidate)
                log.info("auto-load: %s loaded from default path: %s", game_id, candidate)
                break
            except Exception as exc:
                log.warning("auto-load: %s path %s failed: %s", game_id, candidate, exc)

        if game_id not in _INSTALLS:
            log.info(
                "auto-load: %s not found. Set %s_PATH or call gsLoadInstallation.",
                game_id, game_id,
            )

    return loaded


def _normalize_game(game: str) -> str:
    """Normalize game identifier to 'K1' or 'K2'."""
    g = game.strip().upper()
    if g in ("K1", "KOTOR", "KOTOR1", "KOTORI", "1"):
        return "K1"
    if g in ("K2", "KOTOR2", "KOTORII", "TSL", "2"):
        return "K2"
    raise ValueError(f"Unknown game identifier {game!r}. Use 'K1' or 'K2'.")


def _validate_resref(resref: str, context: str = "") -> str | None:
    """Return an error string if resref is invalid, else None."""
    if not resref or not isinstance(resref, str):
        prefix = f"{context}: " if context else ""
        return f"{prefix}resref must be a non-empty string."
    if len(resref) > 16:
        prefix = f"{context}: " if context else ""
        return f"{prefix}resref {resref!r} exceeds 16 characters (KotOR limit)."
    bad = [c for c in resref if not (c.isascii() and (c.isalnum() or c in "_-"))]
    if bad:
        prefix = f"{context}: " if context else ""
        return f"{prefix}resref {resref!r} contains invalid characters: {bad!r}."
    return None


def _find_game_path(game_id: str) -> Path | None:
    """Look up game path via env var, then common install locations."""
    env_keys = {"K1": "K1_PATH", "K2": "K2_PATH"}
    env_val = os.environ.get(env_keys.get(game_id, ""), "")
    if env_val:
        p = Path(env_val)
        if p.exists():
            return p

    for candidate in _DEFAULT_PATHS.get(game_id, []):
        p = Path(candidate)
        if p.exists():
            return p
    return None


def _load_rm(game_id: str, path: str | None = None):
    """Return a cached ResourceManager for *game_id*, loading if necessary."""
    from ghostscripter.core.resource_manager import ResourceManager  # late import

    if game_id in _INSTALLS and path is None:
        return _INSTALLS[game_id]

    game_path: Path | None = Path(path) if path else _find_game_path(game_id)
    if game_path is None:
        raise FileNotFoundError(
            f"No {game_id} installation found. "
            f"Set {'K1_PATH' if game_id == 'K1' else 'K2_PATH'} environment variable."
        )

    rm = ResourceManager()
    ok = rm.load_game(game_path)
    if not ok and not (game_path / "chitin.key").exists():
        # May be a partial install (override-only modding workspace)
        log.warning(f"No chitin.key in {game_path} — override-only mode")
    _INSTALLS[game_id] = rm
    # Invalidate the 2DA parse cache for this game so searchResources
    # re-reads from the new installation rather than serving stale data.
    _2DA_CACHE.pop(game_id, None)
    log.info(f"Loaded {game_id} from {game_path}")
    return rm


def _ok(data: Any) -> List[types.TextContent]:
    """Wrap *data* in a successful MCP text response."""
    return [types.TextContent(type="text", text=json.dumps(data, indent=2))]


def _err(msg: str) -> List[types.TextContent]:
    """Wrap *msg* in an error MCP text response."""
    return [types.TextContent(type="text", text=json.dumps({"error": msg}))]


def _prune(obj: Any, depth: int) -> Any:
    """Recursively prune nested dicts/lists to *depth* levels."""
    if isinstance(obj, (bytes, bytearray, memoryview)):
        raw = bytes(obj)
        return {"encoding": "hex", "data": raw.hex(), "byte_length": len(raw)}
    if depth <= 0:
        return "..." if isinstance(obj, (dict, list)) else obj
    if isinstance(obj, dict):
        return {k: _prune(v, depth - 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_prune(item, depth - 1) for item in obj]
    return obj


def read_module_resource(rm: Any, module_id: str, filename: str) -> bytes | None:
    """Read a resource without losing its module-capsule association.

    Current ResourceManager instances expose ``read_from_module``.  The
    conservative fallback exists for small test/adapter readers and never
    asks for an ambiguous bare ``module.ifo``.
    """
    contextual_reader = getattr(type(rm), "read_from_module", None)
    if callable(contextual_reader):
        return rm.read_from_module(module_id, filename)
    if filename.casefold() == "module.ifo":
        return rm.read(f"{module_id}.ifo")
    return rm.read(filename)


# ─── Path-safety helpers ──────────────────────────────────────────────────────

# File extensions that writeOverride / writeGFF / writeDLG are permitted to write.
# Keeping this allow-list prevents an LLM from accidentally writing executables,
# config files, or other sensitive paths into the game directory.
_SAFE_WRITE_EXTENSIONS: frozenset[str] = frozenset({
    # NWScript
    "nss", "ncs",
    # GFF-family blueprints
    "utc", "utd", "ute", "uti", "utm", "utp", "uts", "utt", "utw",
    # World / module data
    "are", "git", "ifo", "jrl", "fac", "bic", "pth",
    # Dialogue & 2DA
    "dlg", "2da",
    # Archives
    "erf", "mod", "sav", "rim",
    # Textures & models
    "tga", "tpc", "mdl", "mdx",
    # Misc engine formats
    "txi", "wav", "mp3", "bmu", "lyt", "vis", "wok",
    # Generic GFF
    "gff",
})

# Characters not permitted anywhere in a resref or filename written to disk.
_UNSAFE_PATH_CHARS: frozenset[str] = frozenset({
    "..", "/", "\\", ":", "*", "?", "\"", "<", ">", "|", "\x00",
})


# ─── Shared GFF field-extraction utilities ───────────────────────────────────
#
# These replace the 14+ inline definitions of _v / _locstr scattered across
# handlers_composite.py and handlers_read.py.  All handler files should import
# and use these instead of re-defining them locally.
#
# Usage pattern (in any handler):
#
#   from ghostscripter.mcp.tools_pkg._helpers import gff_scalar, gff_locstr
#
#   raw   = GFFService.parse_bytes(data)
#   root  = raw if isinstance(raw, dict) else (raw.get("fields") or raw)
#   tag   = gff_scalar(root, "Tag")
#   name  = gff_locstr(root, "FirstName")
#   name  = gff_locstr(root, "FirstName", rm=rm)   # TLK fallback when rm given

def gff_scalar(root: dict, key: str, default: Any = None) -> Any:
    """Extract a plain scalar from a parsed GFF field dict.

    GFFService may return field values either as raw Python scalars or as
    ``{"value": ...}`` dicts (for typed fields).  This function unwraps either
    form transparently.

    Parameters
    ----------
    root:
        The top-level field dict returned by ``GFFService.parse_bytes()``.
    key:
        GFF field label (case-sensitive, as stored in the binary).
    default:
        Value to return when the key is absent.
    """
    val = root.get(key, default)
    return val.get("value", val) if isinstance(val, dict) else val


def gff_locstr(
    root: dict,
    key: str,
    rm: Any = None,
    include_tlk: bool = True,
) -> str | None:
    """Extract the most useful text from a CExoLocString GFF field.

    Resolution order:
      1. Plain string value stored directly.
      2. Sub-key ``"0"`` (language 0 = English), then ``0``, then ``"value"``.
      3. TLK strref lookup via ``rm.read("dialog.tlk")`` when *rm* is given
         and *include_tlk* is True.

    Parameters
    ----------
    root:
        The top-level field dict returned by ``GFFService.parse_bytes()``.
    key:
        GFF field label.
    rm:
        ResourceManager (or compatible) instance used for TLK lookup.
        Pass ``None`` to skip TLK resolution.
    include_tlk:
        Guard flag — set False to skip TLK resolution even when *rm* is given.

    Returns ``None`` when no text could be resolved.
    """
    entry = root.get(key)
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry or None
    # The read-only GFF3Reader representation is ``(strref, english_text)``.
    # Preserve an embedded substring first, then resolve the live TLK below.
    if isinstance(entry, (tuple, list)) and len(entry) >= 2:
        embedded = entry[1]
        if isinstance(embedded, str) and embedded:
            return embedded
        entry = {"strref": entry[0]}
    if isinstance(entry, dict):
        for sub_key in ("0", 0, "value"):
            v = entry.get(sub_key)
            if isinstance(v, str) and v:
                return v
        # Lossless typed GFF documents nest LocString data under ``value``.
        typed_value = entry.get("value")
        if isinstance(typed_value, dict):
            substrings = typed_value.get("substrings", {})
            if isinstance(substrings, dict):
                for sub_key in ("0", 0, "1", 1):
                    v = substrings.get(sub_key)
                    if isinstance(v, str) and v:
                        return v
        # TLK strref fallback
        if include_tlk and rm is not None:
            strref = entry.get("strref", entry.get("StrRef"))
            if strref is None and isinstance(typed_value, dict):
                strref = typed_value.get("stringref", typed_value.get("strref"))
            if strref is not None:
                try:
                    strref = int(strref)
                except (TypeError, ValueError):
                    strref = None
            if strref is not None and strref >= 0:
                try:
                    from ghostscripter.core.services import TLKService  # late import
                    tlk_bytes = rm.read("dialog.tlk")
                    if tlk_bytes:
                        tlk = TLKService.parse_bytes(tlk_bytes, "dialog.tlk")
                        result = TLKService.lookup(tlk, [strref])
                        # TLKService.lookup returns an ordered list.  Retain
                        # compatibility with older dict-shaped adapters.
                        if isinstance(result, list):
                            text = result[0].get("text") if result else None
                        else:
                            text = result.get(strref, {}).get("text")
                        if text:
                            return text
                except Exception:
                    pass
    return None


def gff_resref(root: dict, key: str) -> str:
    """Extract a ResRef string (always a plain scalar or empty string)."""
    val = gff_scalar(root, key)
    return str(val) if val is not None else ""


def gff_int(root: dict, key: str, default: int = 0) -> int:
    """Extract an integer GFF field, returning *default* on failure."""
    val = gff_scalar(root, key)
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def gff_float(root: dict, key: str, default: float = 0.0) -> float:
    """Extract a float GFF field, returning *default* on failure."""
    val = gff_scalar(root, key)
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def gff_list(root: dict, key: str) -> list:
    """Extract a GFF list field, always returning a list (never None)."""
    val = root.get(key)
    if isinstance(val, list):
        return val
    return []


def gff_struct_fields(struct_entry: Any) -> dict:
    """Unwrap a GFF struct entry to its fields dict.

    GFFService sometimes wraps struct entries as ``{"fields": {...}}`` and
    sometimes returns the field dict directly.  This helper normalises both.
    """
    if isinstance(struct_entry, dict):
        return struct_entry.get("fields") or struct_entry
    return {}


def _safe_write_path(resref: str, restype: str, context: str = "") -> str | None:
    """Validate that *resref* + *restype* are safe to write to the Override folder.

    Returns an error string on failure, or None on success.

    Checks:
      1. resref passes _validate_resref (max 16 chars, alnum/_ /-)
      2. restype is in _SAFE_WRITE_EXTENSIONS
      3. Neither string contains path-traversal characters
    """
    prefix = f"{context}: " if context else ""

    # 1. Validate resref
    err = _validate_resref(resref, context)
    if err:
        return err

    # 2. Check extension allow-list
    ext = restype.lower().lstrip(".")
    if ext not in _SAFE_WRITE_EXTENSIONS:
        return (
            f"{prefix}file type '{ext}' is not in the permitted write extension list. "
            f"Allowed: {sorted(_SAFE_WRITE_EXTENSIONS)}"
        )

    # 3. Path-traversal check on both parts
    for part, label in ((resref, "resref"), (restype, "restype")):
        for bad in _UNSAFE_PATH_CHARS:
            if bad in part:
                return (
                    f"{prefix}{label} {part!r} contains forbidden character {bad!r}."
                )

    return None

