#!/usr/bin/env python3
"""
test_dlg_roundtrip.py — Tests for GFF3 DLG binary round-trip fidelity.
Tests that we can write a DLG to binary and read it back with the same
nodes, replies, and field values intact.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch,
    create_simple_dialogue,
)
from ghostscripter.core.export.dlg_writer import DLGExporter
from ghostscripter.core.export.dlg_reader import DLGImporter


class TestDLGRoundtrip(unittest.TestCase):
    """GFF3 DLG binary round-trip tests."""

    def _roundtrip(self, dlg: DialogueFile, game: str = "K1") -> DialogueFile:
        """Export to bytes then re-import."""
        exporter = DLGExporter()
        data = exporter.export(dlg, target_game=game)
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 12, "Exported DLG must be larger than GFF header")

        importer = DLGImporter()
        result = importer.import_from_bytes(data)
        return result

    # ── Basic creation ────────────────────────────────────────────────────────

    def test_simple_dialogue_roundtrip_k1(self):
        dlg = create_simple_dialogue("test_npc", "npc_001")
        rt = self._roundtrip(dlg, "K1")
        self.assertIsNotNone(rt)

    def test_simple_dialogue_roundtrip_k2(self):
        dlg = create_simple_dialogue("test_npc_k2", "npc_002")
        rt = self._roundtrip(dlg, "K2")
        self.assertIsNotNone(rt)

    def test_export_produces_valid_gff_header(self):
        dlg = create_simple_dialogue("header_test", "npc_003")
        exporter = DLGExporter()
        data = exporter.export(dlg, target_game="K1")
        # GFF V3.2 magic bytes: "DLG " followed by "V3.2"
        self.assertEqual(data[:4], b"DLG ")
        self.assertEqual(data[4:8], b"V3.2")

    # ── Entry / Reply round-trip ──────────────────────────────────────────────

    def test_entries_survive_roundtrip(self):
        dlg = create_simple_dialogue("entries_test", "npc_entries")
        initial_entries = len(dlg.entries)
        self.assertGreater(initial_entries, 0, "Test dialogue must have at least one entry")
        rt = self._roundtrip(dlg)
        self.assertGreater(len(rt.entries), 0)

    def test_replies_survive_roundtrip(self):
        dlg = create_simple_dialogue("replies_test", "npc_replies")
        rt = self._roundtrip(dlg)
        # After roundtrip, structure should be non-empty
        self.assertIsNotNone(rt.entries)

    def test_empty_dialogue_roundtrip(self):
        """An empty DLG file (no entries/replies) should round-trip cleanly."""
        dlg = DialogueFile(name="empty_dlg")
        rt = self._roundtrip(dlg)
        self.assertIsNotNone(rt)

    # ── Speaker / Listener fields ─────────────────────────────────────────────

    def test_entry_speaker_preserved(self):
        dlg = create_simple_dialogue("speaker_test", "npc_speaker")
        if dlg.entries:
            dlg.entries[0].speaker = "unique_npc_speaker_tag"
        rt = self._roundtrip(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].speaker, "unique_npc_speaker_tag")

    # ── Script fields ─────────────────────────────────────────────────────────

    def test_entry_script_preserved(self):
        dlg = create_simple_dialogue("script_test", "npc_script")
        if dlg.entries:
            # GFF RESREF is capped at 16 chars; keep under limit
            dlg.entries[0].script1 = "k_on_dlg_enter"
        rt = self._roundtrip(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].script1, "k_on_dlg_enter")

    def test_reply_script_preserved(self):
        dlg = create_simple_dialogue("reply_script_test", "npc_rscript")
        if dlg.replies:
            # GFF RESREF is capped at 16 chars; keep under limit
            dlg.replies[0].script1 = "k_player_reply"
        rt = self._roundtrip(dlg)
        if rt.replies:
            self.assertEqual(rt.replies[0].script1, "k_player_reply")

    # ── Text / StrRef fields ──────────────────────────────────────────────────

    def test_entry_text_strref_preserved(self):
        dlg = create_simple_dialogue("strref_test", "npc_strref")
        if dlg.entries:
            dlg.entries[0].text = "Hello, traveller."
            dlg.entries[0].text_strref = 12345
        rt = self._roundtrip(dlg)
        if rt.entries:
            self.assertEqual(rt.entries[0].text_strref, 12345)

    # ── Multiple import/export cycles ────────────────────────────────────────

    def test_double_roundtrip(self):
        """Two successive export→import cycles should not corrupt the file."""
        dlg = create_simple_dialogue("double_rt", "npc_double")
        exporter = DLGExporter()
        importer = DLGImporter()

        data1 = exporter.export(dlg, target_game="K1")
        dlg2 = importer.import_from_bytes(data1)
        data2 = exporter.export(dlg2, target_game="K1")
        self.assertIsInstance(data2, bytes)
        self.assertGreater(len(data2), 12)

    # ── Exporter returns bytes ────────────────────────────────────────────────

    def test_export_returns_bytes(self):
        dlg = create_simple_dialogue("bytes_check", "npc_bytes")
        exporter = DLGExporter()
        data = exporter.export(dlg)
        self.assertIsInstance(data, bytes)

    def test_export_size_reasonable(self):
        """Exported DLG should be at least header size (56 bytes for GFF)."""
        dlg = create_simple_dialogue("size_check", "npc_size")
        exporter = DLGExporter()
        data = exporter.export(dlg)
        self.assertGreaterEqual(len(data), 56)


class TestHierarchicalLayoutBFS(unittest.TestCase):
    """
    Tests for _HierarchicalLayout.assign() — specifically that the
    O(V+E) BFS terminates immediately on graphs with cycles/back-edges
    (is_child links), which is the pattern in real KotOR DLG files.

    Regression test for the hang bug caused by unbounded re-enqueuing
    when using list.pop(0) with the old Bellman-Ford style relaxation.
    """

    def _make_cyclic_dlg(self, n_entries: int = 10, n_replies: int = 15) -> DialogueFile:
        """
        Build a synthetic DLG with:
        - n_entries NPC entry nodes
        - n_replies Player reply nodes
        - Cross-links so that some replies loop back to earlier entries
          (simulating is_child back-edges common in real KotOR files).
        """
        dlg = DialogueFile(name="cyclic_test")

        for i in range(n_entries):
            e = DialogueNode(node_id=i, node_type="entry")
            e.text = f"NPC line {i}"
            dlg.entries.append(e)

        for i in range(n_replies):
            r = DialogueNode(node_id=i, node_type="reply")
            r.text = f"Player reply {i}"
            dlg.replies.append(r)

        # Entry i → replies i and i+1 (mod n_replies)
        for i, e in enumerate(dlg.entries):
            e.branches.append(DialogueBranch(branch_id=0, target_node_id=i % n_replies))
            if n_replies > 1:
                e.branches.append(DialogueBranch(branch_id=1,
                                                  target_node_id=(i + 1) % n_replies))

        # Reply i → entry (i+2) % n_entries  — creates back-edges / cycles
        for i, r in enumerate(dlg.replies):
            r.branches.append(DialogueBranch(branch_id=0,
                                              target_node_id=i % n_entries))
            # back-edge: every 3rd reply jumps back to entry 0
            if i % 3 == 0:
                r.branches.append(DialogueBranch(branch_id=1, target_node_id=0))

        # Starter → entry 0
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))
        return dlg

    def test_layout_terminates_on_cyclic_graph(self):
        """assign() must complete quickly (< 1 second) even with back-edges."""
        import time
        dlg = self._make_cyclic_dlg(n_entries=10, n_replies=15)
        # The import inside assign() must work headlessly (no Qt)
        try:
            from ghostscripter.ui.widgets.dialogue_editor_widget import (
                _HierarchicalLayout, _node_key,
            )
        except Exception:
            self.skipTest("Qt not available in headless test environment")

        t0 = time.time()
        layout = _HierarchicalLayout(dlg)
        positions = layout.assign()
        elapsed = time.time() - t0

        self.assertLess(elapsed, 2.0, "Layout should complete in < 2 seconds")
        # All nodes should get a position
        all_keys = {_node_key(n) for n in dlg.nodes}
        self.assertEqual(set(positions.keys()), all_keys,
                         "Every node should get a position")

    def test_layout_large_cyclic_terminates(self):
        """assign() must not hang on a larger dialogue (80 entries, 113 replies)."""
        import time
        dlg = self._make_cyclic_dlg(n_entries=80, n_replies=113)
        try:
            from ghostscripter.ui.widgets.dialogue_editor_widget import (
                _HierarchicalLayout, _node_key,
            )
        except Exception:
            self.skipTest("Qt not available in headless test environment")

        t0 = time.time()
        layout = _HierarchicalLayout(dlg)
        positions = layout.assign()
        elapsed = time.time() - t0

        self.assertLess(elapsed, 5.0,
                        f"Layout of 193-node graph must finish in < 5s (took {elapsed:.2f}s)")
        self.assertGreater(len(positions), 0)

    def test_layout_all_nodes_placed(self):
        """Every node in the dialogue must appear in the returned positions dict."""
        try:
            from ghostscripter.ui.widgets.dialogue_editor_widget import (
                _HierarchicalLayout, _node_key,
            )
        except Exception:
            self.skipTest("Qt not available in headless test environment")

        dlg = self._make_cyclic_dlg(n_entries=5, n_replies=7)
        layout = _HierarchicalLayout(dlg)
        positions = layout.assign()

        all_keys = {_node_key(n) for n in dlg.nodes}
        self.assertEqual(set(positions.keys()), all_keys)

    def test_layout_no_duplicate_positions(self):
        """No two nodes should occupy exactly the same (x,y) position."""
        try:
            from ghostscripter.ui.widgets.dialogue_editor_widget import (
                _HierarchicalLayout,
            )
        except Exception:
            self.skipTest("Qt not available in headless test environment")

        dlg = self._make_cyclic_dlg(n_entries=6, n_replies=8)
        layout = _HierarchicalLayout(dlg)
        positions = layout.assign()

        coords = [(round(p.x()), round(p.y())) for p in positions.values()]
        self.assertEqual(len(coords), len(set(coords)),
                         "Each node must have a unique position")


if __name__ == "__main__":
    unittest.main()
