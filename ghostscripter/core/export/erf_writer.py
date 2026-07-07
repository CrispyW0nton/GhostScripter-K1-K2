"""
GhostScripter-K1-K2 — ERF / Override Export Pipeline
Handles writing compiled mod files to:
  • KotOR Override folder (flat copy)
  • ERF archive format (v1.0, used by .mod / .erf)

ERF binary format:
  Header (160 bytes) → Key list → Resource list → Resource data
"""
from __future__ import annotations

import os
import struct
import shutil
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Resource Type IDs (KotOR) ──────────────────────────────────
# Verified against PyKotor's ResourceType enum and the type IDs found in
# retail K1 module RIMs (e.g. danm13_s.rim: 2035=uts, 2042=utd, 2044=utp,
# 2051=utm, 2058=utw).  Matches the read-side table in
# core/resource_manager/resource_manager.py.
RESTYPE_IDS: Dict[str, int] = {
    ".bmp":  1,
    ".tga":  3,
    ".wav":  4,
    ".plt":  6,
    ".ini":  7,
    ".txt":  10,
    ".mdl":  2002,
    ".nss":  2009,
    ".ncs":  2010,
    ".mod":  2011,
    ".are":  2012,
    ".set":  2013,
    ".ifo":  2014,
    ".bic":  2015,
    ".wok":  2016,
    ".2da":  2017,
    ".tlk":  2018,
    ".txi":  2022,
    ".git":  2023,
    ".bti":  2024,
    ".uti":  2025,
    ".btc":  2026,
    ".utc":  2027,
    ".dlg":  2029,
    ".itp":  2030,
    ".btt":  2031,
    ".utt":  2032,
    ".dds":  2033,
    ".bts":  2034,
    ".uts":  2035,
    ".ltr":  2036,
    ".gff":  2037,
    ".fac":  2038,
    ".bte":  2039,
    ".ute":  2040,
    ".btd":  2041,
    ".utd":  2042,
    ".btp":  2043,
    ".utp":  2044,
    ".dft":  2045,
    ".gic":  2046,
    ".gui":  2047,
    ".css":  2048,
    ".ccs":  2049,
    ".btm":  2050,
    ".utm":  2051,
    ".dwk":  2052,
    ".pwk":  2053,
    ".btg":  2054,
    ".utg":  2055,
    ".jrl":  2056,
    ".sav":  2057,
    ".utw":  2058,
    ".4pc":  2059,
    ".ssf":  2060,
    ".hak":  2061,
    ".nwm":  2062,
    ".bik":  2063,
    ".ndb":  2064,
    ".ptm":  2065,
    ".ptt":  2066,
    ".lyt":  3000,
    ".vis":  3001,
    ".rim":  3002,
    ".pth":  3003,
    ".lip":  3004,
    ".bwm":  3005,
    ".txb":  3006,
    ".tpc":  3007,
    ".mdx":  3008,
    ".rsv":  3009,
    ".sig":  3010,
    ".xbx":  25022,
}


@dataclass
class ExportEntry:
    """Single resource to include in the export."""
    resref: str          # filename without extension, max 16 chars
    restype: int         # KotOR resource type ID
    data: bytes          # raw file bytes
    source_path: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> "ExportEntry":
        ext = path.suffix.lower()
        restype = RESTYPE_IDS.get(ext, 0)
        resref = path.stem[:16]
        data = path.read_bytes()
        return cls(resref=resref, restype=restype, data=data, source_path=path)


@dataclass
class ExportResult:
    success: bool
    message: str
    files_exported: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    output_path: Path | None = None


# ── Override Export ────────────────────────────────────────────

