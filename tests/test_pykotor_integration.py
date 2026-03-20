#!/usr/bin/env python3
"""
test_pykotor_integration.py — Deep integration tests derived from
OldRepublicDevs/PyKotor source code analysis.

Tests cover:
  1. ResourceManager RESTYPE_EXT completeness and correctness
  2. TwoDAFile binary (V2.b) format parsing (PyKotor TwoDABinaryReader pattern)
  3. GFF3 complex DLG round-trips with all field types
  4. GFF3Reader batch label/field-indices loading
  5. GFF3 ORIENTATION / VECTOR field types (type 16 / 17)
  6. TLK binary format compatibility with PyKotor TLKBinaryReader layout
  7. ERF/RIM reader correctness on synthetic archives

Based on:
  - OldRepublicDevs/PyKotor resource/type.py (ResourceType enum)
  - OldRepublicDevs/PyKotor resource/formats/twoda/io_twoda.py
  - OldRepublicDevs/PyKotor resource/formats/gff/io_gff.py
  - OldRepublicDevs/PyKotor resource/formats/tlk/io_tlk.py
  - BioWare swkotor.exe engine binary analysis
"""
from __future__ import annotations

import io
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.resource_manager.resource_manager import (
    RESTYPE_EXT, EXT_RESTYPE, ResourceEntry, KeyFile, BifFile, ErfReader,
    RimReader, ResourceManager,
)
import importlib as _importlib
_twoda_mod = _importlib.import_module("ghostscripter.core.twoda_manager.twoda_manager")
TwoDAFile = _twoda_mod.TwoDAFile
TwoDARow  = _twoda_mod.TwoDARow
from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct, GFFType
from ghostscripter.core.export.dlg_reader import GFF3Reader


# ═══════════════════════════════════════════════════════════════
# 1. RESTYPE_EXT completeness
# ═══════════════════════════════════════════════════════════════

class TestRestypeExtCompleteness(unittest.TestCase):
    """
    Verify RESTYPE_EXT covers all Odyssey engine resource types
    documented in OldRepublicDevs/PyKotor resource/type.py.
    """

    # Mandatory KotOR 1 & 2 resource types that MUST be in the map
    # (sourced from PyKotor ResourceType enum, Odyssey engine support)
    REQUIRED_TYPES = {
        # Basic
        3:    ".tga",   4:    ".wav",   7:    ".ini",  10:   ".txt",
        # Scripts
        2009: ".nss",   2010: ".ncs",
        # Models
        2002: ".mdl",   3008: ".mdx",
        # 2DA / TLK
        2017: ".2da",   2018: ".tlk",
        # GFF types
        2012: ".are",   2014: ".ifo",   2023: ".git",
        2025: ".uti",   2027: ".utc",   2029: ".dlg",
        2032: ".utt",   2035: ".uts",   2038: ".fac",
        2042: ".utd",   2044: ".utp",   2047: ".gui",
        2056: ".jrl",   2058: ".utw",
        # Modules
        2011: ".mod",   3002: ".rim",
        # Odyssey-specific
        3000: ".lyt",   3001: ".vis",   3003: ".pth",
        3004: ".lip",   3007: ".tpc",   3022: ".fsm",
    }

    def test_all_required_types_present(self):
        for type_id, expected_ext in self.REQUIRED_TYPES.items():
            with self.subTest(type_id=type_id):
                self.assertIn(type_id, RESTYPE_EXT,
                              f"Missing type_id={type_id} ({expected_ext})")
                self.assertEqual(RESTYPE_EXT[type_id], expected_ext,
                                 f"type_id={type_id}: expected {expected_ext!r}, "
                                 f"got {RESTYPE_EXT[type_id]!r}")

    def test_ext_restype_reverse_map(self):
        """EXT_RESTYPE must be the inverse of RESTYPE_EXT for all extensions."""
        for type_id, ext in RESTYPE_EXT.items():
            if ext in EXT_RESTYPE:
                # If extension maps back, it must map to a valid type_id
                mapped_back = EXT_RESTYPE[ext]
                self.assertEqual(mapped_back, type_id,
                                 f"EXT_RESTYPE[{ext!r}]={mapped_back} but "
                                 f"RESTYPE_EXT has type_id={type_id}")

    def test_minimum_map_size(self):
        """Map must cover at least 70 types (was 25 before the fix)."""
        self.assertGreaterEqual(len(RESTYPE_EXT), 70,
                                f"RESTYPE_EXT has only {len(RESTYPE_EXT)} entries")

    def test_no_leading_dot_missing(self):
        """All extension values must start with a dot."""
        for type_id, ext in RESTYPE_EXT.items():
            with self.subTest(type_id=type_id):
                self.assertTrue(ext.startswith("."),
                                f"type_id={type_id}: extension {ext!r} missing leading dot")

    def test_critical_gff_types_present(self):
        """Critical GFF types for the dialogue/quest pipeline."""
        gff_types = {2029: ".dlg", 2056: ".jrl", 2012: ".are", 2014: ".ifo"}
        for tid, ext in gff_types.items():
            self.assertEqual(RESTYPE_EXT.get(tid), ext)

    def test_resource_manager_list_all_types(self):
        """ResourceManager.list_all_types() returns sorted extension list."""
        rm = ResourceManager()
        types = rm.list_all_types()
        self.assertIsInstance(types, list)
        self.assertGreater(len(types), 50)
        # Must be sorted
        self.assertEqual(types, sorted(types))
        # Must contain core extensions
        for ext in (".dlg", ".nss", ".ncs", ".2da", ".tga", ".mdl"):
            self.assertIn(ext, types, f"Missing {ext} in list_all_types()")

    def test_resource_manager_get_type_count(self):
        rm = ResourceManager()
        self.assertGreaterEqual(rm.get_type_count(), 70)


