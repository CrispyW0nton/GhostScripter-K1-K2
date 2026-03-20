#!/usr/bin/env python3
"""
test_gff_writer.py — Unit tests for the shared GFF3 binary writer module.

Covers:
  - GFFType enum values
  - GFFStruct field-add helpers
  - GFF3Writer header magic / version
  - GFF3Writer: BYTE, WORD, DWORD, INT, FLOAT, RESREF, CEXOSTRING,
                CEXOLOCSTRING, VOID, DWORD64, INT64, DOUBLE, VECTOR
  - Nested STRUCT fields
  - LIST fields (empty and non-empty)
  - Multiple labels; label section size
  - Header section offsets are consistent
  - Rebuild (build() twice) produces same output
"""
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.export.gff_writer import GFFType, GFFStruct, GFF3Writer


# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_header(data: bytes) -> dict:
    """Unpack the 56-byte GFF header into a dict."""
    (
        file_type, version,
        struct_off, struct_cnt,
        field_off,  field_cnt,
        label_off,  label_cnt,
        fdata_off,  fdata_cnt,
        fi_off,     fi_cnt,
        li_off,     li_cnt,
    ) = struct.unpack_from("<4s4sIIIIIIIIIIII", data, 0)
    return dict(
        file_type=file_type, version=version,
        struct_off=struct_off, struct_cnt=struct_cnt,
        field_off=field_off,   field_cnt=field_cnt,
        label_off=label_off,   label_cnt=label_cnt,
        fdata_off=fdata_off,   fdata_cnt=fdata_cnt,
        fi_off=fi_off,         fi_cnt=fi_cnt,
        li_off=li_off,         li_cnt=li_cnt,
    )


# ── GFFType ────────────────────────────────────────────────────────────────────

class TestGFFType(unittest.TestCase):

    def test_byte_value(self):
        self.assertEqual(GFFType.BYTE, 0)

    def test_resref_value(self):
        self.assertEqual(GFFType.RESREF, 11)

    def test_list_value(self):
        self.assertEqual(GFFType.LIST, 15)

    def test_vector_value(self):
        self.assertEqual(GFFType.VECTOR, 17)

    def test_all_types_distinct(self):
        values = [t.value for t in GFFType]
        self.assertEqual(len(values), len(set(values)))


# ── GFFStruct helpers ──────────────────────────────────────────────────────────

class TestGFFStructHelpers(unittest.TestCase):

    def setUp(self):
        self.s = GFFStruct(struct_type=0)

    def test_add_byte(self):
        self.s.add_byte("Flag", 255)
        label, ftype, val = self.s.fields[0]
        self.assertEqual(label, "Flag")
        self.assertEqual(ftype, GFFType.BYTE)
        self.assertEqual(val, 255)

    def test_add_word(self):
        self.s.add_word("W", 1000)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.WORD)
        self.assertEqual(val, 1000)

    def test_add_dword(self):
        self.s.add_dword("D", 999999)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.DWORD)

    def test_add_int(self):
        self.s.add_int("I", -1)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.INT)

    def test_add_float(self):
        self.s.add_float("F", 3.14)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.FLOAT)

    def test_add_resref(self):
        self.s.add_resref("R", "nw_mymod")
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.RESREF)
        self.assertEqual(val, "nw_mymod")

    def test_add_cexo(self):
        self.s.add_cexo("S", "hello")
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.CEXOSTRING)
        self.assertEqual(val, "hello")

    def test_add_locstring(self):
        self.s.add_locstring("L", strref=100, text="Quest started.")
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.CEXOLOCSTRING)
        self.assertEqual(val, (100, "Quest started."))

    def test_chaining(self):
        result = self.s.add_byte("A", 1).add_word("B", 2).add_dword("C", 3)
        self.assertIs(result, self.s)
        self.assertEqual(len(self.s.fields), 3)

    def test_add_struct(self):
        child = GFFStruct(1)
        self.s.add_struct("Child", child)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.STRUCT)
        self.assertIs(val, child)

    def test_add_list(self):
        items = [GFFStruct(i) for i in range(3)]
        self.s.add_list("Items", items)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.LIST)
        self.assertEqual(len(val), 3)

    def test_add_vector(self):
        self.s.add_vector("Pos", 1.0, 2.0, 3.0)
        _, ftype, val = self.s.fields[0]
        self.assertEqual(ftype, GFFType.VECTOR)
        self.assertEqual(val, (1.0, 2.0, 3.0))


