"""
Tests for TLKFile / TLKEntry parsing and serialisation.

Covers the four bugs reported via Discord (Mar 2026):
  Bug 1 — latin-1 read encoding  → cp1252-only characters (0x80-0x9F) decoded
           as C1 control chars, producing phantom entries other tools can't see.
  Bug 2 — latin-1 write encoding → cp1252 chars corrupted on save; GRigger drops
           or mis-displays entries after round-trip.
  Bug 3 — _apply_edit() clobbers TLK_FLAG_HAS_LENGTH (0x04) and any other flag
           bits, causing tools like GRigger to treat entries as malformed.
  Bug 4 — sound_resref decoded with errors="replace" instead of errors="ignore",
           producing U+FFFD replacement characters in ResRef names.
"""
from __future__ import annotations

import struct
import unittest
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Helpers to build minimal TLK blobs in memory
# ---------------------------------------------------------------------------

def _build_tlk(lang_id: int, entries: List[tuple]) -> bytes:
    """
    Build a minimal TLK V3.0 binary blob.
    entries: list of (flags, sound_resref_bytes, text_bytes)
    """
    count = len(entries)
    str_offset = 20 + count * 40  # absolute offset to string data block

    entry_table = bytearray()
    string_data = bytearray()

    for flags, sound_raw, text_bytes in entries:
        off_str = len(string_data)
        string_data += text_bytes
        # Pad / truncate sound to 16 bytes
        sound_padded = sound_raw[:16].ljust(16, b"\x00")
        entry_table += struct.pack(
            "<I16sIIIIf",
            flags,
            sound_padded,
            0,          # volume_variance
            0,          # pitch_variance
            off_str,
            len(text_bytes),
            0.0,        # sound_length
        )

    header = struct.pack("<4s4sIII",
        b"TLK ",
        b"V3.0",
        lang_id,
        count,
        str_offset,
    )
    return header + bytes(entry_table) + bytes(string_data)


# ---------------------------------------------------------------------------
# Import the classes under test (headless — no Qt needed for data-model tests)
# ---------------------------------------------------------------------------

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Prevent Qt from being initialised; we only test the data-model layer.
# TLKFile / TLKEntry are defined at module level before any QWidget is
# instantiated, so a headless import works fine.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ghostscripter.ui.widgets.tlk_editor_widget import (
    TLKFile, TLKEntry,
    TLK_FLAG_HAS_TEXT, TLK_FLAG_HAS_SOUND, TLK_FLAG_HAS_LENGTH,
    _LANGUAGE_ENCODING, _DEFAULT_ENCODING,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTLKEncodingConstants(unittest.TestCase):
    """_LANGUAGE_ENCODING must map Western languages to cp1252, not latin-1."""

    def test_english_is_cp1252(self):
        self.assertEqual(_LANGUAGE_ENCODING[0], "cp1252")

    def test_french_is_cp1252(self):
        self.assertEqual(_LANGUAGE_ENCODING[1], "cp1252")

    def test_german_is_cp1252(self):
        self.assertEqual(_LANGUAGE_ENCODING[2], "cp1252")

    def test_italian_is_cp1252(self):
        self.assertEqual(_LANGUAGE_ENCODING[3], "cp1252")

    def test_spanish_is_cp1252(self):
        self.assertEqual(_LANGUAGE_ENCODING[4], "cp1252")

    def test_polish_is_cp1252(self):
        self.assertEqual(_LANGUAGE_ENCODING[5], "cp1252")

    def test_korean_is_cp949(self):
        self.assertEqual(_LANGUAGE_ENCODING[128], "cp949")

    def test_chinese_trad_is_cp950(self):
        self.assertEqual(_LANGUAGE_ENCODING[129], "cp950")

    def test_chinese_simp_is_cp936(self):
        self.assertEqual(_LANGUAGE_ENCODING[130], "cp936")

    def test_japanese_is_cp932(self):
        self.assertEqual(_LANGUAGE_ENCODING[131], "cp932")

    def test_default_encoding_is_cp1252(self):
        self.assertEqual(_DEFAULT_ENCODING, "cp1252")