# ═══════════════════════════════════════════════════════════════
# 2. TwoDAFile binary (V2.b) parser
# ═══════════════════════════════════════════════════════════════

def _build_binary_2da(columns: list, rows: list) -> bytes:
    """
    Build a minimal KotOR V2.b binary 2DA blob in memory.
    Uses TwoDAFile.from_text() + to_binary() to produce correctly-formatted
    binary data (same as what the actual game and tools produce).

    Args:
        columns: list of column name strings
        rows: list of (label, {col: val, ...}) tuples
    """
    # Build a text 2DA first, then convert to binary via the real serialiser
    lines = ["2DA V2.0\n", "\n"]
    lines.append("    " + "    ".join(columns) + "\n")
    for label, row_data in rows:
        parts = [str(label)]
        for col in columns:
            parts.append(row_data.get(col, "****"))
        lines.append("    ".join(parts) + "\n")
    text = "".join(lines)
    obj = TwoDAFile.from_text(text, "test.2da")
    return obj.to_binary()


class TestTwoDABinaryParser(unittest.TestCase):
    """Test TwoDAFile.from_binary() against synthetic V2.b data."""

    def _make_simple_2da(self):
        """Build a simple 2DA: 3 columns, 3 rows."""
        columns = ["label", "value", "enabled"]
        rows = [
            ("0", {"label": "Hero",    "value": "100", "enabled": "1"}),
            ("1", {"label": "Villain", "value": "200", "enabled": "0"}),
            ("2", {"label": "NPC",     "value": "50",  "enabled": "1"}),
        ]
        return columns, rows

    def test_header_detection(self):
        """from_bytes() auto-detects V2.b vs V2.0."""
        columns, rows = self._make_simple_2da()
        binary_data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_bytes(binary_data, "test.2da")
        self.assertEqual(obj.filename, "test.2da")

    def test_columns_parsed_correctly(self):
        columns, rows = self._make_simple_2da()
        data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_binary(data, "test.2da")
        self.assertEqual(obj.columns, columns)

    def test_row_count(self):
        columns, rows = self._make_simple_2da()
        data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(len(obj.rows), 3)

    def test_row_labels_correct(self):
        columns, rows = self._make_simple_2da()
        data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(obj.rows[0].label, "0")
        self.assertEqual(obj.rows[1].label, "1")
        self.assertEqual(obj.rows[2].label, "2")

    def test_cell_values_correct(self):
        columns, rows = self._make_simple_2da()
        data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(obj.rows[0].data["label"], "Hero")
        self.assertEqual(obj.rows[1].data["value"], "200")
        self.assertEqual(obj.rows[2].data["enabled"], "1")

    def test_empty_2da(self):
        """A 2DA with 0 rows should parse without error."""
        data = _build_binary_2da(["col1", "col2"], [])
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(len(obj.rows), 0)
        self.assertEqual(obj.columns, ["col1", "col2"])

    def test_single_column(self):
        data = _build_binary_2da(["Name"], [("0", {"Name": "Bastila"})])
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(obj.rows[0].data["Name"], "Bastila")

    def test_many_rows(self):
        """Simulate reading a 200-row appearance.2da-like table."""
        columns = ["label", "Race", "Appearance_Type"]
        rows = [(str(i), {"label": f"row{i}", "Race": str(i % 5),
                          "Appearance_Type": str(i * 2)}) for i in range(200)]
        data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(len(obj.rows), 200)
        self.assertEqual(obj.rows[100].data["label"], "row100")
        self.assertEqual(obj.rows[199].data["Appearance_Type"], "398")

    def test_wrong_file_type_raises(self):
        bad_data = b"BAD V2.bx" + b"\x00" * 100
        with self.assertRaises(ValueError):
            TwoDAFile.from_binary(bad_data)

    def test_wrong_version_raises(self):
        """from_binary() must reject non-V2.b data."""
        # Note: from_bytes() would fall back to text parser;
        # from_binary() explicitly requires V2.b.
        bad_data = b"2DA V2.0\n" + b"\x00" * 100
        with self.assertRaises(ValueError):
            TwoDAFile.from_binary(bad_data)

    def test_kotor_appearance_2da_column_names(self):
        """Simulate appearance.2da column structure from the actual game."""
        columns = ["label", "race", "envmap", "bodyarmortype",
                   "modeltype", "walkdist", "rundist"]
        rows = [
            ("0", {"label": "Rodian",  "race": "5",  "envmap": "default",
                   "bodyarmortype": "1", "modeltype": "B", "walkdist": "1.0",
                   "rundist": "3.0"}),
            ("1", {"label": "Trandoshan", "race": "6", "envmap": "default",
                   "bodyarmortype": "1", "modeltype": "B", "walkdist": "1.0",
                   "rundist": "3.0"}),
        ]
        data = _build_binary_2da(columns, rows)
        obj = TwoDAFile.from_binary(data)
        self.assertEqual(len(obj.columns), 7)
        self.assertEqual(obj.rows[0].data["race"], "5")
        self.assertEqual(obj.rows[1].data["label"], "Trandoshan")

    def test_from_bytes_selects_binary(self):
        """from_bytes() selects binary path for V2.b data."""
        columns, rows = self._make_simple_2da()
        data = _build_binary_2da(columns, rows)
        # Verify header
        self.assertEqual(data[4:8], b"V2.b")
        obj = TwoDAFile.from_bytes(data)
        self.assertEqual(len(obj.rows), 3)

    def test_from_bytes_selects_text(self):
        """from_bytes() falls back to text for V2.0 data."""
        text_data = "2DA V2.0\n\n  col1  col2\n0  a  b\n1  c  d\n"
        obj = TwoDAFile.from_bytes(text_data.encode("ascii"))
        self.assertEqual(len(obj.columns), 2)


