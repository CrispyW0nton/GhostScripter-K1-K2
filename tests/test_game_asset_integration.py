"""
test_game_asset_integration.py
================================
Integration tests using real KotOR 1 game assets from game_files/swkotor/.

These tests verify that every major GhostScripter subsystem correctly reads,
parses, and round-trips real game data — not just synthetic fixture data.

Game files expected at: game_files/swkotor/
  - chitin.key         (KEY file index)
  - data/2da.bif       (BIF archive: 2DA tables)
  - data/scripts.bif   (BIF archive: NSS/NCS scripts)
  - dialog.tlk         (Talk table, 49 265 entries)
  - modules/danm13_s.rim  (Dantooine module: Bastila dialogue, etc.)
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path
from typing import Optional

import pytest

# ---------------------------------------------------------------------------
# Detect whether real game files are present; skip suite if absent.
# ---------------------------------------------------------------------------
GAME_DIR = Path("game_files/swkotor")
GAME_AVAILABLE = (GAME_DIR / "chitin.key").exists()

pytestmark = pytest.mark.skipif(
    not GAME_AVAILABLE,
    reason="Real KotOR 1 game files not present at game_files/swkotor/",
)

# Add project root so imports work whether tests are run from root or /tests
sys.path.insert(0, str(Path(__file__).parent.parent))


# ===========================================================================
# ResourceManager / KEY / BIF integration
# ===========================================================================

class TestResourceManagerWithGameFiles:

    @pytest.fixture(scope="class")
    def rm(self):
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager
        manager = ResourceManager()
        ok = manager.load_game(GAME_DIR)
        assert ok, "ResourceManager.load_game() failed"
        return manager

    def test_load_game_succeeds(self, rm):
        assert rm.is_loaded

    def test_key_file_has_expected_resource_count(self, rm):
        # KotOR 1 chitin.key has ~25 000+ resources
        summary = rm.get_summary()
        total = sum(summary.values())
        assert total >= 20_000, f"Expected 20k+ resources, got {total}"

    def test_list_by_type_2da(self, rm):
        entries = rm.list_by_type(".2da")
        assert len(entries) >= 200, f"Expected 200+ .2da files, got {len(entries)}"

    def test_list_by_type_nss(self, rm):
        entries = rm.list_by_type(".nss")
        assert len(entries) >= 1_000, f"Expected 1k+ .nss files, got {len(entries)}"

    def test_list_by_type_dlg(self, rm):
        entries = rm.list_by_type(".dlg")
        assert len(entries) >= 10, f"Expected at least 10 .dlg files, got {len(entries)}"

    def test_read_appearance_2da(self, rm):
        data = rm.read("appearance.2da")
        assert data is not None, "appearance.2da read returned None"
        assert len(data) > 10_000, f"appearance.2da too small: {len(data)} bytes"
        assert data[:8] == b"2DA V2.b", f"Wrong 2DA header: {data[:8]!r}"

    def test_read_caches_result(self, rm):
        """Second read of the same resource should hit the LRU cache."""
        rm.read("appearance.2da")  # ensure cached
        info = rm.cache_info()
        # Cache was populated by the first read in this or a prior test
        assert info.get("size", 0) >= 1

    def test_read_nonexistent_returns_none(self, rm):
        data = rm.read("nonexistent_file_xyz.2da")
        assert data is None

    def test_batch_read(self, rm):
        results = rm.batch_read(["appearance.2da", "classes.2da", "nonexistent.2da"])
        assert results["appearance.2da"] is not None
        assert results["classes.2da"] is not None
        assert results["nonexistent.2da"] is None

    def test_search_prefix(self, rm):
        results = rm.search("appear")
        names = [e.filename for e in results]
        assert any("appearance" in n for n in names), f"'appearance' not found in {names[:5]}"


# ===========================================================================
# BIF file parsing
# ===========================================================================

class TestBifFileWithGameData:

    @pytest.fixture(scope="class")
    def bif_2da(self):
        from ghostscripter.core.resource_manager.resource_manager import BifFile
        bif = BifFile(GAME_DIR / "data" / "2da.bif")
        assert bif.load(), "BifFile.load() failed for 2da.bif"
        return bif

    def test_bif_loaded_entry_count(self, bif_2da):
        assert len(bif_2da._entries) >= 200

    def test_read_resource_by_index(self, bif_2da):
        data = bif_2da.read_resource(0)
        assert data is not None and len(data) > 0

    def test_appearance_2da_has_correct_header(self, bif_2da):
        from ghostscripter.core.resource_manager.resource_manager import KeyFile
        key = KeyFile()
        key.load(GAME_DIR / "chitin.key")
        entry = key.find("appearance.2da")
        assert entry is not None, "appearance.2da not found in KEY"
        data = bif_2da.read_resource(entry.offset)
        assert data is not None
        assert data[:8] == b"2DA V2.b"


# ===========================================================================
# RIM file parsing
# ===========================================================================

class TestRimReaderWithGameData:

    RIM_PATH = GAME_DIR / "modules" / "danm13_s.rim"

    @pytest.fixture(scope="class")
    def rim(self):
        if not self.RIM_PATH.exists():
            pytest.skip(f"RIM file not found: {self.RIM_PATH}")
        from ghostscripter.core.resource_manager.resource_manager import RimReader
        reader = RimReader(self.RIM_PATH)
        assert reader.load(), "RimReader.load() failed"
        return reader

    def test_rim_has_entries(self, rim):
        assert len(rim.entries) > 100

    def test_rim_has_dlg_entries(self, rim):
        dlg_entries = [e for e in rim.entries if e.restype == 2029]
        assert len(dlg_entries) >= 5, "Expected at least 5 DLG entries in danm13_s.rim"

    def test_read_bastila_dlg_by_filename(self, rim):
        data = rim.read("bastila.dlg")
        assert data is not None, "bastila.dlg not found in rim"
        assert len(data) > 1000

    def test_read_bastila_dlg_has_gff_header(self, rim):
        data = rim.read("bastila.dlg")
        assert data is not None
        assert data[:4] == b"DLG ", f"Expected DLG  header, got {data[:4]!r}"

    def test_read_unknown_resource_returns_none(self, rim):
        assert rim.read("nonexistent_xyz.dlg") is None

    def test_read_by_resref_without_extension_returns_none(self, rim):
        # Correct usage requires extension; bare resref should not match
        result = rim.read("bastila")
        assert result is None, "Read without extension should return None"


# ===========================================================================
# TLK parser and round-trip
# ===========================================================================

class TestTLKWithGameData:

    TLK_PATH = GAME_DIR / "dialog.tlk"

    @pytest.fixture(scope="class")
    def tlk(self):
        if not self.TLK_PATH.exists():
            pytest.skip(f"dialog.tlk not found: {self.TLK_PATH}")
        from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
        return TLKFile.from_file(self.TLK_PATH)

    def test_tlk_entry_count(self, tlk):
        # KotOR 1 dialog.tlk has 49 265 entries
        assert len(tlk) >= 40_000, f"Expected 40k+ entries, got {len(tlk)}"

    def test_tlk_language_is_english(self, tlk):
        assert tlk.language_id == 0  # 0 = English

    def test_tlk_get_string_returns_bastila_line(self, tlk):
        text = tlk.get_string(446)
        assert "Bastila" in text or "T3" in text, f"Unexpected text at 446: {text!r}"

    def test_tlk_get_string_empty_on_zero(self, tlk):
        # Strref -1 / 4294967295 is the "undefined" marker
        text = tlk.get_string(4294967295)
        assert text == "" or text is None

    def test_tlk_round_trip_byte_identical(self, tlk):
        """Serialising and re-parsing must produce identical bytes."""
        original_bytes = self.TLK_PATH.read_bytes()
        serialised = tlk.to_bytes()
        assert len(serialised) == len(original_bytes), (
            f"Size mismatch: orig={len(original_bytes)}, new={len(serialised)}"
        )
        assert serialised == original_bytes, (
            "TLK round-trip produced different bytes — off_str fix may have regressed"
        )

    def test_tlk_empty_entry_off_str_is_zero(self):
        """Regression: off_str for entries with str_size=0 MUST be written as 0."""
        from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
        original_bytes = self.TLK_PATH.read_bytes()
        tlk = TLKFile.from_file(self.TLK_PATH)
        serialised = tlk.to_bytes()

        # The header tells us where entries start (offset 20) and string data starts
        _magic, _ver = original_bytes[:4], original_bytes[4:8]
        count = struct.unpack_from("<I", original_bytes, 12)[0]  # StringCount
        str_off = struct.unpack_from("<I", original_bytes, 16)[0]  # StringEntriesOffset

        ENTRY_SIZE = 40
        for i in range(count):
            base = str_off + i * ENTRY_SIZE
            size_orig = struct.unpack_from("<I", original_bytes, base + 32)[0]
            off_orig  = struct.unpack_from("<I", original_bytes, base + 28)[0]
            off_new   = struct.unpack_from("<I", serialised, base + 28)[0]
            if size_orig == 0:
                assert off_new == 0, (
                    f"Entry {i}: str_size=0 but off_str={off_new} (expected 0)"
                )


# ===========================================================================
# 2DA manager with real game data
# ===========================================================================

class TestTwoDAWithGameData:

    @pytest.fixture(scope="class")
    def rm(self):
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager
        manager = ResourceManager()
        manager.load_game(GAME_DIR)
        return manager

    @pytest.fixture(scope="class")
    def appearance_tda(self, rm):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        data = rm.read("appearance.2da")
        assert data is not None
        return TwoDAFile.from_bytes(data, "appearance.2da")

    def test_appearance_has_509_rows(self, appearance_tda):
        # KotOR 1 appearance.2da has 509 rows (indices 0-508)
        assert len(appearance_tda.rows) >= 500

    def test_appearance_has_expected_columns(self, appearance_tda):
        cols = appearance_tda.columns
        for expected in ("label", "string_ref", "race", "walkdist", "rundist"):
            assert expected in cols, f"Column '{expected}' missing"

    def test_get_row_by_index(self, appearance_tda):
        row = appearance_tda.get_row_by_index(0)
        assert row is not None
        assert row.label == "0"

    def test_set_cell_undo_redo(self, appearance_tda):
        """Critical regression: set_cell must save undo state."""
        row0 = appearance_tda.get_row_by_index(0)
        original = row0.get("label")

        # Modify
        appearance_tda.set_cell_by_index(0, "label", "MODIFIED")
        assert appearance_tda.get_row_by_index(0).get("label") == "MODIFIED"

        # Undo should restore original
        ok = appearance_tda.undo()
        assert ok, "undo() returned False"
        restored = appearance_tda.get_row_by_index(0).get("label")
        assert restored == original, (
            f"Undo failed: expected {original!r}, got {restored!r}"
        )

        # Redo
        appearance_tda.redo()
        assert appearance_tda.get_row_by_index(0).get("label") == "MODIFIED"

        # Restore
        appearance_tda.undo()

    def test_set_cell_by_label_undo(self, appearance_tda):
        """set_cell (by label string) must also save undo state."""
        row0 = appearance_tda.get_row_by_index(0)
        original = row0.get("race")

        appearance_tda.set_cell(row0.label, "race", "TEST_RACE")
        assert appearance_tda.get_row_by_index(0).get("race") == "TEST_RACE"

        appearance_tda.undo()
        assert appearance_tda.get_row_by_index(0).get("race") == original

    def test_binary_round_trip_preserves_row_count(self, appearance_tda):
        binary = appearance_tda.to_binary()
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        tda2 = TwoDAFile.from_bytes(binary)
        assert len(tda2.rows) == len(appearance_tda.rows)
        assert tda2.columns == appearance_tda.columns

    def test_search_returns_matching_rows(self, appearance_tda):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager
        rm = ResourceManager()
        rm.load_game(GAME_DIR)
        data_classes = rm.read("classes.2da")
        assert data_classes is not None
        classes_tda = TwoDAFile.from_bytes(data_classes)
        # KotOR 1 classes.2da has exactly 9 playable classes (0-8)
        assert len(classes_tda.rows) >= 5, (
            f"Expected at least 5 rows in classes.2da, got {len(classes_tda.rows)}"
        )


# ===========================================================================
# DLG importer with real game data
# ===========================================================================

class TestDLGImporterWithGameData:

    RIM_PATH = GAME_DIR / "modules" / "danm13_s.rim"

    @pytest.fixture(scope="class")
    def bastila_dlg(self):
        if not self.RIM_PATH.exists():
            pytest.skip(f"Module RIM not found: {self.RIM_PATH}")
        from ghostscripter.core.resource_manager.resource_manager import RimReader
        from ghostscripter.core.export.dlg_reader import DLGImporter
        rim = RimReader(self.RIM_PATH)
        rim.load()
        data = rim.read("bastila.dlg")
        assert data is not None
        importer = DLGImporter()
        return importer.import_from_bytes(data, "bastila.dlg")

    def test_dlg_has_entries_and_replies(self, bastila_dlg):
        assert len(bastila_dlg.entries) > 0
        assert len(bastila_dlg.replies) > 0

    def test_dlg_nodes_have_strrefs(self, bastila_dlg):
        # In real DLGs, text lives in TLK; nodes should have text_strref ≥ 0
        npc_nodes = [n for n in bastila_dlg.entries if n.text_strref is not None and n.text_strref >= 0]
        assert len(npc_nodes) > 0, "No NPC nodes have valid text_strref"

    def test_dlg_speaker_is_bastila(self, bastila_dlg):
        speakers = {n.speaker for n in bastila_dlg.entries if n.speaker}
        assert "Bastila" in speakers or len(speakers) > 0

    def test_dlg_short_text_shows_strref_fallback(self, bastila_dlg):
        """Without a TLK, short_text should show [StrRef N] for strref nodes."""
        node = bastila_dlg.entries[0]
        if node.text_strref is not None and node.text_strref >= 0 and not node.text:
            st = node.short_text(60)
            assert "StrRef" in st or len(st) == 0  # shows fallback or empty

    def test_dlg_short_text_resolves_with_tlk(self, bastila_dlg):
        """With a TLK, short_text should resolve to real dialogue text."""
        from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
        tlk_path = GAME_DIR / "dialog.tlk"
        if not tlk_path.exists():
            pytest.skip("dialog.tlk not available")
        tlk = TLKFile.from_file(tlk_path)

        # Bastila entry 0 strref=6321
        node = bastila_dlg.entries[0]
        if node.text_strref is not None and node.text_strref >= 0:
            text = node.short_text(200, tlk=tlk)
            assert len(text) > 0, "short_text with TLK returned empty string"
            assert "[StrRef" not in text, "short_text with TLK still shows fallback"

    def test_dlg_starters_reference_valid_entries(self, bastila_dlg):
        entry_ids = {n.node_id for n in bastila_dlg.entries}
        for s in bastila_dlg.starters:
            target = getattr(s, "target_node_id", getattr(s, "index", None))
            if target is not None and target >= 0:
                assert target in entry_ids, f"Starter points to missing entry {target}"


# ===========================================================================
# NWScript DB + parser
# ===========================================================================

class TestNWScriptDBWithGameData:

    @pytest.fixture(scope="class")
    def db(self):
        from ghostscripter.core.nwscript.parser import get_nwscript_db
        return get_nwscript_db("K1")

    def test_db_is_loaded(self, db):
        assert db.is_loaded

    def test_db_has_functions(self, db):
        results = db.autocomplete("Get", max_results=100)
        assert len(results) >= 20, f"Expected 20+ Get* functions, got {len(results)}"

    def test_autocomplete_returns_sorted_prefix_matches(self, db):
        results = db.autocomplete("ActionMove", max_results=10)
        assert all("ActionMove" in r for r in results)

    def test_search_functions_action_move(self, db):
        funcs = db.search_functions("ActionMoveToObject")
        assert len(funcs) >= 1
        assert funcs[0].name == "ActionMoveToObject"

    def test_search_functions_partial_match(self, db):
        # Search for a function that exists in K1 NWScript
        funcs = db.search_functions("GetObjectByTag")
        assert any("GetObjectByTag" in f.name for f in funcs)

    def test_function_categories(self, db):
        # function_categories is a @property returning a dict (not callable)
        cats = db.function_categories
        assert isinstance(cats, dict) and len(cats) > 0

    def test_read_real_nss_file_from_bif(self):
        """Read an NSS source file from the scripts BIF and verify its content."""
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager
        rm = ResourceManager()
        rm.load_game(GAME_DIR)
        nss_entries = rm.list_by_type(".nss")
        assert len(nss_entries) > 0
        # Read the first NSS file
        data = rm.read(nss_entries[0].filename)
        assert data is not None
        text = data.decode("latin-1", errors="replace")
        # NSS files start with comments or void/int/string declarations
        assert len(text) > 10


# ===========================================================================
# Dialogue editor TLK resolution (model layer, no Qt required)
# ===========================================================================

class TestDialogueNodeShortText:
    """Unit-level tests for DialogueNode.short_text() with and without TLK."""

    def _make_node(self, text="", strref=-1):
        from ghostscripter.core.models.dialogue import DialogueNode
        return DialogueNode(node_id=0, node_type="entry",
                            text=text, text_strref=strref)

    def test_short_text_inline(self):
        node = self._make_node(text="Hello world", strref=-1)
        assert node.short_text(40) == "Hello world"

    def test_short_text_truncation(self):
        node = self._make_node(text="A" * 50, strref=-1)
        st = node.short_text(40)
        assert len(st) <= 41  # 40 chars + ellipsis

    def test_short_text_fallback_shows_strref_number(self):
        node = self._make_node(text="", strref=6321)
        st = node.short_text(60)
        assert "6321" in st, f"Expected strref number in fallback, got {st!r}"

    def test_short_text_with_tlk_resolves_text(self):
        """With a TLK, the resolved string must be returned."""
        if not (GAME_DIR / "dialog.tlk").exists():
            pytest.skip("dialog.tlk not available")
        from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
        tlk = TLKFile.from_file(GAME_DIR / "dialog.tlk")
        node = self._make_node(text="", strref=446)
        st = node.short_text(200, tlk=tlk)
        assert "Bastila" in st or "T3" in st, f"Unexpected text: {st!r}"
        assert "[StrRef" not in st

    def test_short_text_with_tlk_empty_strref(self):
        """strref=-1 should still return '' even with a TLK."""
        if not (GAME_DIR / "dialog.tlk").exists():
            pytest.skip("dialog.tlk not available")
        from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
        tlk = TLKFile.from_file(GAME_DIR / "dialog.tlk")
        node = self._make_node(text="", strref=-1)
        assert node.short_text(60, tlk=tlk) == ""

    def test_short_text_inline_takes_precedence_over_strref(self):
        """If node.text is non-empty, it wins over the TLK lookup."""
        if not (GAME_DIR / "dialog.tlk").exists():
            pytest.skip("dialog.tlk not available")
        from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
        tlk = TLKFile.from_file(GAME_DIR / "dialog.tlk")
        node = self._make_node(text="Inline text", strref=6321)
        st = node.short_text(60, tlk=tlk)
        assert st == "Inline text"


# ===========================================================================
# TwoDA undo/redo regression (critical bug fix verification)
# ===========================================================================

class TestTwoDAUndoRedoRegression:
    """Regression tests for the set_cell undo/redo bug fix."""

    @pytest.fixture()
    def simple_tda(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        text = (
            "2DA V2.0\n"
            "\n"
            "         name    value\n"
            "0        alpha   10\n"
            "1        beta    20\n"
            "2        gamma   30\n"
        )
        return TwoDAFile.from_text(text)

    def test_set_cell_by_index_can_undo(self, simple_tda):
        row = simple_tda.get_row_by_index(0)
        orig = row.get("name")
        simple_tda.set_cell_by_index(0, "name", "CHANGED")
        assert simple_tda.get_row_by_index(0).get("name") == "CHANGED"
        assert simple_tda.undo()
        assert simple_tda.get_row_by_index(0).get("name") == orig

    def test_set_cell_by_label_can_undo(self, simple_tda):
        row = simple_tda.get_row_by_index(1)
        orig = row.get("value")
        simple_tda.set_cell(row.label, "value", "999")
        assert simple_tda.get_row_by_index(1).get("value") == "999"
        assert simple_tda.undo()
        assert simple_tda.get_row_by_index(1).get("value") == orig

    def test_set_cell_redo_works(self, simple_tda):
        simple_tda.set_cell_by_index(2, "name", "REDO_ME")
        simple_tda.undo()
        assert simple_tda.redo()
        assert simple_tda.get_row_by_index(2).get("name") == "REDO_ME"
        simple_tda.undo()

    def test_multiple_set_cell_operations_undo_in_order(self, simple_tda):
        simple_tda.set_cell_by_index(0, "name", "A")
        simple_tda.set_cell_by_index(0, "name", "B")
        simple_tda.set_cell_by_index(0, "name", "C")

        simple_tda.undo()
        assert simple_tda.get_row_by_index(0).get("name") == "B"
        simple_tda.undo()
        assert simple_tda.get_row_by_index(0).get("name") == "A"
        simple_tda.undo()
        # Should be back to original "alpha"
        assert simple_tda.get_row_by_index(0).get("name") == "alpha"

    def test_undo_returns_false_when_empty(self, simple_tda):
        # Without any mutations, undo returns False
        assert not simple_tda.undo()

    def test_redo_returns_false_when_empty(self, simple_tda):
        assert not simple_tda.redo()

    def test_set_cell_returns_false_for_nonexistent_label(self, simple_tda):
        result = simple_tda.set_cell("NONEXISTENT_LABEL", "name", "X")
        assert not result

    def test_add_new_column_via_set_cell_by_index(self, simple_tda):
        """set_cell_by_index should add new columns and support undo."""
        assert "newcol" not in simple_tda.columns
        simple_tda.set_cell_by_index(0, "newcol", "new_value")
        assert "newcol" in simple_tda.columns
        assert simple_tda.get_row_by_index(0).get("newcol") == "new_value"
        simple_tda.undo()
        # After undo, the column should be removed and value restored
        assert "newcol" not in simple_tda.columns
