"""Parser robustness tests — error-path coverage inspired by OldRepublicDevs/PyKotor patterns.

PyKotor's test suite systematically tests corrupt/truncated input and bad-path I/O
for every format (test_read_raises / test_write_raises / corrupt-data patterns).
These tests apply the same discipline to GhostScripter's own binary readers,
written against the *actual* public API (no guessing).

Rules:
- No imports from pykotor — stays self-contained.
- Binary blobs built inline (no file fixtures needed) following PyKotor style.
- Each test class focuses on one format with exact exception types.
- Covers: GFF3 reader, 2DA parser, TLK parser, ERF writer, GFFWriter roundtrip.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path


# ── binary builder helpers ────────────────────────────────────────────────────

def _build_minimal_gff3(file_type: bytes = b"DLG ", version: bytes = b"V3.2") -> bytes:
    """Return the smallest valid 56-byte GFF3 header with zero structs/fields/labels."""
    assert len(file_type) == 4
    assert len(version) == 4
    offsets = struct.pack("<IIIIIIIIIIII", 56, 0, 56, 0, 56, 0, 56, 0, 56, 0, 56, 0)
    return file_type + version + offsets


def _build_tlk(texts: list[str], lang_id: int = 0) -> bytes:
    """Return a correctly-structured TLK binary with the given strings.

    Entry format: <I16sIIIIf  (flags, resref[16], vol, pitch, off_str, str_size, sound_len)
    """
    count = len(texts)
    str_offset = 20 + count * 40
    header = struct.pack("<4s4sIII", b"TLK ", b"V3.0", lang_id, count, str_offset)
    str_data = b""
    entries = b""
    for text in texts:
        encoded = text.encode("cp1252") if text else b""
        off = len(str_data)
        flags = 1 if text else 0
        entries += struct.pack("<I16sIIIIf", flags, b"\x00" * 16, 0, 0, off, len(encoded), 0.0)
        str_data += encoded
    return header + entries + str_data


# ── GFF3 reader ───────────────────────────────────────────────────────────────

class TestGFF3ReaderErrors(unittest.TestCase):
    """GFF3Reader must reject malformed input without crashing."""

    def setUp(self) -> None:
        from ghostscripter.core.export.dlg_reader import GFF3Reader, GFF3ReadError
        self.GFF3Reader = GFF3Reader
        self.GFF3ReadError = GFF3ReadError

    def test_too_short_raises(self) -> None:
        """Files shorter than the 56-byte GFF3 header must raise GFF3ReadError."""
        r = self.GFF3Reader.from_bytes(b"\x00" * 10)
        with self.assertRaises(self.GFF3ReadError):
            r._parse_header()

    def test_empty_bytes_raises(self) -> None:
        r = self.GFF3Reader.from_bytes(b"")
        with self.assertRaises(self.GFF3ReadError):
            r._parse_header()

    def test_parse_on_truncated_raises(self) -> None:
        """parse() entry-point must raise GFF3ReadError on 8-byte input."""
        r = self.GFF3Reader.from_bytes(b"GFF V3.2")
        with self.assertRaises(self.GFF3ReadError):
            r.parse()

    def test_bad_version_stored_not_corrected(self) -> None:
        """Unrecognised version string is stored as-is, not silently corrected."""
        r = self.GFF3Reader.from_bytes(b"GFF " + b"V9.9" + b"\x00" * 48)
        r._parse_header()
        self.assertEqual(r.file_version, "V9.9")

    def test_file_type_stripped_of_spaces(self) -> None:
        data = _build_minimal_gff3(b"DLG ", b"V3.2")
        r = self.GFF3Reader.from_bytes(data)
        r._parse_header()
        self.assertEqual(r.file_type, "DLG")

    def test_utc_file_type_recognised(self) -> None:
        data = _build_minimal_gff3(b"UTC ", b"V3.2")
        r = self.GFF3Reader.from_bytes(data)
        r._parse_header()
        self.assertEqual(r.file_type, "UTC")

    def test_version_v32_accepted(self) -> None:
        data = _build_minimal_gff3(b"GFF ", b"V3.2")
        r = self.GFF3Reader.from_bytes(data)
        r._parse_header()
        self.assertEqual(r.file_version, "V3.2")

    def test_zero_struct_root_returns_dict(self) -> None:
        """A GFF3 with zero structs: read_root returns an empty dict (no crash)."""
        data = _build_minimal_gff3(b"GFF ", b"V3.2") + b"\x00" * 64
        r = self.GFF3Reader.from_bytes(data)
        r._parse_header()
        root = r.read_root()
        self.assertIsInstance(root, dict)


# ── DLG reader ────────────────────────────────────────────────────────────────

class TestDLGReaderErrors(unittest.TestCase):
    """DLG reader must reject clearly-corrupt input."""

    def test_totally_corrupt_bytes_raises(self) -> None:
        """Completely corrupt bytes must raise some exception (not silently succeed)."""
        from ghostscripter.core.export.dlg_reader import read_dlg_bytes
        with self.assertRaises(Exception):
            read_dlg_bytes(b"GARBAGE_NOT_A_GFF_FILE_AT_ALL_XXXX", "test")

    def test_read_dlg_bytes_valid_header_returns_dialogue(self) -> None:
        """A minimally-valid GFF3 blob produces a DialogueFile without error."""
        from ghostscripter.core.export.dlg_reader import read_dlg_bytes, DialogueFile
        # Minimal DLG GFF3: zero entries/replies is a valid empty dialogue
        data = _build_minimal_gff3(b"DLG ", b"V3.2") + b"\x00" * 128
        result = read_dlg_bytes(data, "test_dlg")
        self.assertIsInstance(result, DialogueFile)


# ── TwoDA parser ──────────────────────────────────────────────────────────────

class TestTwoDAParserErrors(unittest.TestCase):
    """TwoDAFile.from_binary must reject corrupt/unsupported input."""

    def setUp(self) -> None:
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        self.TwoDAFile = TwoDAFile

    def test_bad_magic_raises(self) -> None:
        t = self.TwoDAFile()
        with self.assertRaises(ValueError):
            t.from_binary(b"NOTTWODA" + b"\x00" * 50)

    def test_bad_version_raises(self) -> None:
        t = self.TwoDAFile()
        with self.assertRaises(ValueError):
            t.from_binary(b"2DA " + b"V1.x" + b"\x00" * 50)

    def test_empty_bytes_raises(self) -> None:
        t = self.TwoDAFile()
        with self.assertRaises((ValueError, struct.error)):
            t.from_binary(b"")

    def test_truncated_after_header_raises(self) -> None:
        t = self.TwoDAFile()
        with self.assertRaises((ValueError, struct.error)):
            t.from_binary(b"2DA V2.b\n")

    def test_roundtrip_binary_preserves_data(self) -> None:
        """A table survives a binary (2DA V2.b) roundtrip."""
        t = self.TwoDAFile()
        t.columns = ["label", "race", "gender"]
        t.add_row("0", {"label": "Human", "race": "1", "gender": "0"})
        t.add_row("1", {"label": "Twi'lek", "race": "2", "gender": "1"})
        raw = t.to_binary()
        # from_binary is a classmethod — call on the class, not an instance
        t2 = self.TwoDAFile.from_binary(raw)
        self.assertEqual(t2.get_row_by_index(0).data["label"], "Human")
        self.assertEqual(t2.get_row_by_index(1).data["race"], "2")

    def test_roundtrip_text_preserves_data(self) -> None:
        """A table survives a text (2DA V2.0) roundtrip."""
        t = self.TwoDAFile()
        t.columns = ["name", "value"]
        t.add_row("0", {"name": "alpha", "value": "10"})
        text = t.to_text()
        # from_text is a classmethod — call on the class, not an instance
        t2 = self.TwoDAFile.from_text(text)
        self.assertEqual(t2.get_row_by_index(0).data["name"], "alpha")
        self.assertEqual(t2.get_row_by_index(0).data["value"], "10")

    def test_empty_cell_token_survives_binary_roundtrip(self) -> None:
        """The special '****' empty token must survive binary round-trip."""
        t = self.TwoDAFile()
        t.columns = ["a", "b"]
        t.add_row("0", {"a": "****", "b": "x"})
        raw = t.to_binary()
        # from_binary is a classmethod — call on the class, not an instance
        t2 = self.TwoDAFile.from_binary(raw)
        val = t2.get_row_by_index(0).data.get("a", "")
        # empty cell may come back as "" or "****" depending on implementation
        self.assertIn(val, ("", "****"))

    def test_row_count_after_add_and_remove(self) -> None:
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "a"})
        t.add_row("1", {"x": "b"})
        t.add_row("2", {"x": "c"})
        self.assertEqual(len(t.rows), 3)
        t.remove_row_by_index(1)
        self.assertEqual(len(t.rows), 2)

    def test_copy_row_increases_count(self) -> None:
        # copy_row signature: (source_index, new_label=None, overrides=None)
        # Pass the data dict as keyword arg 'overrides', not positional new_label
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "original"})
        t.copy_row(0, overrides={"x": "copy"})
        self.assertEqual(len(t.rows), 2)
        self.assertEqual(t.get_row_by_index(1).data["x"], "copy")

    def test_out_of_range_copy_raises(self) -> None:
        t = self.TwoDAFile()
        t.columns = ["x"]
        with self.assertRaises(IndexError):
            t.copy_row(999, {})


# ── TLK parser ────────────────────────────────────────────────────────────────

class TestTLKParserErrors(unittest.TestCase):
    """TLKFile._parse must reject corrupt input and handle edge-cases."""

    def setUp(self) -> None:
        from ghostscripter.core.models.tlk import TLKFile
        self.TLKFile = TLKFile

    def test_bad_magic_raises(self) -> None:
        tlk = self.TLKFile()
        with self.assertRaises(ValueError):
            tlk._parse(b"ERF " + b"\x00" * 200)

    def test_too_short_raises(self) -> None:
        tlk = self.TLKFile()
        with self.assertRaises(ValueError):
            tlk._parse(b"TLK " + b"\x00" * 5)

    def test_empty_bytes_raises(self) -> None:
        tlk = self.TLKFile()
        with self.assertRaises((ValueError, struct.error)):
            tlk._parse(b"")

    def test_zero_entry_count_ok(self) -> None:
        """Zero entries is valid; produces empty list."""
        blob = _build_tlk([])
        tlk = self.TLKFile()
        tlk._parse(blob)
        self.assertEqual(len(tlk.entries), 0)

    def test_text_preserved_through_parse(self) -> None:
        """Text in each entry survives parsing."""
        blob = _build_tlk(["Hello", "World", ""])
        tlk = self.TLKFile()
        tlk._parse(blob)
        self.assertEqual(len(tlk.entries), 3)
        self.assertEqual(tlk.entries[0].text, "Hello")
        self.assertEqual(tlk.entries[1].text, "World")

    def test_get_string_out_of_bounds_returns_default(self) -> None:
        blob = _build_tlk(["Hello"])
        tlk = self.TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.get_string(9999, "MISSING"), "MISSING")

    def test_get_string_negative_returns_default(self) -> None:
        blob = _build_tlk(["Hello"])
        tlk = self.TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.get_string(-1, "FALLBACK"), "FALLBACK")

    def test_get_string_in_bounds(self) -> None:
        blob = _build_tlk(["Bastila"])
        tlk = self.TLKFile()
        tlk._parse(blob)
        self.assertEqual(tlk.get_string(0, "DEFAULT"), "Bastila")


# ── ERF writer ────────────────────────────────────────────────────────────────

def _erf_list_resrefs(data: bytes) -> list[str]:
    """Parse the key list from raw ERF bytes and return resref strings."""
    # ERF V1.0 header layout (after 8-byte magic+version):
    # lang_count, lang_size, entry_count, offset_lang, offset_key, offset_res
    _, _, entry_count, _, offset_key, _ = struct.unpack_from("<IIIIII", data, 8)
    resrefs = []
    for i in range(entry_count):
        resref_raw = data[offset_key + i * 24: offset_key + i * 24 + 16]
        resrefs.append(resref_raw.rstrip(b"\x00").decode("ascii", errors="ignore"))
    return resrefs


def _erf_get_resource(data: bytes, resref: str) -> bytes | None:
    """Extract resource payload from raw ERF bytes by resref."""
    _, _, entry_count, _, offset_key, offset_res = struct.unpack_from("<IIIIII", data, 8)
    for i in range(entry_count):
        rr = data[offset_key + i * 24: offset_key + i * 24 + 16].rstrip(b"\x00").decode("ascii", errors="ignore")
        if rr == resref:
            res_offset, res_size = struct.unpack_from("<II", data, offset_res + i * 8)
            return data[res_offset: res_offset + res_size]
    return None


class TestERFWriterRobustness(unittest.TestCase):
    """ERFWriter must produce valid output and handle edge cases."""

    def setUp(self) -> None:
        from ghostscripter.core.export.erf_writer import ERFWriter
        self.ERFWriter = ERFWriter

    def test_empty_erf_magic_and_version(self) -> None:
        ew = self.ERFWriter("ERF ")
        data = ew.build()
        self.assertEqual(data[:4], b"ERF ")
        self.assertEqual(data[4:8], b"V1.0")

    def test_mod_file_type_in_header(self) -> None:
        ew = self.ERFWriter("MOD ")
        data = ew.build()
        self.assertEqual(data[:4], b"MOD ")

    def test_rim_file_type_in_header(self) -> None:
        ew = self.ERFWriter("RIM ")
        data = ew.build()
        self.assertEqual(data[:4], b"RIM ")

    def test_single_resource_resref_present(self) -> None:
        """A resource added via add_resource() appears in the key list."""
        ew = self.ERFWriter("ERF ")
        ew.add_resource("myscript", "ncs", b"NCS V1.0\x00payload")
        data = ew.build()
        self.assertIn("myscript", _erf_list_resrefs(data))

    def test_single_resource_payload_recoverable(self) -> None:
        """The raw payload is recoverable by parsing the key+resource lists."""
        payload = b"NCS V1.0\x00testdata"
        ew = self.ERFWriter("ERF ")
        ew.add_resource("myscript", "ncs", payload)
        data = ew.build()
        recovered = _erf_get_resource(data, "myscript")
        self.assertEqual(recovered, payload)

    def test_multiple_resources_all_present(self) -> None:
        ew = self.ERFWriter("ERF ")
        ew.add_resource("script1", "ncs", b"abc")
        ew.add_resource("script2", "ncs", b"def")
        ew.add_resource("dialog1", "dlg", b"ghi")
        data = ew.build()
        names = set(_erf_list_resrefs(data))
        self.assertIn("script1", names)
        self.assertIn("script2", names)
        self.assertIn("dialog1", names)

    def test_resref_max_16_chars_not_truncated(self) -> None:
        name16 = "a" * 16
        ew = self.ERFWriter("ERF ")
        ew.add_resource(name16, "ncs", b"data")
        data = ew.build()
        self.assertIn(name16, _erf_list_resrefs(data))

    def test_resref_over_16_chars_stored_as_max_16(self) -> None:
        """Names longer than 16 chars are silently truncated — KotOR binary format limit."""
        long_name = "a" * 24
        ew = self.ERFWriter("ERF ")
        ew.add_resource(long_name, "ncs", b"data")
        data = ew.build()
        names = _erf_list_resrefs(data)
        self.assertTrue(all(len(n) <= 16 for n in names))

    def test_build_is_deterministic(self) -> None:
        """Two identical writers produce byte-identical output."""
        def make() -> bytes:
            ew = self.ERFWriter("ERF ")
            ew.add_resource("s1", "ncs", b"payload")
            return ew.build()
        self.assertEqual(make(), make())

    def test_write_to_file_produces_readable_output(self) -> None:
        """write() produces a file whose bytes have the correct ERF magic."""
        ew = self.ERFWriter("ERF ")
        ew.add_resource("k_test", "ncs", b"NCS V1.0\x00")
        with tempfile.NamedTemporaryFile(suffix=".erf", delete=False) as f:
            tmp = Path(f.name)
        try:
            ew.write([], tmp)  # write() signature: entries, path
            raw = tmp.read_bytes()
            self.assertEqual(raw[:4], b"ERF ")
        finally:
            tmp.unlink(missing_ok=True)


# ── GFFWriter roundtrip ───────────────────────────────────────────────────────

class TestGFFWriterRoundtrip(unittest.TestCase):
    """GFFWriter output must have correct structure."""

    def _make_utc_gff(self) -> bytes:
        from ghostscripter.core.export.gff_writer import GFF3Writer
        w = GFF3Writer("UTC")
        w.root.add_string("Tag", "bastila_solo")
        w.root.add_uint16("Appearance_Type", 42)
        w.root.add_int32("Alignment", -50)
        return w.build()

    def test_magic_bytes_correct(self) -> None:
        data = self._make_utc_gff()
        self.assertEqual(data[:4], b"UTC ")

    def test_version_bytes_correct(self) -> None:
        data = self._make_utc_gff()
        self.assertEqual(data[4:8], b"V3.2")

    def test_header_minimum_size(self) -> None:
        data = self._make_utc_gff()
        self.assertGreaterEqual(len(data), 56)

    def test_gff3reader_parses_type(self) -> None:
        """GFF3Reader can read back the file_type from GFFWriter output."""
        from ghostscripter.core.export.dlg_reader import GFF3Reader
        data = self._make_utc_gff()
        r = GFF3Reader.from_bytes(data)
        r._parse_header()
        self.assertEqual(r.file_type, "UTC")
        self.assertEqual(r.file_version, "V3.2")

    def test_string_field_survives_roundtrip(self) -> None:
        from ghostscripter.core.export.gff_writer import GFF3Writer
        from ghostscripter.core.export.dlg_reader import GFF3Reader
        w = GFF3Writer("UTC")
        w.root.add_string("Tag", "bastila_solo")
        data = w.build()
        root = GFF3Reader.from_bytes(data).read_root()
        self.assertEqual(root.get("Tag"), "bastila_solo")

    def test_uint16_field_survives_roundtrip(self) -> None:
        from ghostscripter.core.export.gff_writer import GFF3Writer
        from ghostscripter.core.export.dlg_reader import GFF3Reader
        w = GFF3Writer("UTC")
        w.root.add_uint16("Appearance_Type", 123)
        data = w.build()
        root = GFF3Reader.from_bytes(data).read_root()
        self.assertEqual(root.get("Appearance_Type"), 123)

    def test_int32_negative_survives_roundtrip(self) -> None:
        from ghostscripter.core.export.gff_writer import GFF3Writer
        from ghostscripter.core.export.dlg_reader import GFF3Reader
        w = GFF3Writer("UTC")
        w.root.add_int32("Alignment", -50)
        data = w.build()
        root = GFF3Reader.from_bytes(data).read_root()
        self.assertEqual(root.get("Alignment"), -50)

    def test_build_is_deterministic(self) -> None:
        self.assertEqual(self._make_utc_gff(), self._make_utc_gff())

    def test_empty_writer_still_produces_header(self) -> None:
        from ghostscripter.core.export.gff_writer import GFF3Writer
        data = GFF3Writer("GFF").build()
        self.assertEqual(data[:4], b"GFF ")
        self.assertGreaterEqual(len(data), 56)


# ── ResourceManager safety ────────────────────────────────────────────────────

class TestResourceManagerSafety(unittest.TestCase):
    """ResourceManager must not crash on nonsense or empty game paths."""

    def test_nonexistent_path_does_not_crash(self) -> None:
        """load_game on a clearly-nonexistent path must return False, not raise."""
        from ghostscripter.core.resource_manager import ResourceManager
        rm = ResourceManager()
        result = rm.load_game(Path("/nonexistent/path/to/nowhere"))
        self.assertFalse(result)

    def test_empty_temp_dir_override_only_mode(self) -> None:
        """load_game on an empty dir (no chitin.key) returns a bool without crashing."""
        from ghostscripter.core.resource_manager import ResourceManager
        with tempfile.TemporaryDirectory() as d:
            rm = ResourceManager()
            result = rm.load_game(Path(d))
            # May be True (override-only) or False — must not raise
            self.assertIsInstance(result, bool)

    def test_is_loaded_false_before_load(self) -> None:
        # is_loaded is a @property, not a method — access without parentheses
        from ghostscripter.core.resource_manager import ResourceManager
        rm = ResourceManager()
        self.assertFalse(rm.is_loaded)


# ── TwoDA PyKotor-parity API tests ───────────────────────────────────────────

class TestTwoDAAPIParity(unittest.TestCase):
    """Tests inspired by PyKotor's test_twoda.py validate_io / test_row_max patterns.

    PyKotor validates:
      - get_cell(row_idx, col_name)    — ergonomic cell accessor
      - label_max()                    — equals row count
      - for-loop iteration             — __iter__ over rows
      - detect_2da(data)               — format tag from raw bytes

    These tests apply the same discipline to our TwoDAFile implementation
    without importing PyKotor.
    """

    def setUp(self) -> None:
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile, detect_2da
        self.TwoDAFile = TwoDAFile
        self.detect_2da = detect_2da

    # ── get_cell ─────────────────────────────────────────────

    def test_get_cell_basic_values(self) -> None:
        """get_cell returns correct values across all three rows — mirrors PyKotor validate_io."""
        t = self.TwoDAFile()
        t.columns = ["col1", "col2", "col3"]
        t.add_row("10", {"col1": "abc", "col2": "def", "col3": "ghi"})
        t.add_row("1",  {"col1": "def", "col2": "ghi", "col3": "123"})
        t.add_row("2",  {"col1": "123", "col2": "",    "col3": "abc"})

        self.assertEqual(t.get_cell(0, "col1"), "abc")
        self.assertEqual(t.get_cell(0, "col2"), "def")
        self.assertEqual(t.get_cell(0, "col3"), "ghi")

        self.assertEqual(t.get_cell(1, "col1"), "def")
        self.assertEqual(t.get_cell(1, "col2"), "ghi")
        self.assertEqual(t.get_cell(1, "col3"), "123")

        self.assertEqual(t.get_cell(2, "col1"), "123")
        self.assertEqual(t.get_cell(2, "col3"), "abc")

    def test_get_cell_blank_returns_empty_string(self) -> None:
        """get_cell maps the '****' blank token to '' — matches PyKotor get_cell('', ...) contract."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "****"})
        self.assertEqual(t.get_cell(0, "x"), "")

    def test_get_cell_missing_col_returns_empty_string(self) -> None:
        """Missing column also falls through to '' (no crash)."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "val"})
        self.assertEqual(t.get_cell(0, "y"), "")

    def test_get_cell_out_of_range_raises_index_error(self) -> None:
        """Out-of-range row_index raises IndexError."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "v"})
        with self.assertRaises(IndexError):
            t.get_cell(99, "x")
        with self.assertRaises(IndexError):
            t.get_cell(-1, "x")

    def test_get_cell_roundtrip_binary(self) -> None:
        """get_cell values survive a binary round-trip."""
        t = self.TwoDAFile()
        t.columns = ["race", "appearance"]
        t.add_row("0", {"race": "Human",   "appearance": "1"})
        t.add_row("1", {"race": "Twi'lek", "appearance": "2"})
        raw = t.to_binary()
        t2 = self.TwoDAFile.from_binary(raw)
        self.assertEqual(t2.get_cell(0, "race"), "Human")
        self.assertEqual(t2.get_cell(1, "appearance"), "2")

    def test_get_cell_roundtrip_text(self) -> None:
        """get_cell values survive a text round-trip."""
        t = self.TwoDAFile()
        t.columns = ["name", "value"]
        t.add_row("0", {"name": "alpha", "value": "10"})
        txt = t.to_text()
        t2 = self.TwoDAFile.from_text(txt)
        self.assertEqual(t2.get_cell(0, "name"),  "alpha")
        self.assertEqual(t2.get_cell(0, "value"), "10")

    # ── label_max ────────────────────────────────────────────

    def test_label_max_zero(self) -> None:
        """label_max() is 0 on an empty table."""
        t = self.TwoDAFile()
        self.assertEqual(t.label_max(), 0)

    def test_label_max_grows_with_rows(self) -> None:
        """label_max() equals len(rows) as rows are added — mirrors PyKotor test_row_max."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "a"})
        self.assertEqual(t.label_max(), 1)
        t.add_row("1", {"x": "b"})
        self.assertEqual(t.label_max(), 2)
        t.add_row("2", {"x": "c"})
        self.assertEqual(t.label_max(), 3)

    def test_label_max_equals_len(self) -> None:
        """label_max() and len() must agree."""
        t = self.TwoDAFile()
        t.columns = ["y"]
        for i in range(5):
            t.add_row(str(i), {"y": str(i * 10)})
        self.assertEqual(t.label_max(), len(t))
        self.assertEqual(t.label_max(), 5)

    def test_label_max_after_remove(self) -> None:
        """label_max() decreases after a row is removed."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "a"})
        t.add_row("1", {"x": "b"})
        t.remove_row_by_index(0)
        self.assertEqual(t.label_max(), 1)

    # ── __iter__ ─────────────────────────────────────────────

    def test_iter_yields_all_rows(self) -> None:
        """Iterating a TwoDAFile yields every TwoDARow in order."""
        t = self.TwoDAFile()
        t.columns = ["v"]
        t.add_row("0", {"v": "first"})
        t.add_row("1", {"v": "second"})
        t.add_row("2", {"v": "third"})
        collected = list(t)
        self.assertEqual(len(collected), 3)
        self.assertEqual(collected[0].data["v"], "first")
        self.assertEqual(collected[2].data["v"], "third")

    def test_iter_labels_match_expected(self) -> None:
        """Row labels from iteration match what was inserted."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("10", {"x": "a"})
        t.add_row("1",  {"x": "b"})
        t.add_row("2",  {"x": "c"})
        labels = [row.label for row in t]
        self.assertEqual(labels, ["10", "1", "2"])

    def test_iter_empty_table_is_empty(self) -> None:
        """Iterating an empty TwoDAFile yields nothing."""
        t = self.TwoDAFile()
        self.assertEqual(list(t), [])

    def test_iter_compatible_with_list_comprehension(self) -> None:
        """List comprehension over TwoDAFile works as expected."""
        t = self.TwoDAFile()
        t.columns = ["score"]
        for i in range(4):
            t.add_row(str(i), {"score": str(i * 3)})
        scores = [int(row.data["score"]) for row in t]
        self.assertEqual(scores, [0, 3, 6, 9])

    # ── detect_2da ───────────────────────────────────────────

    def test_detect_binary_format(self) -> None:
        """detect_2da returns 'binary' for binary 2DA data."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "1"})
        raw = t.to_binary()
        self.assertEqual(self.detect_2da(raw), "binary")

    def test_detect_text_format(self) -> None:
        """detect_2da returns 'text' for text 2DA data."""
        t = self.TwoDAFile()
        t.columns = ["x"]
        t.add_row("0", {"x": "1"})
        raw = t.to_text().encode("utf-8")
        self.assertEqual(self.detect_2da(raw), "text")

    def test_detect_corrupt_data_returns_unknown(self) -> None:
        """detect_2da returns 'unknown' for clearly-corrupt data (mirrors PyKotor CORRUPT_BINARY)."""
        self.assertEqual(self.detect_2da(b"BAD"), "unknown")

    def test_detect_empty_bytes_returns_unknown(self) -> None:
        """detect_2da on empty bytes returns 'unknown' (not a crash)."""
        self.assertEqual(self.detect_2da(b""), "unknown")

    def test_detect_wrong_format_returns_unknown(self) -> None:
        """detect_2da on GFF/TLK/ERF bytes returns 'unknown'."""
        self.assertEqual(self.detect_2da(b"GFF V3.2"), "unknown")
        self.assertEqual(self.detect_2da(b"TLK V3.0"), "unknown")
        self.assertEqual(self.detect_2da(b"ERF V1.0"), "unknown")


if __name__ == "__main__":
    unittest.main()
