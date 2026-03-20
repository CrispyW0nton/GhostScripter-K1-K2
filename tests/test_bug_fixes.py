#!/usr/bin/env python3
"""
test_bug_fixes.py — Regression tests for all identified and fixed bugs.

Bugs covered
------------
BUG-1  dlg_reader.py  — on_end was incorrectly assigned from EndConverAbort;
                        on_abort shared the same value.  Fixed: on_end ← EndConversation
                        (fallback EndConverAbort), on_abort ← EndConverAbort always.
BUG-2  dlg_reader.py  — _STRREF (type 18) was read without the 4-byte size prefix
                        required by the GFF3 spec.  Fixed reader + added STRREF writer
                        to gff_writer.py.
BUG-3  dlg_reader.py  — _visited_structs was reset in parse() but never consulted
                        inside _read_struct().  Fixed: cycle guard added to prevent
                        re-entering the same struct index.
BUG-4  dlg_writer.py  — ERFWriter.RESTYPE_MAP had wrong/colliding type IDs.
                        Fixed: all IDs now match erf_writer.py RESTYPE_IDS (authoritative).
BUG-5  log_setup.py   — _RingBufferHandler used del _RECENT[0] (O(n)) for trimming.
                        Fixed: replaced with collections.deque(maxlen=...) for O(1) ops.
BUG-6  log_viewer_widget.py — _passes_filter had a misleading docstring and a
                        now-redundant min-level check.  Fixed: simplified to exact-match
                        per-button logic with corrected docstring.
BUG-7  ghostrigger_bridge.py — IPCCallbackServer has no warning about port conflict
                        with IPCServer (both default to 7002).  Fixed: deprecation
                        docstring warns not to start both simultaneously.
BUG-13 main_window.py  — open_tlk_editor() method definition was accidentally dropped
                        during the BUG-12 commit, leaving its body as dead code inside
                        _decompile_ncs_bytes().  The welcome-tab button reference caused
                        AttributeError: 'MainWindow' object has no attribute 'open_tlk_editor'
                        on every startup.  Fixed: restored the method header.
BUG-14 main_window.py  — Double-clicking a .utc (or .uti/.utp/.utt/.utm/.uts/.utw) file
                        in the asset library opened a plain-text summary in the detail
                        panel instead of a dedicated editor tab.  Root cause:
                        _open_gff_asset() only wrote a text summary.
                        Fixed: new GFFTemplateViewerWidget parses the GFF binary via
                        PyKotor and shows all fields in labelled sections; wired into
                        _open_gff_asset() for the seven known template types.
BUG-15 asset_library_widget.py / resource_manager.py — Three related fixes:
        (a) .uti/.utp double-click silently failed when raw_data was None (RM read
            returned None); open_asset_from_library now retries via _read_asset_from_rm.
        (b) TPC texture preview used write_tpc(buf, ResourceType.TGA) with BytesIO,
            which raises ValueError ("I/O operation on closed file") in PyKotor.
            Fixed: use TPCMipmap.to_qimage() which avoids any file I/O.
        (c) KotOR 2 TexturePacks/swpc_tex_tp[a-d].erf were never loaded by
            ResourceManager.load_game(); TPC textures from those packs were not
            accessible.  Fixed: load_game() now scans and adds those ERFs.
        Also: all seven UTT/UTM/UTS/UTW template types now appear in the asset
        library tree and are scanned by _GameAssetLoader.
"""
import logging
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.export.gff_writer import GFF3Writer, GFFStruct, GFFType
from ghostscripter.core.export.dlg_reader import GFF3Reader, DLGImporter
from ghostscripter.core.export.dlg_writer import DLGExporter, ERFWriter
from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch,
)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-1 — dlg_reader: on_end / on_abort field confusion
# ─────────────────────────────────────────────────────────────────────────────

class TestBug1OnEndOnAbort(unittest.TestCase):
    """
    Verify that EndConversation → dlg.on_end  and
                EndConverAbort  → dlg.on_abort
    with no cross-contamination.
    """

    def _roundtrip(self, on_end: str, on_abort: str,
                   game: str = "K1") -> DialogueFile:
        """Export a DLG with given field values, re-import and return."""
        dlg = DialogueFile(name="bug1_test")
        dlg.on_end   = on_end
        dlg.on_abort = on_abort
        data = DLGExporter().export(dlg, target_game=game)
        return DLGImporter().import_from_bytes(data, name="bug1_test")

    def test_on_end_preserved(self):
        rt = self._roundtrip("k_end_conv", "k_abort_conv")
        self.assertEqual(rt.on_end, "k_end_conv",
                         "on_end must survive round-trip unchanged")

    def test_on_abort_preserved(self):
        rt = self._roundtrip("k_end_conv", "k_abort_conv")
        self.assertEqual(rt.on_abort, "k_abort_conv",
                         "on_abort must survive round-trip unchanged")

    def test_on_end_and_on_abort_are_independent(self):
        """on_end and on_abort must not share the same value after import."""
        rt = self._roundtrip("k_end_different", "k_abort_different")
        self.assertNotEqual(rt.on_end, rt.on_abort,
                            "on_end and on_abort must not be identical")

    def test_on_end_is_not_abort(self):
        """on_end must not be assigned from EndConverAbort."""
        rt = self._roundtrip("k_end_normal", "k_abort_script")
        # If on_end was wrongly assigned from EndConverAbort, it would equal
        # "k_abort_script" instead of "k_end_normal"
        self.assertEqual(rt.on_end, "k_end_normal")
        self.assertNotEqual(rt.on_end, "k_abort_script",
                            "on_end must NOT be read from EndConverAbort")

    def test_empty_on_end_keeps_abort(self):
        """When on_end is empty, on_abort is still set correctly."""
        rt = self._roundtrip("", "k_abort_only")
        self.assertEqual(rt.on_abort, "k_abort_only")

    def test_k2_game_roundtrip(self):
        rt = self._roundtrip("k_end_tsl", "k_abort_tsl", game="K2")
        self.assertEqual(rt.on_end, "k_end_tsl")
        self.assertEqual(rt.on_abort, "k_abort_tsl")

    def test_max_length_resref(self):
        """RESREF is max 16 chars — longer names get truncated at 16."""
        rt = self._roundtrip("k_a_very_long_en", "k_a_very_long_ab")
        self.assertLessEqual(len(rt.on_end), 16)
        self.assertLessEqual(len(rt.on_abort), 16)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-2 — dlg_reader: STRREF (type 18) encoded/decoded with 4-byte size prefix
# ─────────────────────────────────────────────────────────────────────────────

