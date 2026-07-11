"""
GhostScripter-K1-K2 — Resource Manager
Handles reading KotOR game archives (BIF / KEY / ERF / RIM).

KEY file format:
  Header → File table → Key table → Resource entries

BIF file format:
  Header → Variable resource table → Fixed resource table → Resource data

This module provides:
  • KeyFile   — parses chitin.key (or other .key files)
  • BifFile   — reads individual .bif archives
  • RimReader — reads .rim files
  • ErfReader — reads .erf / .mod files
  • ResourceManager — top-level game file browser

Resource type IDs sourced from:
  • OldRepublicDevs/PyKotor resource/type.py (ResourceType enum)
  • BioWare swkotor.exe resource type system:
    - GetResTypeFromExtension @ 0x005e6670, @ 0x005e7a40
    - GetResTypeFromFile @ 0x00406650
  Covers all Odyssey engine (KotOR 1 & 2) resource types.

Improvements (open-source tools):
  • cachetools.LRUCache — LRU cache for ResourceManager.read() (avoids
    repeated BIF seeks for hot resources)
  • batch_read() — read multiple resources in a single call
  • cache_info() / clear_cache() — introspect and clear the read cache
  • Full RESTYPE_EXT map covering 80+ types (vs original 25)
"""
from __future__ import annotations

import io
import struct
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, BinaryIO

# ── Optional fast-lookup dependencies ────────────────────────────────────────
try:
    from cachetools import LRUCache as _LRUCache
    _HAS_CACHETOOLS = True
except ImportError:  # pragma: no cover
    _HAS_CACHETOOLS = False

_READ_CACHE_SIZE = 256   # number of resources to keep in memory

log = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────

@dataclass
class ResourceEntry:
    resref: str
    restype: int
    restype_str: str = ""
    source_file: str = ""
    offset: int = 0
    size: int = 0

    @property
    def filename(self) -> str:
        ext = self.restype_str if self.restype_str.startswith(".") else ""
        ext = ext or RESTYPE_EXT.get(self.restype, f".type{self.restype}")
        return f"{self.resref}{ext}"