# ── GFF3Writer header ──────────────────────────────────────────────────────────

class TestGFF3WriterHeader(unittest.TestCase):

    def _build(self, file_type="TST ") -> bytes:
        w = GFF3Writer(file_type)
        return w.build()

    def test_returns_bytes(self):
        data = self._build()
        self.assertIsInstance(data, bytes)

    def test_minimum_size(self):
        data = self._build()
        self.assertGreaterEqual(len(data), 56)

    def test_magic_exact(self):
        data = self._build("DLG ")
        self.assertEqual(data[:4], b"DLG ")

    def test_magic_padded(self):
        data = self._build("JRL")   # short → padded to "JRL "
        self.assertEqual(data[:4], b"JRL ")

    def test_version(self):
        data = self._build()
        self.assertEqual(data[4:8], b"V3.2")

    def test_struct_offset_is_56(self):
        data = self._build()
        h = parse_header(data)
        self.assertEqual(h["struct_off"], 56)

    def test_struct_count_at_least_one(self):
        data = self._build()
        h = parse_header(data)
        self.assertGreaterEqual(h["struct_cnt"], 1)

    def test_offsets_contiguous(self):
        data = self._build()
        h = parse_header(data)
        # field section starts right after struct section
        self.assertEqual(h["field_off"],
                         h["struct_off"] + h["struct_cnt"] * 12)


# ── GFF3Writer scalar fields ───────────────────────────────────────────────────

class TestGFF3WriterScalars(unittest.TestCase):

    def _build_with(self, *add_calls) -> bytes:
        w = GFF3Writer("TST ")
        for fn, args in add_calls:
            getattr(w.root, fn)(*args)
        return w.build()

    def test_byte_field(self):
        data = self._build_with(("add_byte", ("Flag", 1)))
        self.assertGreater(len(data), 56)
        h = parse_header(data)
        self.assertEqual(h["field_cnt"], 1)

    def test_cexostring_in_binary(self):
        data = self._build_with(("add_cexo", ("Tag", "K_MYQUEST")))
        self.assertIn(b"K_MYQUEST", data)

    def test_resref_lowercase_in_binary(self):
        data = self._build_with(("add_resref", ("Script", "NW_MYMOD")))
        self.assertIn(b"nw_mymod", data)

    def test_resref_truncated_to_16(self):
        long_name = "a" * 20
        data = self._build_with(("add_resref", ("R", long_name)))
        self.assertIn(b"a" * 16, data)
        self.assertNotIn(b"a" * 17, data)

    def test_locstring_strref_in_binary(self):
        w = GFF3Writer("TST ")
        w.root.add_locstring("Name", strref=42, text="Quest Name")
        data = w.build()
        self.assertIn(b"Quest Name", data)

    def test_multiple_fields(self):
        w = GFF3Writer("TST ")
        w.root.add_byte("A", 1)
        w.root.add_word("B", 2)
        w.root.add_dword("C", 3)
        w.root.add_cexo("D", "hello")
        data = w.build()
        h = parse_header(data)
        self.assertEqual(h["field_cnt"], 4)
        self.assertIn(b"hello", data)

    def test_label_count_matches_unique_names(self):
        w = GFF3Writer("TST ")
        w.root.add_byte("Alpha", 1)
        w.root.add_byte("Alpha", 2)   # same label reused
        w.root.add_byte("Beta",  3)
        data = w.build()
        h = parse_header(data)
        self.assertEqual(h["label_cnt"], 2)  # Alpha + Beta

    def test_void_field(self):
        w = GFF3Writer("TST ")
        w.root.add_void("Blob", b"\xDE\xAD\xBE\xEF")
        data = w.build()
        self.assertIn(b"\xDE\xAD\xBE\xEF", data)

    def test_vector_field(self):
        w = GFF3Writer("TST ")
        w.root.add_vector("Pos", 1.0, 2.0, 3.0)
        data = w.build()
        expected = struct.pack("<fff", 1.0, 2.0, 3.0)
        self.assertIn(expected, data)

    def test_dword64_field(self):
        w = GFF3Writer("TST ")
        w.root.add_dword64("Big", 0xDEADBEEFCAFEBABE)
        data = w.build()
        self.assertIn(struct.pack("<Q", 0xDEADBEEFCAFEBABE), data)

    def test_int64_field(self):
        w = GFF3Writer("TST ")
        w.root.add_int64("NegBig", -1)
        data = w.build()
        self.assertIn(struct.pack("<q", -1), data)

    def test_double_field(self):
        w = GFF3Writer("TST ")
        w.root.add_double("Pi", 3.141592653589793)
        data = w.build()
        self.assertIn(struct.pack("<d", 3.141592653589793), data)