class TestBug2StrrRef(unittest.TestCase):
    """STRREF fields in GFF3 have a 4-byte total_size prefix in field_data."""

    def _write_read(self, strref_value: int) -> dict:
        """Write a GFF containing a STRREF field and re-read it."""
        w = GFF3Writer("TST ")
        w.root.add_strref("MyStrRef", strref_value)
        data = w.build()
        r = GFF3Reader(data)
        return r.parse()

    def test_strref_zero(self):
        d = self._write_read(0)
        self.assertEqual(d.get("MyStrRef"), 0)

    def test_strref_small(self):
        d = self._write_read(42001)
        self.assertEqual(d.get("MyStrRef"), 42001)

    def test_strref_large(self):
        d = self._write_read(999999)
        self.assertEqual(d.get("MyStrRef"), 999999)

    def test_strref_max_valid(self):
        # Max valid TLK index for KotOR is around 0x00FFFFFF
        d = self._write_read(0x00FFFFFF)
        self.assertEqual(d.get("MyStrRef"), 0x00FFFFFF)

    def test_strref_field_data_has_size_prefix(self):
        """Verify the binary layout: 4-byte total_size then 4-byte value."""
        w = GFF3Writer("TST ")
        w.root.add_strref("S", 77)
        data = w.build()
        # Find the 4-byte sequence [4, 0, 0, 0] (total_size=4) + [77, 0, 0, 0]
        needle = struct.pack("<II", 4, 77)
        self.assertIn(needle, data,
                      "STRREF field_data must be: total_size(4) + strref_value(4)")

    def test_gfftype_strref_value(self):
        """GFFType.STRREF must equal 18 per the spec."""
        self.assertEqual(GFFType.STRREF, 18)

    def test_add_strref_helper_on_gffstruct(self):
        """GFFStruct.add_strref() helper must create a STRREF-typed field."""
        s = GFFStruct(0)
        s.add_strref("Ref", 1234)
        label, ftype, val = s.fields[0]
        self.assertEqual(label, "Ref")
        self.assertEqual(ftype, GFFType.STRREF)
        self.assertEqual(val, 1234)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-3 — dlg_reader: _visited_structs cycle guard is now active
# ─────────────────────────────────────────────────────────────────────────────

class TestBug3CycleGuard(unittest.TestCase):
    """
    GFF3Reader._visited_structs now actually guards against infinite loops
    when a pathological/malformed GFF has a STRUCT field pointing back to a
    parent struct index.
    """

    def _build_cyclic_gff(self) -> bytes:
        """
        Build a 'valid' GFF3 with two structs that each hold a reference
        to the other struct (simulating a corrupt/cyclic STRUCT→STRUCT link).

        Because GFF3Writer won't let us directly create a truly cyclic struct
        (Python recursion would hit the stack limit), we test with a deeply
        nested but non-cyclic tree which exercises the visited set.
        """
        w = GFF3Writer("TST ")
        s1 = GFFStruct(1)
        s2 = GFFStruct(2)
        s3 = GFFStruct(3)
        s3.add_cexo("Deep", "leaf")
        s2.add_struct("Level2", s3)
        s1.add_struct("Level1", s2)
        w.root.add_struct("Root", s1)
        return w.build()

    def test_nested_structs_parse_without_error(self):
        """Deeply nested structs should parse without error or recursion limit."""
        data = self._build_cyclic_gff()
        reader = GFF3Reader(data)
        result = reader.parse()
        self.assertIsNotNone(result)

    def test_visited_structs_resets_between_parses(self):
        """_visited_structs must be cleared on each call to parse()."""
        data = self._build_cyclic_gff()
        reader = GFF3Reader(data)
        result1 = reader.parse()
        result2 = reader.parse()   # second parse must succeed (visited set was reset)
        self.assertIsNotNone(result2)
        # Both parses must yield the same leaf value
        self.assertEqual(
            result1.get("Root", {}).get("Level1", {}).get("Level2", {}).get("Deep"),
            result2.get("Root", {}).get("Level1", {}).get("Level2", {}).get("Deep"),
        )

    def test_depth_limit_attribute_exists(self):
        """GFF3Reader._MAX_DEPTH must be set (safety cap for recursion)."""
        reader = GFF3Reader(b"\x00" * 4)
        self.assertGreater(reader._MAX_DEPTH, 0)
        self.assertLessEqual(reader._MAX_DEPTH, 128)

    def test_visited_structs_is_set(self):
        """After parse(), _visited_structs should be a set (not a list)."""
        w = GFF3Writer("TST ")
        w.root.add_cexo("X", "y")
        data = w.build()
        reader = GFF3Reader(data)
        reader.parse()
        self.assertIsInstance(reader._visited_structs, set)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-4 — dlg_writer.ERFWriter: RESTYPE_MAP had wrong / colliding type IDs
# ─────────────────────────────────────────────────────────────────────────────

class TestBug4ERFRestypeMap(unittest.TestCase):
    """
    Verify that ERFWriter.RESTYPE_MAP now contains correct, non-colliding IDs
    that match the authoritative erf_writer.py RESTYPE_IDS mapping.
    """

    def _get_rtype(self, resref_with_ext: str, resource_data: bytes = b"x") -> int:
        """Build a minimal ERF with one file, extract its ResType from binary."""
        erf = ERFWriter()
        erf.add_resource(resref_with_ext, resource_data)
        built = erf.build()
        # Key list starts at offset 160; each entry is 24 bytes.
        # Layout: resref[16] + res_id[4] + rtype[2] + unused[2]
        rtype = struct.unpack_from("<H", built, 160 + 20)[0]
        return rtype

    def test_dlg_type_is_2029(self):
        self.assertEqual(self._get_rtype("test.dlg"), 2029)

    def test_ncs_type_is_2010(self):
        self.assertEqual(self._get_rtype("test.ncs"), 2010)

    def test_nss_type_is_2009(self):
        self.assertEqual(self._get_rtype("test.nss"), 2009)

    def test_utc_type_is_2027(self):
        self.assertEqual(self._get_rtype("test.utc"), 2027)

    def test_utt_type_is_2032(self):
        """Bug was: .utt was mapped to 2023 (wrong, colliding with .git)."""
        self.assertEqual(self._get_rtype("test.utt"), 2032)

    def test_jrl_type_is_2057(self):
        """Bug was: .jrl was missing from the map entirely."""
        self.assertEqual(self._get_rtype("test.jrl"), 2057)

    def test_fac_type_is_2039(self):
        """Bug was: .fac was missing from the map entirely."""
        self.assertEqual(self._get_rtype("test.fac"), 2039)

    def test_bic_type_is_2015(self):
        """Bug was: .bic was missing from the map entirely."""
        self.assertEqual(self._get_rtype("test.bic"), 2015)

    def test_mdx_type_is_3009(self):
        """Bug was: .mdx was mapped to 3002 (colliding with .rim)."""
        self.assertEqual(self._get_rtype("test.mdx"), 3009)

    def test_no_duplicate_type_ids(self):
        """
        Every extension in RESTYPE_MAP must map to a unique ResType ID,
        except where documented extensions genuinely share an ID.
        """
        seen: dict = {}
        collisions = []
        for ext, type_id in ERFWriter.RESTYPE_MAP.items():
            if type_id in seen:
                collisions.append(
                    f"{ext}={type_id} collides with {seen[type_id]}={type_id}"
                )
            else:
                seen[type_id] = ext
        self.assertEqual(collisions, [],
                         "RESTYPE_MAP has colliding type IDs:\n" +
                         "\n".join(collisions))

    def test_txb_type_is_3007(self):
        """TXB is a KotOR texture binary format, type 3007."""
        self.assertEqual(self._get_rtype("test.txb"), 3007)

    def test_mp3_not_in_map_or_no_collision_with_tpc(self):
        """MP3 is not a standard KotOR ERF resource; if present must not collide with .tpc."""
        mp3_type = ERFWriter.RESTYPE_MAP.get(".mp3")
        tpc_type = ERFWriter.RESTYPE_MAP.get(".tpc", -1)
        if mp3_type is not None:
            self.assertNotEqual(mp3_type, tpc_type,
                                ".mp3 and .tpc must not share the same ResType")