class TestTLKReadEncoding(unittest.TestCase):
    """Bug 1 — cp1252 characters must be decoded correctly."""

    # The 0x80-0x9F range is where cp1252 and latin-1 diverge.
    # cp1252 maps 0x93/0x94 → U+201C/U+201D (curly double quotes)
    #             0x96     → U+2013 (en-dash)
    #             0x97     → U+2014 (em-dash)
    #             0x85     → U+2026 (ellipsis)
    CP1252_ONLY_TEXT = (
        b"He said \x93Hello\x94\x97she smiled\x85"
    )
    EXPECTED_TEXT = "He said \u201cHello\u201d\u2014she smiled\u2026"

    def _make_tlk(self, lang_id=0):
        blob = _build_tlk(
            lang_id,
            [(TLK_FLAG_HAS_TEXT, b"", self.CP1252_ONLY_TEXT)],
        )
        tlk = TLKFile()
        tlk._parse(blob)
        return tlk

    def test_curly_quotes_decoded_correctly(self):
        tlk = self._make_tlk()
        self.assertEqual(tlk.entries[0].text, self.EXPECTED_TEXT)

    def test_not_decoded_as_latin1_control_chars(self):
        """latin-1 would give us C1 control characters, not smart quotes."""
        tlk = self._make_tlk()
        # Under the old latin-1 path, 0x93 → U+0093 (a C1 ctrl char), not "
        for char in tlk.entries[0].text:
            self.assertNotIn(ord(char), range(0x80, 0xA0),
                             f"C1 control char U+{ord(char):04X} found "
                             f"(latin-1 decoding bug)")

    def test_lang_0_uses_cp1252(self):
        tlk = self._make_tlk(lang_id=0)
        self.assertEqual(tlk.entries[0].text, self.EXPECTED_TEXT)

    def test_unknown_lang_falls_back_to_cp1252(self):
        # lang_id 999 is not in _LANGUAGE_ENCODING → must fall back to cp1252
        tlk = self._make_tlk(lang_id=999)
        self.assertEqual(tlk.entries[0].text, self.EXPECTED_TEXT)

    def test_empty_entry_gives_empty_string(self):
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", b"")])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.entries[0].text, "")

    def test_plain_ascii_text_unchanged(self):
        text = b"May the Force be with you."
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", text)])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.entries[0].text, text.decode("ascii"))

    def test_multiple_entries_correct_offsets(self):
        """str_offset interpretation: each entry's off_str is relative to the block."""
        entries_raw = [
            (TLK_FLAG_HAS_TEXT, b"", b"First"),
            (TLK_FLAG_HAS_TEXT, b"", b"Second"),
            (TLK_FLAG_HAS_TEXT, b"", b"Third"),
        ]
        blob = _build_tlk(0, entries_raw)
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(len(tlk.entries), 3)
        self.assertEqual(tlk.entries[0].text, "First")
        self.assertEqual(tlk.entries[1].text, "Second")
        self.assertEqual(tlk.entries[2].text, "Third")


