"""
GhostScripter-K1-K2 — GFF3 Binary Reader + DLG Importer
=========================================================
Reads GFF3 binary files (used by KotOR 1 & 2 for .dlg, .utc, etc.)
and reconstructs a DialogueFile model from a .dlg binary.

Supports:
  - KotOR 1 and KotOR 2 (TSL) .dlg files
  - All entry/reply node fields
  - Branch links (Active/Active2/IsChild)
  - AnimList per-node
  - Top-level dialogue properties
  - Graceful degradation for unknown/optional fields

GFF3 binary layout (header = 56 bytes):
  FileType        4 chars   e.g. "DLG "
  FileVersion     4 chars   "V3.2"
  StructOffset    DWORD
  StructCount     DWORD
  FieldOffset     DWORD
  FieldCount      DWORD
  LabelOffset     DWORD
  LabelCount      DWORD
  FieldDataOffset DWORD
  FieldDataCount  DWORD
  FieldIndicesOffset  DWORD
  FieldIndicesCount   DWORD
  ListIndicesOffset   DWORD
  ListIndicesCount    DWORD

References:
  - PyKotor pykotor/resource/formats/gff/io_gff.py
  - xoreos-tools src/aurora/gff3file.cpp
  - TK102 DLGEditor dlgeditor_234.pl
"""

from __future__ import annotations

import logging
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch, DLGAnimation,
)

log = logging.getLogger(__name__)


# ── GFF Field Type constants ───────────────────────────────────
# Type IDs verified against OldRepublicDevs/PyKotor GFFFieldType enum
# and swkotor.exe GFF structure (CResGFF::WriteGFFData @ 0x004113d0).
# NOTE: PyKotor uses Vector4=16, Vector3=17 — our ORIENTATION(16)/VECTOR(17)
# mapping matches this exactly (ORIENTATION is a quaternion = 4 floats = Vector4;
# VECTOR is a position/direction = 3 floats = Vector3).

_BYTE          = 0
_CHAR          = 1
_WORD          = 2
_SHORT         = 3
_DWORD         = 4
_INT           = 5
_DWORD64       = 6
_INT64         = 7
_FLOAT         = 8
_DOUBLE        = 9
_CEXOSTRING    = 10
_RESREF        = 11
_CEXOLOCSTRING = 12
_VOID          = 13
_STRUCT        = 14
_LIST          = 15
_ORIENTATION   = 16   # Quaternion (W, X, Y, Z) — 4 floats in field_data
_VECTOR        = 17   # Position/direction (X, Y, Z) — 3 floats in field_data
_STRREF        = 18   # TSL only: StrRef stored in field_data (size-prefixed u32)

# Types with data stored inline in the field's DataOrOffset dword
_INLINE_TYPES = {_BYTE, _CHAR, _WORD, _SHORT, _DWORD, _INT, _FLOAT}


class GFF3ReadError(Exception):
    pass


class GFF3ParseStats:
    """Collects timing & count information about a single GFF3 parse."""
    def __init__(self):
        self.start_time = time.monotonic()
        self.structs_read = 0
        self.fields_read  = 0
        self.lists_read   = 0
        self.depth_max    = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.start_time

    def __str__(self) -> str:
        return (
            f"structs={self.structs_read} fields={self.fields_read} "
            f"lists={self.lists_read} max_depth={self.depth_max} "
            f"elapsed={self.elapsed()*1000:.1f}ms"
        )