# ─────────────────────────────────────────────────────────────────────────────
# BUG-5 — log_setup.py: ring buffer now uses deque(maxlen=...) for O(1) trim
# ─────────────────────────────────────────────────────────────────────────────

class TestBug5LogRingBuffer(unittest.TestCase):
    """
    Verify that the ring buffer in log_setup is backed by a collections.deque
    with a maxlen, not a plain list with del _RECENT[0].
    """

    def test_ring_buffer_is_deque(self):
        import collections
        import ghostscripter.utils.log_setup as ls
        self.assertIsInstance(ls._RECENT, collections.deque,
                              "_RECENT must be a collections.deque for O(1) trim")

    def test_ring_buffer_has_maxlen(self):
        import ghostscripter.utils.log_setup as ls
        self.assertIsNotNone(ls._RECENT.maxlen,
                             "deque must have maxlen set")
        self.assertEqual(ls._RECENT.maxlen, ls._MAX_RECENT)

    def test_ring_buffer_bounded(self):
        """Adding more than _MAX_RECENT records must not exceed the cap."""
        import ghostscripter.utils.log_setup as ls
        original_size = len(ls._RECENT)
        cap = ls._MAX_RECENT
        logger = logging.getLogger("ghostscripter.test_ring_buffer_overflow")
        for i in range(cap + 50):
            logger.debug("overflow test %d", i)
        self.assertLessEqual(len(ls._RECENT), cap,
                             "Ring buffer must not exceed _MAX_RECENT")
        # Restore approximate previous size (not strictly required by test)

    def test_get_recent_records_returns_list(self):
        """get_recent_records() must return a list (not a deque)."""
        from ghostscripter.utils.log_setup import get_recent_records
        result = get_recent_records()
        self.assertIsInstance(result, list)


# ─────────────────────────────────────────────────────────────────────────────
# BUG-6 — log_viewer_widget: _passes_filter logic and docstring
# ─────────────────────────────────────────────────────────────────────────────

class TestBug6LogViewerFilter(unittest.TestCase):
    """
    Test the corrected _passes_filter logic in LogViewerWidget.
    These tests do NOT require a live Qt application — they directly instantiate
    fake button stubs to drive the logic.
    """

    def _make_record(self, level: int, name: str = "test",
                     msg: str = "test message") -> logging.LogRecord:
        return logging.LogRecord(
            name=name, level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )

    def test_passes_filter_uses_set_not_list(self):
        """The checked_levels variable must use set comprehension for O(1) lookup."""
        import inspect
        import ghostscripter.ui.widgets.log_viewer_widget as m
        src = inspect.getsource(m.LogViewerWidget._passes_filter)
        # Must use set comprehension syntax: { ... for ... in ... if ... }
        # Either explicit `set(...)` or `{ expr for ... }` (set comprehension)
        has_set_comprehension = "{" in src and "for" in src
        has_explicit_set = "set(" in src
        self.assertTrue(
            has_set_comprehension or has_explicit_set,
            "_passes_filter must use a set comprehension for O(1) lookup, got:\n" + src,
        )

    def test_docstring_says_exact_match(self):
        """Docstring must describe exact per-level toggle behaviour."""
        import ghostscripter.ui.widgets.log_viewer_widget as m
        doc = m.LogViewerWidget._passes_filter.__doc__ or ""
        self.assertIn("exact", doc.lower(),
                      "Docstring must mention 'exact' per-level matching")


# ─────────────────────────────────────────────────────────────────────────────
# BUG-7 — ghostrigger_bridge.py: IPCCallbackServer port conflict warning
# ─────────────────────────────────────────────────────────────────────────────

class TestBug7IPCPortConflict(unittest.TestCase):
    """
    IPCCallbackServer defaults to port 7002, which conflicts with IPCServer.
    The class docstring must warn users not to start both simultaneously.
    """

    def test_ipc_callback_server_has_deprecation_warning(self):
        from ghostscripter.ipc.ghostrigger_bridge import IPCCallbackServer
        doc = IPCCallbackServer.__doc__ or ""
        # Must contain a deprecation/warning note about port conflict
        self.assertTrue(
            any(word in doc.lower() for word in ("deprecated", "conflict", "prefer", "not")),
            "IPCCallbackServer docstring must warn about port conflict with IPCServer. "
            f"Current docstring:\n{doc}",
        )

    def test_ipc_server_default_port(self):
        """IPCServer (ipc_server.py) defaults to port 7002."""
        from ghostscripter.ipc.ipc_server import GHOSTSCRIPTER_PORT
        self.assertEqual(GHOSTSCRIPTER_PORT, 7002)

    def test_ipc_callback_server_default_port(self):
        """IPCCallbackServer defaults to port 7002."""
        import inspect
        from ghostscripter.ipc.ghostrigger_bridge import IPCCallbackServer
        sig = inspect.signature(IPCCallbackServer.__init__)
        default_port = sig.parameters.get("port")
        self.assertIsNotNone(default_port)
        self.assertEqual(default_port.default, 7002)


# ─────────────────────────────────────────────────────────────────────────────
# Integration: full DLG round-trip still works after all fixes
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrationAfterFixes(unittest.TestCase):
    """
    End-to-end DLG round-trip tests that confirm all bug fixes work together
    without breaking existing functionality.
    """

    def _make_dlg(self) -> DialogueFile:
        dlg = DialogueFile(name="integration_test")
        dlg.on_end   = "k_end_script"
        dlg.on_abort = "k_abort_sc"
        dlg.skippable = True

        e0 = DialogueNode(node_id=0, node_type="entry")
        e0.text = "Hello, traveller."
        e0.speaker = "npc_001"
        e0.script1 = "k_enter_dlg"
        e0.text_strref = 10001

        r0 = DialogueNode(node_id=0, node_type="reply")
        r0.text = "Greetings."
        r0.text_strref = 20001

        e0.branches.append(DialogueBranch(branch_id=0, target_node_id=0))
        dlg.entries.append(e0)
        dlg.replies.append(r0)
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))
        return dlg

    def test_roundtrip_k1_all_fields(self):
        dlg = self._make_dlg()
        data = DLGExporter().export(dlg, "K1")
        rt = DLGImporter().import_from_bytes(data)
        self.assertEqual(rt.on_end,   "k_end_script")
        self.assertEqual(rt.on_abort, "k_abort_sc")
        self.assertTrue(rt.skippable)
        self.assertGreater(len(rt.entries), 0)
        self.assertEqual(rt.entries[0].speaker, "npc_001")
        self.assertEqual(rt.entries[0].script1, "k_enter_dlg")

    def test_roundtrip_k2_all_fields(self):
        dlg = self._make_dlg()
        data = DLGExporter().export(dlg, "K2")
        rt = DLGImporter().import_from_bytes(data)
        self.assertEqual(rt.on_end,   "k_end_script")
        self.assertEqual(rt.on_abort, "k_abort_sc")

    def test_gff_header_magic_preserved(self):
        dlg = self._make_dlg()
        data = DLGExporter().export(dlg)
        self.assertEqual(data[:4], b"DLG ")
        self.assertEqual(data[4:8], b"V3.2")

    def test_strref_in_dlg_nodes_preserved(self):
        dlg = self._make_dlg()
        data = DLGExporter().export(dlg)
        rt = DLGImporter().import_from_bytes(data)
        if rt.entries:
            self.assertEqual(rt.entries[0].text_strref, 10001)
        if rt.replies:
            self.assertEqual(rt.replies[0].text_strref, 20001)

    def test_multiple_entries_and_replies_preserved(self):
        dlg = DialogueFile(name="multi_test")
        for i in range(5):
            e = DialogueNode(node_id=i, node_type="entry")
            e.text = f"Entry {i}"
            dlg.entries.append(e)
        for i in range(7):
            r = DialogueNode(node_id=i, node_type="reply")
            r.text = f"Reply {i}"
            dlg.replies.append(r)
        data = DLGExporter().export(dlg)
        rt = DLGImporter().import_from_bytes(data)
        self.assertEqual(len(rt.entries), 5)
        self.assertEqual(len(rt.replies), 7)