# Resource type → extension mapping.
# Sourced from OldRepublicDevs/PyKotor ResourceType enum (resource/type.py)
# and verified against BioWare swkotor.exe resource type system.
# Covers every type used by KotOR 1 & 2 (Odyssey engine).
RESTYPE_EXT: Dict[int, str] = {
    # Standard BioWare types (IDs 0-999)
    0:    ".res",   # Generic GFF save data
    1:    ".bmp",   # Windows bitmap
    3:    ".tga",   # Truevision TARGA texture
    4:    ".wav",   # Waveform audio
    6:    ".plt",   # Packed layer texture
    7:    ".ini",   # Configuration (INI text)
    8:    ".bmu",   # BMU audio (MP3 with header)
    9:    ".mpg",   # MPEG video
    10:   ".txt",   # Raw text
    11:   ".wma",   # Windows Media Audio (K1 only)
    12:   ".wmv",   # Windows Media Video
    13:   ".xmv",   # Xbox video
    # Aurora/Odyssey engine types (IDs 2000-2999)
    2000: ".plh",   # Model (placeholder)
    2001: ".tex",   # Texture
    2002: ".mdl",   # BioWare model geometry
    2003: ".thg",   # (unused)
    2005: ".fnt",   # Font
    2007: ".lua",   # LUA script source
    2008: ".slt",   # (unused)
    2009: ".nss",   # NWScript source
    2010: ".ncs",   # NWScript bytecode (compiled)
    2011: ".mod",   # Module ERF archive
    2012: ".are",   # Static area data (GFF)
    2013: ".set",   # Tileset
    2014: ".ifo",   # Module information (GFF)
    2015: ".bic",   # Character data (GFF)
    2016: ".wok",   # Walk mesh
    2017: ".2da",   # Two-dimensional array table
    2018: ".tlk",   # Talk table (localised strings)
    2022: ".txi",   # Texture information (plaintext)
    2023: ".git",   # Dynamic area data (GFF)
    2024: ".bti",   # Item template BioWare (GFF)
    2025: ".uti",   # Item template user (GFF)
    2026: ".btc",   # Creature template BioWare (GFF)
    2027: ".utc",   # Creature template user (GFF)
    2029: ".dlg",   # Dialogue tree (GFF)
    2030: ".itp",   # Toolset palette (GFF)
    2031: ".btt",   # Trigger template BioWare (GFF)
    2032: ".utt",   # Trigger template user (GFF)
    2033: ".dds",   # DirectDraw Surface texture
    2034: ".bts",   # Sound template BioWare (GFF)
    2035: ".uts",   # Sound template user (GFF)
    2036: ".ltr",   # Letter combo probability
    2037: ".gff",   # Generic GFF
    2038: ".fac",   # Faction information (GFF)
    2039: ".bte",   # Encounter template BioWare (GFF)
    2040: ".ute",   # Encounter template user (GFF)
    2041: ".btd",   # Door template BioWare (GFF)
    2042: ".utd",   # Door template user (GFF)
    2043: ".btp",   # Placeable template BioWare (GFF)
    2044: ".utp",   # Placeable template user (GFF)
    2045: ".dft",   # Default values
    2046: ".gic",   # Game instance comments (GFF)
    2047: ".gui",   # GUI definition (GFF)
    2048: ".css",   # Conditional script source
    2049: ".ccs",   # Conditional compiled script
    2050: ".btm",   # Store template BioWare (GFF)
    2051: ".utm",   # Store template user (GFF)
    2052: ".dwk",   # Door walk mesh
    2053: ".pwk",   # Placeable walk mesh
    2054: ".btg",   # Random item generator BioWare (GFF)
    2055: ".utg",   # Random item generator user (GFF)
    2056: ".jrl",   # Journal data (GFF)
    2057: ".sav",   # Game save (ERF)
    2058: ".utw",   # Waypoint template (GFF)
    2059: ".4pc",   # 16-bit RGBA texture (KotOR)
    2060: ".ssf",   # Sound Set File
    2061: ".hak",   # Resource hak pak (ERF, K1 only)
    2062: ".nwm",   # NWN campaign module (ERF)
    2063: ".bik",   # Bink video
    2064: ".ndb",   # Script debugger file
    2065: ".ptm",   # Plot manager (GFF)
    2066: ".ptt",   # Plot wizard template (GFF)
    # Odyssey engine extended types (IDs 3000-3999)
    3000: ".lyt",   # Area layout (plaintext)
    3001: ".vis",   # Area visibility (plaintext)
    3002: ".rim",   # RIM archive
    3003: ".pth",   # Pathfinding data (GFF)
    3004: ".lip",   # Lip sync data
    3005: ".bwm",   # Walk mesh (Odyssey)
    3006: ".txb",   # Texture (binary)
    3007: ".tpc",   # Texture (KotOR compressed)
    3008: ".mdx",   # Model mesh data
    3009: ".rsv",   # (reserved)
    3010: ".sig",   # (reserved)
    3011: ".mab",   # Material binary
    3012: ".qst2",  # Quest (GFF, TSL)
    3013: ".sto",   # (GFF, TSL)
    3015: ".hex",   # Hex grid
    3016: ".mdx2",  # Model mesh data v2
    3017: ".txb2",  # Texture v2
    3022: ".fsm",   # Finite State Machine
    3023: ".art",   # Area environment settings (INI, TSL)
    3024: ".amp",   # Brightening control
    3025: ".cwa",   # Crowd attributes (GFF)
    3028: ".bip",   # Lip sync binary
}

EXT_RESTYPE: Dict[str, int] = {v: k for k, v in RESTYPE_EXT.items()}
# PyKotor exposes both historical spellings for type 2045.  DFT is the
# canonical display extension, while DTF must remain accepted as an alias.
EXT_RESTYPE[".dtf"] = 2045


# ── KEY / BIF reader ──────────────────────────────────────────

class KeyFile:
    """
    Parses a KotOR chitin.key file.
    Builds a registry of {resref.ext → (bif_index, res_id)}.
    """

    def __init__(self):
        self.bif_paths: List[str] = []
        self.entries: List[ResourceEntry] = []
        self._by_name: Dict[str, ResourceEntry] = {}

    def load(self, key_path: Path) -> bool:
        try:
            with open(key_path, "rb") as f:
                self._parse(f, key_path.parent)
            log.info(f"KEY loaded: {len(self.entries)} resources, "
                     f"{len(self.bif_paths)} BIFs")
            return True
        except Exception as e:
            log.error(f"KEY parse error: {e}")
            return False

    def _parse(self, f: BinaryIO, base_dir: Path):
        # Header
        file_type    = f.read(4)
        file_version = f.read(4)
        bif_count    = struct.unpack("<I", f.read(4))[0]
        key_count    = struct.unpack("<I", f.read(4))[0]
        off_file_table = struct.unpack("<I", f.read(4))[0]
        off_key_table  = struct.unpack("<I", f.read(4))[0]
        build_year   = struct.unpack("<I", f.read(4))[0]
        build_day    = struct.unpack("<I", f.read(4))[0]
        f.read(32)  # reserved

        # BIF file table
        f.seek(off_file_table)
        bif_table = []
        for _ in range(bif_count):
            file_size   = struct.unpack("<I", f.read(4))[0]
            name_offset = struct.unpack("<I", f.read(4))[0]
            name_size   = struct.unpack("<H", f.read(2))[0]
            drives      = struct.unpack("<H", f.read(2))[0]
            bif_table.append((file_size, name_offset, name_size))

        for file_size, name_offset, name_size in bif_table:
            f.seek(name_offset)
            raw = f.read(name_size)
            path_str = raw.rstrip(b"\x00").decode("ascii", errors="replace")
            path_str = path_str.replace("\\", "/")
            self.bif_paths.append(str(base_dir / path_str))

        # Key table
        f.seek(off_key_table)
        for _ in range(key_count):
            resref_raw = f.read(16)
            resref = resref_raw.rstrip(b"\x00").decode("ascii", errors="replace")
            restype = struct.unpack("<H", f.read(2))[0]
            res_id  = struct.unpack("<I", f.read(4))[0]
            bif_idx = (res_id >> 20) & 0xFFF
            bif_res_idx = res_id & 0xFFFFF

            entry = ResourceEntry(
                resref=resref,
                restype=restype,
                restype_str=RESTYPE_EXT.get(restype, ""),
                source_file=self.bif_paths[bif_idx] if bif_idx < len(self.bif_paths) else "",
                offset=bif_res_idx,   # stores res_index in BIF for lookup
            )
            self.entries.append(entry)
            self._by_name[entry.filename.lower()] = entry

    def find(self, filename: str) -> ResourceEntry | None:
        return self._by_name.get(filename.lower())

    def search(self, pattern: str) -> List[ResourceEntry]:
        pat = pattern.lower()
        return [e for e in self.entries if pat in e.resref.lower()]

    def by_type(self, restype: int) -> List[ResourceEntry]:
        return [e for e in self.entries if e.restype == restype]