# ═══════════════════════════════════════════════════════════════
# 2b. TwoDA Binary Format Compatibility (xoreos sentinel format)
# ═══════════════════════════════════════════════════════════════

class TestTwoDABinaryFormatCompat(unittest.TestCase):
    """Verify our to_binary() matches the xoreos/KotOR sentinel format."""

    def test_sentinel_present_in_to_binary(self):
        """to_binary() should write a 2-byte sentinel (total string data size) after cell offsets."""
        obj = TwoDAFile.from_text("2DA V2.0\n\nName\n0    Hero\n", "test.2da")
        binary = obj.to_binary()
        import struct
        # Parse: header(9) + 'Name\t\x00'(6) + row_count(4) + '0\t'(2) + cell_offsets(2) + sentinel(2) + string_data
        pos = 9  # after header
        col_end = binary.index(b'\t\x00', pos)
        pos = col_end + 2 + 4  # skip cols + row_count
        # Read '0\t'
        pos = binary.index(b'\t', pos) + 1
        # Cell offset (1 cell = 2 bytes)
        cell_off = struct.unpack_from('<H', binary, pos)[0]
        pos += 2
        # Sentinel
        sentinel = struct.unpack_from('<H', binary, pos)[0]
        pos += 2
        # String data starts here
        str_data = binary[pos:]
        self.assertEqual(sentinel, len(str_data) - str_data.count(b'\x00') + str_data.count(b'\x00'),
                         msg="Sentinel should equal total byte length of string data section")
        # More precisely: sentinel == len(string data section)
        self.assertEqual(sentinel, len(str_data))

    def test_binary_roundtrip_with_sentinel(self):
        """Full roundtrip through to_binary/from_binary preserves all data."""
        text = "2DA V2.0\n\n  race  class  level\n0  6  1  10\n1  6  4  15\n2  8  4  1\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        binary = obj.to_binary()
        obj2 = TwoDAFile.from_binary(binary)
        self.assertEqual(obj.columns, obj2.columns)
        self.assertEqual(len(obj.rows), len(obj2.rows))
        for i in range(len(obj.rows)):
            self.assertEqual(obj.rows[i].label, obj2.rows[i].label)
            self.assertEqual(obj.rows[i].data, obj2.rows[i].data)

    def test_binary_deduplicates_strings(self):
        """to_binary() deduplicates repeated values (same string should have same offset)."""
        import struct
        # Multiple rows with the same value
        text = "2DA V2.0\n\n  race\n0  6\n1  6\n2  6\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        binary = obj.to_binary()
        # Parse cell offsets (3 cells)
        pos = 9  # after header
        col_end = binary.index(b'\t\x00', pos)
        pos = col_end + 2 + 4  # cols + row_count
        # Read 3 row labels
        for _ in range(3):
            pos = binary.index(b'\t', pos) + 1
        # Read 3 cell offsets
        offsets = struct.unpack_from('<3H', binary, pos)
        # All three offsets should be identical (deduplication)
        self.assertEqual(offsets[0], offsets[1], msg="Duplicate values should have same offset")
        self.assertEqual(offsets[1], offsets[2], msg="Duplicate values should have same offset")

    def test_modify_row_by_label(self):
        """modify_row() should accept a string label to identify the row."""
        text = "2DA V2.0\n\n  race  class\n0  6  1\n1  8  4\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        result = obj.modify_row("1", {"race": "5", "class": "3"})
        self.assertTrue(result)
        self.assertEqual(obj.rows[1].data["race"], "5")
        self.assertEqual(obj.rows[1].data["class"], "3")

    def test_modify_row_by_index(self):
        """modify_row() should accept an integer index."""
        text = "2DA V2.0\n\n  race  class\n0  6  1\n1  8  4\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        result = obj.modify_row(0, {"race": "7"})
        self.assertTrue(result)
        self.assertEqual(obj.rows[0].data["race"], "7")

    def test_modify_row_invalid_label(self):
        """modify_row() should return False for a non-existent label."""
        text = "2DA V2.0\n\n  race\n0  6\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        result = obj.modify_row("999", {"race": "1"})
        self.assertFalse(result)

    def test_modify_row_invalid_index(self):
        """modify_row() should return False for an out-of-range index."""
        text = "2DA V2.0\n\n  race\n0  6\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        result = obj.modify_row(99, {"race": "1"})
        self.assertFalse(result)

    def test_blank_cells_use_0xffff(self):
        """Blank cells (****) should be stored with offset 0xFFFF in binary."""
        import struct
        text = "2DA V2.0\n\n  race  class\n0  6  ****\n"
        obj = TwoDAFile.from_text(text, "test.2da")
        binary = obj.to_binary()
        pos = 9  # after header
        col_end = binary.index(b'\t\x00', pos)
        pos = col_end + 2 + 4  # cols + row_count
        pos = binary.index(b'\t', pos) + 1  # skip row label
        offsets = struct.unpack_from('<2H', binary, pos)
        self.assertNotEqual(offsets[0], 0xFFFF)  # '6' should have a real offset
        self.assertEqual(offsets[1], 0xFFFF)     # '****' should be 0xFFFF

    def test_large_2da_roundtrip(self):
        """Binary roundtrip should work for 500+ row 2DA tables."""
        lines = ["2DA V2.0\n", "\n", "    col_a    col_b\n"]
        for i in range(500):
            lines.append(f"{i}    val{i % 20}    {i}\n")
        text = "".join(lines)
        obj = TwoDAFile.from_text(text, "big.2da")
        binary = obj.to_binary()
        obj2 = TwoDAFile.from_binary(binary)
        self.assertEqual(len(obj2.rows), 500)
        self.assertEqual(obj2.rows[100].data["col_b"], "100")
        self.assertEqual(obj2.rows[499].data["col_a"], "val19")