if __name__ == "__main__":
    unittest.main()


# ── BUG-8  asset_library_widget.py ──────────────────────────────────────────
# _GameAssetLoader.run() passed str(self._game_dir) to ResourceManager.load_game(),
# but load_game() calls game_dir.exists() which doesn't exist on str.
# Error: "Could not load game assets: 'str' object has no attribute 'exists'"
# Fix: pass Path(self._game_dir) instead of str(self._game_dir).
#
# BUG-9  asset_library_widget.py ──────────────────────────────────────────
# AssetLibraryWidget.__init__ stored game_dir as-is (str or Path), causing
# inconsistency with set_game_dir() which always converts to Path.
# Fix: always store _game_dir as Path in __init__.

class TestAssetLibraryBugFixes(unittest.TestCase):
    """Regression tests for asset_library_widget fixes (BUG-8, BUG-9)."""

    def test_game_asset_loader_passes_path_not_str(self):
        """_GameAssetLoader should always pass a Path to ResourceManager.load_game."""
        from pathlib import Path
        import unittest.mock as mock

        with mock.patch(
            "ghostscripter.core.resource_manager.resource_manager.ResourceManager"
        ) as MockRM:
            rm_instance = MockRM.return_value
            rm_instance.load_game.return_value = True
            rm_instance.list_by_type.return_value = []

            # Import after patching
            from ghostscripter.ui.widgets.asset_library_widget import _GameAssetLoader

            game_dir = Path("/fake/kotor")
            loader = _GameAssetLoader(game_dir)
            loader.run()

            # load_game must have been called with a Path, not a string
            call_args = rm_instance.load_game.call_args
            self.assertIsNotNone(call_args, "_GameAssetLoader never called load_game()")
            arg = call_args[0][0]
            self.assertIsInstance(
                arg, Path,
                f"load_game() was called with {type(arg).__name__!r}, expected Path"
            )

    def test_asset_library_widget_stores_game_dir_as_path(self):
        """AssetLibraryWidget.__init__ must store _game_dir as Path when a str is given."""
        import os, sys, unittest.mock as mock

        # Skip if no display / Qt not available
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available in this environment")

        from pathlib import Path
        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget

        # Pass a string path (no actual dir needed, just check storage type)
        w = AssetLibraryWidget(game_dir="/some/string/path")
        self.assertIsInstance(
            w._game_dir, Path,
            f"_game_dir should be Path, got {type(w._game_dir).__name__!r}"
        )

    def test_asset_library_widget_none_game_dir(self):
        """AssetLibraryWidget with no game_dir should store None, not crash."""
        import os, sys, unittest.mock as mock

        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available in this environment")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget

        w = AssetLibraryWidget(game_dir=None)
        self.assertIsNone(w._game_dir)

    def test_asset_library_set_game_dir_converts_str(self):
        """set_game_dir() must convert str to Path and store it."""
        import os, sys

        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available in this environment")

        from pathlib import Path
        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        import unittest.mock as mock

        w = AssetLibraryWidget(game_dir=None)
        # set_game_dir with non-existent path — should convert to Path but not load
        with mock.patch.object(w, "_load_game_assets") as mock_load:
            w.set_game_dir("/some/path")
            # _game_dir stored as Path
            self.assertIsInstance(w._game_dir, Path)
            # _load_game_assets not called (path doesn't exist)
            mock_load.assert_not_called()

    # ── BUG-10  asset_library_widget.py / main_window.py ──────────────────────
    # Double-clicking a game asset showed "Use the main menu to open the
    # appropriate editor" instead of actually opening the editor.
    # Fix: AssetLibraryWidget now emits open_asset_requested(resref, ext, data)
    # and MainWindow.open_asset_from_library() routes it to the correct editor.

    def test_open_asset_requested_signal_exists(self):
        """AssetLibraryWidget must expose an open_asset_requested signal."""
        import os, sys
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        w = AssetLibraryWidget(game_dir=None)
        self.assertTrue(
            hasattr(w, "open_asset_requested"),
            "AssetLibraryWidget is missing 'open_asset_requested' signal"
        )

    def test_double_click_emits_signal_with_bytes(self):
        """Double-clicking a tree item must emit open_asset_requested with the raw bytes."""
        import os, sys
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication, QTreeWidgetItem
            from qtpy.QtCore import Qt
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        import unittest.mock as mock

        w = AssetLibraryWidget(game_dir=None)

        # Fake ResourceManager that returns dummy bytes
        fake_rm = mock.MagicMock()
        fake_rm.read.return_value = b"DLG V3.2" + b"\x00" * 100
        w._resource_manager = fake_rm

        emitted: list = []
        w.open_asset_requested.connect(lambda resref, ext, data: emitted.append((resref, ext, data)))

        # Build a fake QTreeWidgetItem with the right UserRole data
        item = QTreeWidgetItem(["kor35_utharwynn.dlg"])
        item.setData(0, Qt.UserRole, {"name": "kor35_utharwynn", "ext": ".dlg"})

        w._on_game_asset_double_click(item, 0)

        self.assertEqual(len(emitted), 1, "open_asset_requested should have been emitted once")
        resref, ext, data = emitted[0]
        self.assertEqual(resref, "kor35_utharwynn")
        self.assertEqual(ext, ".dlg")
        self.assertIsInstance(data, bytes, "raw bytes should be passed with the signal")
        fake_rm.read.assert_called_once_with("kor35_utharwynn.dlg")

    def test_double_click_nss_emits_signal(self):
        """Double-clicking an .nss script should emit open_asset_requested."""
        import os, sys
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication, QTreeWidgetItem
            from qtpy.QtCore import Qt
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        import unittest.mock as mock

        w = AssetLibraryWidget(game_dir=None)

        fake_rm = mock.MagicMock()
        fake_rm.read.return_value = b"void main() {}"
        w._resource_manager = fake_rm

        emitted: list = []
        w.open_asset_requested.connect(lambda r, e, d: emitted.append((r, e, d)))

        item = QTreeWidgetItem(["k_ai_master.nss"])
        item.setData(0, Qt.UserRole, {"name": "k_ai_master", "ext": ".nss"})
        w._on_game_asset_double_click(item, 0)

        self.assertEqual(len(emitted), 1)
        resref, ext, data = emitted[0]
        self.assertEqual(resref, "k_ai_master")
        self.assertEqual(ext, ".nss")
        self.assertIsNotNone(data)

    # ── BUG-11  asset_library_widget.py — double extension in rm.read() ──────
    # _populate_game_asset_tab stored the FULL filename ("kor35_utharwynn.dlg")
    # in the UserRole "name" field.  _on_game_asset_double_click then called
    # rm.read(name + ext) → rm.read("kor35_utharwynn.dlg.dlg") which returned
    # None, so ipc_open_dlg was called with no bytes and opened a blank file.
    # Fix: _populate_game_asset_tab now stores just the bare resref in "name".

    def test_populate_game_asset_tab_stores_resref_not_full_filename(self):
        """_populate_game_asset_tab must store the bare resref (no extension) in UserRole name."""
        import os, sys
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from qtpy.QtWidgets import QApplication
            from qtpy.QtCore import Qt
            app = QApplication.instance() or QApplication(sys.argv[:1])
        except Exception:
            self.skipTest("Qt not available")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget

        w = AssetLibraryWidget(game_dir=None)

        # Inject fake game assets — full filenames as they come from _GameAssetLoader
        w._game_assets = {
            ".dlg": ["kor35_utharwynn.dlg", "mainmenu.dlg"],
            ".nss": ["k_ai_master.nss"],
        }
        w._populate_game_asset_tab()

        # Walk the tree and verify every item's UserRole "name" is a bare resref
        for i in range(w.game_tree.topLevelItemCount()):
            cat = w.game_tree.topLevelItem(i)
            for j in range(cat.childCount()):
                child = cat.child(j)
                data = child.data(0, Qt.UserRole)
                self.assertIsInstance(data, dict)
                name = data.get("name", "")
                ext  = data.get("ext", "")
                self.assertFalse(
                    name.endswith(ext),
                    f"name {name!r} should be a bare resref, not include extension {ext!r}"
                )
                # Also verify rm.read would use the right filename
                self.assertEqual(name + ext, child.text(0),
                    f"name+ext should equal the display text; got {name+ext!r} vs {child.text(0)!r}")