class GFF3Reader:
    """
    Parses a GFF3 binary blob and exposes it as a nested dict/list structure.
    """

    # Hard cap on recursive nesting depth — prevents infinite loops on
    # malformed or complex GFF3 files (e.g. large KotOR DLGs with many
    # cross-linked structs).
    _MAX_DEPTH = 64

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0
        self._file_type = ""
        self._file_version = ""
        self._depth = 0          # current recursion depth
        self._visited_structs: set = set()   # guard against struct cycles
        self._stats = GFF3ParseStats()

        # Offsets from header
        self._struct_offset = 0
        self._struct_count = 0
        self._field_offset = 0
        self._field_count = 0
        self._label_offset = 0
        self._label_count = 0
        self._field_data_offset = 0
        self._field_data_count = 0
        self._field_indices_offset = 0
        self._field_indices_count = 0
        self._list_indices_offset = 0
        self._list_indices_count = 0

        self._labels: List[str] = []
        self._top_level: Dict | None = None

    def _u8(self, offset: int) -> int:
        return struct.unpack_from("<B", self._data, offset)[0]

    def _u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self._data, offset)[0]

    def _i16(self, offset: int) -> int:
        return struct.unpack_from("<h", self._data, offset)[0]

    def _u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self._data, offset)[0]

    def _i32(self, offset: int) -> int:
        return struct.unpack_from("<i", self._data, offset)[0]

    def _u64(self, offset: int) -> int:
        return struct.unpack_from("<Q", self._data, offset)[0]

    def _i64(self, offset: int) -> int:
        return struct.unpack_from("<q", self._data, offset)[0]

    def _f32(self, offset: int) -> float:
        return struct.unpack_from("<f", self._data, offset)[0]

    def _f64(self, offset: int) -> float:
        return struct.unpack_from("<d", self._data, offset)[0]

    # ── Parse header ────────────────────────────────────────────

    def _parse_header(self):
        d = self._data
        if len(d) < 56:
            raise GFF3ReadError("File too small to be a GFF3")
        self._file_type = d[0:4].decode("ascii", errors="replace").strip()
        self._file_version = d[4:8].decode("ascii", errors="replace")
        if self._file_version not in ("V3.2",):
            # Accept V3.2 only; warn but proceed for others
            pass
        self._struct_offset         = self._u32(8)
        self._struct_count          = self._u32(12)
        self._field_offset          = self._u32(16)
        self._field_count           = self._u32(20)
        self._label_offset          = self._u32(24)
        self._label_count           = self._u32(28)
        self._field_data_offset     = self._u32(32)
        self._field_data_count      = self._u32(36)
        self._field_indices_offset  = self._u32(40)
        self._field_indices_count   = self._u32(44)
        self._list_indices_offset   = self._u32(48)
        self._list_indices_count    = self._u32(52)

    # ── Parse labels ──────────────────────────────────────────────

    def _parse_labels(self):
        """Batch-load all labels in one pass (avoids N separate slice ops)."""
        off = self._label_offset
        data = self._data
        # Read all label bytes in one slice, then split into 16-byte chunks
        total = self._label_count * 16
        if off + total <= len(data):
            chunk = data[off: off + total]
            for i in range(self._label_count):
                raw = chunk[i * 16: i * 16 + 16]
                label = raw.rstrip(b"\x00").decode("ascii", errors="replace")
                self._labels.append(label)
        else:
            # Fallback: read one at a time
            for _ in range(self._label_count):
                raw = data[off: off + 16]
                label = raw.rstrip(b"\x00").decode("ascii", errors="replace")
                self._labels.append(label)
                off += 16

    # ── Read field value ─────────────────────────────────────────

    def _read_field_data_string(self, data_offset: int) -> str:
        """Read a CEXOSTRING from the field data block."""
        abs_off = self._field_data_offset + data_offset
        size = self._u32(abs_off)
        raw = self._data[abs_off + 4: abs_off + 4 + size]
        return raw.decode("utf-8", errors="replace")

    def _read_resref(self, data_offset: int) -> str:
        """Read a RESREF (length-prefixed, max 16 bytes) from field data."""
        abs_off = self._field_data_offset + data_offset
        length = self._u8(abs_off)
        raw = self._data[abs_off + 1: abs_off + 1 + length]
        return raw.decode("ascii", errors="replace")

    def _read_cexolocstring(self, data_offset: int) -> Tuple[int, str]:
        """
        Read a CEXOLOCSTRING. Returns (strref, english_text).
        Layout: total_size DWORD, strref DWORD, str_count DWORD,
                [lang_id DWORD, length DWORD, text bytes]*
        """
        abs_off = self._field_data_offset + data_offset
        # total_size = self._u32(abs_off)  # bytes following this field
        strref = self._i32(abs_off + 4)
        str_count = self._u32(abs_off + 8)
        pos = abs_off + 12
        english = ""
        for _ in range(str_count):
            lang_id = self._u32(pos)
            length  = self._u32(pos + 4)
            text    = self._data[pos + 8: pos + 8 + length].decode("utf-8", errors="replace")
            # lang 0 = English (masculine), lang 1 = English (feminine)
            if lang_id in (0, 1) and not english:
                english = text
            pos += 8 + length
        return strref, english

    def _read_field_value(self, field_offset: int) -> Tuple[str, Any]:
        """
        Parse a single field record (12 bytes).
        Returns (label, value).
        """
        ftype     = self._u32(field_offset)
        label_idx = self._u32(field_offset + 4)
        data_dw   = self._u32(field_offset + 8)   # inline or offset

        label = self._labels[label_idx] if label_idx < len(self._labels) else f"label_{label_idx}"

        if ftype == _BYTE:
            value = data_dw & 0xFF
        elif ftype == _CHAR:
            value = struct.unpack("<b", struct.pack("<I", data_dw & 0xFF)[:1])[0]
        elif ftype == _WORD:
            value = data_dw & 0xFFFF
        elif ftype == _SHORT:
            value = struct.unpack("<h", struct.pack("<H", data_dw & 0xFFFF))[0]
        elif ftype == _DWORD:
            value = data_dw
        elif ftype == _INT:
            value = struct.unpack("<i", struct.pack("<I", data_dw))[0]
        elif ftype == _FLOAT:
            value = struct.unpack("<f", struct.pack("<I", data_dw))[0]
        elif ftype == _DWORD64:
            abs_off = self._field_data_offset + data_dw
            value = self._u64(abs_off)
        elif ftype == _INT64:
            abs_off = self._field_data_offset + data_dw
            value = self._i64(abs_off)
        elif ftype == _DOUBLE:
            abs_off = self._field_data_offset + data_dw
            value = self._f64(abs_off)
        elif ftype == _CEXOSTRING:
            value = self._read_field_data_string(data_dw)
        elif ftype == _RESREF:
            value = self._read_resref(data_dw)
        elif ftype == _CEXOLOCSTRING:
            value = self._read_cexolocstring(data_dw)  # (strref, text)
        elif ftype == _VOID:
            abs_off = self._field_data_offset + data_dw
            size = self._u32(abs_off)
            value = self._data[abs_off + 4: abs_off + 4 + size]
        elif ftype == _STRUCT:
            # data_dw is the struct index
            value = self._read_struct(data_dw)
        elif ftype == _LIST:
            # data_dw is offset into list indices block
            value = self._read_list(data_dw)
        elif ftype == _STRREF:
            # TSL STRREF: stored in field_data as a 4-byte total_size DWORD
            # followed by the actual 4-byte StrRef DWORD value.
            # Layout: [total_size: u32][strref_value: u32]
            # We skip the size prefix and read the StrRef as a signed int.
            abs_off = self._field_data_offset + data_dw
            # total_size = self._u32(abs_off)  # should be 4
            value = self._i32(abs_off + 4)
        elif ftype == _VECTOR:
            # VECTOR (type 17): stored in field_data as three 32-bit floats (X, Y, Z)
            abs_off = self._field_data_offset + data_dw
            x = self._f32(abs_off)
            y = self._f32(abs_off + 4)
            z = self._f32(abs_off + 8)
            value = (x, y, z)
        elif ftype == _ORIENTATION:
            # ORIENTATION (type 16): stored on disk as four 32-bit floats in
            # X, Y, Z, W order (PyKotor/HolocronToolset Vector4 convention).
            # Returned as (w, x, y, z) to mirror GFFStruct.add_orientation().
            abs_off = self._field_data_offset + data_dw
            x = self._f32(abs_off)
            y = self._f32(abs_off + 4)
            z = self._f32(abs_off + 8)
            w = self._f32(abs_off + 12)
            value = (w, x, y, z)
        else:
            value = data_dw  # Unknown type — return raw dword

        return label, value

    # ── Read struct ──────────────────────────────────────────────

    def _read_struct(self, struct_idx: int) -> Dict[str, Any]:
        # Guard: depth limit prevents infinite recursion on circular GFF3
        if self._depth >= self._MAX_DEPTH:
            log.warning(
                "GFF3 depth limit (%d) hit at struct %d — truncating subtree",
                self._MAX_DEPTH, struct_idx,
            )
            return {"__struct_type": 0, "__truncated": True}
        # Guard: struct index out of range
        if struct_idx < 0 or struct_idx >= self._struct_count:
            log.warning(
                "GFF3 struct index out of range: %d (count=%d)",
                struct_idx, self._struct_count,
            )
            return {"__struct_type": 0, "__invalid_idx": struct_idx}
        # Guard: cycle detection — each struct index should only be entered once
        # per top-level traversal to prevent infinite loops on malformed GFF3
        # files with circular STRUCT→STRUCT references (rare but possible).
        if struct_idx in self._visited_structs:
            log.debug(
                "GFF3 cycle detected at struct %d — returning stub to break loop",
                struct_idx,
            )
            return {"__struct_type": 0, "__cycle_ref": struct_idx}
        self._visited_structs.add(struct_idx)

        self._depth += 1
        self._stats.structs_read += 1
        if self._depth > self._stats.depth_max:
            self._stats.depth_max = self._depth
        try:
            off = self._struct_offset + struct_idx * 12
            struct_type = self._u32(off)
            data_or_offset = self._u32(off + 4)
            field_count = self._u32(off + 8)

            result: Dict[str, Any] = {"__struct_type": struct_type}

            if field_count == 0:
                return result
            elif field_count == 1:
                # DataOrDataOffset is a direct field index
                field_idx = data_or_offset
                if field_idx < self._field_count:
                    field_off = self._field_offset + field_idx * 12
                    lbl, val = self._read_field_value(field_off)
                    result[lbl] = val
            else:
                # DataOrDataOffset is an offset into field_indices block.
                # Batch-read all field indices in one slice for performance
                # (mirrors PyKotor GFFBinaryReader._load_fields_batch).
                fi_base = self._field_indices_offset + data_or_offset
                fi_end = fi_base + field_count * 4
                if fi_end <= len(self._data):
                    fi_block = self._data[fi_base:fi_end]
                    indices = struct.unpack_from(f"<{field_count}I", fi_block)
                else:
                    # Out-of-bounds: fall back to individual reads
                    indices = [self._u32(fi_base + i * 4) for i in range(field_count)]
                for field_idx in indices:
                    if field_idx < self._field_count:
                        field_off = self._field_offset + field_idx * 12
                        lbl, val = self._read_field_value(field_off)
                        result[lbl] = val

            return result
        finally:
            self._depth -= 1

    # ── Read list ────────────────────────────────────────────────

    def _read_list(self, list_offset: int) -> List[Dict[str, Any]]:
        abs_off = self._list_indices_offset + list_offset
        # Bounds check
        if abs_off + 4 > len(self._data):
            log.warning("GFF3 list offset %d out of bounds (data len=%d)",
                        abs_off, len(self._data))
            return []
        count = self._u32(abs_off)
        # Sanity limit: a DLG won't have more than 10,000 items in one list
        if count > 10000:
            log.warning("GFF3 list at offset %d has unreasonable count %d — skipping",
                        list_offset, count)
            return []
        self._stats.lists_read += 1
        items = []
        for i in range(count):
            struct_idx = self._u32(abs_off + 4 + i * 4)
            items.append(self._read_struct(struct_idx))
        return items

    # ── Public API ───────────────────────────────────────────────

    def parse(self) -> Dict[str, Any]:
        """Parse the GFF3 and return the top-level struct as a dict."""
        log.debug("GFF3Reader.parse() started, data_len=%d", len(self._data))
        self._parse_header()
        log.debug("GFF3 header: type=%r version=%r structs=%d fields=%d labels=%d",
                  self._file_type, self._file_version,
                  self._struct_count, self._field_count, self._label_count)
        self._parse_labels()
        self._depth = 0
        self._visited_structs = set()
        self._stats = GFF3ParseStats()
        self._top_level = self._read_struct(0)
        log.debug("GFF3Reader.parse() done: %s", self._stats)
        return self._top_level

    def read_root(self) -> Dict[str, Any]:
        """Alias for parse() — provided for PyKotor-style API compatibility."""
        return self.parse()

    @classmethod
    def from_bytes(cls, data: bytes) -> "GFF3Reader":
        """Convenience constructor: GFF3Reader.from_bytes(data).parse()."""
        return cls(data)

    @property
    def file_type(self) -> str:
        return self._file_type

    @property
    def file_version(self) -> str:
        return self._file_version


