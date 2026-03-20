#!/usr/bin/env python3
"""
test_journal_editor.py — Tests for JournalFile model, JRL writer/importer,
                          and JournalEditorWidget (headless stub).

Covers:
  - JournalCategory / JournalEntry dataclasses
  - JournalFile model (add/remove categories, to_dict)
  - create_quest_journal() helper
  - JRLWriter binary output (header, label presence)
  - JRLImporter round-trip (write → read → compare)
  - JRLExporter convenience wrapper
  - JournalEditorWidget headless stub (no PyQt5 required)
"""
import sys
import struct
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.models.journal import (
    JournalFile, JournalCategory, JournalEntry, create_quest_journal,
)
from ghostscripter.core.export.jrl_writer import JRLWriter, JRLImporter, JRLExporter


# ── JournalEntry ──────────────────────────────────────────────────────────────

class TestJournalEntry(unittest.TestCase):

    def test_create_minimal(self):
        e = JournalEntry(state_id=0, text="Quest started.", is_end=False, is_quest_entry=True)
        self.assertEqual(e.state_id, 0)
        self.assertEqual(e.text, "Quest started.")
        self.assertFalse(e.is_end)
        self.assertTrue(e.is_quest_entry)

    def test_defaults(self):
        e = JournalEntry(state_id=1, text="")
        self.assertFalse(e.is_end)
        # is_quest_entry may default to True in the model; just check the field exists
        self.assertIsInstance(e.is_quest_entry, bool)
        self.assertEqual(e.comment, "")

    def test_end_entry(self):
        e = JournalEntry(state_id=10, text="Quest complete.", is_end=True, is_quest_entry=True)
        self.assertTrue(e.is_end)

    def test_comment_field(self):
        e = JournalEntry(state_id=0, text="", comment="dev note")
        self.assertEqual(e.comment, "dev note")

    def test_strref_default(self):
        e = JournalEntry(state_id=0, text="")
        self.assertEqual(e.text_strref, -1)

    def test_strref_custom(self):
        e = JournalEntry(state_id=0, text="", text_strref=42001)
        self.assertEqual(e.text_strref, 42001)


# ── JournalCategory ───────────────────────────────────────────────────────────

class TestJournalCategory(unittest.TestCase):

    def test_create(self):
        cat = JournalCategory(tag="K_SWG_MYQUEST", name="My Quest")
        self.assertEqual(cat.tag, "K_SWG_MYQUEST")
        self.assertEqual(cat.name, "My Quest")

    def test_entries_initially_empty(self):
        cat = JournalCategory(tag="K_TEST")
        self.assertEqual(cat.entries, [])

    def test_add_entries(self):
        cat = JournalCategory(tag="K_TEST")
        cat.entries.append(JournalEntry(state_id=0, text="Start"))
        cat.entries.append(JournalEntry(state_id=1, text="Mid"))
        self.assertEqual(len(cat.entries), 2)

    def test_priority_default(self):
        cat = JournalCategory(tag="K_TEST")
        self.assertEqual(cat.priority, 0)

    def test_comment_default(self):
        cat = JournalCategory(tag="K_TEST")
        self.assertEqual(cat.comment, "")

    def test_strref_default(self):
        cat = JournalCategory(tag="K_TEST")
        self.assertEqual(cat.name_strref, -1)


# ── JournalFile ───────────────────────────────────────────────────────────────