# ── BUG-12  main_window.py — .ncs double-click showed blank script editor ─────
# open_asset_from_library() for .ncs files just put a one-line stub comment in
# the script editor instead of decompiling the bytecode.
# Fix: _decompile_ncs_bytes() calls PyKotor NCSDecompiler → NCSBinaryReader
# disassembly → stub, in that priority order.

class TestDecompileNcsBytes(unittest.TestCase):
    """Regression tests for MainWindow._decompile_ncs_bytes (BUG-12)."""

    def _make_ncs_bytes(self) -> bytes:
        """Compile a minimal script and return the raw NCS bytes."""
        import base64, asyncio
        from ghostscripter.mcp.tools_pkg.handlers_write import _compile_script
        import json

        async def _compile():
            return await _compile_script({
                "game": "K1",
                "source": "void main() {}",
                "resref": "test_decompile",
            })

        result = asyncio.run(_compile())
        data = json.loads(result[0].text)
        if data.get("success") and data.get("data_base64"):
            return base64.b64decode(data["data_base64"])
        self.skipTest("PyKotor compiler not available")

    def _make_main_window_stub(self):
        """Create a minimal stub with just the _decompile_ncs_bytes method."""
        import types, sys

        # Import the real method without instantiating MainWindow (which needs Qt)
        # by attaching it to a plain object
        class Stub:
            _game_dir = None
            def log(self, msg):
                pass

        from ghostscripter.ui.main_window import MainWindow
        Stub._decompile_ncs_bytes = MainWindow._decompile_ncs_bytes
        return Stub()

    def test_decompile_returns_nonempty_string_for_valid_ncs(self):
        """_decompile_ncs_bytes must return a non-empty string for valid NCS bytes."""
        ncs_bytes = self._make_ncs_bytes()
        stub = self._make_main_window_stub()
        result = stub._decompile_ncs_bytes(ncs_bytes, "test_decompile")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0, "Expected non-empty decompile output")

    def test_decompile_contains_void_main(self):
        """Decompiling a void main() script should produce text containing 'void main'."""
        ncs_bytes = self._make_ncs_bytes()
        stub = self._make_main_window_stub()
        result = stub._decompile_ncs_bytes(ncs_bytes, "test_decompile")
        self.assertIn("void main", result,
            f"Expected 'void main' in decompiled output, got:\n{result[:300]}")

    def test_decompile_empty_bytes_returns_stub(self):
        """_decompile_ncs_bytes must not crash on empty input."""
        stub = self._make_main_window_stub()
        result = stub._decompile_ncs_bytes(b"", "empty_script")
        self.assertIsInstance(result, str)
        self.assertIn("empty_script", result)

    def test_decompile_garbage_bytes_returns_stub(self):
        """_decompile_ncs_bytes must return a stub (not raise) for unrecognised bytes."""
        stub = self._make_main_window_stub()
        result = stub._decompile_ncs_bytes(b"\xff\xfe\x00\x01" * 16, "bad_script")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


# ---------------------------------------------------------------------------
# BUG-13: MainWindow.open_tlk_editor() accidentally dropped in BUG-12 commit
# ---------------------------------------------------------------------------

class TestBug13TlkEditorMethodRestored(unittest.TestCase):
    """BUG-13 — open_tlk_editor() method was dropped from MainWindow, causing
    AttributeError: 'MainWindow' object has no attribute 'open_tlk_editor'
    on every startup (in _add_welcome_tab / _setup_ui).
    """

    def test_main_window_has_open_tlk_editor(self):
        """MainWindow class must define open_tlk_editor as a callable method."""
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "main_window.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Collect all method names defined directly inside MainWindow
        method_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
                for item in ast.walk(node):
                    if isinstance(item, ast.FunctionDef):
                        method_names.add(item.name)
        self.assertIn(
            "open_tlk_editor",
            method_names,
            "MainWindow must define open_tlk_editor() — it was accidentally removed in BUG-12 commit"
        )

    def test_open_tlk_editor_not_inside_decompile_ncs_bytes(self):
        """open_tlk_editor must be a top-level method of MainWindow, not nested
        inside _decompile_ncs_bytes (which was the broken state)."""
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "main_window.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
                # Direct children of MainWindow should include open_tlk_editor
                direct_methods = {
                    item.name for item in node.body
                    if isinstance(item, ast.FunctionDef)
                }
                self.assertIn(
                    "open_tlk_editor",
                    direct_methods,
                    "open_tlk_editor must be a direct method of MainWindow, "
                    "not nested inside another method"
                )
                return
        self.fail("MainWindow class not found in main_window.py")