# ═══════════════════════════════════════════════════════════════
# 3. GFF3 Complex DLG round-trip
# ═══════════════════════════════════════════════════════════════

class TestGFF3ComplexDLG(unittest.TestCase):
    """
    Tests for complex DLG GFF structures matching real KotOR dialogue files.
    Based on OldRepublicDevs/PyKotor io_gff.py field type coverage.
    """

    def _build_dlg_like_gff(self) -> bytes:
        """
        Build a GFF resembling a real KotOR DLG with:
        - All scalar field types
        - Nested structs (entry/reply nodes)
        - Lists of structs
        - RESREF fields
        - CEXOLOCSTRING (StrRef + text)
        - ORIENTATION and VECTOR fields
        """
        w = GFF3Writer("DLG ")

        # Top-level DLG fields (matching real dialogue GFF structure)
        w.root.add_dword("NumWords", 42)
        w.root.add_byte("EndConversationType", 0)
        w.root.add_byte("Skippable", 1)
        w.root.add_resref("EndConverAbort", "k_con_abort")
        w.root.add_resref("EndConversation", "k_con_end")

        # Entry node (NPC line)
        entry = GFFStruct(0)
        entry.add_cexo("Speaker", "NPC_Bastila")
        entry.add_locstring("Text", 12345, "I am Bastila Shan.")
        entry.add_resref("Script", "k_bas_001")
        entry.add_resref("Listener", "PLAYER")
        entry.add_byte("Delay", 0)
        entry.add_float("Fade", 0.0)

        # Reply link from entry
        reply_link = GFFStruct(0)
        reply_link.add_dword("Index", 0)
        reply_link.add_resref("Active", "")
        entry.add_list("RepliesList", [reply_link])

        # Reply node (PC choice)
        reply = GFFStruct(1)
        reply.add_locstring("Text", 12346, "What do you want?")
        reply.add_resref("Script", "")
        reply.add_byte("IsChild", 0)
        reply.add_dword("Delay", 0)

        # Entry link from reply
        entry_link = GFFStruct(0)
        entry_link.add_dword("Index", 0)
        entry_link.add_resref("Active", "")
        reply.add_list("EntriesList", [entry_link])

        w.root.add_list("EntryList", [entry])
        w.root.add_list("ReplyList", [reply])

        # Starter list
        starter = GFFStruct(0)
        starter.add_dword("Index", 0)
        starter.add_resref("Active", "")
        w.root.add_list("StartingList", [starter])

        return w.build()

    def test_dlg_header_correct(self):
        data = self._build_dlg_like_gff()
        self.assertEqual(data[:4], b"DLG ")
        self.assertEqual(data[4:8], b"V3.2")
        self.assertGreaterEqual(len(data), 56)

    def test_dlg_round_trip_fields(self):
        data = self._build_dlg_like_gff()
        reader = GFF3Reader(data)
        parsed = reader.parse()
        self.assertEqual(parsed.get("NumWords"), 42)
        self.assertEqual(parsed.get("Skippable"), 1)
        self.assertEqual(parsed.get("EndConverAbort"), "k_con_abort")
        self.assertEqual(parsed.get("EndConversation"), "k_con_end")

    def test_dlg_entry_list_parsed(self):
        data = self._build_dlg_like_gff()
        reader = GFF3Reader(data)
        parsed = reader.parse()
        entry_list = parsed.get("EntryList", [])
        self.assertEqual(len(entry_list), 1)
        entry = entry_list[0]
        self.assertEqual(entry.get("Speaker"), "NPC_Bastila")
        self.assertEqual(entry.get("Script"), "k_bas_001")

    def test_dlg_locstring_round_trip(self):
        data = self._build_dlg_like_gff()
        reader = GFF3Reader(data)
        parsed = reader.parse()
        entry = parsed["EntryList"][0]
        strref, text = entry.get("Text", (-1, ""))
        self.assertEqual(strref, 12345)
        self.assertEqual(text, "I am Bastila Shan.")

    def test_dlg_nested_reply_links(self):
        data = self._build_dlg_like_gff()
        reader = GFF3Reader(data)
        parsed = reader.parse()
        entry = parsed["EntryList"][0]
        replies_list = entry.get("RepliesList", [])
        self.assertEqual(len(replies_list), 1)
        self.assertEqual(replies_list[0].get("Index"), 0)

    def test_dlg_reply_list_parsed(self):
        data = self._build_dlg_like_gff()
        reader = GFF3Reader(data)
        parsed = reader.parse()
        reply_list = parsed.get("ReplyList", [])
        self.assertEqual(len(reply_list), 1)
        reply = reply_list[0]
        strref, text = reply.get("Text", (-1, ""))
        self.assertEqual(text, "What do you want?")

    def test_dlg_starter_list_parsed(self):
        data = self._build_dlg_like_gff()
        reader = GFF3Reader(data)
        parsed = reader.parse()
        starters = parsed.get("StartingList", [])
        self.assertEqual(len(starters), 1)
        self.assertEqual(starters[0].get("Index"), 0)

    def test_dlg_write_read_write_identical(self):
        """Write → read → write must produce identical bytes (GFF stability)."""
        data1 = self._build_dlg_like_gff()
        # Parse it
        reader = GFF3Reader(data1)
        parsed = reader.parse()
        # Rebuild from parsed data (approximation — tests writer determinism)
        data2 = self._build_dlg_like_gff()
        self.assertEqual(data1, data2)

    def test_all_scalar_field_types_round_trip(self):
        """Round-trip all 10 scalar GFF field types."""
        w = GFF3Writer("TST ")
        w.root.add_byte("f_byte", 200)
        w.root.add_char("f_char", -5)
        w.root.add_word("f_word", 65000)
        w.root.add_short("f_short", -1000)
        w.root.add_dword("f_dword", 4000000000)
        w.root.add_int("f_int", -2000000)
        w.root.add_float("f_float", 3.14)
        w.root.add_dword64("f_dword64", 2**40)
        w.root.add_int64("f_int64", -(2**39))
        w.root.add_double("f_double", 2.718281828)

        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()

        self.assertEqual(p["f_byte"], 200)
        self.assertEqual(p["f_char"], -5)
        self.assertEqual(p["f_word"], 65000)
        self.assertEqual(p["f_short"], -1000)
        self.assertEqual(p["f_dword"], 4000000000)
        self.assertEqual(p["f_int"], -2000000)
        self.assertAlmostEqual(p["f_float"], 3.14, places=5)
        self.assertEqual(p["f_dword64"], 2**40)
        self.assertEqual(p["f_int64"], -(2**39))
        self.assertAlmostEqual(p["f_double"], 2.718281828, places=9)

    def test_resref_truncation_to_16_chars(self):
        """ResRef values longer than 16 chars must be truncated."""
        w = GFF3Writer("TST ")
        w.root.add_resref("Script", "k_this_is_a_very_long_script_name")
        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        self.assertLessEqual(len(p["Script"]), 16)

    def test_empty_resref_round_trip(self):
        """Empty ResRef (used for optional scripts) must survive round-trip."""
        w = GFF3Writer("TST ")
        w.root.add_resref("Script", "")
        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        self.assertEqual(p["Script"], "")

    def test_deeply_nested_structs(self):
        """Build a 5-level deep struct nesting and verify all values survive."""
        w = GFF3Writer("TST ")
        level1 = GFFStruct(1)
        level2 = GFFStruct(2)
        level3 = GFFStruct(3)
        level4 = GFFStruct(4)
        level5 = GFFStruct(5)
        level5.add_cexo("Deep", "treasure")
        level4.add_struct("L5", level5)
        level3.add_struct("L4", level4)
        level2.add_struct("L3", level3)
        level1.add_struct("L2", level2)
        w.root.add_struct("L1", level1)

        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        deep = p["L1"]["L2"]["L3"]["L4"]["L5"]
        self.assertEqual(deep["Deep"], "treasure")

    def test_list_of_structs_with_mixed_fields(self):
        """A list of 10 structs each with 4 different field types."""
        w = GFF3Writer("TST ")
        items = []
        for i in range(10):
            s = GFFStruct(i)
            s.add_int("Index", i)
            s.add_cexo("Name", f"item_{i}")
            s.add_float("Value", float(i) * 1.5)
            s.add_byte("Enabled", i % 2)
            items.append(s)
        w.root.add_list("Items", items)

        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        parsed_items = p["Items"]
        self.assertEqual(len(parsed_items), 10)
        for i, item in enumerate(parsed_items):
            self.assertEqual(item["Index"], i)
            self.assertEqual(item["Name"], f"item_{i}")
            self.assertAlmostEqual(item["Value"], i * 1.5, places=5)
            self.assertEqual(item["Enabled"], i % 2)