# ── GFF3Writer nested struct ───────────────────────────────────────────────────

class TestGFF3WriterNestedStruct(unittest.TestCase):

    def test_struct_increases_struct_count(self):
        w = GFF3Writer("TST ")
        child = GFFStruct(1)
        child.add_cexo("ChildTag", "inner")
        w.root.add_struct("Sub", child)
        data = w.build()
        h = parse_header(data)
        # root struct + child struct
        self.assertEqual(h["struct_cnt"], 2)

    def test_child_cexo_in_binary(self):
        w = GFF3Writer("TST ")
        child = GFFStruct(1)
        child.add_cexo("ChildTag", "inner_value")
        w.root.add_struct("Sub", child)
        data = w.build()
        self.assertIn(b"inner_value", data)

    def test_deep_nesting(self):
        w = GFF3Writer("TST ")
        a = GFFStruct(1)
        b = GFFStruct(2)
        c = GFFStruct(3)
        c.add_cexo("Deep", "deep_val")
        b.add_struct("C", c)
        a.add_struct("B", b)
        w.root.add_struct("A", a)
        data = w.build()
        h = parse_header(data)
        self.assertEqual(h["struct_cnt"], 4)  # root + a + b + c
        self.assertIn(b"deep_val", data)


# ── GFF3Writer LIST ────────────────────────────────────────────────────────────

class TestGFF3WriterList(unittest.TestCase):

    def test_empty_list(self):
        w = GFF3Writer("TST ")
        w.root.add_list("Items", [])
        data = w.build()
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 56)

    def test_list_of_structs(self):
        w = GFF3Writer("TST ")
        items = []
        for i in range(3):
            s = GFFStruct(i)
            s.add_cexo("Tag", f"item_{i}")
            items.append(s)
        w.root.add_list("Items", items)
        data = w.build()
        h = parse_header(data)
        # root + 3 child structs
        self.assertEqual(h["struct_cnt"], 4)
        for i in range(3):
            self.assertIn(f"item_{i}".encode(), data)

    def test_list_indices_section_populated(self):
        w = GFF3Writer("TST ")
        w.root.add_list("Items", [GFFStruct(0), GFFStruct(1)])
        data = w.build()
        h = parse_header(data)
        self.assertGreater(h["li_cnt"], 0)


# ── GFF3Writer rebuild ─────────────────────────────────────────────────────────

class TestGFF3WriterRebuild(unittest.TestCase):

    def test_rebuild_identical(self):
        w = GFF3Writer("TST ")
        w.root.add_cexo("Name", "test")
        w.root.add_byte("Flag", 1)
        data1 = w.build()
        data2 = w.build()
        self.assertEqual(data1, data2)

    def test_rebuild_different_file_types(self):
        w1 = GFF3Writer("DLG ")
        w2 = GFF3Writer("JRL ")
        w1.root.add_cexo("X", "same")
        w2.root.add_cexo("X", "same")
        self.assertEqual(w1.build()[4:], w2.build()[4:])   # content identical
        self.assertNotEqual(w1.build()[:4], w2.build()[:4])  # magic differs


if __name__ == "__main__":
    unittest.main()