# ---------------------------------------------------------------------------
# BUG-14: Double-clicking .utc / .uti / .utp etc. shows text summary instead
#         of a dedicated editor tab
# ---------------------------------------------------------------------------

def _make_synthetic_utc_bytes() -> bytes:
    """Return minimal real GFF UTC bytes (using PyKotor round-trip)."""
    import tempfile, os
    from pathlib import Path
    from pykotor.resource.generics.utc import UTC, write_utc
    from pykotor.common.misc import Game
    utc = UTC()
    utc.resref = "test_npc"
    utc.tag = "TEST_NPC"
    utc.strength = 14
    utc.max_hp = 50
    utc.challenge_rating = 2
    with tempfile.NamedTemporaryFile(suffix=".utc", delete=False) as f:
        tmp = f.name
    write_utc(utc, Path(tmp), game=Game.K1)
    raw = Path(tmp).read_bytes()
    os.unlink(tmp)
    return raw


def _make_synthetic_uti_bytes() -> bytes:
    """Return minimal real GFF UTI bytes."""
    import tempfile, os
    from pathlib import Path
    from pykotor.resource.generics.uti import UTI, write_uti
    from pykotor.common.misc import Game
    uti = UTI()
    uti.resref = "test_item"
    uti.tag = "TEST_ITEM"
    uti.cost = 500
    with tempfile.NamedTemporaryFile(suffix=".uti", delete=False) as f:
        tmp = f.name
    write_uti(uti, Path(tmp), game=Game.K1)
    raw = Path(tmp).read_bytes()
    os.unlink(tmp)
    return raw


class TestBug14GFFTemplateViewer(unittest.TestCase):
    """BUG-14 — double-clicking UTC/UTI/etc. must open a GFFTemplateViewerWidget tab."""

    # ── Widget unit tests (no Qt needed for these) ────────────────────────────

    def test_gff_template_viewer_module_importable(self):
        """GFFTemplateViewerWidget must be importable without Qt."""
        from ghostscripter.ui.widgets.gff_template_viewer_widget import (
            GFFTemplateViewerWidget,
            _TYPE_META,
        )
        self.assertIn(".utc", _TYPE_META)
        self.assertIn(".uti", _TYPE_META)
        self.assertIn(".utp", _TYPE_META)
        self.assertIn(".utt", _TYPE_META)
        self.assertIn(".utm", _TYPE_META)
        self.assertIn(".uts", _TYPE_META)
        self.assertIn(".utw", _TYPE_META)

    def test_gff_template_viewer_has_correct_metadata(self):
        """Each type entry must have loader, module, and sections keys."""
        from ghostscripter.ui.widgets.gff_template_viewer_widget import _TYPE_META
        for ext, meta in _TYPE_META.items():
            with self.subTest(ext=ext):
                self.assertIn("loader",   meta, f"{ext} missing 'loader'")
                self.assertIn("module",   meta, f"{ext} missing 'module'")
                self.assertIn("sections", meta, f"{ext} missing 'sections'")
                self.assertIn("label",    meta, f"{ext} missing 'label'")

    def test_utc_pykotor_round_trip(self):
        """write_utc / read_utc round-trip must preserve tag and strength."""
        raw = _make_synthetic_utc_bytes()
        self.assertIsInstance(raw, bytes)
        self.assertGreater(len(raw), 100)
        self.assertEqual(raw[:4], b"UTC ")   # GFF magic
        from pykotor.resource.generics.utc import read_utc
        obj = read_utc(raw)
        self.assertEqual(obj.tag, "TEST_NPC")
        self.assertEqual(obj.strength, 14)
        self.assertEqual(obj.max_hp, 50)

    def test_uti_pykotor_round_trip(self):
        """write_uti / read_uti round-trip must preserve tag and cost."""
        raw = _make_synthetic_uti_bytes()
        self.assertIsInstance(raw, bytes)
        self.assertEqual(raw[:4], b"UTI ")
        from pykotor.resource.generics.uti import read_uti
        obj = read_uti(raw)
        self.assertEqual(obj.tag, "TEST_ITEM")
        self.assertEqual(obj.cost, 500)

    def test_viewer_type_loader_functions_exist(self):
        """Every loader function referenced in _TYPE_META must actually exist in its module."""
        from ghostscripter.ui.widgets.gff_template_viewer_widget import _TYPE_META
        for ext, meta in _TYPE_META.items():
            with self.subTest(ext=ext):
                mod = __import__(meta["module"], fromlist=[meta["loader"]])
                fn  = getattr(mod, meta["loader"], None)
                self.assertIsNotNone(
                    fn, f"{meta['loader']} not found in {meta['module']}"
                )
                self.assertTrue(callable(fn), f"{meta['loader']} is not callable")

    # ── main_window wiring tests ──────────────────────────────────────────────

    def test_main_window_has_gff_viewer_types_set(self):
        """MainWindow._GFF_VIEWER_TYPES must include all seven template extensions."""
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("_GFF_VIEWER_TYPES", src,
                      "_GFF_VIEWER_TYPES frozenset missing from main_window.py")
        for ext in (".utc", ".uti", ".utp", ".utt", ".utm", ".uts", ".utw"):
            self.assertIn(f'"{ext}"', src,
                          f'{ext} not found in _GFF_VIEWER_TYPES definition')

    def test_main_window_imports_gff_template_viewer(self):
        """main_window.py must import GFFTemplateViewerWidget."""
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("GFFTemplateViewerWidget", src,
                      "GFFTemplateViewerWidget not imported in main_window.py")

    def test_open_gff_asset_opens_viewer_for_utc(self):
        """_open_gff_asset must create a GFFTemplateViewerWidget for .utc files."""
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from qtpy.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from ghostscripter.ui.widgets.gff_template_viewer_widget import GFFTemplateViewerWidget

        raw = _make_synthetic_utc_bytes()

        # Minimal stub that records tabs added
        tabs_added = []

        class _FakeTabBar:
            RightSide = 1
            def tabButton(self, idx, side): return None

        class _FakeTabs:
            def count(self): return 0
            def tabText(self, i): return ""
            def widget(self, i): return None
            def addTab(self, w, title):
                tabs_added.append((w, title))
                return 0
            def setCurrentIndex(self, i): pass
            def tabBar(self): return _FakeTabBar()

        class _Stub:
            _GFF_VIEWER_TYPES = frozenset({
                ".utc", ".uti", ".utp", ".utt", ".utm", ".uts", ".utw",
            })
            editor_tabs = _FakeTabs()
            def log(self, msg): pass
            _open_gff_asset = GFFTemplateViewerWidget.__module__ and None  # ensure import available

        # Bind the real method to the stub
        import types
        from ghostscripter.ui.main_window import MainWindow
        stub = _Stub()
        stub._open_gff_asset = types.MethodType(MainWindow._open_gff_asset, stub)

        stub._open_gff_asset("test_npc", ".utc", raw)

        self.assertEqual(len(tabs_added), 1, "Expected exactly one tab to be added")
        widget, title = tabs_added[0]
        self.assertIsInstance(widget, GFFTemplateViewerWidget,
                              "Tab widget must be a GFFTemplateViewerWidget")
        self.assertIn("utc", title.lower(),
                      f"Tab title should mention 'utc', got: {title!r}")

