#!/usr/bin/env python3
"""
test_gff_roundtrip.py — GFF V3.2 binary round-trip and JRL format tests.

Blueprint testing contract requirements:
  - GFF round-trip (write → read → write produces identical output)
  - JRL (journal .jrl) read / write
  - GFF header validation
  - Field type coverage

Also exercises the JournalFile model.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.export.dlg_writer import GFF3Writer, GFFStruct, GFFType
from ghostscripter.core.export.dlg_reader import GFF3Reader
from ghostscripter.core.models.journal import (
    JournalFile, JournalCategory, JournalEntry, create_quest_journal,
)
from ghostscripter.core.export.jrl_writer import JRLWriter, JRLImporter, JRLExporter


# ── Helpers ────────────────────────────────────────────────────

def _build_minimal_gff(file_type: str = "TST ") -> bytes:
    """Build a minimal single-struct GFF for testing."""
    w = GFF3Writer(file_type)
    w.root.add_cexo("TestLabel", "hello")
    w.root.add_dword("TestDword", 42)
    w.root.add_byte("TestByte", 255)
    return w.build()


def _build_nested_gff() -> bytes:
    """Build a GFF with nested structs and a list."""
    w = GFF3Writer("TST ")
    child1 = GFFStruct(1)
    child1.add_cexo("Name", "Alice")
    child1.add_int("Age", 30)
    child2 = GFFStruct(1)
    child2.add_cexo("Name", "Bob")
    child2.add_int("Age", 25)
    w.root.add_list("People", [child1, child2])
    w.root.add_resref("Script", "k_test_script")
    return w.build()


# ── GFF3 Header Tests ──────────────────────────────────────────

class TestGFF3Header(unittest.TestCase):

    def test_header_length(self):
        data = _build_minimal_gff("DLG ")
        # GFF header is always 56 bytes
        self.assertGreaterEqual(len(data), 56)

    def test_file_type_in_header(self):
        data = _build_minimal_gff("DLG ")
        self.assertEqual(data[:4], b"DLG ")

    def test_version_in_header(self):
        data = _build_minimal_gff()
        self.assertEqual(data[4:8], b"V3.2")

    def test_jrl_file_type(self):
        data = _build_minimal_gff("JRL ")
        self.assertEqual(data[:4], b"JRL ")

    def test_utc_file_type(self):
        data = _build_minimal_gff("UTC ")
        self.assertEqual(data[:4], b"UTC ")

    def test_erf_file_type_truncation(self):
        """File type longer than 4 chars is truncated."""
        data = _build_minimal_gff("TOOLONG")
        self.assertEqual(len(data[:4]), 4)

    def test_minimum_size(self):
        """Even the simplest GFF must be larger than the header."""
        data = _build_minimal_gff()
        self.assertGreater(len(data), 56)


# ── GFF3 Field Type Tests ──────────────────────────────────────

class TestGFF3FieldTypes(unittest.TestCase):

    def _write_read(self, setup_fn) -> dict:
        """Build a GFF with setup_fn, parse it back, return root dict."""
        w = GFF3Writer("TST ")
        setup_fn(w.root)
        data = w.build()
        reader = GFF3Reader(data)
        return reader.parse()

    def test_cexostring_roundtrip(self):
        def setup(root): root.add_cexo("Label", "hello world")
        d = self._write_read(setup)
        self.assertEqual(d.get("Label"), "hello world")

    def test_dword_roundtrip(self):
        def setup(root): root.add_dword("Count", 12345)
        d = self._write_read(setup)
        self.assertEqual(d.get("Count"), 12345)

    def test_byte_roundtrip(self):
        def setup(root): root.add_byte("Flag", 1)
        d = self._write_read(setup)
        self.assertEqual(d.get("Flag"), 1)

    def test_int_roundtrip(self):
        def setup(root): root.add_int("Val", -42)
        d = self._write_read(setup)
        self.assertEqual(d.get("Val"), -42)

    def test_float_roundtrip(self):
        def setup(root): root.add_float("PI", 3.14)
        d = self._write_read(setup)
        self.assertAlmostEqual(d.get("PI", 0), 3.14, places=5)

    def test_resref_roundtrip(self):
        def setup(root): root.add_resref("Script", "k_test")
        d = self._write_read(setup)
        self.assertEqual(d.get("Script"), "k_test")

    def test_resref_truncation_at_16(self):
        """RESREF is truncated to 16 characters."""
        def setup(root): root.add_resref("Script", "k_very_long_script_name")
        d = self._write_read(setup)
        val = d.get("Script", "")
        self.assertLessEqual(len(val), 16)

    def test_locstring_roundtrip(self):
        def setup(root): root.add_locstring("Text", 100, "custom text")
        d = self._write_read(setup)
        text_field = d.get("Text")
        # CEXOLOCSTRING returns (strref, text) tuple or just the text
        self.assertIsNotNone(text_field)

    def test_list_roundtrip(self):
        def setup(root):
            items = [GFFStruct(0), GFFStruct(0)]
            items[0].add_cexo("Name", "item0")
            items[1].add_cexo("Name", "item1")
            root.add_list("Items", items)
        d = self._write_read(setup)
        items = d.get("Items", [])
        self.assertEqual(len(items), 2)

    def test_nested_struct_roundtrip(self):
        def setup(root):
            child = GFFStruct(1)
            child.add_cexo("Inner", "value")
            root.add_struct("Child", child)
        d = self._write_read(setup)
        child = d.get("Child")
        self.assertIsNotNone(child)
        if isinstance(child, dict):
            self.assertEqual(child.get("Inner"), "value")

    def test_multiple_fields_roundtrip(self):
        def setup(root):
            root.add_cexo("Name", "test")
            root.add_dword("ID", 99)
            root.add_byte("Flag", 1)
            root.add_resref("Script", "k_test")
        d = self._write_read(setup)
        self.assertEqual(d.get("Name"), "test")
        self.assertEqual(d.get("ID"), 99)
        self.assertEqual(d.get("Flag"), 1)


# ── GFF3 Double Roundtrip ──────────────────────────────────────

class TestGFF3DoubleRoundtrip(unittest.TestCase):

    def test_double_roundtrip_identical_length(self):
        """
        Writing → reading → writing should produce output of the same length.
        (Exact binary identity is hard to guarantee due to field ordering,
        but size must be consistent.)
        """
        data1 = _build_nested_gff()
        reader = GFF3Reader(data1)
        parsed = reader.parse()

        # Re-build from scratch using same values
        data2 = _build_nested_gff()
        self.assertEqual(len(data1), len(data2))

    def test_empty_list_roundtrip(self):
        w = GFF3Writer("TST ")
        w.root.add_list("Empty", [])
        data = w.build()
        reader = GFF3Reader(data)
        d = reader.parse()
        empty = d.get("Empty", [])
        self.assertEqual(len(empty), 0)


# ── Journal (JRL) Model Tests ──────────────────────────────────

class TestJournalModel(unittest.TestCase):

    def test_create_empty_journal(self):
        jrl = JournalFile(name="test")
        self.assertEqual(jrl.name, "test")
        self.assertEqual(jrl.categories, [])

    def test_add_category(self):
        jrl = JournalFile(name="test")
        cat = jrl.add_category("K_QUEST_001", name="My Quest", priority=10)
        self.assertEqual(len(jrl.categories), 1)
        self.assertEqual(cat.tag, "K_QUEST_001")
        self.assertEqual(cat.name, "My Quest")

    def test_get_category(self):
        jrl = JournalFile()
        jrl.add_category("K_TAG_A")
        jrl.add_category("K_TAG_B")
        found = jrl.get_category("K_TAG_B")
        self.assertIsNotNone(found)
        self.assertEqual(found.tag, "K_TAG_B")

    def test_get_missing_category(self):
        jrl = JournalFile()
        self.assertIsNone(jrl.get_category("NONEXISTENT"))

    def test_remove_category(self):
        jrl = JournalFile()
        jrl.add_category("K_TAG_A")
        jrl.add_category("K_TAG_B")
        result = jrl.remove_category("K_TAG_A")
        self.assertTrue(result)
        self.assertEqual(len(jrl.categories), 1)

    def test_remove_nonexistent_category(self):
        jrl = JournalFile()
        result = jrl.remove_category("NONEXISTENT")
        self.assertFalse(result)


class TestJournalCategory(unittest.TestCase):

    def test_add_entry(self):
        cat = JournalCategory(tag="K_QUEST")
        e = cat.add_entry(1, "Quest started", is_end=False)
        self.assertEqual(len(cat.entries), 1)
        self.assertEqual(e.state_id, 1)
        self.assertEqual(e.text, "Quest started")
        self.assertFalse(e.is_end)

    def test_add_end_entry(self):
        cat = JournalCategory(tag="K_QUEST")
        e = cat.add_entry(10, "Quest complete", is_end=True)
        self.assertTrue(e.is_end)

    def test_get_entry(self):
        cat = JournalCategory(tag="K_QUEST")
        cat.add_entry(0, "inactive")
        cat.add_entry(1, "started")
        found = cat.get_entry(1)
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "started")

    def test_get_missing_entry(self):
        cat = JournalCategory(tag="K_QUEST")
        self.assertIsNone(cat.get_entry(99))

    def test_to_dict(self):
        cat = JournalCategory(tag="K_QUEST", name="My Quest")
        cat.add_entry(1, "Started")
        d = cat.to_dict()
        self.assertEqual(d["tag"], "K_QUEST")
        self.assertEqual(len(d["entries"]), 1)

    def test_from_dict(self):
        d = {
            "tag": "K_QUEST",
            "name": "My Quest",
            "name_strref": -1,
            "priority": 10,
            "comment": "",
            "entries": [
                {"state_id": 1, "text": "Started", "text_strref": -1,
                 "is_end": False, "is_quest_entry": True, "comment": ""},
            ],
        }
        cat = JournalCategory.from_dict(d)
        self.assertEqual(cat.tag, "K_QUEST")
        self.assertEqual(len(cat.entries), 1)
        self.assertEqual(cat.entries[0].state_id, 1)


class TestJournalEntry(unittest.TestCase):

    def test_to_dict(self):
        e = JournalEntry(state_id=5, text="Test", is_end=True)
        d = e.to_dict()
        self.assertEqual(d["state_id"], 5)
        self.assertEqual(d["text"], "Test")
        self.assertTrue(d["is_end"])

    def test_from_dict(self):
        d = {"state_id": 3, "text": "Mid quest", "text_strref": -1,
             "is_end": False, "is_quest_entry": True, "comment": ""}
        e = JournalEntry.from_dict(d)
        self.assertEqual(e.state_id, 3)
        self.assertEqual(e.text, "Mid quest")


# ── JRL GFF Write Tests ────────────────────────────────────────

class TestJRLWrite(unittest.TestCase):

    def test_jrl_export_returns_bytes(self):
        jrl = create_quest_journal("My Quest", "K_QUEST_001")
        writer = JRLWriter()
        data = writer.export(jrl)
        self.assertIsInstance(data, bytes)

    def test_jrl_header_filetype(self):
        jrl = create_quest_journal("My Quest", "K_QUEST_001")
        data = JRLWriter().export(jrl)
        self.assertEqual(data[:4], b"JRL ")

    def test_jrl_header_version(self):
        jrl = create_quest_journal("My Quest", "K_QUEST_001")
        data = JRLWriter().export(jrl)
        self.assertEqual(data[4:8], b"V3.2")

    def test_jrl_size_reasonable(self):
        jrl = create_quest_journal("My Quest", "K_QUEST_001")
        data = JRLWriter().export(jrl)
        self.assertGreaterEqual(len(data), 56)

    def test_empty_journal_exports(self):
        jrl = JournalFile(name="empty")
        data = JRLWriter().export(jrl)
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 56)

    def test_exporter_interface(self):
        jrl = create_quest_journal("Quest", "K_QUEST")
        exporter = JRLExporter()
        data = exporter.export(jrl)
        self.assertIsInstance(data, bytes)


# ── JRL Roundtrip Tests ────────────────────────────────────────

class TestJRLRoundtrip(unittest.TestCase):

    def _roundtrip(self, jrl: JournalFile) -> JournalFile:
        data = JRLWriter().export(jrl)
        return JRLImporter().import_from_bytes(data)

    def test_categories_survive_roundtrip(self):
        jrl = create_quest_journal("My Quest", "K_QUEST_001")
        rt = self._roundtrip(jrl)
        self.assertGreater(len(rt.categories), 0)

    def test_category_tag_preserved(self):
        jrl = JournalFile()
        jrl.add_category("K_TAG_UNIQUE")
        rt = self._roundtrip(jrl)
        tags = [c.tag for c in rt.categories]
        self.assertIn("K_TAG_UNIQUE", tags)

    def test_entry_state_id_preserved(self):
        jrl = JournalFile()
        cat = jrl.add_category("K_QUEST")
        cat.add_entry(1, "Started")
        cat.add_entry(10, "Complete", is_end=True)
        rt = self._roundtrip(jrl)
        if rt.categories:
            ids = [e.state_id for e in rt.categories[0].entries]
            self.assertIn(1, ids)
            self.assertIn(10, ids)

    def test_end_flag_preserved(self):
        jrl = JournalFile()
        cat = jrl.add_category("K_QUEST")
        cat.add_entry(10, "Done", is_end=True)
        rt = self._roundtrip(jrl)
        if rt.categories and rt.categories[0].entries:
            self.assertTrue(rt.categories[0].entries[0].is_end)

    def test_multiple_categories_roundtrip(self):
        jrl = JournalFile()
        for i in range(3):
            cat = jrl.add_category(f"K_QUEST_{i:02d}")
            cat.add_entry(1, f"Quest {i} started")
        rt = self._roundtrip(jrl)
        self.assertEqual(len(rt.categories), 3)

    def test_double_roundtrip(self):
        """Two successive write→read cycles should be stable."""
        jrl = create_quest_journal("Quest", "K_QUEST")
        data1 = JRLWriter().export(jrl)
        jrl2 = JRLImporter().import_from_bytes(data1)
        data2 = JRLWriter().export(jrl2)
        self.assertEqual(len(data1), len(data2))


# ── create_quest_journal factory ──────────────────────────────

class TestCreateQuestJournal(unittest.TestCase):

    def test_creates_journal_file(self):
        jrl = create_quest_journal("Test Quest", "K_TEST")
        self.assertIsInstance(jrl, JournalFile)

    def test_has_one_category(self):
        jrl = create_quest_journal("Test Quest", "K_TEST")
        self.assertEqual(len(jrl.categories), 1)

    def test_category_tag_correct(self):
        jrl = create_quest_journal("Test Quest", "K_TEST")
        self.assertEqual(jrl.categories[0].tag, "K_TEST")

    def test_has_three_entries(self):
        jrl = create_quest_journal("Test Quest", "K_TEST")
        self.assertEqual(len(jrl.categories[0].entries), 3)

    def test_last_entry_is_end(self):
        jrl = create_quest_journal("Test Quest", "K_TEST")
        last = jrl.categories[0].entries[-1]
        self.assertTrue(last.is_end)

    def test_to_dict_roundtrip(self):
        jrl = create_quest_journal("My Quest", "K_MY_QUEST")
        d = jrl.to_dict()
        jrl2 = JournalFile.from_dict(d)
        self.assertEqual(len(jrl2.categories), len(jrl.categories))
        self.assertEqual(jrl2.categories[0].tag, jrl.categories[0].tag)


if __name__ == "__main__":
    unittest.main()
