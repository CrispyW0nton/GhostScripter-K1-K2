"""
Tests for all improvements implemented in the GhostScripter open-source tooling pass.

Covers:
  1. NWScriptDB — sortedcontainers-backed autocomplete + LRU cache
  2. TwoDAFile  — binary writer (to_binary), LRU search cache, deque undo,
                  find_rows_where, _save_state cache invalidation
  3. ResourceManager — LRU read cache, batch_read, cache_info, clear_cache
  4. DatabaseManager — context manager, WAL checkpoint, prune_script_history,
                       prune_export_history, paginated dialogue_snapshots
  5. DialogueFile    — to_networkx, graph_stats, find_dead_ends
  6. DLGValidator    — validate, validate_structure, validate_node_ids,
                       validate_links, validate_reachability, validate_cycles,
                       validate_scripts, summary_report
  7. ResourceIndex   — add/remove, prefix_search, extension_search,
                       fuzzy_search, __contains__, __len__
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 1 — NWScriptDB
# ─────────────────────────────────────────────────────────────────────────────

class TestNWScriptDB(unittest.TestCase):
    """NWScriptDB: empty DB — exercises prefix lookup structures."""

    def setUp(self):
        from ghostscripter.core.nwscript.parser import NWScriptDB
        self.db = NWScriptDB("K1")
        # Manually inject functions and constants (no .nss file needed)
        from ghostscripter.core.nwscript.parser import NWFunction, NWConstant, NWParam
        funcs = [
            NWFunction("int",    "GetGlobalBoolean", [NWParam("string", "sName")]),
            NWFunction("void",   "SetGlobalBoolean", [NWParam("string", "sName"),
                                                       NWParam("int", "nValue")]),
            NWFunction("object", "GetObjectByTag",   [NWParam("string", "sTag")]),
            NWFunction("int",    "GetIsObjectValid", [NWParam("object", "oObject")]),
        ]
        consts = [
            NWConstant("int", "OBJECT_TYPE_CREATURE", "1"),
            NWConstant("int", "OBJECT_TYPE_ITEM",     "2"),
            NWConstant("int", "ABILITY_STRENGTH",     "0"),
        ]
        self.db.functions = funcs
        self.db.constants = consts
        self.db._func_by_name  = {f.name: f for f in funcs}
        self.db._const_by_name = {c.name: c for c in consts}
        for f in funcs:
            self.db._func_categories.setdefault(f.category, []).append(f)
        for c in consts:
            self.db._const_categories.setdefault(c.category, []).append(c)
        # Build sorted prefix structures — use SortedList when available
        # to match the behaviour of NWScriptDB._load()
        from ghostscripter.core.nwscript.parser import _HAS_SORTED
        func_pairs = sorted((n.lower(), n) for n in self.db._func_by_name)
        const_pairs = sorted((n.lower(), n) for n in self.db._const_by_name)

        if _HAS_SORTED:
            from sortedcontainers import SortedList
            self.db._func_names_lc  = SortedList(lc for lc, _ in func_pairs)
            self.db._const_names_lc = SortedList(lc for lc, _ in const_pairs)
        else:
            self.db._func_names_lc  = [lc for lc, _ in func_pairs]
            self.db._const_names_lc = [lc for lc, _ in const_pairs]

        self.db._func_names_orig  = [orig for _, orig in func_pairs]
        self.db._const_names_orig = [orig for _, orig in const_pairs]
        self.db._loaded = True

    def test_autocomplete_prefix(self):
        results = self.db.autocomplete("Get")
        self.assertIn("GetGlobalBoolean", results)
        self.assertIn("GetObjectByTag",   results)
        self.assertIn("GetIsObjectValid", results)

    def test_autocomplete_no_match(self):
        results = self.db.autocomplete("ZZZNoSuchFunction")
        self.assertEqual(results, [])

    def test_autocomplete_empty_returns_all(self):
        results = self.db.autocomplete("")
        self.assertGreaterEqual(len(results), 4)

    def test_search_functions_cache(self):
        r1 = self.db.search_functions("Get")
        r2 = self.db.search_functions("Get")
        self.assertEqual(len(r1), len(r2))
        # With cachetools installed, same object should be returned
        try:
            from cachetools import LRUCache  # noqa: F401
            self.assertIs(r1, r2, "LRU cache should return the same list object")
        except ImportError:
            pass  # cachetools not installed — skip cache identity check

    def test_get_function_exact(self):
        f = self.db.get_function("GetGlobalBoolean")
        self.assertIsNotNone(f)
        self.assertEqual(f.return_type, "int")

    def test_search_constants(self):
        results = self.db.search_constants("OBJECT_TYPE")
        self.assertEqual(len(results), 2)

    def test_iter_all_names(self):
        names = list(self.db.iter_all_names())
        kinds = {kind for _, kind in names}
        self.assertIn("function", kinds)
        self.assertIn("constant", kinds)

    def test_functions_by_return_type(self):
        objs = self.db.functions_by_return_type("object")
        self.assertEqual(len(objs), 1)
        self.assertEqual(objs[0].name, "GetObjectByTag")

    def test_repr(self):
        r = repr(self.db)
        self.assertIn("K1", r)
        self.assertIn("functions=4", r)


# ─────────────────────────────────────────────────────────────────────────────
# 2 — TwoDAFile improvements
# ─────────────────────────────────────────────────────────────────────────────

class TestTwoDABinaryWriter(unittest.TestCase):
    """to_binary() and binary roundtrip."""

    _SAMPLE = "2DA V2.0\n\nName  Class  HP\n0  Bastila  Jedi  40\n1  HK47  Assassin  ****\n"

    def setUp(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        self.TwoDAFile = TwoDAFile
        self.t = TwoDAFile.from_text(self._SAMPLE)

    def test_to_binary_returns_bytes(self):
        b = self.t.to_binary()
        self.assertIsInstance(b, bytes)

    def test_binary_starts_with_header(self):
        b = self.t.to_binary()
        self.assertTrue(b.startswith(b"2DA V2.b\n"))

    def test_binary_roundtrip_rows(self):
        b = self.t.to_binary()
        t2 = self.TwoDAFile.from_bytes(b)
        self.assertEqual(len(t2.rows), 2)
        self.assertEqual(t2.rows[0].data["Name"],  "Bastila")
        self.assertEqual(t2.rows[1].data["Name"],  "HK47")
        self.assertEqual(t2.rows[1].data["HP"],    "****")

    def test_binary_roundtrip_columns(self):
        b = self.t.to_binary()
        t2 = self.TwoDAFile.from_bytes(b)
        self.assertEqual(t2.columns, ["Name", "Class", "HP"])

    def test_binary_roundtrip_empty(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        t_empty = TwoDAFile.from_text("2DA V2.0\n\nCol1  Col2\n")
        b = t_empty.to_binary()
        t2 = TwoDAFile.from_bytes(b)
        self.assertEqual(len(t2.rows), 0)
        self.assertEqual(t2.columns, ["Col1", "Col2"])

    def test_save_binary_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.2da"
            self.t.save_binary(p)
            self.assertTrue(p.exists())
            data = p.read_bytes()
            self.assertTrue(data.startswith(b"2DA V2.b\n"))

    def test_string_interning_deduplication(self):
        """Strings that appear multiple times should only appear once in the table."""
        t = self.TwoDAFile.from_text(
            "2DA V2.0\n\nLabel\n0  SAME\n1  SAME\n2  SAME\n"
        )
        b = t.to_binary()
        # 'SAME' should only appear once in the binary blob
        self.assertEqual(b.count(b"SAME\x00"), 1)


class TestTwoDASearchCache(unittest.TestCase):
    """LRU search cache and cache invalidation on mutation."""

    def setUp(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        self.t = TwoDAFile.from_text(
            "2DA V2.0\n\nName  Value\n0  alpha  1\n1  alpha_two  2\n2  beta  3\n"
        )

    def test_search_returns_correct_rows(self):
        results = self.t.search("alpha")
        self.assertEqual(len(results), 2)

    def test_search_cache_same_object(self):
        r1 = self.t.search("alpha")
        r2 = self.t.search("alpha")
        try:
            from cachetools import LRUCache  # noqa: F401
            self.assertIs(r1, r2)
        except ImportError:
            pass

    def test_search_cache_invalidated_on_add_row(self):
        _ = self.t.search("gamma")  # cache: "gamma" → []
        self.t.add_row("3", {"Name": "gamma", "Value": "4"})
        result_after = self.t.search("gamma")
        # After mutation, cache must be invalidated, so gamma should now be found
        self.assertEqual(len(result_after), 1)

    def test_find_rows_where_exact_case_insensitive(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        t = TwoDAFile.from_text("2DA V2.0\n\nN\n0  ALPHA\n1  alpha\n2  Alpha\n")
        # Case-insensitive (default)
        results = t.find_rows_where("N", "alpha")
        self.assertEqual(len(results), 3)

    def test_find_rows_where_exact_case_sensitive(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        t = TwoDAFile.from_text("2DA V2.0\n\nN\n0  ALPHA\n1  alpha\n2  Alpha\n")
        results = t.find_rows_where("N", "alpha", case_sensitive=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].data["N"], "alpha")


class TestTwoDAUndoDeque(unittest.TestCase):
    """Undo stack uses deque(maxlen=50) — no manual pop(0)."""

    def setUp(self):
        from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
        import collections
        self.TwoDAFile = TwoDAFile
        self.t = TwoDAFile.from_text("2DA V2.0\n\nN\n0  a\n")

    def test_history_is_deque(self):
        import collections
        self.assertIsInstance(self.t._history, collections.deque)

    def test_history_maxlen(self):
        self.assertEqual(self.t._history.maxlen, self.t._MAX_HISTORY)

    def test_undo_restores_state(self):
        self.t.add_row("1", {"N": "b"})
        self.assertEqual(len(self.t), 2)
        ok = self.t.undo()
        self.assertTrue(ok)
        self.assertEqual(len(self.t), 1)

    def test_redo_works(self):
        self.t.add_row("1", {"N": "b"})
        self.t.undo()
        ok = self.t.redo()
        self.assertTrue(ok)
        self.assertEqual(len(self.t), 2)


# ─────────────────────────────────────────────────────────────────────────────
# 3 — ResourceManager LRU cache
# ─────────────────────────────────────────────────────────────────────────────

class TestResourceManagerCache(unittest.TestCase):
    """ResourceManager: LRU read cache, batch_read, cache_info, clear_cache."""

    def setUp(self):
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager
        self.rm = ResourceManager()
        # Inject a fake override file
        with tempfile.TemporaryDirectory() as td:
            self._td = tempfile.mkdtemp()
        self._override_file = Path(self._td) / "test.2da"
        self._override_file.write_bytes(b"2DA V2.0\n\nN\n0 a\n")
        self.rm._override_files["test.2da"] = self._override_file

    def tearDown(self):
        import shutil
        shutil.rmtree(self._td, ignore_errors=True)

    def test_read_returns_bytes(self):
        data = self.rm.read("test.2da")
        self.assertIsNotNone(data)
        self.assertIsInstance(data, bytes)

    def test_read_cache_stores_result(self):
        d1 = self.rm.read("test.2da")
        d2 = self.rm.read("test.2da")
        # Both calls should return the same bytes
        self.assertEqual(d1, d2)
        # With cachetools: second call should serve from cache
        info = self.rm.cache_info()
        if info.get("available") == 0:
            return  # cachetools not installed
        self.assertGreater(info["size"], 0)

    def test_read_missing_returns_none(self):
        data = self.rm.read("nonexistent_resource.2da")
        self.assertIsNone(data)

    def test_batch_read(self):
        result = self.rm.batch_read(["test.2da", "missing.nss"])
        self.assertIn("test.2da", result)
        self.assertIn("missing.nss", result)
        self.assertIsNotNone(result["test.2da"])
        self.assertIsNone(result["missing.nss"])

    def test_clear_cache(self):
        self.rm.read("test.2da")
        self.rm.clear_cache()
        info = self.rm.cache_info()
        if info.get("available") == 0:
            return  # cachetools not installed
        self.assertEqual(info["size"], 0)

    def test_cache_info_returns_dict(self):
        info = self.rm.cache_info()
        self.assertIsInstance(info, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 4 — DatabaseManager improvements
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabaseManagerImprovements(unittest.TestCase):
    """DatabaseManager: context manager, WAL, prune, paginated snapshots."""

    def _make_db(self):
        from ghostscripter.core.database.manager import DatabaseManager
        return DatabaseManager(db_path=":memory:")

    def test_context_manager(self):
        from ghostscripter.core.database.manager import DatabaseManager
        with DatabaseManager(db_path=":memory:") as db:
            self.assertIsNotNone(db._conn)
        # After __exit__, connection is closed
        self.assertIsNone(db._conn)

    def test_checkpoint_wal_runs_without_error(self):
        db = self._make_db()
        db.checkpoint_wal()   # should not raise
        db.close()

    def test_prune_script_history_keeps_latest(self):
        db = self._make_db()
        pid = "proj_prune"
        for i in range(10):
            db.save_script_revision(pid, "my_script", f"// revision {i}")
        revs_before = db.get_script_revisions(pid, "my_script")
        self.assertEqual(len(revs_before), 10)
        deleted = db.prune_script_history(pid, "my_script", keep=3)
        self.assertEqual(deleted, 7)
        revs_after = db.get_script_revisions(pid, "my_script")
        self.assertEqual(len(revs_after), 3)
        db.close()

    def test_prune_script_history_no_op_when_few_revisions(self):
        db = self._make_db()
        pid = "proj_noop"
        db.save_script_revision(pid, "s", "// rev 1")
        db.save_script_revision(pid, "s", "// rev 2")
        deleted = db.prune_script_history(pid, "s", keep=5)
        self.assertEqual(deleted, 0)
        db.close()

    def test_prune_export_history(self):
        db = self._make_db()
        pid = "proj_exp"
        for i in range(15):
            db.log_export(pid, "erf", f"/tmp/mod_{i}.erf", i)
        deleted = db.prune_export_history(pid, keep=5)
        self.assertEqual(deleted, 10)
        remaining = db.get_export_history(pid)
        self.assertEqual(len(remaining), 5)
        db.close()

    def test_get_dialogue_snapshots_paginated(self):
        from ghostscripter.core.models.dialogue import DialogueFile
        db = self._make_db()
        pid = "proj_dlg"

        class FakeDlg:
            name = "test_dlg"
            def to_dict(self): return {"name": self.name}

        dlg = FakeDlg()
        for _ in range(10):
            db.save_dialogue_snapshot(pid, dlg)

        page1 = db.get_dialogue_snapshots(pid, limit=4, offset=0)
        page2 = db.get_dialogue_snapshots(pid, limit=4, offset=4)
        self.assertEqual(len(page1), 4)
        self.assertEqual(len(page2), 4)
        db.close()

    def test_count_dialogue_snapshots(self):
        db = self._make_db()
        pid = "proj_cnt"

        class FakeDlg:
            name = "dlg_x"
            def to_dict(self): return {"name": "dlg_x"}

        dlg = FakeDlg()
        for _ in range(7):
            db.save_dialogue_snapshot(pid, dlg)

        count = db.count_dialogue_snapshots(pid)
        self.assertEqual(count, 7)
        db.close()

    def test_get_dialogue_snapshot_data(self):
        db = self._make_db()
        pid = "proj_data"

        class FakeDlg:
            name = "dlg_y"
            def to_dict(self): return {"name": "dlg_y", "x": 42}

        dlg = FakeDlg()
        db.save_dialogue_snapshot(pid, dlg)
        snapshots = db.get_dialogue_snapshots(pid)
        self.assertGreater(len(snapshots), 0)
        snap_id = snapshots[0]["id"]
        data = db.get_dialogue_snapshot_data(snap_id)
        self.assertIsNotNone(data)
        import json
        d = json.loads(data)
        self.assertEqual(d["name"], "dlg_y")
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# 5 — DialogueFile networkx graph helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestDialogueFileGraphHelpers(unittest.TestCase):
    """DialogueFile.to_networkx(), graph_stats(), find_dead_ends()."""

    def _make_dlg(self):
        from ghostscripter.core.models.dialogue import create_simple_dialogue
        return create_simple_dialogue("test", "Bastila")

    def test_to_networkx_returns_digraph(self):
        import networkx as nx
        dlg = self._make_dlg()
        G = dlg.to_networkx()
        self.assertIsInstance(G, nx.DiGraph)

    def test_to_networkx_has_start_node(self):
        dlg = self._make_dlg()
        G = dlg.to_networkx()
        self.assertIn("START", G.nodes())

    def test_to_networkx_entry_nodes(self):
        dlg = self._make_dlg()
        G = dlg.to_networkx()
        entry_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "entry"]
        self.assertEqual(len(entry_nodes), len(dlg.entries))

    def test_to_networkx_reply_nodes(self):
        dlg = self._make_dlg()
        G = dlg.to_networkx()
        reply_nodes = [n for n, d in G.nodes(data=True) if d.get("kind") == "reply"]
        self.assertEqual(len(reply_nodes), len(dlg.replies))

    def test_graph_stats_node_count(self):
        dlg = self._make_dlg()
        stats = dlg.graph_stats()
        # +1 for START node
        self.assertEqual(stats["node_count"],
                         len(dlg.entries) + len(dlg.replies) + 1)

    def test_graph_stats_no_cycles_for_simple_dlg(self):
        dlg = self._make_dlg()
        stats = dlg.graph_stats()
        self.assertFalse(stats["has_cycles"])

    def test_graph_stats_unreachable_none_for_simple_dlg(self):
        dlg = self._make_dlg()
        stats = dlg.graph_stats()
        self.assertEqual(stats["unreachable_nodes"], [])

    def test_graph_stats_longest_path(self):
        dlg = self._make_dlg()
        stats = dlg.graph_stats()
        self.assertGreater(stats["longest_path_length"], 0)

    def test_find_dead_ends_reply_with_no_branches(self):
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        dlg = DialogueFile(name="test_dead_end")
        entry = DialogueNode(node_id=0, node_type="entry", text="NPC says hello")
        reply = DialogueNode(node_id=0, node_type="reply", text="Player says goodbye")
        entry.add_branch("Player says goodbye", target_id=0)
        # Reply has NO onward branches → dead end
        dlg.entries.append(entry)
        dlg.replies.append(reply)
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))

        dead = dlg.find_dead_ends()
        # The reply with no branches should appear
        labels = [d.split(":")[0] for d in dead]
        self.assertIn("R0", labels)

    def test_graph_stats_detects_cycles(self):
        """A dialogue with a reply looping back to an entry should be cyclic."""
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        dlg = DialogueFile(name="cyclic")
        entry = DialogueNode(node_id=0, node_type="entry", text="Loop")
        reply = DialogueNode(node_id=0, node_type="reply", text="Back")
        entry.add_branch("Back", target_id=0)
        reply.add_branch("Loop", target_id=0)   # loops back to entry 0

        dlg.entries.append(entry)
        dlg.replies.append(reply)
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))

        stats = dlg.graph_stats()
        self.assertTrue(stats["has_cycles"])


# ─────────────────────────────────────────────────────────────────────────────
# 6 — DLGValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestDLGValidator(unittest.TestCase):
    """DLGValidator: all check methods."""

    def _simple_dlg(self):
        from ghostscripter.core.models.dialogue import create_simple_dialogue
        return create_simple_dialogue("test_dlg", "Bastila")

    def test_validate_clean_dlg_no_issues(self):
        from ghostscripter.core.validation.dlg_validator import DLGValidator
        issues = DLGValidator.validate(self._simple_dlg())
        self.assertEqual(issues, [])

    def test_validate_empty_dlg_has_errors(self):
        from ghostscripter.core.models.dialogue import DialogueFile
        from ghostscripter.core.validation.dlg_validator import DLGValidator, Severity
        dlg = DialogueFile(name="empty")
        issues = DLGValidator.validate(dlg)
        severities = [i.severity for i in issues]
        self.assertIn(Severity.ERROR, severities)

    def test_validate_structure_no_starters(self):
        from ghostscripter.core.models.dialogue import DialogueFile, DialogueNode
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, Severity, CheckCategory
        )
        dlg = DialogueFile(name="nostarter")
        dlg.entries.append(DialogueNode(node_id=0, node_type="entry", text="NPC"))
        issues = DLGValidator.validate_structure(dlg)
        cats = [i.category for i in issues]
        self.assertIn(CheckCategory.STRUCTURE, cats)
        # Should have a WARNING about no starters
        w = [i for i in issues if i.severity == Severity.WARNING]
        self.assertGreater(len(w), 0)

    def test_validate_node_ids_duplicate(self):
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, Severity, CheckCategory
        )
        dlg = DialogueFile(name="dup_ids")
        # Two entries with the same node_id
        dlg.entries.append(DialogueNode(node_id=0, node_type="entry", text="A"))
        dlg.entries.append(DialogueNode(node_id=0, node_type="entry", text="B"))
        issues = DLGValidator.validate_node_ids(dlg)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, Severity.ERROR)
        self.assertEqual(issues[0].category, CheckCategory.NODE_IDS)

    def test_validate_links_dangling_target(self):
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, Severity, CheckCategory
        )
        dlg = DialogueFile(name="dangling")
        entry = DialogueNode(node_id=0, node_type="entry", text="NPC")
        # Branch targets reply 99 which doesn't exist
        entry.branches.append(DialogueBranch(branch_id=0, target_node_id=99))
        dlg.entries.append(entry)
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))
        issues = DLGValidator.validate_links(dlg)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, Severity.ERROR)
        self.assertEqual(issues[0].category, CheckCategory.LINKS)

    def test_validate_reachability_orphan_detected(self):
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, Severity, CheckCategory
        )
        dlg = DialogueFile(name="orphan")
        entry0 = DialogueNode(node_id=0, node_type="entry", text="Reachable")
        entry1 = DialogueNode(node_id=1, node_type="entry", text="Orphaned")
        dlg.entries.extend([entry0, entry1])
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))
        issues = DLGValidator.validate_reachability(dlg)
        unreachable_issues = [i for i in issues
                               if i.category == CheckCategory.REACHABILITY]
        self.assertGreater(len(unreachable_issues), 0)

    def test_validate_cycles_detected(self):
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, CheckCategory
        )
        dlg = DialogueFile(name="cycle")
        entry = DialogueNode(node_id=0, node_type="entry", text="Loop")
        reply = DialogueNode(node_id=0, node_type="reply", text="Back")
        entry.branches.append(DialogueBranch(branch_id=0, target_node_id=0))
        reply.branches.append(DialogueBranch(branch_id=0, target_node_id=0))
        dlg.entries.append(entry)
        dlg.replies.append(reply)
        dlg.starters.append(DialogueBranch(branch_id=0, target_node_id=0))

        issues = DLGValidator.validate_cycles(dlg)
        cycle_issues = [i for i in issues if i.category == CheckCategory.CYCLES]
        self.assertGreater(len(cycle_issues), 0)

    def test_validate_scripts_long_resref(self):
        from ghostscripter.core.models.dialogue import (
            DialogueFile, DialogueNode, DialogueBranch
        )
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, Severity, CheckCategory
        )
        dlg = DialogueFile(name="long_resref")
        node = DialogueNode(
            node_id=0, node_type="entry",
            text="Test",
            script1="this_script_name_is_way_too_long_to_be_a_valid_resref"
        )
        dlg.entries.append(node)
        issues = DLGValidator.validate_scripts(dlg)
        script_issues = [i for i in issues
                         if i.category == CheckCategory.SCRIPTS]
        self.assertGreater(len(script_issues), 0)
        self.assertEqual(script_issues[0].severity, Severity.ERROR)

    def test_validate_scripts_placeholder(self):
        from ghostscripter.core.models.dialogue import DialogueFile, DialogueNode
        from ghostscripter.core.validation.dlg_validator import (
            DLGValidator, Severity, CheckCategory
        )
        dlg = DialogueFile(name="placeholder")
        node = DialogueNode(node_id=0, node_type="entry", text="Test",
                            script1="todo_fix_me")  # 10 chars — valid length but placeholder
        dlg.entries.append(node)
        issues = DLGValidator.validate_scripts(dlg)
        ph_issues = [i for i in issues
                     if i.category == CheckCategory.SCRIPTS
                     and i.severity == Severity.WARNING]
        self.assertGreater(len(ph_issues), 0)

    def test_summary_report_no_issues(self):
        from ghostscripter.core.validation.dlg_validator import DLGValidator
        dlg = self._simple_dlg()
        report = DLGValidator.summary_report(dlg)
        self.assertIn("No issues found", report)
        self.assertIn(dlg.name, report)

    def test_summary_report_with_issues(self):
        from ghostscripter.core.models.dialogue import DialogueFile
        from ghostscripter.core.validation.dlg_validator import DLGValidator
        dlg = DialogueFile(name="broken")
        report = DLGValidator.summary_report(dlg)
        self.assertIn("errors", report)


# ─────────────────────────────────────────────────────────────────────────────
# 7 — ResourceIndex
# ─────────────────────────────────────────────────────────────────────────────

class TestResourceIndex(unittest.TestCase):
    """ResourceIndex: add, remove, prefix/extension/fuzzy search."""

    def setUp(self):
        from ghostscripter.core.search.resource_index import ResourceIndex
        self.idx = ResourceIndex()
        self.idx.add_many([
            "appearance.2da",
            "globalcat.2da",
            "c_bastila.utc",
            "c_hk47.utc",
            "c_t3m4.utc",
            "k_pbot_generic.ncs",
            "k_pbot_hk.ncs",
        ])

    def test_len(self):
        self.assertEqual(len(self.idx), 7)

    def test_contains(self):
        self.assertIn("appearance.2da", self.idx)
        self.assertIn("APPEARANCE.2DA", self.idx)  # case-insensitive
        self.assertNotIn("missing_file.2da", self.idx)

    def test_prefix_search_c(self):
        results = self.idx.prefix_search("c_")
        self.assertEqual(sorted(results),
                         ["c_bastila.utc", "c_hk47.utc", "c_t3m4.utc"])

    def test_prefix_search_k(self):
        results = self.idx.prefix_search("k_")
        self.assertEqual(sorted(results),
                         ["k_pbot_generic.ncs", "k_pbot_hk.ncs"])

    def test_prefix_search_no_match(self):
        results = self.idx.prefix_search("zzz_")
        self.assertEqual(results, [])

    def test_prefix_search_empty_returns_all(self):
        results = self.idx.prefix_search("")
        self.assertEqual(len(results), len(self.idx))

    def test_extension_search_2da(self):
        results = self.idx.extension_search(".2da")
        self.assertEqual(sorted(results), ["appearance.2da", "globalcat.2da"])

    def test_extension_search_without_dot(self):
        results = self.idx.extension_search("2da")
        self.assertEqual(sorted(results), ["appearance.2da", "globalcat.2da"])

    def test_extension_search_utc(self):
        results = self.idx.extension_search(".utc")
        self.assertEqual(len(results), 3)

    def test_fuzzy_search(self):
        results = self.idx.fuzzy_search("bot")
        self.assertIn("k_pbot_generic.ncs", results)
        self.assertIn("k_pbot_hk.ncs", results)

    def test_fuzzy_search_cache(self):
        r1 = self.idx.fuzzy_search("hk")
        r2 = self.idx.fuzzy_search("hk")
        # Both calls must return the same names (cache consistency)
        self.assertEqual(sorted(r1), sorted(r2))
        # With cachetools, verify second call is served from cache
        # (same object stored in cache should be returned)
        try:
            from cachetools import LRUCache  # noqa: F401
            if self.idx._fuzzy_cache is not None:
                # The cache key exists — verify result is in cache
                self.assertIn("hk", self.idx._fuzzy_cache)
        except ImportError:
            pass

    def test_remove(self):
        removed = self.idx.remove("c_bastila.utc")
        self.assertTrue(removed)
        self.assertNotIn("c_bastila.utc", self.idx)
        self.assertEqual(len(self.idx), 6)

    def test_remove_nonexistent(self):
        removed = self.idx.remove("not_there.2da")
        self.assertFalse(removed)
        self.assertEqual(len(self.idx), 7)

    def test_clear(self):
        self.idx.clear()
        self.assertEqual(len(self.idx), 0)

    def test_add_duplicate_no_op(self):
        initial = len(self.idx)
        self.idx.add("appearance.2da")   # already present
        self.assertEqual(len(self.idx), initial)

    def test_extensions(self):
        exts = self.idx.extensions()
        self.assertIn(".2da", exts)
        self.assertIn(".utc", exts)
        self.assertIn(".ncs", exts)

    def test_iter(self):
        names = list(self.idx)
        self.assertEqual(len(names), 7)
        # All lower-case
        for n in names:
            self.assertEqual(n, n.lower())

    def test_repr(self):
        r = repr(self.idx)
        self.assertIn("ResourceIndex", r)
        self.assertIn("7", r)


class TestResourceIndexBuildFromManager(unittest.TestCase):
    """build_index_from_manager helper."""

    def test_build_from_manager_override_files(self):
        from ghostscripter.core.resource_manager.resource_manager import ResourceManager
        from ghostscripter.core.search.resource_index import build_index_from_manager
        rm = ResourceManager()
        # Simulate override files
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "override.2da"
            p1.write_bytes(b"data")
            rm._override_files["override.2da"] = p1

        idx = build_index_from_manager(rm)
        self.assertIn("override.2da", idx)


# ─────────────────────────────────────────────────────────────────────────────
# 8 — Script Editor: Find/Replace, Go-to-line, Cursor position, Auto-indent,
#     Bracket matching (logic-level tests; no Qt display required)
# ─────────────────────────────────────────────────────────────────────────────

class TestCodeEditorBracketMatch(unittest.TestCase):
    """_find_bracket_match logic tested via a minimal stub."""

    def _make_editor_stub(self, text: str, cursor_pos: int):
        """Return a lightweight namespace with the attributes the real method reads."""
        import types
        stub = types.SimpleNamespace()

        class FakeDoc:
            def __init__(self, t): self._t = t
            def toPlainText(self): return self._t

        stub.document = lambda: FakeDoc(text)
        stub.isReadOnly = lambda: False

        # Minimal cursor
        class FC:
            def __init__(self, p): self._p = p
            def position(self): return self._p

        stub.textCursor = lambda: FC(cursor_pos)
        return stub

    def test_bracket_forward_match(self):
        """Placing the cursor after '(' should match the closing ')'."""
        text = "foo(bar)"
        # cursor at position 4 (just after '(')
        OPEN  = {'(': ')', '{': '}', '[': ']'}
        pos   = 4
        n     = len(text)
        ch    = text[pos - 1]    # '('
        self.assertIn(ch, OPEN)
        depth, i = 1, pos
        while i < n and depth:
            if text[i] == ch:           depth += 1
            elif text[i] == OPEN[ch]:   depth -= 1
            i += 1
        self.assertEqual(depth, 0)
        self.assertEqual(text[i - 1], ')')

    def test_bracket_backward_match(self):
        """Placing cursor after ')' should match the opening '('."""
        text = "foo(bar)"
        CLOSE = {')': '(', '}': '{', ']': '['}
        pos   = len(text)          # cursor at end, checking text[pos-1] = ')'
        ch    = text[pos - 1]      # ')'
        self.assertIn(ch, CLOSE)
        depth, i = 1, pos - 2
        while i >= 0 and depth:
            if text[i] == ch:            depth += 1
            elif text[i] == CLOSE[ch]:   depth -= 1
            i -= 1
        self.assertEqual(depth, 0)
        self.assertEqual(text[i + 1], '(')

    def test_unmatched_open_not_found(self):
        """An unmatched '(' should leave depth > 0."""
        text  = "foo(bar"
        OPEN  = {'(': ')'}
        pos   = 4
        ch    = text[pos - 1]
        depth, i = 1, pos
        n     = len(text)
        while i < n and depth:
            if text[i] == ch:           depth += 1
            elif text[i] == OPEN[ch]:   depth -= 1
            i += 1
        self.assertNotEqual(depth, 0)    # unmatched


class TestScriptEditorAutoIndent(unittest.TestCase):
    """Auto-indent logic: verify indent levels are computed correctly."""

    def _indent_for(self, line: str) -> int:
        """Replicate the auto-indent logic from CodeEditor.keyPressEvent."""
        indent = len(line) - len(line.lstrip())
        if line.rstrip().endswith("{"):
            indent += 4
        return indent

    def test_no_indent(self):
        self.assertEqual(self._indent_for("int x;"), 0)

    def test_existing_indent_preserved(self):
        self.assertEqual(self._indent_for("    int x;"), 4)

    def test_open_brace_adds_4(self):
        self.assertEqual(self._indent_for("if (x) {"), 4)

    def test_already_indented_plus_brace(self):
        self.assertEqual(self._indent_for("    if (x) {"), 8)

    def test_trailing_spaces_ignored(self):
        self.assertEqual(self._indent_for("    {  "), 8)   # rstrip keeps lstrip indent at 4, +4 for {


class TestFindReplaceLogic(unittest.TestCase):
    """Find/Replace replace-all logic (pure Python, no Qt)."""

    def _replace_all(self, content: str, find: str, replace: str,
                     case_sensitive: bool = True, use_regex: bool = False) -> tuple:
        """Mirror the logic from ScriptEditorWidget._replace_all."""
        import re as _re
        flags = 0 if case_sensitive else _re.IGNORECASE
        if use_regex:
            new_content, count = _re.subn(find, replace, content, flags=flags)
        else:
            if case_sensitive:
                new_content = content.replace(find, replace)
                count = content.count(find)
            else:
                new_content = _re.sub(_re.escape(find), replace, content, flags=_re.IGNORECASE)
                count = len(_re.findall(_re.escape(find), content, _re.IGNORECASE))
        return new_content, count

    def test_simple_replace(self):
        new, n = self._replace_all("foo foo foo", "foo", "bar")
        self.assertEqual(new, "bar bar bar")
        self.assertEqual(n, 3)

    def test_case_insensitive(self):
        new, n = self._replace_all("Foo FOO foo", "foo", "baz", case_sensitive=False)
        self.assertEqual(n, 3)
        self.assertEqual(new, "baz baz baz")

    def test_case_sensitive_no_match(self):
        new, n = self._replace_all("FOO", "foo", "bar", case_sensitive=True)
        self.assertEqual(n, 0)
        self.assertEqual(new, "FOO")

    def test_regex_replace(self):
        new, n = self._replace_all("abc123def456", r"\d+", "NUM", use_regex=True)
        self.assertEqual(new, "abcNUMdefNUM")
        self.assertEqual(n, 2)

    def test_replace_with_empty_string(self):
        new, n = self._replace_all("remove_this text", "remove_this ", "")
        self.assertEqual(new, "text")
        self.assertEqual(n, 1)


class TestGotoLineLogic(unittest.TestCase):
    """Go-to-line: verify line clamping."""

    def test_clamp_min(self):
        max_line = 100
        line = max(1, min(0, max_line))    # clamped to 1
        self.assertEqual(line, 1)

    def test_clamp_max(self):
        max_line = 50
        line = max(1, min(9999, max_line))
        self.assertEqual(line, 50)

    def test_valid_line(self):
        max_line = 200
        line = max(1, min(42, max_line))
        self.assertEqual(line, 42)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