class BifFile:
    """
    Reads resource data from a .bif archive.
    """

    def __init__(self, bif_path: Path):
        self.path = bif_path
        self._entries: List[Tuple[int, int, int]] = []  # (id, offset, size)
        self._loaded = False

    def load(self) -> bool:
        try:
            with open(self.path, "rb") as f:
                file_type = f.read(4)
                version   = f.read(4)
                var_count = struct.unpack("<I", f.read(4))[0]
                fix_count = struct.unpack("<I", f.read(4))[0]
                var_table_offset = struct.unpack("<I", f.read(4))[0]

                f.seek(var_table_offset)
                for _ in range(var_count):
                    res_id  = struct.unpack("<I", f.read(4))[0]
                    offset  = struct.unpack("<I", f.read(4))[0]
                    size    = struct.unpack("<I", f.read(4))[0]
                    restype = struct.unpack("<I", f.read(4))[0]
                    idx = res_id & 0xFFFFF
                    self._entries.append((idx, offset, size))

            self._loaded = True
            return True
        except Exception as e:
            log.error(f"BIF load error {self.path}: {e}")
            return False

    def read_resource(self, res_index: int) -> bytes | None:
        if not self._loaded:
            self.load()
        for idx, offset, size in self._entries:
            if idx == res_index:
                try:
                    with open(self.path, "rb") as f:
                        f.seek(offset)
                        return f.read(size)
                except Exception as e:
                    log.error(f"BIF read error: {e}")
                    return None
        return None


# ── ERF Reader ────────────────────────────────────────────────

class ErfReader:
    """Reads .erf / .mod / .rim ERF-format archives."""

    def __init__(self, erf_path: Path):
        self.path = erf_path
        self.entries: List[ResourceEntry] = []
        self._offsets: Dict[str, Tuple[int, int]] = {}  # filename → (offset, size)

    def load(self) -> bool:
        try:
            with open(self.path, "rb") as f:
                file_type = f.read(4)
                version   = f.read(4)
                _         = f.read(4)   # lang count
                _         = f.read(4)   # localized string size
                entry_count = struct.unpack("<I", f.read(4))[0]
                off_local   = struct.unpack("<I", f.read(4))[0]
                off_key     = struct.unpack("<I", f.read(4))[0]
                off_res     = struct.unpack("<I", f.read(4))[0]
                f.read(32 + 4 * 10 + 4)  # remainder of header

                f.seek(off_key)
                keys = []
                for _ in range(entry_count):
                    resref  = f.read(16).rstrip(b"\x00").decode("ascii", "replace")
                    res_id  = struct.unpack("<I", f.read(4))[0]
                    restype = struct.unpack("<H", f.read(2))[0]
                    f.read(2)  # unused
                    keys.append((resref, restype))

                f.seek(off_res)
                resources = []
                for _ in range(entry_count):
                    offset = struct.unpack("<I", f.read(4))[0]
                    size   = struct.unpack("<I", f.read(4))[0]
                    resources.append((offset, size))

                for i, (resref, restype) in enumerate(keys):
                    offset, size = resources[i]
                    entry = ResourceEntry(
                        resref=resref,
                        restype=restype,
                        restype_str=RESTYPE_EXT.get(restype, ""),
                        source_file=str(self.path),
                        offset=offset,
                        size=size,
                    )
                    self.entries.append(entry)
                    self._offsets[entry.filename.lower()] = (offset, size)
            return True
        except Exception as e:
            log.error(f"ERF read error {self.path}: {e}")
            return False

    def read(self, filename: str) -> bytes | None:
        info = self._offsets.get(filename.lower())
        if not info:
            return None
        offset, size = info
        try:
            with open(self.path, "rb") as f:
                f.seek(offset)
                return f.read(size)
        except Exception as e:
            log.error(f"ERF read data error: {e}")
            return None