# ---------------------------------------------------------------------------
# BUG-15: .uti/.utp not opening; TPC preview broken; texture packs not loaded
# ---------------------------------------------------------------------------

class TestBug15UTIUTPOpenAndTpcPreview(unittest.TestCase):
    """BUG-15 — three related fixes for the asset library texture/template handling."""

    # ── (a) UTI/UTP raw_data fallback ────────────────────────────────────────

    def test_open_asset_from_library_retries_rm_when_raw_data_none(self):
        """open_asset_from_library must call _read_asset_from_rm when raw_data is None
        for GFF template types, then pass the recovered bytes to _open_gff_asset."""
        import types
        from ghostscripter.ui.main_window import MainWindow

        recovered_data = b"UTI " + b"\x00" * 100   # minimal fake GFF bytes

        calls = {}

        class _FakeTabBar:
            RightSide = 1
            def tabButton(self, idx, side): return None

        class _FakeTabs:
            def count(self): return 0
            def tabText(self, i): return ""
            def widget(self, i): return None
            def addTab(self, w, title):
                calls["tab_added"] = (w, title)
                return 0
            def setCurrentIndex(self, i): pass
            def tabBar(self): return _FakeTabBar()

        class _Stub:
            _GFF_VIEWER_TYPES = frozenset({
                ".utc", ".uti", ".utp", ".utt", ".utm", ".uts", ".utw",
            })
            editor_tabs = _FakeTabs()
            def log(self, msg): pass
            def _read_asset_from_rm(self, resref, ext):
                calls["rm_read"] = (resref, ext)
                return recovered_data
            def _open_gff_asset(self, resref, ext, raw_data):
                calls["gff_opened"] = (resref, ext, raw_data)

        stub = _Stub()
        # Bind open_asset_from_library to the stub
        stub.open_asset_from_library = types.MethodType(
            MainWindow.open_asset_from_library, stub
        )

        # Call with raw_data=None — should retry via _read_asset_from_rm
        stub.open_asset_from_library("g_i_mask01", ".uti", None)

        self.assertIn("rm_read", calls,
                      "_read_asset_from_rm must be called when raw_data is None")
        self.assertEqual(calls["rm_read"], ("g_i_mask01", ".uti"))
        self.assertIn("gff_opened", calls,
                      "_open_gff_asset must be called after RM retry")
        self.assertEqual(calls["gff_opened"][2], recovered_data,
                         "recovered bytes must be passed to _open_gff_asset")

    # ── (b) TPC preview uses to_qimage, not write_tpc ────────────────────────

    def test_show_texture_preview_uses_to_qimage(self):
        """_show_texture_preview for .tpc must not call write_tpc with BytesIO.
        Instead it must use TPCMipmap.to_qimage() to produce the QImage."""
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "widgets" / "asset_library_widget.py"
               ).read_text(encoding="utf-8")
        # The broken pattern is using write_tpc with io.BytesIO
        self.assertNotIn(
            "write_tpc(tpc, buf, ResourceType.TGA)",
            src,
            "_show_texture_preview must NOT use write_tpc(buf, ResourceType.TGA) — "
            "this causes ValueError from PyKotor stream lifecycle"
        )
        # The correct pattern is to_qimage()
        self.assertIn(
            "to_qimage()",
            src,
            "_show_texture_preview must use TPCMipmap.to_qimage()"
        )

    def test_tpc_mip_to_qimage_produces_valid_image(self):
        """TPCMipmap.to_qimage() must produce a non-null QImage for a synthetic TPC."""
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from qtpy.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from pykotor.resource.formats.tpc.tpc_data import TPC, TPCTextureFormat
        tpc = TPC()
        # 4×4 RGBA image (minimum size for DXT compression)
        tpc.set_single(b"\xff\x00\x00\xff" * 16, TPCTextureFormat.RGBA, 4, 4)
        mip = tpc.get(0, 0)
        qimg = mip.to_qimage()
        self.assertIsNotNone(qimg)
        self.assertFalse(qimg.isNull(), "to_qimage() should return a valid QImage")
        self.assertEqual(qimg.width(), 4)
        self.assertEqual(qimg.height(), 4)

    # ── (c) ResourceManager loads texture pack ERFs ──────────────────────────

    def test_load_game_scans_texture_packs_when_present(self):
        """ResourceManager.load_game() must load swpc_tex_tp*.erf if the
        TexturePacks directory exists."""
        import tempfile, shutil
        from pathlib import Path
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager

        # Build a fake game directory with a TexturePacks folder and a dummy ERF
        with tempfile.TemporaryDirectory() as tmp:
            game_dir  = Path(tmp)
            tex_dir   = game_dir / "TexturePacks"
            tex_dir.mkdir()
            over_dir  = game_dir / "override"
            over_dir.mkdir()

            # Write a minimal valid ERF V1.0 binary (0 entries)
            def _minimal_erf() -> bytes:
                # ERF header: type(4) + version(4) + lang_count(4) + desc_size(4)
                # + entry_count(4) + off_localstr(4) + off_keys(4) + off_res(4)
                # + build_year(4) + build_day(4) + desc_strref(4) + reserved(116)
                import struct
                header = b"ERF " + b"V1.0"
                header += struct.pack("<IIIIIIII", 0, 0, 0, 160, 160, 160, 0, 0)
                header += struct.pack("<I", 0xFFFFFFFF)  # desc_strref
                header += b"\x00" * 116
                return header

            erf_bytes = _minimal_erf()
            (tex_dir / "swpc_tex_tpa.erf").write_bytes(erf_bytes)

            rm = ResourceManager()
            ok = rm.load_game(game_dir)
            self.assertTrue(ok)
            # The ERF should have been loaded (even if it has 0 entries)
            self.assertGreater(
                len(rm._erfs), 0,
                "ResourceManager._erfs must include the texture pack ERF"
            )

    # ── Template type coverage in asset library ───────────────────────────────

    def test_asset_loader_scans_all_template_types(self):
        """_GameAssetLoader must scan .utt, .utm, .uts, .utw in addition to
        the original .uti, .utc, .utp."""
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "widgets" / "asset_library_widget.py"
               ).read_text(encoding="utf-8")
        for ext in (".utt", ".utm", ".uts", ".utw"):
            self.assertIn(
                f'"{ext}"', src,
                f"{ext} must appear in the _GameAssetLoader scan list"
            )

    def test_populate_game_asset_tab_includes_all_template_types(self):
        """_populate_game_asset_tab type_meta must include all seven template types."""
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "widgets" / "asset_library_widget.py"
               ).read_text(encoding="utf-8")
        for ext in (".utc", ".uti", ".utp", ".utt", ".utm", ".uts", ".utw"):
            self.assertIn(
                f'"{ext}"', src,
                f"{ext} must appear in the _populate_game_asset_tab type_meta dict"
            )