class OverrideExporter:
    """
    Copies compiled mod files to the game's Override folder.
    Supports K1 and K2 path conventions.
    """

    K1_OVERRIDE = "override"
    K2_OVERRIDE = "override"

    def export(
        self,
        project,
        game_install_dir: Path,
        file_types: list[str] | None = None,
    ) -> ExportResult:
        """
        Export all eligible project files to <game_install_dir>/override/.
        file_types: list of extensions to include, e.g. ['.ncs', '.dlg', '.2da']
                    If None, exports all known KotOR resource types.
        """
        override_dir = game_install_dir / self.K1_OVERRIDE
        override_dir.mkdir(parents=True, exist_ok=True)

        result = ExportResult(
            success=True,
            message="",
            output_path=override_dir,
        )

        collected = self._collect_files(project, file_types)
        if not collected:
            result.success = False
            result.message = "No files found to export."
            return result

        for src_path, dest_name in collected:
            dest = override_dir / dest_name
            try:
                shutil.copy2(str(src_path), str(dest))
                result.files_exported.append(dest_name)
                log.info(f"Exported → {dest}")
            except Exception as e:
                result.errors.append(f"{dest_name}: {e}")
                log.error(f"Export error {dest_name}: {e}")

        exported = len(result.files_exported)
        errs = len(result.errors)
        result.success = errs == 0
        result.message = (
            f"Exported {exported} file(s) to {override_dir}"
            + (f" ({errs} error(s))" if errs else "")
        )
        return result

    def _collect_files(
        self,
        project,
        file_types: list[str] | None,
    ) -> List[Tuple[Path, str]]:
        """Walk all project subdirs and collect exportable files."""
        pairs = []
        allowed_exts = set(file_types or RESTYPE_IDS.keys())

        dirs_to_scan = []
        for attr in ("script_dir", "dialogue_dir", "quest_dir",
                      "twoda_dir", "texture_dir", "model_dir"):
            d = getattr(project, attr, None)
            if d and Path(d).exists():
                dirs_to_scan.append(Path(d))

        for directory in dirs_to_scan:
            for f in directory.iterdir():
                if f.is_file() and f.suffix.lower() in allowed_exts:
                    pairs.append((f, f.name))
        return pairs


# ── ERF Writer ─────────────────────────────────────────────────