class RimReader:
    """Reads .rim files (a simpler ERF-like format)."""

    def __init__(self, rim_path: Path):
        self.path = rim_path
        self.entries: List[ResourceEntry] = []
        self._offsets: Dict[str, Tuple[int, int]] = {}

    def load(self) -> bool:
        try:
            with open(self.path, "rb") as f:
                file_type = f.read(4)   # "RIM "
                version   = f.read(4)   # "V1.0"
                f.read(4)               # reserved
                entry_count = struct.unpack("<I", f.read(4))[0]
                off_entries = struct.unpack("<I", f.read(4))[0]

                f.seek(off_entries)
                for _ in range(entry_count):
                    resref  = f.read(16).rstrip(b"\x00").decode("ascii", "replace")
                    restype = struct.unpack("<I", f.read(4))[0]
                    res_id  = struct.unpack("<I", f.read(4))[0]
                    offset  = struct.unpack("<I", f.read(4))[0]
                    size    = struct.unpack("<I", f.read(4))[0]

                    entry = ResourceEntry(
                        resref=resref,
                        restype=restype,
                        restype_str=RESTYPE_EXT.get(restype, ""),
                        source_file=str(self.path),
                        offset=offset,
                        size=size,
                    )
                    self.entries.append(entry)
                    self._offsets[entry.filename.lower()] = (offset, size)
            return True
        except Exception as e:
            log.error(f"RIM read error {self.path}: {e}")
            return False

    def read(self, filename: str) -> bytes | None:
        info = self._offsets.get(filename.lower())
        if not info:
            return None
        offset, size = info
        try:
            with open(self.path, "rb") as f:
                f.seek(offset)
                return f.read(size)
        except Exception as e:
            log.error(f"RIM read data error: {e}")
            return None


# ── Resource Manager ─────────────────────────────────────────

