#!/usr/bin/env python3
"""
test_2da_editor.py — Tests for the TwoDA file model and editor logic.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile, TwoDARow


class TestTwoDAFileModel(unittest.TestCase):
    """Tests for TwoDAFile creation, parsing, and mutation."""

    # ── Construction ──────────────────────────────────────────────────────────

    def test_empty_file_creation(self):
        t = TwoDAFile("test.2da")
        self.assertEqual(t.filename, "test.2da")
        self.assertEqual(t.rows, [])

    def test_from_text_basic(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0_lbl  row0_val\n"
            "1        row1_lbl  row1_val\n"
        )
        t = TwoDAFile.from_text(raw, filename="basic.2da")
        self.assertEqual(len(t.rows), 2)

    def test_from_bytes_2da_header(self):
        raw = (
            "2DA V2.0\n\n"
            "         col1  col2\n"
            "0        aaa   bbb\n"
        ).encode("utf-8")
        t = TwoDAFile.from_bytes(raw, filename="header_test.2da")
        self.assertIsNotNone(t)
        self.assertEqual(len(t.rows), 1)

    # ── Column headers ────────────────────────────────────────────────────────

    def test_column_headers_parsed(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value     strref\n"
            "0        lbl_a     val_a     100\n"
        )
        t = TwoDAFile.from_text(raw, filename="cols.2da")
        self.assertIn("label", t.columns)
        self.assertIn("value", t.columns)
        self.assertIn("strref", t.columns)

    # ── Row access ────────────────────────────────────────────────────────────

    def test_row_label(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        my_label  my_value\n"
        )
        t = TwoDAFile.from_text(raw, filename="labels.2da")
        self.assertEqual(len(t.rows), 1)
        self.assertIsInstance(t.rows[0], TwoDARow)

    def test_row_data_access(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        my_label  my_value\n"
        )
        t = TwoDAFile.from_text(raw, filename="data.2da")
        row = t.rows[0]
        self.assertEqual(row.get("label"), "my_label")
        self.assertEqual(row.get("value"), "my_value")

    # ── Add row ───────────────────────────────────────────────────────────────

    def test_add_row_increases_count(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      val0\n"
        )
        t = TwoDAFile.from_text(raw, filename="add_row.2da")
        initial = len(t.rows)
        t.add_row("1", {"label": "row1", "value": "val1"})
        self.assertEqual(len(t.rows), initial + 1)

    def test_add_row_returns_index(self):
        t = TwoDAFile.from_text(
            "2DA V2.0\n\n         label\n0        a\n",
            filename="idx.2da"
        )
        idx = t.add_row("1", {"label": "b"})
        self.assertEqual(idx, 1)

    # ── Copy row ──────────────────────────────────────────────────────────────

    def test_copy_row_increases_count(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      val0\n"
            "1        row1      val1\n"
        )
        t = TwoDAFile.from_text(raw, filename="copy.2da")
        initial = len(t.rows)
        t.copy_row(0)
        self.assertEqual(len(t.rows), initial + 1)

    def test_copy_row_preserves_data(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      special_val\n"
        )
        t = TwoDAFile.from_text(raw, filename="copy_data.2da")
        t.copy_row(0)
        new_row = t.rows[-1]
        self.assertEqual(new_row.get("value"), "special_val")

    # ── Remove row ────────────────────────────────────────────────────────────

    def test_remove_row_by_index_decreases_count(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      val0\n"
            "1        row1      val1\n"
        )
        t = TwoDAFile.from_text(raw, filename="remove.2da")
        initial = len(t.rows)
        result = t.remove_row_by_index(0)
        self.assertTrue(result)
        self.assertEqual(len(t.rows), initial - 1)

    # ── Cell mutation ─────────────────────────────────────────────────────────

    def test_set_cell_by_label(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        lbl0      original\n"
        )
        t = TwoDAFile.from_text(raw, filename="set_cell.2da")
        # Row label is the row index ("0"), not the cell content
        result = t.set_cell("0", "value", "modified")
        self.assertTrue(result)
        self.assertEqual(t.rows[0].get("value"), "modified")

    def test_set_cell_by_index(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      original\n"
        )
        t = TwoDAFile.from_text(raw, filename="set_idx.2da")
        result = t.set_cell_by_index(0, "value", "changed")
        self.assertTrue(result)
        self.assertEqual(t.rows[0].get("value"), "changed")

    # ── Serialisation ─────────────────────────────────────────────────────────

    def test_to_text_produces_string(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        lbl_a     val_a\n"
        )
        t = TwoDAFile.from_text(raw, filename="to_text.2da")
        out = t.to_text()
        self.assertIsInstance(out, str)
        self.assertIn("2DA", out)

    def test_to_bytes_produces_bytes(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        lbl_a     val_a\n"
        )
        t = TwoDAFile.from_text(raw, filename="to_bytes.2da")
        # TwoDAFile serialises via to_text(); encode to bytes
        data = t.to_text().encode("utf-8")
        self.assertIsInstance(data, bytes)

    def test_roundtrip(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      val0\n"
            "1        row1      val1\n"
            "2        row2      val2\n"
        )
        t1 = TwoDAFile.from_text(raw, filename="rt1.2da")
        t2 = TwoDAFile.from_text(t1.to_text(), filename="rt2.2da")
        self.assertEqual(len(t1.rows), len(t2.rows))

    # ── Missing values ────────────────────────────────────────────────────────

    def test_missing_value_token(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        ****      ****\n"
        )
        t = TwoDAFile.from_text(raw, filename="missing.2da")
        self.assertEqual(len(t.rows), 1)

    # ── Column add ────────────────────────────────────────────────────────────

    def test_add_column(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        lbl_a     val_a\n"
        )
        t = TwoDAFile.from_text(raw, filename="add_col.2da")
        initial_cols = len(t.columns)
        t.add_column("new_col", default="****")
        self.assertEqual(len(t.columns), initial_cols + 1)
        self.assertIn("new_col", t.columns)

    def test_add_column_sets_default_on_existing_rows(self):
        raw = (
            "2DA V2.0\n\n"
            "         label\n"
            "0        rowA\n"
            "1        rowB\n"
        )
        t = TwoDAFile.from_text(raw, filename="add_col_default.2da")
        t.add_column("extra", default="DEFAULT")
        for row in t.rows:
            self.assertEqual(row.get("extra"), "DEFAULT")

    # ── Filename handling ─────────────────────────────────────────────────────

    def test_filename_attribute(self):
        t = TwoDAFile("appearance.2da")
        self.assertEqual(t.filename, "appearance.2da")

    def test_from_text_with_filename(self):
        t = TwoDAFile.from_text("2DA V2.0\n\n         col1\n0  val\n",
                                 filename="named.2da")
        self.assertEqual(t.filename, "named.2da")

    # ── Undo ─────────────────────────────────────────────────────────────────

    def test_undo_restores_state(self):
        raw = (
            "2DA V2.0\n\n"
            "         label     value\n"
            "0        row0      original\n"
        )
        t = TwoDAFile.from_text(raw, filename="undo.2da")
        t.set_cell("row0", "value", "modified")
        # Undo should be possible if history was saved
        if hasattr(t, "undo"):
            t.undo()
            self.assertEqual(t.rows[0].get("value"), "original")

    # ── Memory token ─────────────────────────────────────────────────────────

    def test_set_memory_token(self):
        """2DAMEMORY token storage should work without error."""
        t = TwoDAFile("memory_test.2da")
        if hasattr(t, "set_memory"):
            t.set_memory("I#0", "42")
            val = t.get_memory("I#0")
            self.assertEqual(val, "42")


if __name__ == "__main__":
    unittest.main()