class ERFWriter:
    """
    Builds a binary ERF v1.0 archive.

    ERF Header (160 bytes):
      FileType      [4]   "ERF " / "MOD " / "SAV "
      Version       [4]   "V1.0"
      LanguageCount [4]
      LocalizedStringSize [4]
      EntryCount    [4]
      OffsetToLocalizedString [4]
      OffsetToKeyList [4]
      OffsetToResourceList [4]
      BuildYear     [4]
      BuildDay      [4]
      DescriptionStrRef [4]
      Reserved      [116]
    """

    ERF_HEADER_SIZE = 160
    KEY_ENTRY_SIZE = 24   # 16 resref + 4 id + 2 type + 2 unused
    RES_ENTRY_SIZE = 8    # 4 offset + 4 size

    def __init__(self, file_type: str = "ERF "):
        assert len(file_type) == 4, "file_type must be exactly 4 chars"
        self.file_type = file_type.encode("ascii")
        self._entries: list[ExportEntry] = []   # accumulated via add_resource()

    def add_resource(self, resref: str, ext: str, data: bytes) -> None:
        """
        Accumulate a resource for later build() call.

        Parameters
        ----------
        resref : Resource reference (filename without extension), max 16 chars.
        ext    : Extension without dot, e.g. 'ncs', 'dlg', '2da'.
        data   : Raw binary content.

        Example
        -------
        writer = ERFWriter('MOD ')
        writer.add_resource('k_mira_join', 'ncs', compiled_bytes)
        writer.add_resource('mira_convo',  'dlg', dlg_bytes)
        erf_data = writer.build()
        """
        dot_ext = f".{ext.lower().lstrip('.')}"
        restype = RESTYPE_IDS.get(dot_ext, 0)
        self._entries.append(ExportEntry(
            resref=resref[:16],
            restype=restype,
            data=data,
        ))

    def build(self) -> bytes:
        """
        Build and return the ERF binary from resources added via add_resource().

        Returns raw bytes ready to write to a .mod / .erf file or send over
        a network.  Does not write to disk — use write() for that.
        """
        import io
        entries = self._entries
        return self._build_bytes(entries)

    def _build_bytes(self, entries: list[ExportEntry]) -> bytes:
        """Internal: build ERF binary from a list of ExportEntry objects."""
        from datetime import datetime
        now = datetime.now()
        year = now.year - 1900
        day = now.timetuple().tm_yday - 1

        entry_count = len(entries)
        offset_localized = self.ERF_HEADER_SIZE
        offset_keylist   = offset_localized
        offset_reslist   = offset_keylist  + entry_count * self.KEY_ENTRY_SIZE
        offset_data_start = offset_reslist + entry_count * self.RES_ENTRY_SIZE

        data_offsets = []
        current_offset = offset_data_start
        for entry in entries:
            data_offsets.append(current_offset)
            current_offset += len(entry.data)

        buf = bytearray()

        # Header
        buf += self.file_type
        buf += b"V1.0"
        buf += struct.pack("<I", 0)                     # LanguageCount
        buf += struct.pack("<I", 0)                     # LocalizedStringSize
        buf += struct.pack("<I", entry_count)
        buf += struct.pack("<I", offset_localized)
        buf += struct.pack("<I", offset_keylist)
        buf += struct.pack("<I", offset_reslist)
        buf += struct.pack("<I", year)
        buf += struct.pack("<I", day)
        buf += struct.pack("<I", 0xFFFFFFFF)            # DescriptionStrRef
        buf += b"\x00" * 116                            # Reserved

        # Key List
        for i, entry in enumerate(entries):
            rb = entry.resref.encode("ascii", errors="replace")[:16].ljust(16, b"\x00")
            buf += rb
            buf += struct.pack("<I", i)                 # ResourceID
            buf += struct.pack("<H", entry.restype)     # ResourceType
            buf += b"\x00\x00"                          # Unused

        # Resource List
        for i, entry in enumerate(entries):
            buf += struct.pack("<I", data_offsets[i])   # Offset
            buf += struct.pack("<I", len(entry.data))   # Size

        # Resource Data
        for entry in entries:
            buf += entry.data

        return bytes(buf)

    def write(self, entries: list[ExportEntry], output_path: Path) -> ExportResult:
        """Build and write the ERF file."""
        result = ExportResult(success=True, message="", output_path=output_path)

        now = datetime.now()
        year = now.year - 1900
        day = now.timetuple().tm_yday - 1

        entry_count = len(entries)
        offset_localized = self.ERF_HEADER_SIZE
        offset_keylist = offset_localized              # no localized strings
        offset_reslist = offset_keylist + entry_count * self.KEY_ENTRY_SIZE
        offset_data_start = offset_reslist + entry_count * self.RES_ENTRY_SIZE

        # Compute data offsets
        data_offsets = []
        current_offset = offset_data_start
        for entry in entries:
            data_offsets.append(current_offset)
            current_offset += len(entry.data)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                # ── Header ──────────────────────────────────────
                f.write(self.file_type)
                f.write(b"V1.0")
                f.write(struct.pack("<I", 0))                    # LanguageCount
                f.write(struct.pack("<I", 0))                    # LocalizedStringSize
                f.write(struct.pack("<I", entry_count))
                f.write(struct.pack("<I", offset_localized))
                f.write(struct.pack("<I", offset_keylist))
                f.write(struct.pack("<I", offset_reslist))
                f.write(struct.pack("<I", year))
                f.write(struct.pack("<I", day))
                f.write(struct.pack("<I", 0xFFFFFFFF))           # DescriptionStrRef
                f.write(b"\x00" * 116)                           # Reserved

                # ── Key List ────────────────────────────────────
                for i, entry in enumerate(entries):
                    resref_bytes = entry.resref.encode("ascii", errors="replace")[:16]
                    resref_bytes = resref_bytes.ljust(16, b"\x00")
                    f.write(resref_bytes)
                    f.write(struct.pack("<I", i))                # ResourceID
                    f.write(struct.pack("<H", entry.restype))    # ResourceType
                    f.write(b"\x00\x00")                         # Unused

                # ── Resource List ────────────────────────────────
                for i, entry in enumerate(entries):
                    f.write(struct.pack("<I", data_offsets[i]))  # Offset
                    f.write(struct.pack("<I", len(entry.data)))  # Size

                # ── Resource Data ────────────────────────────────
                for entry in entries:
                    f.write(entry.data)
                    result.files_exported.append(entry.resref)

        except Exception as e:
            result.success = False
            result.message = f"ERF write failed: {e}"
            result.errors.append(str(e))
            log.error(f"ERF write error: {e}")
            return result

        result.message = (
            f"ERF written: {output_path.name} "
            f"({entry_count} resources, {output_path.stat().st_size:,} bytes)"
        )
        log.info(result.message)
        return result

    def build_from_project(self, project, output_path: Path,
                           file_types: list[str] | None = None) -> ExportResult:
        """Convenience: collect all project files and write ERF."""
        allowed = set(file_types or RESTYPE_IDS.keys())
        entries: list[ExportEntry] = []

        dirs = []
        for attr in ("script_dir", "dialogue_dir", "quest_dir",
                      "twoda_dir", "texture_dir", "model_dir"):
            d = getattr(project, attr, None)
            if d and Path(d).exists():
                dirs.append(Path(d))

        for directory in dirs:
            for f in sorted(directory.iterdir()):
                if f.is_file() and f.suffix.lower() in allowed:
                    try:
                        entries.append(ExportEntry.from_file(f))
                    except Exception as e:
                        log.warning(f"Skipping {f.name}: {e}")

        if not entries:
            return ExportResult(
                success=False,
                message="No exportable files found in project.",
            )
        return self.write(entries, output_path)