class ResourceManager:
    """
    Top-level game resource browser.
    Aggregates KEY/BIF files + Override folder from a KotOR installation.
    Priority: Override files > root resources > ERF/MOD files > KEY/BIF archives.
    """

    def __init__(self):
        self._key: KeyFile | None = None
        self._bifs: Dict[str, BifFile] = {}
        self._erfs: List[ErfReader] = []
        self._rims: List[RimReader] = []
        # Archive lookup indexes are rebuilt whenever an ERF/MOD/RIM is added.
        # They preserve the same precedence used by ``read`` while avoiding a
        # linear scan through every module archive for each resource request.
        self._archive_by_name: Dict[str, ErfReader | RimReader] = {}
        self._archive_entries_by_type: Dict[int, List[ResourceEntry]] = {}
        # Module capsules need a second, contextual index.  Many unrelated
        # capsules contain a resource literally named ``module.ifo``; a flat
        # filename lookup cannot distinguish them safely.  Keys are archive
        # basenames with the retail sidecar suffixes removed (``_s`` and
        # ``_dlg``), and readers remain in engine precedence order:
        # MOD replacement, dialogue ERF, then retail RIMs.
        self._module_archives: Dict[str, List[ErfReader | RimReader]] = {}
        self._override_files: Dict[str, Path] = {}  # filename.lower() -> path
        # Root-level resource files are separate from Override.  In retail
        # installs dialog.tlk lives beside chitin.key rather than in a BIF.
        self._root_files: Dict[str, Path] = {}
        self._game_dir: Path | None = None
        self._loaded = False
        # LRU read cache: filename.lower() → bytes
        # Avoids repeated BIF seeks for frequently-read resources (e.g.
        # appearance.2da, globalcat.2da accessed on every project open).
        if _HAS_CACHETOOLS:
            self._read_cache: _LRUCache = _LRUCache(maxsize=_READ_CACHE_SIZE)
        else:
            self._read_cache = None  # type: ignore[assignment]

    def load_game(self, game_dir: Path) -> bool:
        """Load a KotOR game installation directory.

        Falls back to override-only mode if chitin.key is absent.
        This supports modding workspaces and partial installations where
        the modder has only an override folder and no full game installed
        at that path.

        Returns False if *game_dir* does not exist.
        """
        game_dir = Path(game_dir)
        if not game_dir.exists():
            log.warning(f"load_game: path does not exist — {game_dir}")
            return False

        # A ResourceManager instance can be reused for another installation.
        # Do not retain archives, BIF handles, or cached bytes from the previous
        # game path.
        self._key = None
        self._bifs.clear()
        self._erfs.clear()
        self._rims.clear()
        self._archive_by_name.clear()
        self._archive_entries_by_type.clear()
        self._module_archives.clear()
        self._override_files.clear()
        self._root_files.clear()
        self.clear_cache()

        key_path = game_dir / "chitin.key"
        self._game_dir = game_dir

        # The game talk table is a live, installation-specific root resource.
        # Index TLKs case-insensitively so ARE/IFO LocStrings can be resolved
        # without a bundled or guessed name table.
        try:
            for fpath in game_dir.iterdir():
                if fpath.is_file() and fpath.suffix.casefold() == ".tlk":
                    self._root_files[fpath.name.casefold()] = fpath
        except OSError as exc:
            log.warning("Could not scan root TLK files in %s: %s", game_dir, exc)

        if key_path.exists():
            self._key = KeyFile()
            ok = self._key.load(key_path)
            if not ok:
                log.warning(f"chitin.key found but failed to load in {game_dir}")
                # Continue in override-only mode
            else:
                log.info(f"Game loaded: {game_dir} ({len(self._key.entries)} resources)")
        else:
            log.warning(
                f"chitin.key not found in {game_dir} — override-only mode. "
                f"Only files in the override/ folder will be accessible."
            )

        # Always scan the override folder (highest priority, always available)
        override_dir = game_dir / "override"
        if override_dir.exists():
            for fpath in override_dir.iterdir():
                if fpath.is_file():
                    self._override_files[fpath.name.lower()] = fpath
            log.info(f"Override folder: {len(self._override_files)} files")
        else:
            # Also scan the directory itself as a flat workspace
            # (useful when the path IS the override directory)
            if game_dir.is_dir():
                for fpath in game_dir.iterdir():
                    if fpath.is_file():
                        self._override_files[fpath.name.lower()] = fpath
            if self._override_files:
                log.info(
                    f"Flat workspace mode: {len(self._override_files)} files in {game_dir}"
                )

        self._loaded = True

        # Load module archives.  Retail K1 stores area data in paired RIMs;
        # retail K2 additionally stores dialogue in *_dlg.erf archives.  Mods
        # commonly replace those with .mod (ERF-format) archives.  ERF/MOD
        # readers are kept ahead of RIM readers, so a .mod replacement wins
        # over the corresponding retail .rim while Override remains highest.
        modules_dir = self._find_child_dir(game_dir, "modules")
        module_archive_count = 0
        if modules_dir is not None:
            try:
                module_paths = sorted(
                    (
                        p for p in modules_dir.iterdir()
                        if p.is_file() and p.suffix.lower() in {".mod", ".erf", ".rim"}
                    ),
                    key=lambda p: (
                        {".mod": 0, ".erf": 1, ".rim": 2}[p.suffix.lower()],
                        p.name.lower(),
                    ),
                )
            except OSError as exc:
                log.warning("Could not scan module directory %s: %s", modules_dir, exc)
                module_paths = []

            for archive_path in module_paths:
                if archive_path.suffix.lower() == ".rim":
                    reader = RimReader(archive_path)
                    if reader.load():
                        self._rims.append(reader)
                        self._register_module_archive(archive_path, reader)
                        module_archive_count += 1
                else:
                    reader = ErfReader(archive_path)
                    if reader.load():
                        self._erfs.append(reader)
                        self._register_module_archive(archive_path, reader)
                        module_archive_count += 1

            if module_archive_count:
                log.info(
                    "Module archives loaded: %d (%d ERF/MOD, %d RIM)",
                    module_archive_count,
                    len(self._erfs),
                    len(self._rims),
                )

        # Scan KotOR 2 texture pack ERFs (TexturePacks/swpc_tex_tp[a-d].erf).
        # These contain .tpc textures that are not in chitin.key.
        tex_pack_dir = game_dir / "TexturePacks"
        if tex_pack_dir.exists():
            for tpa_name in ("swpc_tex_tpa.erf", "swpc_tex_tpb.erf",
                             "swpc_tex_tpc.erf", "swpc_tex_tpd.erf"):
                erf_path = tex_pack_dir / tpa_name
                if erf_path.exists():
                    reader = ErfReader(erf_path)
                    if reader.load():
                        self._erfs.append(reader)
                        log.info(f"Texture pack loaded: {tpa_name} ({len(reader.entries)} entries)")

        self._rebuild_archive_index()

        return True  # Always succeed; caller can check is_loaded + has_full_install

    @staticmethod
    def _find_child_dir(parent: Path, child_name: str) -> Path | None:
        """Return a direct child directory using a case-insensitive match.

        Windows game installs commonly use ``Modules``/``TexturePacks`` while
        Linux installs and test fixtures may use lowercase names.  The direct
        path handles the common case without scanning.
        """
        direct = parent / child_name
        if direct.is_dir():
            return direct
        try:
            wanted = child_name.casefold()
            return next(
                (p for p in parent.iterdir() if p.is_dir() and p.name.casefold() == wanted),
                None,
            )
        except OSError:
            return None

    def _rebuild_archive_index(self) -> None:
        """Index loaded archives in read-precedence order.

        Explicit/installed ERF and MOD archives precede RIM archives, matching
        KotOR's use of .mod replacements for retail module RIMs.  Within each
        group, the first loaded archive wins.  Override is indexed separately
        and remains the absolute highest-precedence source.
        """
        self._archive_by_name.clear()
        self._archive_entries_by_type.clear()

        for reader in [*self._erfs, *self._rims]:
            for entry in reader.entries:
                filename = entry.filename.lower()
                # Every module capsule uses the same generic ``module.ifo``
                # filename.  Exposing the first one from a global installation
                # scan would return unrelated metadata for whichever module was
                # requested.  Module IFOs require capsule/module context and are
                # therefore intentionally omitted from the flat global index.
                if filename == "module.ifo":
                    continue
                if filename in self._archive_by_name:
                    continue
                self._archive_by_name[filename] = reader
                self._archive_entries_by_type.setdefault(entry.restype, []).append(entry)

    @staticmethod
    def _module_id_from_archive_path(archive_path: Path) -> str:
        """Derive a module id from a live capsule filename.

        KotOR retail modules use ``<id>.rim`` plus ``<id>_s.rim`` and, in
        K2, commonly ``<id>_dlg.erf``.  A MOD replacement uses
        ``<id>.mod``.  Only these documented sidecar suffixes are removed;
        no display-name catalogue or guessed alias is involved.
        """
        module_id = archive_path.stem.casefold()
        for suffix in ("_dlg", "_s"):
            if module_id.endswith(suffix):
                module_id = module_id[: -len(suffix)]
                break
        return module_id

    def _register_module_archive(
        self,
        archive_path: Path,
        reader: ErfReader | RimReader,
        *,
        module_id: str | None = None,
        prepend: bool = False,
    ) -> None:
        """Associate a loaded capsule with its module context."""
        key = (module_id or self._module_id_from_archive_path(archive_path)).casefold()
        if not key:
            return
        readers = self._module_archives.setdefault(key, [])
        if reader in readers:
            return
        if prepend:
            readers.insert(0, reader)
        else:
            readers.append(reader)

    @property
    def module_ids(self) -> tuple[str, ...]:
        """Module ids derived from capsule filenames in the loaded install."""
        return tuple(sorted(self._module_archives))

    def module_sources(self, module_id: str) -> List[Path]:
        """Return the live capsule paths associated with *module_id*.

        The order is the same precedence used by :meth:`read_from_module`.
        An empty list means that no matching capsule was discovered.
        """
        key = self._normalize_module_id(module_id)
        return [reader.path for reader in self._module_archives.get(key, [])]

    @classmethod
    def _normalize_module_id(cls, module_id: str) -> str:
        value = Path(str(module_id).strip()).name.casefold()
        for extension in (".mod", ".rim", ".erf"):
            if value.endswith(extension):
                value = value[: -len(extension)]
                break
        for suffix in ("_dlg", "_s"):
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value

    def module_ids_for_resource(self, filename: str) -> tuple[str, ...]:
        """Return every live module capsule containing *filename*.

        This supports area-resref lookups without assuming that an area and
        its capsule share a name.  Callers must reject or explicitly resolve
        multiple matches instead of choosing the first archive.
        """
        filename_lc = filename.casefold()
        matches = []
        for module_id, readers in self._module_archives.items():
            if any(reader.read(filename_lc) is not None for reader in readers):
                matches.append(module_id)
        return tuple(sorted(matches))

    def read_from_module(self, module_id: str, filename: str) -> bytes | None:
        """Read *filename* using an explicit module capsule context.

        ``module.ifo`` is resolved only from capsules associated with the
        requested module.  It never falls through to a generic Override or
        unrelated archive.  Other resources retain normal Override priority,
        then use only the requested module's capsules, followed by KEY/BIF
        base-game data when applicable.
        """
        key = self._normalize_module_id(module_id)
        requested = str(filename).strip().casefold()
        if not key or not requested or "/" in requested or "\\" in requested:
            return None

        cache_key = f"module:{key}:{requested}"
        if self._read_cache is not None:
            cached = self._read_cache.get(cache_key)
            if cached is not None:
                return cached

        data: bytes | None = None
        is_generic_ifo = requested == "module.ifo"

        # A loose generic module.ifo has no trustworthy association with the
        # requested capsule.  Non-generic resources still honour Override.
        if not is_generic_ifo:
            override = self._override_files.get(requested)
            if override is not None:
                try:
                    data = override.read_bytes()
                except OSError as exc:
                    log.error("Override read error %s: %s", override, exc)

        if data is None:
            for reader in self._module_archives.get(key, []):
                data = reader.read(requested)
                if data is not None:
                    break

        # Generic IFOs are meaningful only inside the selected capsule.
        if data is None and not is_generic_ifo:
            data = self._read_key_bif(requested)

        if data is not None and self._read_cache is not None:
            self._read_cache[cache_key] = data
        return data

    @property
    def has_full_install(self) -> bool:
        """True if chitin.key was loaded (full game install), False for override-only."""
        return self._key is not None and bool(self._key.entries)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def list_by_type(self, ext: str) -> List[ResourceEntry]:
        """List all resources of a given extension (e.g. '.mdl', '.2da').

        Works in both full-install and override-only mode.
        """
        ext_clean = ext.lstrip(".").lower()
        # EXT_RESTYPE keys are dot-prefixed (e.g. '.2da', '.nss') — look up both forms
        restype = EXT_RESTYPE.get(f".{ext_clean}", EXT_RESTYPE.get(ext_clean, -1))

        results: List[ResourceEntry] = []
        seen_filenames: set[str] = set()

        # From override files (always highest priority)
        for fname, fpath in self._override_files.items():
            name_ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
            if name_ext == ext_clean:
                resref = fname[: -(len(ext_clean) + 1)]
                entry = ResourceEntry(
                    resref=resref,
                    restype=restype,
                    restype_str=f".{ext_clean}",
                    source_file=str(fpath),
                    offset=0,
                    size=fpath.stat().st_size,
                )
                seen_filenames.add(entry.filename.lower())
                results.append(entry)

        # Root-level resources (notably retail dialog.tlk).
        for fname, fpath in self._root_files.items():
            name_ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
            if name_ext == ext_clean and fname not in seen_filenames:
                resref = fname[: -(len(ext_clean) + 1)]
                entry = ResourceEntry(
                    resref=resref,
                    restype=restype,
                    restype_str=f".{ext_clean}",
                    source_file=str(fpath),
                    offset=0,
                    size=fpath.stat().st_size,
                )
                seen_filenames.add(entry.filename.lower())
                results.append(entry)

        # From ERF/MOD/RIM archives.  _archive_entries_by_type is already
        # de-duplicated in read-precedence order.
        if restype != -1:
            for entry in self._archive_entries_by_type.get(restype, []):
                filename = entry.filename.lower()
                if filename not in seen_filenames:
                    seen_filenames.add(filename)
                    results.append(entry)

        # From chitin.key/BIF archives
        if self._key and restype != -1:
            for entry in self._key.by_type(restype):
                filename = entry.filename.lower()
                if filename not in seen_filenames:
                    seen_filenames.add(filename)
                    results.append(entry)

        return results

    def search(self, pattern: str) -> List[ResourceEntry]:
        """Search every loaded source by resref, honoring read precedence."""
        pat = pattern.lower()
        results: List[ResourceEntry] = []
        seen_filenames: set[str] = set()

        for filename, fpath in self._override_files.items():
            resref = Path(filename).stem
            if pat not in resref.lower():
                continue
            ext = Path(filename).suffix.lower()
            restype = EXT_RESTYPE.get(ext, -1)
            entry = ResourceEntry(
                resref=resref,
                restype=restype,
                restype_str=ext,
                source_file=str(fpath),
                size=fpath.stat().st_size,
            )
            seen_filenames.add(filename)
            results.append(entry)

        for filename, fpath in self._root_files.items():
            resref = Path(filename).stem
            if filename in seen_filenames or pat not in resref.lower():
                continue
            ext = Path(filename).suffix.lower()
            results.append(ResourceEntry(
                resref=resref,
                restype=EXT_RESTYPE.get(ext, -1),
                restype_str=ext,
                source_file=str(fpath),
                size=fpath.stat().st_size,
            ))
            seen_filenames.add(filename)

        for restype_entries in self._archive_entries_by_type.values():
            for entry in restype_entries:
                filename = entry.filename.lower()
                if filename in seen_filenames or pat not in entry.resref.lower():
                    continue
                seen_filenames.add(filename)
                results.append(entry)

        if self._key:
            for entry in self._key.search(pattern):
                filename = entry.filename.lower()
                if filename not in seen_filenames:
                    seen_filenames.add(filename)
                    results.append(entry)

        return results

    def read(self, filename: str) -> bytes | None:
        """
        Read a resource by filename (e.g. 'appearance.2da').
        Priority: Override > root resources > ERF/MOD/RIM > KEY/BIF

        Results are cached in an LRU cache (cachetools) so repeated reads
        of the same resource (e.g. appearance.2da) are served from memory.
        """
        key_lc = filename.lower()

        # Check cache first
        if self._read_cache is not None:
            cached = self._read_cache.get(key_lc)
            if cached is not None:
                return cached

        data = self._read_uncached(filename)

        # Store in cache
        if data is not None and self._read_cache is not None:
            self._read_cache[key_lc] = data

        return data

    def _read_uncached(self, filename: str) -> bytes | None:
        """Internal read without cache."""
        # 1. Override folder (highest priority)
        override = self._override_files.get(filename.lower())
        if override:
            try:
                return override.read_bytes()
            except Exception as e:
                log.error(f"Override read error {override}: {e}")

        # 2. Root-level loose resources (dialog.tlk in retail installs)
        root_file = self._root_files.get(filename.lower())
        if root_file:
            try:
                return root_file.read_bytes()
            except Exception as e:
                log.error(f"Root resource read error {root_file}: {e}")

        # 3. ERF/MOD/RIM archives (pre-indexed in precedence order)
        archive = self._archive_by_name.get(filename.lower())
        if archive is not None:
            data = archive.read(filename)
            if data is not None:
                return data

        # 4. KEY/BIF (base game)
        return self._read_key_bif(filename)

    def _read_key_bif(self, filename: str) -> bytes | None:
        """Read directly from KEY/BIF, bypassing loose/module archives."""
        if not self._key:
            return None

        entry = self._key.find(filename)
        if not entry:
            return None

        bif_path = entry.source_file
        if bif_path not in self._bifs:
            bif = BifFile(Path(bif_path))
            self._bifs[bif_path] = bif

        return self._bifs[bif_path].read_resource(entry.offset)

    def add_erf(self, erf_path: Path, module_id: str | None = None) -> bool:
        """Add an ERF/MOD archive as an override source."""
        reader = ErfReader(erf_path)
        if reader.load():
            self._erfs.insert(0, reader)
            if module_id is not None or Path(erf_path).suffix.casefold() == ".mod":
                self._register_module_archive(
                    Path(erf_path), reader, module_id=module_id, prepend=True,
                )
            self._rebuild_archive_index()
            self.clear_cache()
            return True
        return False

    def add_rim(self, rim_path: Path, module_id: str | None = None) -> bool:
        """Add a RIM archive as a resource source."""
        reader = RimReader(rim_path)
        if reader.load():
            self._rims.insert(0, reader)
            self._register_module_archive(
                Path(rim_path), reader, module_id=module_id, prepend=True,
            )
            self._rebuild_archive_index()
            self.clear_cache()
            return True
        return False

    def extract_to(self, filename: str, dest_dir: Path) -> Path | None:
        """Extract a single resource to dest_dir."""
        data = self.read(filename)
        if data is None:
            log.warning(f"Resource not found: {filename}")
            return None
        dest = dest_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        log.info(f"Extracted: {filename} → {dest}")
        return dest

    # ── Batch / cache helpers ──────────────────────────────────

    def batch_read(self, filenames: Iterable[str]) -> Dict[str, bytes | None]:
        """Read multiple resources in a single call.

        Returns a dict mapping each filename → bytes (or None if not found).
        Useful for loading a set of 2DA files at startup without N separate
        calls.
        """
        return {fn: self.read(fn) for fn in filenames}

    def cache_info(self) -> Dict[str, int]:
        """Return LRU cache statistics (hits, misses, size, maxsize)."""
        if self._read_cache is None:
            return {"available": 0}
        return {
            "size": len(self._read_cache),
            "maxsize": self._read_cache.maxsize,
            "hits": getattr(self._read_cache, "hits", -1),
            "misses": getattr(self._read_cache, "misses", -1),
        }

    def clear_cache(self) -> None:
        """Clear the read cache (e.g. after Override folder changes)."""
        if self._read_cache is not None:
            self._read_cache.clear()
            log.debug("ResourceManager read cache cleared")

    def get_summary(self) -> Dict[str, int]:
        if not self._key:
            return {}
        from collections import Counter
        counts = Counter(e.restype_str for e in self._key.entries)
        if self._override_files:
            # Count override by extension
            for fname in self._override_files:
                ext = Path(fname).suffix.lower()
                counts[ext] = counts.get(ext, 0) + 1
        return dict(sorted(counts.items()))

    def get_game_dir(self) -> Path | None:
        return self._game_dir

    def list_all_types(self) -> List[str]:
        """Return sorted list of all known resource type extensions.

        Useful for building type-filter UI dropdowns — derived from the
        RESTYPE_EXT map which covers all Odyssey engine types.
        """
        return sorted(set(RESTYPE_EXT.values()))

    def get_type_count(self) -> int:
        """Return the number of distinct resource types in the type map."""
        return len(RESTYPE_EXT)