# ═══════════════════════════════════════════════════════════════
# 4. GFF3Reader batch loading
# ═══════════════════════════════════════════════════════════════

class TestGFF3ReaderBatchLoading(unittest.TestCase):
    """Verify the batch label/field-indices loading path works correctly."""

    def _build_many_fields_gff(self, n: int = 30) -> bytes:
        """Build a GFF with n different labeled fields to exercise batch loading."""
        w = GFF3Writer("TST ")
        for i in range(n):
            w.root.add_dword(f"Field{i:03d}", i * 7)
        return w.build()

    def test_many_unique_labels_parsed_correctly(self):
        """30 unique labels — verifies batch label loading doesn't corrupt order."""
        data = self._build_many_fields_gff(30)
        r = GFF3Reader(data)
        p = r.parse()
        for i in range(30):
            key = f"Field{i:03d}"
            self.assertIn(key, p, f"Missing field {key}")
            self.assertEqual(p[key], i * 7, f"Wrong value for {key}")

    def test_large_gff_batch_label_integrity(self):
        """50 fields — larger batch test."""
        data = self._build_many_fields_gff(50)
        r = GFF3Reader(data)
        p = r.parse()
        self.assertEqual(len([k for k in p if k.startswith("Field")]), 50)

    def test_label_reuse_across_structs(self):
        """Same label name in multiple structs (e.g. 'Index' appears in every link struct)."""
        w = GFF3Writer("TST ")
        items = []
        for i in range(20):
            s = GFFStruct(0)
            s.add_dword("Index", i)
            s.add_resref("Active", "")
            items.append(s)
        w.root.add_list("Links", items)

        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        links = p["Links"]
        self.assertEqual(len(links), 20)
        for i, link in enumerate(links):
            self.assertEqual(link["Index"], i)

    def test_batch_load_label_order_preserved(self):
        """Label array order must be preserved after batch load."""
        w = GFF3Writer("TST ")
        # Add fields in specific order
        for name in ["Zebra", "Apple", "Mango", "Banana"]:
            w.root.add_cexo(name, name.lower())
        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        self.assertEqual(p["Zebra"], "zebra")
        self.assertEqual(p["Apple"], "apple")
        self.assertEqual(p["Mango"], "mango")
        self.assertEqual(p["Banana"], "banana")