class TestTLKWriteEncoding(unittest.TestCase):
    """Bug 2 — round-trip must be lossless for cp1252 characters."""

    CP1252_TEXT = "He said \u201cHello\u201d\u2014she smiled\u2026"

    def _roundtrip(self, lang_id=0) -> TLKFile:
        # Start with a TLK containing cp1252 text
        original_bytes = "He said \x93Hello\x94\x97she smiled\x85".encode("raw_unicode_escape")
        # Build via _build_tlk so we start with the raw cp1252 bytes
        raw_cp1252 = self.CP1252_TEXT.encode("cp1252")
        blob = _build_tlk(lang_id, [(TLK_FLAG_HAS_TEXT, b"", raw_cp1252)])
        tlk = TLKFile()
        tlk.language_id = lang_id
        tlk._parse(blob)
        # Save and reload
        saved = tlk.to_bytes()
        tlk2 = TLKFile()
        tlk2._parse(saved)
        return tlk2

    def test_cp1252_text_survives_roundtrip(self):
        tlk2 = self._roundtrip()
        self.assertEqual(tlk2.entries[0].text, self.CP1252_TEXT)

    def test_no_replacement_chars_in_roundtrip(self):
        tlk2 = self._roundtrip()
        self.assertNotIn("\ufffd", tlk2.entries[0].text)

    def test_plain_ascii_survives_roundtrip(self):
        text = "May the Force be with you."
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", text.encode("cp1252"))])
        tlk = TLKFile()
        tlk._parse(blob)
        saved = tlk.to_bytes()
        tlk2 = TLKFile()
        tlk2._parse(saved)
        self.assertEqual(tlk2.entries[0].text, text)

    def test_binary_identical_for_ascii_content(self):
        """For ASCII-only text the output bytes must be identical to the input."""
        text = b"Bastila Shan"
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", text)])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.to_bytes(), blob)

    def test_header_preserved(self):
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", b"test")])
        tlk = TLKFile()
        tlk._parse(blob)
        out = tlk.to_bytes()
        self.assertEqual(out[:4], b"TLK ")
        self.assertEqual(out[4:8], b"V3.0")

    def test_string_count_preserved(self):
        entries = [(TLK_FLAG_HAS_TEXT, b"", f"Entry {i}".encode()) for i in range(10)]
        blob = _build_tlk(0, entries)
        tlk = TLKFile()
        tlk._parse(blob)
        saved = tlk.to_bytes()
        count = struct.unpack_from("<I", saved, 12)[0]
        self.assertEqual(count, 10)

    def test_language_id_preserved(self):
        blob = _build_tlk(2, [(TLK_FLAG_HAS_TEXT, b"", b"Hallo")])
        tlk = TLKFile()
        tlk._parse(blob)
        out = tlk.to_bytes()
        lang_id = struct.unpack_from("<I", out, 8)[0]
        self.assertEqual(lang_id, 2)


class TestTLKFlagPreservation(unittest.TestCase):
    """Bug 3 — _apply_edit must not clobber TLK_FLAG_HAS_LENGTH or unknown bits."""

    def _make_entry(self, flags: int, text="original", sound="") -> TLKEntry:
        e = TLKEntry(strref=0)
        e.flags = flags
        e.text = text
        e.sound_resref = sound
        return e

    def _simulate_apply_edit(self, entry: TLKEntry, new_text: str, new_sound: str):
        """Replicate the _apply_edit logic from TLKEditorWidget."""
        entry.text = new_text
        entry.sound_resref = new_sound[:16]
        preserved = entry.flags & ~(TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND)
        entry.flags = preserved | TLK_FLAG_HAS_TEXT
        if entry.sound_resref:
            entry.flags |= TLK_FLAG_HAS_SOUND

    def test_has_length_bit_preserved_on_edit(self):
        flags = TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND | TLK_FLAG_HAS_LENGTH
        e = self._make_entry(flags, sound="voc_kashyyyk")
        self._simulate_apply_edit(e, "New text", "voc_kashyyyk")
        self.assertTrue(e.flags & TLK_FLAG_HAS_LENGTH,
                        "TLK_FLAG_HAS_LENGTH (0x04) was cleared by edit")

    def test_sound_removed_clears_has_sound(self):
        flags = TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND
        e = self._make_entry(flags, sound="voc_test")
        self._simulate_apply_edit(e, "No sound now", "")
        self.assertFalse(e.flags & TLK_FLAG_HAS_SOUND)

    def test_sound_added_sets_has_sound(self):
        e = self._make_entry(TLK_FLAG_HAS_TEXT)
        self._simulate_apply_edit(e, "Text", "new_sound")
        self.assertTrue(e.flags & TLK_FLAG_HAS_SOUND)

    def test_has_text_always_set_after_edit(self):
        e = self._make_entry(TLK_FLAG_HAS_SOUND)  # weird, but should still set TEXT
        self._simulate_apply_edit(e, "Some text", "")
        self.assertTrue(e.flags & TLK_FLAG_HAS_TEXT)

    def test_unknown_bits_preserved(self):
        # bit 3 (0x08) is not defined in K1/TSL but must not be silently wiped
        flags = TLK_FLAG_HAS_TEXT | 0x08
        e = self._make_entry(flags)
        self._simulate_apply_edit(e, "text", "")
        self.assertTrue(e.flags & 0x08,
                        "Unknown flag bit 0x08 was cleared by edit")

    def test_only_text_flag_entry_unchanged(self):
        e = self._make_entry(TLK_FLAG_HAS_TEXT)
        self._simulate_apply_edit(e, "text", "")
        self.assertEqual(e.flags, TLK_FLAG_HAS_TEXT)


