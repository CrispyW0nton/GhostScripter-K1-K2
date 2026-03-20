"""
GhostScripter — TLK (Talk Table) Domain Model
==============================================
Extracted from the UI layer so that the core domain does not depend on Qt.

Coupling model (Khononov, "Balancing Coupling in Software Design")
------------------------------------------------------------------
  Distance   : LOW   (within core.models — same bounded context)
  Strength   : FUNCTIONAL (TLKEntry and TLKFile are one aggregate)
  Volatility : LOW   (binary format is KotOR-stable since 2003)
  ∴ Balance = (FUNCTIONAL XOR LOW-distance) OR NOT LOW-volatility = TRUE ✓

Design: Deep Module
  Large complexity hidden (struct parsing, codepage detection, off-string
  arithmetic) behind a tiny stable interface: from_bytes(), get_string(),
  to_bytes().
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, List


# ── TLK flags ─────────────────────────────────────────────────────────────────

TLK_FLAG_HAS_TEXT   = 0x01
TLK_FLAG_HAS_SOUND  = 0x02
TLK_FLAG_HAS_LENGTH = 0x04

LANGUAGE_IDS: Dict[int, str] = {
    0: "English",
    1: "French",
    2: "German",
    3: "Italian",
    4: "Spanish",
    5: "Polish",
    128: "Korean",
    129: "Chinese (Trad.)",
    130: "Chinese (Simp.)",
    131: "Japanese",
}

# Encoding used for the string data block, keyed by LanguageID.
# KotOR / TSL store Western-language text in Windows-1252 (cp1252), NOT latin-1.
_LANGUAGE_ENCODING: Dict[int, str] = {
    0: "cp1252",   # English
    1: "cp1252",   # French
    2: "cp1252",   # German
    3: "cp1252",   # Italian
    4: "cp1252",   # Spanish
    5: "cp1252",   # Polish
    128: "cp949",  # Korean
    129: "cp950",  # Chinese Traditional
    130: "cp936",  # Chinese Simplified
    131: "cp932",  # Japanese
}
_DEFAULT_ENCODING = "cp1252"


# ── TLKEntry ──────────────────────────────────────────────────────────────────

class TLKEntry:
    """A single string entry in a TLK file."""

    __slots__ = (
        "strref", "text", "sound_resref",
        "flags", "volume_variance", "pitch_variance", "sound_length",
    )

    def __init__(self, strref: int = 0) -> None:
        self.strref: int = strref
        self.text: str = ""
        self.sound_resref: str = ""
        self.flags: int = TLK_FLAG_HAS_TEXT
        self.volume_variance: int = 0
        self.pitch_variance: int = 0
        self.sound_length: float = 0.0

    @property
    def has_text(self) -> bool:
        return bool(self.flags & TLK_FLAG_HAS_TEXT)

    @property
    def has_sound(self) -> bool:
        return bool(self.flags & TLK_FLAG_HAS_SOUND)

    def short_text(self, max_len: int = 60) -> str:
        t = self.text.replace("\r", "").replace("\n", " ").strip()
        return t[:max_len] + "…" if len(t) > max_len else t


# ── TLKFile ───────────────────────────────────────────────────────────────────

class TLKFile:
    """In-memory TLK file — pure domain object, no Qt or UI dependencies."""

    def __init__(self) -> None:
        self.language_id: int = 0
        self.entries: List[TLKEntry] = []
        self.filename: str = ""
        self.file_path: Path | None = None

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def from_bytes(cls, data: bytes, filename: str = "") -> "TLKFile":
        """Parse raw TLK binary bytes and return a TLKFile instance."""
        obj = cls()
        obj.filename = filename
        obj._parse(data)
        return obj

    @classmethod
    def from_file(cls, path: Path) -> "TLKFile":
        obj = cls()
        obj.filename = path.name
        obj.file_path = path
        obj._parse(path.read_bytes())
        return obj

    # ── Binary parsing ────────────────────────────────────────────────────────

    def _parse(self, data: bytes) -> None:
        if data[:4] != b"TLK ":
            raise ValueError("Not a TLK file (missing 'TLK ' magic)")
        if len(data) < 20:
            raise ValueError("TLK file too short (truncated header)")
        (_type, _ver, lang_id, count, str_offset) = struct.unpack_from("<4s4sIII", data, 0)
        self.language_id = lang_id
        enc = _LANGUAGE_ENCODING.get(lang_id, _DEFAULT_ENCODING)

        entry_base = 20
        for i in range(count):
            e = TLKEntry(strref=i)
            (flags, sound_raw, vol_var, pitch_var,
             off_str, str_size, sound_len) = struct.unpack_from(
                "<I16sIIIIf", data, entry_base + i * 40
            )
            e.flags = flags
            e.sound_resref = sound_raw.rstrip(b"\x00").decode("ascii", errors="ignore")
            e.volume_variance = vol_var
            e.pitch_variance = pitch_var
            e.sound_length = sound_len
            if str_size > 0:
                start = str_offset + off_str
                raw = data[start: start + str_size]
                try:
                    e.text = raw.decode(enc)
                except (UnicodeDecodeError, LookupError):
                    e.text = raw.decode("cp1252", errors="replace")
            self.entries.append(e)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_bytes(self) -> bytes:
        """Serialise TLK back to binary, preserving the correct codepage."""
        enc = _LANGUAGE_ENCODING.get(self.language_id, _DEFAULT_ENCODING)
        count = len(self.entries)
        str_offset = 20 + count * 40

        entry_table = bytearray()
        string_data = bytearray()

        for e in self.entries:
            if e.text:
                try:
                    raw_text = e.text.encode(enc, errors="replace")
                except (UnicodeEncodeError, LookupError):
                    raw_text = e.text.encode("cp1252", errors="replace")
            else:
                raw_text = b""

            sound_raw = e.sound_resref[:16].encode("ascii", errors="ignore").ljust(16, b"\x00")
            if raw_text:
                off_str = len(string_data)
                string_data += raw_text
            else:
                off_str = 0

            entry_table += struct.pack(
                "<I16sIIIIf",
                e.flags,
                sound_raw,
                e.volume_variance,
                e.pitch_variance,
                off_str,
                len(raw_text),
                e.sound_length,
            )

        header = struct.pack(
            "<4s4sIII",
            b"TLK ",
            b"V3.0",
            self.language_id,
            count,
            str_offset,
        )
        return header + bytes(entry_table) + bytes(string_data)

    def save(self, path: Path | None = None) -> None:
        target = path or self.file_path
        if not target:
            raise ValueError("No path specified")
        Path(target).write_bytes(self.to_bytes())

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_string(self, strref: int, default: str = "") -> str:
        """Return the text for *strref*, or *default* if out of range."""
        if 0 <= strref < len(self.entries):
            return self.entries[strref].text
        return default

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        lang = LANGUAGE_IDS.get(self.language_id, str(self.language_id))
        return f"TLKFile({self.filename!r}, lang={lang}, entries={len(self.entries)})"