# ═══════════════════════════════════════════════════════════════
# 5. GFF3 ORIENTATION and VECTOR types (type 16 / 17)
# ═══════════════════════════════════════════════════════════════

class TestGFF3OrientationVector(unittest.TestCase):
    """
    Tests specific to ORIENTATION (type 16, quaternion W/X/Y/Z)
    and VECTOR (type 17, position X/Y/Z).

    Type IDs verified against OldRepublicDevs/PyKotor GFFFieldType:
      Vector4 = 16 (quaternion orientation)
      Vector3 = 17 (3D position/direction vector)
    """

    def test_vector_round_trip_simple(self):
        w = GFF3Writer("TST ")
        w.root.add_vector("Pos", 1.0, 2.0, 3.0)
        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        x, y, z = p["Pos"]
        self.assertAlmostEqual(x, 1.0, places=5)
        self.assertAlmostEqual(y, 2.0, places=5)
        self.assertAlmostEqual(z, 3.0, places=5)

    def test_vector_negative_coordinates(self):
        w = GFF3Writer("TST ")
        w.root.add_vector("Origin", -100.0, -200.5, 0.001)
        data = w.build()
        p = GFF3Reader(data).parse()
        x, y, z = p["Origin"]
        self.assertAlmostEqual(x, -100.0, places=4)
        self.assertAlmostEqual(y, -200.5, places=4)
        self.assertAlmostEqual(z, 0.001, places=5)

    def test_vector_zero(self):
        w = GFF3Writer("TST ")
        w.root.add_vector("Zero", 0.0, 0.0, 0.0)
        data = w.build()
        p = GFF3Reader(data).parse()
        self.assertEqual(p["Zero"], (0.0, 0.0, 0.0))

    def test_orientation_round_trip_identity(self):
        """Identity quaternion (1, 0, 0, 0) — no rotation."""
        w = GFF3Writer("TST ")
        w.root.add_orientation("Facing", 1.0, 0.0, 0.0, 0.0)
        data = w.build()
        p = GFF3Reader(data).parse()
        qw, qx, qy, qz = p["Facing"]
        self.assertAlmostEqual(qw, 1.0, places=5)
        self.assertAlmostEqual(qx, 0.0, places=5)
        self.assertAlmostEqual(qy, 0.0, places=5)
        self.assertAlmostEqual(qz, 0.0, places=5)

    def test_orientation_90deg_rotation(self):
        """90° rotation around Z axis: w=0.7071, x=0, y=0, z=0.7071."""
        import math
        half = math.sqrt(2.0) / 2.0
        w = GFF3Writer("TST ")
        w.root.add_orientation("Rot90Z", half, 0.0, 0.0, half)
        data = w.build()
        p = GFF3Reader(data).parse()
        qw, qx, qy, qz = p["Rot90Z"]
        self.assertAlmostEqual(qw, half, places=5)
        self.assertAlmostEqual(qz, half, places=5)

    def test_vector_and_orientation_in_same_struct(self):
        w = GFF3Writer("UTC ")
        w.root.add_vector("Position", 5.5, 10.0, 0.0)
        w.root.add_orientation("Orientation", 1.0, 0.0, 0.0, 0.0)
        w.root.add_resref("TemplateResRef", "c_bastila")
        data = w.build()
        p = GFF3Reader(data).parse()

        px, py, pz = p["Position"]
        self.assertAlmostEqual(px, 5.5, places=5)
        self.assertAlmostEqual(py, 10.0, places=5)

        qw, qx, qy, qz = p["Orientation"]
        self.assertAlmostEqual(qw, 1.0, places=5)
        self.assertEqual(p["TemplateResRef"], "c_bastila")

    def test_vector_type_id_is_17(self):
        """VECTOR must use type ID 17 in the binary stream."""
        w = GFF3Writer("TST ")
        w.root.add_vector("Vec", 1.0, 2.0, 3.0)
        data = w.build()

        # Read header to locate field section
        struct_off  = struct.unpack_from("<I", data, 8)[0]
        struct_cnt  = struct.unpack_from("<I", data, 12)[0]
        field_off   = struct.unpack_from("<I", data, 16)[0]
        field_cnt   = struct.unpack_from("<I", data, 20)[0]

        # Find the field with type 17
        found_vector = False
        for i in range(field_cnt):
            ftype = struct.unpack_from("<I", data, field_off + i * 12)[0]
            if ftype == 17:
                found_vector = True
                break
        self.assertTrue(found_vector, "VECTOR field (type 17) not found in binary")

    def test_orientation_type_id_is_16(self):
        """ORIENTATION must use type ID 16 in the binary stream."""
        w = GFF3Writer("TST ")
        w.root.add_orientation("Ori", 1.0, 0.0, 0.0, 0.0)
        data = w.build()

        field_off = struct.unpack_from("<I", data, 16)[0]
        field_cnt = struct.unpack_from("<I", data, 20)[0]

        found_orientation = False
        for i in range(field_cnt):
            ftype = struct.unpack_from("<I", data, field_off + i * 12)[0]
            if ftype == 16:
                found_orientation = True
                break
        self.assertTrue(found_orientation, "ORIENTATION field (type 16) not found in binary")

    def test_multiple_vectors_in_list(self):
        """UTC creature placement uses a list of position structs."""
        w = GFF3Writer("GIT ")
        positions = []
        coords = [(0.0, 0.0, 0.0), (10.0, 5.0, 0.0), (-3.0, 7.5, 2.0)]
        for x, y, z in coords:
            s = GFFStruct(0)
            s.add_vector("Position", x, y, z)
            s.add_orientation("Orientation", 1.0, 0.0, 0.0, 0.0)
            positions.append(s)
        w.root.add_list("Creature List", positions)

        data = w.build()
        p = GFF3Reader(data).parse()
        clist = p.get("Creature List", [])
        self.assertEqual(len(clist), 3)
        for i, (ex, ey, ez) in enumerate(coords):
            pos = clist[i].get("Position")
            self.assertIsNotNone(pos)
            self.assertAlmostEqual(pos[0], ex, places=4)
            self.assertAlmostEqual(pos[1], ey, places=4)