# ─────────────────────────────────────────────────────────────────
# DLG Importer — converts parsed GFF dict → DialogueFile
# ─────────────────────────────────────────────────────────────────

def _str(d: Dict, key: str, default: str = "") -> str:
    v = d.get(key, default)
    if isinstance(v, tuple):          # CEXOLOCSTRING → (strref, text)
        return v[1]
    return str(v) if v is not None else default


def _int(d: Dict, key: str, default: int = 0) -> int:
    v = d.get(key, default)
    if isinstance(v, tuple):
        return int(v[0]) if v else default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(d: Dict, key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key, default))
    except (TypeError, ValueError):
        return default


def _bool(d: Dict, key: str, default: bool = False) -> bool:
    v = d.get(key, None)
    if v is None:
        return default
    return bool(v)


def _strref(d: Dict, key: str) -> int:
    """Return TLK strref from a CEXOLOCSTRING field."""
    v = d.get(key)
    if isinstance(v, tuple):
        return v[0]
    return -1


class DLGImporter:
    """
    Reads a GFF3 binary .dlg file and returns a DialogueFile model.
    """

    def import_from_bytes(self, data: bytes,
                          name: str = "imported",
                          file_path: str | None = None) -> DialogueFile:
        t_start = time.monotonic()
        log.info("DLGImporter: parsing '%s' (%d bytes)", name, len(data))
        try:
            reader = GFF3Reader(data)
            root = reader.parse()
        except Exception:
            log.exception("GFF3Reader failed to parse '%s'", name)
            raise

        if reader.file_type not in ("DLG", ""):
            log.warning("Unexpected GFF3 file type %r for '%s' (expected 'DLG')",
                        reader.file_type, name)

        dlg = DialogueFile(name=name, file_path=file_path)

        # ── Top-level fields ─────────────────────────────────────
        # EndConversation = the script called when the conversation ends normally.
        # EndConverAbort  = the script called when the conversation is aborted.
        # They are DIFFERENT fields — assign each to the correct attribute.
        # Prefer EndConversation for on_end; fall back to EndConverAbort only
        # if EndConversation is absent (older .dlg files may omit it).
        dlg.on_end           = _str(root, "EndConversation") or _str(root, "EndConverAbort")
        dlg.on_abort         = _str(root, "EndConverAbort")
        dlg.skippable        = bool(_int(root, "Skippable", 1))
        dlg.delay_entry      = _int(root, "DelayEntry")
        dlg.delay_reply      = _int(root, "DelayReply")
        dlg.ambient_track    = _str(root, "AmbientTrack")
        dlg.animated_cut     = bool(_int(root, "AnimatedCut"))
        dlg.camera_model     = _str(root, "CameraModel")
        dlg.conversation_type = _int(root, "ConversationType")
        dlg.computer_type    = _int(root, "ComputerType")
        dlg.old_hit_check    = bool(_int(root, "OldHitCheck"))
        dlg.unequip_items    = bool(_int(root, "UnequipItems"))
        dlg.unequip_h_item   = bool(_int(root, "UnequipHItem"))
        dlg.word_count       = _int(root, "NumWords")

        # ── Entry nodes (NPC lines) ──────────────────────────────
        entry_list = root.get("EntryList", [])
        log.debug("DLGImporter: parsing %d entries for '%s'", len(entry_list), name)
        for idx, e in enumerate(entry_list):
            try:
                node = self._parse_node(e, idx, "entry")
                dlg.entries.append(node)
            except Exception:
                log.exception("DLGImporter: error parsing entry[%d] of '%s'", idx, name)

        # ── Reply nodes (player choices) ─────────────────────────
        reply_list = root.get("ReplyList", [])
        log.debug("DLGImporter: parsing %d replies for '%s'", len(reply_list), name)
        for idx, r in enumerate(reply_list):
            try:
                node = self._parse_node(r, idx, "reply")
                dlg.replies.append(node)
            except Exception:
                log.exception("DLGImporter: error parsing reply[%d] of '%s'", idx, name)

        # ── Starting links ────────────────────────────────────────
        starting_list = root.get("StartingList", [])
        for idx, s in enumerate(starting_list):
            try:
                branch = self._parse_link(s, idx)
                dlg.starters.append(branch)
            except Exception:
                log.exception("DLGImporter: error parsing starter[%d] of '%s'", idx, name)

        # ── Auto-layout nodes ────────────────────────────────────
        x_entry, x_reply = 60, 360
        y_step = 110
        for i, node in enumerate(dlg.entries):
            node.position_x = x_entry
            node.position_y = i * y_step + 40
        for i, node in enumerate(dlg.replies):
            node.position_x = x_reply
            node.position_y = i * y_step + 40

        elapsed = (time.monotonic() - t_start) * 1000
        log.info(
            "DLGImporter: loaded '%s' — %d entries, %d replies, %d starters in %.1fms",
            name, len(dlg.entries), len(dlg.replies), len(dlg.starters), elapsed,
        )
        return dlg

    def import_from_file(self, path: str | Path) -> DialogueFile:
        path = Path(path)
        log.info("DLGImporter: opening file %s", path)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            log.exception("DLGImporter: cannot read file %s", path)
            raise
        return self.import_from_bytes(data,
                                      name=path.stem,
                                      file_path=str(path))

    # ── Private: parse a single node struct ─────────────────────

    def _parse_node(self, d: Dict, idx: int, node_type: str) -> DialogueNode:
        node = DialogueNode(node_id=idx, node_type=node_type)

        # Text
        text_val = d.get("Text")
        if isinstance(text_val, tuple):
            node.text_strref = text_val[0]
            node.text = text_val[1]
        else:
            node.text = str(text_val) if text_val else ""

        # Identity
        node.speaker  = _str(d, "Speaker")
        node.listener = _str(d, "Listener")

        # Scripts
        node.script1  = _str(d, "Script")
        node.script2  = _str(d, "Script2")

        # Audio
        node.vo_resref     = _str(d, "VO_ResRef")
        node.sound         = _str(d, "Sound")
        node.sound_exists  = _int(d, "SoundExists")

        # Timing
        raw_delay = _int(d, "Delay", 0xFFFFFFFF)
        # Delay is DWORD -1 (0xFFFFFFFF) means no delay
        if raw_delay == 0xFFFFFFFF:
            node.delay = -1
        else:
            node.delay = raw_delay
        node.wait_flags = _int(d, "WaitFlags")

        # Quest / plot
        node.quest            = _str(d, "Quest")
        node.quest_entry      = _int(d, "QuestEntry")
        node.plot_index       = _int(d, "PlotIndex", -1)
        node.plot_xp_percentage = _float(d, "PlotXPPercentage", 1.0)

        # Fade
        node.fade_type  = _int(d, "FadeType")
        node.fade_delay = _float(d, "FadeDelay")
        node.fade_length = _float(d, "FadeLength")
        # FadeColor is stored as a VECTOR (3 floats) or separate fields
        fade_color = d.get("FadeColor")
        if isinstance(fade_color, (list, tuple)) and len(fade_color) >= 3:
            node.fade_color_r = float(fade_color[0])
            node.fade_color_g = float(fade_color[1])
            node.fade_color_b = float(fade_color[2])

        # Camera
        node.camera_angle = _int(d, "CameraAngle")
        cam_id = d.get("CameraID")
        node.camera_id = int(cam_id) if cam_id is not None else None
        cam_anim = d.get("CameraAnimation")
        node.camera_animation = int(cam_anim) if cam_anim is not None else None
        cam_fov = d.get("CamFieldOfView")
        node.camera_fov = float(cam_fov) if cam_fov is not None else None
        cam_h = d.get("CamHeightOffset")
        node.camera_height = float(cam_h) if cam_h is not None else None
        cam_eff = d.get("CamVidEffect")
        node.camera_effect = int(cam_eff) if cam_eff is not None else None
        tar_h = d.get("TarHeightOffset")
        node.target_height = float(tar_h) if tar_h is not None else None

        # Comment
        node.comment = _str(d, "Comment")

        # TSL extended
        node.node_unskippable = bool(_int(d, "NodeUnskippable"))
        node.alien_race_node  = _int(d, "AlienRaceNode")
        node.emotion_id       = _int(d, "Emotion")
        node.facial_id        = _int(d, "FacialAnim")
        node.node_id_tsl      = _int(d, "NodeID")
        node.post_proc_node   = _int(d, "PostProcNode")
        node.record_vo        = bool(_int(d, "RecordVO"))
        node.record_no_vo_override = bool(_int(d, "RecordNoVOOverri"))
        node.vo_text_changed  = bool(_int(d, "VOTextChanged"))

        # TSL script params
        node.script1_param1    = _int(d, "ActionParam1")
        node.script1_param2    = _int(d, "ActionParam2")
        node.script1_param3    = _int(d, "ActionParam3")
        node.script1_param4    = _int(d, "ActionParam4")
        node.script1_param5    = _int(d, "ActionParam5")
        node.script1_param_str = _str(d, "ActionParamStrA")
        node.script2_param1    = _int(d, "ActionParam1b")
        node.script2_param2    = _int(d, "ActionParam2b")
        node.script2_param3    = _int(d, "ActionParam3b")
        node.script2_param4    = _int(d, "ActionParam4b")
        node.script2_param5    = _int(d, "ActionParam5b")
        node.script2_param_str = _str(d, "ActionParamStrB")

        # Animations
        anim_list = d.get("AnimList", [])
        for a in anim_list:
            anim = DLGAnimation(
                participant=_str(a, "Participant"),
                animation_id=_int(a, "Animation"),
            )
            node.animations.append(anim)

        # Branches (RepliesList for entry nodes, EntriesList for reply nodes)
        link_list_key = "RepliesList" if node_type == "entry" else "EntriesList"
        link_list = d.get(link_list_key, [])
        for link_idx, link in enumerate(link_list):
            branch = self._parse_link(link, link_idx)
            node.branches.append(branch)

        return node

    def _parse_link(self, d: Dict, idx: int) -> DialogueBranch:
        branch = DialogueBranch(
            branch_id=idx,
            target_node_id=_int(d, "Index", -1),
            active_script=_str(d, "Active"),
            active_script2=_str(d, "Active2"),
            is_child=bool(_int(d, "IsChild")),
            link_comment=_str(d, "LinkComment"),
            display_inactive=bool(_int(d, "DisplayInactive")),
        )
        return branch


# ── Convenience function ─────────────────────────────────────────

def read_dlg(path: str | Path) -> DialogueFile:
    """Read a .dlg GFF3 binary file and return a DialogueFile."""
    return DLGImporter().import_from_file(path)


def read_dlg_bytes(data: bytes, name: str = "imported") -> DialogueFile:
    """Parse a .dlg GFF3 binary blob and return a DialogueFile."""
    return DLGImporter().import_from_bytes(data, name=name)