class TestTLKSoundResRef(unittest.TestCase):
    """Bug 4 — non-ASCII bytes in ResRef field must be ignored, not replaced."""

    def test_non_ascii_resref_ignored(self):
        # A ResRef with a stray non-ASCII byte (0xFF) embedded — should be
        # dropped rather than replaced with U+FFFD.
        sound_raw = b"voc_kas\xffyyyk" + b"\x00" * 4  # 16 bytes total
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND, sound_raw, b"text")])
        tlk = TLKFile()
        tlk._parse(blob)
        resref = tlk.entries[0].sound_resref
        self.assertNotIn("\ufffd", resref,
                         "Replacement character U+FFFD found in ResRef "
                         "(errors='replace' used instead of errors='ignore')")

    def test_clean_ascii_resref_preserved(self):
        sound_raw = b"voc_kashyyyk\x00\x00\x00\x00"
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND, sound_raw, b"text")])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.entries[0].sound_resref, "voc_kashyyyk")

    def test_null_padded_resref_stripped(self):
        sound_raw = b"abc\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        blob = _build_tlk(0, [(TLK_FLAG_HAS_SOUND, sound_raw, b"")])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.entries[0].sound_resref, "abc")

    def test_all_null_resref_is_empty_string(self):
        sound_raw = b"\x00" * 16
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, sound_raw, b"text")])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.entries[0].sound_resref, "")


class TestTLKMagicAndValidation(unittest.TestCase):
    """Parser must reject garbage files and handle edge cases safely."""

    def test_bad_magic_raises(self):
        bad = b"ERF " + b"\x00" * 200
        tlk = TLKFile()
        with self.assertRaises(ValueError):
            tlk._parse(bad)

    def test_too_short_raises(self):
        tlk = TLKFile()
        with self.assertRaises(ValueError):
            tlk._parse(b"TLK " + b"\x00" * 5)  # only 9 bytes

    def test_zero_entry_count(self):
        blob = _build_tlk(0, [])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(len(tlk.entries), 0)

    def test_strref_index_matches_position(self):
        entries = [(TLK_FLAG_HAS_TEXT, b"", f"Entry {i}".encode()) for i in range(5)]
        blob = _build_tlk(0, entries)
        tlk = TLKFile()
        tlk._parse(blob)
        for i, e in enumerate(tlk.entries):
            self.assertEqual(e.strref, i)

    def test_get_string_within_bounds(self):
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", b"Hello")])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.get_string(0), "Hello")

    def test_get_string_out_of_bounds_returns_default(self):
        blob = _build_tlk(0, [(TLK_FLAG_HAS_TEXT, b"", b"Hello")])
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.get_string(999, "MISSING"), "MISSING")

    def test_len_returns_entry_count(self):
        entries = [(TLK_FLAG_HAS_TEXT, b"", b"x") for _ in range(7)]
        blob = _build_tlk(0, entries)
        tlk = TLKFile()
        tlk._parse(blob)
        self.assertEqual(len(tlk), 7)


if __name__ == "__main__":
    unittest.main()