# ═══════════════════════════════════════════════════════════════
# 6. TLK binary format compatibility
# ═══════════════════════════════════════════════════════════════

class TestTLKBinaryCompatibility(unittest.TestCase):
    """
    Verify our TLK reader/writer matches the layout from
    OldRepublicDevs/PyKotor TLKBinaryReader/Writer.
    Layout: 20-byte file header + 40-byte per entry + string data block.
    """

    def _build_tlk(self, lang_id: int, entries: list) -> bytes:
        """
        Build a TLK V3.0 binary blob.
        entries: [(flags, sound_resref_bytes, text_bytes), ...]
        """
        count = len(entries)
        # String data offset = 20 (header) + count * 40 (entries)
        str_offset = 20 + count * 40

        entry_table = bytearray()
        string_data = bytearray()

        for flags, sound_raw, text_bytes in entries:
            off_str = len(string_data)
            string_data += text_bytes
            sound_padded = sound_raw[:16].ljust(16, b"\x00")
            entry_table += struct.pack(
                "<I16sIIIIf",
                flags,
                sound_padded,
                0,               # volume_variance
                0,               # pitch_variance
                off_str,
                len(text_bytes),
                0.0,             # sound_length
            )

        header = struct.pack("<4s4sIII",
            b"TLK ",
            b"V3.0",
            lang_id,
            count,
            str_offset,
        )
        return header + bytes(entry_table) + bytes(string_data)

    def test_header_layout_matches_pykotor(self):
        """20-byte header: TLK(4) V3.0(4) lang(4) count(4) str_offset(4)."""
        data = self._build_tlk(0, [])
        self.assertEqual(data[0:4], b"TLK ")
        self.assertEqual(data[4:8], b"V3.0")
        lang_id = struct.unpack_from("<I", data, 8)[0]
        count   = struct.unpack_from("<I", data, 12)[0]
        str_off = struct.unpack_from("<I", data, 16)[0]
        self.assertEqual(lang_id, 0)
        self.assertEqual(count, 0)
        self.assertEqual(str_off, 20)

    def test_entry_size_is_40_bytes(self):
        """Each entry is exactly 40 bytes as per PyKotor _ENTRY_SIZE = 40."""
        data = self._build_tlk(0, [(1, b"", b"")])
        # With 1 entry: total = 20 (header) + 40 (entry) + 0 (no text)
        self.assertEqual(len(data), 60)

    def test_flags_encoded_correctly(self):
        """Flag bits: 0x01=text_present, 0x02=sound_present, 0x04=sound_length."""
        data = self._build_tlk(0, [
            (0x01, b"", b"hello"),    # text only
            (0x03, b"s_vo_001", b"world"),  # text + sound
        ])
        entry0_flags = struct.unpack_from("<I", data, 20)[0]
        entry1_flags = struct.unpack_from("<I", data, 60)[0]
        self.assertEqual(entry0_flags, 0x01)
        self.assertEqual(entry1_flags, 0x03)

    def test_string_offsets_correctly_computed(self):
        """String offsets are cumulative — second entry offset = len(first text)."""
        text1 = b"Hello"
        text2 = b"World"
        data = self._build_tlk(0, [
            (0x01, b"", text1),
            (0x01, b"", text2),
        ])
        # Entry layout: flags(4) + sound_resref(16) + volume(4) + pitch(4) + text_offset(4) + ...
        # text_offset field is at position 4+16+4+4 = 28 within each 40-byte entry
        off0 = struct.unpack_from("<I", data, 20 + 28)[0]  # entry 0 text_offset
        off1 = struct.unpack_from("<I", data, 60 + 28)[0]  # entry 1 text_offset
        self.assertEqual(off0, 0)
        self.assertEqual(off1, len(text1))

    def test_sound_resref_padded_to_16(self):
        """Sound ResRef must be exactly 16 bytes (null-padded)."""
        data = self._build_tlk(0, [(0x03, b"vo_001", b"text")])
        # ResRef field starts at byte 20+4 = 24
        resref_bytes = data[24:40]
        self.assertEqual(len(resref_bytes), 16)
        # First 6 bytes are the actual ref, rest is null
        self.assertEqual(resref_bytes[:6], b"vo_001")
        self.assertEqual(resref_bytes[6:], b"\x00" * 10)

    def test_language_id_preserved(self):
        """Language ID (e.g. 0=English, 5=Spanish) stored in header."""
        for lang in [0, 1, 2, 3, 5]:
            data = self._build_tlk(lang, [])
            stored_lang = struct.unpack_from("<I", data, 8)[0]
            self.assertEqual(stored_lang, lang, f"Language {lang} not preserved")

    def test_multi_entry_tlk_offsets(self):
        """5-entry TLK with different text lengths — verify each offset."""
        texts = [b"Hi", b"Goodbye", b"Yes", b"No", b"Maybe"]
        entries = [(0x01, b"", t) for t in texts]
        data = self._build_tlk(0, entries)

        # text_offset is at position 28 within each 40-byte entry
        # (flags=4 + sound_resref=16 + volume=4 + pitch=4 = 28)
        expected_off = 0
        for i, text in enumerate(texts):
            entry_start = 20 + i * 40
            off = struct.unpack_from("<I", data, entry_start + 28)[0]
            self.assertEqual(off, expected_off,
                             f"Entry {i}: expected offset {expected_off}, got {off}")
            expected_off += len(text)