class TestJournalFile(unittest.TestCase):

    def test_create_empty(self):
        jf = JournalFile("test_journal")
        self.assertEqual(jf.name, "test_journal")
        self.assertEqual(jf.categories, [])

    def test_add_category(self):
        jf = JournalFile("j")
        cat = JournalCategory(tag="K_TEST", name="Test Quest")
        jf.categories.append(cat)
        self.assertEqual(len(jf.categories), 1)

    def test_multiple_categories(self):
        jf = JournalFile("j")
        for i in range(5):
            jf.categories.append(JournalCategory(tag=f"K_QUEST_{i}"))
        self.assertEqual(len(jf.categories), 5)

    def test_file_path_default_none(self):
        jf = JournalFile("j")
        self.assertIsNone(jf.file_path)

    def test_to_dict_has_name(self):
        jf = JournalFile("myjournal")
        d = jf.to_dict()
        self.assertIn("name", d)
        self.assertEqual(d["name"], "myjournal")

    def test_to_dict_has_categories(self):
        jf = JournalFile("j")
        jf.categories.append(JournalCategory(tag="K_TEST"))
        d = jf.to_dict()
        self.assertIn("categories", d)
        self.assertEqual(len(d["categories"]), 1)

    def test_to_dict_roundtrip(self):
        jf = JournalFile("j")
        cat = JournalCategory(tag="K_ROUND", name="Round Quest", priority=2)
        cat.entries.append(JournalEntry(state_id=0, text="Start", is_quest_entry=True))
        cat.entries.append(JournalEntry(state_id=10, text="Done", is_end=True))
        jf.categories.append(cat)
        d = jf.to_dict()
        # Verify structure
        c = d["categories"][0]
        self.assertEqual(c["tag"], "K_ROUND")
        self.assertEqual(len(c["entries"]), 2)
        self.assertTrue(c["entries"][1]["is_end"])


# ── create_quest_journal ──────────────────────────────────────────────────────

class TestCreateQuestJournal(unittest.TestCase):

    def test_returns_journal_file(self):
        jf = create_quest_journal("My Quest", "K_MY_QUEST")
        self.assertIsInstance(jf, JournalFile)

    def test_has_one_category(self):
        jf = create_quest_journal("Test Quest", "K_TEST")
        self.assertEqual(len(jf.categories), 1)

    def test_category_tag(self):
        jf = create_quest_journal("Dantooine Quest", "K_DANTOOINE")
        self.assertEqual(jf.categories[0].tag, "K_DANTOOINE")

    def test_has_entries(self):
        jf = create_quest_journal("Q", "K_Q")
        self.assertGreater(len(jf.categories[0].entries), 0)

    def test_last_entry_is_end(self):
        jf = create_quest_journal("Q", "K_Q")
        last = jf.categories[0].entries[-1]
        self.assertTrue(last.is_end)

    def test_entry_ids_ascending(self):
        jf = create_quest_journal("Q", "K_Q")
        ids = [e.state_id for e in jf.categories[0].entries]
        self.assertEqual(ids, sorted(ids))

    def test_first_entry_is_quest_entry(self):
        jf = create_quest_journal("Q", "K_Q")
        self.assertTrue(jf.categories[0].entries[0].is_quest_entry)


# ── JRLWriter ─────────────────────────────────────────────────────────────────

class TestJRLWriter(unittest.TestCase):

    def _make_journal(self):
        jf = JournalFile("test")
        cat = JournalCategory(tag="K_TEST", name="Test Quest", priority=1)
        cat.entries.append(JournalEntry(state_id=0, text="Quest begun.", is_quest_entry=True))
        cat.entries.append(JournalEntry(state_id=5, text="Quest done.", is_end=True, is_quest_entry=True))
        jf.categories.append(cat)
        return jf

    def test_build_returns_bytes(self):
        w = JRLWriter()
        jf = self._make_journal()
        data = w.export(jf)
        self.assertIsInstance(data, bytes)

    def test_gff_header_magic(self):
        w = JRLWriter()
        data = w.export(self._make_journal())
        self.assertEqual(data[:4], b"JRL ")

    def test_gff_header_version(self):
        w = JRLWriter()
        data = w.export(self._make_journal())
        self.assertEqual(data[4:8], b"V3.2")

    def test_minimum_size(self):
        w = JRLWriter()
        data = w.export(self._make_journal())
        self.assertGreater(len(data), 56)

    def test_empty_journal_still_valid(self):
        w = JRLWriter()
        data = w.export(JournalFile("empty"))
        self.assertEqual(data[:4], b"JRL ")
        self.assertGreater(len(data), 56)

    def test_multiple_categories(self):
        jf = JournalFile("multi")
        for i in range(3):
            cat = JournalCategory(tag=f"K_QUEST_{i}", name=f"Quest {i}")
            cat.entries.append(JournalEntry(state_id=0, text=f"Q{i} start"))
            jf.categories.append(cat)
        w = JRLWriter()
        data = w.export(jf)
        self.assertEqual(data[:4], b"JRL ")
        # tag strings should appear in the binary
        for i in range(3):
            self.assertIn(f"K_QUEST_{i}".encode(), data)

    def test_tag_in_binary(self):
        jf = JournalFile("j")
        cat = JournalCategory(tag="K_MYTAG")
        jf.categories.append(cat)
        data = JRLWriter().export(jf)
        self.assertIn(b"K_MYTAG", data)