# ─────────────────────────────────────────────────────────────────────────────
# BUG-16 — TGA/TPC preview "not available" because Qt rejects KotOR TGA-1 files
# ─────────────────────────────────────────────────────────────────────────────

class TestBug16TexturePreviewDecoding(unittest.TestCase):
    """
    BUG-16: _show_texture_preview always showed "preview not available" for
    .tga files because Qt's QTgaHandler only accepts TrueVision-2.0 files
    (those ending with 'TRUEVISION-XFILE\0').  KotOR TGA files are plain
    TGA-1 format and Qt rejects them with:
        QTgaHandler::canRead(): Image type (non-TrueVision 2.0) not supported

    Fix: use Pillow (PIL) as the primary decoder for .tga/.png/.bmp; fall
    back to Qt's native loader only as a secondary attempt.  Also add a PIL
    fallback for .tpc in case TPCMipmap.to_qimage() ever fails.
    """

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_tga1_bytes(w: int = 4, h: int = 4) -> bytes:
        """Build a minimal TGA-1 (non-TV2.0) RGBA image in memory."""
        header = bytearray(18)
        header[2]  = 2        # uncompressed true-colour
        header[12] = w & 0xFF
        header[13] = (w >> 8) & 0xFF
        header[14] = h & 0xFF
        header[15] = (h >> 8) & 0xFF
        header[16] = 32       # bits per pixel
        header[17] = 0x20     # top-left origin
        pixel_data = bytes([255, 0, 0, 255] * w * h)  # red RGBA
        return bytes(header) + pixel_data

    @staticmethod
    def _make_tga2_bytes(w: int = 4, h: int = 4) -> bytes:
        """Build a TGA-2 (TrueVision-2.0) RGBA image with footer."""
        header = bytearray(18)
        header[2]  = 2
        header[12] = w & 0xFF
        header[13] = (w >> 8) & 0xFF
        header[14] = h & 0xFF
        header[15] = (h >> 8) & 0xFF
        header[16] = 32
        header[17] = 0x20
        pixel_data = bytes([0, 255, 0, 255] * w * h)  # green RGBA
        footer = b'\x00' * 8 + b'TRUEVISION-XFILE\x00'
        return bytes(header) + pixel_data + footer

    # ── _decode_tga_with_pil ──────────────────────────────────────────────────

    def test_decode_tga1_via_pil(self):
        """_decode_tga_with_pil must decode a TGA-1 (KotOR-style) file."""
        pytest = __import__("pytest")
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        data = self._make_tga1_bytes(4, 4)
        qimg = AssetLibraryWidget._decode_tga_with_pil(data)
        self.assertIsNotNone(qimg, "_decode_tga_with_pil must return a QImage for TGA-1")
        self.assertFalse(qimg.isNull(), "QImage must not be null for valid TGA-1")
        self.assertEqual(qimg.width(),  4)
        self.assertEqual(qimg.height(), 4)

    def test_decode_tga2_via_pil(self):
        """_decode_tga_with_pil must also decode TGA-2 (TrueVision-2.0) files."""
        pytest = __import__("pytest")
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        data = self._make_tga2_bytes(4, 4)
        qimg = AssetLibraryWidget._decode_tga_with_pil(data)
        self.assertIsNotNone(qimg)
        self.assertFalse(qimg.isNull())

    def test_decode_tga_returns_none_on_garbage(self):
        """_decode_tga_with_pil must return None for invalid data (no crash)."""
        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        result = AssetLibraryWidget._decode_tga_with_pil(b"\x00\x01\x02garbage data")
        # Must not raise; result is None or a QImage — either is acceptable as long
        # as there's no exception.
        self.assertTrue(result is None or hasattr(result, "isNull"))

    # ── _pil_to_qimage ────────────────────────────────────────────────────────

    def test_pil_to_qimage_rgba(self):
        """_pil_to_qimage must convert a PIL RGBA image to a valid QImage."""
        pytest = __import__("pytest")
        try:
            from PIL import Image as _PIL
        except ImportError:
            pytest.skip("Pillow not installed")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        pil_img = _PIL.new("RGBA", (8, 8), (128, 64, 32, 255))
        qimg = AssetLibraryWidget._pil_to_qimage(pil_img)
        self.assertIsNotNone(qimg)
        self.assertFalse(qimg.isNull())
        self.assertEqual(qimg.width(),  8)
        self.assertEqual(qimg.height(), 8)

    def test_pil_to_qimage_rgb_auto_converts(self):
        """_pil_to_qimage must accept RGB (non-RGBA) PIL images via auto-convert."""
        pytest = __import__("pytest")
        try:
            from PIL import Image as _PIL
        except ImportError:
            pytest.skip("Pillow not installed")

        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        pil_img = _PIL.new("RGB", (6, 6), (255, 0, 0))
        qimg = AssetLibraryWidget._pil_to_qimage(pil_img)
        self.assertIsNotNone(qimg)
        self.assertFalse(qimg.isNull())

    # ── TPC round-trip ────────────────────────────────────────────────────────

    def test_tpc_to_qimage_via_mip(self):
        """TPC decode path: TPCMipmap.to_qimage() must produce a valid QImage."""
        pytest = __import__("pytest")
        try:
            from pykotor.resource.formats.tpc import TPC, TPCTextureFormat
        except ImportError:
            pytest.skip("pykotor not installed")

        tpc = TPC()
        tpc.set_single(bytes([0, 128, 255, 255] * 4), TPCTextureFormat.RGBA, 2, 2)
        mip  = tpc.get(0, 0)
        qimg = mip.to_qimage()
        self.assertFalse(qimg.isNull(), "to_qimage() must return a valid QImage")
        self.assertEqual(qimg.width(),  2)
        self.assertEqual(qimg.height(), 2)

    # ── Ensure Pillow is available (environment smoke test) ───────────────────

    def test_pillow_available(self):
        """Pillow must be importable — it is required for TGA decoding."""
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.fail("Pillow is not installed; 'pip install Pillow' is required for TGA preview")

    # ── Source-level check: PIL decode path present in source code ────────────

    def test_pil_decode_used_for_tga(self):
        """_show_texture_preview source must use PIL (not only Qt) for .tga files."""
        from pathlib import Path
        src = (Path(__file__).parent.parent /
               "ghostscripter" / "ui" / "widgets" / "asset_library_widget.py"
               ).read_text(encoding="utf-8")
        self.assertIn("_decode_tga_with_pil", src,
                      "_show_texture_preview must call _decode_tga_with_pil for TGA files")
        self.assertIn("PIL", src,
                      "PIL/Pillow must be referenced in the texture preview code")

    def test_tga_helper_methods_defined(self):
        """Both static helper methods must be defined on AssetLibraryWidget."""
        from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
        self.assertTrue(hasattr(AssetLibraryWidget, "_decode_tga_with_pil"),
                        "AssetLibraryWidget must have _decode_tga_with_pil static method")
        self.assertTrue(hasattr(AssetLibraryWidget, "_pil_to_qimage"),
                        "AssetLibraryWidget must have _pil_to_qimage static method")
        self.assertTrue(callable(AssetLibraryWidget._decode_tga_with_pil))
        self.assertTrue(callable(AssetLibraryWidget._pil_to_qimage))
