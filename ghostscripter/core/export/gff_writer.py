"""
GhostScripter-K1-K2 — Shared GFF3 Binary Writer
================================================
KotOR 1 & 2 use GFF V3.2 for almost every resource type:
  .dlg  .utc  .utp  .utd  .utm  .jrl  .are  .git  .ifo  .bic …

This module provides the low-level GFF3 assembler used by all exporters.
Import from here instead of from dlg_writer.py.

Usage:
    from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct, GFFType

    w = GFF3Writer("DLG ")
    w.root.add_cexo("EndConversation", "")
    data = w.build()

GFF3 binary layout (56-byte header):
    FileType         4 chars  e.g. b"DLG "
    FileVersion      4 chars  b"V3.2"
    StructOffset     DWORD
    StructCount      DWORD
    FieldOffset      DWORD
    FieldCount       DWORD
    LabelOffset      DWORD
    LabelCount       DWORD
    FieldDataOffset  DWORD
    FieldDataCount   DWORD
    FieldIndicesOffset  DWORD
    FieldIndicesCount   DWORD
    ListIndicesOffset   DWORD
    ListIndicesCount    DWORD

References:
  - xoreos-tools src/aurora/gff3writer.cpp
  - PyKotor pykotor/resource/formats/gff/io_gff.py
  - TSLPatcher lib/site/Bioware/GFF.pm
"""
from __future__ import annotations

import struct
from enum import IntEnum
from typing import Any, List, Optional, Tuple


# ── GFF Field Types ────────────────────────────────────────────────────────────

class GFFType(IntEnum):
    BYTE          = 0
    CHAR          = 1
    WORD          = 2
    SHORT         = 3
    DWORD         = 4
    INT           = 5
    DWORD64       = 6
    INT64         = 7
    FLOAT         = 8
    DOUBLE        = 9
    CEXOSTRING    = 10
    RESREF        = 11
    CEXOLOCSTRING = 12
    VOID          = 13
    STRUCT        = 14
    LIST          = 15
    ORIENTATION   = 16
    VECTOR        = 17
    STRREF        = 18   # TSL only


# ── GFF Value Container ────────────────────────────────────────────────────────