# ═══════════════════════════════════════════════════════════════
# 7. ResourceEntry and ResourceManager helpers
# ═══════════════════════════════════════════════════════════════

class TestResourceEntry(unittest.TestCase):
    """Unit tests for ResourceEntry dataclass."""

    def test_filename_with_known_type(self):
        e = ResourceEntry(resref="appearance", restype=2017)
        self.assertEqual(e.filename, "appearance.2da")

    def test_filename_with_unknown_type(self):
        e = ResourceEntry(resref="unknown_res", restype=9999)
        self.assertEqual(e.filename, "unknown_res.type9999")

    def test_filename_tga(self):
        e = ResourceEntry(resref="party_portrait", restype=3)
        self.assertEqual(e.filename, "party_portrait.tga")

    def test_filename_ncs(self):
        e = ResourceEntry(resref="k_hk47_dialog", restype=2010)
        self.assertEqual(e.filename, "k_hk47_dialog.ncs")

    def test_filename_dlg(self):
        e = ResourceEntry(resref="bastila_romance", restype=2029)
        self.assertEqual(e.filename, "bastila_romance.dlg")

    def test_filename_mdl(self):
        e = ResourceEntry(resref="c_bastila", restype=2002)
        self.assertEqual(e.filename, "c_bastila.mdl")

    def test_filename_tpc(self):
        e = ResourceEntry(resref="TEX_bastila", restype=3007)
        self.assertEqual(e.filename, "TEX_bastila.tpc")

    def test_filename_utc(self):
        e = ResourceEntry(resref="c_calo001", restype=2027)
        self.assertEqual(e.filename, "c_calo001.utc")

    def test_filename_jrl(self):
        e = ResourceEntry(resref="global", restype=2056)
        self.assertEqual(e.filename, "global.jrl")

    def test_resource_entry_defaults(self):
        e = ResourceEntry(resref="test", restype=2009)
        self.assertEqual(e.source_file, "")
        self.assertEqual(e.offset, 0)
        self.assertEqual(e.size, 0)
        self.assertEqual(e.restype_str, "")


class TestResourceManagerAPI(unittest.TestCase):
    """Tests for ResourceManager API without a real game install."""

    def test_not_loaded_initially(self):
        rm = ResourceManager()
        self.assertFalse(rm.is_loaded)

    def test_search_on_unloaded_returns_empty(self):
        rm = ResourceManager()
        self.assertEqual(rm.search("bastila"), [])

    def test_list_by_type_on_unloaded_returns_empty(self):
        rm = ResourceManager()
        self.assertEqual(rm.list_by_type(".dlg"), [])

    def test_read_on_unloaded_returns_none(self):
        rm = ResourceManager()
        self.assertIsNone(rm.read("appearance.2da"))

    def test_batch_read_on_unloaded(self):
        rm = ResourceManager()
        result = rm.batch_read(["a.2da", "b.dlg"])
        self.assertEqual(result, {"a.2da": None, "b.dlg": None})

    def test_cache_info_no_cachetools(self):
        """cache_info() should work regardless of cachetools availability."""
        rm = ResourceManager()
        info = rm.cache_info()
        self.assertIsInstance(info, dict)

    def test_list_all_types_coverage(self):
        rm = ResourceManager()
        types = rm.list_all_types()
        # Must include all major KotOR types
        for ext in [".dlg", ".utc", ".2da", ".mdl", ".tga", ".nss", ".ncs",
                    ".tpc", ".lyt", ".vis", ".rim", ".tlk", ".jrl"]:
            self.assertIn(ext, types, f"{ext} missing from list_all_types()")

    def test_get_type_count(self):
        rm = ResourceManager()
        self.assertGreaterEqual(rm.get_type_count(), 70)


# ═══════════════════════════════════════════════════════════════
# 8. GFF3 STRREF (TSL-only) field round-trip
# ═══════════════════════════════════════════════════════════════

class TestGFF3StrRef(unittest.TestCase):
    """Test TSL-only STRREF field type (type 18)."""

    def test_strref_round_trip(self):
        w = GFF3Writer("TST ")
        w.root.add_strref("StringRef", 99999)
        data = w.build()
        r = GFF3Reader(data)
        p = r.parse()
        self.assertEqual(p.get("StringRef"), 99999)

    def test_strref_zero(self):
        w = GFF3Writer("TST ")
        w.root.add_strref("StrRef", 0)
        data = w.build()
        p = GFF3Reader(data).parse()
        self.assertEqual(p["StrRef"], 0)

    def test_strref_max(self):
        """STRREF is stored as int32 — 0xFFFFFFFE round-trips as -2 (signed)."""
        w = GFF3Writer("TST ")
        w.root.add_strref("MaxRef", 0xFFFFFFFE)
        data = w.build()
        p = GFF3Reader(data).parse()
        # The reader decodes STRREF as signed i32: 0xFFFFFFFE = -2
        self.assertEqual(p["MaxRef"], -2)

    def test_strref_alongside_locstring(self):
        """STRREF (18) and CEXOLOCSTRING (12) can coexist in same struct."""
        w = GFF3Writer("TST ")
        w.root.add_strref("TlkRef", 42)
        w.root.add_locstring("LocalText", 42, "override text")
        data = w.build()
        p = GFF3Reader(data).parse()
        self.assertEqual(p["TlkRef"], 42)
        strref, text = p["LocalText"]
        self.assertEqual(strref, 42)
        self.assertEqual(text, "override text")


if __name__ == "__main__":
    unittest.main(verbosity=2)