# ── JRLImporter ──────────────────────────────────────────────────────────────

class TestJRLImporter(unittest.TestCase):

    def _make_and_export(self, tag="K_ROUND", name="Round Quest") -> bytes:
        jf = JournalFile("round")
        cat = JournalCategory(tag=tag, name=name, priority=3)
        cat.entries.append(JournalEntry(state_id=0, text="Start of quest.", is_quest_entry=True))
        cat.entries.append(JournalEntry(state_id=5, text="Quest complete.", is_end=True))
        jf.categories.append(cat)
        return JRLWriter().export(jf), jf

    def test_import_returns_journal_file(self):
        data, _ = self._make_and_export()
        imp = JRLImporter()
        jf = imp.import_from_bytes(data)
        self.assertIsInstance(jf, JournalFile)

    def test_category_count_preserved(self):
        data, orig = self._make_and_export()
        jf = JRLImporter().import_from_bytes(data)
        self.assertEqual(len(jf.categories), len(orig.categories))

    def test_category_tag_preserved(self):
        data, _ = self._make_and_export(tag="K_PRESERVE")
        jf = JRLImporter().import_from_bytes(data)
        self.assertEqual(jf.categories[0].tag, "K_PRESERVE")

    def test_entry_count_preserved(self):
        data, orig = self._make_and_export()
        jf = JRLImporter().import_from_bytes(data)
        self.assertEqual(
            len(jf.categories[0].entries),
            len(orig.categories[0].entries)
        )

    def test_entry_end_flag_preserved(self):
        data, _ = self._make_and_export()
        jf = JRLImporter().import_from_bytes(data)
        last = jf.categories[0].entries[-1]
        self.assertTrue(last.is_end)

    def test_entry_quest_entry_preserved(self):
        data, _ = self._make_and_export()
        jf = JRLImporter().import_from_bytes(data)
        first = jf.categories[0].entries[0]
        self.assertTrue(first.is_quest_entry)


# ── JRLExporter ──────────────────────────────────────────────────────────────

class TestJRLExporter(unittest.TestCase):

    def test_export_returns_bytes(self):
        jf = create_quest_journal("Export Test", "K_EXP")
        data = JRLExporter().export(jf)
        self.assertIsInstance(data, bytes)

    def test_export_valid_gff(self):
        jf = create_quest_journal("Export Test", "K_EXP")
        data = JRLExporter().export(jf)
        self.assertEqual(data[:4], b"JRL ")
        self.assertEqual(data[4:8], b"V3.2")

    def test_export_and_reimport(self):
        jf = create_quest_journal("Export Roundtrip", "K_EXP2")
        data = JRLExporter().export(jf)
        jf2 = JRLImporter().import_from_bytes(data)
        self.assertEqual(jf2.categories[0].tag, "K_EXP2")


# ── JournalEditorWidget stub ──────────────────────────────────────────────────

class TestJournalEditorWidgetStub(unittest.TestCase):
    """
    Tests for the JournalEditorWidget.
    Uses offscreen platform if PyQt5 is available, otherwise tests the
    headless stub path.
    """

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
            import sys as _sys
            cls._app = QApplication.instance() or QApplication(_sys.argv)
            cls._has_qt = True
        except Exception:
            cls._has_qt = False

    def _make_widget(self, journal=None):
        from ghostscripter.ui.widgets.journal_editor_widget import JournalEditorWidget
        return JournalEditorWidget(journal=journal)

    def test_instantiation_no_journal(self):
        w = self._make_widget()
        self.assertIsNotNone(w.journal)

    def test_instantiation_with_journal(self):
        jf = create_quest_journal("Test", "K_TEST")
        w = self._make_widget(journal=jf)
        self.assertIs(w.journal, jf)

    def test_not_dirty_initially(self):
        w = self._make_widget()
        self.assertFalse(w.is_dirty)

    def test_set_journal(self):
        w = self._make_widget()
        jf = create_quest_journal("New", "K_NEW")
        w.set_journal(jf)
        self.assertIs(w.journal, jf)


if __name__ == "__main__":
    unittest.main()