class GFFStruct:
    """
    Holds a sequence of (label, GFFType, value) field tuples.
    Convenience add_* helpers mirror all GFF field types.
    """

    def __init__(self, struct_type: int = 0):
        self.struct_type = struct_type
        self.fields: List[Tuple[str, GFFType, Any]] = []

    # ── Core add ──────────────────────────────────────────────────────────────

    def add(self, label: str, ftype: GFFType, value: Any) -> "GFFStruct":
        """Append a field and return self for chaining."""
        self.fields.append((label, ftype, value))
        return self

    # ── Typed helpers ─────────────────────────────────────────────────────────

    def add_byte(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.BYTE, int(v) & 0xFF)

    def add_char(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.CHAR, int(v) & 0xFF)

    def add_word(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.WORD, int(v) & 0xFFFF)

    def add_short(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.SHORT, int(v))

    def add_dword(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.DWORD, int(v) & 0xFFFFFFFF)

    def add_int(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.INT, int(v))

    def add_dword64(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.DWORD64, int(v))

    def add_int64(self, label: str, v: int) -> "GFFStruct":
        return self.add(label, GFFType.INT64, int(v))

    def add_float(self, label: str, v: float) -> "GFFStruct":
        return self.add(label, GFFType.FLOAT, float(v))

    def add_double(self, label: str, v: float) -> "GFFStruct":
        return self.add(label, GFFType.DOUBLE, float(v))

    def add_resref(self, label: str, v: str) -> "GFFStruct":
        """RESREF is max 16 ASCII chars, lower-cased by the writer."""
        return self.add(label, GFFType.RESREF, str(v)[:16])

    def add_cexo(self, label: str, v: str) -> "GFFStruct":
        """CExoString — general-purpose string."""
        return self.add(label, GFFType.CEXOSTRING, str(v))

    def add_locstring(self, label: str, strref: int, text: str = "") -> "GFFStruct":
        """CExoLocString — TLK StrRef + optional English override."""
        return self.add(label, GFFType.CEXOLOCSTRING, (int(strref), str(text)))

    def add_void(self, label: str, v: bytes) -> "GFFStruct":
        return self.add(label, GFFType.VOID, bytes(v))

    def add_strref(self, label: str, v: int) -> "GFFStruct":
        """STRREF — TSL-only TLK StrRef stored in field data (4-byte size + 4-byte value)."""
        return self.add(label, GFFType.STRREF, int(v))

    def add_struct(self, label: str, s: "GFFStruct") -> "GFFStruct":
        return self.add(label, GFFType.STRUCT, s)

    def add_list(self, label: str, items: List["GFFStruct"]) -> "GFFStruct":
        return self.add(label, GFFType.LIST, list(items))

    def add_vector(self, label: str, x: float, y: float, z: float) -> "GFFStruct":
        return self.add(label, GFFType.VECTOR, (float(x), float(y), float(z)))

    def add_orientation(self, label: str, w: float, x: float, y: float, z: float) -> "GFFStruct":
        """ORIENTATION quaternion (W, X, Y, Z) — used for creature/placeable facing."""
        return self.add(label, GFFType.ORIENTATION, (float(w), float(x), float(y), float(z)))

    # ── PyKotor-compatible aliases ─────────────────────────────────────────────
    # These mirror PyKotor's GFFStruct API names for easier cross-project use.

    def add_uint8(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_byte (PyKotor: set_uint8)."""
        return self.add_byte(label, v)

    def add_int8(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_char (PyKotor: set_int8)."""
        return self.add_char(label, v)

    def add_uint16(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_word (PyKotor: set_uint16)."""
        return self.add_word(label, v)

    def add_int16(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_short (PyKotor: set_int16)."""
        return self.add_short(label, v)

    def add_uint32(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_dword (PyKotor: set_uint32)."""
        return self.add_dword(label, v)

    def add_int32(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_int (PyKotor: set_int32)."""
        return self.add_int(label, v)

    def add_uint64(self, label: str, v: int) -> "GFFStruct":
        """Alias for add_dword64 (PyKotor: set_uint64)."""
        return self.add_dword64(label, v)

    def add_single(self, label: str, v: float) -> "GFFStruct":
        """Alias for add_float (PyKotor: set_single)."""
        return self.add_float(label, v)

    def add_string(self, label: str, v: str) -> "GFFStruct":
        """Alias for add_cexo (PyKotor: set_string)."""
        return self.add_cexo(label, v)

    def add_binary(self, label: str, v: bytes) -> "GFFStruct":
        """Alias for add_void (PyKotor: set_binary)."""
        return self.add_void(label, v)

    def add_vector3(self, label: str, x: float, y: float, z: float) -> "GFFStruct":
        """Alias for add_vector (PyKotor: set_vector3)."""
        return self.add_vector(label, x, y, z)

    def add_vector4(self, label: str, w: float, x: float, y: float, z: float) -> "GFFStruct":
        """Alias for add_orientation (PyKotor: set_vector4 = W,X,Y,Z quaternion)."""
        return self.add_orientation(label, w, x, y, z)


# ── GFF3 Binary Assembler ──────────────────────────────────────────────────────

class GFF3Writer:
    """
    Assembles a GFF3 binary blob from a GFFStruct tree.

    Usage::

        w = GFF3Writer("DLG ")
        w.root.add_cexo("EndConversation", "")
        w.root.add_dword("NumWords", 0)
        data: bytes = w.build()

    The same instance can be rebuilt multiple times (tables are reset on
    each call to build()).
    """

    HEADER_SIZE = 56
    GFF_VERSION = b"V3.2"

    def __init__(self, file_type: str):
        """
        file_type : 4-char resource type string, e.g. ``"DLG "``.
        Strings shorter than 4 chars are right-padded with spaces.
        """
        ft = file_type.ljust(4)[:4].encode("ascii")
        self._file_type = ft
        self.root = GFFStruct(0xFFFFFFFF)

        # Populated during build() — reset on each call
        self._structs:      List[GFFStruct] = []
        self._fields:       List[Tuple[int, GFFType, Any]] = []  # (label_idx, type, value)
        self._labels:       List[str] = []
        self._label_map:    dict = {}   # label → index, for O(1) lookup
        self._field_data    = bytearray()
        self._field_indices = bytearray()
        self._list_indices  = bytearray()

    # ── Public ────────────────────────────────────────────────────────────────

    def build(self) -> bytes:
        """Assemble and return the GFF3 binary blob."""
        self._structs.clear()
        self._fields.clear()
        self._labels.clear()
        self._label_map     = {}
        self._field_data    = bytearray()
        self._field_indices = bytearray()
        self._list_indices  = bytearray()

        self._collect_struct(self.root)
        return self._pack()

    # ── Collection pass ───────────────────────────────────────────────────────

    def _label_index(self, label: str) -> int:
        # O(1) dict lookup instead of O(n) list.index() — critical for large
        # DLGs that may have hundreds of unique field labels.
        idx = self._label_map.get(label)
        if idx is None:
            idx = len(self._labels)
            self._labels.append(label)
            self._label_map[label] = idx
        return idx

    def _collect_struct(self, s: GFFStruct) -> int:
        """Recursively collect a struct; returns its index in self._structs."""
        struct_idx = len(self._structs)
        self._structs.append(s)

        # Pre-allocate contiguous field slots for this struct, then recurse.
        s._field_start = len(self._fields)
        s._field_count = len(s.fields)

        for _ in s.fields:
            self._fields.append(None)   # type: ignore[arg-type]

        for i, (label, ftype, value) in enumerate(s.fields):
            lidx = self._label_index(label)
            slot = s._field_start + i

            if ftype == GFFType.STRUCT:
                child_idx = self._collect_struct(value)
                self._fields[slot] = (lidx, ftype, child_idx)
            elif ftype == GFFType.LIST:
                child_indices = [self._collect_struct(item) for item in value]
                list_offset = len(self._list_indices)
                self._list_indices += struct.pack("<I", len(child_indices))
                for ci in child_indices:
                    self._list_indices += struct.pack("<I", ci)
                self._fields[slot] = (lidx, ftype, list_offset)
            else:
                inline = self._encode_field(ftype, value)
                self._fields[slot] = (lidx, ftype, inline)

        return struct_idx

    def _encode_field(self, ftype: GFFType, value: Any) -> int:
        """
        Encode a scalar field.
        Returns an inline DWORD (for small types) or an offset into
        self._field_data (for variable-length types).
        """
        if ftype == GFFType.BYTE:
            return int(value) & 0xFF
        if ftype == GFFType.CHAR:
            return int(value) & 0xFF
        if ftype == GFFType.WORD:
            return int(value) & 0xFFFF
        if ftype == GFFType.SHORT:
            # Store the full int32 bit-pattern in the DWORD slot so that the
            # engine can correctly sign-extend it when reading back.  Masking
            # to 0xFFFF would corrupt negative values (e.g. -1 → 0xFFFF vs
            # 0xFFFFFFFF).  Both xoreos and PyKotor write the full int32.
            return struct.unpack("<I", struct.pack("<i", int(value)))[0]
        if ftype == GFFType.DWORD:
            return int(value) & 0xFFFFFFFF
        if ftype == GFFType.INT:
            return struct.unpack("<I", struct.pack("<i", int(value)))[0]
        if ftype == GFFType.FLOAT:
            return struct.unpack("<I", struct.pack("<f", float(value)))[0]

        # ── Variable-length types (stored in field_data, return offset) ───────
        offset = len(self._field_data)

        if ftype == GFFType.RESREF:
            raw = str(value).lower()[:16].encode("ascii")
            self._field_data += struct.pack("<B", len(raw))
            self._field_data += raw
        elif ftype == GFFType.CEXOSTRING:
            # KotOR reads Western-language strings as windows-1252, not UTF-8.
            raw = str(value).encode("cp1252", errors="replace")
            self._field_data += struct.pack("<I", len(raw))
            self._field_data += raw
        elif ftype == GFFType.CEXOLOCSTRING:
            strref, text = value
            raw_text = str(text).encode("cp1252", errors="replace")
            if text:
                sub = struct.pack("<II", 0, len(raw_text)) + raw_text   # lang 0 = English
                str_count = 1
            else:
                sub = b""
                str_count = 0
            # total_size covers strref(4) + str_count(4) + sub
            total_size = 8 + len(sub)
            strref_val = int(strref) if strref is not None and int(strref) >= 0 else 0xFFFFFFFF
            self._field_data += struct.pack("<I", total_size)
            self._field_data += struct.pack("<I", strref_val)
            self._field_data += struct.pack("<I", str_count)
            if sub:
                self._field_data += sub
        elif ftype == GFFType.DWORD64:
            self._field_data += struct.pack("<Q", int(value) & 0xFFFFFFFFFFFFFFFF)
        elif ftype == GFFType.INT64:
            self._field_data += struct.pack("<q", int(value))
        elif ftype == GFFType.DOUBLE:
            self._field_data += struct.pack("<d", float(value))
        elif ftype == GFFType.VECTOR:
            x, y, z = value
            self._field_data += struct.pack("<fff", float(x), float(y), float(z))
        elif ftype == GFFType.ORIENTATION:
            # ORIENTATION quaternion — stored on disk as X, Y, Z, W
            # (matches PyKotor/HolocronToolset Vector4 file order, which is
            # what working GIT camera quaternions use). The add_orientation()
            # API still takes (w, x, y, z).
            w, x, y, z = value
            self._field_data += struct.pack("<ffff", float(x), float(y), float(z), float(w))
        elif ftype == GFFType.VOID:
            raw = bytes(value) if value else b""
            self._field_data += struct.pack("<I", len(raw))
            self._field_data += raw
        elif ftype == GFFType.STRREF:
            # TSL STRREF: field_data layout is [total_size: u32][strref: u32].
            # total_size counts the bytes *after* the size field itself = 4.
            self._field_data += struct.pack("<II", 4, int(value) & 0xFFFFFFFF)
        else:
            return 0

        return offset

    # ── Pack into bytes ────────────────────────────────────────────────────────

    def _pack(self) -> bytes:
        n_structs = len(self._structs)
        n_fields  = len(self._fields)
        n_labels  = len(self._labels)

        struct_section = bytearray()
        field_section  = bytearray()
        label_section  = bytearray()
        fi_section     = bytearray()   # field indices

        # Build FieldIndices for structs with >1 field
        for s in self._structs:
            if s._field_count == 0:
                s._data_or_offset = 0xFFFFFFFF
            elif s._field_count == 1:
                s._data_or_offset = s._field_start
            else:
                s._data_or_offset = len(fi_section)
                for fi in range(s._field_start, s._field_start + s._field_count):
                    fi_section += struct.pack("<I", fi)

        for s in self._structs:
            struct_section += struct.pack("<III",
                s.struct_type, s._data_or_offset, s._field_count)

        for lidx, ftype, val in self._fields:
            field_section += struct.pack("<III", int(ftype), lidx, val)

        for label in self._labels:
            encoded = label[:16].encode("ascii")
            label_section += encoded.ljust(16, b"\x00")

        struct_offset = self.HEADER_SIZE
        field_offset  = struct_offset + len(struct_section)
        label_offset  = field_offset  + len(field_section)
        fdata_offset  = label_offset  + len(label_section)
        fi_offset     = fdata_offset  + len(self._field_data)
        li_offset     = fi_offset     + len(fi_section)

        header = struct.pack("<4s4sIIIIIIIIIIII",
            self._file_type,
            self.GFF_VERSION,
            struct_offset,  n_structs,
            field_offset,   n_fields,
            label_offset,   n_labels,
            fdata_offset,   len(self._field_data),
            fi_offset,      len(fi_section),
            li_offset,      len(self._list_indices),
        )

        return (header
                + bytes(struct_section)
                + bytes(field_section)
                + bytes(label_section)
                + bytes(self._field_data)
                + bytes(fi_section)
                + bytes(self._list_indices))
